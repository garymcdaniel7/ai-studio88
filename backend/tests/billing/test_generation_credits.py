"""Tests for generation credit settlement hooks."""

from __future__ import annotations

import pytest
from backend import billing_router

from billing.credit_ledger import CreditLedgerService


@pytest.fixture
def isolated_credit_ledger(monkeypatch: pytest.MonkeyPatch) -> CreditLedgerService:
    """Provide a fresh consumer ledger for each settlement test."""
    ledger = CreditLedgerService()
    monkeypatch.setattr(billing_router, "_consumer_credit_ledger", ledger)
    return ledger


@pytest.mark.unit
@pytest.mark.asyncio
async def test_success_debits_after_generation(isolated_credit_ledger: CreditLedgerService) -> None:
    """A successful preset execution debits its registry cost exactly once."""
    isolated_credit_ledger.grant("org-1", 10, reason="test-grant")

    entry = await billing_router.settle_generation_credits(
        "org-1",
        "cinematic-portrait",
        "job-1",
        generation_succeeded=True,
    )

    assert entry is not None
    assert entry.amount == -1
    assert isolated_credit_ledger.balance("org-1") == 9


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failure_before_debit_is_zero_charge(
    isolated_credit_ledger: CreditLedgerService,
) -> None:
    """A failed job does not consume or create credits without a prior debit."""
    isolated_credit_ledger.grant("org-1", 10, reason="test-grant")

    entry = await billing_router.settle_generation_credits(
        "org-1",
        "cinematic-portrait",
        "job-failed",
        generation_succeeded=False,
    )

    assert entry is None
    assert isolated_credit_ledger.balance("org-1") == 10


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failure_after_debit_refunds_once(
    isolated_credit_ledger: CreditLedgerService,
) -> None:
    """A downstream failure after debit is automatically refunded idempotently."""
    isolated_credit_ledger.grant("org-1", 10, reason="test-grant")
    await billing_router.debit_after_generation_success("org-1", "fast-draft", "job-1")

    first_refund = await billing_router.refund_failed_generation("org-1", "fast-draft", "job-1")
    second_refund = await billing_router.refund_failed_generation("org-1", "fast-draft", "job-1")

    assert first_refund is second_refund
    assert isolated_credit_ledger.balance("org-1") == 10
