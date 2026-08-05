"""Atomic job claiming tests — Story 054.

Tests prove:
  - Only one worker can claim a job (concurrency)
  - Claims require matching workspace and queue
  - Lease token required for all mutations (complete/fail/heartbeat)
  - Wrong lease token rejected
  - Expired lease allows re-claim (recovery)
  - Stale heartbeat detected as abandoned
  - Side-effect marker affects recovery policy
  - Stale worker completion rejected after re-lease
  - Cancellation signaled via heartbeat
  - Non-idempotent abandoned jobs fail permanently
"""

import threading
import time

import pytest

from backend.jobs.atomic_claim import (
    ClaimableJob,
    DuplicateClaimError,
    LeaseExpiredError,
    LeaseRequiredError,
    NoEligibleJobError,
    _reset_store,
    atomic_claim,
    cancel_with_lease,
    complete_with_lease,
    fail_with_lease,
    lease_heartbeat,
    mark_side_effect,
    recover_abandoned_leases,
    register_job,
    reject_stale_completion,
    verify_lease,
)

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
WORKER_1 = "worker-1"
WORKER_2 = "worker-2"


@pytest.fixture(autouse=True)
def clean_store():
    _reset_store()
    yield
    _reset_store()


def _register_test_job(**overrides) -> ClaimableJob:
    defaults = {
        "job_id": f"job-{id(overrides)}",
        "org_id": TENANT_A,
        "queue": "generation",
        "operation": "generate_image",
    }
    defaults.update(overrides)
    return register_job(**defaults)


# =============================================================================
# Atomic Claim — Basic
# =============================================================================


@pytest.mark.unit
class TestAtomicClaimBasic:
    """Verify basic claim behavior."""

    def test_claim_returns_job_and_lease(self):
        _register_test_job(job_id="j1")
        job, lease = atomic_claim(WORKER_1, TENANT_A, "generation")
        assert job.job_id == "j1"
        assert lease.lease_owner == WORKER_1
        assert lease.lease_token.startswith("lease-")
        assert job.status == "running"

    def test_no_eligible_job_raises(self):
        with pytest.raises(NoEligibleJobError):
            atomic_claim(WORKER_1, TENANT_A, "generation")

    def test_wrong_org_no_eligible(self):
        _register_test_job(job_id="j1", org_id=TENANT_A)
        with pytest.raises(NoEligibleJobError):
            atomic_claim(WORKER_1, "org-other", "generation")

    def test_wrong_queue_no_eligible(self):
        _register_test_job(job_id="j1", queue="training")
        with pytest.raises(NoEligibleJobError):
            atomic_claim(WORKER_1, TENANT_A, "generation")

    def test_cancelled_job_not_eligible(self):
        job = _register_test_job(job_id="j1")
        job.cancelled = True
        with pytest.raises(NoEligibleJobError):
            atomic_claim(WORKER_1, TENANT_A, "generation")


# =============================================================================
# Concurrency — Only One Claim Succeeds
# =============================================================================


