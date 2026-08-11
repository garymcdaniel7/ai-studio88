"""Durable Feedback Tests (Story 107).

Proves: authenticated submission, idempotency, cross-tenant denial,
lineage linkage, retry behavior, rating validation, and update.

Run with:
    pytest tests/unit/test_durable_feedback.py -v
"""
from __future__ import annotations

import pytest

from backend.durable_feedback import (
    FeedbackAuthError,
    FeedbackCrossTenantError,
    FeedbackError,
    FeedbackRecord,
    FeedbackResponse,
    FeedbackStatus,
    RatingType,
    clear_store,
    get_feedback,
    get_feedback_for_asset,
    get_feedback_for_user,
    submit_feedback,
    update_rating,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_store()
    yield
    clear_store()


def _submit(**overrides) -> FeedbackResponse:
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "asset_id": "asset-abc",
        "job_id": "job-xyz",
        "context_package_id": "ctx-pkg-1",
        "rating_type": RatingType.STARS,
        "rating_value": 4,
        "reason": "Good quality",
        "asset_org_id": "org-123",
    }
    defaults.update(overrides)
    return submit_feedback(**defaults)


# =============================================================================
# Authenticated Submission
# =============================================================================


class TestAuthentication:

    @pytest.mark.unit
    def test_valid_submission_succeeds(self):
        """Authenticated submission with all fields succeeds."""
        resp = _submit()
        assert resp.success is True
        assert resp.status == FeedbackStatus.PERSISTED
        assert resp.feedback_id != ""

    @pytest.mark.unit
    def test_missing_org_id_raises(self):
        """Missing org_id raises auth error."""
        with pytest.raises(FeedbackAuthError):
            _submit(org_id="")

    @pytest.mark.unit
    def test_missing_user_id_raises(self):
        """Missing user_id raises auth error."""
        with pytest.raises(FeedbackAuthError):
            _submit(user_id="")

    @pytest.mark.unit
    def test_missing_asset_id_raises(self):
        """Missing asset_id raises error."""
        with pytest.raises(FeedbackError) as exc_info:
            _submit(asset_id="")
        assert exc_info.value.code == "ASSET_REQUIRED"


# =============================================================================
# Idempotency
# =============================================================================


class TestIdempotency:

    @pytest.mark.unit
    def test_duplicate_key_returns_existing(self):
        """Same idempotency_key returns existing record without re-persisting."""
        resp1 = _submit(idempotency_key="idem-001")
        resp2 = _submit(idempotency_key="idem-001", rating_value=1)  # Different value
        assert resp1.feedback_id == resp2.feedback_id
        assert resp2.is_duplicate is True

    @pytest.mark.unit
    def test_different_keys_create_separate(self):
        """Different idempotency keys create separate records."""
        resp1 = _submit(idempotency_key="key-A")
        resp2 = _submit(idempotency_key="key-B")
        assert resp1.feedback_id != resp2.feedback_id
        assert resp1.is_duplicate is False
        assert resp2.is_duplicate is False

    @pytest.mark.unit
    def test_no_key_always_creates_new(self):
        """Submissions without idempotency key always create new records."""
        resp1 = _submit(idempotency_key="")
        resp2 = _submit(idempotency_key="")
        assert resp1.feedback_id != resp2.feedback_id

    @pytest.mark.unit
    def test_duplicate_preserves_original_rating(self):
        """Duplicate submission doesn't overwrite original rating."""
        _submit(idempotency_key="idem-x", rating_value=5)
        _submit(idempotency_key="idem-x", rating_value=1)  # Try to change
        record = get_feedback(_submit(idempotency_key="idem-x").feedback_id)
        assert record.rating_value == 5  # Original preserved


# =============================================================================
# Cross-Tenant Denial
# =============================================================================


class TestCrossTenant:

    @pytest.mark.unit
    def test_cross_tenant_asset_denied(self):
        """Cannot rate an asset from another workspace."""
        with pytest.raises(FeedbackCrossTenantError):
            _submit(org_id="org-123", asset_org_id="org-evil")

    @pytest.mark.unit
    def test_same_tenant_allowed(self):
        """Same org for user and asset passes."""
        resp = _submit(org_id="org-123", asset_org_id="org-123")
        assert resp.success is True

    @pytest.mark.unit
    def test_empty_asset_org_skips_check(self):
        """Empty asset_org_id skips cross-tenant check (backwards compat)."""
        resp = _submit(org_id="org-123", asset_org_id="")
        assert resp.success is True


# =============================================================================
# Lineage Linkage
# =============================================================================


