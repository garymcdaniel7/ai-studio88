"""MiniMax H3 Video Adapter — Story 144.

Implements the canonical CanonicalVideoProvider contract for MiniMax H3,
a frontier omni-modal video generation model with native stereo audio.

Deployment mode: Hosted API only (api.minimax.io).
Self-hosted weights are territory-restricted (US/EU/UK/Korea excluded)
and are NOT implemented here.

Supported modes:
- Text-to-Video (prompt only)
- Image-to-Video (first-frame, last-frame, or both)
- Reference-to-Video (via provider_options — images, videos, audio refs)

Key constraints:
- Duration: 4–15 seconds (integer only)
- Output: 768P native, 2K via optional Regenerate API call
- FPS: 24 (fixed)
- Native stereo audio in all outputs (32 kHz)
- Cancellation: NOT supported
- Async workflow: submit → poll → download
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx

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


# =============================================================================
# Constants
# =============================================================================

# API endpoints
MINIMAX_API_BASE_GLOBAL = "https://api.minimax.io"
MINIMAX_API_BASE_CN = "https://api.minimaxi.com"

# Endpoint paths
CREATE_TASK_PATH = "/v1/video_generation"
QUERY_TASK_PATH = "/v1/query/video_generation"

# Model identifier
H3_MODEL_ID = "MiniMax-H3"

# Output constraints
H3_MIN_DURATION = 4
H3_MAX_DURATION = 15
H3_FPS = 24
H3_MAX_PROMPT_CHARS = 7000

# Input limits
H3_MAX_IMAGE_SIZE_MB = 30
H3_MAX_VIDEO_SIZE_MB = 50
H3_MAX_AUDIO_SIZE_MB = 15
H3_MAX_BODY_SIZE_MB = 64
H3_MAX_REFERENCE_IMAGES = 9
H3_MAX_REFERENCE_VIDEOS = 3
H3_MAX_REFERENCE_AUDIO = 3
H3_MAX_REFERENCE_TOTAL = 12

# Polling defaults
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_POLL_TIMEOUT_SECONDS = 600.0  # 10 minutes max wait
MAX_POLL_INTERVAL_SECONDS = 15.0

# Pricing (per second, approximate — sourced from AtlasCloud Jul 2026)
COST_PER_SECOND_768P = 0.10
COST_PER_SECOND_2K = 0.14

# Supported aspect ratios
SUPPORTED_ASPECT_RATIOS = [
    "21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive",
]

# Supported image formats
SUPPORTED_IMAGE_FORMATS = {"jpg", "jpeg", "png", "webp", "heic", "heif"}


# =============================================================================
# Model Definition
# =============================================================================

H3_MODEL = VideoModelInfo(
    id="minimax-h3",
    name="MiniMax H3 (Omni-Modal)",
    provider="minimax-h3",
    modes=[VideoMode.TEXT_TO_VIDEO, VideoMode.IMAGE_TO_VIDEO],
    max_duration_seconds=float(H3_MAX_DURATION),
    max_resolution="2560x1440",
    default_resolution="1365x768",
    default_fps=H3_FPS,
    max_fps=H3_FPS,
    min_frames=H3_MIN_DURATION * H3_FPS,
    max_frames=H3_MAX_DURATION * H3_FPS,
    vram_required_gb=0.0,  # Hosted API — no local VRAM needed
    supports_negative_prompt=False,
    supports_camera_motion=False,
    supports_seed=False,
    notes=(
        "MiniMax H3: omni-modal video+audio generation. "
        "768P native, 2K via Regenerate API. "
        "4-15s duration, 24 FPS, native 32kHz stereo audio. "
        "Hosted API only (api.minimax.io)."
    ),
)


# =============================================================================
# API Client
# =============================================================================


class MiniMaxH3Client:
    """HTTP client for the MiniMax H3 Video Generation API.

    Encapsulates authentication, request construction, polling, and
    response parsing. Never exposes the API token in logs or errors.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = MINIMAX_API_BASE_GLOBAL,
        timeout_seconds: float = 30.0,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def health_check(self) -> dict:
        """Verify API connectivity and authentication.

        Makes a lightweight query call to check credentials are valid.
        Returns a dict with 'healthy', 'message', and optional details.
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                # Use a dummy task_id query — a 404 with valid auth confirms connectivity
                resp = client.get(
                    f"{self._base_url}{QUERY_TASK_PATH}",
                    params={"task_id": "health_check_probe"},
                    headers=self._headers,
                )

            # Any response that isn't a connection/auth error = API is reachable
            if resp.status_code == 401:
                return {"healthy": False, "message": "Invalid API key"}
            if resp.status_code == 403:
                return {"healthy": False, "message": "API key lacks video permissions"}
            # 400/404 with valid auth means API is reachable
            return {"healthy": True, "message": "MiniMax API reachable"}

        except httpx.ConnectError as exc:
            return {"healthy": False, "message": f"Connection failed: {exc}"}
        except httpx.TimeoutException:
            return {"healthy": False, "message": "Connection timed out"}
        except Exception as exc:
            return {"healthy": False, "message": f"Health check error: {type(exc).__name__}"}

    def create_text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        prompt_optimizer: bool = True,
        callback_url: str | None = None,
    ) -> dict:
        """Submit a text-to-video generation task.

        Returns the raw API response dict with task_id on success.
        Raises MiniMaxAPIError on failure.
        """
        payload: dict = {
            "model": H3_MODEL_ID,
            "prompt": prompt,
            "duration": duration,
        }

        # H3 uses aspect_ratio for text-to-video
        if aspect_ratio and aspect_ratio != "adaptive":
            payload["aspect_ratio"] = aspect_ratio

        if not prompt_optimizer:
            payload["prompt_optimizer"] = False

        if callback_url:
            payload["callback_url"] = callback_url

        return self._create_task(payload)

    def create_image_to_video(
        self,
        prompt: str,
        first_frame_image: str | None = None,
        last_frame_image: str | None = None,
        duration: int = 5,
        callback_url: str | None = None,
    ) -> dict:
        """Submit a first/last-frame image-to-video generation task.

        Image URLs must be publicly accessible HTTP(S) URLs.
        Returns the raw API response dict with task_id on success.
        """
        payload: dict = {
            "model": H3_MODEL_ID,
            "prompt": prompt,
            "duration": duration,
        }

        if first_frame_image:
            payload["first_frame_image"] = first_frame_image
        if last_frame_image:
            payload["last_frame_image"] = last_frame_image

        if callback_url:
            payload["callback_url"] = callback_url

        return self._create_task(payload)

    def create_reference_to_video(
        self,
        prompt: str,
        image_urls: list[str] | None = None,
        video_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
        duration: int = 5,
        aspect_ratio: str = "adaptive",
        callback_url: str | None = None,
    ) -> dict:
        """Submit a reference-to-video generation task.

        At least one image or video reference is required.
        Audio cannot be the sole reference type.
        """
        payload: dict = {
            "model": H3_MODEL_ID,
            "prompt": prompt,
            "duration": duration,
        }

        if aspect_ratio and aspect_ratio != "adaptive":
            payload["aspect_ratio"] = aspect_ratio

        # Build source_list for H3 reference mode
        source_list: list[dict] = []
        if image_urls:
            for url in image_urls:
                source_list.append({"type": "image_url", "url": url})
        if video_urls:
            for url in video_urls:
                source_list.append({"type": "video_url", "url": url})
        if audio_urls:
            for url in audio_urls:
                source_list.append({"type": "audio_url", "url": url})

        if source_list:
            payload["source_list"] = source_list

        if callback_url:
            payload["callback_url"] = callback_url

        return self._create_task(payload)

    def query_task(self, task_id: str) -> dict:
        """Query the status of a video generation task.

        Returns the raw response body as a dict.
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(
                    f"{self._base_url}{QUERY_TASK_PATH}",
                    params={"task_id": task_id},
                    headers=self._headers,
                )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise MiniMaxAPIError(
                f"Query task failed (HTTP {exc.response.status_code})",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise MiniMaxAPIError(f"Network error querying task: {exc}") from exc

    def poll_until_complete(
        self,
        task_id: str,
        on_progress: Callable[[str, float], None] | None = None,
    ) -> dict:
        """Poll a task until completion, failure, or timeout.

        Args:
            task_id: The task ID returned by create_* methods.
            on_progress: Optional callback(status, elapsed_seconds).

        Returns:
            Final task query response dict on success.

        Raises:
            MiniMaxAPIError: On API errors during polling.
            MiniMaxTimeoutError: If poll_timeout is exceeded.
        """
        start = time.time()
        interval = self._poll_interval

        while True:
            elapsed = time.time() - start
            if elapsed > self._poll_timeout:
                raise MiniMaxTimeoutError(
                    f"Task {task_id} did not complete within {self._poll_timeout}s"
                )

            result = self.query_task(task_id)
            status = (result.get("status") or "").lower()

            if on_progress:
                on_progress(status, elapsed)

            if status in ("success", "succeeded"):
                return result
            elif status in ("failed", "fail", "error"):
                error_msg = result.get("base_resp", {}).get("status_msg", "Unknown error")
                raise MiniMaxAPIError(
                    f"Task {task_id} failed: {error_msg}",
                    details=result,
                )

            # Still processing — wait and retry with backoff
            time.sleep(interval)
            interval = min(interval * 1.2, MAX_POLL_INTERVAL_SECONDS)

    def download_video(self, video_url: str) -> bytes:
        """Download the generated video from the result URL.

        Result URLs expire after 24 hours — download immediately.
        """
        try:
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                resp = client.get(video_url)
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPStatusError as exc:
            raise MiniMaxAPIError(
                f"Video download failed (HTTP {exc.response.status_code})",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise MiniMaxAPIError(f"Video download network error: {exc}") from exc

    # ─── Internal ───────────────────────────────────────────────────────────

    def _create_task(self, payload: dict) -> dict:
        """Send a task creation request to the MiniMax API."""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._base_url}{CREATE_TASK_PATH}",
                    json=payload,
                    headers=self._headers,
                )

            # Parse response
            body = resp.json()

            # Check for API-level errors
            base_resp = body.get("base_resp", {})
            status_code = base_resp.get("status_code", 0)

            if status_code != 0:
                error_msg = base_resp.get("status_msg", "Unknown API error")
                raise MiniMaxAPIError(
                    f"Task creation failed: {error_msg}",
                    status_code=resp.status_code,
                    api_error_code=status_code,
                    details=body,
                )

            # HTTP-level errors
            if resp.status_code >= 400:
                raise MiniMaxAPIError(
                    f"HTTP {resp.status_code} from MiniMax API",
                    status_code=resp.status_code,
                    details=body,
                )

            task_id = body.get("task_id")
            if not task_id:
                raise MiniMaxAPIError(
                    "No task_id in API response",
                    details=body,
                )

            return body

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                raise MiniMaxAPIError("Authentication failed", status_code=401) from exc
            elif status == 429:
                raise MiniMaxRateLimitError("Rate limit exceeded") from exc
            raise MiniMaxAPIError(
                f"HTTP {status} error", status_code=status
            ) from exc
        except httpx.RequestError as exc:
            raise MiniMaxAPIError(f"Network error: {exc}") from exc


