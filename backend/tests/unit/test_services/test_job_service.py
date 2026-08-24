"""Unit tests for JobService — job submission, leasing, and lifecycle.

Tests cover:
    - submit_job creates a queued job
    - submit_job with idempotency_key returns existing non-terminal job
    - claim_job returns None when no jobs available
    - claim_job returns job + lease when a queued job exists
    - complete_job marks job completed and releases lease
    - fail_job marks job failed and releases lease
    - cancel_job cancels a job and expires active lease
    - cancel_job raises error for terminal jobs
    - heartbeat extends lease expiration
    - heartbeat rejects stale workers
    - expire_stale_leases delegates to repository
    - get_job returns a single job
    - list_jobs returns paginated results

Requirements: R21.1, R21.3, R21.4, R21.5, R21.8, R64.1, R64.3
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
# The ORM model chain (app.models -> app.db.base -> sqlalchemy) requires
# comprehensive mocking to avoid partial import failures in the test env.
# =============================================================================

# SQLAlchemy core mocks
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

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)

# Mock sqlalchemy.exc with a real IntegrityError class
_sa_exc_mock = ModuleType("sqlalchemy.exc")


class _IntegrityError(Exception):
    """Mock IntegrityError for testing."""
    def __init__(self, statement=None, params=None, orig=None):
        self.statement = statement
        self.params = params
        self.orig = orig
        super().__init__(str(orig) if orig else "IntegrityError")


_sa_exc_mock.IntegrityError = _IntegrityError  # type: ignore[attr-defined]
sys.modules.setdefault("sqlalchemy.exc", _sa_exc_mock)

# Mock app.db modules
_mock_db_module = ModuleType("app.db")
sys.modules.setdefault("app.db", _mock_db_module)

_mock_db_session = ModuleType("app.db.session")
_mock_db_session.get_db_session = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.session", _mock_db_session)

# Mock app.db.base with real-enough mixins for ORM models
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

# Mock app.db.tenant_scope
_mock_tenant_scope = ModuleType("app.db.tenant_scope")
_mock_tenant_scope.QUARANTINED_ORG_ID = UUID(  # type: ignore[attr-defined]
    "00000000-0000-0000-0000-000000000000"
)
_mock_tenant_scope.TenantScopedRepository = MagicMock()  # type: ignore[attr-defined]
_mock_tenant_scope.validate_org_id = MagicMock()  # type: ignore[attr-defined]
_mock_tenant_scope.tenant_filter = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.tenant_scope", _mock_tenant_scope)

# Mock app.models as a package with sub-modules
# Use a package-like ModuleType with __path__ so sub-imports resolve
_mock_models_pkg = ModuleType("app.models")
_mock_models_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.models", _mock_models_pkg)

# app.models.job — provide mock Job class
_mock_models_job = ModuleType("app.models.job")


class _MockJob:
    """Mock Job class for testing."""
    __tablename__ = "jobs"
    pass


_mock_models_job.Job = _MockJob  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.job", _mock_models_job)

# app.models.job_lease — provide mock JobLease class
_mock_models_job_lease = ModuleType("app.models.job_lease")


class _MockJobLease:
    """Mock JobLease class for testing."""
    __tablename__ = "job_leases"
    pass


_mock_models_job_lease.JobLease = _MockJobLease  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.job_lease", _mock_models_job_lease)

# app.models.talent and app.models.asset (not needed but prevent chain imports)
_mock_models_talent = ModuleType("app.models.talent")
_mock_models_talent.AiTalent = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.talent", _mock_models_talent)

_mock_models_asset = ModuleType("app.models.asset")
_mock_models_asset.Asset = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.asset", _mock_models_asset)

# Now import application modules
from app.schemas.job import JobCreate
from app.schemas.validation import JobType, WorkloadClass
from app.services.job_service import (
    JobNotCancellableError,
    JobService,
    NoActiveLeaseError,
    StaleWorkerError,
)


# =============================================================================
# Fixtures
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
    job.talent_id = kwargs.get("talent_id")
    job.user_id = kwargs.get("user_id")
    job.parameters = kwargs.get("parameters", {})
    job.progress_percent = kwargs.get("progress_percent")
    job.progress_message = kwargs.get("progress_message")
    job.error_message = kwargs.get("error_message")
    job.output_asset_ids = kwargs.get("output_asset_ids", [])
    job.cost_usd = kwargs.get("cost_usd")
    job.attempt_count = kwargs.get("attempt_count", 0)
    job.max_attempts = kwargs.get("max_attempts", 3)
    job.started_at = kwargs.get("started_at")
    job.completed_at = kwargs.get("completed_at")
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
    return AsyncMock()


@pytest.fixture
def job_service(mock_db):
    """Create a JobService with mocked repository."""
    with patch(
        "app.services.job_service.JobRepository"
    ) as MockRepo:
        mock_repo = AsyncMock()
        MockRepo.return_value = mock_repo
        service = JobService(db=mock_db, org_id=ORG_ID)
        service._repo = mock_repo
        yield service, mock_repo


# =============================================================================
# Tests: submit_job
# =============================================================================


@pytest.mark.unit
class TestSubmitJob:
    """Tests for JobService.submit_job."""

    @pytest.mark.asyncio
    async def test_submit_job_creates_queued_job(self, job_service):
        """Submit job creates a new job with status 'queued'."""
        service, mock_repo = job_service
        expected_job = _make_mock_job(status="queued")
        mock_repo.find_by_idempotency_key = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=expected_job)

        schema = JobCreate(
            job_type=JobType.IMAGE_GENERATION,
            priority=7,
            parameters={"prompt": "a sunset"},
        )

        result = await service.submit_job(schema, USER_ID)

        assert result == expected_job
        mock_repo.create.assert_called_once()
        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["status"] == "queued"
        assert call_kwargs["type"] == "image_generation"
        assert call_kwargs["priority"] == 7

    @pytest.mark.asyncio
    async def test_submit_job_with_idempotency_key_returns_existing(
        self, job_service
    ):
        """Submit with existing idempotency_key returns the existing job."""
        service, mock_repo = job_service
        existing_job = _make_mock_job(status="running")
        mock_repo.find_by_idempotency_key = AsyncMock(
            return_value=existing_job
        )

        schema = JobCreate(
            job_type=JobType.IMAGE_GENERATION,
            idempotency_key="dedup-key-123",
        )

        result = await service.submit_job(schema, USER_ID)

        assert result == existing_job
        mock_repo.find_by_idempotency_key.assert_called_once_with(
            "dedup-key-123"
        )
        mock_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_job_without_idempotency_key_skips_dedup(
        self, job_service
    ):
        """Submit without idempotency_key does not check for duplicates."""
        service, mock_repo = job_service
        expected_job = _make_mock_job()
        mock_repo.create = AsyncMock(return_value=expected_job)

        schema = JobCreate(
            job_type=JobType.VIDEO_GENERATION,
        )

        result = await service.submit_job(schema, USER_ID)

        assert result == expected_job
        mock_repo.find_by_idempotency_key.assert_not_called()


# =============================================================================
# Tests: claim_job
# =============================================================================


@pytest.mark.unit
class TestClaimJob:
    """Tests for JobService.claim_job."""

    @pytest.mark.asyncio
    async def test_claim_job_returns_none_when_no_jobs(self, job_service):
        """Claim returns None when no queued jobs are available."""
        service, mock_repo = job_service
        mock_repo.claim_next_job = AsyncMock(return_value=None)

        result = await service.claim_job(worker_identity="worker-1")

        assert result is None
        mock_repo.claim_next_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_claim_job_returns_job_and_lease(self, job_service):
        """Claim returns (Job, JobLease) when a job is available."""
        service, mock_repo = job_service
        mock_job = _make_mock_job(status="claimed")
        mock_lease = _make_mock_lease()
        mock_repo.claim_next_job = AsyncMock(
            return_value=(mock_job, mock_lease)
        )

        result = await service.claim_job(
            worker_identity="worker-1",
            lease_duration_seconds=600,
            workload_class="image_generation",
        )

        assert result is not None
        job, lease = result
        assert job == mock_job
        assert lease == mock_lease

        call_kwargs = mock_repo.claim_next_job.call_args.kwargs
        assert call_kwargs["worker_identity"] == "worker-1"
        assert call_kwargs["lease_duration"] == timedelta(seconds=600)
        assert call_kwargs["workload_class"] == "image_generation"


# =============================================================================
# Tests: heartbeat
# =============================================================================


@pytest.mark.unit
class TestHeartbeat:
    """Tests for JobService.heartbeat."""

    @pytest.mark.asyncio
    async def test_heartbeat_extends_lease(self, job_service):
        """Heartbeat successfully extends the lease expiration."""
        service, mock_repo = job_service
        mock_lease = _make_mock_lease()
        mock_repo.heartbeat = AsyncMock(return_value=mock_lease)

        result = await service.heartbeat(
            job_id=JOB_ID,
            lease_token=LEASE_TOKEN,
            progress_percent=50,
            progress_metadata={"message": "Halfway done"},
        )

        assert result == mock_lease
        mock_repo.heartbeat.assert_called_once_with(
            job_id=JOB_ID,
            lease_token=LEASE_TOKEN,
            progress_percent=50,
            progress_metadata={"message": "Halfway done"},
        )

    @pytest.mark.asyncio
    async def test_heartbeat_rejects_stale_worker(self, job_service):
        """Heartbeat raises StaleWorkerError for invalid lease token."""
        service, mock_repo = job_service
        mock_repo.heartbeat = AsyncMock(
            side_effect=ValueError(
                f"Invalid lease token for job {JOB_ID}. "
                "Heartbeat rejected — stale worker."
            )
        )

        with pytest.raises(StaleWorkerError):
            await service.heartbeat(
                job_id=JOB_ID,
                lease_token=uuid4(),  # Wrong token
            )

    @pytest.mark.asyncio
    async def test_heartbeat_raises_no_active_lease(self, job_service):
        """Heartbeat raises NoActiveLeaseError when no lease exists."""
        service, mock_repo = job_service
        mock_repo.heartbeat = AsyncMock(
            side_effect=ValueError(
                f"No active lease found for job {JOB_ID}. "
                "The lease may have expired."
            )
        )

        with pytest.raises(NoActiveLeaseError):
            await service.heartbeat(
                job_id=JOB_ID,
                lease_token=LEASE_TOKEN,
            )


# =============================================================================
# Tests: complete_job
# =============================================================================


@pytest.mark.unit
class TestCompleteJob:
    """Tests for JobService.complete_job."""

    @pytest.mark.asyncio
    async def test_complete_job_marks_completed(self, job_service):
        """Complete job marks status as 'completed' and releases lease."""
        service, mock_repo = job_service
        completed_job = _make_mock_job(status="completed")
        mock_repo.release_lease = AsyncMock(return_value=completed_job)

        result = await service.complete_job(
            job_id=JOB_ID,
            lease_token=LEASE_TOKEN,
            output_asset_ids=[uuid4()],
        )

        assert result == completed_job
        mock_repo.release_lease.assert_called_once()
        call_kwargs = mock_repo.release_lease.call_args.kwargs
        assert call_kwargs["final_status"] == "completed"

    @pytest.mark.asyncio
    async def test_complete_job_rejects_stale_worker(self, job_service):
        """Complete rejects stale worker with wrong token."""
        service, mock_repo = job_service
        mock_repo.release_lease = AsyncMock(
            side_effect=ValueError(
                f"Invalid lease token for job {JOB_ID}. "
                "Only the current lease holder may update job state."
            )
        )

        with pytest.raises(StaleWorkerError):
            await service.complete_job(
                job_id=JOB_ID,
                lease_token=uuid4(),
            )


# =============================================================================
# Tests: fail_job
# =============================================================================


@pytest.mark.unit
class TestFailJob:
    """Tests for JobService.fail_job."""

    @pytest.mark.asyncio
    async def test_fail_job_marks_failed(self, job_service):
        """Fail job marks status as 'failed' and records error message."""
        service, mock_repo = job_service
        failed_job = _make_mock_job(
            status="failed",
            error_message="GPU OOM",
        )
        mock_repo.release_lease = AsyncMock(return_value=failed_job)

        result = await service.fail_job(
            job_id=JOB_ID,
            lease_token=LEASE_TOKEN,
            error_message="GPU OOM",
        )

        assert result == failed_job
        call_kwargs = mock_repo.release_lease.call_args.kwargs
        assert call_kwargs["final_status"] == "failed"
        assert call_kwargs["error_message"] == "GPU OOM"


# =============================================================================
# Tests: cancel_job
# =============================================================================


@pytest.mark.unit
class TestCancelJob:
    """Tests for JobService.cancel_job."""

    @pytest.mark.asyncio
    async def test_cancel_job_cancels_queued_job(self, job_service):
        """Cancel a queued job without an active lease."""
        service, mock_repo = job_service
        queued_job = _make_mock_job(status="queued")
        cancelled_job = _make_mock_job(status="cancelled")

        mock_repo.get_by_id = AsyncMock(return_value=queued_job)
        mock_repo._get_active_lease = AsyncMock(return_value=None)
        mock_repo.update_status = AsyncMock(return_value=cancelled_job)

        result = await service.cancel_job(JOB_ID)

        assert result == cancelled_job
        mock_repo.update_status.assert_called_once_with(
            job_id=JOB_ID,
            status="cancelled",
        )

    @pytest.mark.asyncio
    async def test_cancel_job_expires_active_lease(self, job_service):
        """Cancel a claimed job expires the active lease."""
        service, mock_repo = job_service
        claimed_job = _make_mock_job(status="claimed")
        cancelled_job = _make_mock_job(status="cancelled")
        mock_lease = _make_mock_lease()

        mock_repo.get_by_id = AsyncMock(return_value=claimed_job)
        mock_repo._get_active_lease = AsyncMock(return_value=mock_lease)
        mock_repo.update_status = AsyncMock(return_value=cancelled_job)

        result = await service.cancel_job(JOB_ID)

        assert result == cancelled_job
        # Verify the lease_expiration was set to approximately now
        assert mock_lease.lease_expiration <= datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_cancel_job_raises_for_terminal_status(self, job_service):
        """Cancel raises JobNotCancellableError for completed jobs."""
        service, mock_repo = job_service
        completed_job = _make_mock_job(status="completed")
        mock_repo.get_by_id = AsyncMock(return_value=completed_job)

        with pytest.raises(JobNotCancellableError):
            await service.cancel_job(JOB_ID)

    @pytest.mark.asyncio
    async def test_cancel_job_raises_for_failed_status(self, job_service):
        """Cancel raises JobNotCancellableError for failed jobs."""
        service, mock_repo = job_service
        failed_job = _make_mock_job(status="failed")
        mock_repo.get_by_id = AsyncMock(return_value=failed_job)

        with pytest.raises(JobNotCancellableError):
            await service.cancel_job(JOB_ID)


# =============================================================================
# Tests: expire_stale_leases
# =============================================================================


@pytest.mark.unit
class TestExpireStaleLeases:
    """Tests for JobService.expire_stale_leases."""

    @pytest.mark.asyncio
    async def test_expire_stale_leases_delegates_to_repo(self, job_service):
        """Expire stale leases delegates to repository and returns IDs."""
        service, mock_repo = job_service
        expired_ids = [uuid4(), uuid4()]
        mock_repo.expire_stale_leases = AsyncMock(return_value=expired_ids)

        result = await service.expire_stale_leases()

        assert result == expired_ids
        mock_repo.expire_stale_leases.assert_called_once()

    @pytest.mark.asyncio
    async def test_expire_stale_leases_returns_empty_list(self, job_service):
        """Returns empty list when no leases are expired."""
        service, mock_repo = job_service
        mock_repo.expire_stale_leases = AsyncMock(return_value=[])

        result = await service.expire_stale_leases()

        assert result == []


# =============================================================================
# Tests: get_job and list_jobs
# =============================================================================


@pytest.mark.unit
class TestGetAndList:
    """Tests for JobService.get_job and list_jobs."""

    @pytest.mark.asyncio
    async def test_get_job_returns_single_job(self, job_service):
        """get_job returns the job from the repository."""
        service, mock_repo = job_service
        mock_job = _make_mock_job()
        mock_repo.get_by_id = AsyncMock(return_value=mock_job)

        result = await service.get_job(JOB_ID)

        assert result == mock_job
        mock_repo.get_by_id.assert_called_once_with(JOB_ID)

    @pytest.mark.asyncio
    async def test_list_jobs_returns_paginated_results(self, job_service):
        """list_jobs returns items and total count."""
        service, mock_repo = job_service
        jobs = [_make_mock_job(), _make_mock_job(job_id=uuid4())]
        mock_repo.list_all = AsyncMock(return_value=(jobs, 2))

        items, total = await service.list_jobs(
            limit=10, offset=0, status="queued"
        )

        assert items == jobs
        assert total == 2
        mock_repo.list_all.assert_called_once_with(
            limit=10,
            offset=0,
            status="queued",
            job_type=None,
            talent_id=None,
        )

    @pytest.mark.asyncio
    async def test_list_jobs_with_all_filters(self, job_service):
        """list_jobs passes all filters to repository."""
        service, mock_repo = job_service
        talent_id = uuid4()
        mock_repo.list_all = AsyncMock(return_value=([], 0))

        await service.list_jobs(
            limit=50,
            offset=10,
            status="running",
            job_type="lora_training",
            talent_id=talent_id,
        )

        mock_repo.list_all.assert_called_once_with(
            limit=50,
            offset=10,
            status="running",
            job_type="lora_training",
            talent_id=talent_id,
        )