class TestLineage:

    @pytest.mark.unit
    def test_record_links_asset(self):
        """Feedback record links to asset_id."""
        resp = _submit(asset_id="asset-out-1")
        record = get_feedback(resp.feedback_id)
        assert record.asset_id == "asset-out-1"

    @pytest.mark.unit
    def test_record_links_job(self):
        """Feedback record links to job_id."""
        resp = _submit(job_id="gen-job-42")
        record = get_feedback(resp.feedback_id)
        assert record.job_id == "gen-job-42"

    @pytest.mark.unit
    def test_record_links_context_package(self):
        """Feedback record links to context_package_id."""
        resp = _submit(context_package_id="ctx-pkg-99")
        record = get_feedback(resp.feedback_id)
        assert record.context_package_id == "ctx-pkg-99"

    @pytest.mark.unit
    def test_record_links_talent(self):
        """Feedback record links to talent_id."""
        resp = _submit(talent_id="talent-melissa")
        record = get_feedback(resp.feedback_id)
        assert record.talent_id == "talent-melissa"


# =============================================================================
# Rating Validation
# =============================================================================


class TestRatingValidation:

    @pytest.mark.unit
    def test_stars_valid_range(self):
        """Stars 1-5 accepted."""
        for v in range(1, 6):
            resp = _submit(rating_value=v, idempotency_key=f"star-{v}")
            assert resp.success is True

    @pytest.mark.unit
    def test_stars_zero_rejected(self):
        """Stars 0 rejected."""
        with pytest.raises(FeedbackError) as exc_info:
            _submit(rating_value=0)
        assert exc_info.value.code == "INVALID_RATING"

    @pytest.mark.unit
    def test_stars_six_rejected(self):
        """Stars 6 rejected."""
        with pytest.raises(FeedbackError):
            _submit(rating_value=6)

    @pytest.mark.unit
    def test_thumbs_up_accepted(self):
        """Thumbs up (2) accepted."""
        resp = _submit(rating_type=RatingType.THUMBS, rating_value=2)
        assert resp.success is True

    @pytest.mark.unit
    def test_thumbs_down_accepted(self):
        """Thumbs down (1) accepted."""
        resp = _submit(rating_type=RatingType.THUMBS, rating_value=1)
        assert resp.success is True

    @pytest.mark.unit
    def test_thumbs_invalid_rejected(self):
        """Thumbs value 3 rejected."""
        with pytest.raises(FeedbackError):
            _submit(rating_type=RatingType.THUMBS, rating_value=3)


# =============================================================================
# Update Rating
# =============================================================================


class TestUpdateRating:

    @pytest.mark.unit
    def test_update_supersedes_original(self):
        """Updating rating supersedes the original."""
        resp = _submit(idempotency_key="orig")
        updated = update_rating(
            resp.feedback_id, org_id="org-123", user_id="user-456",
            new_rating_value=2, new_reason="Changed my mind",
        )
        assert updated.rating_value == 2
        # Original is superseded
        original = get_feedback(resp.feedback_id)
        assert original.status == FeedbackStatus.SUPERSEDED

    @pytest.mark.unit
    def test_update_cross_tenant_denied(self):
        """Cannot update feedback from different org."""
        resp = _submit()
        with pytest.raises(FeedbackCrossTenantError):
            update_rating(
                resp.feedback_id, org_id="org-evil", user_id="user-456",
                new_rating_value=1,
            )

    @pytest.mark.unit
    def test_update_wrong_user_denied(self):
        """Only original author can update."""
        resp = _submit()
        with pytest.raises(FeedbackError) as exc_info:
            update_rating(
                resp.feedback_id, org_id="org-123", user_id="user-other",
                new_rating_value=1,
            )
        assert exc_info.value.code == "UNAUTHORIZED"


# =============================================================================
# Queries
# =============================================================================


class TestQueries:

    @pytest.mark.unit
    def test_get_feedback_for_asset(self):
        """Query feedback by asset (tenant-scoped)."""
        _submit(asset_id="asset-A", idempotency_key="a1")
        _submit(asset_id="asset-A", idempotency_key="a2", user_id="user-2")
        _submit(asset_id="asset-B", idempotency_key="b1")

        results = get_feedback_for_asset("asset-A", "org-123")
        assert len(results) == 2

    @pytest.mark.unit
    def test_get_feedback_for_user(self):
        """Query feedback by user (tenant-scoped)."""
        _submit(idempotency_key="u1")
        _submit(idempotency_key="u2")
        results = get_feedback_for_user("user-456", "org-123")
        assert len(results) == 2

    @pytest.mark.unit
    def test_superseded_excluded_from_queries(self):
        """Superseded feedback excluded from asset queries."""
        resp = _submit(idempotency_key="orig")
        update_rating(
            resp.feedback_id, org_id="org-123", user_id="user-456",
            new_rating_value=2,
        )
        results = get_feedback_for_asset("asset-abc", "org-123")
        # Only the updated record, not the superseded original
        assert len(results) == 1
        assert results[0].rating_value == 2

    @pytest.mark.unit
    def test_response_serializable(self):
        """FeedbackResponse.to_dict() is JSON-serializable."""
        import json
        resp = _submit()
        json.dumps(resp.to_dict())

    @pytest.mark.unit
    def test_record_serializable(self):
        """FeedbackRecord.to_dict() is JSON-serializable."""
        import json
        resp = _submit()
        record = get_feedback(resp.feedback_id)
        json.dumps(record.to_dict())
