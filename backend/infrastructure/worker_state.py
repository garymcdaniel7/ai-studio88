"""Durable GPU Worker State — Story 056.

Persisted lifecycle model for GPU workers with leases, heartbeats,
reconciliation, and split-brain prevention.

Replaces process-local WorkerSession/WorkerOrchestrator as source of truth.
After a restart, the orchestrator reconciles database state with provider reality.

Lifecycle:
    provisioning → booting → installing → ready → busy → idle → stopping → terminated
                                                              → error
                                                              → orphaned (lost contact)

Lease model:
    - Each worker has an orchestrator_lease (who controls it)
    - Only the lease holder can transition state
    - Stale leases (no heartbeat) allow recovery by another orchestrator
    - Prevents duplicate orchestrators from controlling the same worker

Reconciliation:
    On startup, the orchestrator:
    1. Loads all workers with active leases for this workspace
    2. Queries provider API for actual instance state
    3. Reconciles: marks missing instances as orphaned, reconnects live ones
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Lease/heartbeat defaults
ORCHESTRATOR_LEASE_DURATION = 120  # 2 minutes
ORCHESTRATOR_HEARTBEAT_INTERVAL = 30  # seconds
STALE_THRESHOLD_FACTOR = 3  # 3x interval = stale


# =============================================================================
# Worker Lifecycle States
# =============================================================================


class WorkerLifecycle(str, Enum):
    PROVISIONING = "provisioning"  # Provider API called, waiting for instance
    BOOTING = "booting"            # Instance exists, waiting for SSH/connectivity
    INSTALLING = "installing"      # Software being installed (ComfyUI, models)
    READY = "ready"                # Fully operational, accepting jobs
    BUSY = "busy"                  # Executing a job
    IDLE = "idle"                  # No active job, may be shut down
    STOPPING = "stopping"         # Graceful shutdown in progress
    TERMINATED = "terminated"      # Instance destroyed (terminal)
    ERROR = "error"                # Unrecoverable error (terminal)
    ORPHANED = "orphaned"          # Lost contact, needs reconciliation


TERMINAL_STATES = frozenset({WorkerLifecycle.TERMINATED, WorkerLifecycle.ERROR})

# Valid transitions
VALID_TRANSITIONS: dict[WorkerLifecycle, frozenset[WorkerLifecycle]] = {
    WorkerLifecycle.PROVISIONING: frozenset({WorkerLifecycle.BOOTING, WorkerLifecycle.ERROR, WorkerLifecycle.TERMINATED}),
    WorkerLifecycle.BOOTING: frozenset({WorkerLifecycle.INSTALLING, WorkerLifecycle.READY, WorkerLifecycle.ERROR, WorkerLifecycle.TERMINATED}),
    WorkerLifecycle.INSTALLING: frozenset({WorkerLifecycle.READY, WorkerLifecycle.ERROR, WorkerLifecycle.TERMINATED}),
    WorkerLifecycle.READY: frozenset({WorkerLifecycle.BUSY, WorkerLifecycle.IDLE, WorkerLifecycle.STOPPING, WorkerLifecycle.ERROR, WorkerLifecycle.ORPHANED}),
    WorkerLifecycle.BUSY: frozenset({WorkerLifecycle.READY, WorkerLifecycle.IDLE, WorkerLifecycle.STOPPING, WorkerLifecycle.ERROR, WorkerLifecycle.ORPHANED}),
    WorkerLifecycle.IDLE: frozenset({WorkerLifecycle.BUSY, WorkerLifecycle.READY, WorkerLifecycle.STOPPING, WorkerLifecycle.ERROR, WorkerLifecycle.ORPHANED}),
    WorkerLifecycle.STOPPING: frozenset({WorkerLifecycle.TERMINATED, WorkerLifecycle.ERROR}),
    WorkerLifecycle.ERROR: frozenset(),  # Terminal
    WorkerLifecycle.TERMINATED: frozenset(),  # Terminal
    WorkerLifecycle.ORPHANED: frozenset({WorkerLifecycle.READY, WorkerLifecycle.ERROR, WorkerLifecycle.TERMINATED}),  # Recoverable
}


# =============================================================================
# Durable Worker Record
# =============================================================================


@dataclass
class DurableWorkerRecord:
    """Persisted GPU worker state — source of truth (not process memory)."""
    # Identity
    worker_id: str = field(default_factory=lambda: f"gw-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    provider: str = ""  # vast | runpod
    provider_instance_id: str | None = None  # Provider's instance/pod ID

    # Lifecycle
    lifecycle: WorkerLifecycle = WorkerLifecycle.PROVISIONING
    previous_lifecycle: WorkerLifecycle | None = None

    # Provider details
    gpu_name: str = ""
    gpu_vram_mb: int = 0
    ssh_host: str | None = None
    ssh_port: int | None = None
    hourly_rate: float = 0.0

    # Orchestrator lease (who controls this worker)
    orchestrator_id: str | None = None
    orchestrator_lease_token: str | None = None
    orchestrator_lease_expiry: float = 0.0
    orchestrator_heartbeat: float = 0.0

    # Worker heartbeat (is the instance alive)
    worker_heartbeat: float = 0.0
    worker_ready_at: float | None = None

    # Active job tracking
    active_job_id: str | None = None
    active_job_lease_token: str | None = None

    # Readiness
    models_loaded: list[str] = field(default_factory=list)
    comfyui_ready: bool = False
    tunnel_active: bool = False

    # Errors
    last_error: str | None = None
    error_count: int = 0

    # Timing
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Reconciliation
    last_reconciled_at: float | None = None
    reconciliation_status: str = "pending"  # pending | synced | conflict | orphaned

    @property
    def is_terminal(self) -> bool:
        return self.lifecycle in TERMINAL_STATES

    @property
    def is_orchestrator_lease_active(self) -> bool:
        return (
            self.orchestrator_lease_token is not None
            and time.time() < self.orchestrator_lease_expiry
        )

    @property
    def is_orchestrator_lease_stale(self) -> bool:
        if not self.orchestrator_heartbeat:
            return True
        threshold = self.orchestrator_heartbeat + (ORCHESTRATOR_HEARTBEAT_INTERVAL * STALE_THRESHOLD_FACTOR)
        return time.time() > threshold

    @property
    def is_worker_heartbeat_stale(self) -> bool:
        if not self.worker_heartbeat:
            return self.lifecycle in (WorkerLifecycle.READY, WorkerLifecycle.BUSY, WorkerLifecycle.IDLE)
        threshold = self.worker_heartbeat + (ORCHESTRATOR_HEARTBEAT_INTERVAL * STALE_THRESHOLD_FACTOR)
        return time.time() > threshold


# =============================================================================
# Errors
# =============================================================================


class WorkerStateError(Exception):
    """Base error for worker state operations."""
    pass


class InvalidTransitionError(WorkerStateError):
    """Raised when a lifecycle transition is not valid."""
    def __init__(self, current: WorkerLifecycle, target: WorkerLifecycle) -> None:
        super().__init__(f"Invalid transition: {current.value} → {target.value}")


class OrchLeaseRequired(WorkerStateError):
    """Raised when operation requires orchestrator lease but caller doesn't hold it."""
    def __init__(self, worker_id: str, reason: str) -> None:
        super().__init__(f"Orchestrator lease required for {worker_id}: {reason}")


