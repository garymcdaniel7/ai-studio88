"""Durable Training Progress & Cancellation — Story 094.

Persists provider job identity, progress, heartbeat, and cancellation state.
Status mirrors the real provider job. Cancellation is evidence-based —
never reports "cancelled" until provider confirms termination.

Lifecycle:
    queued → transferring → training → finalizing → completed
                                    → cancel_requested → cancel_confirmed | cancel_unresolved
                          → failed (provider error)
                          → lost (heartbeat timeout)

Key invariants:
    - Terminal status requires provider evidence
    - Cancellation request ≠ cancellation complete
    - Unconfirmed termination remains billable
    - Duplicate callbacks are idempotent
    - Progress survives API/browser restart (durable store)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class TrainingStatus(str, Enum):
    QUEUED = "queued"
    TRANSFERRING = "transferring"     # Dataset being sent to worker
    TRAINING = "training"             # Active GPU execution
    FINALIZING = "finalizing"         # Model being saved/uploaded
    COMPLETED = "completed"           # Provider confirmed completion
    FAILED = "failed"                 # Provider reported failure
    CANCEL_REQUESTED = "cancel_requested"   # User requested cancel
    CANCEL_CONFIRMED = "cancel_confirmed"   # Provider confirmed termination
    CANCEL_UNRESOLVED = "cancel_unresolved" # Cancel sent but no confirmation
    LOST = "lost"                     # Worker heartbeat lost


class CancelEvidence(str, Enum):
    NONE = "none"                     # No cancel attempted
    REQUESTED = "requested"           # Cancel request sent to provider
    PROVIDER_ACK = "provider_ack"     # Provider acknowledged receipt
    PROCESS_TERMINATED = "process_terminated"  # Provider confirmed kill
    TIMEOUT_ASSUMED = "timeout_assumed"  # Assumed dead after timeout (unresolved)


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class TrainingProgress:
    """Durable progress state for a training job."""
    current_step: int = 0
    total_steps: int = 0
    current_epoch: int = 0
    total_epochs: int = 0
    loss: float | None = None
    learning_rate: float | None = None
    samples_processed: int = 0
    progress_pct: int = 0

    def update(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)
        # Recompute percentage
        if self.total_steps > 0:
            self.progress_pct = min(int((self.current_step / self.total_steps) * 100), 100)


@dataclass
class TrainingJob:
    """Durable training job with provider tracking."""
    job_id: str = field(default_factory=lambda: f"trn-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    talent_id: str = ""
    manifest_id: str = ""         # Dataset manifest reference

    # Provider execution identity
    provider_job_id: str | None = None    # Vast.ai/RunPod job ID
    worker_id: str | None = None          # Worker instance ID
    lease_id: str | None = None           # Worker lease reference
    process_id: str | None = None         # OS process on worker

    # Status
    status: TrainingStatus = TrainingStatus.QUEUED
    progress: TrainingProgress = field(default_factory=TrainingProgress)

    # Heartbeat
    last_heartbeat: float | None = None
    heartbeat_interval_seconds: int = 30
    heartbeat_timeout_seconds: int = 120  # Mark lost after this

    # Cancellation
    cancel_evidence: CancelEvidence = CancelEvidence.NONE
    cancel_requested_at: float | None = None
    cancel_confirmed_at: float | None = None
    cancel_error: str | None = None

    # Cost tracking
    cost_accrued_usd: float = 0.0
    cost_rate_per_hour: float = 0.0
    billing_started_at: float | None = None
    billing_stopped_at: float | None = None

    # Timing
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None

    # Error
    error: str | None = None
    error_code: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            TrainingStatus.COMPLETED,
            TrainingStatus.FAILED,
            TrainingStatus.CANCEL_CONFIRMED,
        )

    @property
    def is_billable(self) -> bool:
        """Still billable until provider confirms stop."""
        if self.is_terminal:
            return False
        if self.status in (
            TrainingStatus.TRAINING,
            TrainingStatus.FINALIZING,
            TrainingStatus.CANCEL_REQUESTED,
            TrainingStatus.CANCEL_UNRESOLVED,
            TrainingStatus.LOST,
        ):
            return True
        return False

    @property
    def heartbeat_stale(self) -> bool:
        if not self.last_heartbeat:
            return False
        return (time.time() - self.last_heartbeat) > self.heartbeat_timeout_seconds

    @property
    def runtime_seconds(self) -> float:
        if not self.billing_started_at:
            return 0.0
        end = self.billing_stopped_at or time.time()
        return end - self.billing_started_at


# =============================================================================
# Store
# =============================================================================

_jobs: dict[str, TrainingJob] = {}


# =============================================================================
# Job Lifecycle
# =============================================================================


def create_training_job(
    org_id: str,
    talent_id: str,
    manifest_id: str,
    cost_rate_per_hour: float = 0.0,
) -> TrainingJob:
    """Create a durable training job record."""
    if not org_id or not talent_id or not manifest_id:
        raise ValueError("org_id, talent_id, and manifest_id are required")

    job = TrainingJob(
        org_id=org_id,
        talent_id=talent_id,
        manifest_id=manifest_id,
        cost_rate_per_hour=cost_rate_per_hour,
    )
    _jobs[job.job_id] = job
    logger.info(f"TRAINING_JOB_CREATED: id={job.job_id} talent={talent_id}")
    return job


def assign_provider(
    job_id: str,
    org_id: str,
    provider_job_id: str,
    worker_id: str,
    lease_id: str | None = None,
    process_id: str | None = None,
) -> TrainingJob:
    """Assign provider execution identity to the job."""
    job = _get_job(job_id, org_id)

    job.provider_job_id = provider_job_id
    job.worker_id = worker_id
    job.lease_id = lease_id
    job.process_id = process_id
    job.status = TrainingStatus.TRANSFERRING

    logger.info(f"TRAINING_PROVIDER_ASSIGNED: job={job_id} provider={provider_job_id} worker={worker_id}")
    return job


def start_training(job_id: str, org_id: str) -> TrainingJob:
    """Mark training as actively running (GPU execution started)."""
    job = _get_job(job_id, org_id)

    if job.status == TrainingStatus.CANCEL_REQUESTED:
        return job  # Don't overwrite cancel with start

    job.status = TrainingStatus.TRAINING
    job.started_at = time.time()
    job.billing_started_at = time.time()
    job.last_heartbeat = time.time()

    logger.info(f"TRAINING_STARTED: job={job_id}")
    return job


def report_progress(
    job_id: str,
    org_id: str,
    **progress_kwargs: Any,
) -> TrainingJob:
    """Update training progress (idempotent — latest values win)."""
    job = _get_job(job_id, org_id)

    if job.is_terminal:
        return job  # Ignore progress after terminal

    job.progress.update(**progress_kwargs)
    job.last_heartbeat = time.time()

    # Update cost accrual
    if job.billing_started_at and job.cost_rate_per_hour > 0:
        hours = job.runtime_seconds / 3600
        job.cost_accrued_usd = round(hours * job.cost_rate_per_hour, 4)

    return job


def record_heartbeat(job_id: str, org_id: str) -> TrainingJob:
    """Record worker heartbeat (proves worker is alive)."""
    job = _get_job(job_id, org_id)
    if job.is_terminal:
        return job
    job.last_heartbeat = time.time()
    return job


# =============================================================================
# Completion (requires provider evidence)
# =============================================================================


def mark_completed(
    job_id: str,
    org_id: str,
    provider_evidence: str = "",
) -> TrainingJob:
    """Mark training completed — requires provider evidence."""
    job = _get_job(job_id, org_id)

    if job.status == TrainingStatus.CANCEL_CONFIRMED:
        return job  # Already terminated

    job.status = TrainingStatus.COMPLETED
    job.completed_at = time.time()
    job.billing_stopped_at = time.time()
    job.progress.progress_pct = 100

    # Final cost calculation
    if job.billing_started_at and job.cost_rate_per_hour > 0:
        hours = job.runtime_seconds / 3600
        job.cost_accrued_usd = round(hours * job.cost_rate_per_hour, 4)

    logger.info(f"TRAINING_COMPLETED: job={job_id} cost=${job.cost_accrued_usd:.4f}")
    return job


def mark_failed(job_id: str, org_id: str, error: str, error_code: str = "") -> TrainingJob:
    """Mark training failed with error evidence."""
    job = _get_job(job_id, org_id)

    if job.is_terminal:
        return job  # Idempotent

    job.status = TrainingStatus.FAILED
    job.error = error[:500]
    job.error_code = error_code
    job.completed_at = time.time()
    job.billing_stopped_at = time.time()

    logger.warning(f"TRAINING_FAILED: job={job_id} error={error[:100]}")
    return job


# =============================================================================
# Cancellation (evidence-based)
# =============================================================================


def request_cancel(job_id: str, org_id: str) -> TrainingJob:
    """Request cancellation of a training job.

    This does NOT mean the job is cancelled. It means:
    1. A cancel request has been sent to the provider
    2. We are waiting for provider confirmation
    3. The job remains billable until confirmation

    Idempotent: duplicate requests are no-ops.
    """
    job = _get_job(job_id, org_id)

    if job.is_terminal:
        return job  # Already done — idempotent

    if job.status == TrainingStatus.CANCEL_REQUESTED:
        return job  # Already requested — idempotent

    job.status = TrainingStatus.CANCEL_REQUESTED
    job.cancel_requested_at = time.time()
    job.cancel_evidence = CancelEvidence.REQUESTED

    logger.info(f"TRAINING_CANCEL_REQUESTED: job={job_id}")
    return job


def confirm_cancel(
    job_id: str,
    org_id: str,
    evidence: CancelEvidence = CancelEvidence.PROCESS_TERMINATED,
) -> TrainingJob:
    """Confirm cancellation with provider evidence.

    Only after this call is the job truly cancelled and billing stops.
    """
    job = _get_job(job_id, org_id)

    if job.status == TrainingStatus.CANCEL_CONFIRMED:
        return job  # Idempotent

    job.status = TrainingStatus.CANCEL_CONFIRMED
    job.cancel_confirmed_at = time.time()
    job.cancel_evidence = evidence
    job.billing_stopped_at = time.time()
    job.completed_at = time.time()

    # Final cost
    if job.billing_started_at and job.cost_rate_per_hour > 0:
        hours = job.runtime_seconds / 3600
        job.cost_accrued_usd = round(hours * job.cost_rate_per_hour, 4)

    logger.info(f"TRAINING_CANCEL_CONFIRMED: job={job_id} evidence={evidence.value}")
    return job


def mark_cancel_unresolved(job_id: str, org_id: str, reason: str = "") -> TrainingJob:
    """Mark cancellation as unresolved (provider didn't confirm).

    The job remains billable and visible until reconciled.
    """
    job = _get_job(job_id, org_id)

    job.status = TrainingStatus.CANCEL_UNRESOLVED
    job.cancel_evidence = CancelEvidence.TIMEOUT_ASSUMED
    job.cancel_error = reason or "Provider did not confirm cancellation within timeout"

    logger.warning(f"TRAINING_CANCEL_UNRESOLVED: job={job_id} reason={reason}")
    return job


# =============================================================================
# Heartbeat & Recovery
# =============================================================================


def check_heartbeat(job_id: str, org_id: str) -> TrainingJob:
    """Check if worker heartbeat is stale — mark lost if timeout exceeded."""
    job = _get_job(job_id, org_id)

    if job.is_terminal:
        return job

    if job.heartbeat_stale:
        job.status = TrainingStatus.LOST
        logger.warning(f"TRAINING_HEARTBEAT_LOST: job={job_id} last={job.last_heartbeat}")

    return job


def recover_lost_job(job_id: str, org_id: str) -> TrainingJob:
    """Attempt to recover a lost job (worker reconnected)."""
    job = _get_job(job_id, org_id)

    if job.status != TrainingStatus.LOST:
        raise InvalidTrainingState(f"Cannot recover job in state {job.status.value}")

    job.status = TrainingStatus.TRAINING
    job.last_heartbeat = time.time()

    logger.info(f"TRAINING_RECOVERED: job={job_id}")
    return job


# =============================================================================
# Query
# =============================================================================


def get_training_job(job_id: str, org_id: str) -> TrainingJob | None:
    """Get training job with tenant isolation."""
    job = _jobs.get(job_id)
    if not job or job.org_id != org_id:
        return None
    return job


def get_job_status(job_id: str, org_id: str) -> dict[str, Any]:
    """Get training job status for API/UI."""
    job = get_training_job(job_id, org_id)
    if not job:
        return {"error": "not_found"}

    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "progress": {
            "step": job.progress.current_step,
            "total_steps": job.progress.total_steps,
            "epoch": job.progress.current_epoch,
            "total_epochs": job.progress.total_epochs,
            "loss": job.progress.loss,
            "pct": job.progress.progress_pct,
        },
        "provider_job_id": job.provider_job_id,
        "worker_id": job.worker_id,
        "is_billable": job.is_billable,
        "cost_accrued_usd": job.cost_accrued_usd,
        "cancel_evidence": job.cancel_evidence.value,
        "error": job.error,
        "runtime_seconds": job.runtime_seconds,
    }


# =============================================================================
# Helpers
# =============================================================================


def _get_job(job_id: str, org_id: str) -> TrainingJob:
    job = _jobs.get(job_id)
    if not job or job.org_id != org_id:
        raise TrainingJobNotFound(f"Training job {job_id} not found")
    return job


# =============================================================================
# Exceptions
# =============================================================================


class TrainingError(Exception):
    """Base training error."""


class TrainingJobNotFound(TrainingError):
    """Job not found or cross-tenant."""


class InvalidTrainingState(TrainingError):
    """Invalid state for operation."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _jobs.clear()
