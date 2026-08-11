"""Unit tests for job type configurations and JobService integration.

Tests cover:
    - All 6 types have valid configurations
    - heartbeat_interval <= lease_duration / 3 for all types
    - Unknown job type raises ValueError from get_job_type_config
    - Duration clamping works correctly via validate_job_duration
    - submit_job auto-sets workload_class from config
    - submit_job clamps max_duration_seconds to type maximum
    - submit_job sets max_attempts from retry_policy
    - claim_job uses type-specific lease duration for known workload_class

Requirements: R64.4, R64.5
"""

from __future__ import annotations

import sys
from datetime import timedelta
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

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)

# Mock sqlalchemy.exc
_sa_exc_mock = ModuleType("sqlalchemy.exc")


class _IntegrityError(Exception):
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
from app.schemas.validation import JobType, WorkloadClass
from app.services.job_service import JobService
from app.services.job_type_config import (
    JOB_TYPE_CONFIGS,
    JobTypeConfig,
    RetryPolicy,
    get_job_type_config,
    validate_job_duration,
)


# =============================================================================
# Constants
# =============================================================================

ORG_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")
JOB_ID = UUID("33333333-3333-3333-3333-333333333333")

ALL_JOB_TYPES = [
    "image_generation",
    "video_generation",
    "lora_training",
    "brain_heavy_inference",
    "batch_generation",
    "publishing_dispatch",
]


# =============================================================================
# Tests: JobTypeConfig module — configurations
# =============================================================================


@pytest.mark.unit
class TestJobTypeConfigs:
    """Tests for JOB_TYPE_CONFIGS constant."""

    def test_all_six_types_are_configured(self):
        """All 6 expected job types have entries in JOB_TYPE_CONFIGS."""
        for job_type in ALL_JOB_TYPES:
            assert job_type in JOB_TYPE_CONFIGS, (
                f"Missing config for job type: {job_type}"
            )

    def test_configs_are_job_type_config_instances(self):
        """Each entry is a proper JobTypeConfig dataclass."""
        for job_type, config in JOB_TYPE_CONFIGS.items():
            assert isinstance(config, JobTypeConfig), (
                f"{job_type} config is not a JobTypeConfig"
            )

    def test_heartbeat_interval_within_lease_duration_third(self):
        """heartbeat_interval must be <= lease_duration / 3 for all types.

        This ensures workers can detect lease expiration before it happens.
        """
        for job_type, config in JOB_TYPE_CONFIGS.items():
            max_heartbeat = config.lease_duration / 3
            assert config.heartbeat_interval <= max_heartbeat, (
                f"{job_type}: heartbeat_interval ({config.heartbeat_interval}) "
                f"exceeds lease_duration/3 ({max_heartbeat})"
            )

    def test_max_duration_is_positive(self):
        """All max_duration values are positive."""
        for job_type, config in JOB_TYPE_CONFIGS.items():
            assert config.max_duration > timedelta(0), (
                f"{job_type}: max_duration must be positive"
            )

    def test_retry_policy_max_attempts_at_least_one(self):
        """All retry policies have at least 1 attempt."""
        for job_type, config in JOB_TYPE_CONFIGS.items():
            assert config.retry_policy.max_attempts >= 1, (
                f"{job_type}: max_attempts must be >= 1"
            )

    def test_cancellation_behavior_values_are_valid(self):
        """cancellation_behavior must be one of the valid options."""
        valid_behaviors = {"immediate_lease_expire", "graceful_with_timeout"}
        for job_type, config in JOB_TYPE_CONFIGS.items():
            assert config.cancellation_behavior in valid_behaviors, (
                f"{job_type}: invalid cancellation_behavior "
                f"'{config.cancellation_behavior}'"
            )

    def test_workload_class_values_are_nonempty(self):
        """All workload_class values are non-empty strings."""
        for job_type, config in JOB_TYPE_CONFIGS.items():
            assert config.workload_class, (
                f"{job_type}: workload_class must be non-empty"
            )

    def test_image_generation_config_values(self):
        """image_generation has correct configuration per design."""
        cfg = JOB_TYPE_CONFIGS["image_generation"]
        assert cfg.max_duration == timedelta(minutes=30)
        assert cfg.retry_policy.max_attempts == 3
        assert cfg.heartbeat_interval == timedelta(minutes=2)
        assert cfg.lease_duration == timedelta(minutes=10)
        assert cfg.workload_class == "image_generation"

    def test_video_generation_config_values(self):
        """video_generation has correct configuration per design."""
        cfg = JOB_TYPE_CONFIGS["video_generation"]
        assert cfg.max_duration == timedelta(minutes=10)
        assert cfg.retry_policy.max_attempts == 3
        assert cfg.heartbeat_interval == timedelta(minutes=1)
        assert cfg.lease_duration == timedelta(minutes=5)
        assert cfg.workload_class == "video_generation"

    def test_lora_training_config_values(self):
        """lora_training has correct configuration per design."""
        cfg = JOB_TYPE_CONFIGS["lora_training"]
        assert cfg.max_duration == timedelta(hours=4)
        assert cfg.retry_policy.max_attempts == 2
        assert cfg.heartbeat_interval == timedelta(minutes=5)
        assert cfg.lease_duration == timedelta(minutes=15)
        assert cfg.workload_class == "training"
        assert cfg.cancellation_behavior == "graceful_with_timeout"

    def test_brain_heavy_inference_config_values(self):
        """brain_heavy_inference has correct configuration per design."""
        cfg = JOB_TYPE_CONFIGS["brain_heavy_inference"]
        assert cfg.max_duration == timedelta(minutes=5)
        assert cfg.retry_policy.max_attempts == 3
        assert cfg.heartbeat_interval == timedelta(seconds=30)
        assert cfg.lease_duration == timedelta(minutes=2)
        assert cfg.workload_class == "interactive_language"

    def test_batch_generation_config_values(self):
        """batch_generation has correct configuration per design."""
        cfg = JOB_TYPE_CONFIGS["batch_generation"]
        assert cfg.max_duration == timedelta(hours=2)
        assert cfg.retry_policy.max_attempts == 2
        assert cfg.heartbeat_interval == timedelta(minutes=5)
        assert cfg.lease_duration == timedelta(minutes=15)
        assert cfg.workload_class == "batch"

    def test_publishing_dispatch_config_values(self):
        """publishing_dispatch has correct configuration per design."""
        cfg = JOB_TYPE_CONFIGS["publishing_dispatch"]
        assert cfg.max_duration == timedelta(minutes=5)
        assert cfg.retry_policy.max_attempts == 3
        assert cfg.heartbeat_interval == timedelta(seconds=30)
        assert cfg.lease_duration == timedelta(minutes=2)
        assert cfg.workload_class == "publishing"


