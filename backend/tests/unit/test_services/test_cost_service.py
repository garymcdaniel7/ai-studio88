"""Unit tests for CostService — atomic budget enforcement and cost reservations.

Tests cover:
    - reserve_cost creates reservation within budget
    - reserve_cost raises BudgetExceededError when daily limit exceeded
    - reserve_cost raises BudgetExceededError when monthly limit exceeded
    - reserve_cost raises LedgerUnavailableError on DB failure (fail-safe)
    - reserve_cost skips budget check for customer_infrastructure costs
    - reserve_cost raises ValueError for non-positive amount
    - reserve_cost raises ValueError for empty operation
    - check_budget returns True within budget
    - check_budget returns False when over budget
    - check_budget raises LedgerUnavailableError on DB failure
    - get_current_spend sums reservations + entries
    - get_budget_limits returns defaults from settings

Requirements: R14.3, R14.4, R14.9, R14.13, R14.14, R66.1, R66.2, R66.7
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# =============================================================================
# Mock heavy dependencies before importing application modules.
# =============================================================================

# SQLAlchemy core mocks
_sa_mock = MagicMock()
_sa_mock.DateTime = MagicMock
_sa_mock.Float = MagicMock
_sa_mock.Integer = MagicMock
_sa_mock.String = MagicMock
_sa_mock.Text = MagicMock
_sa_mock.Boolean = MagicMock
_sa_mock.Numeric = MagicMock
_sa_mock.ForeignKey = MagicMock
_sa_mock.Index = MagicMock
_sa_mock.func = MagicMock()
_sa_mock.select = MagicMock()
_sa_mock.update = MagicMock()
_sa_mock.and_ = MagicMock()

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

# Mock sqlalchemy.exc with real exception classes
_sa_exc_mock = ModuleType("sqlalchemy.exc")


class _OperationalError(Exception):
    """Mock OperationalError for testing."""

    def __init__(self, statement=None, params=None, orig=None):
        self.statement = statement
        self.params = params
        self.orig = orig
        super().__init__(str(orig) if orig else "OperationalError")


class _DBAPIError(Exception):
    """Mock DBAPIError for testing."""

    def __init__(self, statement=None, params=None, orig=None):
        self.statement = statement
        self.params = params
        self.orig = orig
        super().__init__(str(orig) if orig else "DBAPIError")


_sa_exc_mock.OperationalError = _OperationalError  # type: ignore[attr-defined]
_sa_exc_mock.DBAPIError = _DBAPIError  # type: ignore[attr-defined]
_sa_exc_mock.IntegrityError = type("IntegrityError", (Exception,), {})  # type: ignore[attr-defined]

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)
sys.modules.setdefault("sqlalchemy.exc", _sa_exc_mock)

# Mock app.db modules
_mock_db_module = ModuleType("app.db")
sys.modules.setdefault("app.db", _mock_db_module)

_mock_db_session = ModuleType("app.db.session")
_mock_db_session.get_db_session = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.session", _mock_db_session)

# Mock app.db.base with real-enough mixins
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

# Mock app.models
_mock_models_pkg = ModuleType("app.models")
_mock_models_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.models", _mock_models_pkg)

# Mock app.models.cost with classes that support SQLAlchemy-like comparisons
_mock_models_cost = ModuleType("app.models.cost")


class _MockColumn:
    """Mock column that supports SQLAlchemy-like operations."""

    def __ge__(self, other):
        return MagicMock()

    def __le__(self, other):
        return MagicMock()

    def __eq__(self, other):
        return MagicMock()

    def in_(self, values):
        return MagicMock()


class _MockCostReservation:
    """Mock CostReservation for testing."""

    __tablename__ = "cost_reservations"
    id = _MockColumn()
    org_id = _MockColumn()
    status = _MockColumn()
    cost_classification = _MockColumn()
    created_at = _MockColumn()
    reserved_amount_usd = _MockColumn()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if "id" not in kwargs:
            self.id = uuid4()


class _MockCostEntry:
    """Mock CostEntry for testing."""

    __tablename__ = "cost_entries"
    id = _MockColumn()
    org_id = _MockColumn()
    entry_type = _MockColumn()
    cost_classification = _MockColumn()
    created_at = _MockColumn()
    amount_usd = _MockColumn()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if "id" not in kwargs:
            self.id = uuid4()


_mock_models_cost.CostReservation = _MockCostReservation  # type: ignore[attr-defined]
_mock_models_cost.CostEntry = _MockCostEntry  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.cost", _mock_models_cost)


# Now import application modules
from app.schemas.cost import CostClassification, ReservationStatus
from app.services.cost_service import (
    BudgetExceededError,
    BudgetLimits,
    CostService,
    CostServiceError,
    LedgerUnavailableError,
)


# =============================================================================
# Fixtures
# =============================================================================

ORG_ID = UUID("11111111-1111-1111-1111-111111111111")
JOB_ID = UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture
def mock_db():
    """Create a mock async session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock(return_value=Decimal("0"))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def cost_service(mock_db):
    """Create a CostService instance with mock DB."""
    return CostService(db=mock_db, org_id=ORG_ID)


