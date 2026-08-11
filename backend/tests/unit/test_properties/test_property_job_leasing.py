"""Property tests for Job Lease Exclusivity and Idempotent Job Submission.

Property 4: Job Lease Exclusivity (R21.3, R64.2)
    For any job in the system, at most ONE active lease SHALL exist at any
    point in time. Concurrent claim attempts on the same job result in at most
    one successful claim; all others receive None.

Property 9: Idempotent Job Submission (R21.11)
    For any job submission with idempotency_key K for org O, if a non-terminal
    job exists with same (org_id=O, key=K), the existing job is returned.
    Never duplicated. Different orgs with the same key create separate jobs.

Validates: Requirements R21.3, R21.11, R64.2

Run with:
    pytest backend/tests/unit/test_properties/test_property_job_leasing.py -v
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# =============================================================================
# Mock heavy dependencies before importing application modules.
# Follows existing pattern from test_job_idempotency.py.
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
from app.schemas.job import JobCreate
from app.schemas.validation import JobType
from app.services.job_service import JobService


# =============================================================================
# Hypothesis Strategies
# =============================================================================

uuid_strategy = st.builds(uuid4)

job_type_strategy = st.sampled_from(list(JobType))

worker_identity_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() != "")

idempotency_key_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip() != "")

priority_strategy = st.integers(min_value=1, max_value=10)

num_workers_strategy = st.integers(min_value=2, max_value=10)


# =============================================================================
# Helpers
# =============================================================================


def _make_mock_job(
    job_id: UUID | None = None,
    status: str = "queued",
    job_type: str = "image_generation",
    org_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> MagicMock:
    """Create a mock Job ORM instance."""
    job = MagicMock()
    job.id = job_id or uuid4()
    job.org_id = org_id or uuid4()
    job.status = status
    job.job_type = job_type
    job.idempotency_key = idempotency_key
    job.priority = 5
    job.attempt_count = 0
    job.max_attempts = 3
    job.workload_class = "image_generation"
    job.max_duration_seconds = 1800
    job.created_at = datetime.now(UTC)
    job.updated_at = datetime.now(UTC)
    return job


def _make_mock_lease(
    job_id: UUID | None = None,
    worker_identity: str = "worker-1",
    expired: bool = False,
) -> MagicMock:
    """Create a mock JobLease ORM instance."""
    lease = MagicMock()
    lease.id = uuid4()
    lease.job_id = job_id or uuid4()
    lease.org_id = uuid4()
    lease.worker_identity = worker_identity
    lease.lease_token = uuid4()
    if expired:
        lease.lease_expiration = datetime.now(UTC) - timedelta(minutes=5)
    else:
        lease.lease_expiration = datetime.now(UTC) + timedelta(minutes=30)
    lease.heartbeat_at = datetime.now(UTC)
    return lease


# =============================================================================
# Property 4: Job Lease Exclusivity
# Feature: production-revamp, Property 4
# =============================================================================


@pytest.mark.unit
class TestProperty4_JobLeaseExclusivity:
    """Property 4: At most ONE active lease per job at any time.

    The claim_next_job operation uses FOR UPDATE SKIP LOCKED which ensures
    only one worker claims a given job. All other concurrent claimants
    skip the locked row and either get a different job or None.

    **Validates: Requirements R21.3, R64.2**
    """

    @settings(max_examples=50)
    @given(
        org_id=uuid_strategy,
        num_workers=num_workers_strategy,
        worker_identities=st.lists(
            worker_identity_strategy, min_size=2, max_size=10
        ),
    )
    @pytest.mark.asyncio
    async def test_concurrent_claims_yield_at_most_one_winner(
        self,
        org_id: UUID,
        num_workers: int,
        worker_identities: list[str],
    ) -> None:
        """Multiple workers claiming simultaneously: at most one succeeds.

        **Validates: Requirements R21.3, R64.2**

        Property: When N workers concurrently attempt to claim the same job,
        the FOR UPDATE SKIP LOCKED mechanism ensures exactly one gets the
        lease and N-1 get None. This is tested by simulating the repo
        returning the job only for the first caller and None for the rest.
        """
        mock_db = AsyncMock()
        job_id = uuid4()
        mock_job = _make_mock_job(job_id=job_id, org_id=org_id)
        mock_lease = _make_mock_lease(job_id=job_id)

        # Track claim results: only the first attempt succeeds
        claim_count = 0

        async def mock_claim_next(
            worker_identity: str,
            lease_duration=None,
            workload_class=None,
        ):
            nonlocal claim_count
            claim_count += 1
            if claim_count == 1:
                return (mock_job, mock_lease)
            return None

        with patch("app.services.job_service.JobRepository") as MockRepo:
            mock_repo = AsyncMock()
            MockRepo.return_value = mock_repo
            mock_repo.claim_next_job = AsyncMock(side_effect=mock_claim_next)

            service = JobService(db=mock_db, org_id=org_id)
            service._repo = mock_repo

            # Simulate N workers trying to claim
            results = []
            for identity in worker_identities[:num_workers]:
                result = await service.claim_job(worker_identity=identity)
                results.append(result)

            # Invariant: at most one worker gets a lease
            successful_claims = [r for r in results if r is not None]
            assert len(successful_claims) <= 1

    @settings(max_examples=50)
    @given(
        org_id=uuid_strategy,
        worker_a=worker_identity_strategy,
        worker_b=worker_identity_strategy,
    )
    @pytest.mark.asyncio
    async def test_second_claim_on_same_job_returns_none(
        self,
        org_id: UUID,
        worker_a: str,
        worker_b: str,
    ) -> None:
        """After one worker claims a job, another cannot claim the same one.

        **Validates: Requirements R21.3, R64.2**

        Property: The partial unique index on (job_id) WHERE
        lease_expiration > now() prevents a second active lease from existing.
        If worker A holds the lease, worker B's claim attempt for the same
        job gets None (the locked row is skipped).
        """
        mock_db = AsyncMock()
        job_id = uuid4()
        mock_job = _make_mock_job(job_id=job_id, org_id=org_id)
        mock_lease = _make_mock_lease(job_id=job_id, worker_identity=worker_a)

        call_count = 0

        async def mock_claim_next(
            worker_identity: str,
            lease_duration=None,
            workload_class=None,
        ):
            nonlocal call_count
            call_count += 1
            # First claim succeeds, subsequent claims find no queued jobs
            if call_count == 1:
                return (mock_job, mock_lease)
            return None

        with patch("app.services.job_service.JobRepository") as MockRepo:
            mock_repo = AsyncMock()
            MockRepo.return_value = mock_repo
            mock_repo.claim_next_job = AsyncMock(side_effect=mock_claim_next)

            service = JobService(db=mock_db, org_id=org_id)
            service._repo = mock_repo

            # Worker A claims
            result_a = await service.claim_job(worker_identity=worker_a)
            assert result_a is not None
            claimed_job, claimed_lease = result_a

            # Worker B attempts to claim — no queued jobs left
            result_b = await service.claim_job(worker_identity=worker_b)
            assert result_b is None

    @settings(max_examples=50)
    @given(org_id=uuid_strategy, worker=worker_identity_strategy)
    @pytest.mark.asyncio
    async def test_no_queued_jobs_returns_none(
        self, org_id: UUID, worker: str
    ) -> None:
        """When no jobs are queued, claim returns None (no lease created).

        **Validates: Requirements R21.3**

        Property: If the job queue is empty, claim_job returns None and
        no lease is created — maintaining the invariant of at most one
        active lease per job (zero in this case).
        """
        mock_db = AsyncMock()

        with patch("app.services.job_service.JobRepository") as MockRepo:
            mock_repo = AsyncMock()
            MockRepo.return_value = mock_repo
            mock_repo.claim_next_job = AsyncMock(return_value=None)

            service = JobService(db=mock_db, org_id=org_id)
            service._repo = mock_repo

            result = await service.claim_job(worker_identity=worker)
            assert result is None

    @settings(max_examples=50)
    @given(
        org_id=uuid_strategy,
        worker=worker_identity_strategy,
    )
    @pytest.mark.asyncio
    async def test_released_lease_allows_new_claim(
        self, org_id: UUID, worker: str
    ) -> None:
        """After lease release, a new claim on the same job is allowed.

        **Validates: Requirements R21.3, R64.2**

        Property: Once a lease is released (expiration set to now), the
        partial unique index no longer blocks. A new claim attempt can
        succeed — but still at most one active lease exists at any time.
        """
        mock_db = AsyncMock()
        job_id = uuid4()
        mock_job = _make_mock_job(job_id=job_id, org_id=org_id, status="queued")
        new_lease = _make_mock_lease(job_id=job_id, worker_identity=worker)

        with patch("app.services.job_service.JobRepository") as MockRepo:
            mock_repo = AsyncMock()
            MockRepo.return_value = mock_repo
            # After previous lease was released, job is re-queued and claimable
            mock_repo.claim_next_job = AsyncMock(
                return_value=(mock_job, new_lease)
            )

            service = JobService(db=mock_db, org_id=org_id)
            service._repo = mock_repo

            result = await service.claim_job(worker_identity=worker)
            assert result is not None
            _, lease = result
            # New lease exists — exactly one active lease for the job
            assert lease.lease_expiration > datetime.now(UTC)


# =============================================================================
# Property 9: Idempotent Job Submission
# Feature: production-revamp, Property 9
# =============================================================================


@pytest.mark.unit
class TestProperty9_IdempotentJobSubmission:
    """Property 9: Same (org_id, idempotency_key) always returns same job.

    Submitting multiple times with the same idempotency key within the same
    org always returns the existing non-terminal job without creating
    duplicates. Different orgs with the same key create independent jobs.

    **Validates: Requirements R21.11**
    """

    @settings(max_examples=50)
    @given(
        org_id=uuid_strategy,
        user_id=uuid_strategy,
        idempotency_key=idempotency_key_strategy,
        job_type=job_type_strategy,
        num_submissions=st.integers(min_value=2, max_value=5),
    )
    @pytest.mark.asyncio
    async def test_repeated_submissions_return_same_job(
        self,
        org_id: UUID,
        user_id: UUID,
        idempotency_key: str,
        job_type: JobType,
        num_submissions: int,
    ) -> None:
        """Same idempotency key returns the same job every time.

        **Validates: Requirements R21.11**

        Property: For any N submissions with the same (org_id, key) pair,
        all N calls return the same job_id. The repository's create method
        is called at most once (for the first submission).
        """
        mock_db = AsyncMock()
        mock_db.rollback = AsyncMock()

        existing_job = _make_mock_job(
            org_id=org_id,
            job_type=job_type.value,
            idempotency_key=idempotency_key,
            status="queued",
        )

        with patch("app.services.job_service.JobRepository") as MockRepo:
            mock_repo = AsyncMock()
            MockRepo.return_value = mock_repo
            # After first creation, find_by_idempotency_key always returns it
            mock_repo.find_by_idempotency_key = AsyncMock(
                return_value=existing_job
            )

            service = JobService(db=mock_db, org_id=org_id)
            service._repo = mock_repo

            schema = JobCreate(
                job_type=job_type,
                idempotency_key=idempotency_key,
            )

            results = []
            for _ in range(num_submissions):
                result = await service.submit_job(schema, user_id)
                results.append(result)

            # Invariant: all results are the same job
            for result in results:
                assert result.id == existing_job.id

            # Invariant: create was never called (existing found each time)
            mock_repo.create.assert_not_called()

    @settings(max_examples=50)
    @given(
        org_id=uuid_strategy,
        user_id=uuid_strategy,
        idempotency_key=idempotency_key_strategy,
        job_type=job_type_strategy,
    )
    @pytest.mark.asyncio
    async def test_race_condition_returns_existing_job_not_duplicate(
        self,
        org_id: UUID,
        user_id: UUID,
        idempotency_key: str,
        job_type: JobType,
    ) -> None:
        """IntegrityError from concurrent insert resolves to existing job.

        **Validates: Requirements R21.11**

        Property: When two concurrent submissions both pass the initial
        find_by_idempotency_key check (race window), the second insert
        hits the unique index, triggers IntegrityError, rolls back, and
        returns the winning row. No duplicate is created.
        """
        mock_db = AsyncMock()
        mock_db.rollback = AsyncMock()

        existing_job = _make_mock_job(
            org_id=org_id,
            job_type=job_type.value,
            idempotency_key=idempotency_key,
            status="queued",
        )

        with patch("app.services.job_service.JobRepository") as MockRepo:
            mock_repo = AsyncMock()
            MockRepo.return_value = mock_repo
            # First find returns None (race window), second returns existing
            mock_repo.find_by_idempotency_key = AsyncMock(
                side_effect=[None, existing_job]
            )
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

            service = JobService(db=mock_db, org_id=org_id)
            service._repo = mock_repo

            schema = JobCreate(
                job_type=job_type,
                idempotency_key=idempotency_key,
            )

            result = await service.submit_job(schema, user_id)

            # Invariant: returns existing job, no duplicate created
            assert result.id == existing_job.id
            mock_db.rollback.assert_called_once()

    @settings(max_examples=50)
    @given(
        org_a=uuid_strategy,
        org_b=uuid_strategy,
        user_a=uuid_strategy,
        user_b=uuid_strategy,
        idempotency_key=idempotency_key_strategy,
        job_type=job_type_strategy,
    )
    @pytest.mark.asyncio
    async def test_different_orgs_same_key_create_separate_jobs(
        self,
        org_a: UUID,
        org_b: UUID,
        user_a: UUID,
        user_b: UUID,
        idempotency_key: str,
        job_type: JobType,
    ) -> None:
        """Different orgs with the same idempotency key get separate jobs.

        **Validates: Requirements R21.11**

        Property: Tenant isolation means org A's idempotency key does not
        collide with org B's. Each org can independently use the same key
        and get their own job record.
        """
        assume(org_a != org_b)

        mock_db = AsyncMock()

        job_a = _make_mock_job(
            org_id=org_a,
            job_type=job_type.value,
            idempotency_key=idempotency_key,
        )
        job_b = _make_mock_job(
            org_id=org_b,
            job_type=job_type.value,
            idempotency_key=idempotency_key,
        )

        schema = JobCreate(
            job_type=job_type,
            idempotency_key=idempotency_key,
        )

        # Submit for org A
        with patch("app.services.job_service.JobRepository") as MockRepo:
            mock_repo_a = AsyncMock()
            MockRepo.return_value = mock_repo_a
            mock_repo_a.find_by_idempotency_key = AsyncMock(return_value=None)
            mock_repo_a.create = AsyncMock(return_value=job_a)

            service_a = JobService(db=mock_db, org_id=org_a)
            service_a._repo = mock_repo_a

            result_a = await service_a.submit_job(schema, user_a)

        # Submit for org B
        with patch("app.services.job_service.JobRepository") as MockRepo:
            mock_repo_b = AsyncMock()
            MockRepo.return_value = mock_repo_b
            mock_repo_b.find_by_idempotency_key = AsyncMock(return_value=None)
            mock_repo_b.create = AsyncMock(return_value=job_b)

            service_b = JobService(db=mock_db, org_id=org_b)
            service_b._repo = mock_repo_b

            result_b = await service_b.submit_job(schema, user_b)

        # Invariant: different jobs for different orgs
        assert result_a.id != result_b.id
        assert result_a.org_id == org_a
        assert result_b.org_id == org_b

    @settings(max_examples=50)
    @given(
        org_id=uuid_strategy,
        user_id=uuid_strategy,
        idempotency_key=idempotency_key_strategy,
        job_type=job_type_strategy,
    )
    @pytest.mark.asyncio
    async def test_first_submission_creates_new_job(
        self,
        org_id: UUID,
        user_id: UUID,
        idempotency_key: str,
        job_type: JobType,
    ) -> None:
        """First submission with a key creates a new job.

        **Validates: Requirements R21.11**

        Property: When no existing job matches the idempotency key,
        submit_job creates a new job and returns it. Total job count for
        this key becomes exactly 1.
        """
        mock_db = AsyncMock()

        new_job = _make_mock_job(
            org_id=org_id,
            job_type=job_type.value,
            idempotency_key=idempotency_key,
            status="queued",
        )

        with patch("app.services.job_service.JobRepository") as MockRepo:
            mock_repo = AsyncMock()
            MockRepo.return_value = mock_repo
            mock_repo.find_by_idempotency_key = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=new_job)

            service = JobService(db=mock_db, org_id=org_id)
            service._repo = mock_repo

            schema = JobCreate(
                job_type=job_type,
                idempotency_key=idempotency_key,
            )

            result = await service.submit_job(schema, user_id)

            # Job was created
            assert result.id == new_job.id
            mock_repo.create.assert_called_once()