# =============================================================================
# Tests: get_job_type_config helper
# =============================================================================


@pytest.mark.unit
class TestGetJobTypeConfig:
    """Tests for get_job_type_config helper function."""

    def test_returns_config_for_valid_type(self):
        """Returns JobTypeConfig for a known job type."""
        config = get_job_type_config("image_generation")
        assert isinstance(config, JobTypeConfig)
        assert config.workload_class == "image_generation"

    def test_raises_value_error_for_unknown_type(self):
        """Raises ValueError with valid types listed for unknown type."""
        with pytest.raises(ValueError, match="Unknown job type"):
            get_job_type_config("nonexistent_type")

    def test_error_message_lists_valid_types(self):
        """ValueError message includes valid job types."""
        with pytest.raises(ValueError, match="image_generation"):
            get_job_type_config("bad_type")


# =============================================================================
# Tests: validate_job_duration helper
# =============================================================================


@pytest.mark.unit
class TestValidateJobDuration:
    """Tests for validate_job_duration helper function."""

    def test_returns_requested_when_within_bounds(self):
        """Returns requested_seconds unchanged when below max."""
        # image_generation max is 30 min = 1800s
        result = validate_job_duration("image_generation", 600)
        assert result == 600

    def test_clamps_to_max_when_exceeds(self):
        """Clamps to type's max_duration when requested exceeds it."""
        # image_generation max is 30 min = 1800s
        result = validate_job_duration("image_generation", 9999)
        assert result == 1800

    def test_returns_exact_max_when_at_boundary(self):
        """Returns the max value when requested equals max."""
        # lora_training max is 4h = 14400s
        result = validate_job_duration("lora_training", 14400)
        assert result == 14400

    def test_raises_for_unknown_type(self):
        """Raises ValueError for unknown job type."""
        with pytest.raises(ValueError, match="Unknown job type"):
            validate_job_duration("fake_type", 100)

    def test_brain_heavy_inference_clamps_to_300s(self):
        """brain_heavy_inference max is 5 min = 300s."""
        result = validate_job_duration("brain_heavy_inference", 1000)
        assert result == 300