# =============================================================================
# Exceptions
# =============================================================================


class MiniMaxAPIError(Exception):
    """Base exception for MiniMax API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        api_error_code: int | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.api_error_code = api_error_code
        self.details = details or {}


class MiniMaxTimeoutError(MiniMaxAPIError):
    """Task polling timed out."""


class MiniMaxRateLimitError(MiniMaxAPIError):
    """API rate limit exceeded."""


# =============================================================================
# Canonical Adapter
# =============================================================================


class MiniMaxH3VideoAdapter(CanonicalVideoProvider):
    """Canonical adapter for MiniMax H3 video generation (hosted API).

    Implements the Story 143 CanonicalVideoProvider contract. All
    provider-specific logic (API calls, polling, response parsing) is
    isolated here. Shared orchestration sees only canonical types.

    Configuration (via VideoProviderConfig.settings):
        api_key: MiniMax API token (required)
        base_url: API base URL (default: https://api.minimax.io)
        poll_interval_seconds: Initial polling interval (default: 5)
        poll_timeout_seconds: Max wait for task completion (default: 600)
        enable_2k: Whether to use H3-Regenerate-2K (default: false)
        prompt_optimizer: Whether to use MiniMax prompt optimization (default: true)
    """

    def __init__(self) -> None:
        self._config: VideoProviderConfig | None = None
        self._client: MiniMaxH3Client | None = None

    @property
    def name(self) -> str:
        return "minimax-h3"

    @property
    def display_name(self) -> str:
        return "MiniMax H3 (Omni-Modal Video)"

    # ─── Discovery ──────────────────────────────────────────────────────────

    def capabilities(self) -> VideoProviderCapabilities:
        return VideoProviderCapabilities(
            provider_name=self.name,
            modes=[VideoMode.TEXT_TO_VIDEO, VideoMode.IMAGE_TO_VIDEO],
            models=[H3_MODEL],
            max_concurrent_jobs=5,
            supports_cancellation=False,
            supports_progress=True,
            supports_cost_estimate=True,
            supports_priority=False,
            deployment_mode="cloud",
            notes=(
                "MiniMax H3 hosted API. Generates video with native stereo audio. "
                "4-15s, 24fps, 768P/2K. Text-to-video, image-to-video, and "
                "reference-to-video (via provider_options). "
                "Cancellation not supported."
            ),
        )

    def health(self) -> VideoProviderHealth:
        """Check MiniMax API health.

        Distinguishes:
        - NOT_CONFIGURED: No API key set
        - AUTH_FAILED: Invalid credentials
        - UNAVAILABLE: Network/service unreachable
        - AVAILABLE: API reachable and authenticated
        """
        if not self._client:
            return VideoProviderHealth(
                provider_name=self.name,
                status=VideoProviderStatus.UNAVAILABLE,
                message="MiniMax H3 not configured (missing API key)",
            )

        result = self._client.health_check()

        if result["healthy"]:
            return VideoProviderHealth(
                provider_name=self.name,
                status=VideoProviderStatus.AVAILABLE,
                message=result["message"],
            )
        else:
            # Distinguish auth failure from connectivity
            msg = result["message"]
            if "Invalid API key" in msg or "lacks" in msg:
                status = VideoProviderStatus.UNAVAILABLE
            else:
                status = VideoProviderStatus.DEGRADED

            return VideoProviderHealth(
                provider_name=self.name,
                status=status,
                message=msg,
            )

    def list_models(self) -> list[VideoModelInfo]:
        return [H3_MODEL]

    # ─── Validation ─────────────────────────────────────────────────────────

    def validate_request(self, request: VideoGenerationRequest) -> VideoProviderError | None:
        """Pre-validate request against H3 constraints.

        Fails fast before any paid API call.
        """
        # Mode check
        if request.mode == VideoMode.VIDEO_TO_VIDEO:
            return VideoProviderError(
                code=VideoErrorCode.UNSUPPORTED_MODE,
                message=(
                    "MiniMax H3 does not support video-to-video mode. "
                    "Use text_to_video or image_to_video. For reference-based "
                    "generation, use provider_options with image/video/audio URLs."
                ),
                provider_name=self.name,
            )

        # Duration check (H3 requires integer 4-15)
        duration = int(request.duration_seconds)
        if duration < H3_MIN_DURATION:
            return VideoProviderError(
                code=VideoErrorCode.INVALID_INPUT,
                message=f"Minimum duration is {H3_MIN_DURATION}s for MiniMax H3.",
                provider_name=self.name,
            )
        if duration > H3_MAX_DURATION:
            return VideoProviderError(
                code=VideoErrorCode.DURATION_EXCEEDED,
                message=f"Maximum duration is {H3_MAX_DURATION}s for MiniMax H3.",
                provider_name=self.name,
            )

        # Prompt required
        if not request.prompt or not request.prompt.strip():
            return VideoProviderError(
                code=VideoErrorCode.INVALID_INPUT,
                message="A text prompt is required for all MiniMax H3 modes.",
                provider_name=self.name,
            )

        # Prompt length check
        if len(request.prompt) > H3_MAX_PROMPT_CHARS:
            return VideoProviderError(
                code=VideoErrorCode.INPUT_TOO_LARGE,
                message=f"Prompt exceeds {H3_MAX_PROMPT_CHARS} character limit.",
                provider_name=self.name,
            )

        # Image-to-video requires at least one image
        if request.mode == VideoMode.IMAGE_TO_VIDEO:
            has_image = bool(
                request.input_image_url
                or request.input_image_bytes
                or request.provider_options.get("first_frame_image")
                or request.provider_options.get("last_frame_image")
            )
            if not has_image:
                return VideoProviderError(
                    code=VideoErrorCode.INVALID_INPUT,
                    message=(
                        "Image-to-video requires at least one image. "
                        "Provide input_image_url or set first_frame_image / "
                        "last_frame_image in provider_options."
                    ),
                    provider_name=self.name,
                )

        # Reference mode validation (via provider_options)
        ref_images = request.provider_options.get("reference_images", [])
        ref_videos = request.provider_options.get("reference_videos", [])
        ref_audio = request.provider_options.get("reference_audio", [])

        if ref_images or ref_videos or ref_audio:
            total_refs = len(ref_images) + len(ref_videos) + len(ref_audio)
            if total_refs > H3_MAX_REFERENCE_TOTAL:
                return VideoProviderError(
                    code=VideoErrorCode.INPUT_TOO_LARGE,
                    message=f"Total reference files ({total_refs}) exceeds limit of {H3_MAX_REFERENCE_TOTAL}.",
                    provider_name=self.name,
                )
            if len(ref_images) > H3_MAX_REFERENCE_IMAGES:
                return VideoProviderError(
                    code=VideoErrorCode.INPUT_TOO_LARGE,
                    message=f"Max {H3_MAX_REFERENCE_IMAGES} reference images allowed.",
                    provider_name=self.name,
                )
            if len(ref_videos) > H3_MAX_REFERENCE_VIDEOS:
                return VideoProviderError(
                    code=VideoErrorCode.INPUT_TOO_LARGE,
                    message=f"Max {H3_MAX_REFERENCE_VIDEOS} reference videos allowed.",
                    provider_name=self.name,
                )
            if len(ref_audio) > H3_MAX_REFERENCE_AUDIO:
                return VideoProviderError(
                    code=VideoErrorCode.INPUT_TOO_LARGE,
                    message=f"Max {H3_MAX_REFERENCE_AUDIO} reference audio clips allowed.",
                    provider_name=self.name,
                )
            # Audio requires image or video
            if ref_audio and not ref_images and not ref_videos:
                return VideoProviderError(
                    code=VideoErrorCode.INVALID_INPUT,
                    message="Audio references require at least one image or video reference.",
                    provider_name=self.name,
                )

        return None

    # ─── Cost ───────────────────────────────────────────────────────────────

    def estimate_cost(self, request: VideoGenerationRequest) -> VideoCostEstimate:
        """Estimate cost based on duration and resolution.

        Pricing sourced from AtlasCloud (Jul 2026):
        - 768P: ~$0.10/sec
        - 2K: ~$0.14/sec
        """
        duration = max(H3_MIN_DURATION, min(int(request.duration_seconds), H3_MAX_DURATION))
        enable_2k = request.provider_options.get("enable_2k", False)

        if enable_2k:
            rate = COST_PER_SECOND_2K
            resolution = "2K"
        else:
            rate = COST_PER_SECOND_768P
            resolution = "768P"

        estimated = round(duration * rate, 3)

        return VideoCostEstimate(
            estimated_cost_usd=estimated,
            confidence="estimate",
            breakdown={
                "duration_seconds": duration,
                "rate_per_second_usd": rate,
                "resolution": resolution,
                "includes_audio": True,
            },
            message=f"MiniMax H3 {resolution}: {duration}s at ~${rate}/sec = ~${estimated:.3f}",
        )

    # ─── Execution ──────────────────────────────────────────────────────────

    def submit(
        self,
        request: VideoGenerationRequest,
        on_progress: Callable[[VideoGenerationProgress], None] | None = None,
    ) -> VideoGenerationResult:
        """Execute a video generation request via MiniMax H3 API.

        Workflow:
        1. Determine mode and build API request
        2. Submit task to MiniMax API
        3. Poll until completion or timeout
        4. Download the generated video
        5. Return canonical result with provenance
        """
        if not self._client:
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.PROVIDER_UNAVAILABLE,
                error_message="MiniMax H3 not configured (missing API key)",
                retryable=False,
                provider_name=self.name,
                model_used=H3_MODEL_ID,
            )

        start_time = time.time()
        duration = max(H3_MIN_DURATION, min(int(request.duration_seconds), H3_MAX_DURATION))
        aspect_ratio = request.provider_options.get("aspect_ratio", "16:9")
        prompt_optimizer = request.provider_options.get("prompt_optimizer", True)

        try:
            # Determine generation mode and submit
            task_response = self._submit_task(
                request, duration, aspect_ratio, prompt_optimizer
            )
            task_id = task_response.get("task_id", "")

            logger.info(
                "minimax_h3_task_submitted",
                extra={
                    "task_id": task_id,
                    "mode": request.mode.value,
                    "duration": duration,
                    "org_id": request.org_id,
                },
            )

            # Poll for completion with progress reporting
            def report_progress(status: str, elapsed: float) -> None:
                if on_progress:
                    # Estimate percent based on elapsed time vs expected
                    expected_time = duration * 10.0  # Rough: 10s compute per 1s output
                    percent = min(int((elapsed / expected_time) * 100), 95)
                    on_progress(VideoGenerationProgress(
                        percent=percent,
                        message=f"MiniMax H3: {status} ({elapsed:.0f}s elapsed)",
                        eta_seconds=max(0, expected_time - elapsed),
                    ))

            final_result = self._client.poll_until_complete(
                task_id, on_progress=report_progress
            )

            # Extract video URL from result
            video_url = self._extract_video_url(final_result)
            if not video_url:
                return VideoGenerationResult(
                    success=False,
                    status=VideoJobStatus.FAILED,
                    error_code=VideoErrorCode.OUTPUT_MISSING,
                    error_message="Task succeeded but no video URL in response",
                    retryable=True,
                    provider_name=self.name,
                    model_used=H3_MODEL_ID,
                    provider_job_id=task_id,
                    generation_time_seconds=round(time.time() - start_time, 2),
                )

            # Download the video
            video_bytes = self._client.download_video(video_url)

            # Parse output dimensions from result
            video_width = final_result.get("video_width", 1365)
            video_height = final_result.get("video_height", 768)

            generation_time = round(time.time() - start_time, 2)

            # Report 100% progress
            if on_progress:
                on_progress(VideoGenerationProgress(
                    percent=100,
                    message="Generation complete — video downloaded",
                ))

            return VideoGenerationResult(
                success=True,
                status=VideoJobStatus.COMPLETED,
                output_bytes=video_bytes,
                output_url=video_url,
                filename=f"minimax_h3_{task_id}.mp4",
                mime_type="video/mp4",
                duration_seconds=float(duration),
                fps=H3_FPS,
                width=video_width,
                height=video_height,
                generation_time_seconds=generation_time,
                cost_usd=round(duration * COST_PER_SECOND_768P, 3),
                provider_name=self.name,
                model_used=H3_MODEL_ID,
                provider_job_id=task_id,
                metadata={
                    "has_native_audio": True,
                    "audio_sample_rate_hz": 32000,
                    "audio_channels": "stereo",
                    "resolution_tier": "768P",
                    "aspect_ratio": aspect_ratio,
                    "prompt_optimizer_used": prompt_optimizer,
                },
            )

        except MiniMaxRateLimitError as exc:
            logger.warning("minimax_h3_rate_limited", extra={"org_id": request.org_id})
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.PROVIDER_RATE_LIMITED,
                error_message="MiniMax API rate limit exceeded. Retry after backoff.",
                retryable=True,
                provider_name=self.name,
                model_used=H3_MODEL_ID,
                generation_time_seconds=round(time.time() - start_time, 2),
            )

        except MiniMaxTimeoutError as exc:
            logger.error(
                "minimax_h3_timeout",
                extra={"org_id": request.org_id, "error": str(exc)},
            )
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.TIMED_OUT,
                error_code=VideoErrorCode.PROVIDER_TIMEOUT,
                error_message=str(exc),
                retryable=True,
                provider_name=self.name,
                model_used=H3_MODEL_ID,
                generation_time_seconds=round(time.time() - start_time, 2),
            )

        except MiniMaxAPIError as exc:
            logger.error(
                "minimax_h3_api_error",
                extra={
                    "org_id": request.org_id,
                    "status_code": exc.status_code,
                    "error": str(exc),
                },
            )
            # Map specific API errors
            error_code = VideoErrorCode.GENERATION_FAILED
            retryable = True

            if exc.status_code == 401:
                error_code = VideoErrorCode.PROVIDER_AUTH_FAILED
                retryable = False
            elif exc.status_code == 429:
                error_code = VideoErrorCode.PROVIDER_RATE_LIMITED
            elif exc.status_code and exc.status_code >= 500:
                error_code = VideoErrorCode.PROVIDER_UNAVAILABLE

            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=error_code,
                error_message=str(exc),
                retryable=retryable,
                provider_name=self.name,
                model_used=H3_MODEL_ID,
                generation_time_seconds=round(time.time() - start_time, 2),
            )

        except Exception as exc:
            logger.exception(
                "minimax_h3_unexpected_error",
                extra={"org_id": request.org_id},
            )
            return VideoGenerationResult(
                success=False,
                status=VideoJobStatus.FAILED,
                error_code=VideoErrorCode.UNKNOWN,
                error_message=f"Unexpected error: {type(exc).__name__}",
                retryable=False,
                provider_name=self.name,
                model_used=H3_MODEL_ID,
                generation_time_seconds=round(time.time() - start_time, 2),
            )

    def cancel(self, provider_job_id: str) -> bool:
        """MiniMax H3 does not support task cancellation.

        Per official documentation, H3 tasks cannot be cancelled once submitted.
        Always returns False.
        """
        logger.info(
            "minimax_h3_cancel_unsupported",
            extra={"task_id": provider_job_id},
        )
        return False

    # ─── Lifecycle ──────────────────────────────────────────────────────────

    def initialize(self, config: VideoProviderConfig) -> None:
        """Validate configuration and create the API client.

        Required settings:
            api_key: MiniMax API token

        Optional settings:
            base_url: API endpoint (default: https://api.minimax.io)
            poll_interval_seconds: Initial poll interval (default: 5)
            poll_timeout_seconds: Max poll duration (default: 600)
            enable_2k: Enable 2K regeneration (default: false)
            prompt_optimizer: Use MiniMax prompt optimizer (default: true)

        Raises ValueError if api_key is missing.
        """
        self._config = config
        settings = config.settings

        api_key = settings.get("api_key", "")
        if not api_key:
            raise ValueError(
                "MiniMax H3 requires 'api_key' in settings. "
                "Set VIDEO_PROVIDER_MINIMAX_H3_API_KEY environment variable."
            )

        base_url = settings.get("base_url", MINIMAX_API_BASE_GLOBAL)
        poll_interval = float(settings.get("poll_interval_seconds", DEFAULT_POLL_INTERVAL_SECONDS))
        poll_timeout = float(settings.get("poll_timeout_seconds", DEFAULT_POLL_TIMEOUT_SECONDS))

        self._client = MiniMaxH3Client(
            api_key=api_key,
            base_url=base_url,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )

        logger.info(
            "minimax_h3_initialized",
            extra={
                "base_url": base_url,
                "poll_timeout": poll_timeout,
                "enable_2k": settings.get("enable_2k", False),
            },
        )

    def shutdown(self) -> None:
        """Clean up resources."""
        self._client = None
        self._config = None

    # ─── Internal Helpers ───────────────────────────────────────────────────

    def _submit_task(
        self,
        request: VideoGenerationRequest,
        duration: int,
        aspect_ratio: str,
        prompt_optimizer: bool,
    ) -> dict:
        """Route to the correct MiniMax API method based on request mode."""
        # Check for reference-to-video (via provider_options)
        ref_images = request.provider_options.get("reference_images", [])
        ref_videos = request.provider_options.get("reference_videos", [])
        ref_audio = request.provider_options.get("reference_audio", [])

        if ref_images or ref_videos or ref_audio:
            return self._client.create_reference_to_video(
                prompt=request.prompt,
                image_urls=ref_images,
                video_urls=ref_videos,
                audio_urls=ref_audio,
                duration=duration,
                aspect_ratio=aspect_ratio,
            )

        if request.mode == VideoMode.IMAGE_TO_VIDEO:
            # Resolve image URLs from canonical fields or provider_options
            first_frame = (
                request.input_image_url
                or request.provider_options.get("first_frame_image")
            )
            last_frame = request.provider_options.get("last_frame_image")

            return self._client.create_image_to_video(
                prompt=request.prompt,
                first_frame_image=first_frame,
                last_frame_image=last_frame,
                duration=duration,
            )

        # Default: text-to-video
        return self._client.create_text_to_video(
            prompt=request.prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            prompt_optimizer=prompt_optimizer,
        )

    @staticmethod
    def _extract_video_url(result: dict) -> str | None:
        """Extract the video download URL from a completed task response.

        MiniMax returns the URL in different locations depending on
        API version. Try known paths.
        """
        # v1 format: file_id → construct download URL
        # v2/H3 format: content.url or video_url directly
        if "content" in result and isinstance(result["content"], dict):
            url = result["content"].get("url")
            if url:
                return url

        # Direct video_url field
        if "video_url" in result:
            return result["video_url"]

        # file_id based (older API format — construct URL)
        file_id = result.get("file_id")
        if file_id:
            # MiniMax file download endpoint
            return f"https://api.minimax.io/v1/files/retrieve?file_id={file_id}"

        return None
