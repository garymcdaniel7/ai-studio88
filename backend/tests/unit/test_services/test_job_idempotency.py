"""Unit tests for job idempotency, cancellation signal, and stale worker rejection.

Focused tests for Task 7.3 requirements:
    - R21.11: Idempotency key deduplication (including race condition handling)
    - R21.6: Cancellation revokes lease (signal worker to stop via poll)
    - R21.12: Stale worker rejection on complete/fail/heartbeat
    - R21.13: Progress reporting with metadata

Requirements: R21.6, R21.11, R21.12, R21.13
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# =============================================================================
# Mock heavy dependencies before importing application modules.
# =============================================================================

_sa_mock = MagicMock()
_sa_mock.DateTime = MagicMock
_sa_mock.Float = MagicMock
_sa_mock.Integer = MagicMock
_sa_mock.String = MagicMock
_sa_mock.Text = MagicMock
_sa_mock.Boolean = MagicMock
_sa_mock.ForeignKey = MagicMock
_sa_mock.Index = MagicMock
_sa_mock.func = MagicMock()
_sa_mock.select = MagicMock()
_sa_mock.update = MagicMock()

_sa_orm_mock = MagicMock()
_sa_orm_mock.Mapped = MagicMock
_sa_orm_mock.mapped_column = MagicMock(return_value=None)
_sa_orm_mock.relationship = MagicMock(return_value=None)
_sa_orm_mock.DeclarativeBase = type("DeclarativeBase", (), {})

_sa_dialects_pg_mock = MagicMock()
_sa_dialects_pg_mock.UUID = MagicMock
_sa_dialects_pg_mock.JSONB = MagicMock
_sa_dialects_pg_mock.ARRAY = MagicMock

_sa_ext_asyncio_mock = MagicMock()
_sa_ext_asyncio_mock.AsyncEngine = MagicMock
_sa_ext_asyncio_mock.AsyncSession = MagicMock
_sa_ext_asyncio_mock.async_sessionmaker = MagicMock
_sa_ext_asyncio_mock.create_async_engine = MagicMock

_sa_exc_mock = MagicMock()


class _MockIntegrityError(Exception):
    """Mock IntegrityError that behaves like a real exception."""

    def __init__(self, statement=None, params=None, orig=None):
        self.statement = statement
        self.params = params
        self.orig = orig
        msg = str(orig) if orig else "IntegrityError"
        super().__init__(msg)


_sa_exc_mock.IntegrityError = _MockIntegrityError

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)
sys.modules.setdefault("sqlalchemy.exc", _sa_exc_mock)

# Retrieve the actual IntegrityError from whatever ended up in sys.modules.
# When another test file runs first and registers a different mock, we use that.
_RealIntegrityError = sys.modules["sqlalchemy.exc"].IntegrityError

# Mock app.db modules
_mock_db_module = ModuleType("app.db")
sys.modules.setdefault("app.db", _mock_db_module)

_mock_db_session = ModuleType("app.db.session")
_mock_db_session.get_db_session = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.session", _mock_db_session)

_mock_db_base = ModuleType("app.db.base")


class _MockBase:
    pass


class _MockTimestampMixin:
    pass


class _MockUUIDMixin:
    pass


class _MockTenantMixin:
    pass


class _MockSoftDeleteMixin:
    pass


_mock_db_base.Base = _MockBase  # type: ignore[attr-defined]
_mock_db_base.TimestampMixin = _MockTimestampMixin  # type: ignore[attr-defined]
_mock_db_base.UUIDMixin = _MockUUIDMixin  # type: ignore[attr-defined]
_mock_db_base.TenantMixin = _MockTenantMixin  # type: ignore[attr-defined]
_mock_db_base.SoftDeleteMixin = _MockSoftDeleteMixin  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.base", _mock_db_base)

_mock_tenant_scope = ModuleType("app.db.tenant_scope")
_mock_tenant_scope.QUARANTINED_ORG_ID = UUID(  # type: ignore[attr-defined]
    "00000000-0000-0000-0000-000000000000"
)
_mock_tenant_scope.TenantScopedRepository = MagicMock()  # type: ignore[attr-defined]
_mock_tenant_scope.validate_org_id = MagicMock()  # type: ignore[attr-defined]
_mock_tenant_scope.tenant_filter = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.tenant_scope", _mock_tenant_scope)

_mock_models_pkg = ModuleType("app.models")
_mock_models_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.models", _mock_models_pkg)

_mock_models_job = ModuleType("app.models.job")


class _MockJob:
    __tablename__ = "jobs"
    pass


_mock_models_job.Job = _MockJob  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.job", _mock_models_job)

_mock_models_job_lease = ModuleType("app.models.job_lease")


class _MockJobLease:
    __tablename__ = "job_leases"
    pass


_mock_models_job_lease.JobLease = _MockJobLease  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.job_lease", _mock_models_job_lease)

_mock_models_talent = ModuleType("app.models.talent")
_mock_models_talent.AiTalent = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.talent", _mock_models_talent)

_mock_models_asset = ModuleType("app.models.asset")
_mock_models_asset.Asset = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.asset", _mock_models_asset)

# Now import application modules
from sqlalchemy.exc import IntegrityError

from app.schemas.job import JobCreate
from app.schemas.validation import JobType
from app.services.job_service import (
    JobNotCancellableError,
    JobService,
    NoActiveLeaseError,
    StaleWorkerError,
)


# =============================================================================
# Constants
# =============================================================================

ORG_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")
JOB_ID = UUID("33333333-3333-3333-3333-333333333333")
LEASE_TOKEN = UUID("44444444-4444-4444-4444-444444444444")


def _make_mock_job(
    job_id: UUID = JOB_ID,
    status: str = "queued",
    job_type: str = "image_generation",
    org_id: UUID = ORG_ID,
    **kwargs,
) -> MagicMock:
    """Create a mock Job ORM instance."""
    job = MagicMock()
    job.id = job_id
    job.org_id = org_id
    job.status = status
    job.job_type = job_type
    job.priority = kwargs.get("priority", 5)
    job.idempotency_key = kwargs.get("idempotency_key")
    job.workload_class = kwargs.get("workload_class")
    job.max_duration_seconds = kwargs.get("max_duration_seconds", 1800)
    job.attempt_count = kwargs.get("attempt_count", 0)
    job.max_attempts = kwargs.get("max_attempts", 3)
    job.created_at = kwargs.get("created_at", datetime.now(UTC))
    job.updated_at = kwargs.get("updated_at", datetime.now(UTC))
    return job


def _make_mock_lease(
    job_id: UUID = JOB_ID,
    lease_token: UUID = LEASE_TOKEN,
    worker_identity: str = "worker-1",
) -> MagicMock:
    """Create a mock JobLease ORM instance."""
    lease = MagicMock()
    lease.id = uuid4()
    lease.job_id = job_id
    lease.org_id = ORG_ID
    lease.worker_identity = worker_identity
    lease.lease_token = lease_token
    lease.lease_expiration = datetime.now(UTC) + timedelta(minutes=30)
    lease.heartbeat_at = datetime.now(UTC)
    return lease


@pytest.fixture
def mock_db():
    """Create a mock async DB session."""
    db = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def job_service(mock_db):
    """Create a JobService with mocked repository."""
    with patch("app.services.job_service.JobRepository") as MockRepo:
        mock_repo = AsyncMock()
        MockRepo.return_value = mock_repo
        service = JobService(db=mock_db, org_id=ORG_ID)
        service._repo = mock_repo
        yield service, mock_repo


# =============================================================================
# Tests: Idempotency Key Race Condition (R21.11)
# =============================================================================


@pytest.mark.unit
class TestIdempotencyRaceCondition:
    """Tests for idempotency_key race condition handling in submit_job.

    When two concurrent requests with the same idempotency_key both pass
    the initial dedup check, the DB unique index catches the duplicate.
    The service handles this IntegrityError gracefully (R21.11).
    """

    @pytest.mark.asyncio
    async def test_integrity_error_resolved_by_refetch(self, job_service):
        """IntegrityError on duplicate key is resolved by re-fetching.

        Simulates: Request A inserts first. Request B's find returns None
        (race window), then B's insert hits the unique index. B catches
        IntegrityError, rolls back, and returns A's row.
        """
        service, mock_repo = job_service
        existing_job = _make_mock_job(
            status="queued", idempotency_key="race-key"
        )

        # First call: no existing job found (race window)
        # Second call (after rollback): returns the existing job
        mock_repo.find_by_idempotency_key = AsyncMock(
            side_effect=[None, existing_job]
        )
        # create raises IntegrityError (unique constraint violation)
        mock_repo.create = AsyncMock(
            side_effect=_RealIntegrityError(
                "INSERT INTO jobs",
                {},
                Exception(
                    "duplicate key value violates unique constraint "
                    '"ix_jobs_org_idempotency_key"'
                ),
            )
        )

        schema = JobCreate(
            job_type=JobType.IMAGE_GENERATION,
            idempotency_key="race-key",
        )

        result = await service.submit_job(schema, USER_ID)

        assert result == existing_job
        # Verify rollback was called
        service._db.rollback.assert_called_once()
        # Verify re-fetch happened
        assert mock_repo.find_by_idempotency_key.call_count == 2

    @pytest.mark.asyncio
    async def test_non_idempotency_integrity_error_reraises(self, job_service):
        """IntegrityError unrelated to idempotency_key is re-raised."""
        service, mock_repo = job_service
        mock_repo.find_by_idempotency_key = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(
            side_effect=_RealIntegrityError(
                "INSERT INTO jobs",
                {},
                Exception("violates foreign key constraint"),
            )
        )

        schema = JobCreate(
            job_type=JobType.IMAGE_GENERATION,
            idempotency_key="some-key",
        )

        with pytest.raises(_RealIntegrityError):
            await service.submit_job(schema, USER_ID)

    @pytest.mark.asyncio
    async def test_integrity_error_without_idempotency_key_reraises(
        self, job_service
    ):
        """IntegrityError without idempotency_key is always re-raised."""
        service, mock_repo = job_service
        mock_repo.create = AsyncMock(
            side_effect=_RealIntegrityError(
                "INSERT INTO jobs",
                {},
                Exception("some other constraint"),
            )
        )

        schema = JobCreate(
            job_type=JobType.IMAGE_GENERATION,
            # No idempotency_key set
        )

        with pytest.raises(_RealIntegrityError):
            await service.submit_job(schema, USER_ID)


# =============================================================================
# Tests: Cancellation Expires Lease (R21.6)
# =============================================================================


@pytest.mark.unit
class TestCancellationSignal:
    """Tests proving cancellation expires the active lease.

    Per R21.6: "cancellation of a leased job SHALL revoke the lease and
    signal the worker to stop." In a heartbeat-polling system, expiring
    the lease IS the signal — the worker discovers it on next heartbeat.
    """

    @pytest.mark.asyncio
    async def test_cancel_expires_lease_so_next_heartbeat_fails(
        self, job_service
    ):
        """Cancelling a claimed job sets lease_expiration <= now().

        After cancellation, any heartbeat or complete attempt by the
        worker will find no active lease and be rejected (stale worker).
        """
        service, mock_repo = job_service
        claimed_job = _make_mock_job(status="claimed")
        cancelled_job = _make_mock_job(status="cancelled")
        mock_lease = _make_mock_lease()

        # Lease expiration is in the future before cancellation
        assert mock_lease.lease_expiration > datetime.now(UTC)

        mock_repo.get_by_id = AsyncMock(return_value=claimed_job)
        mock_repo._get_active_lease = AsyncMock(return_value=mock_lease)
        mock_repo.update_status = AsyncMock(return_value=cancelled_job)

        result = await service.cancel_job(JOB_ID)

        assert result == cancelled_job
        # The lease_expiration was set to now (or earlier), meaning
        # the worker's next heartbeat will find no active lease
        assert mock_lease.lease_expiration <= datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_cancel_queued_job_without_lease_succeeds(
        self, job_service
    ):
        """Cancelling a queued job (no lease) just sets status cancelled."""
        service, mock_repo = job_service
        queued_job = _make_mock_job(status="queued")
        cancelled_job = _make_mock_job(status="cancelled")

        mock_repo.get_by_id = AsyncMock(return_value=queued_job)
        mock_repo._get_active_lease = AsyncMock(return_value=None)
        mock_repo.update_status = AsyncMock(return_value=cancelled_job)

        result = await service.cancel_job(JOB_ID)

        assert result == cancelled_job
        mock_repo.update_status.assert_called_once_with(
            job_id=JOB_ID, status="cancelled"
        )

    @pytest.mark.asyncio
    async def test_cancel_terminal_job_raises_error(self, job_service):
        """Cannot cancel a completed/failed/cancelled job."""
        service, mock_repo = job_service
        for terminal_status in ("completed", "failed", "cancelled"):
            terminal_job = _make_mock_job(status=terminal_status)
            mock_repo.get_by_id = AsyncMock(return_value=terminal_job)

            with pytest.raises(JobNotCancellableError):
                await service.cancel_job(JOB_ID)


# =============================================================================
# Tests: Stale Worker Rejection (R21.12)
# =============================================================================


@pytest.mark.unit
class TestStaleWorkerRejection:
    """Tests proving stale workers are rejected on complete/fail/heartbeat.

    Per R21.12: "The Platform SHALL reject stale workers attempting to
    write results for a job whose lease they no longer hold."
    """

    @pytest.mark.asyncio
    async def test_complete_rejects_wrong_lease_token(self, job_service):
        """complete_job with wrong token raises StaleWorkerError."""
        service, mock_repo = job_service
        mock_repo.release_lease = AsyncMock(
            side_effect=ValueError(
                f"Invalid lease token for job {JOB_ID}. "
                "Only the current lease holder may update job state."
            )
        )

        with pytest.raises(StaleWorkerError) as exc_info:
            await service.complete_job(
                job_id=JOB_ID,
                lease_token=uuid4(),  # Wrong token
            )

        assert "STALE_WORKER" == exc_info.value.code

    @pytest.mark.asyncio
    async def test_fail_rejects_wrong_lease_token(self, job_service):
        """fail_job with wrong token raises StaleWorkerError."""
        service, mock_repo = job_service
        mock_repo.release_lease = AsyncMock(
            side_effect=ValueError(
                f"Invalid lease token for job {JOB_ID}. "
                "Only the current lease holder may update job state."
            )
        )

        with pytest.raises(StaleWorkerError) as exc_info:
            await service.fail_job(
                job_id=JOB_ID,
                lease_token=uuid4(),
                error_message="GPU OOM",
            )

        assert "STALE_WORKER" == exc_info.value.code

    @pytest.mark.asyncio
    async def test_heartbeat_rejects_wrong_lease_token(self, job_service):
        """heartbeat with wrong token raises StaleWorkerError."""
        service, mock_repo = job_service
        mock_repo.heartbeat = AsyncMock(
            side_effect=ValueError(
                f"Invalid lease token for job {JOB_ID}. "
                "Heartbeat rejected — stale worker."
            )
        )

        with pytest.raises(StaleWorkerError) as exc_info:
            await service.heartbeat(
                job_id=JOB_ID,
                lease_token=uuid4(),
            )

        assert "STALE_WORKER" == exc_info.value.code

    @pytest.mark.asyncio
    async def test_complete_raises_no_active_lease(self, job_service):
        """complete_job with expired lease raises NoActiveLeaseError."""
        service, mock_repo = job_service
        mock_repo.release_lease = AsyncMock(
            side_effect=ValueError(
                f"No active lease found for job {JOB_ID}. "
                "The lease may have expired."
            )
        )

        with pytest.raises(NoActiveLeaseError) as exc_info:
            await service.complete_job(
                job_id=JOB_ID,
                lease_token=LEASE_TOKEN,
            )

        assert "NO_ACTIVE_LEASE" == exc_info.value.code


# =============================================================================
# Tests: Progress Reporting with Metadata (R21.13)
# =============================================================================


@pytest.mark.unit
class TestProgressMetadata:
    """Tests for progress reporting including structured metadata.

    Per R21.13: "The Platform SHALL support progress reporting from workers:
    progress_percent (0-100), progress_message, and optional structured
    progress_metadata."
    """

    @pytest.mark.asyncio
    async def test_heartbeat_passes_metadata_to_repo(self, job_service):
        """Heartbeat passes progress_metadata through to the repository."""
        service, mock_repo = job_service
        mock_lease = _make_mock_lease()
        mock_repo.heartbeat = AsyncMock(return_value=mock_lease)

        metadata = {"step": "denoising", "current_step": 15, "total_steps": 20}

        await service.heartbeat(
            job_id=JOB_ID,
            lease_token=LEASE_TOKEN,
            progress_percent=75,
            progress_message="Denoising step 15/20",
            progress_metadata=metadata,
        )

        mock_repo.heartbeat.assert_called_once_with(
            job_id=JOB_ID,
            lease_token=LEASE_TOKEN,
            progress_percent=75,
            progress_message="Denoising step 15/20",
            progress_metadata=metadata,
        )

    @pytest.mark.asyncio
    async def test_heartbeat_without_metadata_passes_none(self, job_service):
        """Heartbeat without metadata passes None for progress_metadata."""
        service, mock_repo = job_service
        mock_lease = _make_mock_lease()
        mock_repo.heartbeat = AsyncMock(return_value=mock_lease)

        await service.heartbeat(
            job_id=JOB_ID,
            lease_token=LEASE_TOKEN,
            progress_percent=50,
        )

        mock_repo.heartbeat.assert_called_once_with(
            job_id=JOB_ID,
            lease_token=LEASE_TOKEN,
            progress_percent=50,
            progress_message=None,
            progress_metadata=None,
        )
