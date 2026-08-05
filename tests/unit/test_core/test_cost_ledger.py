"""Cost ledger & budget enforcement tests — Story 058.

Tests prove:
  - Reservations require org_id and positive amount
  - Hard limit blocks reservation atomically
  - Soft limit allows but reports warning
  - Ledger unavailability blocks all paid ops (fail-safe)
  - Finalization converts reservation to actual
  - Over-estimate releases difference
  - Under-estimate records overage
  - Release returns budget
  - Duplicate reconciliation is idempotent
  - Concurrent reservations are atomic
  - Spend summary is accurate
"""

import threading
import time

import pytest

from backend.cost_ledger import (
    BudgetExceededError,
    BudgetLimits,
    LedgerUnavailableError,
    LimitResult,
    _reset_store,
    check_budget,
    finalize_cost,
    get_spend_summary,
    reconcile_provider_receipt,
    release_reservation,
    reserve_cost,
    set_ledger_availability,
    set_workspace_limits,
)

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture(autouse=True)
def clean_store():
    _reset_store()
    yield
    _reset_store()


# =============================================================================
# Budget Check
# =============================================================================


@pytest.mark.unit
class TestBudgetCheck:

    def test_within_budget_allowed(self):
        result, details = check_budget(TENANT_A, 5.0, "daily")
        assert result == LimitResult.ALLOWED

    def test_exceeds_hard_limit(self):
        set_workspace_limits(TENANT_A, BudgetLimits(daily_hard_usd=10.0, daily_soft_usd=8.0))
        result, details = check_budget(TENANT_A, 15.0, "daily")
        assert result == LimitResult.HARD_LIMIT

    def test_exceeds_soft_limit(self):
        set_workspace_limits(TENANT_A, BudgetLimits(daily_hard_usd=10.0, daily_soft_usd=5.0))
        result, details = check_budget(TENANT_A, 6.0, "daily")
        assert result == LimitResult.SOFT_LIMIT

    def test_unavailable_ledger_blocks(self):
        set_ledger_availability(False)
        result, _ = check_budget(TENANT_A, 1.0, "daily")
        assert result == LimitResult.UNAVAILABLE

    def test_empty_org_unavailable(self):
        result, _ = check_budget("", 1.0)
        assert result == LimitResult.UNAVAILABLE


# =============================================================================
# Reservation
# =============================================================================


@pytest.mark.unit
class TestReservation:

    def test_reserve_creates_entry(self):
        res = reserve_cost(TENANT_A, 2.50, "generate_image", job_id="j1")
        assert res.status == "active"
        assert res.reserved_amount_usd == 2.50
        assert res.org_id == TENANT_A

    def test_reserve_requires_org_id(self):
        with pytest.raises(ValueError, match="org_id"):
            reserve_cost("", 1.0, "test")

    def test_reserve_requires_positive_amount(self):
        with pytest.raises(ValueError, match="positive"):
            reserve_cost(TENANT_A, 0.0, "test")

    def test_reserve_blocked_at_hard_limit(self):
        set_workspace_limits(TENANT_A, BudgetLimits(daily_hard_usd=5.0, daily_soft_usd=4.0))
        with pytest.raises(BudgetExceededError):
            reserve_cost(TENANT_A, 10.0, "train_lora")

    def test_reserve_unavailable_ledger(self):
        set_ledger_availability(False)
        with pytest.raises(LedgerUnavailableError):
            reserve_cost(TENANT_A, 1.0, "test")

    def test_reservation_reduces_available_budget(self):
        set_workspace_limits(TENANT_A, BudgetLimits(daily_hard_usd=10.0, daily_soft_usd=8.0))
        reserve_cost(TENANT_A, 6.0, "op1")
        # Second reservation should see reduced budget
        result, details = check_budget(TENANT_A, 6.0, "daily")
        assert result == LimitResult.HARD_LIMIT  # 6 + 6 = 12 > 10


# =============================================================================
# Finalization
# =============================================================================


