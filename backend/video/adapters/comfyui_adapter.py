"""ComfyUI/WAN Video Adapter — Story 143.

Wraps the existing ComfyUIVideoProvider to implement the canonical
CanonicalVideoProvider contract. All provider-specific behavior
(workflow loading, ComfyUI polling, WAN parameters) stays isolated here.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.video.contract import (
    CanonicalVideoProvider,
    VideoCostEstimate,
    VideoErrorCode,
    VideoGenerationProgress,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoJobStatus,
    VideoMode,
    VideoModelInfo,
    VideoProviderCapabilities,
    VideoProviderConfig,
    VideoProviderError,
    VideoProviderHealth,
    VideoProviderStatus,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# WAN 2.1 model definition
WAN_21_MODEL = VideoModelInfo(
    id="wan-2.1",
    name="WAN 2.1 (14B)",
    provider="comfyui-wan",
    modes=[VideoMode.TEXT_TO_VIDEO, VideoMode.IMAGE_TO_VIDEO],
    max_duration_seconds=10.0,
    max_resolution="1280x720",
    default_resolution="832x480",
    default_fps=24,
    max_fps=24,
    min_frames=17,
    max_frames=81,
    vram_required_gb=80.0,
    supports_negative_prompt=True,
    supports_camera_motion=False,
    supports_seed=True,
    notes="WAN 2.1 14B requires 80GB+ VRAM. Typical gen time: 3-10 min per 2s clip.",
)


class ComfyUIVideoAdapter(CanonicalVideoProvider):
    """Canonical adapter wrapping the existing ComfyUI/WAN video provider.

    Delegates actual generation to ComfyUIVideoProvider but translates
    requests and responses to/from the canonical contract.
    """

    def __init__(self) -> None:
        self._config: VideoProviderConfig | None = None
        self._inner: object | None = None  # Lazy — created on first use

    @property
    def name(self) -> str:
        return "comfyui-wan"

    @property
    def display_name(self) -> str:
        return "ComfyUI (WAN 2.1)"

    # ─── Discovery ──────────────────────────────────────────────────────────

    def capabilities(self) -> VideoProviderCapabilities:
        return VideoProviderCapabilities(
            provider_name=self.name,
            modes=[VideoMode.TEXT_TO_VIDEO, VideoMode.IMAGE_TO_VIDEO],
            models=[WAN_21_MODEL],
            max_concurrent_jobs=1,
            supports_cancellation=True,
            supports_progress=True,
            supports_cost_estimate=True,
            supports_priority=False,
            deployment_mode="cloud",
            notes="WAN 2.1 via ComfyUI on Vast.ai GPU workers",
        )

    def health(self) -> VideoProviderHealth:
        inner = self._get_inner()
        raw_health = inner.health()

        if raw_health.get("healthy"):
            return VideoProviderHealth(
                provider_name=self.name,
                status=VideoProviderStatus.AVAILABLE,
                gpu_name=raw_health.get("gpu_name"),
                vram_total_gb=raw_health.get("vram_total_gb"),
                vram_free_gb=raw_health.get("vram_free_gb"),
                queue_size=raw_health.get("queue_remaining", 0),
            )
        else:
            return VideoProviderHealth(
                provider_name=self.name,
                status=VideoProviderStatus.UNAVAILABLE,
                message=raw_health.get("error", "ComfyUI unreachable"),
            )

    def list_models(self) -> list[VideoModelInfo]:
        return [WAN_21_MODEL]

    # ─── Validation ─────────────────────────────────────────────────────────

    def validate_request(self, request: VideoGenerationRequest) -> VideoProviderError | None:
        # Mode check
        if request.mode == VideoMode.VIDEO_TO_VIDEO:
            return VideoProviderError(
                code=VideoErrorCode.UNSUPPORTED_MODE,
                message="ComfyUI/WAN does not support video-to-video. Use text_to_video or image_to_video.",
                provider_name=self.name,
            )

        # Duration check
        if request.duration_seconds > WAN_21_MODEL.max_duration_seconds:
            return VideoProviderError(
                code=VideoErrorCode.DURATION_EXCEEDED,
                message=f"Maximum duration is {WAN_21_MODEL.max_duration_seconds}s for WAN 2.1.",
                provider_name=self.name,
            )

        # Prompt required for t2v
        if request.mode == VideoMode.TEXT_TO_VIDEO and not request.prompt.strip():
            return VideoProviderError(
                code=VideoErrorCode.INVALID_INPUT,
                message="A text prompt is required for text-to-video generation.",
                provider_name=self.name,
            )

        # Image required for i2v
        if request.mode == VideoMode.IMAGE_TO_VIDEO:
            if not request.input_image_url and not request.input_image_bytes:
                return VideoProviderError(
                    code=VideoErrorCode.INVALID_INPUT,
                    message="An input image is required for image-to-video generation.",
                    provider_name=self.name,
                )

        return None

    # ─── Cost ───────────────────────────────────────────────────────────────

    def estimate_cost(self, request: VideoGenerationRequest) -> VideoCostEstimate:
        # WAN 2.1 on Vast.ai: ~$0.50-1.50/hr, typical gen 3-10 min
        # Rough estimate: $0.08-0.25 per 2s clip
        frames = int(request.duration_seconds * request.fps)
        # Approximate: ~$0.005 per frame at 80GB GPU rates
        estimated = round(frames * 0.005, 3)
        return VideoCostEstimate(
            estimated_cost_usd=estimated,
            confidence="estimate",
            breakdown={"frames": frames, "rate_per_frame_usd": 0.005},
            message=f"Estimated {frames} frames at ~$0.005/frame on Vast.ai GPU.",
        )

    # ─── Execution ──────────────────────────────────────────────────────────

    def submit(
        self,
        request: VideoGenerationRequest,
        on_progress: Callable[[VideoGenerationProgress], None] | None = None,
    ) -> VideoGenerationResult:
        from backend.video.provider import VideoProgress, VideoRequest

        inner = self._get_inner()

        # Translate canonical request → legacy VideoRequest
        legacy_request = VideoRequest(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            motion_prompt=request.motion_prompt,
            input_image_bytes=request.input_image_bytes,
            duration_seconds=request.duration_seconds,
            fps=request.fps,
            resolution=f"{request.width}x{request.height}",
            model=request.model,
            camera_motion=request.camera_motion,
            seed=request.seed,
            extra={
                "mode": request.mode.value,
                "steps": request.steps,
                "cfg": request.cfg_scale,
                **request.provider_options,
            },
        )

        # Progress callback translation
        def translate_progress(p: VideoProgress) -> None:
            if on_progress:
                on_progress(VideoGenerationProgress(
                    percent=p.percent,
                    frame=p.frame,
                    total_frames=p.total_frames,
                    message=p.message,
                ))

        # Execute via legacy provider
        try:
            legacy_result = inner.submit(legacy_request, on_progress=translate_progress)
        except Exception as exc:
            logger.error("ComfyUI video generation failed: %s", exc)
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.GENERATION_FAILED,
                error_message=str(exc),
                retryable=True,
                provider_name=self.name,
                model_used=request.model,
            )

        # Translate legacy result → canonical result
        if legacy_result.success:
            return VideoGenerationResult(
                success=True,
                status=VideoJobStatus.COMPLETED,
                output_bytes=legacy_result.output_bytes,
                filename=legacy_result.filename,
                mime_type=legacy_result.mime_type,
                duration_seconds=legacy_result.duration_seconds,
                fps=legacy_result.fps,
                width=request.width,
                height=request.height,
                generation_time_seconds=legacy_result.generation_time_seconds,
                provider_name=self.name,
                model_used=request.model,
                seed_used=legacy_result.metadata.get("seed"),
                metadata={
                    k: v for k, v in legacy_result.metadata.items()
                    if k not in ("prompt",)  # Don't duplicate large fields
                },
            )
        else:
            # Map error
            error_code = VideoErrorCode.GENERATION_FAILED
            retryable = True
            error_msg = legacy_result.error or "Generation failed"

            if "timeout" in error_msg.lower():
                error_code = VideoErrorCode.PROVIDER_TIMEOUT
            elif "not reachable" in error_msg.lower() or "unavailable" in error_msg.lower():
                error_code = VideoErrorCode.PROVIDER_UNAVAILABLE
            elif "workflow" in error_msg.lower() and "not found" in error_msg.lower():
                error_code = VideoErrorCode.INVALID_INPUT
                retryable = False

            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=error_code,
                error_message=error_msg,
                retryable=retryable,
                provider_name=self.name,
                model_used=request.model,
                generation_time_seconds=legacy_result.generation_time_seconds,
            )

    def cancel(self, provider_job_id: str) -> bool:
        inner = self._get_inner()
        return inner.cancel(provider_job_id)

    # ─── Lifecycle ──────────────────────────────────────────────────────────

    def initialize(self, config: VideoProviderConfig) -> None:
        self._config = config
        # Validate required settings
        settings = config.settings
        base_url = settings.get("base_url", "http://localhost:8188")
        if not base_url:
            raise ValueError("ComfyUI adapter requires 'base_url' in settings")
        # Don't test connectivity at init — health() handles that
        logger.info("ComfyUI video adapter initialized (url=%s)", base_url)

    def shutdown(self) -> None:
        self._inner = None

    # ─── Internal ───────────────────────────────────────────────────────────

    def _get_inner(self):
        """Lazy-load the legacy ComfyUIVideoProvider."""
        if self._inner is None:
            from backend.video.comfyui_provider import ComfyUIVideoProvider

            settings = self._config.settings if self._config else {}
            self._inner = ComfyUIVideoProvider(
                base_url=settings.get("base_url"),
                timeout=settings.get("timeout_seconds"),
                workflow_name=settings.get("workflow_template"),
            )
        return self._inner
