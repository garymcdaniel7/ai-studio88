"""Thread-safe integer consumer-credit ledger.

This module is deliberately separate from ``backend.cost_ledger``. The latter
accounts for infrastructure spend in USD; this ledger accounts for credits
consumed by an organisation's generation jobs.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from threading import RLock
from uuid import UUID, uuid4


class CreditLedgerError(Exception):
    """Base exception for consumer-credit ledger failures."""


class InsufficientCredits(CreditLedgerError):  # noqa: N818
    """Raised when a debit would make an organisation's balance negative."""


class GenerationNotSuccessful(CreditLedgerError):  # noqa: N818
    """Raised when a generation debit is attempted before success."""


class CreditEntryType(str, Enum):
    """Allowed consumer-credit ledger entry types."""

    GRANT = "grant"
    DEBIT = "debit"
    REFUND = "refund"
    EXPIRE = "expire"


@dataclass(frozen=True, slots=True)
class CreditLedgerEntry:
    """Immutable representation of one signed credit-ledger entry."""

    id: UUID
    org_id: UUID | str
    entry_type: CreditEntryType
    amount: int
    balance_after: int
    reason: str
    ref_id: str | None
    created_at: datetime


OrgID = UUID | str


class CreditLedgerService:
    """Apply atomic grants, successful-generation debits, refunds, and expiry."""

    def __init__(self) -> None:
        self._entries: list[CreditLedgerEntry] = []
        self._balances: dict[Hashable, int] = {}
        self._ref_index: dict[tuple[Hashable, CreditEntryType, str], CreditLedgerEntry] = {}
        self._lock = RLock()

    def entries(self, org_id: OrgID | None = None) -> tuple[CreditLedgerEntry, ...]:
        """Return an immutable snapshot of entries, optionally tenant-scoped."""
        with self._lock:
            if org_id is None:
                return tuple(self._entries)
            key = self._key(org_id)
            return tuple(entry for entry in self._entries if self._key(entry.org_id) == key)

    def balance(self, org_id: OrgID) -> int:
        """Return the current non-negative balance for an organisation."""
        with self._lock:
            return self._balances.get(self._key(org_id), 0)

    def grant(
        self,
        org_id: OrgID,
        amount: int,
        *,
        reason: str,
        ref_id: str | None = None,
    ) -> CreditLedgerEntry:
        """Grant credits to an organisation."""
        return self._append(
            org_id,
            CreditEntryType.GRANT,
            self._positive_amount(amount),
            reason,
            ref_id,
        )

    def debit_after_success(
        self,
        org_id: OrgID,
        amount: int,
        *,
        reason: str,
        ref_id: str | None = None,
        generation_succeeded: bool,
    ) -> CreditLedgerEntry:
        """Debit credits only after an authoritative generation success event."""
        if not generation_succeeded:
            raise GenerationNotSuccessful(
                "Credits are debited only after generation success is recorded."
            )

        debit_amount = self._positive_amount(amount)
        with self._lock:
            key = self._key(org_id)
            if ref_id is not None:
                existing = self._ref_index.get((key, CreditEntryType.DEBIT, ref_id))
                if existing is not None:
                    return existing

            current = self._balances.get(key, 0)
            if current < debit_amount:
                raise InsufficientCredits(
                    f"Organisation has {current} credits; debit requires {debit_amount}."
                )

            return self._append_locked(
                org_id,
                CreditEntryType.DEBIT,
                -debit_amount,
                reason,
                ref_id,
            )

    def refund(
        self,
        org_id: OrgID,
        amount: int,
        *,
        reason: str,
        ref_id: str | None = None,
    ) -> CreditLedgerEntry:
        """Return credits for a failed or cancelled generation."""
        return self._append(
            org_id,
            CreditEntryType.REFUND,
            self._positive_amount(amount),
            reason,
            ref_id,
        )

    def expire(
        self,
        org_id: OrgID,
        amount: int,
        *,
        reason: str,
        ref_id: str | None = None,
    ) -> CreditLedgerEntry:
        """Expire unused credits without allowing a negative balance."""
        expire_amount = self._positive_amount(amount)
        with self._lock:
            key = self._key(org_id)
            current = self._balances.get(key, 0)
            if current < expire_amount:
                raise InsufficientCredits(
                    f"Organisation has {current} credits; expiry requires {expire_amount}."
                )
            return self._append_locked(
                org_id,
                CreditEntryType.EXPIRE,
                -expire_amount,
                reason,
                ref_id,
            )

    @staticmethod
    def _key(org_id: OrgID) -> str:
        """Normalize UUID and string tenant identifiers to one key."""
        if not org_id:
            raise ValueError("org_id is required")
        return str(org_id)

    @staticmethod
    def _positive_amount(amount: int) -> int:
        """Validate a positive integer credit amount."""
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise ValueError("credit amount must be a positive integer")
        return amount

    def _append(
        self,
        org_id: OrgID,
        entry_type: CreditEntryType,
        amount: int,
        reason: str,
        ref_id: str | None,
    ) -> CreditLedgerEntry:
        """Append one entry while holding the ledger lock."""
        if not reason.strip():
            raise ValueError("reason is required")
        with self._lock:
            key = self._key(org_id)
            if ref_id is not None:
                existing = self._ref_index.get((key, entry_type, ref_id))
                if existing is not None:
                    return existing
            return self._append_locked(org_id, entry_type, amount, reason, ref_id)

    def _append_locked(
        self,
        org_id: OrgID,
        entry_type: CreditEntryType,
        amount: int,
        reason: str,
        ref_id: str | None,
    ) -> CreditLedgerEntry:
        """Append an entry; caller must hold ``_lock``."""
        key = self._key(org_id)
        balance_after = self._balances.get(key, 0) + amount
        if balance_after < 0:
            raise InsufficientCredits("ledger invariant violated: balance would be negative")

        entry = CreditLedgerEntry(
            id=uuid4(),
            org_id=org_id,
            entry_type=entry_type,
            amount=amount,
            balance_after=balance_after,
            reason=reason,
            ref_id=ref_id,
            created_at=datetime.now(UTC),
        )
        self._balances[key] = balance_after
        self._entries.append(entry)
        if ref_id is not None:
            self._ref_index[(key, entry_type, ref_id)] = entry
        return entry


CreditLedger = CreditLedgerService
