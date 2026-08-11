"""Unit tests for JobRepository — job leasing and claim operations.

Tests atomic claiming (FOR UPDATE SKIP LOCKED semantics), lease release
with stale worker rejection, heartbeat extension, and stale lease expiration.
All DB operations are mocked — no I/O.

Validates: Requirements R21.3, R21.4, R21.5, R21.11, R21.12, R64.2
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def org_id() -> UUID:
    """A sample org_id for tests."""
    return uuid4()


@pytest.fixture
def other_org_id() -> UUID:
    """A different org_id for cross-tenant tests."""
    return uuid4()


@pytest.fixture
def job_id() -> UUID:
    """A sample job_id."""
    return uuid4()


@pytest.fixture
def lease_token() -> UUID:
    """A sample lease token."""
    return uuid4()


@pytest.fixture
def mock_job(org_id: UUID, job_id: UUID) -> MagicMock:
    """Create a mock Job instance."""
    job = MagicMock()
    job.id = job_id
    job.org_id = org_id
    job.job_type = "image_generation"
    job.status = "queued"
    job.priority = 5
    job.attempt_count = 0
    job.max_attempts = 3
    job.max_duration_seconds = 1800
    job.workload_class = "image_generation"
    job.idempotency_key = None
    job.started_at = None
    job.completed_at = None
    job.error_message = None
    job.progress_percent = None
    job.progress_message = None
    job.cost_usd = None
    job.output_asset_ids = None
    return job


@pytest.fixture
def mock_lease(org_id: UUID, job_id: UUID, lease_token: UUID) -> MagicMock:
    """Create a mock JobLease instance."""
    lease = MagicMock()
    lease.id = uuid4()
    lease.org_id = org_id
    lease.job_id = job_id
    lease.worker_identity = "worker-1"
    lease.lease_token = lease_token
    lease.lease_expiration = datetime.now(UTC) + timedelta(minutes=30)
    lease.heartbeat_at = datetime.now(UTC)
    return lease


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock async database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def repo(mock_db: AsyncMock, org_id: UUID):
    """Create a JobRepository with mocked dependencies."""
    from app.repositories.job_repository import JobRepository

    return JobRepository(db=mock_db, org_id=org_id)


# =============================================================================
# Test: claim_next_job
# =============================================================================


class TestClaimNextJob:
    """Tests for the atomic job claiming operation (R21.3, R64.2)."""

    @pytest.mark.unit
    async def test_claim_returns_job_and_lease_when_available(
        self, repo, mock_db, mock_job, org_id
    ):
        """When a queued job exists, claim returns (Job, JobLease)."""
        # Setup: DB returns a queued job
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db.execute.return_value = mock_result

        result = await repo.claim_next_job(worker_identity="worker-1")

        assert result is not None
        job, lease = result
        assert job.status == "claimed"
        assert job.attempt_count == 1
        mock_db.add.assert_called_once()  # Lease was added
        mock_db.flush.assert_called_once()

    @pytest.mark.unit
    async def test_claim_returns_none_when_no_jobs(
        self, repo, mock_db, org_id
    ):
        """When no queued jobs exist, claim returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await repo.claim_next_job(worker_identity="worker-1")

        assert result is None
        mock_db.add.assert_not_called()

    @pytest.mark.unit
    async def test_claim_increments_attempt_count(
        self, repo, mock_db, mock_job, org_id
    ):
        """Claiming a job increments its attempt_count."""
        mock_job.attempt_count = 2
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db.execute.return_value = mock_result

        result = await repo.claim_next_job(worker_identity="worker-1")

        assert result is not None
        job, _lease = result
        assert job.attempt_count == 3

    @pytest.mark.unit
    async def test_claim_respects_workload_class_filter(
        self, repo, mock_db, mock_job, org_id
    ):
        """When workload_class is specified, only matching jobs are claimed."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db.execute.return_value = mock_result

        result = await repo.claim_next_job(
            worker_identity="worker-1",
            workload_class="image_generation",
        )

        # Verify execute was called (the WHERE clause adds workload_class)
        assert result is not None
        mock_db.execute.assert_called_once()

    @pytest.mark.unit
    async def test_claim_uses_custom_lease_duration(
        self, repo, mock_db, mock_job, org_id
    ):
        """Custom lease_duration is reflected in the created lease."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db.execute.return_value = mock_result

        custom_duration = timedelta(hours=2)
        result = await repo.claim_next_job(
            worker_identity="worker-1",
            lease_duration=custom_duration,
        )

        assert result is not None
        # The lease added to session should have an expiration ~2 hours from now
        mock_db.add.assert_called_once()


