"""Calendar Status Derivation Tests (Story 125).

Proves: valid/invalid transitions, partial success, receipt requirement,
caller forgery blocked, audit trail, and state derivation.

Run with:
    pytest tests/unit/test_calendar_status.py -v
"""
from __future__ import annotations

import pytest

from backend.calendar_status import (
    CalendarEntryStatus,
    DestinationResult,
    EditorialState,
    ExecutionState,
    InvalidTransitionError,
    ProtectedFieldError,
    clear_store,
    derive_execution_state,
    get_entry,
    record_publish_attempt,
    record_publish_failure,
    record_publish_success,
    save_entry,
    transition_editorial,
    update_execution_state,
    validate_client_update,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_store()
    yield
    clear_store()


def _entry(destinations: int = 2, **overrides) -> CalendarEntryStatus:
    entry = CalendarEntryStatus(
        org_id="org-123",
        content_item_id="content-1",
        **overrides,
    )
    for i in range(destinations):
        entry.destinations.append(DestinationResult(
            destination_id=f"dest-{i}",
            platform=["instagram", "tiktok", "youtube"][i % 3],
        ))
    return entry


# =============================================================================
# Editorial Transitions
# =============================================================================


class TestEditorialTransitions:

    @pytest.mark.unit
    def test_draft_to_ready(self):
        """DRAFT → READY is valid."""
        entry = _entry()
        transition_editorial(entry, EditorialState.READY, actor="user-1")
        assert entry.editorial_state == EditorialState.READY

    @pytest.mark.unit
    def test_ready_to_approved(self):
        """READY → APPROVED is valid."""
        entry = _entry(editorial_state=EditorialState.READY)
        transition_editorial(entry, EditorialState.APPROVED, actor="system")
        assert entry.editorial_state == EditorialState.APPROVED

    @pytest.mark.unit
    def test_approved_to_scheduled(self):
        """APPROVED → SCHEDULED is valid."""
        entry = _entry(editorial_state=EditorialState.APPROVED)
        transition_editorial(entry, EditorialState.SCHEDULED, actor="user-1")
        assert entry.editorial_state == EditorialState.SCHEDULED

    @pytest.mark.unit
    def test_scheduled_to_cancelled(self):
        """SCHEDULED → CANCELLED is valid."""
        entry = _entry(editorial_state=EditorialState.SCHEDULED)
        transition_editorial(entry, EditorialState.CANCELLED, actor="user-1")
        assert entry.editorial_state == EditorialState.CANCELLED

    @pytest.mark.unit
    def test_draft_to_approved_invalid(self):
        """DRAFT → APPROVED directly is invalid (must go through READY)."""
        entry = _entry()
        with pytest.raises(InvalidTransitionError):
            transition_editorial(entry, EditorialState.APPROVED, actor="user-1")

    @pytest.mark.unit
    def test_cancelled_to_ready_invalid(self):
        """CANCELLED → READY is invalid."""
        entry = _entry(editorial_state=EditorialState.CANCELLED)
        with pytest.raises(InvalidTransitionError):
            transition_editorial(entry, EditorialState.READY, actor="user-1")

    @pytest.mark.unit
    def test_ready_to_draft_sendback(self):
        """READY → DRAFT (send back for edits) is valid."""
        entry = _entry(editorial_state=EditorialState.READY)
        transition_editorial(entry, EditorialState.DRAFT, actor="reviewer-1")
        assert entry.editorial_state == EditorialState.DRAFT


# =============================================================================
# Execution State Derivation
# =============================================================================


class TestExecutionDerivation:

    @pytest.mark.unit
    def test_no_destinations_is_none(self):
        """No destinations → NONE."""
        entry = _entry(destinations=0)
        assert derive_execution_state(entry) == ExecutionState.NONE

    @pytest.mark.unit
    def test_all_pending(self):
        """All destinations pending → PENDING."""
        entry = _entry(destinations=2)
        assert derive_execution_state(entry) == ExecutionState.PENDING

    @pytest.mark.unit
    def test_any_publishing(self):
        """Any destination publishing → PUBLISHING."""
        entry = _entry(destinations=2)
        entry.destinations[0].state = "publishing"
        assert derive_execution_state(entry) == ExecutionState.PUBLISHING

    @pytest.mark.unit
    def test_all_published_with_receipts(self):
        """All published with receipts → PUBLISHED."""
        entry = _entry(destinations=2)
        for d in entry.destinations:
            d.state = "published"
            d.provider_receipt_id = f"receipt-{d.destination_id}"
        assert derive_execution_state(entry) == ExecutionState.PUBLISHED

    @pytest.mark.unit
    def test_all_failed(self):
        """All destinations failed → FAILED."""
        entry = _entry(destinations=2)
        for d in entry.destinations:
            d.state = "failed"
        assert derive_execution_state(entry) == ExecutionState.FAILED

    @pytest.mark.unit
    def test_published_without_receipt_not_published(self):
        """Published state without receipt_id doesn't count as PUBLISHED."""
        entry = _entry(destinations=1)
        entry.destinations[0].state = "published"
        entry.destinations[0].provider_receipt_id = ""  # No receipt
        # Falls through to PENDING since it doesn't match strict PUBLISHED rules
        state = derive_execution_state(entry)
        assert state != ExecutionState.PUBLISHED


# =============================================================================
# Partial Success
# =============================================================================


class TestPartialSuccess:

    @pytest.mark.unit
    def test_some_published_some_failed(self):
        """Mixed results → PARTIAL."""
        entry = _entry(destinations=3)
        entry.destinations[0].state = "published"
        entry.destinations[0].provider_receipt_id = "rcpt-1"
        entry.destinations[1].state = "failed"
        entry.destinations[2].state = "failed"
        assert derive_execution_state(entry) == ExecutionState.PARTIAL

    @pytest.mark.unit
    def test_partial_preserves_per_destination_detail(self):
        """Partial state preserves individual destination results."""
        entry = _entry(destinations=2)
        record_publish_attempt(entry, "dest-0")
        record_publish_success(entry, "dest-0", provider_receipt_id="rcpt-0")
        record_publish_attempt(entry, "dest-1")
        record_publish_failure(entry, "dest-1", error="Rate limited")

        assert entry.execution_state == ExecutionState.PARTIAL
        assert entry.destinations[0].state == "published"
        assert entry.destinations[1].state == "failed"
        assert entry.destinations[1].error_message == "Rate limited"


# =============================================================================
# Receipt Requirement
# =============================================================================


class TestReceiptRequirement:

    @pytest.mark.unit
    def test_success_requires_receipt(self):
        """Cannot mark published without provider_receipt_id."""
        entry = _entry(destinations=1)
        record_publish_attempt(entry, "dest-0")
        with pytest.raises(InvalidTransitionError) as exc_info:
            record_publish_success(entry, "dest-0", provider_receipt_id="")
        assert exc_info.value.code == "RECEIPT_REQUIRED"

    @pytest.mark.unit
    def test_success_with_receipt_works(self):
        """Publication with receipt succeeds."""
        entry = _entry(destinations=1)
        record_publish_attempt(entry, "dest-0")
        record_publish_success(entry, "dest-0", provider_receipt_id="ig-12345", provider_url="https://instagram.com/p/abc")
        assert entry.destinations[0].provider_receipt_id == "ig-12345"
        assert entry.destinations[0].provider_url == "https://instagram.com/p/abc"
        assert entry.execution_state == ExecutionState.PUBLISHED

    @pytest.mark.unit
    def test_published_sets_timestamp(self):
        """All-published sets published_at on entry."""
        entry = _entry(destinations=1)
        record_publish_attempt(entry, "dest-0")
        record_publish_success(entry, "dest-0", provider_receipt_id="rcpt")
        assert entry.published_at is not None


# =============================================================================
# Caller Forgery Blocked
# =============================================================================


class TestCallerForgery:

    @pytest.mark.unit
    def test_client_cannot_set_execution_state(self):
        """Client cannot directly set execution_state."""
        with pytest.raises(ProtectedFieldError) as exc_info:
            validate_client_update({"execution_state": "published"})
        assert exc_info.value.field_name == "execution_state"

    @pytest.mark.unit
    def test_client_cannot_set_published_at(self):
        """Client cannot directly set published_at."""
        with pytest.raises(ProtectedFieldError):
            validate_client_update({"published_at": "2025-01-01T00:00:00Z"})

    @pytest.mark.unit
    def test_client_cannot_set_provider_receipts(self):
        """Client cannot set provider_receipts."""
        with pytest.raises(ProtectedFieldError):
            validate_client_update({"provider_receipts": [{"id": "fake"}]})

    @pytest.mark.unit
    def test_non_protected_fields_allowed(self):
        """Non-protected fields pass validation."""
        validate_client_update({"editorial_state": "ready", "schedule_time": "2025-12-01"})

    @pytest.mark.unit
    def test_none_values_not_flagged(self):
        """None values in protected fields not flagged (field not actually set)."""
        validate_client_update({"execution_state": None, "published_at": None})


# =============================================================================
# Audit Trail
# =============================================================================


class TestAuditTrail:

    @pytest.mark.unit
    def test_editorial_transition_recorded(self):
        """Editorial transitions create audit entries."""
        entry = _entry()
        transition_editorial(entry, EditorialState.READY, actor="user-1", reason="Content complete")
        assert len(entry.transitions) == 1
        assert entry.transitions[0]["type"] == "editorial"
        assert entry.transitions[0]["actor"] == "user-1"
        assert entry.transitions[0]["reason"] == "Content complete"

    @pytest.mark.unit
    def test_execution_transition_recorded(self):
        """Execution state changes create audit entries."""
        entry = _entry(destinations=1)
        record_publish_attempt(entry, "dest-0")
        record_publish_success(entry, "dest-0", provider_receipt_id="rcpt")
        exec_transitions = [t for t in entry.transitions if t["type"] == "execution"]
        assert len(exec_transitions) >= 1
        assert exec_transitions[-1]["actor"] == "system"

    @pytest.mark.unit
    def test_multiple_transitions_accumulated(self):
        """Full workflow accumulates all transitions."""
        entry = _entry(destinations=1)
        transition_editorial(entry, EditorialState.READY, actor="u-1")
        transition_editorial(entry, EditorialState.APPROVED, actor="system")
        transition_editorial(entry, EditorialState.SCHEDULED, actor="u-1")
        record_publish_attempt(entry, "dest-0")
        record_publish_success(entry, "dest-0", provider_receipt_id="rcpt")

        assert len(entry.transitions) >= 4

    @pytest.mark.unit
    def test_entry_serializable(self):
        """CalendarEntryStatus.to_dict() is JSON-serializable."""
        import json
        entry = _entry(destinations=2)
        transition_editorial(entry, EditorialState.READY, actor="u-1")
        json.dumps(entry.to_dict())


# =============================================================================
# Cross-Tenant
# =============================================================================


class TestCrossTenant:

    @pytest.mark.unit
    def test_get_entry_denies_cross_tenant(self):
        """Cannot retrieve entry from different org."""
        entry = _entry()
        save_entry(entry)
        result = get_entry(entry.entry_id, org_id="org-evil")
        assert result is None

    @pytest.mark.unit
    def test_get_entry_same_org_works(self):
        """Can retrieve entry from same org."""
        entry = _entry()
        save_entry(entry)
        result = get_entry(entry.entry_id, org_id="org-123")
        assert result is not None
        assert result.entry_id == entry.entry_id
