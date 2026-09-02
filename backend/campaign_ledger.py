"""Campaign Financial Ledger — Story 131.

Evidence-backed financial reconciliation for campaigns. Every total is
derived from itemized authoritative entries — never from caller-supplied
aggregate values.

Entry Types:
    PLANNED     — Budget allocation at campaign creation
    RESERVED    — Cost reserved before job execution (Story 058)
    ESTIMATED   — Provider estimate before actual charge
    ACTUAL      — Confirmed provider charge with receipt
    REFUNDED    — Credit/refund from provider or internal
    ATTRIBUTED  — Revenue/value attributed to spend (analytics-linked)
    UNRESOLVED  — Cost unknown (provider timeout, reconciliation pending)

Reconciliation States:
    PENDING     — Entry awaiting confirmation
    CONFIRMED   — Provider receipt verified
    DISPUTED    — Amount differs from estimate, needs review
    WRITTEN_OFF — Unrecoverable, accepted as loss

Invariants:
1. Totals derived from entries (never set directly)
2. Duplicate receipts cannot double-count (idempotency_key)
3. Estimated vs actual remain distinct
4. Attribution references explicit policy version and analytics snapshot
5. Currency and normalization rate recorded per entry
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Entry Types
# =============================================================================


class EntryType(StrEnum):
    PLANNED = "planned"
    RESERVED = "reserved"
    ESTIMATED = "estimated"
    ACTUAL = "actual"
    REFUNDED = "refunded"
    ATTRIBUTED = "attributed"
    UNRESOLVED = "unresolved"


class ReconciliationState(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
    WRITTEN_OFF = "written_off"


# =============================================================================
# Ledger Entry
# =============================================================================


@dataclass
class LedgerEntry:
    """A single financial entry with full evidence trail."""

    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    campaign_id: str = ""

    # Classification
    entry_type: EntryType = EntryType.ACTUAL
    reconciliation_state: ReconciliationState = ReconciliationState.PENDING

    # Amount
    amount_usd: float = 0.0         # Normalized to USD
    original_amount: float = 0.0    # In original currency
    original_currency: str = "USD"
    exchange_rate: float = 1.0      # Rate used for normalization
    exchange_rate_version: str = "" # Rate source/date

    # Evidence references
    content_item_id: str = ""
    platform_variant_id: str = ""
    job_id: str = ""                # Generation or publishing job
    provider_attempt_id: str = ""
    provider_receipt_id: str = ""   # Provider's charge receipt
    idempotency_key: str = ""       # Prevents duplicate entries

    # Attribution (optional, for ATTRIBUTED type)
    attribution_policy_version: str = ""
    attribution_window: str = ""    # e.g., "7_day_click"
    analytics_snapshot_id: str = ""

    # Metadata
    description: str = ""
    created_by: str = ""            # actor or "system"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "org_id": self.org_id,
            "campaign_id": self.campaign_id,
            "entry_type": self.entry_type.value,
            "reconciliation_state": self.reconciliation_state.value,
            "amount_usd": self.amount_usd,
            "original_amount": self.original_amount,
            "original_currency": self.original_currency,
            "job_id": self.job_id,
            "provider_receipt_id": self.provider_receipt_id,
            "description": self.description,
            "created_at": self.created_at,
        }


# =============================================================================
# Campaign Budget Summary (derived, never set directly)
# =============================================================================


@dataclass
class CampaignBudgetSummary:
    """Derived financial summary for a campaign."""

    campaign_id: str = ""
    org_id: str = ""
    planned_usd: float = 0.0
    reserved_usd: float = 0.0
    estimated_usd: float = 0.0
    actual_usd: float = 0.0
    refunded_usd: float = 0.0
    attributed_usd: float = 0.0
    unresolved_usd: float = 0.0
    # Computed
    net_spend_usd: float = 0.0      # actual - refunded
    budget_remaining_usd: float = 0.0  # planned - (reserved + actual - refunded)
    entry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "planned_usd": self.planned_usd,
            "reserved_usd": self.reserved_usd,
            "estimated_usd": self.estimated_usd,
            "actual_usd": self.actual_usd,
            "refunded_usd": self.refunded_usd,
            "attributed_usd": self.attributed_usd,
            "unresolved_usd": self.unresolved_usd,
            "net_spend_usd": self.net_spend_usd,
            "budget_remaining_usd": self.budget_remaining_usd,
            "entry_count": self.entry_count,
        }


# =============================================================================
# Store
# =============================================================================

_ledger: list[LedgerEntry] = []
_idempotency_index: set[str] = set()


def clear_ledger() -> None:
    _ledger.clear()
    _idempotency_index.clear()


# =============================================================================
# Entry Creation (idempotent)
# =============================================================================


class LedgerError(Exception):
    def __init__(self, message: str, code: str = "LEDGER_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class DuplicateEntryError(LedgerError):
    def __init__(self, idempotency_key: str):
        super().__init__(
            f"Duplicate ledger entry with key {idempotency_key}",
            code="DUPLICATE_ENTRY",
        )


def add_entry(
    *,
    org_id: str,
    campaign_id: str,
    entry_type: EntryType,
    amount_usd: float,
    job_id: str = "",
    provider_receipt_id: str = "",
    provider_attempt_id: str = "",
    content_item_id: str = "",
    platform_variant_id: str = "",
    original_amount: float | None = None,
    original_currency: str = "USD",
    exchange_rate: float = 1.0,
    exchange_rate_version: str = "",
    description: str = "",
    idempotency_key: str = "",
    created_by: str = "system",
    attribution_policy_version: str = "",
    attribution_window: str = "",
    analytics_snapshot_id: str = "",
) -> LedgerEntry:
    """Add a financial entry to the campaign ledger.

    Idempotent: duplicate idempotency_key is silently ignored (returns existing).
    """
    if not org_id or not campaign_id:
        raise LedgerError("org_id and campaign_id required", code="MISSING_CONTEXT")

    # Idempotency check
    if idempotency_key:
        if idempotency_key in _idempotency_index:
            # Find and return existing
            for entry in _ledger:
                if entry.idempotency_key == idempotency_key:
                    return entry
            raise DuplicateEntryError(idempotency_key)
        _idempotency_index.add(idempotency_key)

    entry = LedgerEntry(
        org_id=org_id,
        campaign_id=campaign_id,
        entry_type=entry_type,
        amount_usd=amount_usd,
        original_amount=original_amount if original_amount is not None else amount_usd,
        original_currency=original_currency,
        exchange_rate=exchange_rate,
        exchange_rate_version=exchange_rate_version,
        job_id=job_id,
        provider_receipt_id=provider_receipt_id,
        provider_attempt_id=provider_attempt_id,
        content_item_id=content_item_id,
        platform_variant_id=platform_variant_id,
        description=description,
        idempotency_key=idempotency_key,
        created_by=created_by,
        attribution_policy_version=attribution_policy_version,
        attribution_window=attribution_window,
        analytics_snapshot_id=analytics_snapshot_id,
        reconciliation_state=ReconciliationState.PENDING,
    )

    _ledger.append(entry)
    return entry


# =============================================================================
# Convenience Functions
# =============================================================================


def add_planned(org_id: str, campaign_id: str, amount_usd: float, **kwargs) -> LedgerEntry:
    """Record planned budget allocation."""
    return add_entry(org_id=org_id, campaign_id=campaign_id, entry_type=EntryType.PLANNED, amount_usd=amount_usd, **kwargs)


def add_reservation(org_id: str, campaign_id: str, amount_usd: float, job_id: str, **kwargs) -> LedgerEntry:
    """Record cost reservation before execution."""
    return add_entry(org_id=org_id, campaign_id=campaign_id, entry_type=EntryType.RESERVED, amount_usd=amount_usd, job_id=job_id, **kwargs)


def add_actual(org_id: str, campaign_id: str, amount_usd: float, job_id: str, provider_receipt_id: str, **kwargs) -> LedgerEntry:
    """Record confirmed actual provider charge."""
    entry = add_entry(
        org_id=org_id, campaign_id=campaign_id, entry_type=EntryType.ACTUAL,
        amount_usd=amount_usd, job_id=job_id, provider_receipt_id=provider_receipt_id,
        **kwargs,
    )
    entry.reconciliation_state = ReconciliationState.CONFIRMED
    return entry


def add_refund(org_id: str, campaign_id: str, amount_usd: float, provider_receipt_id: str = "", **kwargs) -> LedgerEntry:
    """Record a refund/credit (negative spend)."""
    return add_entry(
        org_id=org_id, campaign_id=campaign_id, entry_type=EntryType.REFUNDED,
        amount_usd=amount_usd, provider_receipt_id=provider_receipt_id, **kwargs,
    )


def add_unresolved(org_id: str, campaign_id: str, amount_usd: float, job_id: str, **kwargs) -> LedgerEntry:
    """Record an unresolved cost (provider outcome unknown)."""
    return add_entry(org_id=org_id, campaign_id=campaign_id, entry_type=EntryType.UNRESOLVED, amount_usd=amount_usd, job_id=job_id, **kwargs)


# =============================================================================
# Reconciliation
# =============================================================================


def confirm_entry(entry_id: str) -> LedgerEntry | None:
    """Mark an entry as confirmed (verified by provider evidence)."""
    for entry in _ledger:
        if entry.entry_id == entry_id:
            entry.reconciliation_state = ReconciliationState.CONFIRMED
            return entry
    return None


def dispute_entry(entry_id: str, reason: str = "") -> LedgerEntry | None:
    """Mark an entry as disputed (amount discrepancy)."""
    for entry in _ledger:
        if entry.entry_id == entry_id:
            entry.reconciliation_state = ReconciliationState.DISPUTED
            entry.description = f"DISPUTED: {reason}" if reason else entry.description
            return entry
    return None


def resolve_unresolved(entry_id: str, actual_amount_usd: float, provider_receipt_id: str) -> LedgerEntry | None:
    """Resolve an unresolved entry with actual cost evidence."""
    for entry in _ledger:
        if entry.entry_id == entry_id and entry.entry_type == EntryType.UNRESOLVED:
            entry.entry_type = EntryType.ACTUAL
            entry.amount_usd = actual_amount_usd
            entry.provider_receipt_id = provider_receipt_id
            entry.reconciliation_state = ReconciliationState.CONFIRMED
            return entry
    return None


# =============================================================================
# Derived Totals
# =============================================================================


def get_campaign_summary(campaign_id: str, org_id: str) -> CampaignBudgetSummary:
    """Derive campaign budget summary from ledger entries.

    All totals computed from entries — never set directly.
    """
    entries = [e for e in _ledger if e.campaign_id == campaign_id and e.org_id == org_id]

    summary = CampaignBudgetSummary(campaign_id=campaign_id, org_id=org_id)
    summary.entry_count = len(entries)

    for entry in entries:
        if entry.entry_type == EntryType.PLANNED:
            summary.planned_usd += entry.amount_usd
        elif entry.entry_type == EntryType.RESERVED:
            summary.reserved_usd += entry.amount_usd
        elif entry.entry_type == EntryType.ESTIMATED:
            summary.estimated_usd += entry.amount_usd
        elif entry.entry_type == EntryType.ACTUAL:
            summary.actual_usd += entry.amount_usd
        elif entry.entry_type == EntryType.REFUNDED:
            summary.refunded_usd += entry.amount_usd
        elif entry.entry_type == EntryType.ATTRIBUTED:
            summary.attributed_usd += entry.amount_usd
        elif entry.entry_type == EntryType.UNRESOLVED:
            summary.unresolved_usd += entry.amount_usd

    summary.net_spend_usd = round(summary.actual_usd - summary.refunded_usd, 4)
    summary.budget_remaining_usd = round(
        summary.planned_usd - (summary.reserved_usd + summary.actual_usd - summary.refunded_usd), 4
    )

    return summary


# =============================================================================
# Queries
# =============================================================================


def get_entries(campaign_id: str, org_id: str, entry_type: EntryType | None = None) -> list[LedgerEntry]:
    """Get ledger entries (tenant-scoped)."""
    results = [e for e in _ledger if e.campaign_id == campaign_id and e.org_id == org_id]
    if entry_type:
        results = [e for e in results if e.entry_type == entry_type]
    return results


def get_unresolved(org_id: str) -> list[LedgerEntry]:
    """Get all unresolved entries for an org."""
    return [e for e in _ledger if e.org_id == org_id and e.entry_type == EntryType.UNRESOLVED]