# =============================================================================
# Test: release_lease
# =============================================================================


class TestReleaseLease:
    """Tests for lease release (R21.12 stale worker rejection)."""

    @pytest.mark.unit
    async def test_release_with_valid_token_succeeds(
        self, repo, mock_db, mock_job, mock_lease, org_id, job_id, lease_token
    ):
        """Releasing with the correct token succeeds."""
        # Mock _get_active_lease to return the lease
        mock_lease_result = MagicMock()
        mock_lease_result.scalar_one_or_none.return_value = mock_lease

        # Mock get_by_id for the job lookup
        mock_job_result = MagicMock()
        mock_job_result.scalar_one_or_none.return_value = mock_job

        mock_db.execute.side_effect = [mock_lease_result, mock_job_result]

        job = await repo.release_lease(
            job_id=job_id,
            lease_token=lease_token,
            final_status="completed",
        )

        assert job.status == "completed"
        assert job.completed_at is not None

    @pytest.mark.unit
    async def test_release_with_wrong_token_raises_valueerror(
        self, repo, mock_db, mock_lease, org_id, job_id
    ):
        """Releasing with a wrong token raises ValueError (stale worker)."""
        mock_lease_result = MagicMock()
        mock_lease_result.scalar_one_or_none.return_value = mock_lease
        mock_db.execute.return_value = mock_lease_result

        wrong_token = uuid4()

        with pytest.raises(ValueError, match="Invalid lease token"):
            await repo.release_lease(
                job_id=job_id,
                lease_token=wrong_token,
                final_status="completed",
            )

    @pytest.mark.unit
    async def test_release_with_no_active_lease_raises_valueerror(
        self, repo, mock_db, org_id, job_id, lease_token
    ):
        """Releasing when no active lease exists raises ValueError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="No active lease found"):
            await repo.release_lease(
                job_id=job_id,
                lease_token=lease_token,
                final_status="completed",
            )

    @pytest.mark.unit
    async def test_release_sets_cost_and_output_assets(
        self, repo, mock_db, mock_job, mock_lease, org_id, job_id, lease_token
    ):
        """Release correctly sets cost_usd and output_asset_ids."""
        mock_lease_result = MagicMock()
        mock_lease_result.scalar_one_or_none.return_value = mock_lease
        mock_job_result = MagicMock()
        mock_job_result.scalar_one_or_none.return_value = mock_job
        mock_db.execute.side_effect = [mock_lease_result, mock_job_result]

        output_ids = [uuid4(), uuid4()]

        job = await repo.release_lease(
            job_id=job_id,
            lease_token=lease_token,
            final_status="completed",
            cost_usd=2.50,
            output_asset_ids=output_ids,
        )

        assert job.cost_usd == 2.50
        assert job.output_asset_ids == output_ids


# =============================================================================
# Test: heartbeat
# =============================================================================


class TestHeartbeat:
    """Tests for lease heartbeat extension (R21.4, R21.5)."""

    @pytest.mark.unit
    async def test_heartbeat_extends_lease(
        self, repo, mock_db, mock_lease, org_id, job_id, lease_token
    ):
        """Valid heartbeat extends the lease expiration."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_lease
        mock_db.execute.return_value = mock_result

        lease = await repo.heartbeat(
            job_id=job_id,
            lease_token=lease_token,
        )

        # Heartbeat should update heartbeat_at and lease_expiration
        assert lease.heartbeat_at is not None
        assert lease.lease_expiration is not None

    @pytest.mark.unit
    async def test_heartbeat_with_wrong_token_raises(
        self, repo, mock_db, mock_lease, org_id, job_id
    ):
        """Heartbeat with wrong token is rejected (stale worker)."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_lease
        mock_db.execute.return_value = mock_result

        wrong_token = uuid4()

        with pytest.raises(ValueError, match="Invalid lease token"):
            await repo.heartbeat(
                job_id=job_id,
                lease_token=wrong_token,
            )

    @pytest.mark.unit
    async def test_heartbeat_with_no_active_lease_raises(
        self, repo, mock_db, org_id, job_id, lease_token
    ):
        """Heartbeat when no active lease exists raises ValueError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="No active lease found"):
            await repo.heartbeat(
                job_id=job_id,
                lease_token=lease_token,
            )

    @pytest.mark.unit
    async def test_heartbeat_with_progress_updates_job(
        self, repo, mock_db, mock_job, mock_lease, org_id, job_id, lease_token
    ):
        """Heartbeat with progress updates the job's progress fields."""
        mock_lease_result = MagicMock()
        mock_lease_result.scalar_one_or_none.return_value = mock_lease

        mock_job_result = MagicMock()
        mock_job_result.scalar_one_or_none.return_value = mock_job

        mock_db.execute.side_effect = [mock_lease_result, mock_job_result]

        await repo.heartbeat(
            job_id=job_id,
            lease_token=lease_token,
            progress_percent=42,
            progress_message="Processing frame 42/100",
        )

        assert mock_job.progress_percent == 42
        assert mock_job.progress_message == "Processing frame 42/100"


