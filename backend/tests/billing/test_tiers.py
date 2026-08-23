"""Tests for tier grants and free-credit expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from billing.credit_ledger import CreditLedgerService
from billing.tiers import FREE_TIER_EXPIRY_DAYS, TIERS, CreditGrantScheduler


@pytest.mark.unit
def test_tier_grants_match_pricing_plan() -> None:
    """All five pricing tiers expose the specified grant policy."""
    assert TIERS["screen_test"].one_time_credits == 250
    assert TIERS["day_player"].monthly_credits == 2_000
    assert TIERS["series_regular"].monthly_credits == 8_000
    assert TIERS["showrunner"].monthly_credits == 25_000
    assert TIERS["hefner"].monthly_credits is None
    assert FREE_TIER_EXPIRY_DAYS == 90


@pytest.mark.unit
def test_monthly_grant_is_idempotent() -> None:
    """Repeating a monthly scheduler run cannot double-grant credits."""
    ledger = CreditLedgerService()
    scheduler = CreditGrantScheduler(ledger)
    org_id = uuid4()
    period_start = datetime(2026, 8, 1, tzinfo=UTC)

    first = scheduler.grant_for_period(org_id, "day_player", period_start=period_start)
    second = scheduler.grant_for_period(org_id, "day_player", period_start=period_start)

    assert first is second
    assert ledger.balance(org_id) == 2_000


@pytest.mark.unit
def test_screen_test_credits_expire_after_90_days() -> None:
    """Unused free credits are removed when the 90-day expiry clock elapses."""
    ledger = CreditLedgerService()
    scheduler = CreditGrantScheduler(ledger)
    org_id = uuid4()
    granted_at = datetime(2026, 8, 1, tzinfo=UTC)

    scheduler.grant_for_period(org_id, "screen_test", period_start=granted_at)
    expired = scheduler.run_expiry(now=granted_at + timedelta(days=90))

    assert len(expired) == 1
    assert ledger.balance(org_id) == 0
    assert expired[0].amount == -250
