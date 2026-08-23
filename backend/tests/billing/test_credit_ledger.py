"""Invariant tests for integer consumer-credit accounting."""

from __future__ import annotations

from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from billing.credit_ledger import (
    CreditLedgerService,
    GenerationNotSuccessful,
    InsufficientCredits,
)


@pytest.mark.unit
def test_debit_requires_successful_generation() -> None:
    """A failed generation cannot consume credits."""
    ledger = CreditLedgerService()
    org_id = uuid4()
    ledger.grant(org_id, 10, reason="screen-test")

    with pytest.raises(GenerationNotSuccessful):
        ledger.debit_after_success(
            org_id,
            4,
            reason="render",
            ref_id="job-failed",
            generation_succeeded=False,
        )

    assert ledger.balance(org_id) == 10


@pytest.mark.unit
def test_debit_cannot_make_balance_negative() -> None:
    """Insufficient credits reject a debit and preserve the prior balance."""
    ledger = CreditLedgerService()
    org_id = uuid4()
    ledger.grant(org_id, 3, reason="screen-test")

    with pytest.raises(InsufficientCredits):
        ledger.debit_after_success(
            org_id,
            4,
            reason="render",
            ref_id="job-too-expensive",
            generation_succeeded=True,
        )

    assert ledger.balance(org_id) == 3


@pytest.mark.unit
@given(
    grants=st.lists(st.integers(min_value=1, max_value=100), min_size=1, max_size=20),
    debits=st.lists(st.integers(min_value=1, max_value=100), max_size=20),
)
def test_balance_never_negative(grants: list[int], debits: list[int]) -> None:
    """Arbitrary accepted grant/debit sequences preserve non-negative balance."""
    ledger = CreditLedgerService()
    org_id = uuid4()

    for index, amount in enumerate(grants):
        ledger.grant(org_id, amount, reason="test-grant", ref_id=f"grant-{index}")

    for index, amount in enumerate(debits):
        try:
            ledger.debit_after_success(
                org_id,
                amount,
                reason="successful-render",
                ref_id=f"debit-{index}",
                generation_succeeded=True,
            )
        except InsufficientCredits:
            pass

        assert ledger.balance(org_id) >= 0
