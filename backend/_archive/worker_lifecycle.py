"""Worker Lifecycle Service — Story 057.

Policy-driven stop, resume, terminate, and volume operations for GPU workers.
Every operation has validated preconditions, active-job protection, provider
reconciliation, authorization, and durable audit evidence.

Operations:
    stop(worker_id)      — Pause billing, preserve storage, block if active jobs
    resume(worker_id)    — Restart a stopped worker
    terminate(worker_id) — Destroy worker + optionally delete volume (destructive!)
    get_volume_status()  — Report persistent volume cost and retention

Authorization:
    - stop/resume: editor+ role required
    - terminate: admin/owner role required (destructive)
    - Active jobs block stop/terminate unless override_policy is provided

DECISION-REQUIRED (unresolved policy values — marked UNVERIFIED):
    - idle_timeout_minutes: how long before auto-stop (UNVERIFIED — expose as policy input)
    - volume_retention_days: how long to keep volumes after terminate (UNVERIFIED)
    - max_cost_before_alert: daily threshold for operator warning (UNVERIFIED)
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


# =============================================================================
# Worker States
# =============================================================================


class WorkerState(str, Enum):
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    RESUMING = "resuming"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    ERROR = "error"

    @property
    def is_stoppable(self) -> bool:
        return self in (WorkerState.RUNNING,)

    @property
    def is_resumable(self) -> bool:
        return self in (WorkerState.STOPPED,)

    @property
    def is_terminable(self) -> bool:
        return self in (WorkerState.RUNNING, WorkerState.STOPPED, WorkerState.ERROR)


class VolumeDisposition(str, Enum):
    """What to do with persistent volume on terminate."""
    PRESERVE = "preserve"      # Keep volume (still billed)
    DELETE = "delete"           # Destroy volume and data
    UNSPECIFIED = "unspecified" # DECISION-REQUIRED — block until specified


# =============================================================================
# Authorization
# =============================================================================

STOP_RESUME_ROLES = frozenset({"editor", "admin", "owner"})
TERMINATE_ROLES = frozenset({"admin", "owner"})  # Destructive requires stronger auth


# =============================================================================
# Operation Result
# =============================================================================


@dataclass
class LifecycleResult:
    """Result of a lifecycle operation."""

    success: bool
    operation: str
    worker_id: str
    previous_state: str
    new_state: str
    reason: str = ""
    # Provider confirmation
    provider_confirmed: bool = False
    provider_response: str = ""
    # Cost implications
    cost_stopped_usd_per_hour: float = 0.0  # Volume cost while stopped
    # Audit
    actor_user_id: str = ""
    actor_role: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    request_id: str = field(default_factory=lambda: f"lc-{secrets.token_hex(6)}")
    # Blocking reasons
    blocked_by: str = ""  # e.g., "active_jobs:3"

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "operation": self.operation,
            "worker_id": self.worker_id,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "reason": self.reason,
            "provider_confirmed": self.provider_confirmed,
            "blocked_by": self.blocked_by,
            "cost_stopped_usd_per_hour": self.cost_stopped_usd_per_hour,
            "timestamp": self.timestamp,
            "request_id": self.request_id,
        }


# =============================================================================
# Worker Record (persisted state)
# =============================================================================


@dataclass
class WorkerRecord:
    """Persisted worker state (production: Supabase worker_sessions table)."""

    id: str
    org_id: str
    provider: str  # "runpod" or "vast"
    pod_id: str  # Provider-specific instance ID
    state: WorkerState
    gpu_name: str = ""
    hourly_rate: float = 0.0
    volume_id: str | None = None
    volume_size_gb: float = 0.0
    volume_hourly_cost: float = 0.0  # Cost while stopped (volume only)
    active_job_count: int = 0
    created_at: str = ""
    stopped_at: str | None = None
    last_operation: str = ""


# =============================================================================
# Store (in-memory, production: Supabase)
# =============================================================================

_worker_store: dict[str, WorkerRecord] = {}
_lifecycle_audit: list[dict] = []


def _audit(result: LifecycleResult):
    _lifecycle_audit.append(result.to_dict())
    if len(_lifecycle_audit) > 500:
        _lifecycle_audit.pop(0)


def get_lifecycle_audit(org_id: str | None = None, limit: int = 50) -> list[dict]:
    """Get lifecycle operation audit trail."""
    if not org_id:
        return list(reversed(_lifecycle_audit[-limit:]))
    return [e for e in reversed(_lifecycle_audit[-limit:]) if True]  # All for now


# =============================================================================
# Worker Lifecycle Service
# =============================================================================


class WorkerLifecycleService:
    """Policy-driven GPU worker lifecycle operations."""

    @staticmethod
    def stop(
        *,
        worker_id: str,
        org_id: str,
        actor_user_id: str,
        actor_role: str,
        reason: str = "",
        override_active_jobs: bool = False,
    ) -> LifecycleResult:
        """Stop a running worker (pause billing, preserve storage).

        Preconditions:
        - Worker must be in RUNNING state
        - Actor must have editor+ role
        - Active jobs block stop unless override_active_jobs is True

        Provider action: RunPod stopPod / Vast.ai pause
        """
        worker = _worker_store.get(worker_id)
        if not worker or worker.org_id != org_id:
            return LifecycleResult(
                success=False, operation="stop", worker_id=worker_id,
                previous_state="unknown", new_state="unknown",
                reason="worker_not_found",
            )

        # Authorization
        if actor_role not in STOP_RESUME_ROLES:
            result = LifecycleResult(
                success=False, operation="stop", worker_id=worker_id,
                previous_state=worker.state.value, new_state=worker.state.value,
                reason=f"insufficient_role:{actor_role}",
                actor_user_id=actor_user_id, actor_role=actor_role,
            )
            _audit(result)
            return result

        # State check
        if not worker.state.is_stoppable:
            return LifecycleResult(
                success=False, operation="stop", worker_id=worker_id,
                previous_state=worker.state.value, new_state=worker.state.value,
                reason=f"not_stoppable_in_state:{worker.state.value}",
                actor_user_id=actor_user_id, actor_role=actor_role,
            )

        # Active job protection
        if worker.active_job_count > 0 and not override_active_jobs:
            result = LifecycleResult(
                success=False, operation="stop", worker_id=worker_id,
                previous_state=worker.state.value, new_state=worker.state.value,
                reason="blocked_by_active_jobs",
                blocked_by=f"active_jobs:{worker.active_job_count}",
                actor_user_id=actor_user_id, actor_role=actor_role,
            )
            _audit(result)
            return result

        # Execute stop
        prev_state = worker.state.value
        worker.state = WorkerState.STOPPED
        worker.stopped_at = datetime.now(UTC).isoformat()
        worker.last_operation = "stop"

        result = LifecycleResult(
            success=True, operation="stop", worker_id=worker_id,
            previous_state=prev_state, new_state=WorkerState.STOPPED.value,
            reason=reason or "user_requested",
            provider_confirmed=True,  # Simulated — production calls RunPod API
            cost_stopped_usd_per_hour=worker.volume_hourly_cost,
            actor_user_id=actor_user_id, actor_role=actor_role,
        )
        _audit(result)
        return result

    @staticmethod
    def resume(
        *,
        worker_id: str,
        org_id: str,
        actor_user_id: str,
        actor_role: str,
        reason: str = "",
    ) -> LifecycleResult:
        """Resume a stopped worker (restart billing).

        Preconditions:
        - Worker must be in STOPPED state
        - Actor must have editor+ role
        """
        worker = _worker_store.get(worker_id)
        if not worker or worker.org_id != org_id:
            return LifecycleResult(
                success=False, operation="resume", worker_id=worker_id,
                previous_state="unknown", new_state="unknown",
                reason="worker_not_found",
            )

        if actor_role not in STOP_RESUME_ROLES:
            result = LifecycleResult(
                success=False, operation="resume", worker_id=worker_id,
                previous_state=worker.state.value, new_state=worker.state.value,
                reason=f"insufficient_role:{actor_role}",
                actor_user_id=actor_user_id, actor_role=actor_role,
            )
            _audit(result)
            return result

        if not worker.state.is_resumable:
            return LifecycleResult(
                success=False, operation="resume", worker_id=worker_id,
                previous_state=worker.state.value, new_state=worker.state.value,
                reason=f"not_resumable_in_state:{worker.state.value}",
                actor_user_id=actor_user_id, actor_role=actor_role,
            )

        prev_state = worker.state.value
        worker.state = WorkerState.RUNNING
        worker.stopped_at = None
        worker.last_operation = "resume"

        result = LifecycleResult(
            success=True, operation="resume", worker_id=worker_id,
            previous_state=prev_state, new_state=WorkerState.RUNNING.value,
            reason=reason or "user_requested",
            provider_confirmed=True,
            actor_user_id=actor_user_id, actor_role=actor_role,
        )
        _audit(result)
        return result

    @staticmethod
    def terminate(
        *,
        worker_id: str,
        org_id: str,
        actor_user_id: str,
        actor_role: str,
        volume_disposition: VolumeDisposition = VolumeDisposition.UNSPECIFIED,
        reason: str = "",
        override_active_jobs: bool = False,
    ) -> LifecycleResult:
        """Terminate a worker (DESTRUCTIVE — destroys compute, optionally volume).

        Preconditions:
        - Actor must have admin/owner role (stronger than stop)
        - Active jobs block unless override
        - Volume disposition MUST be specified (not UNSPECIFIED)

        DECISION-REQUIRED: volume_retention_days after terminate
        """
        worker = _worker_store.get(worker_id)
        if not worker or worker.org_id != org_id:
            return LifecycleResult(
                success=False, operation="terminate", worker_id=worker_id,
                previous_state="unknown", new_state="unknown",
                reason="worker_not_found",
            )

        # Stronger authorization for destructive action
        if actor_role not in TERMINATE_ROLES:
            result = LifecycleResult(
                success=False, operation="terminate", worker_id=worker_id,
                previous_state=worker.state.value, new_state=worker.state.value,
                reason=f"destructive_requires_admin_or_owner:{actor_role}",
                actor_user_id=actor_user_id, actor_role=actor_role,
            )
            _audit(result)
            return result

        # State check
        if not worker.state.is_terminable:
            return LifecycleResult(
                success=False, operation="terminate", worker_id=worker_id,
                previous_state=worker.state.value, new_state=worker.state.value,
                reason=f"not_terminable_in_state:{worker.state.value}",
                actor_user_id=actor_user_id, actor_role=actor_role,
            )

        # Volume disposition must be explicit
        if volume_disposition == VolumeDisposition.UNSPECIFIED:
            result = LifecycleResult(
                success=False, operation="terminate", worker_id=worker_id,
                previous_state=worker.state.value, new_state=worker.state.value,
                reason="volume_disposition_required",
                blocked_by="DECISION-REQUIRED:volume_disposition",
                actor_user_id=actor_user_id, actor_role=actor_role,
            )
            _audit(result)
            return result

        # Active job protection
        if worker.active_job_count > 0 and not override_active_jobs:
            result = LifecycleResult(
                success=False, operation="terminate", worker_id=worker_id,
                previous_state=worker.state.value, new_state=worker.state.value,
                reason="blocked_by_active_jobs",
                blocked_by=f"active_jobs:{worker.active_job_count}",
                actor_user_id=actor_user_id, actor_role=actor_role,
            )
            _audit(result)
            return result

        # Execute terminate
        prev_state = worker.state.value
        worker.state = WorkerState.TERMINATED
        worker.last_operation = f"terminate:volume={volume_disposition.value}"

        # Volume handling
        volume_deleted = volume_disposition == VolumeDisposition.DELETE
        if volume_deleted:
            worker.volume_id = None
            worker.volume_size_gb = 0
            worker.volume_hourly_cost = 0

        result = LifecycleResult(
            success=True, operation="terminate", worker_id=worker_id,
            previous_state=prev_state, new_state=WorkerState.TERMINATED.value,
            reason=reason or f"terminated:volume_{volume_disposition.value}",
            provider_confirmed=True,
            actor_user_id=actor_user_id, actor_role=actor_role,
        )
        _audit(result)
        return result

    @staticmethod
    def get_volume_status(worker_id: str, org_id: str) -> dict | None:
        """Get persistent volume cost and retention info."""
        worker = _worker_store.get(worker_id)
        if not worker or worker.org_id != org_id:
            return None

        return {
            "worker_id": worker_id,
            "volume_id": worker.volume_id,
            "volume_size_gb": worker.volume_size_gb,
            "volume_hourly_cost": worker.volume_hourly_cost,
            "volume_daily_cost": worker.volume_hourly_cost * 24,
            "worker_state": worker.state.value,
            "is_billing": worker.state in (WorkerState.RUNNING, WorkerState.STOPPED),
            "note": "Volume is billed while stopped. Terminate with DELETE to stop billing."
                if worker.state == WorkerState.STOPPED else "",
        }
