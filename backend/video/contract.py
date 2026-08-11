"""Canonical Video Provider Contract — Story 143.

This module defines the ONE supported integration boundary for all video
generation providers in AI Studio. Every provider adapter implements this
contract. Shared orchestration, UI, and job lifecycle consume only these
types — never provider-specific shapes.

Design principles:
- Typed capability discovery (not arbitrary dicts)
- Normalized errors with actionable messages (no secrets)
- Cost estimation before paid execution
- Progress updates with cancellation support
- Output asset finalization with provenance
- Provider/model health as first-class concepts
- Configuration validation at registration time
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


# =============================================================================
# Enums
# =============================================================================


class VideoMode(StrEnum):
    """Supported video generation modes."""

    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    VIDEO_TO_VIDEO = "video_to_video"


class VideoProviderStatus(StrEnum):
    """Provider availability states."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    MAINTENANCE = "maintenance"


class VideoJobStatus(StrEnum):
    """Canonical job lifecycle states."""

    PENDING = "pending"
    VALIDATING = "validating"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class VideoErrorCode(StrEnum):
    """Normalized error codes for consistent handling."""

    # Provider-level
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_AUTH_FAILED = "PROVIDER_AUTH_FAILED"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"

    # Request-level
    UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
    UNSUPPORTED_MODEL = "UNSUPPORTED_MODEL"
    UNSUPPORTED_RESOLUTION = "UNSUPPORTED_RESOLUTION"
    INVALID_INPUT = "INVALID_INPUT"
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"
    DURATION_EXCEEDED = "DURATION_EXCEEDED"

    # Execution-level
    GENERATION_FAILED = "GENERATION_FAILED"
    OUTPUT_MISSING = "OUTPUT_MISSING"
    CANCELLED = "CANCELLED"

    # Cost-level
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    COST_UNAVAILABLE = "COST_UNAVAILABLE"

    # Unknown
    UNKNOWN = "UNKNOWN"


# =============================================================================
# Data Contracts
# =============================================================================


@dataclass(frozen=True)
class VideoModelInfo:
    """A model available through a provider."""

    id: str
    name: str
    provider: str
    modes: list[VideoMode] = field(default_factory=list)
    max_duration_seconds: float = 10.0
    max_resolution: str = "1280x720"
    default_resolution: str = "832x480"
    default_fps: int = 24
    max_fps: int = 30
    min_frames: int = 17
    max_frames: int = 81
    vram_required_gb: float = 24.0
    supports_negative_prompt: bool = True
    supports_camera_motion: bool = False
    supports_seed: bool = True
    notes: str = ""


@dataclass(frozen=True)
class VideoProviderCapabilities:
    """Typed capability advertisement for a video provider."""

    provider_name: str
    modes: list[VideoMode]
    models: list[VideoModelInfo]
    max_concurrent_jobs: int = 1
    supports_cancellation: bool = True
    supports_progress: bool = True
    supports_cost_estimate: bool = False
    supports_priority: bool = False
    deployment_mode: str = "cloud"  # cloud, local, hybrid
    notes: str = ""


@dataclass(frozen=True)
class VideoProviderHealth:
    """Typed health status for a video provider."""

    provider_name: str
    status: VideoProviderStatus
    message: str = ""
    gpu_name: str | None = None
    vram_total_gb: float | None = None
    vram_free_gb: float | None = None
    queue_size: int = 0
    estimated_wait_seconds: float | None = None


@dataclass
class VideoGenerationRequest:
    """Canonical request for video generation.

    All provider adapters accept this shape. Provider-specific parameters
    go in `provider_options` but shared orchestration never reads them.
    """

    # Required
    mode: VideoMode
    prompt: str

    # Content inputs
    negative_prompt: str = ""
    motion_prompt: str = ""
    input_image_url: str | None = None
    input_image_bytes: bytes | None = None
    input_video_url: str | None = None
    input_video_bytes: bytes | None = None

    # Generation parameters
    model: str = "wan-2.1"
    duration_seconds: float = 2.0
    fps: int = 24
    width: int = 832
    height: int = 480
    seed: int = -1
    steps: int = 20
    cfg_scale: float = 6.0
    camera_motion: str = "static"

    # Context / provenance
    org_id: str | None = None
    user_id: str | None = None
    project_id: str | None = None
    talent_id: str | None = None
    job_id: str | None = None

    # Provider-specific options (adapter reads, orchestration ignores)
    provider_options: dict = field(default_factory=dict)


@dataclass(frozen=True)
class VideoGenerationProgress:
    """Canonical progress update from a running generation."""

    percent: int = 0
    frame: int = 0
    total_frames: int = 0
    message: str = ""
    eta_seconds: float | None = None
    preview_url: str | None = None