class DuplicateWorkerError(WorkerStateError):
    """Raised when trying to create a worker that already exists for this org+provider."""
    pass


# =============================================================================
# Worker State Store
# =============================================================================

_worker_store: dict[str, DurableWorkerRecord] = {}
_store_lock = threading.Lock()


# =============================================================================
# Lifecycle Operations
# =============================================================================


def create_worker(
    org_id: str,
    provider: str,
    orchestrator_id: str,
    provider_instance_id: str | None = None,
    gpu_name: str = "",
    hourly_rate: float = 0.0,
) -> DurableWorkerRecord:
    """Create a new durable worker record with orchestrator lease."""
    if not org_id:
        raise ValueError("org_id is required")
    if not orchestrator_id:
        raise ValueError("orchestrator_id is required")

    with _store_lock:
        # Check for duplicate active workers (same org + provider instance)
        if provider_instance_id:
            for w in _worker_store.values():
                if (w.org_id == org_id and w.provider_instance_id == provider_instance_id
                        and not w.is_terminal):
                    raise DuplicateWorkerError(
                        f"Worker already exists for instance {provider_instance_id}"
                    )

        record = DurableWorkerRecord(
            org_id=org_id,
            provider=provider,
            provider_instance_id=provider_instance_id,
            gpu_name=gpu_name,
            hourly_rate=hourly_rate,
            orchestrator_id=orchestrator_id,
            orchestrator_lease_token=f"olease-{uuid.uuid4().hex[:12]}",
            orchestrator_lease_expiry=time.time() + ORCHESTRATOR_LEASE_DURATION,
            orchestrator_heartbeat=time.time(),
        )

        _worker_store[record.worker_id] = record
        logger.info(f"WORKER_CREATED: id={record.worker_id} org={org_id[:8]} provider={provider}")
        return record


