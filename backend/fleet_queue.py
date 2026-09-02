"""Durable Fleet Queue — Story 055.

Replaces in-memory fleet assignment with persistent jobs, atomic leases,
heartbeat/retry/cancel, linked to canonical generation jobs.

Properties:
    1. Persisted before assignment (survives restarts)
    2. Atomic lease: only ONE worker can claim a job (prevents duplicate execution)
    3. Workspace-scoped: every job carries org_id + authorization context
    4. Model-aware: jobs specify required model/specialty
    5. Heartbeat-monitored: stale leases are reclaimed
    6. Linked: fleet job references canonical generation_job_id
    7. Cost-reserved: estimated cost tracked from submission

Lifecycle:
    PENDING → LEASED → EXECUTING → COMPLETED | FAILED | CANCELLED | LEASE_EXPIRED
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


# =============================================================================
# Fleet Job States
# =============================================================================


class FleetJobState(str, Enum):
    PENDING = "pending"            # Queued, waiting for worker
    LEASED = "leased"              # Worker claimed exclusively
    EXECUTING = "executing"        # Provider invoked
    COMPLETED = "completed"        # Output delivered
    FAILED = "failed"              # Execution error (retryable)
    CANCELLED = "cancelled"        # User or system cancelled
    LEASE_EXPIRED = "lease_expired" # Worker didn't heartbeat (retryable)

    @property
    def is_terminal(self) -> bool:
        return self in (FleetJobState.COMPLETED, FleetJobState.CANCELLED)

    @property
    def is_claimable(self) -> bool:
        return self == FleetJobState.PENDING

    @property
    def is_retryable(self) -> bool:
        return self in (FleetJobState.FAILED, FleetJobState.LEASE_EXPIRED)


# =============================================================================
# Fleet Job Record
# =============================================================================

DEFAULT_LEASE_SECONDS = 300  # 5 minutes


@dataclass
class FleetJob:
    """A durable fleet execution job with atomic lease."""

    id: str
    # Canonical linkage
    generation_job_id: str  # Links to GenerationJob from Story 053
    # Workspace context (trusted, not client-supplied)
    org_id: str
    user_id: str
    # Requirements
    required_model: str  # e.g., "flux-dev", "sdxl-turbo"
    worker_specialty: str = "generation"  # generation, training, video
    min_vram_gb: float = 0.0
    priority: int = 5  # 1 (highest) to 10 (lowest)
    # Lifecycle
    state: FleetJobState = FleetJobState.PENDING
    attempt: int = 0
    max_attempts: int = 3
    # Lease (atomic claim)
    leased_by_worker_id: str | None = None
    lease_granted_at: str | None = None
    lease_expires_at: str | None = None
    last_heartbeat: str | None = None
    # Cost
    cost_reservation_usd: float = 0.0
    actual_cost_usd: float = 0.0
    # Result
    output_asset_id: str | None = None
    error: str = ""
    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None

    def to_status(self) -> dict:
        return {
            "id": self.id,
            "generation_job_id": self.generation_job_id,
            "state": self.state.value,
            "required_model": self.required_model,
            "priority": self.priority,
            "attempt": self.attempt,
            "leased_by_worker_id": self.leased_by_worker_id,
            "cost_reservation_usd": self.cost_reservation_usd,
            "actual_cost_usd": self.actual_cost_usd,
            "output_asset_id": self.output_asset_id,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "is_terminal": self.state.is_terminal,
        }


# =============================================================================
# Fleet Queue Store (in-memory, production: Supabase/Redis)
# =============================================================================

_fleet_store: dict[str, FleetJob] = {}
_store_lock = threading.Lock()


def _make_fleet_id() -> str:
    return f"fleet-{secrets.token_hex(8)}"


# =============================================================================
# Fleet Queue Service
# =============================================================================


class FleetQueueService:
    """Durable fleet queue with atomic lease claims."""

    @staticmethod
    def enqueue(
        *,
        generation_job_id: str,
        org_id: str,
        user_id: str,
        required_model: str,
        worker_specialty: str = "generation",
        min_vram_gb: float = 0.0,
        priority: int = 5,
        cost_reservation_usd: float = 0.0,
    ) -> FleetJob:
        """Enqueue a fleet job (persisted before any assignment)."""
        if not org_id:
            raise ValueError("org_id required")
        if not generation_job_id:
            raise ValueError("generation_job_id required")

        job = FleetJob(
            id=_make_fleet_id(),
            generation_job_id=generation_job_id,
            org_id=org_id,
            user_id=user_id,
            required_model=required_model,
            worker_specialty=worker_specialty,
            min_vram_gb=min_vram_gb,
            priority=priority,
            cost_reservation_usd=cost_reservation_usd,
        )

        with _store_lock:
            _fleet_store[job.id] = job

        return job

    @staticmethod
    def atomic_claim(
        worker_id: str,
        *,
        supported_models: list[str] | None = None,
        specialty: str = "generation",
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> FleetJob | None:
        """Atomically claim the highest-priority pending job.

        Only ONE worker can claim each job. The claim is a time-limited lease —
        worker must heartbeat or the lease expires and job becomes reclaimable.

        Args:
            worker_id: Claiming worker's identifier
            supported_models: Models this worker can handle (None = any)
            specialty: Worker type filter
            lease_seconds: How long the lease is valid without heartbeat

        Returns:
            The claimed FleetJob, or None if no matching jobs available.
        """
        now = datetime.now(UTC)
        lease_expiry = (now + timedelta(seconds=lease_seconds)).isoformat()

        with _store_lock:
            # Find highest-priority pending job matching worker capabilities
            candidates = [
                job for job in _fleet_store.values()
                if job.state.is_claimable
                and job.worker_specialty == specialty
                and (supported_models is None or job.required_model in supported_models)
            ]

            if not candidates:
                return None

            # Sort by priority (lower number = higher priority), then by creation time
            candidates.sort(key=lambda j: (j.priority, j.created_at))
            job = candidates[0]

            # Atomic claim — within the lock, no other worker can claim this
            job.state = FleetJobState.LEASED
            job.leased_by_worker_id = worker_id
            job.lease_granted_at = now.isoformat()
            job.lease_expires_at = lease_expiry
            job.last_heartbeat = now.isoformat()
            job.attempt += 1

        return job

    @staticmethod
    def start_execution(job_id: str, worker_id: str) -> bool:
        """Mark a leased job as executing (worker is calling provider)."""
        with _store_lock:
            job = _fleet_store.get(job_id)
            if not job:
                return False
            if job.state != FleetJobState.LEASED:
                return False
            if job.leased_by_worker_id != worker_id:
                return False  # Wrong worker

            job.state = FleetJobState.EXECUTING
            job.started_at = datetime.now(UTC).isoformat()
            job.last_heartbeat = datetime.now(UTC).isoformat()
        return True

    @staticmethod
    def heartbeat(job_id: str, worker_id: str) -> bool:
        """Refresh the lease heartbeat (proves worker is alive)."""
        with _store_lock:
            job = _fleet_store.get(job_id)
            if not job:
                return False
            if job.leased_by_worker_id != worker_id:
                return False
            if job.state not in (FleetJobState.LEASED, FleetJobState.EXECUTING):
                return False

            job.last_heartbeat = datetime.now(UTC).isoformat()
            # Extend lease
            job.lease_expires_at = (
                datetime.now(UTC) + timedelta(seconds=DEFAULT_LEASE_SECONDS)
            ).isoformat()
        return True

    @staticmethod
    def complete(
        job_id: str,
        worker_id: str,
        *,
        output_asset_id: str = "",
        actual_cost_usd: float = 0.0,
    ) -> bool:
        """Mark job as completed with output."""
        with _store_lock:
            job = _fleet_store.get(job_id)
            if not job:
                return False
            if job.leased_by_worker_id != worker_id:
                return False
            if job.state not in (FleetJobState.LEASED, FleetJobState.EXECUTING):
                return False

            job.state = FleetJobState.COMPLETED
            job.output_asset_id = output_asset_id
            job.actual_cost_usd = actual_cost_usd
            job.completed_at = datetime.now(UTC).isoformat()
        return True

    @staticmethod
    def fail(job_id: str, worker_id: str, error: str) -> bool:
        """Mark job as failed (retryable if attempts remain)."""
        with _store_lock:
            job = _fleet_store.get(job_id)
            if not job:
                return False
            if job.leased_by_worker_id != worker_id:
                return False

            job.state = FleetJobState.FAILED
            job.error = error[:500]
            job.completed_at = datetime.now(UTC).isoformat()
            # Release lease so it can be retried
            job.leased_by_worker_id = None
            job.lease_expires_at = None
        return True

    @staticmethod
    def cancel(job_id: str, org_id: str) -> FleetJob | None:
        """Cancel a fleet job (tenant-scoped, idempotent)."""
        with _store_lock:
            job = _fleet_store.get(job_id)
            if not job or job.org_id != org_id:
                return None
            if job.state == FleetJobState.CANCELLED:
                return job  # Idempotent
            if job.state.is_terminal:
                return job  # Can't cancel completed

            job.state = FleetJobState.CANCELLED
            job.completed_at = datetime.now(UTC).isoformat()
        return job

    @staticmethod
    def retry(job_id: str, org_id: str) -> FleetJob | None:
        """Re-enqueue a failed/expired job for retry (tenant-scoped)."""
        with _store_lock:
            job = _fleet_store.get(job_id)
            if not job or job.org_id != org_id:
                return None
            if not job.state.is_retryable:
                return job
            if job.attempt >= job.max_attempts:
                return job  # Exhausted

            job.state = FleetJobState.PENDING
            job.leased_by_worker_id = None
            job.lease_granted_at = None
            job.lease_expires_at = None
            job.last_heartbeat = None
            job.started_at = None
            job.completed_at = None
            job.error = ""
        return job

    @staticmethod
    def check_expired_leases() -> list[str]:
        """Find jobs with expired leases (worker died). Returns expired job IDs."""
        now = datetime.now(UTC)
        expired = []

        with _store_lock:
            for job in _fleet_store.values():
                if job.state not in (FleetJobState.LEASED, FleetJobState.EXECUTING):
                    continue
                if not job.lease_expires_at:
                    continue
                try:
                    expiry = datetime.fromisoformat(job.lease_expires_at)
                    if now > expiry:
                        job.state = FleetJobState.LEASE_EXPIRED
                        job.error = "Worker lease expired (no heartbeat)"
                        job.leased_by_worker_id = None
                        expired.append(job.id)
                except (ValueError, TypeError):
                    pass

        return expired

    @staticmethod
    def get_status(job_id: str, org_id: str) -> dict | None:
        """Get fleet job status (tenant-scoped)."""
        job = _fleet_store.get(job_id)
        if not job or job.org_id != org_id:
            return None
        return job.to_status()

    @staticmethod
    def get_pending_count(specialty: str = "generation") -> int:
        """Count pending jobs (for orchestrator scaling decisions)."""
        return sum(
            1 for j in _fleet_store.values()
            if j.state == FleetJobState.PENDING and j.worker_specialty == specialty
        )
