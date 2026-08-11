"""Unit tests for ProviderReputationService — dynamic ranking and auto-quarantine.

Tests cover:
    - record_job_outcome updates metrics correctly for success
    - record_job_outcome updates metrics correctly for failure
    - record_job_outcome auto-quarantines at >30% failure rate
    - record_job_outcome does NOT quarantine below min job threshold
    - get_provider_ranking returns sorted providers by score
    - get_provider_ranking excludes quarantined by default
    - check_quarantine quarantines high failure rate providers
    - check_quarantine releases recovered providers
    - check_quarantine no-ops for unknown providers
    - get_provider_metrics returns None for unknown provider
    - _compute_overall_score produces valid score
    - _ema computes exponential moving average correctly

Requirements: R65.1, R65.2, R65.3, R65.4, R65.5, R65.6
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
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
_sa_mock.Index = MagicMock
_sa_mock.func = MagicMock()
_sa_mock.select = MagicMock()
_sa_mock.update = MagicMock()
_sa_mock.and_ = MagicMock()

_sa_orm_mock = MagicMock()
_sa_orm_mock.Mapped = MagicMock
_sa_orm_mock.mapped_column = MagicMock(return_value=None)
_sa_orm_mock.DeclarativeBase = type("DeclarativeBase", (), {})

_sa_dialects_pg_mock = MagicMock()
_sa_dialects_pg_mock.UUID = MagicMock
_sa_dialects_pg_mock.JSONB = MagicMock
_sa_dialects_pg_mock.ARRAY = MagicMock
_sa_dialects_pg_mock.insert = MagicMock()

_sa_ext_asyncio_mock = MagicMock()
_sa_ext_asyncio_mock.AsyncSession = MagicMock

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)
sys.modules.setdefault("sqlalchemy.exc", MagicMock())

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


_mock_db_base.Base = _MockBase  # type: ignore[attr-defined]
_mock_db_base.TimestampMixin = _MockTimestampMixin  # type: ignore[attr-defined]
_mock_db_base.UUIDMixin = _MockUUIDMixin  # type: ignore[attr-defined]
_mock_db_base.TenantMixin = _MockTenantMixin  # type: ignore[attr-defined]
_mock_db_base.SoftDeleteMixin = type("SoftDeleteMixin", (), {})  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.base", _mock_db_base)

# Mock app.db.tenant_scope
_mock_tenant_scope = ModuleType("app.db.tenant_scope")
_mock_tenant_scope.QUARANTINED_ORG_ID = UUID("00000000-0000-0000-0000-000000000000")  # type: ignore[attr-defined]
_mock_tenant_scope.validate_org_id = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.tenant_scope", _mock_tenant_scope)

# Mock app.core.logging
_mock_core_logging = ModuleType("app.core.logging")
_mock_logger = MagicMock()
_mock_core_logging.get_logger = MagicMock(return_value=_mock_logger)  # type: ignore[attr-defined]
sys.modules.setdefault("app.core.logging", _mock_core_logging)

# Mock app.models.provider_reputation with a class supporting attribute access
_mock_models_pkg = ModuleType("app.models")
_mock_models_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.models", _mock_models_pkg)


class _MockProviderReputation:
    """Mock ProviderReputation model with SQLAlchemy-like column access."""

    __tablename__ = "provider_reputation"

    class org_id:
        @staticmethod
        def __eq__(other): return MagicMock()  # noqa: E704

    class provider_name:
        @staticmethod
        def __eq__(other): return MagicMock()  # noqa: E704

    class overall_score:
        @staticmethod
        def desc(): return MagicMock()  # noqa: E704

    class is_quarantined:
        @staticmethod
        def is_(val): return MagicMock()  # noqa: E704

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mock_model_mod = ModuleType("app.models.provider_reputation")
_mock_model_mod.ProviderReputation = _MockProviderReputation  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.provider_reputation", _mock_model_mod)

# Now import the schemas and service under test
from app.schemas.provider_reputation import (
    JobOutcomeStatus,
    ProviderType,
    RecordJobOutcomeRequest,
)
from app.services.provider_reputation_service import (
    MIN_JOBS_FOR_QUARANTINE,
    QUARANTINE_FAILURE_THRESHOLD,
    ProviderReputationService,
)


# =============================================================================
# Test Fixtures
# =============================================================================

ORG_ID = uuid4()


def _make_reputation_record(
    provider_name: str = "runpod",
    total_jobs: int = 0,
    successful_jobs: int = 0,
    failed_jobs: int = 0,
    failure_rate_24h: float = 0.0,
    is_quarantined: bool = False,
    overall_score: float = 0.5,
    **kwargs,
):
    """Create a mock ProviderReputation record for testing."""
    record = MagicMock()
    record.id = uuid4()
    record.org_id = ORG_ID
    record.provider_name = provider_name
    record.provider_type = "compute"
    record.startup_latency_seconds = kwargs.get("startup_latency_seconds", 30.0)
    record.queue_latency_seconds = kwargs.get("queue_latency_seconds", 5.0)
    record.generation_duration_seconds = kwargs.get("generation_duration_seconds", 60.0)
    record.failure_rate_24h = failure_rate_24h
    record.cost_variance = kwargs.get("cost_variance", 0.1)
    record.availability_7d = kwargs.get("availability_7d", 0.95)
    record.model_cache_readiness = kwargs.get("model_cache_readiness", 0.8)
    record.quality_acceptance_rate = kwargs.get("quality_acceptance_rate", 0.9)
    record.cleanup_failures = kwargs.get("cleanup_failures", 0)
    record.cost_overruns = kwargs.get("cost_overruns", 0)
    record.timeout_rate = kwargs.get("timeout_rate", 0.0)
    record.connection_failures = kwargs.get("connection_failures", 0)
    record.total_jobs = total_jobs
    record.successful_jobs = successful_jobs
    record.failed_jobs = failed_jobs
    record.total_cost_usd = kwargs.get("total_cost_usd", 0.0)
    record.is_quarantined = is_quarantined
    record.quarantined_at = kwargs.get("quarantined_at", None)
    record.quarantine_reason = kwargs.get("quarantine_reason", None)
    record.overall_score = overall_score
    record.metadata_ = kwargs.get("metadata_", None)
    record.last_job_at = kwargs.get("last_job_at", None)
    return record


# =============================================================================
# Tests: record_job_outcome
# =============================================================================


@pytest.mark.unit
class TestRecordJobOutcome:
    """Tests for ProviderReputationService.record_job_outcome()."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        return ProviderReputationService(mock_db)

    @pytest.mark.asyncio
    async def test_success_increments_successful_jobs(self, service, mock_db):
        """Successful job outcome increments successful_jobs counter."""
        record = _make_reputation_record(total_jobs=5, successful_jobs=4, failed_jobs=1)
        service._get_or_create_record = AsyncMock(return_value=record)

        request = RecordJobOutcomeRequest(
            provider_name="runpod",
            status=JobOutcomeStatus.SUCCESS,
            startup_latency_seconds=20.0,
            generation_duration_seconds=45.0,
        )
        result = await service.record_job_outcome(ORG_ID, request)

        assert record.total_jobs == 6
        assert record.successful_jobs == 5
        assert record.failed_jobs == 1
        assert result.provider_name == "runpod"
        assert result.total_jobs == 6
        assert result.is_quarantined is False

    @pytest.mark.asyncio
    async def test_failure_increments_failed_jobs(self, service, mock_db):
        """Failed job outcome increments failed_jobs counter."""
        record = _make_reputation_record(total_jobs=5, successful_jobs=4, failed_jobs=1)
        service._get_or_create_record = AsyncMock(return_value=record)

        request = RecordJobOutcomeRequest(
            provider_name="runpod",
            status=JobOutcomeStatus.FAILED,
        )
        result = await service.record_job_outcome(ORG_ID, request)

        assert record.total_jobs == 6
        assert record.successful_jobs == 4
        assert record.failed_jobs == 2

    @pytest.mark.asyncio
    async def test_auto_quarantine_high_failure_rate(self, service, mock_db):
        """Provider auto-quarantined when failure rate exceeds 30%."""
        record = _make_reputation_record(
            total_jobs=5, successful_jobs=1, failed_jobs=4, failure_rate_24h=0.8,
        )
        service._get_or_create_record = AsyncMock(return_value=record)

        request = RecordJobOutcomeRequest(
            provider_name="bad_provider",
            status=JobOutcomeStatus.FAILED,
        )
        result = await service.record_job_outcome(ORG_ID, request)

        assert record.is_quarantined is True
        assert record.quarantined_at is not None
        assert "Auto-quarantined" in record.quarantine_reason
        assert result.is_quarantined is True

    @pytest.mark.asyncio
    async def test_no_quarantine_below_min_jobs(self, service, mock_db):
        """Provider NOT quarantined below minimum job threshold."""
        record = _make_reputation_record(
            total_jobs=3, successful_jobs=1, failed_jobs=2, failure_rate_24h=0.67,
        )
        service._get_or_create_record = AsyncMock(return_value=record)

        request = RecordJobOutcomeRequest(
            provider_name="new_provider",
            status=JobOutcomeStatus.FAILED,
        )
        result = await service.record_job_outcome(ORG_ID, request)

        # total_jobs is now 4, still below MIN_JOBS_FOR_QUARANTINE (5)
        assert record.is_quarantined is False
        assert result.is_quarantined is False

    @pytest.mark.asyncio
    async def test_timeout_updates_timeout_rate(self, service, mock_db):
        """Timeout outcome updates the timeout_rate metric."""
        record = _make_reputation_record(total_jobs=9, successful_jobs=8, failed_jobs=1)
        record.timeout_rate = 0.1
        service._get_or_create_record = AsyncMock(return_value=record)

        request = RecordJobOutcomeRequest(
            provider_name="runpod",
            status=JobOutcomeStatus.TIMEOUT,
        )
        await service.record_job_outcome(ORG_ID, request)
        assert record.timeout_rate > 0.1

    @pytest.mark.asyncio
    async def test_connection_failure_increments_counter(self, service, mock_db):
        """Connection failure increments connection_failures counter."""
        record = _make_reputation_record(total_jobs=5, successful_jobs=4, failed_jobs=1)
        record.connection_failures = 2
        service._get_or_create_record = AsyncMock(return_value=record)

        request = RecordJobOutcomeRequest(
            provider_name="fluidstack",
            status=JobOutcomeStatus.CONNECTION_FAILURE,
        )
        await service.record_job_outcome(ORG_ID, request)
        assert record.connection_failures == 3

    @pytest.mark.asyncio
    async def test_cost_overrun_tracked(self, service, mock_db):
        """Cost overrun detected when actual > estimated."""
        record = _make_reputation_record(total_jobs=5, successful_jobs=5, failed_jobs=0)
        record.cost_overruns = 0
        record.total_cost_usd = 5.0
        service._get_or_create_record = AsyncMock(return_value=record)

        request = RecordJobOutcomeRequest(
            provider_name="runpod",
            status=JobOutcomeStatus.SUCCESS,
            estimated_cost_usd=1.0,
            actual_cost_usd=1.5,
        )
        await service.record_job_outcome(ORG_ID, request)

        assert record.cost_overruns == 1
        assert record.total_cost_usd == 6.5

    @pytest.mark.asyncio
    async def test_quality_rejection_lowers_rate(self, service, mock_db):
        """Quality rejection lowers quality_acceptance_rate."""
        record = _make_reputation_record(total_jobs=9, successful_jobs=9, failed_jobs=0)
        record.quality_acceptance_rate = 0.9
        service._get_or_create_record = AsyncMock(return_value=record)

        request = RecordJobOutcomeRequest(
            provider_name="runpod",
            status=JobOutcomeStatus.SUCCESS,
            quality_accepted=False,
        )
        await service.record_job_outcome(ORG_ID, request)
        assert record.quality_acceptance_rate < 0.9


