"""Background Generation Job System — Story 053.

Splits generation submission (API) from execution (worker). Jobs are durable,
survive browser closure and API restarts, and support cancel/retry/reconnect.

Lifecycle:
    submit (API)    → QUEUED
    claim (worker)  → CLAIMED
    start (worker)  → RUNNING (with progress + heartbeat)
    complete        → COMPLETED (asset registered, cost recorded)
    fail            → FAILED (retryable)
    cancel (user)   → CANCELLED (idempotent)
    retry (user)    → re-QUEUED from FAILED/CANCELLED

Key properties:
    - Submission returns promptly with job_id (no waiting for provider)
    - Worker claims job exclusively (prevents duplicate execution)
    - Progress/heartbeat persisted (visible to polling clients)
    - Browser closure does not cancel or lose work
    - Completed jobs reference authoritative assets with lineage
    - Costs, provider/model versions, and effective settings persisted
    - Cancel and retry are idempotent
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


# =============================================================================
# Job States
# =============================================================================


class GenerationState(str, Enum):
    """Generation job lifecycle states."""

    QUEUED = "queued"          # Submitted, waiting for worker
    CLAIMED = "claimed"        # Worker picked it up
    RUNNING = "running"        # Provider is executing
    COMPLETED = "completed"    # Output asset registered
    FAILED = "failed"          # Provider/system error (retryable)
    CANCELLED = "cancelled"    # User-requested cancellation
    TIMEOUT = "timeout"        # Heartbeat expired (retryable)

    @property
    def is_terminal(self) -> bool:
        return self in (GenerationState.COMPLETED, GenerationState.CANCELLED)

    @property
    def is_retryable(self) -> bool:
        return self in (GenerationState.FAILED, GenerationState.TIMEOUT, GenerationState.CANCELLED)

    @property
    def is_active(self) -> bool:
        return self in (GenerationState.QUEUED, GenerationState.CLAIMED, GenerationState.RUNNING)


# =============================================================================
# Generation Job Record
# =============================================================================


@dataclass
class GenerationJob:
    """A durable generation job record."""

    id: str
    org_id: str
    user_id: str
    session_id: str
    # Request
    prompt: str
    negative_prompt: str = ""
    model: str = "flux-dev"
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg: float = 3.5
    seed: int = -1
    # Context
    talent_id: str | None = None
    project_id: str | None = None
    lora_ids: list[str] = field(default_factory=list)
    # Lifecycle
    state: GenerationState = GenerationState.QUEUED
    progress: float = 0.0  # 0.0 to 1.0
    # Worker
    worker_id: str | None = None
    claimed_at: str | None = None
    last_heartbeat: str | None = None
    # Result
    output_asset_id: str | None = None
    output_url: str | None = None
    error: str = ""
    attempt: int = 0
    max_attempts: int = 3
    # Cost & lineage
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    provider_used: str = ""
    model_version: str = ""
    effective_settings: dict[str, Any] = field(default_factory=dict)
    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    # Idempotency
    idempotency_key: str = ""

    def to_status(self) -> dict:
        """Client-facing status view (for polling)."""
        return {
            "job_id": self.id,
            "state": self.state.value,
            "progress": self.progress,
            "model": self.model,
            "output_asset_id": self.output_asset_id,
            "output_url": self.output_url,
            "error": self.error,
            "attempt": self.attempt,
            "estimated_cost_usd": self.estimated_cost_usd,
            "actual_cost_usd": self.actual_cost_usd,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "is_terminal": self.state.is_terminal,
            "is_retryable": self.state.is_retryable,
        }


# =============================================================================
# Job Store (in-memory, production: Supabase jobs table)
# =============================================================================

_job_store: dict[str, GenerationJob] = {}
_idempotency_index: dict[str, str] = {}
_store_lock = threading.Lock()

# Queue: list of job IDs ready for workers to claim
_job_queue: list[str] = []


def _make_job_id() -> str:
    return f"gen-{secrets.token_hex(10)}"


# =============================================================================
# Submission (API-side — returns promptly)
# =============================================================================


class SubmissionError(Exception):
    """Raised when job cannot be submitted."""
    pass


def submit_generation(
    *,
    org_id: str,
    user_id: str,
    session_id: str = "",
    prompt: str,
    negative_prompt: str = "",
    model: str = "flux-dev",
    width: int = 1024,
    height: int = 1024,
    steps: int = 20,
    cfg: float = 3.5,
    seed: int = -1,
    talent_id: str | None = None,
    project_id: str | None = None,
    lora_ids: list[str] | None = None,
    estimated_cost_usd: float = 0.0,
    idempotency_key: str = "",
) -> GenerationJob:
    """Submit a generation job — returns immediately with job_id.

    The job is persisted and enqueued for background worker execution.
    Browser can close — job survives.

    Args:
        org_id: Workspace (from trusted auth context)
        user_id: Actor (from trusted auth context)
        prompt: Generation prompt
        ...other params...
        idempotency_key: Prevents duplicate submission

    Returns:
        GenerationJob in QUEUED state

    Raises:
        SubmissionError: If validation fails
    """
    if not org_id:
        raise SubmissionError("org_id required")
    if not user_id:
        raise SubmissionError("user_id required")
    if not prompt:
        raise SubmissionError("prompt required")

    # Idempotency check
    if idempotency_key:
        with _store_lock:
            if idempotency_key in _idempotency_index:
                existing_id = _idempotency_index[idempotency_key]
                if existing_id in _job_store:
                    return _job_store[existing_id]

    # Create job record
    job = GenerationJob(
        id=_make_job_id(),
        org_id=org_id,
        user_id=user_id,
        session_id=session_id,
        prompt=prompt,
        negative_prompt=negative_prompt,
        model=model,
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
        seed=seed,
        talent_id=talent_id,
        project_id=project_id,
        lora_ids=lora_ids or [],
        estimated_cost_usd=estimated_cost_usd,
        idempotency_key=idempotency_key,
    )

    # Persist and enqueue
    with _store_lock:
        _job_store[job.id] = job
        _job_queue.append(job.id)
        if idempotency_key:
            _idempotency_index[idempotency_key] = job.id

    return job


# =============================================================================
# Worker Execution (background — independent of API process)
# =============================================================================


def claim_job(worker_id: str) -> GenerationJob | None:
    """Worker claims the next available job from the queue.

    Returns None if queue is empty. Only one worker can claim each job.
    """
    with _store_lock:
        while _job_queue:
            job_id = _job_queue.pop(0)
            job = _job_store.get(job_id)
            if not job:
                continue
            if job.state != GenerationState.QUEUED:
                continue  # Already claimed or cancelled

            # Claim it
            job.state = GenerationState.CLAIMED
            job.worker_id = worker_id
            job.claimed_at = datetime.now(UTC).isoformat()
            return job

    return None


def start_execution(job_id: str) -> bool:
    """Mark job as running (worker is calling provider)."""
    job = _job_store.get(job_id)
    if not job or job.state != GenerationState.CLAIMED:
        return False

    job.state = GenerationState.RUNNING
    job.started_at = datetime.now(UTC).isoformat()
    job.last_heartbeat = datetime.now(UTC).isoformat()
    return True


def update_progress(job_id: str, progress: float) -> bool:
    """Update job progress (0.0 to 1.0) and heartbeat."""
    job = _job_store.get(job_id)
    if not job or job.state != GenerationState.RUNNING:
        return False

    job.progress = min(max(progress, 0.0), 1.0)
    job.last_heartbeat = datetime.now(UTC).isoformat()
    return True


def complete_job(
    job_id: str,
    *,
    output_asset_id: str,
    output_url: str = "",
    actual_cost_usd: float = 0.0,
    provider_used: str = "",
    model_version: str = "",
    effective_settings: dict | None = None,
) -> bool:
    """Mark job as completed with output asset and cost."""
    job = _job_store.get(job_id)
    if not job or job.state not in (GenerationState.RUNNING, GenerationState.CLAIMED):
        return False

    job.state = GenerationState.COMPLETED
    job.progress = 1.0
    job.output_asset_id = output_asset_id
    job.output_url = output_url
    job.actual_cost_usd = actual_cost_usd
    job.provider_used = provider_used
    job.model_version = model_version
    job.effective_settings = effective_settings or {}
    job.completed_at = datetime.now(UTC).isoformat()
    return True


def fail_job(job_id: str, error: str) -> bool:
    """Mark job as failed (retryable)."""
    job = _job_store.get(job_id)
    if not job or job.state.is_terminal:
        return False

    job.state = GenerationState.FAILED
    job.error = error[:500]
    job.completed_at = datetime.now(UTC).isoformat()
    return True


# =============================================================================
# Cancel / Retry / Status (user-facing)
# =============================================================================


def cancel_job(job_id: str, org_id: str) -> GenerationJob | None:
    """Cancel a job (idempotent, tenant-scoped).

    Only cancels active jobs. Already-cancelled returns the job.
    Wrong org returns None (no existence leak).
    """
    job = _job_store.get(job_id)
    if not job or job.org_id != org_id:
        return None

    if job.state == GenerationState.CANCELLED:
        return job  # Idempotent

    if job.state.is_terminal:
        return job  # Can't cancel completed

    job.state = GenerationState.CANCELLED
    job.completed_at = datetime.now(UTC).isoformat()
    return job


def retry_job(job_id: str, org_id: str) -> GenerationJob | None:
    """Retry a failed/cancelled job (re-enqueues, idempotent).

    Creates a new attempt on the same job record.
    Wrong org returns None. Non-retryable returns the job as-is.
    """
    job = _job_store.get(job_id)
    if not job or job.org_id != org_id:
        return None

    if not job.state.is_retryable:
        return job  # Can't retry active or completed

    if job.attempt >= job.max_attempts:
        return job  # Max attempts reached

    # Reset for retry
    job.state = GenerationState.QUEUED
    job.attempt += 1
    job.error = ""
    job.progress = 0.0
    job.worker_id = None
    job.claimed_at = None
    job.started_at = None
    job.completed_at = None
    job.last_heartbeat = None

    with _store_lock:
        _job_queue.append(job.id)

    return job


def get_job_status(job_id: str, org_id: str) -> dict | None:
    """Get current job status (tenant-scoped — wrong org returns None)."""
    job = _job_store.get(job_id)
    if not job or job.org_id != org_id:
        return None
    return job.to_status()


def list_jobs_for_session(session_id: str, org_id: str) -> list[dict]:
    """List all generation jobs for a session (for reconnect/resume)."""
    return [
        job.to_status()
        for job in _job_store.values()
        if job.session_id == session_id and job.org_id == org_id
    ]


# =============================================================================
# Heartbeat / Timeout Detection
# =============================================================================

HEARTBEAT_TIMEOUT_SECONDS = 120  # 2 minutes without heartbeat = timeout


def check_stale_jobs() -> list[str]:
    """Find jobs whose worker hasn't heartbeated (for scheduler to clean up).

    Returns list of job IDs that timed out.
    """
    now = datetime.now(UTC)
    timed_out = []

    for job in _job_store.values():
        if job.state != GenerationState.RUNNING:
            continue
        if not job.last_heartbeat:
            continue

        try:
            last_hb = datetime.fromisoformat(job.last_heartbeat)
            if (now - last_hb) > timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS):
                job.state = GenerationState.TIMEOUT
                job.error = "Worker heartbeat timeout"
                timed_out.append(job.id)
        except (ValueError, TypeError):
            pass

    return timed_out