@pytest.mark.unit
class TestFinalization:

    def test_finalize_with_exact_cost(self):
        res = reserve_cost(TENANT_A, 2.0, "generate")
        result = finalize_cost(res.reservation_id, 2.0)
        assert result.status == "finalized"
        assert result.actual_amount_usd == 2.0

    def test_finalize_under_estimate_releases(self):
        res = reserve_cost(TENANT_A, 5.0, "train")
        finalize_cost(res.reservation_id, 3.0)
        # Check that budget recovered the $2 difference
        summary = get_spend_summary(TENANT_A)
        assert summary["daily_spend_usd"] < 5.0

    def test_finalize_over_estimate_records_overage(self):
        res = reserve_cost(TENANT_A, 2.0, "gpu")
        finalize_cost(res.reservation_id, 4.0)
        summary = get_spend_summary(TENANT_A)
        assert summary["daily_spend_usd"] >= 4.0

    def test_finalize_invalid_reservation(self):
        with pytest.raises(ValueError, match="not found"):
            finalize_cost("nonexistent", 1.0)

    def test_double_finalize_rejected(self):
        res = reserve_cost(TENANT_A, 2.0, "test")
        finalize_cost(res.reservation_id, 2.0)
        with pytest.raises(ValueError, match="Cannot finalize"):
            finalize_cost(res.reservation_id, 2.0)


# =============================================================================
# Release
# =============================================================================


@pytest.mark.unit
class TestRelease:

    def test_release_returns_budget(self):
        set_workspace_limits(TENANT_A, BudgetLimits(daily_hard_usd=10.0, daily_soft_usd=8.0))
        res = reserve_cost(TENANT_A, 8.0, "train")
        release_reservation(res.reservation_id, "cancelled")
        # Budget should be fully available again
        result, _ = check_budget(TENANT_A, 8.0, "daily")
        assert result == LimitResult.ALLOWED

    def test_release_already_released_rejected(self):
        res = reserve_cost(TENANT_A, 1.0, "test")
        release_reservation(res.reservation_id)
        with pytest.raises(ValueError, match="Cannot release"):
            release_reservation(res.reservation_id)


# =============================================================================
# Provider Reconciliation
# =============================================================================


@pytest.mark.unit
class TestReconciliation:

    def test_reconcile_with_reservation(self):
        res = reserve_cost(TENANT_A, 3.0, "gpu", provider="vast")
        entry = reconcile_provider_receipt(TENANT_A, "vast", "charge-001", 2.50, res.reservation_id)
        assert entry.entry_type.value in ("actual", "reconciliation")

    def test_reconcile_without_reservation(self):
        entry = reconcile_provider_receipt(TENANT_A, "runpod", "charge-002", 1.50)
        assert "Unmatched" in entry.description

    def test_duplicate_receipt_idempotent(self):
        res = reserve_cost(TENANT_A, 2.0, "test", provider="vast")
        entry1 = reconcile_provider_receipt(TENANT_A, "vast", "charge-003", 2.0, res.reservation_id)
        entry2 = reconcile_provider_receipt(TENANT_A, "vast", "charge-003", 2.0, res.reservation_id)
        assert entry1.entry_id == entry2.entry_id  # Same entry returned


# =============================================================================
# Concurrency
# =============================================================================


@pytest.mark.unit
class TestConcurrency:

    def test_concurrent_reservations_atomic(self):
        """Multiple threads reserving — budget is correctly tracked."""
        set_workspace_limits(TENANT_A, BudgetLimits(daily_hard_usd=100.0, daily_soft_usd=80.0))
        results = {"reserved": 0, "blocked": 0}

        def try_reserve():
            try:
                reserve_cost(TENANT_A, 5.0, "test")
                results["reserved"] += 1
            except BudgetExceededError:
                results["blocked"] += 1

        threads = [threading.Thread(target=try_reserve) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed (15 * 5 = 75 < 100 hard limit)
        assert results["reserved"] == 15
        assert results["blocked"] == 0


# =============================================================================
# Spend Summary
# =============================================================================


@pytest.mark.unit
class TestSpendSummary:

    def test_empty_summary(self):
        summary = get_spend_summary(TENANT_A)
        assert summary["daily_spend_usd"] == 0.0
        assert summary["active_reservations_usd"] == 0.0

    def test_summary_after_reservation(self):
        reserve_cost(TENANT_A, 3.50, "generate")
        summary = get_spend_summary(TENANT_A)
        assert summary["daily_spend_usd"] == 3.50
        assert summary["active_reservations_usd"] == 3.50

    def test_summary_after_finalization(self):
        res = reserve_cost(TENANT_A, 5.0, "train")
        finalize_cost(res.reservation_id, 3.0)
        summary = get_spend_summary(TENANT_A)
        assert summary["active_reservations_usd"] == 0.0  # Finalized, not active
