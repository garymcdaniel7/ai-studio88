"""Calendar Status Derivation — Story 125.

Separate editorial lifecycle from execution lifecycle. Protected states
are derived from authoritative evidence — clients cannot forge completion.

Editorial States (user-controlled):
    DRAFT       → Content being created
    READY       → Content complete, awaiting approval
    APPROVED    → Passed preflight + approval (system-set after binding)
    SCHEDULED   → Scheduled for future publication
    CANCELLED   → Cancelled by user

Execution States (system-derived, protected):
    PENDING     → Scheduled, not yet dispatched
    PUBLISHING  → Actively being posted to destination(s)
    PUBLISHED   → All destinations confirmed with provider receipt
    PARTIAL     → Some destinations succeeded, others failed
    FAILED      → All destinations failed
    RECONCILING → Verifying status with provider after ambiguous result

Protected Fields (cannot be set by client directly):
    execution_state, published_at, provider_receipts, attempt_count

Derivation Rules:
    - PUBLISHED requires verified provider receipt for every destination
    - PARTIAL when at least one succeeds and at least one fails
    - FAILED when all destinations fail
    - Transitions require evidence (receipt, error, cancellation actor)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Editorial State (user-controllable)
# =============================================================================


class EditorialState(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    APPROVED = "approved"       # System-set after preflight binding
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


# Valid editorial transitions (user-initiated)
EDITORIAL_TRANSITIONS: dict[tuple[EditorialState, EditorialState], bool] = {
    (EditorialState.DRAFT, EditorialState.READY): True,
    (EditorialState.READY, EditorialState.DRAFT): True,     # Send back
    (EditorialState.READY, EditorialState.APPROVED): True,  # Via system after preflight
    (EditorialState.APPROVED, EditorialState.SCHEDULED): True,
    (EditorialState.SCHEDULED, EditorialState.CANCELLED): True,
    (EditorialState.APPROVED, EditorialState.CANCELLED): True,
    (EditorialState.DRAFT, EditorialState.CANCELLED): True,
}


# =============================================================================
# Execution State (system-derived, protected)
# =============================================================================


class ExecutionState(StrEnum):
    PENDING = "pending"         # Scheduled, not yet dispatched
    PUBLISHING = "publishing"   # Actively posting
    PUBLISHED = "published"     # All destinations confirmed
    PARTIAL = "partial"         # Mixed results
    FAILED = "failed"           # All destinations failed
    RECONCILING = "reconciling" # Verifying with provider
    NONE = "none"               # Not yet in execution


# =============================================================================
# Destination Result
# =============================================================================


@dataclass
class DestinationResult:
    """Result for a single publishing destination."""

    destination_id: str = ""        # Platform account/page
    platform: str = ""              # instagram, tiktok, youtube...
    state: str = "pending"          # pending, publishing, published, failed
    provider_receipt_id: str = ""   # External ID from provider
    provider_url: str = ""          # Published content URL
    error_message: str = ""
    attempt_count: int = 0
    last_attempt_at: str | None = None
    published_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "destination_id": self.destination_id,
            "platform": self.platform,
            "state": self.state,
            "provider_receipt_id": self.provider_receipt_id,
            "provider_url": self.provider_url,
            "error_message": self.error_message,
            "attempt_count": self.attempt_count,
            "published_at": self.published_at,
        }


# =============================================================================
# Calendar Entry Status
# =============================================================================


@dataclass
class CalendarEntryStatus:
    """Combined editorial + execution status for a calendar entry."""

    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    content_item_id: str = ""

    # Editorial (user-controlled)
    editorial_state: EditorialState = EditorialState.DRAFT

    # Execution (system-derived — PROTECTED)
    execution_state: ExecutionState = ExecutionState.NONE
    destinations: list[DestinationResult] = field(default_factory=list)

    # Aggregate (derived)
    published_at: str | None = None

    # Audit
    transitions: list[dict] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "org_id": self.org_id,
            "content_item_id": self.content_item_id,
            "editorial_state": self.editorial_state.value,
            "execution_state": self.execution_state.value,
            "destinations": [d.to_dict() for d in self.destinations],
            "published_at": self.published_at,
            "transition_count": len(self.transitions),
            "updated_at": self.updated_at,
        }


# =============================================================================
# Transition Errors
# =============================================================================


class InvalidTransitionError(Exception):
    def __init__(self, message: str, code: str = "INVALID_TRANSITION"):
        self.message = message
        self.code = code
        super().__init__(message)


class ProtectedFieldError(Exception):
    """Raised when client attempts to set a protected execution state."""

    def __init__(self, field_name: str):
        self.message = f"Field '{field_name}' is protected and cannot be set by client"
        self.field_name = field_name
        super().__init__(self.message)


PROTECTED_FIELDS: set[str] = {
    "execution_state", "published_at", "provider_receipts", "attempt_count",
}


# =============================================================================
# Editorial Transitions (user-initiated)
# =============================================================================


def transition_editorial(
    entry: CalendarEntryStatus,
    new_state: EditorialState,
    *,
    actor: str,
    reason: str = "",
) -> CalendarEntryStatus:
    """Transition editorial state with validation.

    Raises InvalidTransitionError on invalid transition.
    """
    key = (entry.editorial_state, new_state)
    if key not in EDITORIAL_TRANSITIONS:
        raise InvalidTransitionError(
            f"Invalid editorial transition: {entry.editorial_state.value} → {new_state.value}"
        )

    entry.transitions.append({
        "type": "editorial",
        "from": entry.editorial_state.value,
        "to": new_state.value,
        "actor": actor,
        "reason": reason,
        "at": datetime.now(UTC).isoformat(),
    })
    entry.editorial_state = new_state
    entry.updated_at = datetime.now(UTC).isoformat()
    return entry


# =============================================================================
# Execution State Derivation (system-only)
# =============================================================================


def derive_execution_state(entry: CalendarEntryStatus) -> ExecutionState:
    """Derive execution state from destination results.

    Rules:
    1. No destinations → NONE
    2. All pending → PENDING
    3. Any publishing → PUBLISHING
    4. All published (with receipts) → PUBLISHED
    5. Some published + some failed → PARTIAL
    6. All failed → FAILED
    7. Any reconciling → RECONCILING
    """
    if not entry.destinations:
        return ExecutionState.NONE

    states = [d.state for d in entry.destinations]

    if all(s == "pending" for s in states):
        return ExecutionState.PENDING

    if any(s == "reconciling" for s in states):
        return ExecutionState.RECONCILING

    if any(s == "publishing" for s in states):
        return ExecutionState.PUBLISHING

    published = [s for s in states if s == "published"]
    failed = [s for s in states if s == "failed"]

    if len(published) == len(states) and all(
        d.provider_receipt_id for d in entry.destinations if d.state == "published"
    ):
        return ExecutionState.PUBLISHED

    if len(failed) == len(states):
        return ExecutionState.FAILED

    if published and failed:
        return ExecutionState.PARTIAL

    return ExecutionState.PENDING


def update_execution_state(entry: CalendarEntryStatus) -> CalendarEntryStatus:
    """Recompute and set execution state from evidence."""
    new_state = derive_execution_state(entry)

    if new_state != entry.execution_state:
        entry.transitions.append({
            "type": "execution",
            "from": entry.execution_state.value,
            "to": new_state.value,
            "actor": "system",
            "reason": "Derived from destination results",
            "at": datetime.now(UTC).isoformat(),
        })
        entry.execution_state = new_state

        if new_state == ExecutionState.PUBLISHED:
            entry.published_at = datetime.now(UTC).isoformat()

    entry.updated_at = datetime.now(UTC).isoformat()
    return entry


# =============================================================================
# Destination Updates (with evidence)
# =============================================================================


def record_publish_attempt(
    entry: CalendarEntryStatus,
    destination_id: str,
) -> CalendarEntryStatus:
    """Record that a publish attempt has started for a destination."""
    for dest in entry.destinations:
        if dest.destination_id == destination_id:
            dest.state = "publishing"
            dest.attempt_count += 1
            dest.last_attempt_at = datetime.now(UTC).isoformat()
            break

    update_execution_state(entry)
    return entry


def record_publish_success(
    entry: CalendarEntryStatus,
    destination_id: str,
    *,
    provider_receipt_id: str,
    provider_url: str = "",
) -> CalendarEntryStatus:
    """Record successful publication with provider receipt.

    Receipt ID is REQUIRED — cannot mark published without it.
    """
    if not provider_receipt_id:
        raise InvalidTransitionError(
            "Cannot mark published without provider_receipt_id",
            code="RECEIPT_REQUIRED",
        )

    for dest in entry.destinations:
        if dest.destination_id == destination_id:
            dest.state = "published"
            dest.provider_receipt_id = provider_receipt_id
            dest.provider_url = provider_url
            dest.published_at = datetime.now(UTC).isoformat()
            break

    update_execution_state(entry)
    return entry


def record_publish_failure(
    entry: CalendarEntryStatus,
    destination_id: str,
    *,
    error: str,
) -> CalendarEntryStatus:
    """Record a failed publish attempt."""
    for dest in entry.destinations:
        if dest.destination_id == destination_id:
            dest.state = "failed"
            dest.error_message = error
            break

    update_execution_state(entry)
    return entry


# =============================================================================
# Client Forgery Prevention
# =============================================================================


def validate_client_update(fields: dict[str, Any]) -> None:
    """Validate that a client update does not attempt to set protected fields.

    Raises ProtectedFieldError if any protected field is present.
    """
    for field_name in PROTECTED_FIELDS:
        if field_name in fields and fields[field_name] is not None:
            raise ProtectedFieldError(field_name)


# =============================================================================
# Store
# =============================================================================

_store: dict[str, CalendarEntryStatus] = {}


def clear_store() -> None:
    _store.clear()


def save_entry(entry: CalendarEntryStatus) -> CalendarEntryStatus:
    _store[entry.entry_id] = entry
    return entry


def get_entry(entry_id: str, *, org_id: str) -> CalendarEntryStatus | None:
    entry = _store.get(entry_id)
    if entry and entry.org_id != org_id:
        return None  # Cross-tenant denied
    return entry
