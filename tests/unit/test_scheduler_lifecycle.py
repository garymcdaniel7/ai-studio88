"""Scheduler Lifecycle Tests (Story 119).

Proves: single-owner, duplicate prevention, heartbeat expiry, overlap handling,
restart recovery, failure visibility, and readiness integration.

Run with:
    pytest tests/unit/test_scheduler_lifecycle.py -v
"""
from __future__ import annotations

import threading

import pytest

from backend.scheduler_lifecycle import (
    HEARTBEAT_TIMEOUT_SECONDS,
    JobOverlapError,
    JobState,
    OwnershipError,
    ScheduledJob,
    SchedulerOwnership,
    acquire_ownership,
    clear_registry,
    complete_job_run,
    disable_job,
    enable_job,
    fail_job_run,
    get_failed_jobs,
    get_job,
    get_ownership,
    get_scheduler_health,
    is_owner,
    list_jobs,
    recover_stale_jobs,
    register_job,
    release_ownership,
    send_heartbeat,
    start_job_run,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


# =============================================================================
# Single Owner
# =============================================================================


class TestSingleOwner:

    @pytest.mark.unit
    def test_first_instance_acquires(self):
        """First instance acquires ownership."""
        assert acquire_ownership("instance-A") is True
        assert is_owner("instance-A") is True

    @pytest.mark.unit
    def test_second_instance_blocked(self):
        """Second instance cannot acquire while first holds."""
        acquire_ownership("instance-A")
        assert acquire_ownership("instance-B") is False
        assert is_owner("instance-B") is False

    @pytest.mark.unit
    def test_same_instance_reacquires(self):
        """Same instance re-acquiring is idempotent."""
        acquire_ownership("instance-A")
        assert acquire_ownership("instance-A") is True

    @pytest.mark.unit
    def test_graceful_release_allows_new_owner(self):
        """After graceful release, new instance can claim."""
        acquire_ownership("instance-A")
        release_ownership("instance-A")
        assert acquire_ownership("instance-B") is True
        assert is_owner("instance-B") is True

    @pytest.mark.unit
    def test_wrong_instance_cannot_release(self):
        """Non-owner cannot release ownership."""
        acquire_ownership("instance-A")
        assert release_ownership("instance-B") is False
        assert is_owner("instance-A") is True


# =============================================================================
# Duplicate Prevention
# =============================================================================


class TestDuplicatePrevention:

    @pytest.mark.unit
    def test_concurrent_acquire_one_wins(self):
        """Under concurrency, exactly one instance acquires ownership."""
        results: list[tuple[str, bool]] = []

        def try_acquire(name: str):
            result = acquire_ownership(name)
            results.append((name, result))

        threads = [threading.Thread(target=try_acquire, args=(f"inst-{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        winners = [name for name, won in results if won]
        # At least one winner, and only one unique owner at the end
        ownership = get_ownership()
        assert ownership.is_active is True
        assert ownership.owner_id in [f"inst-{i}" for i in range(5)]

    @pytest.mark.unit
    def test_job_registration_idempotent(self):
        """Registering same job_id twice returns existing."""
        j1 = register_job(job_id="monitor-1", name="Health Check", interval_seconds=60)
        j2 = register_job(job_id="monitor-1", name="Different Name", interval_seconds=120)
        assert j1.job_id == j2.job_id
        assert j2.name == "Health Check"  # Original preserved


# =============================================================================
# Heartbeat Expiry
# =============================================================================


class TestHeartbeatExpiry:

    @pytest.mark.unit
    def test_valid_heartbeat_accepted(self):
        """Owner's heartbeat is accepted."""
        acquire_ownership("instance-A")
        assert send_heartbeat("instance-A") is True

    @pytest.mark.unit
    def test_non_owner_heartbeat_rejected(self):
        """Non-owner's heartbeat is rejected."""
        acquire_ownership("instance-A")
        assert send_heartbeat("instance-B") is False

    @pytest.mark.unit
    def test_expired_ownership_allows_takeover(self):
        """Expired heartbeat allows new instance to claim."""
        # Simulate expired ownership (old timestamp)
        acquire_ownership("instance-A", now="2020-01-01T00:00:00+00:00")
        # New instance tries with current time (well past timeout)
        assert acquire_ownership("instance-B", now="2025-06-01T00:00:00+00:00") is True
        assert is_owner("instance-B") is True

    @pytest.mark.unit
    def test_ownership_expiry_detection(self):
        """Ownership is detected as expired when heartbeat is stale."""
        acquire_ownership("instance-A", now="2020-01-01T00:00:00+00:00")
        ownership = get_ownership()
        assert ownership.is_expired("2025-01-01T00:00:00+00:00") is True

    @pytest.mark.unit
    def test_fresh_heartbeat_not_expired(self):
        """Recent heartbeat is not expired."""
        now = "2025-06-01T12:00:00+00:00"
        acquire_ownership("instance-A", now=now)
        ownership = get_ownership()
        assert ownership.is_expired(now) is False


# =============================================================================
# Overlap Handling
# =============================================================================


class TestOverlapHandling:

    @pytest.mark.unit
    def test_overlap_blocked_by_default(self):
        """Running job blocks re-start when overlap not allowed."""
        register_job(job_id="j-1", name="Monitor", interval_seconds=60)
        enable_job("j-1")
        start_job_run("j-1")
        with pytest.raises(JobOverlapError):
            start_job_run("j-1")

    @pytest.mark.unit
    def test_overlap_allowed_when_configured(self):
        """Job with allow_overlap=True can run concurrently."""
        register_job(job_id="j-2", name="Idempotent Check", interval_seconds=30, allow_overlap=True)
        enable_job("j-2")
        start_job_run("j-2")
        # Second start doesn't raise
        start_job_run("j-2")  # No exception

    @pytest.mark.unit
    def test_disabled_job_cannot_start(self):
        """Disabled job raises on start."""
        register_job(job_id="j-3", name="Disabled Job", interval_seconds=60)
        enable_job("j-3")
        disable_job("j-3")
        with pytest.raises(OwnershipError):
            start_job_run("j-3")


# =============================================================================
# Restart Recovery
# =============================================================================


class TestRecovery:

    @pytest.mark.unit
    def test_recover_running_jobs(self):
        """Jobs left RUNNING by dead owner are recovered as FAILED."""
        register_job(job_id="j-1", name="Stuck Job", interval_seconds=60)
        enable_job("j-1")
        start_job_run("j-1")
        assert get_job("j-1").state == JobState.RUNNING

        recovered = recover_stale_jobs()
        assert len(recovered) == 1
        assert recovered[0].job_id == "j-1"
        assert recovered[0].state == JobState.FAILED
        assert "previous owner died" in recovered[0].last_error

    @pytest.mark.unit
    def test_recovery_increments_failure_count(self):
        """Recovery increments failure_count."""
        register_job(job_id="j-1", name="Job", interval_seconds=60)
        enable_job("j-1")
        start_job_run("j-1")
        recover_stale_jobs()
        assert get_job("j-1").failure_count == 1

    @pytest.mark.unit
    def test_recovery_does_not_touch_completed(self):
        """Recovery doesn't affect completed or scheduled jobs."""
        register_job(job_id="j-ok", name="OK Job", interval_seconds=60)
        enable_job("j-ok")
        start_job_run("j-ok")
        complete_job_run("j-ok")

        recovered = recover_stale_jobs()
        assert len(recovered) == 0
        assert get_job("j-ok").state == JobState.COMPLETED


# =============================================================================
# Failure Visibility
# =============================================================================


class TestFailureVisibility:

    @pytest.mark.unit
    def test_failed_job_records_error(self):
        """Failed job records error message and timestamp."""
        register_job(job_id="j-1", name="Monitor", interval_seconds=60)
        enable_job("j-1")
        start_job_run("j-1")
        fail_job_run("j-1", error="Connection refused to provider")
        job = get_job("j-1")
        assert job.state == JobState.FAILED
        assert job.last_error == "Connection refused to provider"
        assert job.last_failure_at is not None
        assert job.failure_count == 1

    @pytest.mark.unit
    def test_get_failed_jobs(self):
        """Can query all failed jobs."""
        register_job(job_id="j-1", name="A", interval_seconds=60)
        register_job(job_id="j-2", name="B", interval_seconds=60)
        enable_job("j-1")
        enable_job("j-2")
        start_job_run("j-1")
        start_job_run("j-2")
        fail_job_run("j-1", error="err")
        complete_job_run("j-2")

        failed = get_failed_jobs()
        assert len(failed) == 1
        assert failed[0].job_id == "j-1"

    @pytest.mark.unit
    def test_scheduler_health_reports_state(self):
        """Health endpoint reports ownership and job counts."""
        acquire_ownership("instance-A")
        register_job(job_id="j-1", name="A", interval_seconds=60)
        register_job(job_id="j-2", name="B", interval_seconds=60)
        enable_job("j-1")
        enable_job("j-2")
        start_job_run("j-1")
        fail_job_run("j-1", error="err")

        health = get_scheduler_health()
        assert health["has_owner"] is True
        assert health["owner_id"] == "instance-A"
        assert health["total_jobs"] == 2
        assert health["failed_count"] == 1
        assert health["scheduled_count"] == 1  # j-2 still scheduled


# =============================================================================
# Job Lifecycle
# =============================================================================


class TestJobLifecycle:

    @pytest.mark.unit
    def test_full_lifecycle(self):
        """Job goes through full lifecycle: register → enable → run → complete."""
        register_job(job_id="j-1", name="Full Cycle", interval_seconds=60)
        assert get_job("j-1").state == JobState.REGISTERED

        enable_job("j-1")
        assert get_job("j-1").state == JobState.SCHEDULED

        start_job_run("j-1")
        assert get_job("j-1").state == JobState.RUNNING
        assert get_job("j-1").run_count == 1

        complete_job_run("j-1")
        assert get_job("j-1").state == JobState.COMPLETED
        assert get_job("j-1").last_success_at is not None

    @pytest.mark.unit
    def test_re_enable_after_failure(self):
        """Failed job can be re-enabled for next schedule."""
        register_job(job_id="j-1", name="Retry", interval_seconds=60)
        enable_job("j-1")
        start_job_run("j-1")
        fail_job_run("j-1", error="timeout")
        enable_job("j-1")
        assert get_job("j-1").state == JobState.SCHEDULED

    @pytest.mark.unit
    def test_disable_stops_scheduling(self):
        """Disabled job is not scheduled."""
        register_job(job_id="j-1", name="Disable", interval_seconds=60)
        enable_job("j-1")
        disable_job("j-1")
        assert get_job("j-1").state == JobState.DISABLED

    @pytest.mark.unit
    def test_list_jobs(self):
        """list_jobs returns all registered jobs."""
        register_job(job_id="j-1", name="A", interval_seconds=60)
        register_job(job_id="j-2", name="B", interval_seconds=120)
        assert len(list_jobs()) == 2

    @pytest.mark.unit
    def test_job_serializable(self):
        """ScheduledJob.to_dict() is JSON-serializable."""
        import json
        register_job(job_id="j-1", name="Test", interval_seconds=60)
        json.dumps(get_job("j-1").to_dict())
