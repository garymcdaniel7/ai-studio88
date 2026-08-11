"""Simulation Video Adapter — Story 143.

Wraps the existing SimulatedVideoProvider to implement the canonical
CanonicalVideoProvider contract. Always available, zero cost, instant
results. Used for development, testing, and CI without GPU.
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

# Simulation supports all models
SIMULATION_MODELS = [
    VideoModelInfo(
        id="wan-2.1",
        name="WAN 2.1 (Simulated)",
        provider="simulation",
        modes=[VideoMode.TEXT_TO_VIDEO, VideoMode.IMAGE_TO_VIDEO, VideoMode.VIDEO_TO_VIDEO],
        max_duration_seconds=30.0,
        max_resolution="2160x3840",
        default_resolution="832x480",
        default_fps=24,
        max_fps=30,
        min_frames=1,
        max_frames=720,
        vram_required_gb=0.0,
        supports_negative_prompt=True,
        supports_camera_motion=True,
        supports_seed=True,
        notes="Simulated — returns deterministic fake output instantly.",
    ),
    VideoModelInfo(
        id="hunyuan",
        name="HunyuanVideo (Simulated)",
        provider="simulation",
        modes=[VideoMode.TEXT_TO_VIDEO, VideoMode.IMAGE_TO_VIDEO],
        max_duration_seconds=10.0,
        max_resolution="1280x720",
        default_resolution="832x480",
        default_fps=24,
        max_fps=24,
        min_frames=1,
        max_frames=240,
        vram_required_gb=0.0,
        supports_negative_prompt=True,
        supports_camera_motion=False,
        supports_seed=True,
        notes="Simulated HunyuanVideo for testing.",
    ),
    VideoModelInfo(
        id="ltx",
        name="LTX Video (Simulated)",
        provider="simulation",
        modes=[VideoMode.TEXT_TO_VIDEO],
        max_duration_seconds=5.0,
        max_resolution="1280x720",
        default_resolution="768x512",
        default_fps=24,
        max_fps=24,
        min_frames=1,
        max_frames=120,
        vram_required_gb=0.0,
        supports_negative_prompt=True,
        supports_camera_motion=False,
        supports_seed=True,
        notes="Simulated LTX Video for testing.",
    ),
]


class SimulationVideoAdapter(CanonicalVideoProvider):
    """Canonical adapter wrapping the existing SimulatedVideoProvider.

    Always healthy, always available, zero cost. Useful for:
    - Development without GPU
    - CI/CD testing
    - UI development and demos
    - Fallback when no real provider is available
    """

    def __init__(self) -> None:
        self._config: VideoProviderConfig | None = None

    @property
    def name(self) -> str:
        return "simulation"

    @property
    def display_name(self) -> str:
        return "Simulation (Development)"

    # ─── Discovery ──────────────────────────────────────────────────────────

    def capabilities(self) -> VideoProviderCapabilities:
        return VideoProviderCapabilities(
            provider_name=self.name,
            modes=[VideoMode.TEXT_TO_VIDEO, VideoMode.IMAGE_TO_VIDEO, VideoMode.VIDEO_TO_VIDEO],
            models=SIMULATION_MODELS,
            max_concurrent_jobs=100,
            supports_cancellation=True,
            supports_progress=True,
            supports_cost_estimate=True,
            supports_priority=False,
            deployment_mode="local",
            notes="Simulated provider for development. No GPU required. Instant results.",
        )

    def health(self) -> VideoProviderHealth:
        return VideoProviderHealth(
            provider_name=self.name,
            status=VideoProviderStatus.AVAILABLE,
            message="Simulation provider is always available.",
            estimated_wait_seconds=0.0,
        )

    def list_models(self) -> list[VideoModelInfo]:
        return SIMULATION_MODELS

    # ─── Validation ─────────────────────────────────────────────────────────

    def validate_request(self, request: VideoGenerationRequest) -> VideoProviderError | None:
        # Simulation accepts almost everything
        if not request.prompt.strip() and request.mode == VideoMode.TEXT_TO_VIDEO:
            return VideoProviderError(
                code=VideoErrorCode.INVALID_INPUT,
                message="A text prompt is required for text-to-video generation.",
                provider_name=self.name,
            )
        return None

    # ─── Cost ───────────────────────────────────────────────────────────────

    def estimate_cost(self, request: VideoGenerationRequest) -> VideoCostEstimate:
        return VideoCostEstimate(
            estimated_cost_usd=0.0,
            confidence="fixed",
            message="Simulation is free — no GPU resources used.",
        )

    # ─── Execution ──────────────────────────────────────────────────────────

    def submit(
        self,
        request: VideoGenerationRequest,
        on_progress: Callable[[VideoGenerationProgress], None] | None = None,
    ) -> VideoGenerationResult:
        from backend.video.provider import VideoProgress, VideoRequest

        # Get the legacy simulation provider
        from backend.video.provider import SimulatedVideoProvider

        inner = SimulatedVideoProvider()

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
        )

        # Progress translation
        def translate_progress(p: VideoProgress) -> None:
            if on_progress:
                on_progress(VideoGenerationProgress(
                    percent=p.percent,
                    frame=p.frame,
                    total_frames=p.total_frames,
                    message=p.message,
                ))

        try:
            legacy_result = inner.submit(legacy_request, on_progress=translate_progress)
        except Exception as exc:
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.GENERATION_FAILED,
                error_message=str(exc),
                retryable=False,
                provider_name=self.name,
                model_used=request.model,
            )

        # Translate result
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
                cost_usd=0.0,
                provider_name=self.name,
                model_used=request.model,
                seed_used=legacy_result.metadata.get("seed"),
                metadata=legacy_result.metadata,
            )
        else:
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.GENERATION_FAILED,
                error_message=legacy_result.error or "Simulation failed",
                retryable=False,
                provider_name=self.name,
                model_used=request.model,
            )

    def cancel(self, provider_job_id: str) -> bool:
        # Simulation always accepts cancellation
        return True

    # ─── Lifecycle ──────────────────────────────────────────────────────────

    def initialize(self, config: VideoProviderConfig) -> None:
        self._config = config
        logger.info("Simulation video adapter initialized")

    def shutdown(self) -> None:
        pass
