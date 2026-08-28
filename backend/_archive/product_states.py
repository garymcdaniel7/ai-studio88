"""Shared Product State Contract — Story 113.

One vocabulary for capability readiness and execution lifecycle across ALL
media surfaces (Create, Storyboard, Quick Edit, Production, Video, Audio,
Music, Training, Hermes).

Capability Readiness (is this feature available?):
    AVAILABLE       — Fully operational, production-ready
    DEGRADED        — Partially functional with disclosed limitations
    UNAVAILABLE     — Not configured, offline, or credentials invalid
    SIMULATION      — Demo/dev mode explicitly enabled (labeled)
    UNKNOWN         — State cannot be determined (fails safe to UNAVAILABLE)

Execution Lifecycle (what happened to this job?):
    QUEUED          — Accepted, waiting for resources
    RUNNING         — Actively executing
    COMPLETED       — Verified output asset exists
    FAILED          — Terminal failure with reason
    CANCELLED       — User-initiated cancellation
    SIMULATION_DONE — Simulation produced demo output (NOT production)
    LINEAGE_INCOMPLETE — Output exists but provenance is incomplete

Completion Rule:
    COMPLETED requires: verified asset_id + storage_key + checksum
    Simulation output → SIMULATION_DONE (never COMPLETED)
    Message-only responses → never COMPLETED

Every surface must use these enums. No surface-specific "success" that
bypasses the contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Capability Readiness States
# =============================================================================


class CapabilityState(StrEnum):
    AVAILABLE = "available"         # Production-ready
    DEGRADED = "degraded"           # Functional with limitations
    UNAVAILABLE = "unavailable"     # Not operational
    SIMULATION = "simulation"       # Dev/demo mode (labeled)
    UNKNOWN = "unknown"             # Cannot determine (fails safe)


# =============================================================================
# Execution Lifecycle States
# =============================================================================


class ExecutionState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"                 # Requires verified output asset
    FAILED = "failed"
    CANCELLED = "cancelled"
    SIMULATION_DONE = "simulation_done"     # Demo output, NOT production
    LINEAGE_INCOMPLETE = "lineage_incomplete"  # Output exists, provenance gaps

    @property
    def is_terminal(self) -> bool:
        return self in (
            ExecutionState.COMPLETED, ExecutionState.FAILED,
            ExecutionState.CANCELLED, ExecutionState.SIMULATION_DONE,
            ExecutionState.LINEAGE_INCOMPLETE,
        )

    @property
    def is_production_complete(self) -> bool:
        """Only COMPLETED satisfies production completion."""
        return self == ExecutionState.COMPLETED

    @property
    def is_active(self) -> bool:
        return self in (ExecutionState.QUEUED, ExecutionState.RUNNING)


# =============================================================================
# Capability Status (per media surface)
# =============================================================================


class MediaSurface(StrEnum):
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    VIDEO_ASSEMBLY = "video_assembly"
    AUDIO_VOICE = "audio_voice"
    AUDIO_MUSIC = "audio_music"
    QUICK_EDIT = "quick_edit"
    LORA_TRAINING = "lora_training"
    LIP_SYNC = "lip_sync"
    BRAIN_CHAT = "brain_chat"


@dataclass
class CapabilityStatus:
    """Readiness status for a single media capability."""

    surface: MediaSurface
    state: CapabilityState
    explanation: str = ""           # User-visible, non-secret reason
    provider: str = ""
    last_checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    is_stale: bool = False          # True if check is older than threshold

    def to_dict(self) -> dict:
        return {
            "surface": self.surface.value,
            "state": self.state.value,
            "explanation": self.explanation,
            "provider": self.provider,
            "last_checked_at": self.last_checked_at,
            "is_stale": self.is_stale,
        }


# =============================================================================
# Execution Status (per job)
# =============================================================================


@dataclass
class ExecutionStatus:
    """Current execution status for any generation/transform/training job."""

    job_id: str = ""
    surface: MediaSurface = MediaSurface.IMAGE_GENERATION
    state: ExecutionState = ExecutionState.QUEUED
    is_simulation: bool = False
    # Output evidence (required for COMPLETED)
    has_verified_asset: bool = False
    asset_id: str | None = None
    has_storage_key: bool = False
    has_checksum: bool = False
    # Progress
    progress_pct: float = 0.0
    # Explanation
    explanation: str = ""           # Failure reason or status detail
    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "surface": self.surface.value,
            "state": self.state.value,
            "is_simulation": self.is_simulation,
            "has_verified_asset": self.has_verified_asset,
            "progress_pct": self.progress_pct,
            "explanation": self.explanation,
            "asset_id": self.asset_id,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


# =============================================================================
# State Derivation (from backend evidence)
# =============================================================================


def derive_capability_state(
    *,
    credentials_configured: bool = False,
    credentials_valid: bool | None = None,
    health_check_passed: bool | None = None,
    explicit_simulation: bool = False,
    degradation_reason: str | None = None,
) -> CapabilityState:
    """Derive capability state from backend evidence.

    Rules (evaluated in order):
    1. Explicit simulation mode → SIMULATION
    2. No credentials → UNAVAILABLE
    3. Credentials invalid → UNAVAILABLE
    4. Health check failed → UNAVAILABLE
    5. Health check passed + degradation → DEGRADED
    6. All clear → AVAILABLE
    7. Anything ambiguous → UNKNOWN (fails safe)
    """
    if explicit_simulation:
        return CapabilityState.SIMULATION

    if not credentials_configured:
        return CapabilityState.UNAVAILABLE

    if credentials_valid is False:
        return CapabilityState.UNAVAILABLE

    if health_check_passed is False:
        return CapabilityState.UNAVAILABLE

    if health_check_passed is True and degradation_reason:
        return CapabilityState.DEGRADED

    if credentials_valid is True and health_check_passed is True:
        return CapabilityState.AVAILABLE

    # Ambiguous — fail safe
    return CapabilityState.UNKNOWN


def derive_execution_state(
    *,
    is_simulation: bool = False,
    has_asset_id: bool = False,
    has_storage_key: bool = False,
    has_checksum: bool = False,
    is_cancelled: bool = False,
    has_error: bool = False,
    is_executing: bool = False,
    lineage_complete: bool = True,
) -> ExecutionState:
    """Derive execution state from output evidence.

    Rules:
    1. Cancelled → CANCELLED
    2. Error → FAILED
    3. Simulation with output → SIMULATION_DONE
    4. Has verified output + lineage → COMPLETED
    5. Has output but incomplete lineage → LINEAGE_INCOMPLETE
    6. Executing → RUNNING
    7. Default → QUEUED
    """
    if is_cancelled:
        return ExecutionState.CANCELLED

    if has_error:
        return ExecutionState.FAILED

    has_verified_output = has_asset_id and has_storage_key and has_checksum

    if is_simulation and has_verified_output:
        return ExecutionState.SIMULATION_DONE

    if has_verified_output and lineage_complete:
        return ExecutionState.COMPLETED

    if has_verified_output and not lineage_complete:
        return ExecutionState.LINEAGE_INCOMPLETE

    if is_executing:
        return ExecutionState.RUNNING

    return ExecutionState.QUEUED


# =============================================================================
# Stale Detection
# =============================================================================

STALE_THRESHOLD_SECONDS: int = 300  # 5 minutes


def is_status_stale(last_checked_at: str, now: str | None = None) -> bool:
    """Check if a capability status check is stale.

    Status older than STALE_THRESHOLD_SECONDS is stale.
    Stale status should be treated as UNKNOWN until refreshed.
    """
    current = now or datetime.now(UTC).isoformat()
    # Simplified ISO comparison (works for same-timezone ISO strings)
    return last_checked_at < _subtract_seconds(current, STALE_THRESHOLD_SECONDS)


def _subtract_seconds(iso_str: str, seconds: int) -> str:
    """Subtract seconds from an ISO timestamp (simplified)."""
    # For contract testing: just compare strings
    # Production would use proper datetime math
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        from datetime import timedelta
        result = dt - timedelta(seconds=seconds)
        return result.isoformat()
    except (ValueError, TypeError):
        return iso_str


# =============================================================================
# Completion Guard
# =============================================================================


class CompletionGuardError(Exception):
    """Raised when a job cannot be marked as production-complete."""

    def __init__(self, message: str, missing: list[str] | None = None):
        self.message = message
        self.missing = missing or []
        super().__init__(message)


def guard_production_completion(
    *,
    is_simulation: bool = False,
    has_asset_id: bool = False,
    has_storage_key: bool = False,
    has_checksum: bool = False,
    lineage_complete: bool = True,
) -> None:
    """Guard: block production completion unless all evidence present.

    Raises CompletionGuardError with missing evidence list.
    """
    if is_simulation:
        raise CompletionGuardError(
            "Simulation cannot satisfy production completion",
            missing=["production_provider"],
        )

    missing: list[str] = []
    if not has_asset_id:
        missing.append("asset_id")
    if not has_storage_key:
        missing.append("storage_key")
    if not has_checksum:
        missing.append("checksum")

    if missing:
        raise CompletionGuardError(
            f"Production completion requires: {', '.join(missing)}",
            missing=missing,
        )

    if not lineage_complete:
        raise CompletionGuardError(
            "Output has incomplete provenance lineage",
            missing=["lineage"],
        )


# =============================================================================
# Cross-Surface Registry
# =============================================================================

_capability_registry: dict[MediaSurface, CapabilityStatus] = {}


def clear_registry() -> None:
    _capability_registry.clear()


def register_capability(status: CapabilityStatus) -> None:
    """Register or update a capability status."""
    _capability_registry[status.surface] = status


def get_capability(surface: MediaSurface) -> CapabilityStatus:
    """Get capability status. Returns UNKNOWN if not registered (fail-safe)."""
    if surface in _capability_registry:
        return _capability_registry[surface]
    return CapabilityStatus(
        surface=surface,
        state=CapabilityState.UNKNOWN,
        explanation="Capability status not registered",
    )


def get_all_capabilities() -> list[CapabilityStatus]:
    """Get all registered capability statuses."""
    return list(_capability_registry.values())


def get_available_surfaces() -> list[MediaSurface]:
    """Get surfaces that are AVAILABLE for production use."""
    return [
        s for s, status in _capability_registry.items()
        if status.state == CapabilityState.AVAILABLE
    ]
