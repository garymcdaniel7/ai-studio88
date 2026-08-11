"""Unit tests for CostService reconciliation methods.

Tests cover:
    - finalize_cost: records actual cost, releases hold, logs variance >20%
    - release_reservation: releases active reservation without cost
    - record_partial_failure: calculates partial GPU cost and finalizes
    - record_retry_cost: records independent cost entry per attempt
    - get_cost_summary: returns aggregated spend data
    - list_reservations: paginated reservation listing
    - list_entries: paginated cost entries listing

Requirements: R14.5, R14.6, R14.10, R14.11, R66.3, R66.4, R66.5
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

    def desc(self):
        return MagicMock()

    def asc(self):
        return MagicMock()


# Ensure CostReservation and CostEntry mock classes have desc() on created_at
# even when loaded from another test module's sys.modules cache
if "app.models.cost" in sys.modules:
    _existing_cost_module = sys.modules["app.models.cost"]
    _existing_res_cls = getattr(_existing_cost_module, "CostReservation", None)
    _existing_entry_cls = getattr(_existing_cost_module, "CostEntry", None)
    if _existing_res_cls and not hasattr(_existing_res_cls.created_at, "desc"):
        _existing_res_cls.created_at = _MockColumn()
    if _existing_entry_cls and not hasattr(_existing_entry_cls.created_at, "desc"):
        _existing_entry_cls.created_at = _MockColumn()


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
    provider = _MockColumn()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if "id" not in kwargs:
            self.id = uuid4()


_mock_models_cost = ModuleType("app.models.cost")
_mock_models_cost.CostReservation = _MockCostReservation  # type: ignore[attr-defined]
_mock_models_cost.CostEntry = _MockCostEntry  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.cost", _mock_models_cost)

from app.schemas.cost import CostClassification, ReservationStatus
from app.services.cost_service import (
    BudgetLimits,
    CostService,
    LedgerUnavailableError,
)

# =============================================================================
# Fixtures
# =============================================================================

ORG_ID = UUID("11111111-1111-1111-1111-111111111111")
JOB_ID = UUID("33333333-3333-3333-3333-333333333333")
RESERVATION_ID = UUID("44444444-4444-4444-4444-444444444444")


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


def _make_active_reservation(
    reservation_id: UUID = RESERVATION_ID,
    amount: Decimal = Decimal("5.0000"),
    job_id: UUID | None = JOB_ID,
) -> _MockCostReservation:
    """Create a mock active reservation for testing."""
    return _MockCostReservation(
        id=reservation_id,
        org_id=ORG_ID,
        job_id=job_id,
        operation="image_generation",
        reserved_amount_usd=amount,
        actual_amount_usd=None,
        cost_classification=CostClassification.MANAGED_COMPUTE.value,
        status=ReservationStatus.ACTIVE.value,
        provider="vast.ai",
        expires_at=datetime.now(UTC) + timedelta(hours=4),
        finalized_at=None,
    )


# =============================================================================
# Tests: finalize_cost
# =============================================================================


@pytest.mark.unit
class TestFinalizeCost:
    """Tests for finalize_cost — R14.10, R66.3."""

    @pytest.mark.asyncio
    async def test_finalizes_with_actual_cost(self, cost_service, mock_db):
        """finalize_cost records actual cost and releases hold."""
        reservation = _make_active_reservation()
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        result = await cost_service.finalize_cost(
            reservation_id=RESERVATION_ID,
            actual_amount_usd=Decimal("4.5000"),
        )

        assert result.status == ReservationStatus.FINALIZED.value
        assert result.actual_amount_usd == Decimal("4.5000")
        assert result.finalized_at is not None
        # Should add actual entry + release entry
        assert mock_db.add.call_count == 2
        assert mock_db.flush.call_count == 1

    @pytest.mark.asyncio
    async def test_logs_variance_above_20_percent(self, cost_service, mock_db):
        """finalize_cost logs anomaly when variance exceeds 20%.

        Validates: R14.10 (log variance >20% as cost anomaly)
        """
        reservation = _make_active_reservation(amount=Decimal("5.0000"))
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        # 50% variance (actual 7.5 vs reserved 5.0)
        with patch("app.services.cost_service.logger") as mock_logger:
            await cost_service.finalize_cost(
                reservation_id=RESERVATION_ID,
                actual_amount_usd=Decimal("7.5000"),
            )
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "cost_variance_anomaly"

    @pytest.mark.asyncio
    async def test_no_anomaly_log_within_20_percent(self, cost_service, mock_db):
        """finalize_cost does NOT log anomaly when variance <= 20%."""
        reservation = _make_active_reservation(amount=Decimal("5.0000"))
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        # 10% variance (actual 5.5 vs reserved 5.0)
        with patch("app.services.cost_service.logger") as mock_logger:
            await cost_service.finalize_cost(
                reservation_id=RESERVATION_ID,
                actual_amount_usd=Decimal("5.5000"),
            )
            mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_already_finalized(self, cost_service, mock_db):
        """finalize_cost raises ValueError for already-finalized reservation."""
        reservation = _make_active_reservation()
        reservation.status = ReservationStatus.FINALIZED.value
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        with pytest.raises(ValueError, match="terminal state"):
            await cost_service.finalize_cost(
                reservation_id=RESERVATION_ID,
                actual_amount_usd=Decimal("4.0000"),
            )

    @pytest.mark.asyncio
    async def test_rejects_not_found(self, cost_service, mock_db):
        """finalize_cost raises ValueError when reservation not found."""
        cost_service._get_reservation = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await cost_service.finalize_cost(
                reservation_id=uuid4(),
                actual_amount_usd=Decimal("4.0000"),
            )

    @pytest.mark.asyncio
    async def test_rejects_negative_actual_amount(self, cost_service, mock_db):
        """finalize_cost raises ValueError for negative amount."""
        with pytest.raises(ValueError, match="negative"):
            await cost_service.finalize_cost(
                reservation_id=RESERVATION_ID,
                actual_amount_usd=Decimal("-1.0000"),
            )

    @pytest.mark.asyncio
    async def test_includes_provider_receipt(self, cost_service, mock_db):
        """finalize_cost includes provider_receipt in ledger entry description."""
        reservation = _make_active_reservation()
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        await cost_service.finalize_cost(
            reservation_id=RESERVATION_ID,
            actual_amount_usd=Decimal("4.5000"),
            provider_receipt="inv-12345",
        )

        # Check that the actual entry description includes receipt
        added_objects = [call[0][0] for call in mock_db.add.call_args_list]
        actual_entry = next(
            (obj for obj in added_objects if getattr(obj, "entry_type", None) == "actual"),
            None,
        )
        assert actual_entry is not None
        assert "inv-12345" in actual_entry.description


# =============================================================================
# Tests: release_reservation
# =============================================================================


@pytest.mark.unit
class TestReleaseReservation:
    """Tests for release_reservation — R66.3."""

    @pytest.mark.asyncio
    async def test_releases_active_reservation(self, cost_service, mock_db):
        """release_reservation marks reservation as released."""
        reservation = _make_active_reservation()
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        result = await cost_service.release_reservation(
            reservation_id=RESERVATION_ID,
            reason="job_cancelled",
        )

        assert result.status == ReservationStatus.RELEASED.value
        assert result.finalized_at is not None
        # Should add a release entry
        assert mock_db.add.call_count == 1

    @pytest.mark.asyncio
    async def test_release_entry_has_negative_amount(self, cost_service, mock_db):
        """Release entry has negative amount to offset the hold."""
        reservation = _make_active_reservation(amount=Decimal("5.0000"))
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        await cost_service.release_reservation(
            reservation_id=RESERVATION_ID,
        )

        added_objects = [call[0][0] for call in mock_db.add.call_args_list]
        release_entry = added_objects[0]
        assert release_entry.entry_type == "release"
        assert release_entry.amount_usd == Decimal("-5.0000")

    @pytest.mark.asyncio
    async def test_includes_reason_in_description(self, cost_service, mock_db):
        """Release entry includes reason when provided."""
        reservation = _make_active_reservation()
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        await cost_service.release_reservation(
            reservation_id=RESERVATION_ID,
            reason="job_cancelled",
        )

        added_objects = [call[0][0] for call in mock_db.add.call_args_list]
        release_entry = added_objects[0]
        assert "job_cancelled" in release_entry.description

    @pytest.mark.asyncio
    async def test_rejects_already_released(self, cost_service, mock_db):
        """release_reservation raises ValueError for already-released reservation."""
        reservation = _make_active_reservation()
        reservation.status = ReservationStatus.RELEASED.value
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        with pytest.raises(ValueError, match="terminal state"):
            await cost_service.release_reservation(
                reservation_id=RESERVATION_ID,
            )

    @pytest.mark.asyncio
    async def test_rejects_not_found(self, cost_service, mock_db):
        """release_reservation raises ValueError when not found."""
        cost_service._get_reservation = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await cost_service.release_reservation(
                reservation_id=uuid4(),
            )


# =============================================================================
# Tests: record_partial_failure
# =============================================================================


@pytest.mark.unit
class TestRecordPartialFailure:
    """Tests for record_partial_failure — R14.11, R66.4."""

    @pytest.mark.asyncio
    async def test_records_partial_gpu_cost(self, cost_service, mock_db):
        """record_partial_failure calculates and records partial GPU cost.

        Failed jobs are NOT assumed $0 — partial cost is always recorded.
        Validates: R14.11, R66.4
        """
        reservation = _make_active_reservation(amount=Decimal("5.0000"))
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        # 600 seconds at $1.00/hr = $0.1667
        result = await cost_service.record_partial_failure(
            reservation_id=RESERVATION_ID,
            partial_gpu_seconds=600.0,
            gpu_rate_per_hour=Decimal("1.00"),
        )

        assert result.status == ReservationStatus.FINALIZED.value
        assert result.actual_amount_usd == Decimal("0.1667")

    @pytest.mark.asyncio
    async def test_uses_default_rate_when_not_provided(
        self, cost_service, mock_db
    ):
        """record_partial_failure uses $0.50/hr default when rate not given."""
        reservation = _make_active_reservation()
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        # 3600 seconds at default $0.50/hr = $0.50
        result = await cost_service.record_partial_failure(
            reservation_id=RESERVATION_ID,
            partial_gpu_seconds=3600.0,
        )

        assert result.actual_amount_usd == Decimal("0.5000")

    @pytest.mark.asyncio
    async def test_rejects_negative_gpu_seconds(self, cost_service, mock_db):
        """record_partial_failure rejects negative GPU seconds."""
        with pytest.raises(ValueError, match="negative"):
            await cost_service.record_partial_failure(
                reservation_id=RESERVATION_ID,
                partial_gpu_seconds=-100.0,
            )

    @pytest.mark.asyncio
    async def test_zero_gpu_seconds_results_in_zero_cost(
        self, cost_service, mock_db
    ):
        """record_partial_failure with 0 seconds results in $0.0000."""
        reservation = _make_active_reservation()
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        result = await cost_service.record_partial_failure(
            reservation_id=RESERVATION_ID,
            partial_gpu_seconds=0.0,
        )

        assert result.actual_amount_usd == Decimal("0.0000")


# =============================================================================
# Tests: record_retry_cost
# =============================================================================


@pytest.mark.unit
class TestRecordRetryCost:
    """Tests for record_retry_cost — R14.11, R66.5."""

    @pytest.mark.asyncio
    async def test_creates_independent_entry(self, cost_service, mock_db):
        """record_retry_cost creates a separate cost entry per attempt.

        Validates: R14.11, R66.5 (each retry gets its own entry)
        """
        reservation = _make_active_reservation()
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        entry = await cost_service.record_retry_cost(
            reservation_id=RESERVATION_ID,
            attempt_number=2,
            amount_usd=Decimal("1.5000"),
        )

        assert entry.entry_type == "actual"
        assert entry.amount_usd == Decimal("1.5000")
        assert entry.reservation_id == RESERVATION_ID
        assert "attempt 2" in entry.description.lower()
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_links_to_parent_reservation(self, cost_service, mock_db):
        """Retry entry is linked to the parent reservation."""
        reservation = _make_active_reservation()
        cost_service._get_reservation = AsyncMock(return_value=reservation)

        entry = await cost_service.record_retry_cost(
            reservation_id=RESERVATION_ID,
            attempt_number=1,
            amount_usd=Decimal("2.0000"),
        )

        assert entry.reservation_id == RESERVATION_ID
        assert entry.job_id == JOB_ID
        assert entry.org_id == ORG_ID

    @pytest.mark.asyncio
    async def test_rejects_negative_amount(self, cost_service, mock_db):
        """record_retry_cost rejects negative amount."""
        with pytest.raises(ValueError, match="negative"):
            await cost_service.record_retry_cost(
                reservation_id=RESERVATION_ID,
                attempt_number=1,
                amount_usd=Decimal("-1.0000"),
            )

    @pytest.mark.asyncio
    async def test_rejects_zero_attempt_number(self, cost_service, mock_db):
        """record_retry_cost rejects attempt_number < 1."""
        with pytest.raises(ValueError, match="must be >= 1"):
            await cost_service.record_retry_cost(
                reservation_id=RESERVATION_ID,
                attempt_number=0,
                amount_usd=Decimal("1.0000"),
            )

    @pytest.mark.asyncio
    async def test_rejects_not_found_reservation(self, cost_service, mock_db):
        """record_retry_cost raises ValueError when reservation not found."""
        cost_service._get_reservation = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await cost_service.record_retry_cost(
                reservation_id=uuid4(),
                attempt_number=1,
                amount_usd=Decimal("1.0000"),
            )


# =============================================================================
# Tests: get_cost_summary
# =============================================================================


@pytest.mark.unit
class TestGetCostSummary:
    """Tests for get_cost_summary — R14.5."""

    @pytest.mark.asyncio
    async def test_returns_complete_summary(self, cost_service, mock_db):
        """get_cost_summary returns all expected fields.

        Validates: R14.5 (summary endpoint with breakdowns)
        """
        cost_service.get_current_spend = AsyncMock(
            side_effect=[Decimal("10.0000"), Decimal("150.0000")]
        )
        cost_service.get_budget_limits = AsyncMock(
            return_value=BudgetLimits(
                daily_hard_usd=Decimal("50.0"),
                monthly_hard_usd=Decimal("500.0"),
            )
        )
        cost_service._get_active_reservations_total = AsyncMock(
            return_value=Decimal("5.0000")
        )
        cost_service._breakdown_by_classification = AsyncMock(
            return_value={"managed_compute": Decimal("100.0000")}
        )
        cost_service._breakdown_by_provider = AsyncMock(
            return_value={"vast.ai": Decimal("80.0000"), "runpod": Decimal("20.0000")}
        )

        summary = await cost_service.get_cost_summary()

        assert summary["today_spend_usd"] == Decimal("10.0000")
        assert summary["month_spend_usd"] == Decimal("150.0000")
        assert summary["daily_budget_usd"] == Decimal("50.0")
        assert summary["monthly_budget_usd"] == Decimal("500.0")
        assert summary["active_reservations_usd"] == Decimal("5.0000")
        assert "managed_compute" in summary["breakdown_by_classification"]
        assert "vast.ai" in summary["breakdown_by_provider"]

    @pytest.mark.asyncio
    async def test_raises_ledger_unavailable_on_failure(
        self, cost_service, mock_db
    ):
        """get_cost_summary raises LedgerUnavailableError on DB failure."""
        from sqlalchemy.exc import OperationalError

        cost_service.get_current_spend = AsyncMock(
            side_effect=OperationalError("SELECT", {}, Exception("down"))
        )

        with pytest.raises(LedgerUnavailableError):
            await cost_service.get_cost_summary()


# =============================================================================
# Tests: list_reservations
# =============================================================================


@pytest.mark.unit
class TestListReservations:
    """Tests for list_reservations pagination."""

    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, cost_service, mock_db):
        """list_reservations returns paginated results."""
        mock_reservations = [_make_active_reservation()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_reservations
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.scalar = AsyncMock(return_value=1)

        items, total = await cost_service.list_reservations(
            limit=20, offset=0
        )

        assert total == 1
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_supports_status_filter(self, cost_service, mock_db):
        """list_reservations filters by status when provided."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.scalar = AsyncMock(return_value=0)

        items, total = await cost_service.list_reservations(
            limit=10, offset=0, status_filter="active"
        )

        assert total == 0
        assert items == []


# =============================================================================
# Tests: list_entries
# =============================================================================


@pytest.mark.unit
class TestListEntries:
    """Tests for list_entries pagination."""

    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, cost_service, mock_db):
        """list_entries returns paginated results."""
        mock_entry = _MockCostEntry(
            org_id=ORG_ID,
            entry_type="actual",
            amount_usd=Decimal("1.5000"),
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_entry]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.scalar = AsyncMock(return_value=1)

        items, total = await cost_service.list_entries(
            limit=20, offset=0
        )

        assert total == 1
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_supports_entry_type_filter(self, cost_service, mock_db):
        """list_entries filters by entry_type when provided."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.scalar = AsyncMock(return_value=0)

        items, total = await cost_service.list_entries(
            limit=10, offset=0, entry_type_filter="actual"
        )

        assert total == 0
        assert items == []
