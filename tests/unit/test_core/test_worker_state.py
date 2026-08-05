"""Durable GPU worker state tests — Story 056.

Tests prove:
  - Lifecycle transitions are validated (invalid rejected)
  - Orchestrator lease required for all mutations
  - Wrong lease token rejected (split-brain prevention)
  - Stale lease allows recovery by new orchestrator
  - Duplicate worker prevention for same instance
  - Reconciliation marks missing instances as orphaned
  - Reconciliation re-acquires stale leases
  - Worker heartbeat tracks instance liveness
  - Job assignment/release transitions correctly
  - Terminal states cannot transition further
"""

import time
import threading

import pytest

from backend.infrastructure.worker_state import (
    ORCHESTRATOR_LEASE_DURATION,
    DuplicateWorkerError,
    DurableWorkerRecord,
    InvalidTransitionError,
    OrchLeaseRequired,
    WorkerLifecycle,
    WorkerStateError,
    _reset_store,
    acquire_orphaned_lease,
    assign_job,
    create_worker,
    get_worker,
    list_workers_for_org,
    orchestrator_heartbeat,
    reconcile_workers,
    release_job,
    transition_lifecycle,
    worker_heartbeat,
)

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORCH_1 = "orchestrator-1"
ORCH_2 = "orchestrator-2"


@pytest.fixture(autouse=True)
def clean_store():
    _reset_store()
    yield
    _reset_store()


# =============================================================================
# Worker Creation
# =============================================================================


@pytest.mark.unit
class TestWorkerCreation:

    def test_create_returns_record_with_lease(self):
        w = create_worker(TENANT_A, "vast", ORCH_1, provider_instance_id="i-123")
        assert w.org_id == TENANT_A
        assert w.provider == "vast"
        assert w.lifecycle == WorkerLifecycle.PROVISIONING
        assert w.orchestrator_lease_token is not None
        assert w.is_orchestrator_lease_active is True

    def test_requires_org_id(self):
        with pytest.raises(ValueError, match="org_id"):
            create_worker("", "vast", ORCH_1)

    def test_requires_orchestrator_id(self):
        with pytest.raises(ValueError, match="orchestrator_id"):
            create_worker(TENANT_A, "vast", "")

    def test_duplicate_instance_rejected(self):
        create_worker(TENANT_A, "vast", ORCH_1, provider_instance_id="i-123")
        with pytest.raises(DuplicateWorkerError):
            create_worker(TENANT_A, "vast", ORCH_1, provider_instance_id="i-123")

    def test_terminated_instance_allows_recreation(self):
        w = create_worker(TENANT_A, "vast", ORCH_1, provider_instance_id="i-old")
        transition_lifecycle(w.worker_id, WorkerLifecycle.ERROR, w.orchestrator_lease_token)
        # Now can create with same instance (old is terminal)
        w2 = create_worker(TENANT_A, "vast", ORCH_1, provider_instance_id="i-old")
        assert w2.worker_id != w.worker_id


# =============================================================================
# Lifecycle Transitions
# =============================================================================