# Helper to create async mock functions
def _async_return(value):
    """Create a simple async function that returns a value."""

    async def _fn(*args, **kwargs):
        return value

    return _fn


def _async_budget_limits(daily=Decimal("50.0"), monthly=Decimal("500.0")):
    """Create an async function returning BudgetLimits."""

    async def _fn(*args, **kwargs):
        return BudgetLimits(daily_hard_usd=daily, monthly_hard_usd=monthly)

    return _fn


# =============================================================================
# Tests: reserve_cost — happy path
# =============================================================================


class TestReserveCostHappyPath:
    """Tests for successful cost reservation."""

    @pytest.mark.asyncio
    async def test_creates_reservation_within_budget(
        self, cost_service, mock_db
    ):
        """reserve_cost creates a reservation when within budget."""
        mock_db.scalar = AsyncMock(return_value=Decimal("0"))
        cost_service._sum_active_reservations = _async_return(Decimal("0"))
        cost_service._sum_cost_entries = _async_return(Decimal("0"))
        cost_service.get_budget_limits = _async_budget_limits()

        reservation = await cost_service.reserve_cost(
            operation="image_generation",
            estimated_amount_usd=Decimal("1.5000"),
            job_id=JOB_ID,
            provider="vast.ai",
        )

        assert reservation is not None
        assert reservation.org_id == ORG_ID
        assert reservation.job_id == JOB_ID
        assert reservation.operation == "image_generation"
        assert reservation.reserved_amount_usd == Decimal("1.5000")
        assert reservation.status == ReservationStatus.ACTIVE.value
        assert reservation.cost_classification == CostClassification.MANAGED_COMPUTE.value
        assert reservation.provider == "vast.ai"

        # Should have added both reservation and entry
        assert mock_db.add.call_count == 2
        assert mock_db.flush.call_count == 2

    @pytest.mark.asyncio
    async def test_sets_default_expiry(self, cost_service, mock_db):
        """reserve_cost sets a default expiry if none provided."""
        mock_db.scalar = AsyncMock(return_value=Decimal("0"))
        cost_service._sum_active_reservations = _async_return(Decimal("0"))
        cost_service._sum_cost_entries = _async_return(Decimal("0"))
        cost_service.get_budget_limits = _async_budget_limits()

        reservation = await cost_service.reserve_cost(
            operation="training",
            estimated_amount_usd=Decimal("5.0000"),
        )

        assert reservation.expires_at is not None
        now = datetime.now(UTC)
        assert reservation.expires_at > now
        assert reservation.expires_at < now + timedelta(hours=6)

    @pytest.mark.asyncio
    async def test_custom_expiry_honored(self, cost_service, mock_db):
        """reserve_cost uses the provided expires_at."""
        mock_db.scalar = AsyncMock(return_value=Decimal("0"))
        cost_service._sum_active_reservations = _async_return(Decimal("0"))
        cost_service._sum_cost_entries = _async_return(Decimal("0"))
        cost_service.get_budget_limits = _async_budget_limits()
        custom_expiry = datetime.now(UTC) + timedelta(hours=2)

        reservation = await cost_service.reserve_cost(
            operation="video_generation",
            estimated_amount_usd=Decimal("3.0000"),
            expires_at=custom_expiry,
        )

        assert reservation.expires_at == custom_expiry


