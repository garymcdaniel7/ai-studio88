"""Quick Edit Transform Job — Story 111.

One server-authoritative durable lifecycle for image transforms (Quick Edit).
Source ownership is verified before execution. Completion requires a persisted
output asset. Browser closure does not lose accepted work.

Transform Operations:
    UPSCALE, REMOVE_BG, INPAINT, OUTPAINT, STYLE_TRANSFER, ENHANCE, CROP_RESIZE

Job Lifecycle:
    SUBMITTED → SOURCE_VERIFIED → EXECUTING → COMPLETED | FAILED | CANCELLED

Invariants:
1. Source asset must be verified (storage confirmed + org ownership) before execution
2. Transform spec is immutable after submission
3. Completed requires persisted output asset (asset_id + storage_key + checksum)
4. Retry and cancel are idempotent
5. Cross-workspace source IDs are denied
6. One durable job ID survives browser refresh/disconnect
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Transform Operations
# =============================================================================


class TransformOperation(StrEnum):
    UPSCALE = "upscale"
    REMOVE_BG = "remove_bg"
    INPAINT = "inpaint"
    OUTPAINT = "outpaint"
    STYLE_TRANSFER = "style_transfer"
    ENHANCE = "enhance"
    CROP_RESIZE = "crop_resize"


# =============================================================================
# Job States
# =============================================================================


class TransformState(StrEnum):
    SUBMITTED = "submitted"
    SOURCE_VERIFIED = "source_verified"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (TransformState.COMPLETED, TransformState.FAILED, TransformState.CANCELLED)

    @property
    def is_cancellable(self) -> bool:
        return self in (TransformState.SUBMITTED, TransformState.SOURCE_VERIFIED)

    @property
    def is_retryable(self) -> bool:
        return self == TransformState.FAILED


# =============================================================================
# Transform Specification (immutable)
# =============================================================================


@dataclass
class TransformSpec:
    """Immutable specification for the transform operation."""

    operation: TransformOperation
    # Source
    source_asset_id: str = ""
    source_storage_key: str = ""
    source_checksum: str = ""
    # Operation-specific settings
    scale_factor: float | None = None       # For upscale (2x, 4x)
    mask_data: str | None = None            # For inpaint (base64 or storage key)
    style_reference: str | None = None      # For style_transfer
    target_width: int | None = None         # For crop_resize
    target_height: int | None = None
    strength: float = 1.0                   # Operation intensity
    extras: dict = field(default_factory=dict)

    def compute_hash(self) -> str:
        """Deterministic hash of the transform specification."""
        parts = [
            self.operation.value,
            self.source_asset_id,
            self.source_checksum,
            str(self.scale_factor or 0),
            str(self.target_width or 0),
            str(self.target_height or 0),
            str(self.strength),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]

    def to_dict(self) -> dict:
        return {
            "operation": self.operation.value,
            "source_asset_id": self.source_asset_id,
            "source_storage_key": self.source_storage_key,
            "source_checksum": self.source_checksum,
            "scale_factor": self.scale_factor,
            "target_width": self.target_width,
            "target_height": self.target_height,
            "strength": self.strength,
        }


# =============================================================================
# Transform Job
# =============================================================================


@dataclass
class TransformJob:
    """Durable transform job for Quick Edit."""

    # Identity
    job_id: str = field(default_factory=lambda: f"tx-{uuid.uuid4().hex[:12]}")
    idempotency_key: str = ""
    org_id: str = ""
    user_id: str = ""
    project_id: str | None = None

    # Specification (immutable)
    spec: TransformSpec | None = None
    spec_hash: str = ""

    # State
    state: TransformState = TransformState.SUBMITTED
    progress_pct: float = 0.0

    # Output (populated on completion)
    output_asset_id: str | None = None
    output_storage_key: str = ""
    output_checksum: str = ""
    output_mime_type: str = ""
    output_size_bytes: int = 0

    # Cost
    cost_estimated_usd: float = 0.0
    cost_actual_usd: float | None = None

    # Provider
    provider: str = ""
    worker_id: str | None = None

    # Error/retry
    error_message: str | None = None
    attempt: int = 1
    max_attempts: int = 3

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "org_id": self.org_id,
            "state": self.state.value,
            "operation": self.spec.operation.value if self.spec else None,
            "source_asset_id": self.spec.source_asset_id if self.spec else None,
            "spec_hash": self.spec_hash,
            "progress_pct": self.progress_pct,
            "output_asset_id": self.output_asset_id,
            "cost_estimated_usd": self.cost_estimated_usd,
            "cost_actual_usd": self.cost_actual_usd,
            "error_message": self.error_message,
            "attempt": self.attempt,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


# =============================================================================
# Source Validation
# =============================================================================


class SourceValidationError(Exception):
    def __init__(self, message: str, code: str = "SOURCE_INVALID"):
        self.message = message
        self.code = code
        super().__init__(message)


@dataclass
class SourceAsset:
    """Minimal source asset info for validation."""

    asset_id: str = ""
    org_id: str = ""
    storage_key: str = ""
    checksum: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    is_finalized: bool = False


ALLOWED_SOURCE_MIMES: set[str] = {"image/jpeg", "image/png", "image/webp"}


def validate_source(source: SourceAsset, requesting_org_id: str) -> None:
    """Validate source asset before transform execution.

    Checks: ownership, storage confirmed, MIME type, finalization.
    Raises SourceValidationError on failure.
    """
    if not source.asset_id:
        raise SourceValidationError("Source asset_id is required")

    if source.org_id != requesting_org_id:
        raise SourceValidationError(
            "Source asset belongs to a different workspace",
            code="CROSS_TENANT",
        )

    if not source.is_finalized:
        raise SourceValidationError(
            "Source asset is not finalized (storage not confirmed)",
            code="NOT_FINALIZED",
        )

    if not source.storage_key:
        raise SourceValidationError(
            "Source asset has no confirmed storage location",
            code="NO_STORAGE",
        )

    if source.mime_type not in ALLOWED_SOURCE_MIMES:
        raise SourceValidationError(
            f"Source MIME type '{source.mime_type}' not supported for transforms",
            code="UNSUPPORTED_MIME",
        )


# =============================================================================
# Job Store
# =============================================================================

_job_store: dict[str, TransformJob] = {}
_idempotency_index: dict[str, str] = {}


def clear_store() -> None:
    _job_store.clear()
    _idempotency_index.clear()


def get_job(job_id: str) -> TransformJob | None:
    return _job_store.get(job_id)


# =============================================================================
# Submit Transform
# =============================================================================


class TransformError(Exception):
    def __init__(self, message: str, code: str = "TRANSFORM_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


def submit_transform(
    *,
    org_id: str,
    user_id: str,
    source: SourceAsset,
    operation: TransformOperation,
    project_id: str | None = None,
    scale_factor: float | None = None,
    target_width: int | None = None,
    target_height: int | None = None,
    strength: float = 1.0,
    mask_data: str | None = None,
    style_reference: str | None = None,
    cost_estimated_usd: float = 0.0,
    idempotency_key: str = "",
) -> TransformJob:
    """Submit a transform job.

    1. Validates source asset ownership and storage
    2. Creates immutable spec
    3. Persists durable job
    Idempotent: same key returns existing job.
    """
    if not org_id or not user_id:
        raise TransformError("Authentication required", code="AUTH_REQUIRED")

    # Idempotency
    if idempotency_key and idempotency_key in _idempotency_index:
        existing = _job_store.get(_idempotency_index[idempotency_key])
        if existing:
            return existing

    # Validate source
    validate_source(source, org_id)

    # Create immutable spec
    spec = TransformSpec(
        operation=operation,
        source_asset_id=source.asset_id,
        source_storage_key=source.storage_key,
        source_checksum=source.checksum,
        scale_factor=scale_factor,
        mask_data=mask_data,
        style_reference=style_reference,
        target_width=target_width,
        target_height=target_height,
        strength=strength,
    )

    # Create job
    job = TransformJob(
        idempotency_key=idempotency_key,
        org_id=org_id,
        user_id=user_id,
        project_id=project_id,
        spec=spec,
        spec_hash=spec.compute_hash(),
        state=TransformState.SOURCE_VERIFIED,
        cost_estimated_usd=cost_estimated_usd,
    )

    _job_store[job.job_id] = job
    if idempotency_key:
        _idempotency_index[idempotency_key] = job.job_id

    return job


# =============================================================================
# Execution
# =============================================================================


def start_execution(job_id: str) -> TransformJob | None:
    """Mark job as executing."""
    job = _job_store.get(job_id)
    if not job:
        return None
    if job.state != TransformState.SOURCE_VERIFIED:
        return job  # Already started or terminal
    job.state = TransformState.EXECUTING
    job.started_at = datetime.now(UTC).isoformat()
    return job


def complete_transform(
    job_id: str,
    *,
    output_asset_id: str,
    output_storage_key: str,
    output_checksum: str,
    output_mime_type: str = "image/webp",
    output_size_bytes: int = 0,
    cost_actual_usd: float = 0.0,
) -> TransformJob:
    """Complete a transform with verified output asset.

    Idempotent: completing already-completed job returns it unchanged.
    Raises TransformError if output requirements not met.
    """
    job = _job_store.get(job_id)
    if not job:
        raise TransformError(f"Job {job_id} not found", code="NOT_FOUND")

    if job.state == TransformState.COMPLETED:
        return job  # Idempotent

    if not output_asset_id:
        raise TransformError("output_asset_id required for completion", code="NO_OUTPUT")
    if not output_storage_key:
        raise TransformError("output_storage_key required for completion", code="NO_STORAGE")
    if not output_checksum:
        raise TransformError("output_checksum required for completion", code="NO_CHECKSUM")

    job.state = TransformState.COMPLETED
    job.output_asset_id = output_asset_id
    job.output_storage_key = output_storage_key
    job.output_checksum = output_checksum
    job.output_mime_type = output_mime_type
    job.output_size_bytes = output_size_bytes
    job.cost_actual_usd = cost_actual_usd
    job.completed_at = datetime.now(UTC).isoformat()
    job.error_message = None
    return job


# =============================================================================
# Failure & Retry
# =============================================================================


def fail_transform(job_id: str, *, error: str) -> TransformJob | None:
    """Mark job as failed."""
    job = _job_store.get(job_id)
    if not job or job.state.is_terminal:
        return job
    job.state = TransformState.FAILED
    job.error_message = error
    job.completed_at = datetime.now(UTC).isoformat()
    return job


def retry_transform(job_id: str) -> TransformJob | None:
    """Retry a failed transform.

    Resets to SOURCE_VERIFIED for re-execution.
    Idempotent: retrying non-failed job returns it unchanged.
    """
    job = _job_store.get(job_id)
    if not job:
        return None
    if not job.state.is_retryable:
        return job  # Not retryable
    if job.attempt >= job.max_attempts:
        return job  # Exhausted

    job.state = TransformState.SOURCE_VERIFIED
    job.error_message = None
    job.attempt += 1
    job.completed_at = None
    return job


# =============================================================================
# Cancellation
# =============================================================================


def cancel_transform(job_id: str) -> TransformJob | None:
    """Cancel a transform job.

    Only cancellable before execution starts.
    Idempotent: cancelling already-cancelled/completed returns unchanged.
    """
    job = _job_store.get(job_id)
    if not job:
        return None
    if job.state.is_terminal:
        return job  # Already done
    if not job.state.is_cancellable:
        return job  # Cannot cancel during execution

    job.state = TransformState.CANCELLED
    job.completed_at = datetime.now(UTC).isoformat()
    return job


# =============================================================================
# Progress
# =============================================================================


def update_progress(job_id: str, progress_pct: float) -> TransformJob | None:
    """Update transform progress."""
    job = _job_store.get(job_id)
    if not job or job.state.is_terminal:
        return job
    job.progress_pct = max(0.0, min(100.0, progress_pct))
    return job
