"""Atomic Job Claiming — Story 054.

Transactional lease-based job claiming that prevents duplicate execution.
Only ONE worker can hold a lease on a job at any time.

Algorithm:
    1. Worker requests claim with: worker_id, org_id, queue, capabilities
    2. System atomically finds eligible job AND sets lease (single operation)
    3. Lease includes: owner, token, start, expiry, heartbeat, attempt
    4. Only the active lease holder can mutate job state
    5. Expired leases are recoverable based on idempotency/side-effect state

Lease fields:
    lease_token    — Unique per-claim (UUID), required for all mutations
    lease_owner    — Worker identity that holds the lease
    lease_start    — When the lease was acquired
    lease_expiry   — When the lease expires if not renewed
    lease_heartbeat — Last heartbeat from the lease holder
    attempt_number — Which attempt this is (for retry tracking)
    side_effect_marker — Whether external side effects may have occurred

Concurrency guarantee:
    The claim uses an atomic compare-and-swap pattern:
    UPDATE ... SET lease_token=X WHERE status='queued' AND lease_token IS NULL
    Only one concurrent caller can succeed (database row-level lock).

Recovery policy:
    - Expired lease + no side_effect_marker → safe to re-lease
    - Expired lease + side_effect_marker → REQUIRES manual review or idempotent retry
    - Stale heartbeat (3x interval) → lease considered abandoned
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Lease defaults
DEFAULT_LEASE_DURATION_SECONDS = 300  # 5 minutes
DEFAULT_HEARTBEAT_INTERVAL = 30      # seconds
STALE_HEARTBEAT_FACTOR = 3           # 3x interval = considered abandoned


# =============================================================================
# Lease Record
# =============================================================================


@dataclass
class JobLease:
    """An active lease on a job — proof of exclusive execution rights."""
    lease_token: str = field(default_factory=lambda: f"lease-{uuid.uuid4().hex}")
    lease_owner: str = ""              # Worker identity
    lease_start: float = field(default_factory=time.time)
    lease_expiry: float = 0.0          # When lease expires
    lease_heartbeat: float = field(default_factory=time.time)
    attempt_number: int = 1
    side_effect_marker: bool = False   # True if external side effects may have occurred
    org_id: str = ""                   # Authorized workspace
    queue: str = ""                    # Authorized queue

    @property
    def is_expired(self) -> bool:
        return time.time() > self.lease_expiry

    @property
    def is_heartbeat_stale(self) -> bool:
        threshold = self.lease_heartbeat + (DEFAULT_HEARTBEAT_INTERVAL * STALE_HEARTBEAT_FACTOR)
        return time.time() > threshold

    @property
    def is_abandoned(self) -> bool:
        """Lease is considered abandoned if expired OR heartbeat stale."""
        return self.is_expired or self.is_heartbeat_stale


# =============================================================================
# Errors
# =============================================================================


class ClaimError(Exception):
    """Base claim error."""
    pass


class NoEligibleJobError(ClaimError):
    """No eligible job found for this worker."""
    pass


class LeaseRequiredError(ClaimError):
    """Operation requires active lease token but none/wrong provided."""
    def __init__(self, job_id: str, reason: str) -> None:
        self.job_id = job_id
        self.reason = reason
        super().__init__(f"Lease required for job {job_id}: {reason}")


class LeaseExpiredError(ClaimError):
    """Lease has expired — worker must stop."""
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Lease expired for job {job_id}")


class DuplicateClaimError(ClaimError):
    """Job already claimed by another worker."""
    def __init__(self, job_id: str, current_owner: str) -> None:
        self.job_id = job_id
        self.current_owner = current_owner
        super().__init__(f"Job {job_id} already claimed by {current_owner}")


# =============================================================================
# Claimable Job Record
# =============================================================================


@dataclass
class ClaimableJob:
    """A job record with lease state for atomic claiming."""
    job_id: str
    org_id: str
    queue: str
    operation: str
    priority: int = 5
    status: str = "queued"  # queued | running | completed | failed | cancelled
    payload: dict = field(default_factory=dict)

    # Lease state (None = unclaimed)
    lease: JobLease | None = None

    # Idempotency
    idempotency_key: str | None = None
    is_idempotent: bool = True

    # Cancellation
    cancelled: bool = False


# =============================================================================
# Atomic Claim Store
# =============================================================================

_job_registry: dict[str, ClaimableJob] = {}
_claim_lock = threading.Lock()  # Simulates DB row-level lock for in-memory store


def register_job(
    job_id: str,
    org_id: str,
    queue: str,
    operation: str,
    payload: dict | None = None,
    priority: int = 5,
    is_idempotent: bool = True,
    idempotency_key: str | None = None,
) -> ClaimableJob:
    """Register a job as claimable."""
    job = ClaimableJob(
        job_id=job_id,
        org_id=org_id,
        queue=queue,
        operation=operation,
        payload=payload or {},
        priority=priority,
        is_idempotent=is_idempotent,
        idempotency_key=idempotency_key,
    )
    _job_registry[job_id] = job
    return job


# =============================================================================
# Atomic Claim Operation
# =============================================================================


def atomic_claim(
    worker_id: str,
    org_id: str,
    queue: str,
    capabilities: frozenset[str] | None = None,
    lease_duration: int = DEFAULT_LEASE_DURATION_SECONDS,
) -> tuple[ClaimableJob, JobLease]:
    """Atomically claim the next eligible job.

    This is the SINGLE approved way to acquire work.
    Uses compare-and-swap semantics — only one caller can succeed per job.

    Args:
        worker_id: Unique worker identity.
        org_id: Workspace this worker is authorized for.
        queue: Queue this worker serves.
        capabilities: Optional capability filter.
        lease_duration: How long the lease lasts before requiring renewal.

    Returns:
        (job, lease) tuple. Lease token required for all subsequent mutations.

    Raises:
        NoEligibleJobError: No claimable job found.
    """
    with _claim_lock:  # Atomic — simulates DB transaction/row lock
        # Find eligible job
        eligible = _find_eligible_job(org_id, queue, capabilities)
        if not eligible:
            raise NoEligibleJobError()

        # Verify not already claimed (double-check under lock)
        if eligible.lease and not eligible.lease.is_abandoned:
            raise DuplicateClaimError(eligible.job_id, eligible.lease.lease_owner)

        # Determine attempt number
        attempt = 1
        if eligible.lease:
            attempt = eligible.lease.attempt_number + 1

        # Create lease (atomic assignment under lock)
        lease = JobLease(
            lease_owner=worker_id,
            lease_expiry=time.time() + lease_duration,
            attempt_number=attempt,
            org_id=org_id,
            queue=queue,
        )

        eligible.lease = lease
        eligible.status = "running"

        logger.info(
            f"ATOMIC_CLAIM: job={eligible.job_id} worker={worker_id} "
            f"token={lease.lease_token[:12]} attempt={attempt}"
        )

        return eligible, lease


def _find_eligible_job(
    org_id: str,
    queue: str,
    capabilities: frozenset[str] | None,
) -> ClaimableJob | None:
    """Find the highest-priority eligible job for this worker."""
    candidates = []
    for job in _job_registry.values():
        # Must be queued OR have abandoned lease
        if job.status == "queued" and (job.lease is None or job.lease.is_abandoned):
            pass
        elif job.status == "running" and job.lease and job.lease.is_abandoned:
            pass  # Abandoned — eligible for re-claim
        else:
            continue

        # Must match workspace
        if job.org_id != org_id:
            continue

        # Must match queue
        if job.queue != queue:
            continue

        # Must not be cancelled
        if job.cancelled:
            continue

        candidates.append(job)

    if not candidates:
        return None

    # Sort by priority (lowest number = highest priority), then by position
    candidates.sort(key=lambda j: j.priority)
    return candidates[0]


# =============================================================================
# Lease-Guarded Mutations
# =============================================================================


def verify_lease(job_id: str, lease_token: str) -> ClaimableJob:
    """Verify that the caller holds the active lease for a job.

    Raises:
        LeaseRequiredError: If token doesn't match.
        LeaseExpiredError: If lease has expired.
    """
    job = _job_registry.get(job_id)
    if not job:
        raise LeaseRequiredError(job_id, "Job not found")

    if not job.lease:
        raise LeaseRequiredError(job_id, "No active lease")

    if job.lease.lease_token != lease_token:
        raise LeaseRequiredError(job_id, "Lease token mismatch — another worker may hold the lease")

    if job.lease.is_expired:
        raise LeaseExpiredError(job_id)

    return job


def lease_heartbeat(job_id: str, lease_token: str, extend_seconds: int = DEFAULT_LEASE_DURATION_SECONDS) -> bool:
    """Renew lease heartbeat. Extends expiry.

    Returns False if job has been cancelled (worker should stop).
    """
    job = verify_lease(job_id, lease_token)
    job.lease.lease_heartbeat = time.time()
    job.lease.lease_expiry = time.time() + extend_seconds

    if job.cancelled:
        return False  # Signal cancellation to worker

    return True


def mark_side_effect(job_id: str, lease_token: str) -> None:
    """Mark that external side effects may have occurred.

    Call this BEFORE making irreversible external calls (GPU launch, API post).
    Affects recovery policy: jobs with side effects require manual review on re-lease.
    """
    job = verify_lease(job_id, lease_token)
    job.lease.side_effect_marker = True


def complete_with_lease(job_id: str, lease_token: str, result: dict | None = None) -> ClaimableJob:
    """Complete a job — requires active lease."""
    job = verify_lease(job_id, lease_token)
    job.status = "completed"
    logger.info(f"JOB_COMPLETE_LEASE: job={job_id} owner={job.lease.lease_owner}")
    return job


def fail_with_lease(job_id: str, lease_token: str, error: str) -> ClaimableJob:
    """Fail a job — requires active lease."""
    job = verify_lease(job_id, lease_token)

    if job.is_idempotent:
        # Re-queue for retry (release lease)
        job.status = "queued"
        # Keep lease info for attempt tracking but mark as releasable
        job.lease.lease_expiry = 0  # Expire immediately → claimable
    else:
        job.status = "failed"

    logger.info(f"JOB_FAIL_LEASE: job={job_id} error={error[:100]} idempotent={job.is_idempotent}")
    return job


def cancel_with_lease(job_id: str, lease_token: str) -> ClaimableJob:
    """Acknowledge cancellation — worker confirms it has stopped."""
    job = verify_lease(job_id, lease_token)
    job.status = "cancelled"
    job.cancelled = True
    return job


# =============================================================================
# Lease Recovery
# =============================================================================


def recover_abandoned_leases() -> list[str]:
    """Find and recover jobs with abandoned leases.

    Recovery policy:
    - No side_effect_marker + idempotent → re-queue safely
    - side_effect_marker → mark for manual review (status='needs_review')
    - Non-idempotent + abandoned → fail permanently

    Returns list of recovered job IDs.
    """
    recovered = []

    for job in _job_registry.values():
        if job.status != "running" or not job.lease or not job.lease.is_abandoned:
            continue

        if not job.lease.side_effect_marker and job.is_idempotent:
            # Safe to re-lease
            job.status = "queued"
            recovered.append(job.job_id)
            logger.info(f"LEASE_RECOVERED: job={job.job_id} (safe re-queue)")
        elif job.lease.side_effect_marker:
            # Needs manual review
            job.status = "failed"
            logger.warning(
                f"LEASE_ABANDONED_WITH_SIDE_EFFECTS: job={job.job_id} "
                f"owner={job.lease.lease_owner} — requires manual review"
            )
        else:
            # Non-idempotent, abandoned
            job.status = "failed"
            logger.warning(f"LEASE_ABANDONED_NON_IDEMPOTENT: job={job.job_id}")

    return recovered


# =============================================================================
# Stale Completion Guard
# =============================================================================


def reject_stale_completion(job_id: str, lease_token: str) -> bool:
    """Check if a completion attempt is from a stale (expired/re-leased) worker.

    Returns True if the completion should be REJECTED (stale worker).
    """
    job = _job_registry.get(job_id)
    if not job or not job.lease:
        return True  # No job or no lease — reject

    if job.lease.lease_token != lease_token:
        # Different lease token — this is a stale worker from a previous attempt
        logger.warning(
            f"STALE_COMPLETION_REJECTED: job={job_id} "
            f"stale_token={lease_token[:12]} current_token={job.lease.lease_token[:12]}"
        )
        return True

    return False


# =============================================================================
# Testing Utilities
# =============================================================================


def _reset_store() -> None:
    """Reset claim store. FOR TESTING ONLY."""
    _job_registry.clear()
