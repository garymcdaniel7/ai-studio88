"""Publishing Preflight Tests (Story 123).

Proves: pass/block/review states, stale invalidation, synthetic media,
outage handling (unavailable), approval binding, and disclosure enforcement.

Run with:
    pytest tests/unit/test_publishing_preflight.py -v
"""
from __future__ import annotations

import pytest

from backend.publishing_preflight import (
    ApprovalBindingError,
    CheckCategory,
    PreflightState,
    bind_approval,
    check_invalidation,
    compute_content_hash,
    evaluate_preflight,
)


# =============================================================================
# Helpers
# =============================================================================


def _eval(**overrides):
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "content_item_id": "item-1",
        "content_version": 1,
        "platform": "instagram",
        "account_id": "acct-ig-1",
        "account_connected": True,
        "lineage_complete": True,
    }
    defaults.update(overrides)
    return evaluate_preflight(**defaults)


# =============================================================================
# Pass State
# =============================================================================


class TestPassState:

    @pytest.mark.unit
    def test_basic_content_passes(self):
        """Non-sponsored, non-synthetic content with connected account passes."""
        result = _eval()
        assert result.overall_state == PreflightState.PASS
        assert result.blocked_count == 0

    @pytest.mark.unit
    def test_sponsored_with_name_passes(self):
        """Sponsored content with sponsor name passes."""
        result = _eval(is_sponsored=True, sponsor_name="Nike")
        assert result.overall_state == PreflightState.PASS

    @pytest.mark.unit
    def test_synthetic_with_disclosure_passes(self):
        """Synthetic content (disclosure auto-applied) passes."""
        result = _eval(is_synthetic=True, consent_valid=True)
        assert result.overall_state == PreflightState.PASS
        assert result.disclosures.is_synthetic is True
        assert result.disclosures.synthetic_disclosure_text != ""

    @pytest.mark.unit
    def test_content_hash_computed(self):
        """Content hash is computed and stored."""
        result = _eval()
        assert result.content_hash != ""
        assert len(result.content_hash) == 24


# =============================================================================
# Block State
# =============================================================================


class TestBlockState:

    @pytest.mark.unit
    def test_disconnected_account_blocks(self):
        """Disconnected account blocks publishing."""
        result = _eval(account_connected=False)
        assert result.overall_state == PreflightState.BLOCK
        assert result.blocked_count >= 1

    @pytest.mark.unit
    def test_sponsored_without_name_blocks(self):
        """Sponsored content without sponsor name blocks."""
        result = _eval(is_sponsored=True, sponsor_name="")
        assert result.overall_state == PreflightState.BLOCK

    @pytest.mark.unit
    def test_revoked_consent_blocks(self):
        """Revoked consent on synthetic content blocks."""
        result = _eval(is_synthetic=True, consent_valid=False)
        assert result.overall_state == PreflightState.BLOCK

    @pytest.mark.unit
    def test_block_message_informative(self):
        """Block check has informative message."""
        result = _eval(account_connected=False)
        blocked = [c for c in result.checks if c.state == PreflightState.BLOCK]
        assert len(blocked) >= 1
        assert "not connected" in blocked[0].message.lower()


# =============================================================================
# Unavailable (Outage / Fail-Safe)
# =============================================================================


class TestUnavailable:

    @pytest.mark.unit
    def test_unknown_account_status_unavailable(self):
        """Unknown account connection → UNAVAILABLE (fail-safe)."""
        result = _eval(account_connected=None)
        assert result.overall_state == PreflightState.UNAVAILABLE
        assert result.unavailable_count >= 1

    @pytest.mark.unit
    def test_unknown_consent_unavailable(self):
        """Unknown consent on AI voice content → UNAVAILABLE."""
        result = _eval(is_ai_voice=True, consent_valid=None)
        assert result.overall_state == PreflightState.UNAVAILABLE

    @pytest.mark.unit
    def test_unavailable_cannot_be_approved(self):
        """UNAVAILABLE result cannot be approved."""
        result = _eval(account_connected=None)
        with pytest.raises(ApprovalBindingError) as exc_info:
            bind_approval(result, approval_id="app-1", approved_by="admin")
        assert exc_info.value.code == "UNAVAILABLE"


# =============================================================================
# Warning State
# =============================================================================


class TestWarningState:

    @pytest.mark.unit
    def test_missing_feature_produces_warning(self):
        """Account missing feature produces WARNING (non-blocking)."""
        result = _eval(account_has_feature=False)
        assert result.overall_state == PreflightState.WARNING
        assert result.warning_count >= 1

    @pytest.mark.unit
    def test_incomplete_lineage_warning(self):
        """Incomplete asset lineage produces warning."""
        result = _eval(lineage_complete=False)
        assert result.overall_state == PreflightState.WARNING

    @pytest.mark.unit
    def test_warning_can_be_approved(self):
        """WARNING result can still be approved."""
        result = _eval(lineage_complete=False)
        assert result.overall_state == PreflightState.WARNING
        bound = bind_approval(result, approval_id="app-1", approved_by="admin")
        assert bound.approval_id == "app-1"


