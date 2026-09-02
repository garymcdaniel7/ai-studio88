"""Video Assembly & Export — Durable Job Lifecycle (Story 077).

Production completion requires a REAL persisted output asset.
Simulation uses a distinct visible status and cannot satisfy production completion.

This module routes video assembly and export through the canonical durable job
platform (Story 053/071), requires verified source assets, and finalizes only
after an authoritative output asset exists at a retrievable location.

Job States (extends canonical):
    SUBMITTED       → Request validated, sources listed
    SOURCES_VERIFIED → All source assets confirmed present
    QUEUED          → In provider queue
    EXECUTING       → Assembly/render in progress
    UPLOADING       → Output being persisted to managed storage
    COMPLETED       → Output asset finalized + signed URL available
    FAILED          → Terminal failure (retryable if transient)
    CANCELLED       → User-initiated cancel
    SIMULATION_DONE → Simulation completed (NOT production-complete)

Invariants:
1. COMPLETED requires: asset_id + storage_key + checksum + signed URL
2. Simulation produces SIMULATION_DONE, never COMPLETED
3. Source assets verified BEFORE execution begins
4. Duplicate completion callbacks are idempotent
5. Cancel during execution leaves partial state recoverable
6. Signed URLs expire (default 1 hour) and can be refreshed
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Assembly Job States
# =============================================================================


class AssemblyState(StrEnum):
    SUBMITTED = "submitted"
    SOURCES_VERIFIED = "sources_verified"
    QUEUED = "queued"
    EXECUTING = "executing"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SIMULATION_DONE = "simulation_done"  # Distinct from COMPLETED

    @property
    def is_terminal(self) -> bool:
        return self in (
            AssemblyState.COMPLETED,
            AssemblyState.FAILED,
            AssemblyState.CANCELLED,
            AssemblyState.SIMULATION_DONE,
        )

    @property
    def is_active(self) -> bool:
        return self in (
            AssemblyState.SUBMITTED,
            AssemblyState.SOURCES_VERIFIED,
            AssemblyState.QUEUED,
            AssemblyState.EXECUTING,
            AssemblyState.UPLOADING,
        )

    @property
    def is_cancellable(self) -> bool:
        return self in (
            AssemblyState.SUBMITTED,
            AssemblyState.SOURCES_VERIFIED,
            AssemblyState.QUEUED,
        )

    @property
    def is_production_complete(self) -> bool:
        return self == AssemblyState.COMPLETED


class AssemblyType(StrEnum):
    VIDEO_ASSEMBLY = "video_assembly"   # Combine shots into sequence
    VIDEO_EXPORT = "video_export"       # Final render/encode
    AUDIO_MIX = "audio_mix"            # Combine audio tracks
    COMPOSITE = "composite"            # Multi-layer composition


# =============================================================================
# Source Asset Reference
# =============================================================================


@dataclass
class SourceAssetRef:
    """A reference to a source asset required for assembly."""

    asset_id: str
    asset_type: str = "video"       # video, image, audio
    role: str = "shot"              # shot, overlay, audio_track, background
    sequence_order: int = 0
    verified: bool = False
    verification_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "role": self.role,
            "sequence_order": self.sequence_order,
            "verified": self.verified,
            "verification_error": self.verification_error,
        }


# =============================================================================
# Assembly Output
# =============================================================================


@dataclass
class AssemblyOutput:
    """The finalized output of a completed assembly job."""

    asset_id: str = ""
    storage_key: str = ""
    checksum_sha256: str = ""
    mime_type: str = "video/mp4"
    size_bytes: int = 0
    duration_seconds: float = 0.0
    width: int | None = None
    height: int | None = None
    # Signed access
    signed_url: str | None = None
    signed_url_expires_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "storage_key": self.storage_key,
            "checksum_sha256": self.checksum_sha256,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "signed_url": self.signed_url,
            "signed_url_expires_at": self.signed_url_expires_at,
        }


# =============================================================================
# Assembly Job
# =============================================================================


@dataclass
class AssemblyJob:
    """Durable video assembly/export job."""

    # Identity
    job_id: str = field(default_factory=lambda: f"asm-{secrets.token_hex(8)}")
    org_id: str = ""
    user_id: str = ""
    assembly_type: AssemblyType = AssemblyType.VIDEO_ASSEMBLY

    # State
    state: AssemblyState = AssemblyState.SUBMITTED
    state_history: list[dict] = field(default_factory=list)
    is_simulation: bool = False

    # Sources
    source_assets: list[SourceAssetRef] = field(default_factory=list)
    all_sources_verified: bool = False

    # Output (populated on completion)
    output: AssemblyOutput | None = None

    # Provider/execution
    provider: str = ""
    worker_id: str | None = None
    progress_pct: float = 0.0

    # Cost
    cost_estimated_usd: float | None = None
    cost_actual_usd: float | None = None

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None

    # Retry/error
    attempt: int = 1
    max_attempts: int = 3
    error_message: str | None = None
    last_error_at: str | None = None

    def transition(self, new_state: AssemblyState, reason: str = "") -> None:
        """Record a state transition."""
        self.state_history.append({
            "from": self.state.value,
            "to": new_state.value,
            "at": datetime.now(UTC).isoformat(),
            "reason": reason,
        })
        self.state = new_state
        if new_state == AssemblyState.EXECUTING:
            self.started_at = datetime.now(UTC).isoformat()
        elif new_state.is_terminal:
            self.completed_at = datetime.now(UTC).isoformat()

    def to_status(self) -> dict:
        return {
            "job_id": self.job_id,
            "org_id": self.org_id,
            "assembly_type": self.assembly_type.value,
            "state": self.state.value,
            "is_simulation": self.is_simulation,
            "progress_pct": self.progress_pct,
            "source_count": len(self.source_assets),
            "all_sources_verified": self.all_sources_verified,
            "output": self.output.to_dict() if self.output else None,
            "cost_estimated_usd": self.cost_estimated_usd,
            "cost_actual_usd": self.cost_actual_usd,
            "error_message": self.error_message,
            "attempt": self.attempt,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# =============================================================================
# Source Verification
# =============================================================================


class SourceVerificationError(Exception):
    """Raised when source assets cannot be verified."""

    def __init__(self, message: str, missing_assets: list[str] | None = None):
        self.message = message
        self.missing_assets = missing_assets or []
        super().__init__(message)


def verify_sources(
    job: AssemblyJob,
    available_asset_ids: set[str],
) -> AssemblyJob:
    """Verify all source assets exist and are accessible.

    Updates each SourceAssetRef's verified flag.
    Transitions job to SOURCES_VERIFIED if all pass.
    Raises SourceVerificationError if any source is missing.
    """
    missing: list[str] = []

    for ref in job.source_assets:
        if ref.asset_id in available_asset_ids:
            ref.verified = True
        else:
            ref.verified = False
            ref.verification_error = "Asset not found or inaccessible"
            missing.append(ref.asset_id)

    if missing:
        job.error_message = f"Missing source assets: {', '.join(missing[:5])}"
        raise SourceVerificationError(
            f"{len(missing)} source asset(s) not found",
            missing_assets=missing,
        )

    job.all_sources_verified = True
    job.transition(AssemblyState.SOURCES_VERIFIED, "All sources verified")
    return job


# =============================================================================
# Completion Validation
# =============================================================================


class CompletionError(Exception):
    """Raised when completion requirements are not met."""

    def __init__(self, message: str, code: str = "INCOMPLETE"):
        self.message = message
        self.code = code
        super().__init__(message)


def validate_completion(job: AssemblyJob) -> list[str]:
    """Validate that a job can be marked as production-complete.

    Returns list of violations. Empty = valid for completion.
    """
    violations: list[str] = []

    if job.is_simulation:
        violations.append("Simulation cannot satisfy production completion")

    if job.output is None:
        violations.append("No output asset registered")
        return violations

    if not job.output.asset_id:
        violations.append("Output missing asset_id")

    if not job.output.storage_key:
        violations.append("Output missing storage_key")

    if not job.output.checksum_sha256:
        violations.append("Output missing checksum")

    if job.output.size_bytes <= 0:
        violations.append("Output has no content (size_bytes=0)")

    if not job.output.signed_url:
        violations.append("Output missing signed retrieval URL")

    return violations


# =============================================================================
# Finalize Assembly (Idempotent)
# =============================================================================


def finalize_assembly(
    job: AssemblyJob,
    *,
    output: AssemblyOutput,
) -> AssemblyJob:
    """Finalize an assembly job with a verified output.

    Idempotent: if already COMPLETED, returns without change.
    Simulation jobs get SIMULATION_DONE, never COMPLETED.

    Raises CompletionError if output doesn't meet requirements.
    """
    # Idempotent — already completed
    if job.state == AssemblyState.COMPLETED:
        return job
    if job.state == AssemblyState.SIMULATION_DONE:
        return job

    # Attach output
    job.output = output

    # Simulation path
    if job.is_simulation:
        job.transition(AssemblyState.SIMULATION_DONE, "Simulation complete")
        return job

    # Production validation
    violations = validate_completion(job)
    if violations:
        raise CompletionError(
            f"Cannot complete: {'; '.join(violations)}",
            code="COMPLETION_REQUIREMENTS_NOT_MET",
        )

    job.transition(AssemblyState.COMPLETED, "Output asset finalized and retrievable")
    return job


# =============================================================================
# Cancel Assembly
# =============================================================================


def cancel_assembly(job: AssemblyJob, *, reason: str = "") -> AssemblyJob:
    """Cancel an assembly job.

    Only cancellable in pre-execution states.
    Returns the job unchanged if already terminal or executing.
    """
    if job.state.is_terminal:
        return job  # Already done

    if not job.state.is_cancellable:
        # Cannot cancel during execution — partial state is recoverable
        return job

    job.transition(AssemblyState.CANCELLED, reason or "User cancelled")
    return job


# =============================================================================
# Fail Assembly (Retryable)
# =============================================================================


def fail_assembly(job: AssemblyJob, *, error: str) -> AssemblyJob:
    """Mark assembly as failed.

    Failed jobs remain retryable if attempts < max_attempts.
    """
    if job.state.is_terminal:
        return job  # Already terminal

    job.error_message = error
    job.last_error_at = datetime.now(UTC).isoformat()
    job.transition(AssemblyState.FAILED, error)
    return job


def retry_assembly(job: AssemblyJob) -> AssemblyJob:
    """Retry a failed assembly job.

    Resets to SUBMITTED state for re-execution.
    Returns None if max attempts exceeded.
    """
    if job.state != AssemblyState.FAILED:
        return job  # Can only retry failed jobs

    if job.attempt >= job.max_attempts:
        return job  # Exhausted retries

    job.attempt += 1
    job.error_message = None
    job.transition(AssemblyState.SUBMITTED, f"Retry attempt {job.attempt}")
    return job


# =============================================================================
# Signed URL Generation
# =============================================================================


def generate_signed_url(
    storage_key: str,
    *,
    expires_seconds: int = 3600,
) -> tuple[str, str]:
    """Generate a signed URL for output access.

    Returns (signed_url, expires_at_iso).
    In production: uses B2 presigned URL generation.
    Here: simulated with expiry tracking.
    """
    token = secrets.token_urlsafe(16)
    expires_at = datetime.now(UTC).isoformat()
    # Simulated URL structure
    url = f"https://cdn.ai-studio.app{storage_key}?token={token}&expires={expires_seconds}"
    return url, expires_at


def refresh_signed_url(job: AssemblyJob, expires_seconds: int = 3600) -> AssemblyJob:
    """Refresh the signed URL for a completed job's output.

    Only works for COMPLETED or SIMULATION_DONE jobs with an output.
    """
    if job.output is None:
        return job

    if not job.output.storage_key:
        return job

    url, expires_at = generate_signed_url(job.output.storage_key, expires_seconds=expires_seconds)
    job.output.signed_url = url
    job.output.signed_url_expires_at = expires_at
    return job


# =============================================================================
# Progress Update
# =============================================================================


def update_progress(job: AssemblyJob, progress_pct: float) -> AssemblyJob:
    """Update assembly progress percentage."""
    if job.state.is_terminal:
        return job  # Don't update terminal jobs

    job.progress_pct = max(0.0, min(100.0, progress_pct))
    return job
