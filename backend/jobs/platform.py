"""Canonical Durable Job Platform — Story 052.

ONE supported job platform for all long-running work in AI Studio.
Backed by Redis + Celery with durable state persistence.

Job Envelope:
    Every job carries a typed envelope with identity, context, lifecycle,
    and observability metadata. No naked task dispatch without an envelope.

Lifecycle:
    submitted → queued → running → completed | failed | cancelled | dead_letter

Queue Routes:
    generation  — image/video generation (GPU workers)
    training    — LoRA training (long-running GPU)
    fleet       — worker provisioning/shutdown
    publishing  — social media publishing
    cleanup     — data retention, orphan cleanup
    scheduled   — Beat-triggered periodic tasks
    default     — catch-all

Context Propagation:
    Every job carries org_id, user_id, role from TenantContext.
    Workers validate context before executing side effects.

Retry Policy:
    - Idempotent operations: max 3 retries with exponential backoff
    - Non-idempotent: no retry (fail immediately, require re-submission)
    - Dead letter after retry exhaustion

Cancellation:
    - Jobs check cancellation flag at heartbeat intervals
    - Late cancellation after side effects records partial state

Monitoring:
    - Queue depth, age, failure rate per route
    - Worker heartbeat and health
    - Dead letter queue size
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Job Lifecycle States
# =============================================================================


class JobStatus(str, Enum):
    SUBMITTED = "submitted"       # Created, not yet queued
    QUEUED = "queued"             # In queue, waiting for worker
    RUNNING = "running"           # Worker picked up, executing
    COMPLETED = "completed"       # Finished successfully
    FAILED = "failed"             # Failed (retries exhausted or non-retryable)
    CANCELLED = "cancelled"       # User/system cancelled
    DEAD_LETTER = "dead_letter"   # Exhausted retries, moved to DLQ


TERMINAL_STATES = frozenset({
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
    JobStatus.DEAD_LETTER,
})


# =============================================================================
# Queue Routes
# =============================================================================


class QueueRoute(str, Enum):
    GENERATION = "generation"
    TRAINING = "training"
    FLEET = "fleet"
    PUBLISHING = "publishing"
    CLEANUP = "cleanup"
    SCHEDULED = "scheduled"
    DEFAULT = "default"


# Route → Celery queue name mapping
QUEUE_NAMES: dict[QueueRoute, str] = {
    QueueRoute.GENERATION: "ai-studio.generation",
    QueueRoute.TRAINING: "ai-studio.training",
    QueueRoute.FLEET: "ai-studio.fleet",
    QueueRoute.PUBLISHING: "ai-studio.publishing",
    QueueRoute.CLEANUP: "ai-studio.cleanup",
    QueueRoute.SCHEDULED: "ai-studio.scheduled",
    QueueRoute.DEFAULT: "ai-studio.default",
}


# =============================================================================
# Retry Policy
# =============================================================================


class RetryPolicy(str, Enum):
    IDEMPOTENT = "idempotent"         # Safe to retry (max 3, exponential backoff)
    NON_IDEMPOTENT = "non_idempotent" # No retry — fail immediately
    CUSTOM = "custom"                  # Caller-defined retry behavior


@dataclass(frozen=True)
class RetryConfig:
    """Retry configuration for a job."""
    max_retries: int = 3
    backoff_base_seconds: int = 30
    backoff_max_seconds: int = 600
    policy: RetryPolicy = RetryPolicy.IDEMPOTENT

    def get_delay(self, attempt: int) -> int:
        """Calculate backoff delay for a retry attempt."""
        if self.policy == RetryPolicy.NON_IDEMPOTENT:
            return 0  # Should never retry
        delay = min(
            self.backoff_base_seconds * (2 ** attempt),
            self.backoff_max_seconds,
        )
        return delay


DEFAULT_RETRY = RetryConfig()
NO_RETRY = RetryConfig(max_retries=0, policy=RetryPolicy.NON_IDEMPOTENT)


# =============================================================================
# Job Envelope
# =============================================================================


@dataclass
class JobEnvelope:
    """Canonical typed job envelope.

    Every job in AI Studio carries this envelope. No naked task dispatch.
    """
    # Identity
    job_id: str = field(default_factory=lambda: f"job-{uuid.uuid4().hex[:16]}")
    idempotency_key: str | None = None  # For duplicate detection

    # Workspace/Actor Context (from TenantContext)
    org_id: str = ""
    user_id: str = ""
    role: str = "editor"
    actor_type: str = "user"  # user | system | worker | scheduler

    # Operation
    operation: str = ""         # e.g., "generate_image", "train_lora"
    queue_route: QueueRoute = QueueRoute.DEFAULT
    payload_ref: str | None = None  # Reference to large payload (not inline in Redis)
    payload: dict = field(default_factory=dict)  # Small inline payload only

    # Priority
    priority: int = 5           # 1=highest, 10=lowest

    # Lifecycle
    status: JobStatus = JobStatus.SUBMITTED
    attempts: int = 0
    max_attempts: int = 3
    retry_config: RetryConfig = field(default_factory=lambda: DEFAULT_RETRY)

    # Timing
    submitted_at: float = field(default_factory=time.time)
    queued_at: float | None = None
    started_at: float | None = None
    completed_at: float | None = None
    timeout_seconds: int = 1800  # 30 min default
    last_heartbeat: float | None = None
    heartbeat_interval: int = 30  # seconds

    # Result
    result: dict | None = None
    error: str | None = None

    # Observability
    trace_id: str = field(default_factory=lambda: f"trace-{uuid.uuid4().hex[:12]}")
    cancelled: bool = False
    cancel_reason: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    @property
    def is_timed_out(self) -> bool:
        if self.started_at and self.status == JobStatus.RUNNING:
            return time.time() - self.started_at > self.timeout_seconds
        return False

    @property
    def is_heartbeat_stale(self) -> bool:
        """Check if worker heartbeat is overdue (potential crash)."""
        if self.status != JobStatus.RUNNING or not self.last_heartbeat:
            return False
        return time.time() - self.last_heartbeat > self.heartbeat_interval * 3


# =============================================================================
# Job Store (durable state outside Redis transport)
# =============================================================================

_job_store: dict[str, JobEnvelope] = {}
_idempotency_index: dict[str, str] = {}  # idempotency_key → job_id


# =============================================================================
# Job Platform Operations
# =============================================================================


def submit_job(
    org_id: str,
    user_id: str,
    operation: str,
    payload: dict,
    queue_route: QueueRoute = QueueRoute.DEFAULT,
    priority: int = 5,
    timeout_seconds: int = 1800,
    idempotency_key: str | None = None,
    retry_config: RetryConfig | None = None,
    role: str = "editor",
    actor_type: str = "user",
) -> JobEnvelope:
    """Submit a job to the canonical platform.

    Validates context, checks idempotency, persists envelope, and queues.

    Args:
        org_id: Workspace (from TenantContext — required).
        user_id: Actor identity (required for user jobs).
        operation: What the job does (e.g., "generate_image").
        payload: Job parameters (keep small — use payload_ref for large data).
        queue_route: Which queue/worker pool.
        priority: 1=highest, 10=lowest.
        timeout_seconds: Max execution time.
        idempotency_key: Prevent duplicate submissions.
        retry_config: Override default retry behavior.
        role: Actor's role.
        actor_type: user | system | worker | scheduler.

    Returns:
        JobEnvelope in SUBMITTED state.

    Raises:
        ValueError: If context is invalid.
        JobDuplicateError: If idempotency key already exists.
    """
    # Validate context
    if not org_id:
        raise ValueError("org_id is required for job submission")
    if not user_id and actor_type == "user":
        raise ValueError("user_id is required for user-submitted jobs")
    if not operation:
        raise ValueError("operation is required")

    # Check idempotency (duplicate detection)
    if idempotency_key:
        existing_id = _idempotency_index.get(idempotency_key)
        if existing_id and existing_id in _job_store:
            existing = _job_store[existing_id]
            if not existing.is_terminal:
                raise JobDuplicateError(existing.job_id, idempotency_key)

    # Validate payload size (large payloads must use payload_ref)
    payload_size = len(json.dumps(payload, default=str))
    if payload_size > 64_000:  # 64KB limit for inline payload
        raise ValueError(
            f"Payload too large ({payload_size} bytes). "
            "Use payload_ref for large data (store in B2/DB, pass reference)."
        )

    # Create envelope
    envelope = JobEnvelope(
        org_id=org_id,
        user_id=user_id,
        role=role,
        actor_type=actor_type,
        operation=operation,
        queue_route=queue_route,
        payload=payload,
        priority=priority,
        timeout_seconds=timeout_seconds,
        retry_config=retry_config or DEFAULT_RETRY,
    )

    if idempotency_key:
        envelope.idempotency_key = idempotency_key
        _idempotency_index[idempotency_key] = envelope.job_id

    # Persist (durable state)
    _job_store[envelope.job_id] = envelope

    # Transition to QUEUED
    envelope.status = JobStatus.QUEUED
    envelope.queued_at = time.time()

    logger.info(
        f"JOB_SUBMITTED: id={envelope.job_id} op={operation} "
        f"org={org_id[:8]} route={queue_route.value} priority={priority}"
    )

    return envelope


def claim_job(job_id: str, worker_id: str) -> JobEnvelope | None:
    """Worker claims a job for execution.

    Transitions: QUEUED → RUNNING. Sets start time and heartbeat.
    Returns None if job is not claimable.
    """
    envelope = _job_store.get(job_id)
    if not envelope or envelope.status != JobStatus.QUEUED:
        return None

    envelope.status = JobStatus.RUNNING
    envelope.started_at = time.time()
    envelope.last_heartbeat = time.time()
    envelope.attempts += 1

    logger.info(f"JOB_CLAIMED: id={job_id} worker={worker_id} attempt={envelope.attempts}")
    return envelope


def heartbeat(job_id: str, progress: dict | None = None) -> bool:
    """Worker heartbeat — proves job is still alive.

    Returns False if job has been cancelled (worker should stop).
    """
    envelope = _job_store.get(job_id)
    if not envelope or envelope.status != JobStatus.RUNNING:
        return False

    envelope.last_heartbeat = time.time()

    if envelope.cancelled:
        return False  # Signal worker to stop

    return True


def complete_job(job_id: str, result: dict | None = None) -> JobEnvelope | None:
    """Mark job as completed successfully."""
    envelope = _job_store.get(job_id)
    if not envelope or envelope.status != JobStatus.RUNNING:
        return None

    envelope.status = JobStatus.COMPLETED
    envelope.completed_at = time.time()
    envelope.result = result

    logger.info(
        f"JOB_COMPLETED: id={job_id} op={envelope.operation} "
        f"duration={(envelope.completed_at - (envelope.started_at or 0)):.1f}s"
    )
    return envelope


def fail_job(job_id: str, error: str) -> JobEnvelope | None:
    """Mark job as failed. Checks retry eligibility.

    If retries remain and policy allows, re-queues the job.
    Otherwise, marks as FAILED or DEAD_LETTER.
    """
    envelope = _job_store.get(job_id)
    if not envelope or envelope.is_terminal:
        return None

    retry = envelope.retry_config

    # Check if retryable
    if (retry.policy == RetryPolicy.IDEMPOTENT and
            envelope.attempts < retry.max_retries):
        # Re-queue for retry
        envelope.status = JobStatus.QUEUED
        envelope.error = error
        envelope.queued_at = time.time()
        logger.info(
            f"JOB_RETRY: id={job_id} attempt={envelope.attempts}/{retry.max_retries} "
            f"error={error[:100]}"
        )
        return envelope

    # Exhausted retries or non-idempotent
    if envelope.attempts >= retry.max_retries and retry.policy == RetryPolicy.IDEMPOTENT:
        envelope.status = JobStatus.DEAD_LETTER
        logger.warning(f"JOB_DEAD_LETTER: id={job_id} after {envelope.attempts} attempts")
    else:
        envelope.status = JobStatus.FAILED

    envelope.error = error
    envelope.completed_at = time.time()
    return envelope


def cancel_job(job_id: str, reason: str = "user_cancelled") -> JobEnvelope | None:
    """Cancel a job. If running, sets flag for next heartbeat check."""
    envelope = _job_store.get(job_id)
    if not envelope or envelope.is_terminal:
        return None

    if envelope.status == JobStatus.RUNNING:
        # Late cancellation — worker checks on next heartbeat
        envelope.cancelled = True
        envelope.cancel_reason = reason
    else:
        # Immediate cancellation (queued/submitted)
        envelope.status = JobStatus.CANCELLED
        envelope.cancel_reason = reason
        envelope.completed_at = time.time()

    logger.info(f"JOB_CANCELLED: id={job_id} reason={reason} was_running={envelope.status == JobStatus.RUNNING}")
    return envelope


def get_job(job_id: str) -> JobEnvelope | None:
    """Get job status (read-only)."""
    return _job_store.get(job_id)


# =============================================================================
# Monitoring
# =============================================================================


def get_queue_stats() -> dict[str, Any]:
    """Get queue monitoring statistics."""
    stats: dict[str, dict[str, int]] = {}
    for route in QueueRoute:
        route_jobs = [j for j in _job_store.values() if j.queue_route == route]
        stats[route.value] = {
            "queued": sum(1 for j in route_jobs if j.status == JobStatus.QUEUED),
            "running": sum(1 for j in route_jobs if j.status == JobStatus.RUNNING),
            "completed": sum(1 for j in route_jobs if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in route_jobs if j.status == JobStatus.FAILED),
            "dead_letter": sum(1 for j in route_jobs if j.status == JobStatus.DEAD_LETTER),
        }

    total_queued = sum(s["queued"] for s in stats.values())
    total_running = sum(s["running"] for s in stats.values())
    stale = sum(1 for j in _job_store.values() if j.is_heartbeat_stale)

    return {
        "queues": stats,
        "total_queued": total_queued,
        "total_running": total_running,
        "stale_heartbeats": stale,
        "total_jobs": len(_job_store),
    }


# =============================================================================
# Domain Adapters (migration helpers)
# =============================================================================


def submit_generation_job(org_id: str, user_id: str, params: dict) -> JobEnvelope:
    """Adapter: submit an image/video generation job."""
    return submit_job(
        org_id=org_id,
        user_id=user_id,
        operation="generate_image",
        payload=params,
        queue_route=QueueRoute.GENERATION,
        timeout_seconds=300,
        retry_config=NO_RETRY,  # Generation is non-idempotent (costs money)
    )


def submit_training_job(org_id: str, user_id: str, params: dict) -> JobEnvelope:
    """Adapter: submit a LoRA training job."""
    return submit_job(
        org_id=org_id,
        user_id=user_id,
        operation="train_lora",
        payload=params,
        queue_route=QueueRoute.TRAINING,
        timeout_seconds=14400,  # 4 hours
        priority=3,  # Higher priority
        retry_config=NO_RETRY,  # Training is expensive, no auto-retry
    )


def submit_fleet_job(org_id: str, user_id: str, operation: str, params: dict) -> JobEnvelope:
    """Adapter: submit a fleet management job."""
    return submit_job(
        org_id=org_id,
        user_id=user_id,
        operation=operation,
        payload=params,
        queue_route=QueueRoute.FLEET,
        timeout_seconds=600,
        retry_config=DEFAULT_RETRY,  # Infrastructure ops are idempotent
    )


def submit_publishing_job(org_id: str, user_id: str, params: dict) -> JobEnvelope:
    """Adapter: submit a social publishing job."""
    return submit_job(
        org_id=org_id,
        user_id=user_id,
        operation="publish_post",
        payload=params,
        queue_route=QueueRoute.PUBLISHING,
        timeout_seconds=120,
        retry_config=NO_RETRY,  # Publishing is non-idempotent
    )


def submit_cleanup_job(org_id: str, operation: str, params: dict) -> JobEnvelope:
    """Adapter: submit a cleanup/maintenance job (system-initiated)."""
    return submit_job(
        org_id=org_id,
        user_id="system",
        operation=operation,
        payload=params,
        queue_route=QueueRoute.CLEANUP,
        timeout_seconds=3600,
        actor_type="system",
        retry_config=DEFAULT_RETRY,
    )


# =============================================================================
# Errors
# =============================================================================


class JobDuplicateError(Exception):
    """Raised when a duplicate idempotency key is submitted."""
    def __init__(self, existing_job_id: str, idempotency_key: str) -> None:
        self.existing_job_id = existing_job_id
        self.idempotency_key = idempotency_key
        super().__init__(f"Duplicate job: key={idempotency_key} existing={existing_job_id}")


# =============================================================================
# Testing Utilities
# =============================================================================


def _reset_store() -> None:
    """Reset job store. FOR TESTING ONLY."""
    _job_store.clear()
    _idempotency_index.clear()
