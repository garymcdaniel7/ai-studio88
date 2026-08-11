"""Post-Publication Actions Tests (Story 129).

Proves: provider confirmation required, unsupported actions labeled,
partial success, already-missing handling, credential loss, tombstones,
and reconciliation.

Run with:
    pytest tests/unit/test_post_publication.py -v
"""
from __future__ import annotations

import pytest

from backend.post_publication import (
    ActionState,
    ConfirmationRequiredError,
    CredentialRequiredError,
    PostPubAction,
    PostPubError,
    PostPublicationAction,
    clear_store,
    confirm_action,
    fail_action,
    get_action,
    get_actions_for_content,
    get_tombstones,
    handle_already_missing,
    is_action_supported,
    mark_reconciling,
    request_action,
    start_execution,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_store()
    yield
    clear_store()


def _request(**overrides) -> PostPublicationAction:
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "publish_job_id": "pub-job-1",
        "provider_receipt_id": "ig-post-12345",
        "platform": "instagram",
        "destination_id": "dest-ig-1",
        "action_type": PostPubAction.DELETE,
        "reason": "Content no longer relevant",
    }
    defaults.update(overrides)
    return request_action(**defaults)


# =============================================================================
# Provider Confirmation Required
# =============================================================================


class TestConfirmationRequired:

    @pytest.mark.unit
    def test_confirm_requires_id(self):
        """Cannot confirm without provider_confirmation_id."""
        action = _request()
        start_execution(action.action_id)
        with pytest.raises(ConfirmationRequiredError):
            confirm_action(action.action_id, provider_confirmation_id="")

    @pytest.mark.unit
    def test_confirm_with_id_succeeds(self):
        """Confirmation with provider ID succeeds."""
        action = _request()
        start_execution(action.action_id)
        result = confirm_action(
            action.action_id,
            provider_confirmation_id="ig-del-confirm-789",
        )
        # DELETE → TOMBSTONE (not just CONFIRMED)
        assert result.state == ActionState.TOMBSTONE
        assert result.provider_confirmation_id == "ig-del-confirm-789"
        assert result.confirmed_at is not None

    @pytest.mark.unit
    def test_confirm_idempotent(self):
        """Re-confirming already-confirmed action is idempotent."""
        action = _request(action_type=PostPubAction.UNPUBLISH, platform="youtube")
        start_execution(action.action_id)
        confirm_action(action.action_id, provider_confirmation_id="yt-conf-1")
        # Second confirm
        result = confirm_action(action.action_id, provider_confirmation_id="yt-conf-2")
        assert result.provider_confirmation_id == "yt-conf-1"  # Original preserved

    @pytest.mark.unit
    def test_local_state_never_claims_without_confirmation(self):
        """Executing state doesn't imply confirmed — stays EXECUTING."""
        action = _request()
        start_execution(action.action_id)
        assert action.state == ActionState.EXECUTING
        assert action.state != ActionState.CONFIRMED


# =============================================================================
# Unsupported Actions
# =============================================================================


class TestUnsupportedActions:

    @pytest.mark.unit
    def test_unsupported_action_labeled(self):
        """Unsupported action immediately marked UNSUPPORTED."""
        action = _request(platform="instagram", action_type=PostPubAction.CORRECT)
        assert action.state == ActionState.UNSUPPORTED
        assert "does not support" in action.error_message

    @pytest.mark.unit
    def test_supported_action_stays_requested(self):
        """Supported action stays REQUESTED (ready for execution)."""
        action = _request(platform="instagram", action_type=PostPubAction.DELETE)
        assert action.state == ActionState.REQUESTED

    @pytest.mark.unit
    def test_capability_check_function(self):
        """is_action_supported returns correct results."""
        assert is_action_supported("instagram", PostPubAction.DELETE) is True
        assert is_action_supported("instagram", PostPubAction.CORRECT) is False
        assert is_action_supported("youtube", PostPubAction.CORRECT) is True
        assert is_action_supported("youtube", PostPubAction.UNPUBLISH) is True

    @pytest.mark.unit
    def test_unknown_platform_all_unsupported(self):
        """Unknown platform has no supported actions."""
        assert is_action_supported("unknown_platform", PostPubAction.DELETE) is False

    @pytest.mark.unit
    def test_unsupported_action_preserved_in_store(self):
        """Unsupported actions are still stored for audit."""
        action = _request(platform="tiktok", action_type=PostPubAction.ARCHIVE)
        retrieved = get_action(action.action_id)
        assert retrieved is not None
        assert retrieved.state == ActionState.UNSUPPORTED


# =============================================================================
# Already-Missing
# =============================================================================


class TestAlreadyMissing:

    @pytest.mark.unit
    def test_already_missing_marks_confirmed(self):
        """Content already removed → CONFIRMED/TOMBSTONE (desired outcome achieved)."""
        action = _request()
        start_execution(action.action_id)
        handle_already_missing(action.action_id)
        assert action.state == ActionState.TOMBSTONE
        assert action.provider_confirmation_id == "already_missing"

    @pytest.mark.unit
    def test_already_missing_creates_tombstone(self):
        """Already-missing deletion creates proper tombstone data."""
        action = _request()
        start_execution(action.action_id)
        handle_already_missing(action.action_id)
        assert "already missing" in action.tombstone_data.get("reason", "")
        assert action.tombstone_data["original_receipt_id"] == "ig-post-12345"

    @pytest.mark.unit
    def test_already_missing_non_delete_confirms(self):
        """Already-missing for non-delete action (e.g., unpublish) → CONFIRMED."""
        action = _request(action_type=PostPubAction.UNPUBLISH, platform="youtube")
        start_execution(action.action_id)
        handle_already_missing(action.action_id)
        assert action.state == ActionState.CONFIRMED


