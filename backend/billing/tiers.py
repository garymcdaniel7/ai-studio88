"""Credit tiers and deterministic grant/expiry scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from backend.billing.credit_ledger import CreditLedgerEntry, CreditLedgerService

FREE_TIER_EXPIRY_DAYS = 90


@dataclass(frozen=True, slots=True)
class TierDefinition:
    """Consumer tier credit policy."""

    id: str
    monthly_credits: int | None
    one_time_credits: int | None = None
    free: bool = False
    expiry_days: int | None = None


TIERS: dict[str, TierDefinition] = {
    "screen_test": TierDefinition(
        id="screen_test",
        monthly_credits=None,
        one_time_credits=250,
        free=True,
        expiry_days=FREE_TIER_EXPIRY_DAYS,
    ),
    "day_player": TierDefinition(id="day_player", monthly_credits=2_000),
    "series_regular": TierDefinition(id="series_regular", monthly_credits=8_000),
    "showrunner": TierDefinition(id="showrunner", monthly_credits=25_000),
    "hefner": TierDefinition(id="hefner", monthly_credits=None),
}


class CreditGrantScheduler:
    """Idempotently grant monthly credits and expire free-tier credits."""

    def __init__(self, ledger: CreditLedgerService) -> None:
        self.ledger = ledger
        self._free_grants: dict[str, tuple[int, datetime, str]] = {}

    def grant_for_period(
        self,
        org_id: UUID | str,
        tier_id: str,
        *,
        period_start: datetime | None = None,
    ) -> CreditLedgerEntry | None:
        """Grant the tier's one-time or monthly credits once per period."""
        tier = self._tier(tier_id)
        timestamp = period_start or datetime.now(UTC)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        if tier.free:
            amount = tier.one_time_credits
            if amount is None:
                return None
            ref_id = f"grant:{tier.id}:{org_id}"
            entry = self.ledger.grant(
                org_id,
                amount,
                reason="screen-test-free-grant",
                ref_id=ref_id,
            )
            self._free_grants[str(org_id)] = (
                amount,
                timestamp + timedelta(days=tier.expiry_days or FREE_TIER_EXPIRY_DAYS),
                ref_id,
            )
            return entry

        if tier.monthly_credits is None:
            return None

        period = timestamp.strftime("%Y-%m")
        return self.ledger.grant(
            org_id,
            tier.monthly_credits,
            reason=f"{tier.id}-monthly-grant",
            ref_id=f"grant:{tier.id}:{org_id}:{period}",
        )

    def run_expiry(self, *, now: datetime | None = None) -> list[CreditLedgerEntry]:
        """Expire due free-tier balances and return generated ledger entries."""
        current_time = now or datetime.now(UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        expired: list[CreditLedgerEntry] = []
        for org_id, (amount, expires_at, grant_ref_id) in tuple(self._free_grants.items()):
            if current_time < expires_at:
                continue

            remaining = min(amount, self.ledger.balance(org_id))
            if remaining:
                expired.append(
                    self.ledger.expire(
                        org_id,
                        remaining,
                        reason="screen-test-free-grant-expired",
                        ref_id=f"expire:{grant_ref_id}",
                    )
                )
            del self._free_grants[org_id]
        return expired

    @staticmethod
    def _tier(tier_id: str) -> TierDefinition:
        """Resolve a tier or raise a clear validation error."""
        try:
            return TIERS[tier_id]
        except KeyError as exc:
            raise ValueError(f"Unknown credit tier: {tier_id}") from exc


GrantScheduler = CreditGrantScheduler


def get_tier(tier_id: str) -> TierDefinition:
    """Return a configured tier definition."""
    return CreditGrantScheduler._tier(tier_id)