# =============================================================================
# Tests: reserve_cost — budget exceeded
# =============================================================================


class TestReserveCostBudgetExceeded:
    """Tests for budget enforcement on reserve_cost."""

    @pytest.mark.asyncio
    async def test_rejects_when_daily_budget_exceeded(
        self, cost_service, mock_db
    ):
        """reserve_cost raises BudgetExceededError when daily limit exceeded.

        Validates: R14.3, R66.2
        """
        cost_service._sum_active_reservations = _async_return(Decimal("40.0000"))
        cost_service._sum_cost_entries = _async_return(Decimal("8.0000"))
        cost_service.get_budget_limits = _async_budget_limits()

        with pytest.raises(BudgetExceededError) as exc_info:
            await cost_service.reserve_cost(
                operation="image_generation",
                estimated_amount_usd=Decimal("5.0000"),
            )

        error = exc_info.value
        assert error.code == "DAILY_BUDGET_EXCEEDED"
        assert error.period == "daily"
        assert error.requested_usd == Decimal("5.0000")
        assert error.limit_usd == Decimal("50.0")

    @pytest.mark.asyncio
    async def test_rejects_when_monthly_budget_exceeded(
        self, cost_service, mock_db
    ):
        """reserve_cost raises BudgetExceededError when monthly limit exceeded.

        Validates: R14.4, R66.2
        """
        # Daily spend is fine, but monthly is over
        call_count = [0]

        async def mock_reservations(window_start):
            return Decimal("3.0000")

        async def mock_entries(window_start):
            nonlocal call_count
            call_count[0] += 1
            # daily entries: low; monthly entries: high
            if call_count[0] == 1:
                return Decimal("2.0000")  # daily entries
            return Decimal("490.0000")  # monthly entries

        cost_service._sum_active_reservations = mock_reservations
        cost_service._sum_cost_entries = mock_entries
        cost_service.get_budget_limits = _async_budget_limits()

        with pytest.raises(BudgetExceededError) as exc_info:
            await cost_service.reserve_cost(
                operation="training",
                estimated_amount_usd=Decimal("10.0000"),
            )

        error = exc_info.value
        assert error.code == "MONTHLY_BUDGET_EXCEEDED"
        assert error.period == "monthly"


# =============================================================================
# Tests: reserve_cost — fail-safe
# =============================================================================


class TestReserveCostFailSafe:
    """Tests for fail-safe behavior when ledger is unavailable."""

    @pytest.mark.asyncio
    async def test_raises_ledger_unavailable_on_db_error(
        self, cost_service, mock_db
    ):
        """reserve_cost raises LedgerUnavailableError on DB failure.

        Validates: R14.13, R66.7
        """
        from sqlalchemy.exc import OperationalError

        mock_db.execute = AsyncMock(
            side_effect=OperationalError(
                "SELECT", {}, Exception("connection refused")
            )
        )

        with pytest.raises(LedgerUnavailableError) as exc_info:
            await cost_service.reserve_cost(
                operation="image_generation",
                estimated_amount_usd=Decimal("1.0000"),
            )

        error = exc_info.value
        assert error.code == "LEDGER_UNAVAILABLE"
        assert "fail-safe" in error.message.lower()
        assert "never assume $0" in error.message.lower()


# =============================================================================
# Tests: reserve_cost — customer infrastructure (informational only)
# =============================================================================