# =============================================================================
# Tests: get_provider_ranking
# =============================================================================


@pytest.mark.unit
class TestGetProviderRanking:
    """Tests for ProviderReputationService.get_provider_ranking()."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return ProviderReputationService(mock_db)

    @pytest.mark.asyncio
    async def test_returns_sorted_ranking(self, service, mock_db):
        """Rankings returned sorted by overall_score descending."""
        high = _make_reputation_record(
            provider_name="runpod", overall_score=0.9, total_jobs=20,
        )
        low = _make_reputation_record(
            provider_name="fluidstack", overall_score=0.4, total_jobs=10,
        )

        mock_result_main = MagicMock()
        mock_result_main.scalars.return_value.all.return_value = [high, low]
        mock_result_quarantine = MagicMock()
        mock_result_quarantine.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(
            side_effect=[mock_result_main, mock_result_quarantine]
        )
        result = await service.get_provider_ranking(ORG_ID)

        assert result.total_providers == 2
        assert result.rankings[0].provider_name == "runpod"
        assert result.rankings[0].overall_score == 0.9
        assert result.rankings[1].provider_name == "fluidstack"
        assert result.quarantined_count == 0

    @pytest.mark.asyncio
    async def test_excludes_quarantined_by_default(self, service, mock_db):
        """Quarantined providers excluded from ranking by default."""
        active = _make_reputation_record(
            provider_name="runpod", overall_score=0.8, is_quarantined=False,
        )
        quarantined = _make_reputation_record(
            provider_name="bad_host", overall_score=0.2, is_quarantined=True,
        )

        mock_result_main = MagicMock()
        mock_result_main.scalars.return_value.all.return_value = [active]
        mock_result_quarantine = MagicMock()
        mock_result_quarantine.scalars.return_value.all.return_value = [quarantined]

        mock_db.execute = AsyncMock(
            side_effect=[mock_result_main, mock_result_quarantine]
        )
        result = await service.get_provider_ranking(ORG_ID)

        assert result.total_providers == 1
        assert result.rankings[0].provider_name == "runpod"
        assert result.quarantined_count == 1


# =============================================================================
# Tests: check_quarantine
# =============================================================================


@pytest.mark.unit
class TestCheckQuarantine:
    """Tests for ProviderReputationService.check_quarantine()."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        return ProviderReputationService(mock_db)

    @pytest.mark.asyncio
    async def test_quarantines_high_failure_provider(self, service, mock_db):
        """Provider quarantined when failure rate > 30%."""
        record = _make_reputation_record(
            provider_name="bad_host", total_jobs=10,
            successful_jobs=5, failed_jobs=5, failure_rate_24h=0.5,
            is_quarantined=False,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.check_quarantine(ORG_ID, "bad_host")

        assert result.is_quarantined is True
        assert result.action_taken == "quarantined"
        assert result.threshold == QUARANTINE_FAILURE_THRESHOLD

    @pytest.mark.asyncio
    async def test_releases_recovered_provider(self, service, mock_db):
        """Quarantined provider released when failure rate recovers."""
        record = _make_reputation_record(
            provider_name="recovered", total_jobs=20,
            successful_jobs=18, failed_jobs=2, failure_rate_24h=0.1,
            is_quarantined=True, quarantined_at=datetime.now(UTC),
            quarantine_reason="Auto-quarantined",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.check_quarantine(ORG_ID, "recovered")

        assert result.is_quarantined is False
        assert result.action_taken == "released"

    @pytest.mark.asyncio
    async def test_no_change_for_unknown_provider(self, service, mock_db):
        """Unknown provider returns not quarantined with no action."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.check_quarantine(ORG_ID, "unknown")

        assert result.is_quarantined is False
        assert result.action_taken is None


# =============================================================================
# Tests: get_provider_metrics
# =============================================================================


@pytest.mark.unit
class TestGetProviderMetrics:
    """Tests for ProviderReputationService.get_provider_metrics()."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return ProviderReputationService(mock_db)

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown(self, service, mock_db):
        """Returns None when provider has no reputation data."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_provider_metrics(ORG_ID, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_record_for_known(self, service, mock_db):
        """Returns reputation record for known provider."""
        record = _make_reputation_record(
            provider_name="runpod", total_jobs=50, overall_score=0.85,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_provider_metrics(ORG_ID, "runpod")

        assert result is not None
        assert result.provider_name == "runpod"
        assert result.total_jobs == 50


# =============================================================================
# Tests: Static helper methods
# =============================================================================


@pytest.mark.unit
class TestHelperMethods:
    """Tests for static helper methods on ProviderReputationService."""

    def test_ema_first_observation(self):
        """EMA returns new value on first observation."""
        result = ProviderReputationService._ema(0.0, 42.0, 1)
        assert result == 42.0

    def test_ema_blends_subsequent(self):
        """EMA blends current and new values after first observation."""
        result = ProviderReputationService._ema(50.0, 100.0, 10)
        assert abs(result - 55.0) < 0.01

    def test_compute_rolling_rate_first(self):
        """Rolling rate returns 1.0 for first event."""
        result = ProviderReputationService._compute_rolling_rate(0.0, 1, True)
        assert result == 1.0

    def test_compute_rolling_rate_incremental(self):
        """Rolling rate updates incrementally."""
        result = ProviderReputationService._compute_rolling_rate(0.2, 10, True)
        assert abs(result - 0.28) < 0.01

    def test_overall_score_perfect_provider(self):
        """Perfect provider gets score near 1.0."""
        record = _make_reputation_record(
            total_jobs=100, successful_jobs=100, failed_jobs=0,
            startup_latency_seconds=10.0, cost_variance=0.0,
            availability_7d=1.0, quality_acceptance_rate=1.0,
        )
        score = ProviderReputationService._compute_overall_score(record)
        assert score > 0.9

    def test_overall_score_terrible_provider(self):
        """Terrible provider gets low score."""
        record = _make_reputation_record(
            total_jobs=100, successful_jobs=10, failed_jobs=90,
            startup_latency_seconds=250.0, cost_variance=0.9,
            availability_7d=0.1, quality_acceptance_rate=0.1,
        )
        score = ProviderReputationService._compute_overall_score(record)
        assert score < 0.3

    def test_overall_score_bounded(self):
        """Overall score always between 0.0 and 1.0."""
        record = _make_reputation_record(
            total_jobs=50, successful_jobs=25, failed_jobs=25,
            startup_latency_seconds=500.0, cost_variance=2.0,
            availability_7d=0.5, quality_acceptance_rate=0.5,
        )
        score = ProviderReputationService._compute_overall_score(record)
        assert 0.0 <= score <= 1.0

    def test_evaluate_quarantine_below_min(self):
        """No quarantine below MIN_JOBS_FOR_QUARANTINE."""
        record = _make_reputation_record(total_jobs=3, failure_rate_24h=0.9)
        result = ProviderReputationService._evaluate_quarantine(record)
        assert result == "no_change"

    def test_evaluate_quarantine_triggers(self):
        """Quarantine triggers above threshold."""
        record = _make_reputation_record(
            total_jobs=10, failure_rate_24h=0.5, is_quarantined=False,
        )
        result = ProviderReputationService._evaluate_quarantine(record)
        assert result == "quarantine"

    def test_evaluate_quarantine_releases(self):
        """Release triggers when failure rate recovers."""
        record = _make_reputation_record(
            total_jobs=10, failure_rate_24h=0.1, is_quarantined=True,
        )
        result = ProviderReputationService._evaluate_quarantine(record)
        assert result == "release"