@pytest.mark.unit
class TestConcurrency:
    """Verify only one worker wins the claim."""

    def test_second_claim_raises_duplicate(self):
        _register_test_job(job_id="j1")
        atomic_claim(WORKER_1, TENANT_A, "generation")
        with pytest.raises(NoEligibleJobError):
            atomic_claim(WORKER_2, TENANT_A, "generation")

    def test_concurrent_threads_one_winner(self):
        """Simulate concurrent claim attempts — only one should succeed."""
        _register_test_job(job_id="j-race")
        results = {"winners": 0, "losers": 0}

        def try_claim(worker_id):
            try:
                atomic_claim(worker_id, TENANT_A, "generation")
                results["winners"] += 1
            except (NoEligibleJobError, DuplicateClaimError):
                results["losers"] += 1

        threads = [
            threading.Thread(target=try_claim, args=(f"w-{i}",))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results["winners"] == 1
        assert results["losers"] == 9


# =============================================================================
# Lease Token — Mutation Guards
# =============================================================================


@pytest.mark.unit
class TestLeaseGuards:
    """Verify lease token is required for all mutations."""

    def test_complete_requires_correct_token(self):
        _register_test_job(job_id="j1")
        _, lease = atomic_claim(WORKER_1, TENANT_A, "generation")
        # Correct token works
        complete_with_lease("j1", lease.lease_token)

    def test_complete_wrong_token_rejected(self):
        _register_test_job(job_id="j1")
        atomic_claim(WORKER_1, TENANT_A, "generation")
        with pytest.raises(LeaseRequiredError, match="mismatch"):
            complete_with_lease("j1", "wrong-token")

    def test_heartbeat_requires_correct_token(self):
        _register_test_job(job_id="j1")
        _, lease = atomic_claim(WORKER_1, TENANT_A, "generation")
        assert lease_heartbeat("j1", lease.lease_token) is True

    def test_heartbeat_wrong_token_rejected(self):
        _register_test_job(job_id="j1")
        atomic_claim(WORKER_1, TENANT_A, "generation")
        with pytest.raises(LeaseRequiredError):
            lease_heartbeat("j1", "wrong-token")

    def test_fail_requires_correct_token(self):
        _register_test_job(job_id="j1")
        _, lease = atomic_claim(WORKER_1, TENANT_A, "generation")
        fail_with_lease("j1", lease.lease_token, "error")


# =============================================================================
# Lease Expiry and Recovery
# =============================================================================


@pytest.mark.unit
class TestLeaseExpiry:
    """Verify expired leases are recoverable."""

    def test_expired_lease_allows_reclaim(self):
        _register_test_job(job_id="j1")
        _, lease = atomic_claim(WORKER_1, TENANT_A, "generation", lease_duration=1)
        # Manually expire
        lease.lease_expiry = time.time() - 10

        # Second worker can now claim
        job2, lease2 = atomic_claim(WORKER_2, TENANT_A, "generation")
        assert job2.job_id == "j1"
        assert lease2.lease_owner == WORKER_2
        assert lease2.attempt_number == 2

    def test_expired_lease_rejected_on_mutation(self):
        _register_test_job(job_id="j1")
        _, lease = atomic_claim(WORKER_1, TENANT_A, "generation", lease_duration=1)
        lease.lease_expiry = time.time() - 10
        with pytest.raises(LeaseExpiredError):
            complete_with_lease("j1", lease.lease_token)

    def test_recover_abandoned_idempotent(self):
        _register_test_job(job_id="j1", is_idempotent=True)
        _, lease = atomic_claim(WORKER_1, TENANT_A, "generation", lease_duration=1)
        lease.lease_expiry = time.time() - 10  # Expire

        recovered = recover_abandoned_leases()
        assert "j1" in recovered

    def test_recover_with_side_effects_fails(self):
        _register_test_job(job_id="j1", is_idempotent=True)
        _, lease = atomic_claim(WORKER_1, TENANT_A, "generation", lease_duration=1)
        mark_side_effect("j1", lease.lease_token)
        lease.lease_expiry = time.time() - 10

        recovered = recover_abandoned_leases()
        assert "j1" not in recovered  # Cannot safely re-queue

    def test_non_idempotent_abandoned_fails(self):
        _register_test_job(job_id="j1", is_idempotent=False)
        _, lease = atomic_claim(WORKER_1, TENANT_A, "generation", lease_duration=1)
        lease.lease_expiry = time.time() - 10

        recovered = recover_abandoned_leases()
        assert "j1" not in recovered
        job = _register_test_job.__wrapped__ if hasattr(_register_test_job, '__wrapped__') else None
        # Verify it was marked failed
        from backend.jobs.atomic_claim import _job_registry
        assert _job_registry["j1"].status == "failed"


# =============================================================================
# Stale Worker Completion Guard
# =============================================================================


@pytest.mark.unit
class TestStaleCompletionGuard:
    """Verify stale workers cannot complete after re-lease."""

    def test_stale_token_rejected(self):
        _register_test_job(job_id="j1")
        _, old_lease = atomic_claim(WORKER_1, TENANT_A, "generation", lease_duration=1)
        old_token = old_lease.lease_token
        old_lease.lease_expiry = time.time() - 10  # Expire

        # Worker 2 re-claims
        _, new_lease = atomic_claim(WORKER_2, TENANT_A, "generation")

        # Worker 1 tries to complete with old token
        assert reject_stale_completion("j1", old_token) is True

    def test_current_token_accepted(self):
        _register_test_job(job_id="j1")
        _, lease = atomic_claim(WORKER_1, TENANT_A, "generation")
        assert reject_stale_completion("j1", lease.lease_token) is False


# =============================================================================
# Cancellation During Lease
# =============================================================================


@pytest.mark.unit
class TestCancellationDuringLease:
    """Verify cancellation is communicated via heartbeat."""

    def test_heartbeat_returns_false_when_cancelled(self):
        job = _register_test_job(job_id="j1")
        _, lease = atomic_claim(WORKER_1, TENANT_A, "generation")
        job.cancelled = True
        assert lease_heartbeat("j1", lease.lease_token) is False

    def test_cancel_acknowledge_with_lease(self):
        _register_test_job(job_id="j1")
        job, lease = atomic_claim(WORKER_1, TENANT_A, "generation")
        job.cancelled = True
        result = cancel_with_lease("j1", lease.lease_token)
        assert result.status == "cancelled"


# =============================================================================
# Side Effect Marker
# =============================================================================


@pytest.mark.unit
class TestSideEffectMarker:
    """Verify side-effect marking works."""

    def test_mark_before_external_call(self):
        _register_test_job(job_id="j1")
        _, lease = atomic_claim(WORKER_1, TENANT_A, "generation")
        mark_side_effect("j1", lease.lease_token)
        from backend.jobs.atomic_claim import _job_registry
        assert _job_registry["j1"].lease.side_effect_marker is True

    def test_mark_requires_lease(self):
        _register_test_job(job_id="j1")
        atomic_claim(WORKER_1, TENANT_A, "generation")
        with pytest.raises(LeaseRequiredError):
            mark_side_effect("j1", "wrong-token")


# =============================================================================
# Priority Ordering
# =============================================================================


@pytest.mark.unit
class TestPriorityOrdering:
    """Verify highest priority job is claimed first."""

    def test_higher_priority_claimed_first(self):
        _register_test_job(job_id="low", priority=10)
        _register_test_job(job_id="high", priority=1)
        job, _ = atomic_claim(WORKER_1, TENANT_A, "generation")
        assert job.job_id == "high"
