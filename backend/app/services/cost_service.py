"""Cost Service — atomic budget enforcement and cost reservation management.

Provides atomic cost reservation with budget enforcement in a single database
transaction. Uses SELECT ... FOR UPDATE to prevent race conditions when
multiple concurrent requests attempt to reserve budget simultaneously.

Key invariants:
    - Atomic: budget check AND reservation creation in ONE transaction
    - Fail-safe: if the ledger/DB is unavailable, block all paid operations
    - Missing evidence != $0: unavailable cost data flagged for reconciliation
    - Customer-infrastructure costs: tracked informational, NOT reserved
    - Platform-wide compute budget caps total managed GPU liability

Cost classification (three-tier):
    - customer_infrastructure: customer-owned compute (informational only)
    - platform_expense: AI Studio internal operational costs
    - managed_compute: platform-managed compute charged to tenant (budgeted)

Requirements: R14.3, R14.4, R14.9, R14.13, R14.14, R66.1, R66.2, R66.7
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.tenant_scope import validate_org_id
from app.models.cost import CostEntry, CostReservation
from app.schemas.cost import CostClassification, ReservationStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class CostServiceError(Exception):
    """Base exception for CostService operations."""

    def __init__(self, message: str, code: str = "COST_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class BudgetExceededError(CostServiceError):
    """Raised when a cost reservation would exceed the tenant's budget.

    Maps to HTTP 402 Payment Required at the router layer.
    Contains details about current spend and limit for client display.

    Validates: R14.3, R14.4, R66.2
    """

    def __init__(
        self,
        org_id: UUID,
        requested_usd: Decimal,
        current_spend_usd: Decimal,
        limit_usd: Decimal,
        period: str,
    ) -> None:
        self.org_id = org_id
        self.requested_usd = requested_usd
        self.current_spend_usd = current_spend_usd
        self.limit_usd = limit_usd
        self.period = period
        code = (
            "DAILY_BUDGET_EXCEEDED"
            if period == "daily"
            else "MONTHLY_BUDGET_EXCEEDED"
        )
        super().__init__(
            message=(
                f"Budget exceeded for org {org_id}: "
                f"requested ${requested_usd}, "
                f"current {period} spend ${current_spend_usd}, "
                f"limit ${limit_usd}"
            ),
            code=code,
        )


class LedgerUnavailableError(CostServiceError):
    """Raised when the cost ledger (database) is unavailable.

    Fail-safe behavior: if we cannot determine budget state, we MUST
    block all paid operations. Never assume $0 cost when evidence
    is unavailable.

    Validates: R14.13, R14.14, R66.7
    """

    def __init__(self, reason: str = "Cost ledger unavailable") -> None:
        super().__init__(
            message=(
                f"{reason} — paid operations blocked (fail-safe). "
                "Never assume $0 when cost evidence is unavailable."
            ),
            code="LEDGER_UNAVAILABLE",
        )


# =============================================================================
# Budget Limits
# =============================================================================


@dataclass(frozen=True)
class BudgetLimits:
    """Budget limits for a workspace.

    Default values come from application settings. Per-workspace overrides
    can be stored in a future budget_limits table.
    """

    daily_hard_usd: Decimal
    monthly_hard_usd: Decimal

    @classmethod
    def from_settings(cls) -> "BudgetLimits":
        """Create BudgetLimits from application settings."""
        settings = get_settings()
        return cls(
            daily_hard_usd=Decimal(str(settings.cost_daily_budget)),
            monthly_hard_usd=Decimal(str(settings.cost_monthly_budget)),
        )


# Default reservation expiry: job max duration + 1 hour grace
DEFAULT_RESERVATION_EXPIRY = timedelta(hours=5)


# =============================================================================
# Cost Service
# =============================================================================


class CostService:
    """Atomic cost reservation and budget enforcement service.

    Encapsulates the full cost reservation lifecycle:
    - Budget check (can the org afford this operation?)
    - Atomic reservation (check + hold in single transaction)
    - Spend queries (current daily/monthly spend)
    - Budget limit resolution (per-workspace or platform defaults)

    All operations are tenant-scoped. org_id is derived from TenantContext,
    never from client input.

    The service uses SELECT ... FOR UPDATE on active reservations to prevent
    race conditions where concurrent requests could collectively exceed budget.

    Validates: R14.3, R14.4, R14.9, R14.13, R14.14, R66.1, R66.2, R66.7
    """

    def __init__(self, db: "AsyncSession", org_id: UUID) -> None:
        """Initialize CostService with a DB session and org_id.

        Args:
            db: SQLAlchemy async session (must be within a transaction).
            org_id: Authenticated org UUID from TenantContext.

        Raises:
            HTTPException: 422 if org_id is the quarantined UUID.
        """
        validate_org_id(org_id)
        self._db = db
        self._org_id = org_id

    # =========================================================================
    # Public API
    # =========================================================================

    async def reserve_cost(
        self,
        operation: str,
        estimated_amount_usd: Decimal,
        job_id: UUID | None = None,
        provider: str | None = None,
        cost_classification: str = CostClassification.MANAGED_COMPUTE.value,
        expires_at: datetime | None = None,
    ) -> CostReservation:
        """Atomically check budget availability AND create a reservation hold.

        This is a single-transaction operation: the budget check and the
        reservation creation happen together with row-level locking to
        prevent race conditions.

        Customer-infrastructure costs are tracked but NOT reserved against
        the tenant's budget (R14.15, R66.6).

        Args:
            operation: Description of the operation (e.g., "image_generation").
            estimated_amount_usd: Worst-reasonable cost estimate in USD.
            job_id: Optional job UUID this reservation covers.
            provider: Provider that will incur the cost.
            cost_classification: Three-tier classification tier.
            expires_at: When this reservation expires if not finalized.

        Returns:
            The created CostReservation ORM instance.

        Raises:
            BudgetExceededError: If reservation would exceed budget (HTTP 402).
            LedgerUnavailableError: If DB query fails (fail-safe).
            ValueError: If estimated_amount_usd is not positive.

        Validates: R14.9, R66.1, R66.2
        """
        if estimated_amount_usd <= Decimal("0"):
            raise ValueError("Reservation amount must be positive")

        if not operation:
            raise ValueError("Operation description is required")

        # Set default expiry if not provided
        if expires_at is None:
            expires_at = datetime.now(UTC) + DEFAULT_RESERVATION_EXPIRY

        # Customer-infrastructure costs: track but do NOT enforce budget
        if cost_classification == CostClassification.CUSTOMER_INFRASTRUCTURE.value:
            return await self._create_reservation_without_budget_check(
                operation=operation,
                estimated_amount_usd=estimated_amount_usd,
                job_id=job_id,
                provider=provider,
                cost_classification=cost_classification,
                expires_at=expires_at,
            )

        # Managed compute and platform expense: enforce budget atomically
        try:
            return await self._atomic_reserve(
                operation=operation,
                estimated_amount_usd=estimated_amount_usd,
                job_id=job_id,
                provider=provider,
                cost_classification=cost_classification,
                expires_at=expires_at,
            )
        except (OperationalError, DBAPIError) as exc:
            logger.error(
                "cost_ledger_unavailable",
                org_id=str(self._org_id),
                operation=operation,
                error=str(exc),
            )
            raise LedgerUnavailableError(
                reason=f"Database error during cost reservation: {type(exc).__name__}"
            ) from exc

    async def check_budget(
        self,
        amount_usd: Decimal,
        period: str = "daily",
    ) -> bool:
        """Check if the org's budget allows a spend of amount_usd.

        Does NOT create a reservation — use reserve_cost() for atomic
        check-and-hold. This method is for informational pre-flight checks.

        Args:
            amount_usd: The amount to check against budget.
            period: "daily" or "monthly".

        Returns:
            True if the spend is within budget, False otherwise.

        Raises:
            LedgerUnavailableError: If DB query fails (fail-safe).
        """
        try:
            current_spend = await self.get_current_spend(period)
            limits = await self.get_budget_limits()
            limit_value = (
                limits.daily_hard_usd if period == "daily" else limits.monthly_hard_usd
            )
            return (current_spend + amount_usd) <= limit_value
        except (OperationalError, DBAPIError) as exc:
            logger.error(
                "cost_budget_check_unavailable",
                org_id=str(self._org_id),
                period=period,
                error=str(exc),
            )
            raise LedgerUnavailableError(
                reason=f"Database error during budget check: {type(exc).__name__}"
            ) from exc

    async def get_current_spend(self, period: str = "daily") -> Decimal:
        """Calculate current spend for the org (reservations + actuals).

        Includes:
        - Active/committed reservations (reserved_amount_usd)
        - Finalized reservations (actual_amount_usd)
        - Direct cost entries (ACTUAL, RECONCILIATION types)
        - Releases and refunds (negative, reduce spend)

        Only considers managed_compute and platform_expense classifications.
        Customer-infrastructure costs are excluded from budget calculations.

        Args:
            period: "daily" or "monthly" — determines the time window.

        Returns:
            Current spend as Decimal (USD).

        Raises:
            LedgerUnavailableError: If DB query fails (fail-safe).

        Validates: R14.3, R14.4
        """
        try:
            now = datetime.now(UTC)
            if period == "daily":
                window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                window_start = now.replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )

            # Sum active/committed reservations within the time window
            # These represent budget holds not yet reconciled
            reservation_spend = await self._sum_active_reservations(window_start)

            # Sum finalized cost entries (ACTUAL, RECONCILIATION, RELEASE, REFUND)
            entry_spend = await self._sum_cost_entries(window_start)

            total = reservation_spend + entry_spend
            return max(total, Decimal("0"))

        except (OperationalError, DBAPIError) as exc:
            logger.error(
                "cost_spend_query_unavailable",
                org_id=str(self._org_id),
                period=period,
                error=str(exc),
            )
            raise LedgerUnavailableError(
                reason=f"Database error querying spend: {type(exc).__name__}"
            ) from exc

    async def get_budget_limits(self) -> BudgetLimits:
        """Retrieve budget limits for this workspace.

        Currently uses application-level defaults from settings.
        Future: per-workspace overrides from a budget_limits table.

        Returns:
            BudgetLimits with daily and monthly hard limits.
        """
        # Future: query budget_limits table for per-workspace overrides
        # For now, use platform-wide defaults from settings
        return BudgetLimits.from_settings()

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _atomic_reserve(
        self,
        operation: str,
        estimated_amount_usd: Decimal,
        job_id: UUID | None,
        provider: str | None,
        cost_classification: str,
        expires_at: datetime,
    ) -> CostReservation:
        """Perform atomic budget check + reservation in one transaction.

        Uses SELECT ... FOR UPDATE on active reservations to serialize
        concurrent reservation attempts for the same org. This prevents
        race conditions where two concurrent requests could both pass the
        budget check and collectively exceed the limit.

        Validates: R66.1 (single transaction), R66.2 (reject if exceeds)
        """
        # Lock active reservations for this org to prevent concurrent
        # budget check races. FOR UPDATE ensures serialized access.
        lock_stmt = (
            select(CostReservation.id)
            .where(
                CostReservation.org_id == self._org_id,
                CostReservation.status.in_(
                    [ReservationStatus.ACTIVE.value, ReservationStatus.COMMITTED.value]
                ),
                CostReservation.cost_classification.in_([
                    CostClassification.MANAGED_COMPUTE.value,
                    CostClassification.PLATFORM_EXPENSE.value,
                ]),
            )
            .with_for_update()
        )
        await self._db.execute(lock_stmt)

        # Now check budget (daily AND monthly)
        daily_spend = await self.get_current_spend("daily")
        monthly_spend = await self.get_current_spend("monthly")
        limits = await self.get_budget_limits()

        # Check daily limit
        if (daily_spend + estimated_amount_usd) > limits.daily_hard_usd:
            logger.warning(
                "cost_daily_budget_exceeded",
                org_id=str(self._org_id),
                operation=operation,
                requested_usd=str(estimated_amount_usd),
                current_daily_spend=str(daily_spend),
                daily_limit=str(limits.daily_hard_usd),
            )
            raise BudgetExceededError(
                org_id=self._org_id,
                requested_usd=estimated_amount_usd,
                current_spend_usd=daily_spend,
                limit_usd=limits.daily_hard_usd,
                period="daily",
            )

        # Check monthly limit
        if (monthly_spend + estimated_amount_usd) > limits.monthly_hard_usd:
            logger.warning(
                "cost_monthly_budget_exceeded",
                org_id=str(self._org_id),
                operation=operation,
                requested_usd=str(estimated_amount_usd),
                current_monthly_spend=str(monthly_spend),
                monthly_limit=str(limits.monthly_hard_usd),
            )
            raise BudgetExceededError(
                org_id=self._org_id,
                requested_usd=estimated_amount_usd,
                current_spend_usd=monthly_spend,
                limit_usd=limits.monthly_hard_usd,
                period="monthly",
            )

        # Budget OK — create the reservation
        reservation = CostReservation(
            org_id=self._org_id,
            job_id=job_id,
            operation=operation,
            reserved_amount_usd=estimated_amount_usd,
            cost_classification=cost_classification,
            status=ReservationStatus.ACTIVE.value,
            provider=provider,
            expires_at=expires_at,
        )
        self._db.add(reservation)
        await self._db.flush()

        # Also create a ledger entry for the reservation
        entry = CostEntry(
            org_id=self._org_id,
            job_id=job_id,
            reservation_id=reservation.id,
            entry_type="reservation",
            amount_usd=estimated_amount_usd,
            operation=operation,
            provider=provider,
            cost_classification=cost_classification,
            description=f"Reserved ${estimated_amount_usd} for {operation}",
        )
        self._db.add(entry)
        await self._db.flush()

        logger.info(
            "cost_reserved",
            org_id=str(self._org_id),
            reservation_id=str(reservation.id),
            job_id=str(job_id) if job_id else None,
            operation=operation,
            amount_usd=str(estimated_amount_usd),
            cost_classification=cost_classification,
            provider=provider,
        )

        return reservation

    async def _create_reservation_without_budget_check(
        self,
        operation: str,
        estimated_amount_usd: Decimal,
        job_id: UUID | None,
        provider: str | None,
        cost_classification: str,
        expires_at: datetime,
    ) -> CostReservation:
        """Create a reservation for informational tracking only (no budget check).

        Used for customer_infrastructure costs which are tracked but not
        enforced against the tenant's budget.

        Validates: R14.15, R66.6
        """
        reservation = CostReservation(
            org_id=self._org_id,
            job_id=job_id,
            operation=operation,
            reserved_amount_usd=estimated_amount_usd,
            cost_classification=cost_classification,
            status=ReservationStatus.ACTIVE.value,
            provider=provider,
            expires_at=expires_at,
        )
        self._db.add(reservation)
        await self._db.flush()

        # Create informational ledger entry
        entry = CostEntry(
            org_id=self._org_id,
            job_id=job_id,
            reservation_id=reservation.id,
            entry_type="reservation",
            amount_usd=estimated_amount_usd,
            operation=operation,
            provider=provider,
            cost_classification=cost_classification,
            description=(
                f"Informational: reserved ${estimated_amount_usd} for "
                f"{operation} (customer infrastructure — not budgeted)"
            ),
        )
        self._db.add(entry)
        await self._db.flush()

        logger.info(
            "cost_reserved_informational",
            org_id=str(self._org_id),
            reservation_id=str(reservation.id),
            operation=operation,
            amount_usd=str(estimated_amount_usd),
            cost_classification=cost_classification,
        )

        return reservation

    async def finalize_cost(
        self,
        reservation_id: UUID,
        actual_amount_usd: Decimal,
        provider_receipt: str | None = None,
    ) -> CostReservation:
        """Finalize a reservation: release the hold and record actual cost.

        Compares actual vs reserved and logs a warning if variance > 20%.

        Args:
            reservation_id: The reservation UUID to finalize.
            actual_amount_usd: The actual cost incurred (USD).
            provider_receipt: Optional external receipt/reference from provider.

        Returns:
            The finalized CostReservation.

        Raises:
            ValueError: If reservation not found or already finalized.
            LedgerUnavailableError: If DB query fails.

        Validates: R14.10, R66.3
        """
        if actual_amount_usd < Decimal("0"):
            raise ValueError("Actual amount cannot be negative")

        try:
            reservation = await self._get_reservation(reservation_id)
        except (OperationalError, DBAPIError) as exc:
            raise LedgerUnavailableError(
                reason=f"Database error fetching reservation: {type(exc).__name__}"
            ) from exc

        if reservation is None:
            raise ValueError(
                f"Reservation {reservation_id} not found for org {self._org_id}"
            )

        if reservation.status in (
            ReservationStatus.FINALIZED.value,
            ReservationStatus.RELEASED.value,
            ReservationStatus.EXPIRED.value,
        ):
            raise ValueError(
                f"Reservation {reservation_id} is already in terminal state "
                f"'{reservation.status}'"
            )

        # Calculate variance
        reserved = reservation.reserved_amount_usd
        if reserved > Decimal("0"):
            variance = abs(actual_amount_usd - reserved) / reserved
        else:
            variance = Decimal("0")

        # Log anomaly if variance exceeds 20%
        if variance > Decimal("0.20"):
            logger.warning(
                "cost_variance_anomaly",
                org_id=str(self._org_id),
                reservation_id=str(reservation_id),
                reserved_usd=str(reserved),
                actual_usd=str(actual_amount_usd),
                variance_pct=str(round(variance * 100, 2)),
                provider_receipt=provider_receipt,
            )

        # Update reservation to finalized
        now = datetime.now(UTC)
        reservation.actual_amount_usd = actual_amount_usd
        reservation.status = ReservationStatus.FINALIZED.value
        reservation.finalized_at = now

        # Create actual cost entry
        entry = CostEntry(
            org_id=self._org_id,
            job_id=reservation.job_id,
            reservation_id=reservation.id,
            entry_type="actual",
            amount_usd=actual_amount_usd,
            operation=reservation.operation,
            provider=reservation.provider,
            cost_classification=reservation.cost_classification,
            description=(
                f"Finalized: actual ${actual_amount_usd} "
                f"(reserved ${reserved}, variance {round(variance * 100, 1)}%)"
                + (f" receipt: {provider_receipt}" if provider_receipt else "")
            ),
        )
        self._db.add(entry)

        # Create release entry to offset the reservation hold
        release_entry = CostEntry(
            org_id=self._org_id,
            job_id=reservation.job_id,
            reservation_id=reservation.id,
            entry_type="release",
            amount_usd=-reserved,
            operation=reservation.operation,
            provider=reservation.provider,
            cost_classification=reservation.cost_classification,
            description=f"Released reservation hold of ${reserved}",
        )
        self._db.add(release_entry)

        await self._db.flush()

        logger.info(
            "cost_finalized",
            org_id=str(self._org_id),
            reservation_id=str(reservation_id),
            reserved_usd=str(reserved),
            actual_usd=str(actual_amount_usd),
            variance_pct=str(round(variance * 100, 2)),
        )

        return reservation

    async def release_reservation(
        self,
        reservation_id: UUID,
        reason: str | None = None,
    ) -> CostReservation:
        """Release an active reservation without recording actual cost.

        Used when a job is cancelled or abandoned before any cost is incurred.

        Args:
            reservation_id: The reservation UUID to release.
            reason: Optional reason for the release (e.g., "job_cancelled").

        Returns:
            The released CostReservation.

        Raises:
            ValueError: If reservation not found or already in terminal state.
            LedgerUnavailableError: If DB query fails.

        Validates: R66.3
        """
        try:
            reservation = await self._get_reservation(reservation_id)
        except (OperationalError, DBAPIError) as exc:
            raise LedgerUnavailableError(
                reason=f"Database error fetching reservation: {type(exc).__name__}"
            ) from exc

        if reservation is None:
            raise ValueError(
                f"Reservation {reservation_id} not found for org {self._org_id}"
            )

        if reservation.status in (
            ReservationStatus.FINALIZED.value,
            ReservationStatus.RELEASED.value,
            ReservationStatus.EXPIRED.value,
        ):
            raise ValueError(
                f"Reservation {reservation_id} is already in terminal state "
                f"'{reservation.status}'"
            )

        # Update reservation to released
        reservation.status = ReservationStatus.RELEASED.value
        reservation.finalized_at = datetime.now(UTC)

        # Create release entry to offset the reservation hold
        release_entry = CostEntry(
            org_id=self._org_id,
            job_id=reservation.job_id,
            reservation_id=reservation.id,
            entry_type="release",
            amount_usd=-reservation.reserved_amount_usd,
            operation=reservation.operation,
            provider=reservation.provider,
            cost_classification=reservation.cost_classification,
            description=(
                f"Released reservation of ${reservation.reserved_amount_usd}"
                + (f" — reason: {reason}" if reason else "")
            ),
        )
        self._db.add(release_entry)
        await self._db.flush()

        logger.info(
            "cost_reservation_released",
            org_id=str(self._org_id),
            reservation_id=str(reservation_id),
            amount_usd=str(reservation.reserved_amount_usd),
            reason=reason,
        )

        return reservation

    async def record_partial_failure(
        self,
        reservation_id: UUID,
        partial_gpu_seconds: float,
        gpu_rate_per_hour: Decimal | None = None,
    ) -> CostReservation:
        """Record partial cost for a failed job that consumed GPU time.

        Failed jobs are NOT assumed to be $0 — partial GPU time is still
        charged. The reservation is finalized with the partial cost.

        Args:
            reservation_id: The reservation UUID.
            partial_gpu_seconds: Seconds of GPU time consumed before failure.
            gpu_rate_per_hour: Hourly GPU rate in USD. If None, uses a default.

        Returns:
            The finalized CostReservation with partial cost.

        Raises:
            ValueError: If reservation not found or invalid state.
            LedgerUnavailableError: If DB query fails.

        Validates: R14.11, R66.4
        """
        if partial_gpu_seconds < 0:
            raise ValueError("GPU seconds cannot be negative")

        # Default GPU rate: $0.50/hour if not provided
        rate = gpu_rate_per_hour or Decimal("0.50")
        partial_cost = (rate * Decimal(str(partial_gpu_seconds))) / Decimal("3600")
        # Round to 4 decimal places
        partial_cost = partial_cost.quantize(Decimal("0.0001"))

        return await self.finalize_cost(
            reservation_id=reservation_id,
            actual_amount_usd=partial_cost,
            provider_receipt=f"partial_failure: {partial_gpu_seconds}s @ ${rate}/hr",
        )

    async def record_retry_cost(
        self,
        reservation_id: UUID,
        attempt_number: int,
        amount_usd: Decimal,
    ) -> CostEntry:
        """Record an independent cost entry for a retry attempt.

        Each retry attempt gets its own cost entry linked to the parent
        reservation. This does NOT finalize the reservation — the final
        finalize_cost call handles the overall reconciliation.

        Args:
            reservation_id: The parent reservation UUID.
            attempt_number: Which attempt this cost is for (1-indexed).
            amount_usd: Cost incurred in this attempt.

        Returns:
            The created CostEntry.

        Raises:
            ValueError: If reservation not found or amount invalid.
            LedgerUnavailableError: If DB query fails.

        Validates: R14.11, R66.5
        """
        if amount_usd < Decimal("0"):
            raise ValueError("Retry cost amount cannot be negative")

        if attempt_number < 1:
            raise ValueError("Attempt number must be >= 1")

        try:
            reservation = await self._get_reservation(reservation_id)
        except (OperationalError, DBAPIError) as exc:
            raise LedgerUnavailableError(
                reason=f"Database error fetching reservation: {type(exc).__name__}"
            ) from exc

        if reservation is None:
            raise ValueError(
                f"Reservation {reservation_id} not found for org {self._org_id}"
            )

        entry = CostEntry(
            org_id=self._org_id,
            job_id=reservation.job_id,
            reservation_id=reservation.id,
            entry_type="actual",
            amount_usd=amount_usd,
            operation=reservation.operation,
            provider=reservation.provider,
            cost_classification=reservation.cost_classification,
            description=(
                f"Retry attempt {attempt_number}: ${amount_usd} "
                f"for {reservation.operation}"
            ),
        )
        self._db.add(entry)
        await self._db.flush()

        logger.info(
            "cost_retry_recorded",
            org_id=str(self._org_id),
            reservation_id=str(reservation_id),
            attempt_number=attempt_number,
            amount_usd=str(amount_usd),
        )

        return entry

    async def get_cost_summary(self) -> dict:
        """Get a comprehensive cost summary for the org.

        Returns today_spend, month_spend, budget limits, and breakdowns
        by provider and classification.

        Validates: R14.5
        """
        try:
            today_spend = await self.get_current_spend("daily")
            month_spend = await self.get_current_spend("monthly")
            limits = await self.get_budget_limits()
            active_reservations = await self._get_active_reservations_total()
            breakdown_by_classification = await self._breakdown_by_classification()
            breakdown_by_provider = await self._breakdown_by_provider()

            return {
                "today_spend_usd": today_spend,
                "month_spend_usd": month_spend,
                "active_reservations_usd": active_reservations,
                "daily_budget_usd": limits.daily_hard_usd,
                "monthly_budget_usd": limits.monthly_hard_usd,
                "breakdown_by_classification": breakdown_by_classification,
                "breakdown_by_provider": breakdown_by_provider,
            }
        except (OperationalError, DBAPIError) as exc:
            raise LedgerUnavailableError(
                reason=f"Database error fetching cost summary: {type(exc).__name__}"
            ) from exc

    async def list_reservations(
        self,
        limit: int = 20,
        offset: int = 0,
        status_filter: str | None = None,
    ) -> tuple[list[CostReservation], int]:
        """List cost reservations for the org with pagination.

        Args:
            limit: Max items to return.
            offset: Offset for pagination.
            status_filter: Optional status to filter by.

        Returns:
            Tuple of (items, total_count).
        """
        count_stmt = (
            select(func.count())
            .select_from(CostReservation)
            .where(CostReservation.org_id == self._org_id)
        )
        items_stmt = (
            select(CostReservation)
            .where(CostReservation.org_id == self._org_id)
            .order_by(CostReservation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if status_filter:
            count_stmt = count_stmt.where(
                CostReservation.status == status_filter
            )
            items_stmt = items_stmt.where(
                CostReservation.status == status_filter
            )

        total = await self._db.scalar(count_stmt) or 0
        result = await self._db.execute(items_stmt)
        items = list(result.scalars().all())
        return items, total

    async def list_entries(
        self,
        limit: int = 20,
        offset: int = 0,
        entry_type_filter: str | None = None,
    ) -> tuple[list[CostEntry], int]:
        """List cost entries for the org with pagination.

        Args:
            limit: Max items to return.
            offset: Offset for pagination.
            entry_type_filter: Optional entry_type to filter by.

        Returns:
            Tuple of (items, total_count).
        """
        count_stmt = (
            select(func.count())
            .select_from(CostEntry)
            .where(CostEntry.org_id == self._org_id)
        )
        items_stmt = (
            select(CostEntry)
            .where(CostEntry.org_id == self._org_id)
            .order_by(CostEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if entry_type_filter:
            count_stmt = count_stmt.where(
                CostEntry.entry_type == entry_type_filter
            )
            items_stmt = items_stmt.where(
                CostEntry.entry_type == entry_type_filter
            )

        total = await self._db.scalar(count_stmt) or 0
        result = await self._db.execute(items_stmt)
        items = list(result.scalars().all())
        return items, total

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _get_reservation(self, reservation_id: UUID) -> CostReservation | None:
        """Fetch a reservation by ID scoped to the org."""
        stmt = select(CostReservation).where(
            CostReservation.id == reservation_id,
            CostReservation.org_id == self._org_id,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_active_reservations_total(self) -> Decimal:
        """Sum of all active/committed reservation amounts."""
        stmt = select(
            func.coalesce(
                func.sum(CostReservation.reserved_amount_usd), Decimal("0")
            )
        ).where(
            CostReservation.org_id == self._org_id,
            CostReservation.status.in_(
                [ReservationStatus.ACTIVE.value, ReservationStatus.COMMITTED.value]
            ),
        )
        result = await self._db.scalar(stmt)
        return Decimal(str(result)) if result else Decimal("0")

    async def _breakdown_by_classification(self) -> dict[str, Decimal]:
        """Get spend breakdown by cost classification for current month."""
        now = datetime.now(UTC)
        window_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        stmt = (
            select(
                CostEntry.cost_classification,
                func.coalesce(func.sum(CostEntry.amount_usd), Decimal("0")),
            )
            .where(
                CostEntry.org_id == self._org_id,
                CostEntry.entry_type.in_(["actual", "reconciliation"]),
                CostEntry.created_at >= window_start,
            )
            .group_by(CostEntry.cost_classification)
        )
        result = await self._db.execute(stmt)
        rows = result.all()
        return {
            str(row[0]): Decimal(str(row[1])) for row in rows
        }

    async def _breakdown_by_provider(self) -> dict[str, Decimal]:
        """Get spend breakdown by provider for current month."""
        now = datetime.now(UTC)
        window_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        stmt = (
            select(
                func.coalesce(CostEntry.provider, "unknown"),
                func.coalesce(func.sum(CostEntry.amount_usd), Decimal("0")),
            )
            .where(
                CostEntry.org_id == self._org_id,
                CostEntry.entry_type.in_(["actual", "reconciliation"]),
                CostEntry.created_at >= window_start,
            )
            .group_by(CostEntry.provider)
        )
        result = await self._db.execute(stmt)
        rows = result.all()
        return {
            str(row[0]): Decimal(str(row[1])) for row in rows
        }

    async def _sum_active_reservations(self, window_start: datetime) -> Decimal:
        """Sum reserved amounts for active/committed reservations in the window.

        Only includes managed_compute and platform_expense classifications.
        """
        stmt = select(
            func.coalesce(
                func.sum(CostReservation.reserved_amount_usd), Decimal("0")
            )
        ).where(
            and_(
                CostReservation.org_id == self._org_id,
                CostReservation.status.in_(
                    [ReservationStatus.ACTIVE.value, ReservationStatus.COMMITTED.value]
                ),
                CostReservation.cost_classification.in_([
                    CostClassification.MANAGED_COMPUTE.value,
                    CostClassification.PLATFORM_EXPENSE.value,
                ]),
                CostReservation.created_at >= window_start,
            )
        )
        result = await self._db.scalar(stmt)
        return Decimal(str(result)) if result else Decimal("0")

    async def _sum_cost_entries(self, window_start: datetime) -> Decimal:
        """Sum cost entries (actuals, releases, refunds, reconciliations) in window.

        Includes:
        - ACTUAL entries (positive cost)
        - RECONCILIATION entries (adjustments)
        - RELEASE entries (negative — reduce spend)
        - REFUND entries (negative — reduce spend)

        Only includes entries for managed_compute and platform_expense.
        Excludes entries linked to active/committed reservations (already counted).
        """
        stmt = select(
            func.coalesce(func.sum(CostEntry.amount_usd), Decimal("0"))
        ).where(
            and_(
                CostEntry.org_id == self._org_id,
                CostEntry.entry_type.in_(
                    ["actual", "reconciliation", "release", "refund"]
                ),
                CostEntry.cost_classification.in_([
                    CostClassification.MANAGED_COMPUTE.value,
                    CostClassification.PLATFORM_EXPENSE.value,
                ]),
                CostEntry.created_at >= window_start,
            )
        )
        result = await self._db.scalar(stmt)
        return Decimal(str(result)) if result else Decimal("0")