@pytest.mark.unit
class TestLifecycleTransitions:

    def test_valid_transition_succeeds(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        result = transition_lifecycle(w.worker_id, WorkerLifecycle.BOOTING, w.orchestrator_lease_token)
        assert result.lifecycle == WorkerLifecycle.BOOTING
        assert result.previous_lifecycle == WorkerLifecycle.PROVISIONING

    def test_invalid_transition_rejected(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        with pytest.raises(InvalidTransitionError):
            transition_lifecycle(w.worker_id, WorkerLifecycle.BUSY, w.orchestrator_lease_token)

    def test_terminal_cannot_transition(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        transition_lifecycle(w.worker_id, WorkerLifecycle.ERROR, w.orchestrator_lease_token, "crash")
        with pytest.raises(InvalidTransitionError):
            transition_lifecycle(w.worker_id, WorkerLifecycle.READY, w.orchestrator_lease_token)

    def test_full_lifecycle_path(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        token = w.orchestrator_lease_token
        transition_lifecycle(w.worker_id, WorkerLifecycle.BOOTING, token)
        transition_lifecycle(w.worker_id, WorkerLifecycle.INSTALLING, token)
        transition_lifecycle(w.worker_id, WorkerLifecycle.READY, token)
        assert w.lifecycle == WorkerLifecycle.READY
        assert w.worker_ready_at is not None


# =============================================================================
# Orchestrator Lease (Split-Brain Prevention)
# =============================================================================


@pytest.mark.unit
class TestOrchestratorLease:

    def test_wrong_token_rejected(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        with pytest.raises(OrchLeaseRequired, match="mismatch"):
            transition_lifecycle(w.worker_id, WorkerLifecycle.BOOTING, "wrong-token")

    def test_expired_lease_rejected(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        w.orchestrator_lease_expiry = time.time() - 10
        with pytest.raises(OrchLeaseRequired, match="expired"):
            transition_lifecycle(w.worker_id, WorkerLifecycle.BOOTING, w.orchestrator_lease_token)

    def test_heartbeat_extends_lease(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        old_expiry = w.orchestrator_lease_expiry
        time.sleep(0.01)
        orchestrator_heartbeat(w.worker_id, w.orchestrator_lease_token)
        assert w.orchestrator_lease_expiry > old_expiry

    def test_stale_lease_detectable(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        w.orchestrator_heartbeat = time.time() - 200  # Way past threshold
        assert w.is_orchestrator_lease_stale is True


# =============================================================================
# Lease Recovery (New Orchestrator After Crash)
# =============================================================================


@pytest.mark.unit
class TestLeaseRecovery:

    def test_acquire_stale_lease(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        old_token = w.orchestrator_lease_token
        # Simulate orchestrator crash (stale heartbeat + expired)
        w.orchestrator_heartbeat = time.time() - 200
        w.orchestrator_lease_expiry = time.time() - 100

        result = acquire_orphaned_lease(w.worker_id, ORCH_2)
        assert result is not None
        assert result.orchestrator_id == ORCH_2
        assert result.orchestrator_lease_token != old_token

    def test_cannot_acquire_active_lease(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        # Lease is fresh — cannot steal
        result = acquire_orphaned_lease(w.worker_id, ORCH_2)
        assert result is None

    def test_cannot_acquire_terminal_worker(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        transition_lifecycle(w.worker_id, WorkerLifecycle.ERROR, w.orchestrator_lease_token)
        w.orchestrator_heartbeat = time.time() - 200
        w.orchestrator_lease_expiry = time.time() - 100
        result = acquire_orphaned_lease(w.worker_id, ORCH_2)
        assert result is None


# =============================================================================
# Reconciliation
# =============================================================================


@pytest.mark.unit
class TestReconciliation:

    def test_missing_instance_marked_orphaned(self):
        w = create_worker(TENANT_A, "vast", ORCH_1, provider_instance_id="i-gone")
        transition_lifecycle(w.worker_id, WorkerLifecycle.BOOTING, w.orchestrator_lease_token)
        # Provider reports NO instances
        actions = reconcile_workers(TENANT_A, ORCH_1, [])
        assert actions[w.worker_id] == "marked_orphaned"
        assert w.lifecycle == WorkerLifecycle.ORPHANED

    def test_existing_instance_synced(self):
        w = create_worker(TENANT_A, "vast", ORCH_1, provider_instance_id="i-live")
        transition_lifecycle(w.worker_id, WorkerLifecycle.BOOTING, w.orchestrator_lease_token)
        actions = reconcile_workers(TENANT_A, ORCH_1, [{"id": "i-live", "status": "running"}])
        assert actions[w.worker_id] == "already_synced"
        assert w.reconciliation_status == "synced"

    def test_stale_lease_reacquired_on_reconcile(self):
        w = create_worker(TENANT_A, "vast", ORCH_1, provider_instance_id="i-live")
        transition_lifecycle(w.worker_id, WorkerLifecycle.BOOTING, w.orchestrator_lease_token)
        # Simulate crash
        w.orchestrator_heartbeat = time.time() - 200
        w.orchestrator_lease_expiry = time.time() - 100
        actions = reconcile_workers(TENANT_A, ORCH_2, [{"id": "i-live", "status": "running"}])
        assert actions[w.worker_id] == "lease_reacquired"
        assert w.orchestrator_id == ORCH_2


# =============================================================================
# Job Assignment
# =============================================================================


@pytest.mark.unit
class TestJobAssignment:

    def test_assign_job_transitions_to_busy(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        token = w.orchestrator_lease_token
        transition_lifecycle(w.worker_id, WorkerLifecycle.BOOTING, token)
        transition_lifecycle(w.worker_id, WorkerLifecycle.READY, token)
        assign_job(w.worker_id, token, "job-1", "jlease-1")
        assert w.lifecycle == WorkerLifecycle.BUSY
        assert w.active_job_id == "job-1"

    def test_release_job_transitions_to_ready(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        token = w.orchestrator_lease_token
        transition_lifecycle(w.worker_id, WorkerLifecycle.BOOTING, token)
        transition_lifecycle(w.worker_id, WorkerLifecycle.READY, token)
        assign_job(w.worker_id, token, "job-1", "jlease-1")
        release_job(w.worker_id, token)
        assert w.lifecycle == WorkerLifecycle.READY
        assert w.active_job_id is None

    def test_cannot_assign_to_non_ready_worker(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        with pytest.raises(WorkerStateError, match="not ready"):
            assign_job(w.worker_id, w.orchestrator_lease_token, "job-1", "jlease-1")


# =============================================================================
# Worker Heartbeat
# =============================================================================


@pytest.mark.unit
class TestWorkerHeartbeat:

    def test_heartbeat_updates_timestamp(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        token = w.orchestrator_lease_token
        worker_heartbeat(w.worker_id, token, models_loaded=["flux-dev"])
        assert w.worker_heartbeat > 0
        assert "flux-dev" in w.models_loaded

    def test_stale_worker_heartbeat_detected(self):
        w = create_worker(TENANT_A, "vast", ORCH_1)
        token = w.orchestrator_lease_token
        transition_lifecycle(w.worker_id, WorkerLifecycle.BOOTING, token)
        transition_lifecycle(w.worker_id, WorkerLifecycle.READY, token)
        w.worker_heartbeat = time.time() - 200
        assert w.is_worker_heartbeat_stale is True
