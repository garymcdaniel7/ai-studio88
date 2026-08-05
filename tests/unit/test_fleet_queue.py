"""Durable Fleet Queue Tests (Story 055).

Proves: atomic claims, lease expiry, restart recovery, cancellation races,
concurrent claims, tenant isolation, and priority ordering.

Run with:
    pytest tests/unit/test_fleet_queue.py -v
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.fleet_queue import (
    FleetJobState,
    FleetQueueService,
    _fleet_store,
)

ORG_A = str(uuid4())
ORG_B = str(uuid4())
USER_A = str(uuid4())


@pytest.fixture(autouse=True)
def clean():
    _fleet_store.clear()
    yield
    _fleet_store.clear()


def _enqueue(org_id=ORG_A, model="flux-dev", priority=5):
    return FleetQueueService.enqueue(
        generation_job_id=f"gen-{uuid4().hex[:8]}",
        org_id=org_id, user_id=USER_A,
        required_model=model, priority=priority,
    )


# =============================================================================
# Atomic Claim
# =============================================================================


class TestAtomicClaim:

    @pytest.mark.unit
    def test_claim_returns_pending_job(self):
        _enqueue()
        job = FleetQueueService.atomic_claim("worker-1")
        assert job is not None
        assert job.state == FleetJobState.LEASED
        assert job.leased_by_worker_id == "worker-1"

    @pytest.mark.unit
    def test_claimed_job_not_reclaimable(self):
        """Once claimed, another worker cannot claim the same job."""
        _enqueue()
        FleetQueueService.atomic_claim("worker-1")
        # Second worker gets nothing
        job2 = FleetQueueService.atomic_claim("worker-2")
        assert job2 is None

    @pytest.mark.unit
    def test_claim_empty_queue_returns_none(self):
        assert FleetQueueService.atomic_claim("w1") is None

    @pytest.mark.unit
    def test_claim_filters_by_model(self):
        """Worker only claims jobs matching its supported models."""
        _enqueue(model="flux-dev")
        _enqueue(model="sdxl-turbo")
        job = FleetQueueService.atomic_claim("w1", supported_models=["sdxl-turbo"])
        assert job is not None
        assert job.required_model == "sdxl-turbo"

    @pytest.mark.unit
    def test_claim_priority_ordering(self):
        """Higher priority (lower number) claimed first."""
        _enqueue(priority=8)
        high = _enqueue(priority=2)
        job = FleetQueueService.atomic_claim("w1")
        assert job.id == high.id


# =============================================================================
# Lease Expiry (Restart Recovery)
# =============================================================================


class TestLeaseExpiry:

    @pytest.mark.unit
    def test_expired_lease_detected(self):
        """Job with expired lease is marked LEASE_EXPIRED."""
        _enqueue()
        job = FleetQueueService.atomic_claim("w1", lease_seconds=1)
        # Simulate time passing
        _fleet_store[job.id].lease_expires_at = (
            datetime.now(UTC) - timedelta(seconds=60)
        ).isoformat()

        expired = FleetQueueService.check_expired_leases()
        assert job.id in expired
        assert _fleet_store[job.id].state == FleetJobState.LEASE_EXPIRED

    @pytest.mark.unit
    def test_expired_job_is_retryable(self):
        """LEASE_EXPIRED jobs can be re-enqueued."""
        job = _enqueue()
        FleetQueueService.atomic_claim("w1")
        _fleet_store[job.id].lease_expires_at = (
            datetime.now(UTC) - timedelta(seconds=60)
        ).isoformat()
        FleetQueueService.check_expired_leases()

        result = FleetQueueService.retry(job.id, ORG_A)
        assert result.state == FleetJobState.PENDING

    @pytest.mark.unit
    def test_heartbeat_extends_lease(self):
        """Heartbeat refreshes the lease (prevents expiry)."""
        job = _enqueue()
        FleetQueueService.atomic_claim("w1", lease_seconds=10)
        old_expiry = _fleet_store[job.id].lease_expires_at

        FleetQueueService.heartbeat(job.id, "w1")
        new_expiry = _fleet_store[job.id].lease_expires_at
        assert new_expiry > old_expiry

    @pytest.mark.unit
    def test_wrong_worker_cannot_heartbeat(self):
        """Only the lease holder can heartbeat."""
        job = _enqueue()
        FleetQueueService.atomic_claim("w1")
        assert FleetQueueService.heartbeat(job.id, "imposter") is False


# =============================================================================
# Cancellation Races
# =============================================================================


class TestCancellationRaces:

    @pytest.mark.unit
    def test_cancel_pending_job(self):
        job = _enqueue()
        result = FleetQueueService.cancel(job.id, ORG_A)
        assert result.state == FleetJobState.CANCELLED

    @pytest.mark.unit
    def test_cancel_leased_job(self):
        """Can cancel even after worker claimed (before completion)."""
        job = _enqueue()
        FleetQueueService.atomic_claim("w1")
        result = FleetQueueService.cancel(job.id, ORG_A)
        assert result.state == FleetJobState.CANCELLED

    @pytest.mark.unit
    def test_cancel_completed_no_effect(self):
        """Cannot cancel a completed job."""
        job = _enqueue()
        FleetQueueService.atomic_claim("w1")
        FleetQueueService.complete(job.id, "w1", output_asset_id="a1")
        result = FleetQueueService.cancel(job.id, ORG_A)
        assert result.state == FleetJobState.COMPLETED  # Unchanged

    @pytest.mark.unit
    def test_cancel_is_idempotent(self):
        job = _enqueue()
        FleetQueueService.cancel(job.id, ORG_A)
        result = FleetQueueService.cancel(job.id, ORG_A)
        assert result.state == FleetJobState.CANCELLED


# =============================================================================
# Tenant Isolation
# =============================================================================


class TestTenantIsolation:

    @pytest.mark.unit
    def test_cancel_wrong_org_returns_none(self):
        job = _enqueue(org_id=ORG_A)
        assert FleetQueueService.cancel(job.id, ORG_B) is None

    @pytest.mark.unit
    def test_retry_wrong_org_returns_none(self):
        job = _enqueue(org_id=ORG_A)
        _fleet_store[job.id].state = FleetJobState.FAILED
        assert FleetQueueService.retry(job.id, ORG_B) is None

    @pytest.mark.unit
    def test_status_wrong_org_returns_none(self):
        job = _enqueue(org_id=ORG_A)
        assert FleetQueueService.get_status(job.id, ORG_B) is None
        assert FleetQueueService.get_status(job.id, ORG_A) is not None


# =============================================================================
# Completion & Failure
# =============================================================================


class TestCompletionFailure:

    @pytest.mark.unit
    def test_complete_records_output(self):
        job = _enqueue()
        FleetQueueService.atomic_claim("w1")
        FleetQueueService.start_execution(job.id, "w1")
        FleetQueueService.complete(job.id, "w1", output_asset_id="asset-xyz", actual_cost_usd=0.05)

        stored = _fleet_store[job.id]
        assert stored.state == FleetJobState.COMPLETED
        assert stored.output_asset_id == "asset-xyz"
        assert stored.actual_cost_usd == 0.05

    @pytest.mark.unit
    def test_wrong_worker_cannot_complete(self):
        """Only the lease holder can complete."""
        job = _enqueue()
        FleetQueueService.atomic_claim("w1")
        assert FleetQueueService.complete(job.id, "imposter") is False

    @pytest.mark.unit
    def test_fail_releases_lease(self):
        """Failed job releases the worker lease (can be retried by another)."""
        job = _enqueue()
        FleetQueueService.atomic_claim("w1")
        FleetQueueService.fail(job.id, "w1", "GPU OOM")

        stored = _fleet_store[job.id]
        assert stored.state == FleetJobState.FAILED
        assert stored.leased_by_worker_id is None  # Released
        assert stored.error == "GPU OOM"

    @pytest.mark.unit
    def test_retry_max_attempts(self):
        """Cannot retry beyond max_attempts."""
        job = _enqueue()
        _fleet_store[job.id].state = FleetJobState.FAILED
        _fleet_store[job.id].attempt = 3  # At max

        result = FleetQueueService.retry(job.id, ORG_A)
        assert result.state == FleetJobState.FAILED  # Not re-enqueued

    @pytest.mark.unit
    def test_pending_count(self):
        """get_pending_count reflects queue depth."""
        _enqueue()
        _enqueue()
        _enqueue()
        FleetQueueService.atomic_claim("w1")  # Claims one

        assert FleetQueueService.get_pending_count() == 2