class TestReserveCostCustomerInfrastructure:
    """Tests for customer_infrastructure cost tracking."""

    @pytest.mark.asyncio
    async def test_skips_budget_check_for_customer_infrastructure(
        self, cost_service, mock_db
    ):
        """Customer infrastructure costs are tracked but NOT budgeted.

        Validates: R14.15, R66.6
        """
        reservation = await cost_service.reserve_cost(
            operation="customer_gpu_job",
            estimated_amount_usd=Decimal("10.0000"),
            provider="customer_runpod",
            cost_classification=CostClassification.CUSTOMER_INFRASTRUCTURE.value,
        )

        assert reservation is not None
        assert (
            reservation.cost_classification
            == CostClassification.CUSTOMER_INFRASTRUCTURE.value
        )
        assert reservation.status == ReservationStatus.ACTIVE.value
        # Should still be tracked (added to DB)
        assert mock_db.add.call_count == 2  # reservation + entry
        assert mock_db.flush.call_count == 2


# =============================================================================
# Tests: reserve_cost — validation errors
# =============================================================================


class TestReserveCostValidation:
    """Tests for input validation on reserve_cost."""

    @pytest.mark.asyncio
    async def test_rejects_zero_amount(self, cost_service):
        """reserve_cost raises ValueError for zero amount."""
        with pytest.raises(ValueError, match="positive"):
            await cost_service.reserve_cost(
                operation="test",
                estimated_amount_usd=Decimal("0"),
            )

    @pytest.mark.asyncio
    async def test_rejects_negative_amount(self, cost_service):
        """reserve_cost raises ValueError for negative amount."""
        with pytest.raises(ValueError, match="positive"):
            await cost_service.reserve_cost(
                operation="test",
                estimated_amount_usd=Decimal("-1.0"),
            )

    @pytest.mark.asyncio
    async def test_rejects_empty_operation(self, cost_service):
        """reserve_cost raises ValueError for empty operation."""
        with pytest.raises(ValueError, match="required"):
            await cost_service.reserve_cost(
                operation="",
                estimated_amount_usd=Decimal("1.0"),
            )


# =============================================================================
# Tests: check_budget
# =============================================================================


