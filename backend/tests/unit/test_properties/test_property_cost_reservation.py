"""Property tests for Cost Reservation Budget Invariant.

Property 3: Cost Reservation Budget Invariant (R14.9, R66.1, R66.2, R89.2)
    For any sequence of cost reservations against a tenant's budget, the sum
    of active reservations plus actual spend SHALL never exceed the tenant's
    hard budget limit. The system either succeeds (within budget) or raises
    BudgetExceededError. Never allows over-budget.

Validates: Requirements R14.9, R66.1, R66.2, R89.2

# Feature: production-revamp, Property 3: Cost Reservation Budget Invariant

Run with:
    pytest backend/tests/unit/test_properties/test_property_cost_reservation.py -v
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st


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
_sa_mock.Numeric = MagicMock
_sa_mock.func = MagicMock()
_sa_mock.select = MagicMock(return_value=MagicMock(
    where=MagicMock(return_value=MagicMock(
        with_for_update=MagicMock(return_value=MagicMock())
    ))
))
_sa_mock.update = MagicMock()
_sa_mock.and_ = lambda *args: args

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

_mock_db_base = ModuleType("app.db.base")


class _MockBase:
    pass


_mock_db_base.Base = _MockBase  # type: ignore[attr-defined]
_mock_db_base.TimestampMixin = type("TimestampMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.UUIDMixin = type("UUIDMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.TenantMixin = type("TenantMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.SoftDeleteMixin = type("SoftDeleteMixin", (), {})  # type: ignore[attr-defined]
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

# Mock cost models with class-level attributes for SQLAlchemy column access
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
    """Mock CostReservation with class-level column attributes."""

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
            object.__setattr__(self, "id", uuid4())


class _MockCostEntry:
    """Mock CostEntry with class-level column attributes."""

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
            object.__setattr__(self, "id", uuid4())


_mock_models_cost.CostReservation = _MockCostReservation  # type: ignore[attr-defined]
_mock_models_cost.CostEntry = _MockCostEntry  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.cost", _mock_models_cost)


# Now import application modules
from app.schemas.cost import CostClassification, ReservationStatus
from app.services.cost_service import (
    BudgetExceededError,
    BudgetLimits,
    CostService,
    LedgerUnavailableError,
)


# =============================================================================
# Hypothesis Strategies
# =============================================================================

# Reservation amounts: Decimal between 0.01 and 50.00
reservation_amount_strategy = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("50.00"),
    places=4,
    allow_nan=False,
    allow_infinity=False,
)

# Budget limits for daily (reasonable range)
daily_budget_strategy = st.decimals(
    min_value=Decimal("10.00"),
    max_value=Decimal("500.00"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

# Budget limits for monthly (always >= daily)
monthly_budget_strategy = st.decimals(
    min_value=Decimal("100.00"),
    max_value=Decimal("5000.00"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


# =============================================================================
# In-Memory Budget Tracker (oracle model)
# =============================================================================


class InMemoryBudgetTracker:
    """Oracle model tracking budget state to verify invariants.

    Simulates the aggregate state the CostService would see from the DB:
    active reservations and finalized spend. Verifies the budget invariant
    at every step.
    """

    def __init__(self, daily_limit: Decimal, monthly_limit: Decimal) -> None:
        self.daily_limit = daily_limit
        self.monthly_limit = monthly_limit
        self.active_reservations: dict[UUID, Decimal] = {}
        self.finalized_spend: Decimal = Decimal("0")

    @property
    def total_committed(self) -> Decimal:
        """Sum of active reservations + finalized actual spend."""
        reservations_total = sum(
            self.active_reservations.values(), Decimal("0")
        )
        return reservations_total + self.finalized_spend

    def can_reserve(self, amount: Decimal) -> bool:
        """Check if a reservation fits within BOTH daily and monthly."""
        new_total = self.total_committed + amount
        return new_total <= self.daily_limit and new_total <= self.monthly_limit

    def reserve(self, reservation_id: UUID, amount: Decimal) -> None:
        """Record a new active reservation."""
        self.active_reservations[reservation_id] = amount

    def finalize(self, reservation_id: UUID, actual_amount: Decimal) -> None:
        """Finalize: remove reservation hold, add actual spend."""
        if reservation_id in self.active_reservations:
            del self.active_reservations[reservation_id]
            self.finalized_spend += actual_amount

    def release(self, reservation_id: UUID) -> None:
        """Release: remove hold, no spend recorded."""
        self.active_reservations.pop(reservation_id, None)


# =============================================================================
# Helper: create CostService with mocked internals
# =============================================================================


def _make_service(
    org_id: UUID,
    daily_limit: Decimal,
    monthly_limit: Decimal,
    current_spend_daily: Decimal = Decimal("0"),
    current_spend_monthly: Decimal = Decimal("0"),
):
    """Create a CostService with mocked DB that returns specified spend."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock())
    mock_db.scalar = AsyncMock(return_value=Decimal("0"))
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    service = CostService(db=mock_db, org_id=org_id)

    # Patch internal methods to return controlled values
    async def _get_budget_limits():
        return BudgetLimits(
            daily_hard_usd=daily_limit,
            monthly_hard_usd=monthly_limit,
        )

    service.get_budget_limits = _get_budget_limits  # type: ignore[method-assign]

    return service, mock_db


