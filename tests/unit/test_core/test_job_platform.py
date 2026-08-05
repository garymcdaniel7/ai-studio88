"""Canonical durable job platform tests — Story 052.

Tests prove:
  - Job submission requires org_id and operation
  - Duplicate idempotency key rejected for active jobs
  - Lifecycle transitions are correct (queued→running→completed)
  - Retry on failure for idempotent jobs
  - No retry for non-idempotent jobs (immediate fail)
  - Dead letter after retry exhaustion
  - Cancellation of queued job (immediate)
  - Cancellation of running job (flag for heartbeat)
  - Heartbeat returns False when cancelled (signal to stop)
  - Timeout detection works
  - Stale heartbeat detection works
  - Large payload rejected (must use payload_ref)
  - Queue routing assigns correct queue
  - Domain adapters use correct routes and configs
  - Monitoring stats are accurate
"""

import time

import pytest

from backend.jobs.platform import (
    DEFAULT_RETRY,
    NO_RETRY,
    JobDuplicateError,
    JobEnvelope,
    JobStatus,
    QueueRoute,
    RetryPolicy,
    _reset_store,
    cancel_job,
    claim_job,
    complete_job,
    fail_job,
    get_job,
    get_queue_stats,
    heartbeat,
    submit_fleet_job,
    submit_generation_job,
    submit_job,
    submit_publishing_job,
    submit_training_job,
)

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_A = "user-aaaa"


@pytest.fixture(autouse=True)
def clean_store():
    _reset_store()
    yield
    _reset_store()


# =============================================================================
# Submission Validation
# =============================================================================


@pytest.mark.unit
class TestJobSubmission:
    """Verify job submission validates context."""

    def test_valid_submission(self):
        job = submit_job(TENANT_A, USER_A, "generate_image", {"prompt": "test"})
        assert job.status == JobStatus.QUEUED
        assert job.org_id == TENANT_A
        assert job.user_id == USER_A
        assert job.operation == "generate_image"

    def test_requires_org_id(self):
        with pytest.raises(ValueError, match="org_id"):
            submit_job("", USER_A, "generate_image", {})

    def test_requires_user_id_for_user_jobs(self):
        with pytest.raises(ValueError, match="user_id"):
            submit_job(TENANT_A, "", "generate_image", {})

    def test_requires_operation(self):
        with pytest.raises(ValueError, match="operation"):
            submit_job(TENANT_A, USER_A, "", {})

    def test_rejects_large_payload(self):
        big_payload = {"data": "x" * 100_000}
        with pytest.raises(ValueError, match="Payload too large"):
            submit_job(TENANT_A, USER_A, "test", big_payload)

    def test_system_jobs_skip_user_id(self):
        """System jobs don't need user_id."""
        job = submit_job(TENANT_A, "system", "cleanup", {}, actor_type="system")
        assert job.actor_type == "system"


# =============================================================================
# Idempotency (Duplicate Detection)
# =============================================================================


@pytest.mark.unit
class TestIdempotency:
    """Verify duplicate submissions are rejected."""

    def test_duplicate_key_rejected(self):
        submit_job(TENANT_A, USER_A, "test", {}, idempotency_key="key-1")
        with pytest.raises(JobDuplicateError):
            submit_job(TENANT_A, USER_A, "test", {}, idempotency_key="key-1")

    def test_duplicate_allowed_after_terminal(self):
        """Duplicate key OK if previous job completed."""
        job = submit_job(TENANT_A, USER_A, "test", {}, idempotency_key="key-2")
        claim_job(job.job_id, "worker-1")
        complete_job(job.job_id)
        # Should NOT raise — previous is terminal
        new_job = submit_job(TENANT_A, USER_A, "test", {}, idempotency_key="key-2")
        assert new_job.job_id != job.job_id


# =============================================================================
# Lifecycle Transitions
# =============================================================================


@pytest.mark.unit
class TestLifecycle:
    """Verify lifecycle transitions."""

    def test_submit_to_queued(self):
        job = submit_job(TENANT_A, USER_A, "test", {})
        assert job.status == JobStatus.QUEUED
        assert job.queued_at is not None

    def test_claim_to_running(self):
        job = submit_job(TENANT_A, USER_A, "test", {})
        claimed = claim_job(job.job_id, "worker-1")
        assert claimed.status == JobStatus.RUNNING
        assert claimed.started_at is not None
        assert claimed.attempts == 1

    def test_complete_from_running(self):
        job = submit_job(TENANT_A, USER_A, "test", {})
        claim_job(job.job_id, "w1")
        completed = complete_job(job.job_id, result={"output": "done"})
        assert completed.status == JobStatus.COMPLETED
        assert completed.result == {"output": "done"}

    def test_cannot_claim_non_queued(self):
        job = submit_job(TENANT_A, USER_A, "test", {})
        claim_job(job.job_id, "w1")
        # Already running — cannot claim again
        assert claim_job(job.job_id, "w2") is None


# =============================================================================
# Retry and Dead Letter
# =============================================================================


