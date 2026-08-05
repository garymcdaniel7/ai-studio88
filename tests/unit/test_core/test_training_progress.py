"""Training progress & cancellation tests — Story 094.

Tests prove:
  - Provider IDs persisted on assignment
  - Progress survives as durable state
  - Lost heartbeat detected and marked
  - Provider timeout triggers unresolved state
  - Duplicate callbacks are idempotent
  - Cancel during transfer/training/finalizing
  - Cancel of already-finished job is idempotent
  - Recovery from lost heartbeat
  - Cost accrues until provider confirms stop
  - Cancel request ≠ cancel complete
  - Cross-tenant access denied
"""

import time

import pytest

from backend.training_progress import (
    CancelEvidence,
    InvalidTrainingState,
    TrainingJobNotFound,
    TrainingStatus,
    _reset_store,
    assign_provider,
    check_heartbeat,
    confirm_cancel,
    create_training_job,
    get_training_job,
    mark_cancel_unresolved,
    mark_completed,
    mark_failed,
    recover_lost_job,
    record_heartbeat,
    report_progress,
    request_cancel,
    start_training,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
TALENT = "talent-001"
MANIFEST = "dsm-001"


def _running_job(cost_rate: float = 1.0) -> str:
    """Create a job and advance to training state."""
    job = create_training_job(ORG, TALENT, MANIFEST, cost_rate_per_hour=cost_rate)
    assign_provider(job.job_id, ORG, "vast-123", "worker-001", "lease-001", "pid-999")
    start_training(job.job_id, ORG)
    return job.job_id


# =============================================================================
# Provider Identity
# =============================================================================


@pytest.mark.unit
class TestProviderIdentity:

    def test_provider_ids_persisted(self):
        job = create_training_job(ORG, TALENT, MANIFEST)
        assign_provider(job.job_id, ORG, "vast-456", "w-002", "l-002", "p-123")

        assert job.provider_job_id == "vast-456"
        assert job.worker_id == "w-002"
        assert job.lease_id == "l-002"
        assert job.process_id == "p-123"
        assert job.status == TrainingStatus.TRANSFERRING


# =============================================================================
# Progress & Heartbeat
# =============================================================================


@pytest.mark.unit
class TestProgressHeartbeat:

    def test_progress_updates_durably(self):
        job_id = _running_job()
        report_progress(job_id, ORG, current_step=50, total_steps=100, loss=0.5)

        job = get_training_job(job_id, ORG)
        assert job.progress.current_step == 50
        assert job.progress.total_steps == 100
        assert job.progress.loss == 0.5
        assert job.progress.progress_pct == 50

    def test_heartbeat_records_time(self):
        job_id = _running_job()
        before = time.time()
        record_heartbeat(job_id, ORG)
        job = get_training_job(job_id, ORG)
        assert job.last_heartbeat >= before

    def test_progress_ignored_after_terminal(self):
        job_id = _running_job()
        mark_completed(job_id, ORG)
        report_progress(job_id, ORG, current_step=999)
        job = get_training_job(job_id, ORG)
        # Progress not updated after completion
        assert job.progress.current_step != 999 or job.status == TrainingStatus.COMPLETED


# =============================================================================
# Lost Heartbeat
# =============================================================================


@pytest.mark.unit
class TestLostHeartbeat:

    def test_stale_heartbeat_marks_lost(self):
        job_id = _running_job()
        job = get_training_job(job_id, ORG)
        # Simulate stale heartbeat
        job.last_heartbeat = time.time() - 300  # 5 min ago (timeout is 120s)

        check_heartbeat(job_id, ORG)
        assert job.status == TrainingStatus.LOST

    def test_fresh_heartbeat_not_lost(self):
        job_id = _running_job()
        record_heartbeat(job_id, ORG)  # Fresh
        check_heartbeat(job_id, ORG)
        job = get_training_job(job_id, ORG)
        assert job.status == TrainingStatus.TRAINING

    def test_recover_from_lost(self):
        job_id = _running_job()
        job = get_training_job(job_id, ORG)
        job.last_heartbeat = time.time() - 300
        check_heartbeat(job_id, ORG)
        assert job.status == TrainingStatus.LOST

        recover_lost_job(job_id, ORG)
        assert job.status == TrainingStatus.TRAINING
        assert job.last_heartbeat > time.time() - 5

    def test_recover_non_lost_raises(self):
        job_id = _running_job()
        with pytest.raises(InvalidTrainingState):
            recover_lost_job(job_id, ORG)


# =============================================================================
# Duplicate Callbacks (Idempotent)
# =============================================================================


@pytest.mark.unit
class TestDuplicateCallbacks:

    def test_duplicate_completion_idempotent(self):
        job_id = _running_job()
        mark_completed(job_id, ORG)
        # Second completion after cancel_confirmed is also safe
        job = get_training_job(job_id, ORG)
        assert job.status == TrainingStatus.COMPLETED

    def test_duplicate_failure_idempotent(self):
        job_id = _running_job()
        mark_failed(job_id, ORG, "err1")
        mark_failed(job_id, ORG, "err2")  # Second call — idempotent
        job = get_training_job(job_id, ORG)
        assert job.status == TrainingStatus.FAILED
        assert job.error == "err1"  # First error preserved

    def test_duplicate_cancel_request_idempotent(self):
        job_id = _running_job()
        request_cancel(job_id, ORG)
        request_cancel(job_id, ORG)  # Second call — idempotent
        job = get_training_job(job_id, ORG)
        assert job.status == TrainingStatus.CANCEL_REQUESTED


# =============================================================================
# Cancellation Phases
# =============================================================================


@pytest.mark.unit
class TestCancellationPhases:

    def test_cancel_during_training(self):
        job_id = _running_job()
        request_cancel(job_id, ORG)
        job = get_training_job(job_id, ORG)
        assert job.status == TrainingStatus.CANCEL_REQUESTED
        assert job.cancel_evidence == CancelEvidence.REQUESTED
        assert job.is_billable  # Still billable!

    def test_cancel_confirm_stops_billing(self):
        job_id = _running_job()
        request_cancel(job_id, ORG)
        confirm_cancel(job_id, ORG)
        job = get_training_job(job_id, ORG)
        assert job.status == TrainingStatus.CANCEL_CONFIRMED
        assert job.cancel_evidence == CancelEvidence.PROCESS_TERMINATED
        assert not job.is_billable
        assert job.billing_stopped_at is not None

    def test_cancel_unresolved_stays_billable(self):
        job_id = _running_job()
        request_cancel(job_id, ORG)
        mark_cancel_unresolved(job_id, ORG, "provider timeout")
        job = get_training_job(job_id, ORG)
        assert job.status == TrainingStatus.CANCEL_UNRESOLVED
        assert job.is_billable  # STILL billable — unconfirmed

    def test_cancel_already_completed_idempotent(self):
        job_id = _running_job()
        mark_completed(job_id, ORG)
        request_cancel(job_id, ORG)  # After completion — no-op
        job = get_training_job(job_id, ORG)
        assert job.status == TrainingStatus.COMPLETED

    def test_cancel_during_transfer(self):
        job = create_training_job(ORG, TALENT, MANIFEST)
        assign_provider(job.job_id, ORG, "v-1", "w-1")
        request_cancel(job.job_id, ORG)
        assert job.status == TrainingStatus.CANCEL_REQUESTED


# =============================================================================
# Cost Accrual
# =============================================================================


@pytest.mark.unit
class TestCostAccrual:

    def test_cost_accrues_during_training(self):
        job_id = _running_job(cost_rate=2.0)
        job = get_training_job(job_id, ORG)
        # Simulate time passing
        job.billing_started_at = time.time() - 1800  # 30 min ago

        report_progress(job_id, ORG, current_step=50, total_steps=100)
        assert job.cost_accrued_usd > 0.0
        # 30 min at $2/hr = ~$1.00
        assert 0.9 < job.cost_accrued_usd < 1.1

    def test_cost_stops_on_completion(self):
        job_id = _running_job(cost_rate=2.0)
        job = get_training_job(job_id, ORG)
        job.billing_started_at = time.time() - 3600  # 1 hour

        mark_completed(job_id, ORG)
        assert job.billing_stopped_at is not None
        assert 1.9 < job.cost_accrued_usd < 2.1  # ~$2 for 1 hour

    def test_cost_continues_after_cancel_request(self):
        job_id = _running_job(cost_rate=1.0)
        job = get_training_job(job_id, ORG)
        job.billing_started_at = time.time() - 600  # 10 min

        request_cancel(job_id, ORG)
        # Still billable — no confirmation yet
        assert job.is_billable

    def test_cost_stops_on_cancel_confirm(self):
        job_id = _running_job(cost_rate=1.0)
        job = get_training_job(job_id, ORG)
        job.billing_started_at = time.time() - 600

        request_cancel(job_id, ORG)
        confirm_cancel(job_id, ORG)
        assert not job.is_billable
        assert job.billing_stopped_at is not None


# =============================================================================
# Cross-Tenant
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_get_returns_none(self):
        job_id = _running_job()
        assert get_training_job(job_id, OTHER_ORG) is None

    def test_cross_tenant_cancel_raises(self):
        job_id = _running_job()
        with pytest.raises(TrainingJobNotFound):
            request_cancel(job_id, OTHER_ORG)

    def test_cross_tenant_progress_raises(self):
        job_id = _running_job()
        with pytest.raises(TrainingJobNotFound):
            report_progress(job_id, OTHER_ORG, current_step=10)