# =============================================================================
# Credential Loss
# =============================================================================


class TestCredentialLoss:

    @pytest.mark.unit
    def test_invalid_credential_blocks_request(self):
        """Cannot request action with invalid credential."""
        with pytest.raises(CredentialRequiredError) as exc_info:
            _request(credential_valid=False)
        assert exc_info.value.code == "CREDENTIAL_REQUIRED"

    @pytest.mark.unit
    def test_valid_credential_allows_request(self):
        """Valid credential allows action request."""
        action = _request(credential_valid=True)
        assert action.state == ActionState.REQUESTED

    @pytest.mark.unit
    def test_missing_receipt_blocks_request(self):
        """Cannot act without original provider_receipt_id."""
        with pytest.raises(PostPubError) as exc_info:
            _request(provider_receipt_id="")
        assert exc_info.value.code == "NO_RECEIPT"


# =============================================================================
# Tombstones
# =============================================================================


class TestTombstones:

    @pytest.mark.unit
    def test_delete_creates_tombstone(self):
        """Confirmed DELETE creates tombstone with lineage."""
        action = _request(action_type=PostPubAction.DELETE)
        start_execution(action.action_id)
        confirm_action(action.action_id, provider_confirmation_id="del-conf")
        assert action.state == ActionState.TOMBSTONE
        assert action.tombstone_data["original_receipt_id"] == "ig-post-12345"
        assert action.tombstone_data["confirmation_id"] == "del-conf"

    @pytest.mark.unit
    def test_takedown_creates_tombstone(self):
        """Confirmed TAKEDOWN also creates tombstone."""
        action = _request(action_type=PostPubAction.TAKEDOWN, platform="youtube")
        start_execution(action.action_id)
        confirm_action(action.action_id, provider_confirmation_id="td-conf")
        assert action.state == ActionState.TOMBSTONE

    @pytest.mark.unit
    def test_correction_no_tombstone(self):
        """CORRECT action confirmed → CONFIRMED (no tombstone)."""
        action = _request(action_type=PostPubAction.CORRECT, platform="youtube")
        start_execution(action.action_id)
        confirm_action(action.action_id, provider_confirmation_id="edit-conf")
        assert action.state == ActionState.CONFIRMED
        assert action.tombstone_data == {}

    @pytest.mark.unit
    def test_get_tombstones_scoped(self):
        """get_tombstones returns only tombstones for requesting org."""
        a1 = _request(org_id="org-1")
        start_execution(a1.action_id)
        confirm_action(a1.action_id, provider_confirmation_id="c1")

        a2 = _request(org_id="org-2", publish_job_id="pub-2")
        start_execution(a2.action_id)
        confirm_action(a2.action_id, provider_confirmation_id="c2")

        tombstones = get_tombstones("org-1")
        assert len(tombstones) == 1
        assert tombstones[0].org_id == "org-1"


# =============================================================================
# Reconciliation & Failure
# =============================================================================


class TestReconciliation:

    @pytest.mark.unit
    def test_mark_reconciling(self):
        """Unknown outcome → RECONCILING."""
        action = _request()
        start_execution(action.action_id)
        mark_reconciling(action.action_id)
        assert action.state == ActionState.RECONCILING

    @pytest.mark.unit
    def test_failure_recorded(self):
        """Failed action records error."""
        action = _request()
        start_execution(action.action_id)
        fail_action(action.action_id, error="403 Forbidden")
        assert action.state == ActionState.FAILED
        assert action.error_message == "403 Forbidden"

    @pytest.mark.unit
    def test_terminal_not_affected_by_reconcile(self):
        """Terminal actions not affected by reconcile call."""
        action = _request()
        start_execution(action.action_id)
        confirm_action(action.action_id, provider_confirmation_id="conf")
        mark_reconciling(action.action_id)
        assert action.state == ActionState.TOMBSTONE  # Unchanged


# =============================================================================
# Queries & Serialization
# =============================================================================


class TestQueries:

    @pytest.mark.unit
    def test_get_actions_for_content(self):
        """Query actions by publish_job_id (tenant-scoped)."""
        _request(publish_job_id="pub-1", org_id="org-1")
        _request(publish_job_id="pub-1", org_id="org-1", action_type=PostPubAction.UNPUBLISH, platform="youtube")
        _request(publish_job_id="pub-2", org_id="org-1")

        results = get_actions_for_content("pub-1", "org-1")
        assert len(results) == 2

    @pytest.mark.unit
    def test_cross_tenant_excluded(self):
        """Actions from other orgs excluded from queries."""
        _request(publish_job_id="pub-1", org_id="org-1")
        _request(publish_job_id="pub-1", org_id="org-evil")
        results = get_actions_for_content("pub-1", "org-1")
        assert len(results) == 1

    @pytest.mark.unit
    def test_action_serializable(self):
        """PostPublicationAction.to_dict() is JSON-serializable."""
        import json
        action = _request()
        json.dumps(action.to_dict())