# =============================================================================
# Tests: JobService integration with job type configs
# =============================================================================


@pytest.fixture
def mock_db():
    """Create a mock async DB session."""
    return AsyncMock()


@pytest.fixture
def job_service(mock_db):
    """Create a JobService with mocked repository."""
    with patch("app.services.job_service.JobRepository") as MockRepo:
        mock_repo = AsyncMock()
        MockRepo.return_value = mock_repo
        service = JobService(db=mock_db, org_id=ORG_ID)
        service._repo = mock_repo
        yield service, mock_repo


def _make_mock_job(
    job_id: UUID = JOB_ID,
    status: str = "queued",
    job_type: str = "image_generation",
    **kwargs,
) -> MagicMock:
    """Create a mock Job ORM instance."""
    job = MagicMock()
    job.id = job_id
    job.org_id = ORG_ID
    job.status = status
    job.job_type = job_type
    job.priority = kwargs.get("priority", 5)
    job.workload_class = kwargs.get("workload_class")
    job.max_duration_seconds = kwargs.get("max_duration_seconds", 1800)
    job.max_attempts = kwargs.get("max_attempts", 3)
    return job


@pytest.mark.unit
class TestSubmitJobTypeConfigIntegration:
    """Tests for JobService.submit_job integration with JOB_TYPE_CONFIGS."""

    @pytest.mark.asyncio
    async def test_auto_sets_workload_class_from_config(self, job_service):
        """submit_job auto-sets workload_class when not provided by client."""
        service, mock_repo = job_service
        expected_job = _make_mock_job(workload_class="image_generation")
        mock_repo.find_by_idempotency_key = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=expected_job)

        schema = JobCreate(
            job_type=JobType.IMAGE_GENERATION,
            priority=5,
            # workload_class NOT provided
        )

        await service.submit_job(schema, USER_ID)

        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["workload_class"] == "image_generation"

    @pytest.mark.asyncio
    async def test_client_workload_class_overrides_config(self, job_service):
        """Client-provided workload_class takes precedence over config."""
        service, mock_repo = job_service
        expected_job = _make_mock_job(workload_class="batch")
        mock_repo.find_by_idempotency_key = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=expected_job)

        schema = JobCreate(
            job_type=JobType.IMAGE_GENERATION,
            workload_class=WorkloadClass.BATCH,
        )

        await service.submit_job(schema, USER_ID)

        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["workload_class"] == "batch"

    @pytest.mark.asyncio
    async def test_clamps_max_duration_seconds(self, job_service):
        """submit_job clamps max_duration_seconds to type's maximum."""
        service, mock_repo = job_service
        expected_job = _make_mock_job(max_duration_seconds=300)
        mock_repo.find_by_idempotency_key = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=expected_job)

        schema = JobCreate(
            job_type=JobType.BRAIN_HEAVY_INFERENCE,
            max_duration_seconds=9999,  # Exceeds 5min max
        )

        await service.submit_job(schema, USER_ID)

        call_kwargs = mock_repo.create.call_args.kwargs
        # brain_heavy_inference max is 300 seconds
        assert call_kwargs["max_duration_seconds"] == 300

    @pytest.mark.asyncio
    async def test_passes_duration_unchanged_when_within_bounds(
        self, job_service
    ):
        """submit_job passes duration as-is when within type's max."""
        service, mock_repo = job_service
        expected_job = _make_mock_job(max_duration_seconds=120)
        mock_repo.find_by_idempotency_key = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=expected_job)

        schema = JobCreate(
            job_type=JobType.BRAIN_HEAVY_INFERENCE,
            max_duration_seconds=120,  # Well within 300s max
        )

        await service.submit_job(schema, USER_ID)

        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["max_duration_seconds"] == 120

    @pytest.mark.asyncio
    async def test_sets_max_attempts_from_retry_policy(self, job_service):
        """submit_job sets max_attempts from the type's retry_policy."""
        service, mock_repo = job_service
        expected_job = _make_mock_job(max_attempts=2)
        mock_repo.find_by_idempotency_key = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=expected_job)

        schema = JobCreate(
            job_type=JobType.LORA_TRAINING,
        )

        await service.submit_job(schema, USER_ID)

        call_kwargs = mock_repo.create.call_args.kwargs
        # lora_training has max_attempts=2
        assert call_kwargs["max_attempts"] == 2

    @pytest.mark.asyncio
    async def test_image_generation_gets_3_attempts(self, job_service):
        """image_generation retry_policy sets max_attempts=3."""
        service, mock_repo = job_service
        expected_job = _make_mock_job(max_attempts=3)
        mock_repo.find_by_idempotency_key = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock(return_value=expected_job)

        schema = JobCreate(job_type=JobType.IMAGE_GENERATION)
        await service.submit_job(schema, USER_ID)

        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["max_attempts"] == 3