class TestCheckBudget:
    """Tests for check_budget informational query."""

    @pytest.mark.asyncio
    async def test_returns_true_within_budget(self, cost_service, mock_db):
        """check_budget returns True when spend + amount <= limit."""
        cost_service._sum_active_reservations = _async_return(Decimal("5.0000"))
        cost_service._sum_cost_entries = _async_return(Decimal("5.0000"))
        cost_service.get_budget_limits = _async_budget_limits()

        result = await cost_service.check_budget(
            amount_usd=Decimal("5.0000"),
            period="daily",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_over_budget(self, cost_service, mock_db):
        """check_budget returns False when spend + amount > limit."""
        cost_service._sum_active_reservations = _async_return(Decimal("30.0000"))
        cost_service._sum_cost_entries = _async_return(Decimal("18.0000"))
        cost_service.get_budget_limits = _async_budget_limits()

        result = await cost_service.check_budget(
            amount_usd=Decimal("5.0000"),
            period="daily",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_raises_ledger_unavailable_on_db_error(
        self, cost_service, mock_db
    ):
        """check_budget raises LedgerUnavailableError on DB failure.

        Validates: R14.13, R66.7
        """
        from sqlalchemy.exc import OperationalError

        async def fail(*args, **kwargs):
            raise OperationalError("SELECT", {}, Exception("timeout"))

        cost_service._sum_active_reservations = fail

        with pytest.raises(LedgerUnavailableError):
            await cost_service.check_budget(
                amount_usd=Decimal("1.0000"),
                period="daily",
            )


# =============================================================================
# Tests: get_current_spend
# =============================================================================


class TestGetCurrentSpend:
    """Tests for spend calculation queries."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_activity(self, cost_service, mock_db):
        """get_current_spend returns 0 when no reservations or entries."""
        cost_service._sum_active_reservations = _async_return(Decimal("0"))
        cost_service._sum_cost_entries = _async_return(Decimal("0"))

        spend = await cost_service.get_current_spend("daily")
        assert spend == Decimal("0")

    @pytest.mark.asyncio
    async def test_sums_reservations_and_entries(self, cost_service, mock_db):
        """get_current_spend sums active reservations + cost entries."""
        cost_service._sum_active_reservations = _async_return(Decimal("5.0000"))
        cost_service._sum_cost_entries = _async_return(Decimal("3.0000"))

        spend = await cost_service.get_current_spend("daily")
        assert spend == Decimal("8.0000")

    @pytest.mark.asyncio
    async def test_never_returns_negative(self, cost_service, mock_db):
        """get_current_spend never returns negative (floor at 0)."""
        cost_service._sum_active_reservations = _async_return(Decimal("-2.0000"))
        cost_service._sum_cost_entries = _async_return(Decimal("-3.0000"))

        spend = await cost_service.get_current_spend("daily")
        assert spend >= Decimal("0")

    @pytest.mark.asyncio
    async def test_raises_ledger_unavailable_on_db_error(
        self, cost_service, mock_db
    ):
        """get_current_spend raises LedgerUnavailableError on DB failure."""
        from sqlalchemy.exc import OperationalError

        async def fail(window_start):
            raise OperationalError("SELECT", {}, Exception("down"))

        cost_service._sum_active_reservations = fail

        with pytest.raises(LedgerUnavailableError):
            await cost_service.get_current_spend("daily")


# =============================================================================
# Tests: get_budget_limits
# =============================================================================


class TestGetBudgetLimits:
    """Tests for budget limit resolution."""

    @pytest.mark.asyncio
    async def test_returns_defaults_from_settings(self, cost_service):
        """get_budget_limits returns platform defaults from settings."""
        limits = await cost_service.get_budget_limits()

        assert limits.daily_hard_usd > Decimal("0")
        assert limits.monthly_hard_usd > Decimal("0")
        assert limits.monthly_hard_usd > limits.daily_hard_usd


# =============================================================================
# Tests: BudgetExceededError
# =============================================================================


class TestBudgetExceededError:
    """Tests for BudgetExceededError structure."""

    def test_daily_budget_exceeded_error_code(self):
        """BudgetExceededError has DAILY_BUDGET_EXCEEDED code for daily."""
        error = BudgetExceededError(
            org_id=ORG_ID,
            requested_usd=Decimal("5.0"),
            current_spend_usd=Decimal("48.0"),
            limit_usd=Decimal("50.0"),
            period="daily",
        )
        assert error.code == "DAILY_BUDGET_EXCEEDED"
        assert isinstance(error, CostServiceError)

    def test_monthly_budget_exceeded_error_code(self):
        """BudgetExceededError has MONTHLY_BUDGET_EXCEEDED code for monthly."""
        error = BudgetExceededError(
            org_id=ORG_ID,
            requested_usd=Decimal("50.0"),
            current_spend_usd=Decimal("480.0"),
            limit_usd=Decimal("500.0"),
            period="monthly",
        )
        assert error.code == "MONTHLY_BUDGET_EXCEEDED"


# =============================================================================
# Tests: LedgerUnavailableError
# =============================================================================


class TestLedgerUnavailableError:
    """Tests for LedgerUnavailableError structure."""

    def test_fail_safe_message(self):
        """LedgerUnavailableError communicates fail-safe intent."""
        error = LedgerUnavailableError()
        assert error.code == "LEDGER_UNAVAILABLE"
        assert "fail-safe" in error.message.lower()
        assert "never assume $0" in error.message.lower()

    def test_custom_reason(self):
        """LedgerUnavailableError includes custom reason."""
        error = LedgerUnavailableError(reason="Connection timeout")
        assert "Connection timeout" in error.message


# =============================================================================
# Tests: CostService initialization
# =============================================================================


class TestCostServiceInit:
    """Tests for CostService construction."""

    def test_rejects_quarantined_org_id(self, mock_db):
        """CostService rejects the quarantined org_id (00000000...)."""
        from fastapi import HTTPException

        quarantined = UUID("00000000-0000-0000-0000-000000000000")

        with patch(
            "app.services.cost_service.validate_org_id",
            side_effect=HTTPException(status_code=422, detail="Quarantined"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                CostService(db=mock_db, org_id=quarantined)
            assert exc_info.value.status_code == 422