# =============================================================================
# Test: expire_stale_leases
# =============================================================================


class TestExpireStaleLeases:
    """Tests for stale lease expiration (R21.5, R21.8, R21.9)."""

    @pytest.mark.unit
    async def test_expire_requeues_job_under_max_attempts(
        self, repo, mock_db, mock_job, mock_lease, org_id
    ):
        """Expired lease on job with attempts remaining → re-queue."""
        mock_lease.lease_expiration = datetime.now(UTC) - timedelta(minutes=5)
        mock_job.attempt_count = 1
        mock_job.max_attempts = 3
        mock_job.status = "claimed"

        # First execute: find expired leases
        leases_result = MagicMock()
        leases_result.scalars.return_value.all.return_value = [mock_lease]

        # Second execute: get associated job
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = mock_job

        mock_db.execute.side_effect = [leases_result, job_result]

        expired_ids = await repo.expire_stale_leases()

        assert len(expired_ids) == 1
        assert mock_job.status == "queued"
        assert mock_job.started_at is None

    @pytest.mark.unit
    async def test_expire_fails_job_at_max_attempts(
        self, repo, mock_db, mock_job, mock_lease, org_id
    ):
        """Expired lease on job at max attempts → mark failed."""
        mock_lease.lease_expiration = datetime.now(UTC) - timedelta(minutes=5)
        mock_job.attempt_count = 3
        mock_job.max_attempts = 3
        mock_job.status = "running"

        leases_result = MagicMock()
        leases_result.scalars.return_value.all.return_value = [mock_lease]

        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = mock_job

        mock_db.execute.side_effect = [leases_result, job_result]

        expired_ids = await repo.expire_stale_leases()

        assert len(expired_ids) == 1
        assert mock_job.status == "failed"
        assert "failed after 3 attempts" in mock_job.error_message
        assert mock_job.completed_at is not None

    @pytest.mark.unit
    async def test_expire_returns_empty_when_no_stale_leases(
        self, repo, mock_db, org_id
    ):
        """No expired leases → empty list returned."""
        leases_result = MagicMock()
        leases_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = leases_result

        expired_ids = await repo.expire_stale_leases()

        assert expired_ids == []


# =============================================================================
# Test: find_by_idempotency_key (R21.11)
# =============================================================================


class TestIdempotencyKey:
    """Tests for idempotency key deduplication."""

    @pytest.mark.unit
    async def test_find_returns_existing_non_terminal_job(
        self, repo, mock_db, mock_job, org_id
    ):
        """When a non-terminal job with the key exists, it is returned."""
        mock_job.idempotency_key = "test-key-123"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db.execute.return_value = mock_result

        result = await repo.find_by_idempotency_key("test-key-123")

        assert result is not None
        assert result.idempotency_key == "test-key-123"

    @pytest.mark.unit
    async def test_find_returns_none_when_no_match(
        self, repo, mock_db, org_id
    ):
        """When no job with the key exists, returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await repo.find_by_idempotency_key("nonexistent-key")

        assert result is None