@pytest.mark.unit
class TestClaimJobTypeConfigIntegration:
    """Tests for JobService.claim_job integration with JOB_TYPE_CONFIGS."""

    @pytest.mark.asyncio
    async def test_uses_type_specific_lease_for_image_generation(
        self, job_service
    ):
        """claim_job uses 10-minute lease for image_generation workload."""
        service, mock_repo = job_service
        mock_repo.claim_next_job = AsyncMock(return_value=None)

        await service.claim_job(
            worker_identity="worker-1",
            workload_class="image_generation",
        )

        call_kwargs = mock_repo.claim_next_job.call_args.kwargs
        assert call_kwargs["lease_duration"] == timedelta(minutes=10)

    @pytest.mark.asyncio
    async def test_uses_type_specific_lease_for_training(self, job_service):
        """claim_job uses 15-minute lease for training workload."""
        service, mock_repo = job_service
        mock_repo.claim_next_job = AsyncMock(return_value=None)

        await service.claim_job(
            worker_identity="worker-1",
            workload_class="training",
        )

        call_kwargs = mock_repo.claim_next_job.call_args.kwargs
        assert call_kwargs["lease_duration"] == timedelta(minutes=15)

    @pytest.mark.asyncio
    async def test_uses_type_specific_lease_for_interactive_language(
        self, job_service
    ):
        """claim_job uses 2-minute lease for interactive_language workload."""
        service, mock_repo = job_service
        mock_repo.claim_next_job = AsyncMock(return_value=None)

        await service.claim_job(
            worker_identity="worker-1",
            workload_class="interactive_language",
        )

        call_kwargs = mock_repo.claim_next_job.call_args.kwargs
        assert call_kwargs["lease_duration"] == timedelta(minutes=2)

    @pytest.mark.asyncio
    async def test_falls_back_to_default_for_unknown_workload(
        self, job_service
    ):
        """claim_job uses default 30-min lease for unrecognized workload."""
        service, mock_repo = job_service
        mock_repo.claim_next_job = AsyncMock(return_value=None)

        await service.claim_job(
            worker_identity="worker-1",
            workload_class="unknown_workload",
        )

        call_kwargs = mock_repo.claim_next_job.call_args.kwargs
        assert call_kwargs["lease_duration"] == timedelta(minutes=30)

    @pytest.mark.asyncio
    async def test_explicit_duration_overrides_type_config(self, job_service):
        """Explicit lease_duration_seconds overrides type-specific config."""
        service, mock_repo = job_service
        mock_repo.claim_next_job = AsyncMock(return_value=None)

        await service.claim_job(
            worker_identity="worker-1",
            lease_duration_seconds=900,
            workload_class="image_generation",
        )

        call_kwargs = mock_repo.claim_next_job.call_args.kwargs
        assert call_kwargs["lease_duration"] == timedelta(seconds=900)

    @pytest.mark.asyncio
    async def test_default_lease_when_no_workload_class(self, job_service):
        """claim_job uses default 30-min lease when no workload_class."""
        service, mock_repo = job_service
        mock_repo.claim_next_job = AsyncMock(return_value=None)

        await service.claim_job(worker_identity="worker-1")

        call_kwargs = mock_repo.claim_next_job.call_args.kwargs
        assert call_kwargs["lease_duration"] == timedelta(minutes=30)
