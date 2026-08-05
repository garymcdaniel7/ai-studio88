"""Cost Ledger & Budget Enforcement — Story 058.

Tenant-scoped durable cost ledger with atomic reservations, hard/soft limit
enforcement, provider reconciliation, and fail-safe behavior.

Ledger entries:
    RESERVATION — worst-reasonable cost reserved before paid launch
    COMMITMENT  — provider confirmed the work started (reservation→commitment)
    ACTUAL      — final cost from provider receipt
    RELEASE     — unused reservation returned to budget
    REFUND      — provider credit/reversal
    RECONCILIATION — discrepancy adjustment

Budget enforcement:
    HARD LIMIT  — blocks paid operations (atomic check before reservation)
    SOFT LIMIT  — warns but allows (produces alert, requires acknowledgment)

Fail-safe:
    If ledger is unavailable, paid operations MUST fail (never assume zero cost).

DECISION-REQUIRED:
    - Hard limit values per plan (starter/pro/enterprise)
    - Soft limit percentage (e.g., 80% of hard limit)
    - Grace period for over-budget (currently: none, immediate block)
    - Currency (currently: USD only)
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Ledger Entry Types
# =============================================================================


class EntryType(str, Enum):
    RESERVATION = "reservation"
    COMMITMENT = "commitment"
    ACTUAL = "actual"
    RELEASE = "release"
    REFUND = "refund"
    RECONCILIATION = "reconciliation"


class LimitResult(str, Enum):
    ALLOWED = "allowed"          # Within budget
    SOFT_LIMIT = "soft_limit"    # Over soft limit (warn, allow with ack)
    HARD_LIMIT = "hard_limit"    # Over hard limit (blocked)
    UNAVAILABLE = "unavailable"  # Ledger unavailable (fail-safe: block)


# =============================================================================
# Budget Limits (DECISION-REQUIRED values — configurable per workspace)
# =============================================================================


@dataclass(frozen=True)
class BudgetLimits:
    """Workspace budget limits. DECISION-REQUIRED: actual values per plan."""
    daily_hard_usd: float = 50.0     # DECISION-REQUIRED: default placeholder
    daily_soft_usd: float = 40.0     # DECISION-REQUIRED: 80% of hard
    monthly_hard_usd: float = 500.0  # DECISION-REQUIRED: default placeholder
    monthly_soft_usd: float = 400.0  # DECISION-REQUIRED: 80% of hard


DEFAULT_LIMITS = BudgetLimits()


# =============================================================================
# Ledger Entry
# =============================================================================


@dataclass
class LedgerEntry:
    """A single cost ledger entry."""
    entry_id: str = field(default_factory=lambda: f"le-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    entry_type: EntryType = EntryType.RESERVATION
    amount_usd: float = 0.0
    job_id: str | None = None
    operation: str = ""
    provider: str = ""
    description: str = ""
    reservation_id: str | None = None  # Links actual/release to reservation
    created_at: float = field(default_factory=time.time)
    reconciled: bool = False


# =============================================================================
# Reservation Record
# =============================================================================


@dataclass
class CostReservation:
    """An active cost reservation (hold on budget)."""
    reservation_id: str = field(default_factory=lambda: f"res-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    job_id: str | None = None
    operation: str = ""
    reserved_amount_usd: float = 0.0
    actual_amount_usd: float | None = None  # Set when finalized
    status: str = "active"  # active | committed | finalized | released | expired
    provider: str = ""
    created_at: float = field(default_factory=time.time)
    finalized_at: float | None = None


# =============================================================================
# Cost Ledger Store
# =============================================================================

_ledger_entries: list[LedgerEntry] = []
_reservations: dict[str, CostReservation] = {}
_workspace_limits: dict[str, BudgetLimits] = {}
_ledger_lock = threading.RLock()
_ledger_available: bool = True  # Simulates DB availability


# =============================================================================
# Budget Check (Pre-Reservation Gate)
# =============================================================================


def check_budget(
    org_id: str,
    estimated_cost_usd: float,
    period: str = "daily",
) -> tuple[LimitResult, dict[str, Any]]:
    """Check if a workspace can afford a new paid operation.

    This MUST be called BEFORE creating a reservation.
    If the ledger is unavailable, returns UNAVAILABLE (fail-safe: block).

    Args:
        org_id: Workspace.
        estimated_cost_usd: Worst-reasonable cost for this operation.
        period: "daily" or "monthly".

    Returns:
        (result, details) — result is the enforcement decision.
    """
    if not _ledger_available:
        return LimitResult.UNAVAILABLE, {
            "reason": "Cost ledger unavailable — paid operations blocked (fail-safe)",
        }

    if not org_id:
        return LimitResult.UNAVAILABLE, {"reason": "org_id required"}

    limits = _workspace_limits.get(org_id, DEFAULT_LIMITS)
    current_spend = _get_current_spend(org_id, period)
    projected = current_spend + estimated_cost_usd

    if period == "daily":
        hard = limits.daily_hard_usd
        soft = limits.daily_soft_usd
    else:
        hard = limits.monthly_hard_usd
        soft = limits.monthly_soft_usd

    details = {
        "current_spend_usd": round(current_spend, 4),
        "estimated_cost_usd": round(estimated_cost_usd, 4),
        "projected_usd": round(projected, 4),
        "hard_limit_usd": hard,
        "soft_limit_usd": soft,
        "period": period,
    }

    if projected > hard:
        return LimitResult.HARD_LIMIT, {**details, "reason": f"Projected ${projected:.2f} exceeds hard limit ${hard:.2f}"}

    if projected > soft:
        return LimitResult.SOFT_LIMIT, {**details, "reason": f"Projected ${projected:.2f} exceeds soft limit ${soft:.2f}"}

    return LimitResult.ALLOWED, details


# =============================================================================
# Atomic Reservation
# =============================================================================


def reserve_cost(
    org_id: str,
    estimated_cost_usd: float,
    operation: str,
    job_id: str | None = None,
    provider: str = "",
) -> CostReservation:
    """Atomically reserve budget for a paid operation.

    Must pass check_budget() first. Creates a hold that reduces available budget.
    The reservation must later be finalized (actual), released, or expired.

    Raises:
        BudgetExceededError: If hard limit would be violated.
        LedgerUnavailableError: If ledger is down (fail-safe).
    """
    if not _ledger_available:
        raise LedgerUnavailableError()

    if not org_id:
        raise ValueError("org_id required for cost reservation")

    if estimated_cost_usd <= 0:
        raise ValueError("Reservation amount must be positive")

    with _ledger_lock:
        # Atomic budget check + reservation
        result, details = check_budget(org_id, estimated_cost_usd, "daily")

        if result == LimitResult.HARD_LIMIT:
            raise BudgetExceededError(org_id, estimated_cost_usd, details)

        if result == LimitResult.UNAVAILABLE:
            raise LedgerUnavailableError()

        # Create reservation
        reservation = CostReservation(
            org_id=org_id,
            job_id=job_id,
            operation=operation,
            reserved_amount_usd=estimated_cost_usd,
            provider=provider,
        )
        _reservations[reservation.reservation_id] = reservation

        # Record ledger entry
        entry = LedgerEntry(
            org_id=org_id,
            entry_type=EntryType.RESERVATION,
            amount_usd=estimated_cost_usd,
            job_id=job_id,
            operation=operation,
            provider=provider,
            reservation_id=reservation.reservation_id,
            description=f"Reserved ${estimated_cost_usd:.4f} for {operation}",
        )
        _ledger_entries.append(entry)

        logger.info(
            f"COST_RESERVED: org={org_id[:8]} amount=${estimated_cost_usd:.4f} "
            f"op={operation} res_id={reservation.reservation_id}"
        )

        return reservation


def finalize_cost(
    reservation_id: str,
    actual_cost_usd: float,
    provider_receipt: dict | None = None,
) -> CostReservation:
    """Finalize a reservation with actual cost from provider.

    Converts the reservation to an actual charge.
    If actual < reserved, the difference is released.
    If actual > reserved, the overage is recorded (reconciliation needed).
    """
    with _ledger_lock:
        reservation = _reservations.get(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status not in ("active", "committed"):
            raise ValueError(f"Cannot finalize reservation in status: {reservation.status}")

        reservation.actual_amount_usd = actual_cost_usd
        reservation.status = "finalized"
        reservation.finalized_at = time.time()

        # Record actual charge
        _ledger_entries.append(LedgerEntry(
            org_id=reservation.org_id,
            entry_type=EntryType.ACTUAL,
            amount_usd=actual_cost_usd,
            job_id=reservation.job_id,
            operation=reservation.operation,
            provider=reservation.provider,
            reservation_id=reservation_id,
            description=f"Actual cost ${actual_cost_usd:.4f} for {reservation.operation}",
        ))

        # Release difference if actual < reserved
        diff = reservation.reserved_amount_usd - actual_cost_usd
        if diff > 0.001:
            _ledger_entries.append(LedgerEntry(
                org_id=reservation.org_id,
                entry_type=EntryType.RELEASE,
                amount_usd=-diff,
                job_id=reservation.job_id,
                operation=reservation.operation,
                reservation_id=reservation_id,
                description=f"Released ${diff:.4f} unused reservation",
            ))

        # Record overage if actual > reserved
        if actual_cost_usd > reservation.reserved_amount_usd + 0.001:
            overage = actual_cost_usd - reservation.reserved_amount_usd
            _ledger_entries.append(LedgerEntry(
                org_id=reservation.org_id,
                entry_type=EntryType.RECONCILIATION,
                amount_usd=overage,
                reservation_id=reservation_id,
                description=f"Overage ${overage:.4f} — actual exceeded estimate",
            ))

        return reservation


def release_reservation(reservation_id: str, reason: str = "cancelled") -> CostReservation:
    """Release an active reservation (job cancelled, not needed)."""
    with _ledger_lock:
        reservation = _reservations.get(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        if reservation.status != "active":
            raise ValueError(f"Cannot release reservation in status: {reservation.status}")

        reservation.status = "released"
        reservation.finalized_at = time.time()

        _ledger_entries.append(LedgerEntry(
            org_id=reservation.org_id,
            entry_type=EntryType.RELEASE,
            amount_usd=-reservation.reserved_amount_usd,
            reservation_id=reservation_id,
            description=f"Released reservation: {reason}",
        ))

        return reservation


# =============================================================================
# Spend Queries
# =============================================================================


def _get_current_spend(org_id: str, period: str = "daily") -> float:
    """Calculate current spend for a workspace (reservations + actuals)."""
    now = time.time()
    if period == "daily":
        window_start = now - 86400
    else:
        window_start = now - (30 * 86400)

    total = 0.0
    for entry in _ledger_entries:
        if entry.org_id != org_id:
            continue
        if entry.created_at < window_start:
            continue
        if entry.entry_type in (EntryType.RESERVATION, EntryType.ACTUAL, EntryType.RECONCILIATION):
            total += entry.amount_usd
        elif entry.entry_type == EntryType.RELEASE:
            total += entry.amount_usd  # Negative values reduce spend

    return max(total, 0.0)


def get_spend_summary(org_id: str) -> dict[str, Any]:
    """Get spend summary for dashboard display."""
    daily = _get_current_spend(org_id, "daily")
    monthly = _get_current_spend(org_id, "monthly")
    limits = _workspace_limits.get(org_id, DEFAULT_LIMITS)

    active_reservations = sum(
        r.reserved_amount_usd for r in _reservations.values()
        if r.org_id == org_id and r.status == "active"
    )

    return {
        "daily_spend_usd": round(daily, 4),
        "monthly_spend_usd": round(monthly, 4),
        "active_reservations_usd": round(active_reservations, 4),
        "daily_limit_usd": limits.daily_hard_usd,
        "monthly_limit_usd": limits.monthly_hard_usd,
        "daily_remaining_usd": round(max(limits.daily_hard_usd - daily, 0), 4),
        "monthly_remaining_usd": round(max(limits.monthly_hard_usd - monthly, 0), 4),
    }


# =============================================================================
# Provider Reconciliation
# =============================================================================


def reconcile_provider_receipt(
    org_id: str,
    provider: str,
    provider_charge_id: str,
    amount_usd: float,
    reservation_id: str | None = None,
) -> LedgerEntry:
    """Reconcile a provider charge with our ledger.

    If a matching reservation exists, finalizes it.
    If no reservation, creates a reconciliation entry (unexpected charge).
    Idempotent: duplicate provider_charge_id is ignored.
    """
    with _ledger_lock:
        # Check for duplicate receipt
        for entry in _ledger_entries:
            if entry.description and provider_charge_id in entry.description:
                return entry  # Already reconciled

        if reservation_id and reservation_id in _reservations:
            finalize_cost(reservation_id, amount_usd)
            return _ledger_entries[-1]

        # Unexpected charge — record for investigation
        entry = LedgerEntry(
            org_id=org_id,
            entry_type=EntryType.RECONCILIATION,
            amount_usd=amount_usd,
            provider=provider,
            description=f"Unmatched provider charge: {provider_charge_id} ${amount_usd:.4f}",
        )
        _ledger_entries.append(entry)
        logger.warning(f"UNMATCHED_CHARGE: org={org_id[:8]} provider={provider} amount=${amount_usd:.4f}")
        return entry


# =============================================================================
# Errors
# =============================================================================


class BudgetExceededError(Exception):
    """Raised when hard budget limit is exceeded."""
    def __init__(self, org_id: str, requested: float, details: dict) -> None:
        self.org_id = org_id
        self.requested = requested
        self.details = details
        super().__init__(
            f"Budget exceeded for {org_id[:8]}: "
            f"requested ${requested:.2f}, {details.get('reason', '')}"
        )


class LedgerUnavailableError(Exception):
    """Raised when cost ledger is unavailable (fail-safe: block all paid ops)."""
    def __init__(self) -> None:
        super().__init__("Cost ledger unavailable — paid operations blocked (fail-safe)")


# =============================================================================
# Configuration
# =============================================================================


def set_workspace_limits(org_id: str, limits: BudgetLimits) -> None:
    """Set custom budget limits for a workspace."""
    _workspace_limits[org_id] = limits


def set_ledger_availability(available: bool) -> None:
    """Set ledger availability (for testing fail-safe behavior)."""
    global _ledger_available
    _ledger_available = available


# =============================================================================
# Testing
# =============================================================================


def _reset_store() -> None:
    global _ledger_available
    _ledger_entries.clear()
    _reservations.clear()
    _workspace_limits.clear()
    _ledger_available = True