# =============================================================================
# Property 3: Cost Reservation Budget Invariant
# Feature: production-revamp, Property 3
# =============================================================================


@pytest.mark.unit
class TestProperty3_CostReservationBudgetInvariant:
    """Property 3: Active reservations + actual spend never exceeds hard limit.

    The CostService uses atomic budget check + reservation creation. If a
    reservation would exceed the limit, BudgetExceededError is raised.
    The invariant holds at every point in any sequence of operations.

    **Validates: Requirements R14.9, R66.1, R66.2, R89.2**
    """

    @settings(max_examples=100)
    @given(
        amounts=st.lists(
            reservation_amount_strategy,
            min_size=1,
            max_size=15,
        ),
        daily_limit=daily_budget_strategy,
        monthly_limit=monthly_budget_strategy,
    )
    @pytest.mark.asyncio
    async def test_sequential_reservations_never_exceed_daily_budget(
        self,
        amounts: list[Decimal],
        daily_limit: Decimal,
        monthly_limit: Decimal,
    ) -> None:
        """Sequential reservations never exceed daily hard budget limit.

        **Validates: Requirements R14.9, R66.1, R66.2**

        For any sequence of reserve_cost calls, the total committed
        (active reservations + spend) NEVER exceeds the daily hard limit.
        The system either succeeds or raises BudgetExceededError.
        """
        assume(monthly_limit >= daily_limit)

        org_id = uuid4()
        tracker = InMemoryBudgetTracker(daily_limit, monthly_limit)
        service, mock_db = _make_service(org_id, daily_limit, monthly_limit)

        for amount in amounts:
            # Mock _sum_active_reservations and _sum_cost_entries to
            # return the tracker's current state
            reservations_sum = sum(
                tracker.active_reservations.values(), Decimal("0")
            )
            finalized_sum = tracker.finalized_spend

            async def _mock_reservations(ws):
                return reservations_sum

            async def _mock_entries(ws):
                return finalized_sum

            service._sum_active_reservations = _mock_reservations  # type: ignore[method-assign]
            service._sum_cost_entries = _mock_entries  # type: ignore[method-assign]

            try:
                reservation = await service.reserve_cost(
                    operation="image_generation",
                    estimated_amount_usd=amount,
                    cost_classification=CostClassification.MANAGED_COMPUTE.value,
                )
                # Reservation succeeded — track it in oracle
                tracker.reserve(reservation.id, amount)

            except BudgetExceededError:
                # Correctly rejected — would have exceeded budget
                pass

            # INVARIANT CHECK: total committed never exceeds daily limit
            assert tracker.total_committed <= daily_limit, (
                f"Budget invariant violated! "
                f"committed={tracker.total_committed} > "
                f"daily_limit={daily_limit}"
            )

    @settings(max_examples=100)
    @given(
        amounts=st.lists(
            reservation_amount_strategy,
            min_size=1,
            max_size=15,
        ),
        daily_limit=daily_budget_strategy,
        monthly_limit=monthly_budget_strategy,
    )
    @pytest.mark.asyncio
    async def test_sequential_reservations_never_exceed_monthly_budget(
        self,
        amounts: list[Decimal],
        daily_limit: Decimal,
        monthly_limit: Decimal,
    ) -> None:
        """Sequential reservations never exceed monthly hard budget limit.

        **Validates: Requirements R14.9, R66.2, R89.2**

        For any sequence of reserve_cost calls, the total committed
        NEVER exceeds the monthly hard limit either.
        """
        assume(monthly_limit >= daily_limit)

        org_id = uuid4()
        tracker = InMemoryBudgetTracker(daily_limit, monthly_limit)
        service, mock_db = _make_service(org_id, daily_limit, monthly_limit)

        for amount in amounts:
            reservations_sum = sum(
                tracker.active_reservations.values(), Decimal("0")
            )
            finalized_sum = tracker.finalized_spend

            async def _mock_reservations(ws):
                return reservations_sum

            async def _mock_entries(ws):
                return finalized_sum

            service._sum_active_reservations = _mock_reservations  # type: ignore[method-assign]
            service._sum_cost_entries = _mock_entries  # type: ignore[method-assign]

            try:
                reservation = await service.reserve_cost(
                    operation="video_generation",
                    estimated_amount_usd=amount,
                    cost_classification=CostClassification.MANAGED_COMPUTE.value,
                )
                tracker.reserve(reservation.id, amount)
            except BudgetExceededError:
                pass

            # INVARIANT CHECK: total committed never exceeds monthly limit
            assert tracker.total_committed <= monthly_limit, (
                f"Monthly budget invariant violated! "
                f"committed={tracker.total_committed} > "
                f"monthly_limit={monthly_limit}"
            )

    @settings(max_examples=100)
    @given(
        existing_spend=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("200.00"),
            places=4,
            allow_nan=False,
            allow_infinity=False,
        ),
        request_amount=reservation_amount_strategy,
        daily_limit=daily_budget_strategy,
        monthly_limit=monthly_budget_strategy,
    )
    @pytest.mark.asyncio
    async def test_reservation_with_existing_spend_respects_limit(
        self,
        existing_spend: Decimal,
        request_amount: Decimal,
        daily_limit: Decimal,
        monthly_limit: Decimal,
    ) -> None:
        """A reservation with pre-existing spend respects the budget limit.

        **Validates: Requirements R14.9, R66.1, R66.2**

        When there is already spend recorded, a new reservation is only
        allowed if existing_spend + request_amount <= limit. If it would
        exceed, BudgetExceededError is raised.
        """
        assume(monthly_limit >= daily_limit)

        org_id = uuid4()
        service, mock_db = _make_service(org_id, daily_limit, monthly_limit)

        # Mock internals to reflect existing spend
        async def _mock_reservations(ws):
            return existing_spend

        async def _mock_entries(ws):
            return Decimal("0")

        service._sum_active_reservations = _mock_reservations  # type: ignore[method-assign]
        service._sum_cost_entries = _mock_entries  # type: ignore[method-assign]

        try:
            await service.reserve_cost(
                operation="lora_training",
                estimated_amount_usd=request_amount,
                cost_classification=CostClassification.MANAGED_COMPUTE.value,
            )
            # Succeeded — verify the total is within budget
            total_after = existing_spend + request_amount
            assert total_after <= daily_limit, (
                f"Reservation succeeded but total {total_after} > "
                f"daily limit {daily_limit}"
            )
            assert total_after <= monthly_limit, (
                f"Reservation succeeded but total {total_after} > "
                f"monthly limit {monthly_limit}"
            )
        except BudgetExceededError as exc:
            # Rejected — verify it WOULD have exceeded at least one limit
            total_if_allowed = existing_spend + request_amount
            assert (
                total_if_allowed > daily_limit
                or total_if_allowed > monthly_limit
            ), (
                f"BudgetExceededError raised but total {total_if_allowed} "
                f"<= both limits (daily={daily_limit}, monthly={monthly_limit})"
            )

    @settings(max_examples=100)
    @given(
        amounts=st.lists(
            reservation_amount_strategy,
            min_size=1,
            max_size=10,
        ),
        daily_limit=daily_budget_strategy,
        monthly_limit=monthly_budget_strategy,
    )
    @pytest.mark.asyncio
    async def test_customer_infrastructure_never_affects_budget(
        self,
        amounts: list[Decimal],
        daily_limit: Decimal,
        monthly_limit: Decimal,
    ) -> None:
        """Customer infrastructure costs bypass budget enforcement.

        **Validates: Requirements R14.9, R89.2**

        Customer-infrastructure costs are tracked informationally but do NOT
        count against the tenant's hard budget limit. Reserving as
        customer_infrastructure always succeeds regardless of budget state.
        """
        assume(monthly_limit >= daily_limit)

        org_id = uuid4()
        service, mock_db = _make_service(org_id, daily_limit, monthly_limit)

        # Fill the budget entirely
        async def _mock_reservations(ws):
            return daily_limit  # Budget is completely consumed

        async def _mock_entries(ws):
            return Decimal("0")

        service._sum_active_reservations = _mock_reservations  # type: ignore[method-assign]
        service._sum_cost_entries = _mock_entries  # type: ignore[method-assign]

        for amount in amounts:
            # Customer infrastructure should ALWAYS succeed even when
            # managed_compute budget is fully consumed
            reservation = await service.reserve_cost(
                operation="customer_gpu_job",
                estimated_amount_usd=amount,
                cost_classification=CostClassification.CUSTOMER_INFRASTRUCTURE.value,
            )
            assert reservation is not None
            assert (
                reservation.cost_classification
                == CostClassification.CUSTOMER_INFRASTRUCTURE.value
            )

    @settings(max_examples=100)
    @given(
        reserve_amounts=st.lists(
            reservation_amount_strategy,
            min_size=2,
            max_size=8,
        ),
        daily_limit=daily_budget_strategy,
        monthly_limit=monthly_budget_strategy,
    )
    @pytest.mark.asyncio
    async def test_budget_invariant_holds_after_releases(
        self,
        reserve_amounts: list[Decimal],
        daily_limit: Decimal,
        monthly_limit: Decimal,
    ) -> None:
        """Budget invariant holds through reserve/release sequences.

        **Validates: Requirements R14.9, R66.1, R66.2, R89.2**

        After releasing a reservation, the freed budget is available for
        new reservations. The invariant (sum <= limit) holds at every step
        even through mixed reserve/release operations.
        """
        assume(monthly_limit >= daily_limit)

        org_id = uuid4()
        tracker = InMemoryBudgetTracker(daily_limit, monthly_limit)
        service, mock_db = _make_service(org_id, daily_limit, monthly_limit)

        successful_reservations: list[tuple[UUID, Decimal]] = []

        for i, amount in enumerate(reserve_amounts):
            reservations_sum = sum(
                tracker.active_reservations.values(), Decimal("0")
            )
            finalized_sum = tracker.finalized_spend

            async def _mock_reservations(ws, _r=reservations_sum):
                return _r

            async def _mock_entries(ws, _e=finalized_sum):
                return _e

            service._sum_active_reservations = _mock_reservations  # type: ignore[method-assign]
            service._sum_cost_entries = _mock_entries  # type: ignore[method-assign]

            try:
                reservation = await service.reserve_cost(
                    operation="batch_generation",
                    estimated_amount_usd=amount,
                    cost_classification=CostClassification.MANAGED_COMPUTE.value,
                )
                tracker.reserve(reservation.id, amount)
                successful_reservations.append((reservation.id, amount))
            except BudgetExceededError:
                pass

            # Release every other successful reservation to free budget
            if i % 2 == 1 and successful_reservations:
                released_id, released_amount = successful_reservations.pop(0)
                tracker.release(released_id)

            # INVARIANT CHECK at every step
            assert tracker.total_committed <= daily_limit, (
                f"Budget invariant violated after step {i}! "
                f"committed={tracker.total_committed} > "
                f"daily_limit={daily_limit}"
            )
            assert tracker.total_committed <= monthly_limit, (
                f"Monthly budget invariant violated after step {i}! "
                f"committed={tracker.total_committed} > "
                f"monthly_limit={monthly_limit}"
            )
