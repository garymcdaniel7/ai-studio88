"""Background Generation Job Tests (Story 053).

Proves: lifecycle states, submission/claim/execution split, cancel/retry
idempotency, restart recovery, heartbeat timeout, and tenant isolation.

Run with:
    pytest tests/unit/test_generation_jobs.py -v
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.generation_jobs import (
    GenerationState,
    _idempotency_index,
    _job_queue,
    _job_store,
    cancel_job,
    check_stale_jobs,
    claim_job,
    complete_job,
    fail_job,
    get_job_status,
    list_jobs_for_session,
    retry_job,
    start_execution,
    submit_generation,
    update_progress,
)

ORG_A = str(uuid4())
ORG_B = str(uuid4())
USER_A = str(uuid4())


@pytest.fixture(autouse=True)
def clean():
    _job_store.clear()
    _job_queue.clear()
    _idempotency_index.clear()
    yield
    _job_store.clear()
    _job_queue.clear()
    _idempotency_index.clear()


# =============================================================================
# Submission
# =============================================================================


class TestSubmission:

    @pytest.mark.unit
    def test_submit_returns_queued_job(self):
        """Submission creates a QUEUED job and returns immediately."""
        job = submit_generation(
            org_id=ORG_A, user_id=USER_A, prompt="A portrait",
            model="flux-dev", session_id="s1",
        )
        assert job.state == GenerationState.QUEUED
        assert job.id.startswith("gen-")
        assert job.org_id == ORG_A
        assert job.prompt == "A portrait"

    @pytest.mark.unit
    def test_submit_enqueues_for_worker(self):
        """Submitted job appears in the worker queue."""
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        assert job.id in _job_queue

    @pytest.mark.unit
    def test_idempotent_submission(self):
        """Same idempotency_key returns same job (no duplicate)."""
        j1 = submit_generation(
            org_id=ORG_A, user_id=USER_A, prompt="test",
            idempotency_key="key-1",
        )
        j2 = submit_generation(
            org_id=ORG_A, user_id=USER_A, prompt="test",
            idempotency_key="key-1",
        )
        assert j1.id == j2.id

    @pytest.mark.unit
    def test_submit_requires_prompt(self):
        from backend.generation_jobs import SubmissionError
        with pytest.raises(SubmissionError):
            submit_generation(org_id=ORG_A, user_id=USER_A, prompt="")


# =============================================================================
# Worker Claim & Execution
# =============================================================================


class TestWorkerExecution:

    @pytest.mark.unit
    def test_claim_takes_from_queue(self):
        """Worker claims the next queued job."""
        submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        job = claim_job("worker-1")
        assert job is not None
        assert job.state == GenerationState.CLAIMED
        assert job.worker_id == "worker-1"

    @pytest.mark.unit
    def test_claim_empty_queue_returns_none(self):
        assert claim_job("worker-1") is None

    @pytest.mark.unit
    def test_start_transitions_to_running(self):
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        claim_job("w1")
        assert start_execution(job.id) is True
        assert _job_store[job.id].state == GenerationState.RUNNING

    @pytest.mark.unit
    def test_progress_updates(self):
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        claim_job("w1")
        start_execution(job.id)
        update_progress(job.id, 0.5)
        assert _job_store[job.id].progress == 0.5

    @pytest.mark.unit
    def test_complete_registers_asset(self):
        """Completion records asset, cost, and provider info."""
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        claim_job("w1")
        start_execution(job.id)
        complete_job(
            job.id,
            output_asset_id="asset-123",
            actual_cost_usd=0.03,
            provider_used="comfyui",
            model_version="flux-dev-fp8",
        )
        stored = _job_store[job.id]
        assert stored.state == GenerationState.COMPLETED
        assert stored.output_asset_id == "asset-123"
        assert stored.actual_cost_usd == 0.03
        assert stored.provider_used == "comfyui"

    @pytest.mark.unit
    def test_fail_is_retryable(self):
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        claim_job("w1")
        start_execution(job.id)
        fail_job(job.id, "GPU OOM")
        stored = _job_store[job.id]
        assert stored.state == GenerationState.FAILED
        assert stored.state.is_retryable


# =============================================================================
# Cancel & Retry
# =============================================================================


class TestCancelRetry:

    @pytest.mark.unit
    def test_cancel_active_job(self):
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        result = cancel_job(job.id, ORG_A)
        assert result.state == GenerationState.CANCELLED

    @pytest.mark.unit
    def test_cancel_is_idempotent(self):
        """Double cancel returns same result."""
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        cancel_job(job.id, ORG_A)
        result = cancel_job(job.id, ORG_A)
        assert result.state == GenerationState.CANCELLED

    @pytest.mark.unit
    def test_cancel_cross_tenant_returns_none(self):
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        assert cancel_job(job.id, ORG_B) is None

    @pytest.mark.unit
    def test_retry_failed_job(self):
        """Retry re-enqueues a failed job."""
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        claim_job("w1")
        start_execution(job.id)
        fail_job(job.id, "error")

        result = retry_job(job.id, ORG_A)
        assert result.state == GenerationState.QUEUED
        assert result.attempt == 1
        assert job.id in _job_queue

    @pytest.mark.unit
    def test_retry_respects_max_attempts(self):
        """Cannot retry beyond max_attempts."""
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        job.state = GenerationState.FAILED
        job.attempt = 3  # Already at max

        result = retry_job(job.id, ORG_A)
        assert result.state == GenerationState.FAILED  # Not re-queued

    @pytest.mark.unit
    def test_retry_cancelled_job(self):
        """Can retry a cancelled job."""
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        cancel_job(job.id, ORG_A)
        result = retry_job(job.id, ORG_A)
        assert result.state == GenerationState.QUEUED

    @pytest.mark.unit
    def test_retry_cross_tenant_returns_none(self):
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        job.state = GenerationState.FAILED
        assert retry_job(job.id, ORG_B) is None


# =============================================================================
# Status & Reconnect
# =============================================================================


class TestStatusReconnect:

    @pytest.mark.unit
    def test_get_status_returns_current_state(self):
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test", session_id="s1")
        status = get_job_status(job.id, ORG_A)
        assert status["state"] == "queued"
        assert status["job_id"] == job.id

    @pytest.mark.unit
    def test_get_status_cross_tenant_none(self):
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        assert get_job_status(job.id, ORG_B) is None

    @pytest.mark.unit
    def test_list_jobs_for_session_reconnect(self):
        """Client can reconnect and see all jobs for their session."""
        submit_generation(org_id=ORG_A, user_id=USER_A, prompt="a", session_id="s1")
        submit_generation(org_id=ORG_A, user_id=USER_A, prompt="b", session_id="s1")
        submit_generation(org_id=ORG_A, user_id=USER_A, prompt="c", session_id="s2")

        s1_jobs = list_jobs_for_session("s1", ORG_A)
        assert len(s1_jobs) == 2

    @pytest.mark.unit
    def test_list_jobs_cross_tenant_empty(self):
        submit_generation(org_id=ORG_A, user_id=USER_A, prompt="a", session_id="s1")
        assert list_jobs_for_session("s1", ORG_B) == []


# =============================================================================
# Heartbeat / Timeout (restart recovery)
# =============================================================================


class TestHeartbeatTimeout:

    @pytest.mark.unit
    def test_stale_job_detected(self):
        """Job without heartbeat for >2min is timed out."""
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        claim_job("w1")
        start_execution(job.id)
        # Simulate stale heartbeat
        _job_store[job.id].last_heartbeat = (
            datetime.now(UTC) - timedelta(seconds=300)
        ).isoformat()

        timed_out = check_stale_jobs()
        assert job.id in timed_out
        assert _job_store[job.id].state == GenerationState.TIMEOUT

    @pytest.mark.unit
    def test_timeout_is_retryable(self):
        """Timed-out jobs can be retried."""
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        claim_job("w1")
        start_execution(job.id)
        _job_store[job.id].last_heartbeat = (
            datetime.now(UTC) - timedelta(seconds=300)
        ).isoformat()
        check_stale_jobs()

        result = retry_job(job.id, ORG_A)
        assert result.state == GenerationState.QUEUED

    @pytest.mark.unit
    def test_healthy_job_not_timed_out(self):
        """Job with recent heartbeat is NOT timed out."""
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        claim_job("w1")
        start_execution(job.id)
        update_progress(job.id, 0.3)  # Fresh heartbeat

        timed_out = check_stale_jobs()
        assert job.id not in timed_out


# =============================================================================
# Browser Closure Recovery
# =============================================================================


class TestBrowserClosureRecovery:

    @pytest.mark.unit
    def test_job_survives_independent_of_session(self):
        """Job persists in store regardless of client connection."""
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="survive", session_id="s1")

        # Simulate: client disconnects, time passes, client reconnects
        # Job is still in store and queryable
        status = get_job_status(job.id, ORG_A)
        assert status is not None
        assert status["state"] == "queued"

    @pytest.mark.unit
    def test_completed_job_has_asset_after_disconnect(self):
        """After worker completes, asset is available regardless of client."""
        job = submit_generation(org_id=ORG_A, user_id=USER_A, prompt="test")
        claim_job("w1")
        start_execution(job.id)
        complete_job(job.id, output_asset_id="asset-final", actual_cost_usd=0.02)

        # Client reconnects later
        status = get_job_status(job.id, ORG_A)
        assert status["state"] == "completed"
        assert status["output_asset_id"] == "asset-final"
