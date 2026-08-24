"""Video generation job handler.

Executes a ``video_generation`` job against the real video generation engine
(ComfyUI/WAN via ``backend.video``), uploads the resulting video bytes to
Backblaze B2, and returns a public URL for the job output.

This replaces the previous SimulationHandler shim so worker jobs produce real
videos when a ComfyUI/WAN provider is reachable. When ComfyUI is unavailable
(or no provider is configured), the handler falls back to the simulation
provider with a clear warning logged.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from backend.handlers.base import BaseHandler
from backend.storage import generate_storage_key, upload_file
from backend.video.contract import VideoMode
from backend.video.provider import (
    VideoProgress,
    VideoProvider,
    VideoRequest,
    get_video_provider,
)
from backend.video.registry import get_video_provider_registry

logger = logging.getLogger(__name__)

# Registry name used to prefer the real ComfyUI/WAN provider during selection.
_COMFYUI_REGISTRY_NAME = "comfyui-wan"
# Concrete provider name passed to get_video_provider for the ComfyUI engine.
_COMFYUI_PROVIDER_NAME = "comfyui"
_SIMULATION_PROVIDER_NAME = "simulation"

# Defaults applied when the job input omits optional fields.
_DEFAULT_MODEL = "wan-2.1"
_DEFAULT_DURATION = 5.0
_DEFAULT_WIDTH = 832
_DEFAULT_HEIGHT = 480
_DEFAULT_FPS = 24
_DEFAULT_SEED = -1


class VideoGenerationHandler(BaseHandler):
    """Generate a real video via the configured video provider and upload to B2."""

    @property
    def name(self) -> str:
        return "video_generation"

    def execute(self, job: dict, report_progress: Any) -> dict:
        job_input = job.get("input", {}) or {}
        provider = self._select_provider(job_input)
        request = self._build_request(job_input)

        logger.info(
            "Generating video: provider=%s model=%s duration=%ss prompt=%r",
            provider.name,
            request.model,
            request.duration_seconds,
            request.prompt[:80] if len(request.prompt) > 80 else request.prompt,
        )
        report_progress(1)

        result = provider.submit(request, on_progress=self._progress_callback(report_progress))

        if not result.success or not result.output_bytes:
            raise RuntimeError(result.error or "Video generation failed")

        storage_key = generate_storage_key(result.filename or "video.mp4", "video")
        video_url = upload_file(result.output_bytes, storage_key, result.mime_type)

        logger.info(
            "Video generation complete: provider=%s storage_key=%s size=%d bytes",
            provider.name,
            storage_key,
            len(result.output_bytes),
        )
        report_progress(100)

        return {
            "video_url": video_url,
            "duration_seconds": result.duration_seconds or request.duration_seconds,
            "provider": provider.name,
            "storage_provider": "backblaze_b2",
        }

    def _build_request(self, job_input: dict) -> VideoRequest:
        """Build a VideoRequest from the job input, applying sensible defaults."""
        width = int(job_input.get("width", _DEFAULT_WIDTH))
        height = int(job_input.get("height", _DEFAULT_HEIGHT))
        duration = float(
            job_input.get("duration_seconds", job_input.get("duration", _DEFAULT_DURATION))
        )
        return VideoRequest(
            prompt=job_input.get("prompt", ""),
            negative_prompt=job_input.get("negative_prompt", ""),
            motion_prompt=job_input.get("motion_prompt", ""),
            duration_seconds=duration,
            fps=int(job_input.get("fps", _DEFAULT_FPS)),
            resolution=f"{width}x{height}",
            model=job_input.get("model", _DEFAULT_MODEL),
            camera_motion=job_input.get("camera_motion", "static"),
            seed=int(job_input.get("seed", _DEFAULT_SEED)),
        )

    def _select_provider(self, job_input: dict) -> VideoProvider:
        """Prefer the real ComfyUI provider (via the registry); else simulation.

        Selection order:
        1. Ask the video provider registry to select a provider for the
           requested model, preferring ``comfyui-wan``.
        2. If the registry selects ComfyUI, verify it is actually reachable
           and fall back to simulation with a warning when it is not.
        3. If the registry selection fails or returns nothing, use simulation.

        Never raises — a missing or broken registry should not fail the job.
        """
        model = job_input.get("model", _DEFAULT_MODEL)
        provider_name = _SIMULATION_PROVIDER_NAME

        try:
            registry = get_video_provider_registry()
            selected = registry.select_provider(
                mode=VideoMode.TEXT_TO_VIDEO,
                model=model,
                preferred=_COMFYUI_REGISTRY_NAME,
            )
            if selected is not None:
                logger.info(
                    "Video provider registry selected '%s' for model %s",
                    selected.name,
                    model,
                )
                provider_name = _COMFYUI_PROVIDER_NAME
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Video provider registry selection failed; using simulation: %s", exc
            )

        provider = get_video_provider(provider_name)

        # If we landed on ComfyUI, verify it is reachable. When it is not,
        # FAIL FAST with a clear, actionable error instead of hanging on a
        # dead endpoint or silently returning a fake simulation URL.
        if provider.name == _COMFYUI_PROVIDER_NAME:
            try:
                health = provider.health()
                if not health.get("healthy"):
                    reason = health.get("error") or health.get("message") or "ComfyUI unreachable"
                    raise RuntimeError(
                        f"ComfyUI/WAN video engine unavailable: {reason}. "
                        "Start ComfyUI on the worker (COMFYUI_BASE_URL) before running "
                        "video_generation jobs."
                    )
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError(
                    f"ComfyUI/WAN health check failed: {exc}. "
                    "Start ComfyUI on the worker (COMFYUI_BASE_URL) before running "
                    "video_generation jobs."
                ) from exc

        return provider

    @staticmethod
    def _progress_callback(report_progress: Callable[[int], None]) -> Callable[[VideoProgress], None]:
        """Adapt a provider VideoProgress callback to the worker's 0-100 report."""

        def _on_progress(progress: VideoProgress) -> None:
            percent = int(getattr(progress, "percent", 0))
            report_progress(max(0, min(percent, 100)))

        return _on_progress
