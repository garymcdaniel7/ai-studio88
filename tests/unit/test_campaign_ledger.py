"""Campaign Financial Ledger Tests (Story 131).

Proves: duplicate prevention, late-cost handling, refunds, currency,
partial success, tenant isolation, derived totals, and reconciliation.

Run with:
    pytest tests/unit/test_campaign_ledger.py -v
"""
from __future__ import annotations

import pytest

from backend.campaign_ledger import (
    CampaignBudgetSummary,
    EntryType,
    LedgerEntry,
    LedgerError,
    ReconciliationState,
    add_actual,
    add_entry,
    add_planned,
    add_refund,
    add_reservation,
    add_unresolved,
    clear_ledger,
    confirm_entry,
    dispute_entry,
    get_campaign_summary,
    get_entries,
    get_unresolved,
    resolve_unresolved,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_ledger()
    yield
    clear_ledger()


# =============================================================================
# Duplicate Prevention
# =============================================================================


class TestDuplicatePrevention:

    @pytest.mark.unit
    def test_duplicate_idempotency_key_ignored(self):
        """Same idempotency_key returns existing entry (no double-count)."""
        e1 = add_actual(
            "org-1", "camp-1", 0.05, "job-1", "rcpt-1",
            idempotency_key="idem-001",
        )
        e2 = add_actual(
            "org-1", "camp-1", 0.10, "job-1", "rcpt-1",
            idempotency_key="idem-001",
        )
        assert e1.entry_id == e2.entry_id
        # Amount not doubled
        summary = get_campaign_summary("camp-1", "org-1")
        assert summary.actual_usd == 0.05

    @pytest.mark.unit
    def test_different_keys_both_recorded(self):
        """Different keys create separate entries."""
        add_actual("org-1", "camp-1", 0.05, "job-1", "rcpt-1", idempotency_key="k-A")
        add_actual("org-1", "camp-1", 0.03, "job-2", "rcpt-2", idempotency_key="k-B")
        summary = get_campaign_summary("camp-1", "org-1")
        assert summary.actual_usd == pytest.approx(0.08)

    @pytest.mark.unit
    def test_no_key_always_creates(self):
        """Entries without idempotency_key always create new."""
        add_actual("org-1", "camp-1", 0.05, "job-1", "rcpt-1")
        add_actual("org-1", "camp-1", 0.05, "job-1", "rcpt-1")
        summary = get_campaign_summary("camp-1", "org-1")
        assert summary.actual_usd == pytest.approx(0.10)


# =============================================================================
# Late-Cost Handling
# =============================================================================


class TestLateCost:

    @pytest.mark.unit
    def test_unresolved_then_resolved(self):
        """Unresolved entry gets resolved with actual cost later."""
        entry = add_unresolved("org-1", "camp-1", 0.05, "job-1")
        assert entry.entry_type == EntryType.UNRESOLVED

        resolve_unresolved(entry.entry_id, 0.04, "late-rcpt-123")
        summary = get_campaign_summary("camp-1", "org-1")
        assert summary.actual_usd == 0.04
        assert summary.unresolved_usd == 0.0

    @pytest.mark.unit
    def test_unresolved_visible_in_summary(self):
        """Unresolved costs visible in summary separately."""
        add_actual("org-1", "camp-1", 0.10, "job-1", "rcpt-1")
        add_unresolved("org-1", "camp-1", 0.05, "job-2")
        summary = get_campaign_summary("camp-1", "org-1")
        assert summary.actual_usd == 0.10
        assert summary.unresolved_usd == 0.05

    @pytest.mark.unit
    def test_get_unresolved_query(self):
        """Can query all unresolved entries for an org."""
        add_unresolved("org-1", "camp-1", 0.03, "job-1")
        add_unresolved("org-1", "camp-2", 0.02, "job-2")
        add_actual("org-1", "camp-1", 0.05, "job-3", "rcpt-3")
        unresolved = get_unresolved("org-1")
        assert len(unresolved) == 2


# =============================================================================
# Refunds
# =============================================================================


class TestRefunds:

    @pytest.mark.unit
    def test_refund_reduces_net_spend(self):
        """Refund reduces net spend (actual - refunded)."""
        add_actual("org-1", "camp-1", 1.00, "job-1", "rcpt-1")
        add_refund("org-1", "camp-1", 0.30, "rcpt-1")
        summary = get_campaign_summary("camp-1", "org-1")
        assert summary.actual_usd == 1.00
        assert summary.refunded_usd == 0.30
        assert summary.net_spend_usd == pytest.approx(0.70)

    @pytest.mark.unit
    def test_refund_increases_remaining_budget(self):
        """Refund increases budget remaining."""
        add_planned("org-1", "camp-1", 5.00)
        add_actual("org-1", "camp-1", 2.00, "job-1", "rcpt-1")
        add_refund("org-1", "camp-1", 0.50)
        summary = get_campaign_summary("camp-1", "org-1")
        # remaining = planned - (reserved + actual - refunded) = 5 - (0 + 2 - 0.5) = 3.5
        assert summary.budget_remaining_usd == pytest.approx(3.50)

    @pytest.mark.unit
    def test_multiple_refunds(self):
        """Multiple refunds accumulate."""
        add_actual("org-1", "camp-1", 1.00, "job-1", "rcpt-1")
        add_refund("org-1", "camp-1", 0.20)
        add_refund("org-1", "camp-1", 0.10)
        summary = get_campaign_summary("camp-1", "org-1")
        assert summary.refunded_usd == pytest.approx(0.30)


# =============================================================================
# Currency
# =============================================================================


class TestCurrency:

    @pytest.mark.unit
    def test_non_usd_with_exchange_rate(self):
        """Non-USD entry stores original + normalized amount."""
        entry = add_entry(
            org_id="org-1", campaign_id="camp-1",
            entry_type=EntryType.ACTUAL,
            amount_usd=0.85,  # Normalized
            original_amount=1.00,
            original_currency="EUR",
            exchange_rate=0.85,
            exchange_rate_version="2026-08-01",
            job_id="job-1", provider_receipt_id="rcpt-eur",
        )
        assert entry.original_currency == "EUR"
        assert entry.original_amount == 1.00
        assert entry.amount_usd == 0.85
        assert entry.exchange_rate == 0.85

    @pytest.mark.unit
    def test_summary_uses_normalized_usd(self):
        """Summary totals use normalized USD amounts."""
        add_entry(
            org_id="org-1", campaign_id="camp-1", entry_type=EntryType.ACTUAL,
            amount_usd=0.85, original_amount=1.00, original_currency="EUR",
            exchange_rate=0.85,
        )
        add_entry(
            org_id="org-1", campaign_id="camp-1", entry_type=EntryType.ACTUAL,
            amount_usd=0.50, original_amount=0.50, original_currency="USD",
        )
        summary = get_campaign_summary("camp-1", "org-1")
        assert summary.actual_usd == pytest.approx(1.35)


# =============================================================================
# Partial Success
# =============================================================================


class TestPartialSuccess:

    @pytest.mark.unit
    def test_mixed_actual_and_unresolved(self):
        """Campaign with some confirmed and some unresolved costs."""
        add_actual("org-1", "camp-1", 0.10, "job-1", "rcpt-1")
        add_actual("org-1", "camp-1", 0.08, "job-2", "rcpt-2")
        add_unresolved("org-1", "camp-1", 0.05, "job-3")
        summary = get_campaign_summary("camp-1", "org-1")
        assert summary.actual_usd == pytest.approx(0.18)
        assert summary.unresolved_usd == 0.05
        assert summary.entry_count == 3

    @pytest.mark.unit
    def test_reservation_then_partial_actual(self):
        """Reserved amount, then only partial actual (some failed)."""
        add_planned("org-1", "camp-1", 2.00)
        add_reservation("org-1", "camp-1", 0.50, "job-1")
        add_reservation("org-1", "camp-1", 0.50, "job-2")
        add_actual("org-1", "camp-1", 0.45, "job-1", "rcpt-1")
        # job-2 failed — no actual recorded
        summary = get_campaign_summary("camp-1", "org-1")
        assert summary.planned_usd == 2.00
        assert summary.reserved_usd == 1.00
        assert summary.actual_usd == 0.45


# =============================================================================
# Tenant Isolation
# =============================================================================


class TestTenantIsolation:

    @pytest.mark.unit
    def test_summary_scoped_to_org(self):
        """Summary only includes entries from requesting org."""
        add_actual("org-1", "camp-1", 1.00, "job-1", "rcpt-1")
        add_actual("org-2", "camp-1", 5.00, "job-2", "rcpt-2")
        summary = get_campaign_summary("camp-1", "org-1")
        assert summary.actual_usd == 1.00  # Not 6.00

    @pytest.mark.unit
    def test_entries_scoped_to_org(self):
        """get_entries only returns requesting org's entries."""
        add_actual("org-1", "camp-1", 0.50, "job-1", "rcpt-1")
        add_actual("org-evil", "camp-1", 9.99, "job-x", "rcpt-x")
        entries = get_entries("camp-1", "org-1")
        assert len(entries) == 1
        assert entries[0].org_id == "org-1"

    @pytest.mark.unit
    def test_missing_context_raises(self):
        """Missing org_id raises error."""
        with pytest.raises(LedgerError) as exc_info:
            add_entry(org_id="", campaign_id="camp-1", entry_type=EntryType.ACTUAL, amount_usd=1.0)
        assert exc_info.value.code == "MISSING_CONTEXT"


# =============================================================================
# Derived Totals
# =============================================================================


class TestDerivedTotals:

    @pytest.mark.unit
    def test_budget_remaining_computed(self):
        """Budget remaining = planned - (reserved + actual - refunded)."""
        add_planned("org-1", "camp-1", 10.00)
        add_reservation("org-1", "camp-1", 2.00, "job-1")
        add_actual("org-1", "camp-1", 1.50, "job-2", "rcpt-2")
        add_refund("org-1", "camp-1", 0.50)
        summary = get_campaign_summary("camp-1", "org-1")
        # 10 - (2 + 1.5 - 0.5) = 10 - 3 = 7
        assert summary.budget_remaining_usd == pytest.approx(7.00)

    @pytest.mark.unit
    def test_empty_campaign_zeroes(self):
        """Campaign with no entries has all zeroes."""
        summary = get_campaign_summary("camp-empty", "org-1")
        assert summary.actual_usd == 0.0
        assert summary.planned_usd == 0.0
        assert summary.entry_count == 0

    @pytest.mark.unit
    def test_summary_serializable(self):
        """CampaignBudgetSummary.to_dict() is JSON-serializable."""
        import json
        add_planned("org-1", "camp-1", 5.00)
        summary = get_campaign_summary("camp-1", "org-1")
        json.dumps(summary.to_dict())

    @pytest.mark.unit
    def test_entry_serializable(self):
        """LedgerEntry.to_dict() is JSON-serializable."""
        import json
        entry = add_actual("org-1", "camp-1", 0.05, "job-1", "rcpt-1")
        json.dumps(entry.to_dict())


# =============================================================================
# Reconciliation
# =============================================================================


class TestReconciliation:

    @pytest.mark.unit
    def test_confirm_entry(self):
        """Confirming entry sets CONFIRMED state."""
        entry = add_reservation("org-1", "camp-1", 0.50, "job-1")
        confirm_entry(entry.entry_id)
        assert entry.reconciliation_state == ReconciliationState.CONFIRMED

    @pytest.mark.unit
    def test_dispute_entry(self):
        """Disputing entry sets DISPUTED state with reason."""
        entry = add_actual("org-1", "camp-1", 0.50, "job-1", "rcpt-1")
        dispute_entry(entry.entry_id, reason="Provider charged $0.60 not $0.50")
        assert entry.reconciliation_state == ReconciliationState.DISPUTED

    @pytest.mark.unit
    def test_resolve_converts_to_actual(self):
        """Resolving unresolved converts to ACTUAL with receipt."""
        entry = add_unresolved("org-1", "camp-1", 0.05, "job-1")
        resolve_unresolved(entry.entry_id, 0.04, "late-rcpt")
        assert entry.entry_type == EntryType.ACTUAL
        assert entry.amount_usd == 0.04
        assert entry.provider_receipt_id == "late-rcpt"
        assert entry.reconciliation_state == ReconciliationState.CONFIRMED