@dataclass
class VideoGenerationResult:
    """Canonical result from a completed (or failed) generation.

    On success: output_bytes or output_url is populated.
    On failure: error_code and error_message are populated.
    """

    # Status
    success: bool = False
    status: VideoJobStatus = VideoJobStatus.FAILED

    # Output (on success)
    output_bytes: bytes | None = None
    output_url: str | None = None
    filename: str = ""
    mime_type: str = "video/mp4"
    duration_seconds: float = 0.0
    fps: int = 24
    width: int = 0
    height: int = 0

    # Timing
    generation_time_seconds: float = 0.0
    queue_time_seconds: float = 0.0

    # Cost
    cost_usd: float | None = None

    # Provenance
    provider_name: str = ""
    model_used: str = ""
    seed_used: int | None = None
    provider_job_id: str | None = None

    # Error (on failure)
    error_code: VideoErrorCode | None = None
    error_message: str | None = None
    retryable: bool = False

    # Metadata (non-secret provider context for debugging/audit)
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class VideoCostEstimate:
    """Pre-execution cost estimate."""

    estimated_cost_usd: float
    currency: str = "USD"
    confidence: str = "estimate"  # estimate, fixed, unavailable
    breakdown: dict = field(default_factory=dict)
    message: str = ""


@dataclass(frozen=True)
class VideoProviderError:
    """Normalized provider error — never contains secrets."""

    code: VideoErrorCode
    message: str
    retryable: bool = False
    provider_name: str = ""
    details: dict = field(default_factory=dict)


# =============================================================================
# Provider Configuration
# =============================================================================


@dataclass
class VideoProviderConfig:
    """Configuration required to register a provider adapter.

    Validated at registration time — invalid configs prevent startup.
    """

    name: str
    enabled: bool = True
    # Provider-specific settings (adapter validates internally)
    settings: dict = field(default_factory=dict)
    # Priority for provider selection (lower = preferred)
    priority: int = 100
    # Rate limits
    max_concurrent_jobs: int = 1
    max_requests_per_minute: int = 10


# =============================================================================
# Canonical Provider Interface
# =============================================================================


class CanonicalVideoProvider(ABC):
    """The ONE supported integration boundary for video generation.

    Every video provider adapter implements this interface. Shared callers
    (orchestration, UI, job lifecycle) consume ONLY this contract.

    Adapter responsibilities:
    - Translate VideoGenerationRequest → provider-specific API calls
    - Translate provider-specific responses → VideoGenerationResult
    - Report typed capabilities and health
    - Validate configuration at construction time
    - Handle provider-specific errors and map to VideoErrorCode
    - Never expose provider secrets in errors or metadata
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier (e.g., 'comfyui-wan', 'minimax', 'kling')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name for UI."""
        ...

    # ─── Discovery ──────────────────────────────────────────────────────────

    @abstractmethod
    def capabilities(self) -> VideoProviderCapabilities:
        """Return typed capabilities, supported modes, and models.

        Must be callable without network I/O (use cached data).
        """
        ...

    @abstractmethod
    def health(self) -> VideoProviderHealth:
        """Check current provider health and availability.

        May perform network I/O (health check to remote service).
        """
        ...

    @abstractmethod
    def list_models(self) -> list[VideoModelInfo]:
        """Enumerate available models with their constraints."""
        ...

    # ─── Validation ─────────────────────────────────────────────────────────

    @abstractmethod
    def validate_request(self, request: VideoGenerationRequest) -> VideoProviderError | None:
        """Pre-validate a request against capabilities.

        Returns None if valid, or a VideoProviderError if the request
        cannot be fulfilled. Called BEFORE cost estimation or execution.
        """
        ...

    # ─── Cost ───────────────────────────────────────────────────────────────

    def estimate_cost(self, request: VideoGenerationRequest) -> VideoCostEstimate:
        """Estimate execution cost before committing.

        Default: returns unavailable. Override for providers with pricing APIs.
        """
        return VideoCostEstimate(
            estimated_cost_usd=0.0,
            confidence="unavailable",
            message="Cost estimation not available for this provider.",
        )

    # ─── Execution ──────────────────────────────────────────────────────────

    @abstractmethod
    def submit(
        self,
        request: VideoGenerationRequest,
        on_progress: Callable[[VideoGenerationProgress], None] | None = None,
    ) -> VideoGenerationResult:
        """Execute a video generation request.

        Blocks until completion, failure, or timeout. Reports progress
        through on_progress callback if provided.

        MUST:
        - Set result.provider_name and result.model_used
        - Set result.seed_used if deterministic
        - Map all provider errors to VideoErrorCode
        - Never include secrets in result.metadata or error_message
        - Set result.retryable appropriately
        """
        ...

    @abstractmethod
    def cancel(self, provider_job_id: str) -> bool:
        """Request cancellation of a running job.

        Returns True if cancellation was accepted (not necessarily completed).
        Providers that don't support cancellation return False.
        """
        ...

    # ─── Lifecycle ──────────────────────────────────────────────────────────

    def initialize(self, config: VideoProviderConfig) -> None:
        """Called once at registration time to validate config.

        Override to check required settings, test connectivity, etc.
        Raise ValueError if config is invalid.
        """

    def shutdown(self) -> None:
        """Called on graceful shutdown. Override to clean up resources."""