@pytest.mark.unit
class TestRetryBehavior:
    """Verify retry policy enforcement."""

    def test_idempotent_retries_on_failure(self):
        job = submit_job(TENANT_A, USER_A, "test", {}, retry_config=DEFAULT_RETRY)
        claim_job(job.job_id, "w1")
        failed = fail_job(job.job_id, "Connection timeout")
        # Should be re-queued, not terminal
        assert failed.status == JobStatus.QUEUED

    def test_non_idempotent_fails_immediately(self):
        job = submit_job(TENANT_A, USER_A, "generate", {}, retry_config=NO_RETRY)
        claim_job(job.job_id, "w1")
        failed = fail_job(job.job_id, "GPU error")
        assert failed.status == JobStatus.FAILED

    def test_dead_letter_after_exhaustion(self):
        from backend.jobs.platform import RetryConfig
        config = RetryConfig(max_retries=2, policy=RetryPolicy.IDEMPOTENT)
        job = submit_job(TENANT_A, USER_A, "test", {}, retry_config=config)

        # Attempt 1 — fails, retries (attempts=1 < max_retries=2)
        claim_job(job.job_id, "w1")
        fail_job(job.job_id, "fail-1")
        assert job.status == JobStatus.QUEUED  # Re-queued

        # Attempt 2 — fails, retries (attempts=2 = max_retries, so dead letter)
        claim_job(job.job_id, "w2")
        result = fail_job(job.job_id, "fail-2")
        assert result.status == JobStatus.DEAD_LETTER


# =============================================================================
# Cancellation
# =============================================================================


@pytest.mark.unit
class TestCancellation:
    """Verify cancellation behavior."""

    def test_cancel_queued_immediate(self):
        job = submit_job(TENANT_A, USER_A, "test", {})
        cancelled = cancel_job(job.job_id, "user request")
        assert cancelled.status == JobStatus.CANCELLED
        assert cancelled.cancel_reason == "user request"

    def test_cancel_running_sets_flag(self):
        job = submit_job(TENANT_A, USER_A, "test", {})
        claim_job(job.job_id, "w1")
        cancel_job(job.job_id, "too expensive")
        # Status still RUNNING (worker handles graceful stop)
        assert job.cancelled is True

    def test_heartbeat_returns_false_when_cancelled(self):
        job = submit_job(TENANT_A, USER_A, "test", {})
        claim_job(job.job_id, "w1")
        cancel_job(job.job_id, "abort")
        # Worker heartbeat should signal cancellation
        assert heartbeat(job.job_id) is False

    def test_cancel_terminal_no_effect(self):
        job = submit_job(TENANT_A, USER_A, "test", {})
        claim_job(job.job_id, "w1")
        complete_job(job.job_id)
        assert cancel_job(job.job_id) is None


# =============================================================================
# Timeout and Heartbeat
# =============================================================================


@pytest.mark.unit
class TestTimeoutHeartbeat:
    """Verify timeout and heartbeat detection."""

    def test_timeout_detection(self):
        job = submit_job(TENANT_A, USER_A, "test", {}, timeout_seconds=1)
        claim_job(job.job_id, "w1")
        job.started_at = time.time() - 10  # Simulate elapsed time
        assert job.is_timed_out is True

    def test_not_timed_out_within_limit(self):
        job = submit_job(TENANT_A, USER_A, "test", {}, timeout_seconds=3600)
        claim_job(job.job_id, "w1")
        assert job.is_timed_out is False

    def test_stale_heartbeat_detection(self):
        job = submit_job(TENANT_A, USER_A, "test", {})
        claim_job(job.job_id, "w1")
        job.last_heartbeat = time.time() - 200  # 200s ago, interval=30s
        assert job.is_heartbeat_stale is True

    def test_fresh_heartbeat_not_stale(self):
        job = submit_job(TENANT_A, USER_A, "test", {})
        claim_job(job.job_id, "w1")
        heartbeat(job.job_id)
        assert job.is_heartbeat_stale is False


# =============================================================================
# Queue Routing
# =============================================================================


@pytest.mark.unit
class TestQueueRouting:
    """Verify jobs are routed to correct queues."""

    def test_generation_route(self):
        job = submit_generation_job(TENANT_A, USER_A, {"prompt": "test"})
        assert job.queue_route == QueueRoute.GENERATION
        assert job.retry_config.policy == RetryPolicy.NON_IDEMPOTENT

    def test_training_route(self):
        job = submit_training_job(TENANT_A, USER_A, {"talent_id": "t1"})
        assert job.queue_route == QueueRoute.TRAINING
        assert job.timeout_seconds == 14400
        assert job.priority == 3

    def test_fleet_route(self):
        job = submit_fleet_job(TENANT_A, USER_A, "launch_worker", {"gpu": "A100"})
        assert job.queue_route == QueueRoute.FLEET
        assert job.retry_config.policy == RetryPolicy.IDEMPOTENT

    def test_publishing_route(self):
        job = submit_publishing_job(TENANT_A, USER_A, {"platform": "instagram"})
        assert job.queue_route == QueueRoute.PUBLISHING
        assert job.retry_config.policy == RetryPolicy.NON_IDEMPOTENT


# =============================================================================
# Monitoring
# =============================================================================


@pytest.mark.unit
class TestMonitoring:
    """Verify queue stats are accurate."""

    def test_empty_stats(self):
        stats = get_queue_stats()
        assert stats["total_queued"] == 0
        assert stats["total_running"] == 0
        assert stats["total_jobs"] == 0

    def test_stats_reflect_submissions(self):
        submit_job(TENANT_A, USER_A, "a", {}, queue_route=QueueRoute.GENERATION)
        submit_job(TENANT_A, USER_A, "b", {}, queue_route=QueueRoute.GENERATION)
        submit_job(TENANT_A, USER_A, "c", {}, queue_route=QueueRoute.TRAINING)

        stats = get_queue_stats()
        assert stats["total_queued"] == 3
        assert stats["queues"]["generation"]["queued"] == 2
        assert stats["queues"]["training"]["queued"] == 1
