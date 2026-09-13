"""Thunder H3 Provider — engine-level GenerationProvider for /generation/run.

Delegates to the canonical ThunderH3VideoAdapter (backend.video.adapters.
thunder_h3_adapter) which talks to Gary's Thunder Compute A6000 box ComfyUI.

Usage via /generation/run:
    POST /generation/run
    {
      "type": "video_generation",
      "provider": "thunder-h3",
      "prompt": "...",
      "negative_prompt": "...",
      "width": 768, "height": 1152, "steps": 8, "seed": 12345,
      "extra": {
        "first_frame": "/path/to/first.png",   # or http(s) URL, or
        "first_frame_b64": "...",              # base64-encoded image bytes
        "length": 226,                          # 226/243/260/277 (17k+5 grid)
        "model_loras": [{"filename": "...", "strength": 0.9}, ...],
        "out_prefix": "video/tsq_crawl"
      }
    }

The default LoRA stack (Male_Anatomy 0.9, JOKER141 motion repair 0.9,
turbo 8-step 1.0) is applied when model_loras is omitted.
"""

from __future__ import annotations

import logging
import os
import random
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv

from backend.engine.models import (
    GenerationOutput,
    GenerationProgress,
    GenerationRequest,
    ProviderCapabilities,
    ProviderHealth,
)
from backend.engine.provider import (
    GenerationProvider,
    ProviderError,
    ProviderExecutionError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)
load_dotenv()

COMFYUI_BASE_URL = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
COMFYUI_TIMEOUT = int(os.getenv("COMFYUI_API_TIMEOUT", os.getenv("COMFYUI_TIMEOUT_SECONDS", "1800")))


class ThunderH3Provider(GenerationProvider):
    """H3 image-to-video generation on Gary's Thunder box via ComfyUI."""

    def __init__(self, base_url: str | None = None, timeout: int | None = None) -> None:
        self._base_url = (base_url or COMFYUI_BASE_URL).rstrip("/")
        self._timeout = timeout or COMFYUI_TIMEOUT
        self._adapter: Any | None = None

    @property
    def name(self) -> str:
        return "thunder-h3"

    def health(self) -> ProviderHealth:
        from backend.video.adapters.thunder_h3_adapter import ThunderH3VideoAdapter

        adapter = self._get_adapter()
        health = adapter.health()
        return ProviderHealth(
            healthy=health.status.value == "available",
            provider_name=self.name,
            message=health.message,
            gpu_name=health.gpu_name,
            vram_total_gb=health.vram_total_gb,
            vram_free_gb=health.vram_free_gb,
            queue_size=health.queue_size,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            supports_image=False,
            supports_video=True,
            supports_upscale=False,
            supports_training=False,
            supports_voice=False,
            max_resolution=1152,
            supported_models=["thunder-h3"],
            max_batch_size=1,
        )

    def submit(
        self,
        request: GenerationRequest,
        on_progress: Callable[[GenerationProgress], None] | None = None,
    ) -> GenerationOutput:
        from backend.video.adapters.thunder_h3_adapter import (
            ThunderH3VideoAdapter,
            validate_h3_length,
        )
        from backend.video.contract import VideoGenerationRequest, VideoMode

        extra = request.extra or {}

        # Resolve the first frame from extra (path, URL, or base64 bytes).
        first_frame = extra.get("first_frame")
        first_frame_b64 = extra.get("first_frame_b64")
        if not first_frame and not first_frame_b64:
            raise ProviderExecutionError(
                self.name,
                "thunder-h3 requires an image-to-video first frame: "
                "pass extra.first_frame (local path or http(s) URL) or "
                "extra.first_frame_b64 (base64 image bytes).",
            )

        try:
            length = validate_h3_length(int(extra.get("length", extra.get("num_frames", 243))))
        except (TypeError, ValueError) as exc:
            raise ProviderExecutionError(self.name, str(exc)) from exc

        seed = request.seed if request.seed and request.seed > 0 else random.randint(1, 999999999)

        provider_options: dict = {
            "length": length,
            "steps": request.steps,
            "seed": seed,
            "out_prefix": extra.get("out_prefix", "video/tsq_crawl"),
        }
        if extra.get("model_loras"):
            provider_options["model_loras"] = extra["model_loras"]
        if first_frame:
            provider_options["first_frame_path"] = first_frame
        if first_frame_b64:
            provider_options["first_frame_b64"] = first_frame_b64

        canonical = VideoGenerationRequest(
            mode=VideoMode.IMAGE_TO_VIDEO,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            model="thunder-h3",
            duration_seconds=round(length / 24.0, 3),
            fps=24,
            width=request.width,
            height=request.height,
            seed=seed,
            steps=request.steps,
            org_id=None,
            user_id=None,
            project_id=request.project_id,
            talent_id=request.talent_id,
            provider_options=provider_options,
        )

        def translate_progress(p) -> None:
            if on_progress:
                on_progress(
                    GenerationProgress(
                        percent=p.percent,
                        message=p.message or "H3 generating on Thunder box...",
                    )
                )

        try:
            adapter = self._get_adapter()
            result = adapter.submit(canonical, on_progress=translate_progress)
        except Exception as exc:
            logger.exception("thunder_h3_engine_error")
            raise ProviderExecutionError(self.name, f"Thunder H3 generation failed: {exc}") from exc

        if not result.success:
            raise ProviderExecutionError(
                self.name,
                result.error_message or f"H3 generation failed (code={result.error_code.value if result.error_code else 'unknown'})",
            )

        if not result.output_bytes:
            raise ProviderExecutionError(self.name, "H3 provider returned no video bytes")

        return GenerationOutput(
            file_bytes=result.output_bytes,
            filename=result.filename,
            mime_type=result.mime_type or "video/mp4",
            width=result.width,
            height=result.height,
            seed_used=result.seed_used,
            generation_time_seconds=result.generation_time_seconds,
            metadata={
                **result.metadata,
                "provider": self.name,
                "model": "thunder-h3",
                "prompt_id": result.provider_job_id,
                "duration_seconds": result.duration_seconds,
            },
        )

    def cancel(self, job_id: str) -> bool:
        return self._get_adapter().cancel(job_id)

    def validate_workflow(self, workflow: dict) -> tuple[bool, str]:
        if not isinstance(workflow, dict) or not workflow:
            return False, "Workflow must be a non-empty dict"
        return True, ""

    # ─── Internal ───────────────────────────────────────────────────────────

    def _get_adapter(self):
        from backend.video.adapters.thunder_h3_adapter import ThunderH3VideoAdapter

        if self._adapter is None:
            self._adapter = ThunderH3VideoAdapter()
            from backend.video.contract import VideoProviderConfig

            self._adapter.initialize(
                VideoProviderConfig(
                    name="thunder-h3",
                    enabled=True,
                    priority=40,
                    settings={
                        "base_url": self._base_url,
                        "timeout_seconds": self._timeout,
                    },
                )
            )
        return self._adapter