def transition_lifecycle(
    worker_id: str,
    target: WorkerLifecycle,
    lease_token: str,
    error_message: str | None = None,
) -> DurableWorkerRecord:
    """Transition a worker's lifecycle state.

    Requires orchestrator lease. Validates the transition is legal.
    """
    record = _get_and_verify_lease(worker_id, lease_token)

    # Validate transition
    current = record.lifecycle
    valid_targets = VALID_TRANSITIONS.get(current, frozenset())
    if target not in valid_targets:
        raise InvalidTransitionError(current, target)

    # Apply transition
    record.previous_lifecycle = current
    record.lifecycle = target
    record.updated_at = time.time()

    if error_message:
        record.last_error = error_message
        record.error_count += 1

    if target == WorkerLifecycle.READY and not record.worker_ready_at:
        record.worker_ready_at = time.time()

    logger.info(f"WORKER_TRANSITION: id={worker_id} {current.value}→{target.value}")
    return record


def orchestrator_heartbeat(worker_id: str, lease_token: str) -> DurableWorkerRecord:
    """Orchestrator heartbeat — proves this orchestrator still controls the worker."""
    record = _get_and_verify_lease(worker_id, lease_token)
    record.orchestrator_heartbeat = time.time()
    record.orchestrator_lease_expiry = time.time() + ORCHESTRATOR_LEASE_DURATION
    record.updated_at = time.time()
    return record


def worker_heartbeat(worker_id: str, lease_token: str, models_loaded: list[str] | None = None) -> DurableWorkerRecord:
    """Worker instance heartbeat — proves the GPU instance is alive."""
    record = _get_and_verify_lease(worker_id, lease_token)
    record.worker_heartbeat = time.time()
    record.updated_at = time.time()
    if models_loaded is not None:
        record.models_loaded = models_loaded
    return record


def assign_job(worker_id: str, lease_token: str, job_id: str, job_lease_token: str) -> DurableWorkerRecord:
    """Assign a job to this worker (transition to BUSY)."""
    record = _get_and_verify_lease(worker_id, lease_token)
    if record.lifecycle not in (WorkerLifecycle.READY, WorkerLifecycle.IDLE):
        raise WorkerStateError(f"Worker {worker_id} not ready for jobs (state={record.lifecycle.value})")
    record.active_job_id = job_id
    record.active_job_lease_token = job_lease_token
    record.lifecycle = WorkerLifecycle.BUSY
    record.updated_at = time.time()
    return record


def release_job(worker_id: str, lease_token: str) -> DurableWorkerRecord:
    """Release job from worker (transition back to READY/IDLE)."""
    record = _get_and_verify_lease(worker_id, lease_token)
    record.active_job_id = None
    record.active_job_lease_token = None
    if record.lifecycle == WorkerLifecycle.BUSY:
        record.lifecycle = WorkerLifecycle.READY
    record.updated_at = time.time()
    return record


# =============================================================================
# Orchestrator Lease Recovery (Split-Brain Prevention)
# =============================================================================