# =============================================================================
# Synthetic Media
# =============================================================================


class TestSyntheticMedia:

    @pytest.mark.unit
    def test_synthetic_disclosure_applied(self):
        """Synthetic content has disclosure text in package."""
        result = _eval(is_synthetic=True, consent_valid=True)
        assert result.disclosures.is_synthetic is True
        assert "AI-generated" in result.disclosures.synthetic_disclosure_text

    @pytest.mark.unit
    def test_ai_voice_disclosure_applied(self):
        """AI voice content has voice disclosure check."""
        result = _eval(is_ai_voice=True, consent_valid=True)
        assert result.disclosures.is_ai_voice is True
        voice_checks = [c for c in result.checks if c.name == "ai_voice_disclosure"]
        assert len(voice_checks) == 1

    @pytest.mark.unit
    def test_synthetic_requires_consent(self):
        """Synthetic media triggers consent check."""
        result = _eval(is_synthetic=True, consent_valid=True)
        consent_checks = [c for c in result.checks if c.category == CheckCategory.CONSENT]
        assert len(consent_checks) >= 1


# =============================================================================
# Stale Invalidation
# =============================================================================


class TestInvalidation:

    @pytest.mark.unit
    def test_same_content_not_stale(self):
        """Same version and hash → not stale."""
        result = _eval()
        is_stale = check_invalidation(
            result,
            current_content_version=1,
            current_content_hash=result.content_hash,
        )
        assert is_stale is False
        assert result.is_stale is False

    @pytest.mark.unit
    def test_version_change_invalidates(self):
        """Content version change → stale."""
        result = _eval()
        is_stale = check_invalidation(
            result,
            current_content_version=2,
            current_content_hash=result.content_hash,
        )
        assert is_stale is True
        assert result.is_stale is True

    @pytest.mark.unit
    def test_hash_change_invalidates(self):
        """Content hash change → stale."""
        result = _eval()
        is_stale = check_invalidation(
            result,
            current_content_version=1,
            current_content_hash="different_hash_abc",
        )
        assert is_stale is True

    @pytest.mark.unit
    def test_stale_result_cannot_be_approved(self):
        """Stale result cannot be approved."""
        result = _eval()
        result.is_stale = True
        with pytest.raises(ApprovalBindingError) as exc_info:
            bind_approval(result, approval_id="app-1", approved_by="admin")
        assert exc_info.value.code == "STALE"

    @pytest.mark.unit
    def test_hash_deterministic(self):
        """Same inputs produce same hash."""
        h1 = compute_content_hash(
            content_item_id="item-1", content_version=1,
            asset_checksums=["a", "b"], platform="ig",
            account_id="acct-1", is_sponsored=False, is_synthetic=True,
        )
        h2 = compute_content_hash(
            content_item_id="item-1", content_version=1,
            asset_checksums=["a", "b"], platform="ig",
            account_id="acct-1", is_sponsored=False, is_synthetic=True,
        )
        assert h1 == h2

    @pytest.mark.unit
    def test_hash_changes_with_sponsorship(self):
        """Changing sponsorship flag changes hash."""
        h1 = compute_content_hash(
            content_item_id="item-1", content_version=1,
            asset_checksums=[], platform="ig",
            account_id="acct-1", is_sponsored=False, is_synthetic=False,
        )
        h2 = compute_content_hash(
            content_item_id="item-1", content_version=1,
            asset_checksums=[], platform="ig",
            account_id="acct-1", is_sponsored=True, is_synthetic=False,
        )
        assert h1 != h2


# =============================================================================
# Approval Binding
# =============================================================================


class TestApprovalBinding:

    @pytest.mark.unit
    def test_pass_can_be_approved(self):
        """PASS result can be approved."""
        result = _eval()
        bound = bind_approval(result, approval_id="app-123", approved_by="admin-1")
        assert bound.approval_id == "app-123"
        assert bound.approved_by == "admin-1"
        assert bound.approved_at is not None

    @pytest.mark.unit
    def test_block_cannot_be_approved(self):
        """BLOCK result cannot be approved."""
        result = _eval(account_connected=False)
        with pytest.raises(ApprovalBindingError) as exc_info:
            bind_approval(result, approval_id="app-1", approved_by="admin")
        assert exc_info.value.code == "BLOCKED"

    @pytest.mark.unit
    def test_result_serializable(self):
        """PreflightResult.to_dict() is JSON-serializable."""
        import json
        result = _eval(is_sponsored=True, sponsor_name="Brand X", is_synthetic=True, consent_valid=True)
        json.dumps(result.to_dict())