def acquire_orphaned_lease(worker_id: str, new_orchestrator_id: str) -> DurableWorkerRecord | None:
    """Acquire the orchestrator lease on a worker whose lease is stale.

    Used during restart recovery when the original orchestrator crashed.
    Only succeeds if the existing lease is stale/expired.
    """
    with _store_lock:
        record = _worker_store.get(worker_id)
        if not record:
            return None

        if record.is_terminal:
            return None

        # Only acquire if lease is stale or expired
        if record.is_orchestrator_lease_active and not record.is_orchestrator_lease_stale:
            return None  # Another orchestrator still holds active lease

        # Acquire new lease
        record.orchestrator_id = new_orchestrator_id
        record.orchestrator_lease_token = f"olease-{uuid.uuid4().hex[:12]}"
        record.orchestrator_lease_expiry = time.time() + ORCHESTRATOR_LEASE_DURATION
        record.orchestrator_heartbeat = time.time()
        record.updated_at = time.time()

        logger.info(f"LEASE_ACQUIRED: worker={worker_id} new_orchestrator={new_orchestrator_id}")
        return record


# =============================================================================
# Reconciliation
# =============================================================================


def reconcile_workers(
    org_id: str,
    orchestrator_id: str,
    provider_instances: list[dict],
) -> dict[str, str]:
    """Reconcile database state with provider reality.

    Called on orchestrator startup/recovery.

    Args:
        org_id: Workspace being reconciled.
        orchestrator_id: This orchestrator's identity.
        provider_instances: List of dicts from provider API with instance state.

    Returns:
        Dict of worker_id → reconciliation_action taken.
    """
    actions: dict[str, str] = {}
    provider_ids = {inst.get("id") for inst in provider_instances}

    for record in list(_worker_store.values()):
        if record.org_id != org_id or record.is_terminal:
            continue

        instance_id = record.provider_instance_id

        if instance_id and instance_id not in provider_ids:
            # Instance missing from provider — mark orphaned
            record.lifecycle = WorkerLifecycle.ORPHANED
            record.reconciliation_status = "orphaned"
            record.updated_at = time.time()
            actions[record.worker_id] = "marked_orphaned"
            logger.warning(f"RECONCILE_ORPHANED: worker={record.worker_id} instance={instance_id}")

        elif instance_id and instance_id in provider_ids:
            # Instance exists — attempt to re-acquire lease
            if record.is_orchestrator_lease_stale or not record.is_orchestrator_lease_active:
                acquired = acquire_orphaned_lease(record.worker_id, orchestrator_id)
                if acquired:
                    acquired.reconciliation_status = "synced"
                    acquired.last_reconciled_at = time.time()
                    actions[record.worker_id] = "lease_reacquired"
                else:
                    actions[record.worker_id] = "lease_held_by_other"
            else:
                record.reconciliation_status = "synced"
                record.last_reconciled_at = time.time()
                actions[record.worker_id] = "already_synced"

    return actions


# =============================================================================
# Queries
# =============================================================================


def get_worker(worker_id: str) -> DurableWorkerRecord | None:
    return _worker_store.get(worker_id)


def list_workers_for_org(org_id: str, include_terminal: bool = False) -> list[DurableWorkerRecord]:
    results = []
    for w in _worker_store.values():
        if w.org_id != org_id:
            continue
        if not include_terminal and w.is_terminal:
            continue
        results.append(w)
    return results


# =============================================================================
# Internal Helpers
# =============================================================================


def _get_and_verify_lease(worker_id: str, lease_token: str) -> DurableWorkerRecord:
    """Get worker and verify orchestrator lease."""
    record = _worker_store.get(worker_id)
    if not record:
        raise OrchLeaseRequired(worker_id, "Worker not found")

    if not record.orchestrator_lease_token:
        raise OrchLeaseRequired(worker_id, "No active lease")

    if record.orchestrator_lease_token != lease_token:
        raise OrchLeaseRequired(worker_id, "Lease token mismatch — another orchestrator may hold the lease")

    if not record.is_orchestrator_lease_active:
        raise OrchLeaseRequired(worker_id, "Lease expired")

    return record


# =============================================================================
# Testing
# =============================================================================


def _reset_store() -> None:
    _worker_store.clear()
