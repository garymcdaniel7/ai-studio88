"""Storyboard shot completion tests — Story 076.

Tests prove:
  - Shot completion requires verified persisted asset
  - Transient state (no verification) is rejected
  - Missing asset_id rejected
  - Missing storage_key rejected
  - storage_verified=False rejected
  - Partial batch: some shots complete, some failed
  - Retry resets shot to pending
  - Cancel clears shot state
  - Storyboard-level status reflects shot states
  - Cross-tenant access denied
  - Idempotent completion (same asset)
  - Already complete with different asset rejected
"""

import pytest

from backend.storyboard_completion import (
    CompletionDenied,
    InvalidShotOperation,
    ShotAlreadyComplete,
    ShotStatus,
    StoryboardNotFound,
    StoryboardStatus,
    _reset_store,
    cancel_shot,
    complete_shot,
    create_storyboard,
    fail_shot,
    get_storyboard,
    get_storyboard_progress,
    retry_shot,
    start_shot_generation,
    verify_shot_completion,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"


def _create_3_shot_storyboard() -> str:
    sb = create_storyboard(ORG, "Test Board", [
        {"prompt": "shot 1"},
        {"prompt": "shot 2"},
        {"prompt": "shot 3"},
    ])
    return sb.storyboard_id


# =============================================================================
# Completion Gate — Asset Verification Required
# =============================================================================


@pytest.mark.unit
class TestCompletionGate:

    def test_complete_with_verified_asset(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        shot = complete_shot(sb_id, 0, ORG, "ast-001", "org/images/001.webp", storage_verified=True)
        assert shot.is_complete is True
        assert shot.verified_asset is not None
        assert shot.verified_asset.storage_verified is True

    def test_missing_asset_id_rejected(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        with pytest.raises(CompletionDenied, match="asset_id"):
            complete_shot(sb_id, 0, ORG, "", "key", storage_verified=True)

    def test_missing_storage_key_rejected(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        with pytest.raises(CompletionDenied, match="storage_key"):
            complete_shot(sb_id, 0, ORG, "ast-001", "", storage_verified=True)

    def test_unverified_storage_rejected(self):
        """storage_verified=False means B2 HEAD check failed — no completion."""
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        with pytest.raises(CompletionDenied, match="storage_verified"):
            complete_shot(sb_id, 0, ORG, "ast-001", "key", storage_verified=False)

    def test_cancelled_shot_cannot_complete(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        cancel_shot(sb_id, 0, ORG)
        with pytest.raises(CompletionDenied, match="cancelled"):
            complete_shot(sb_id, 0, ORG, "ast-001", "key", storage_verified=True)


# =============================================================================
# Transient State Rejection
# =============================================================================


@pytest.mark.unit
class TestTransientStateRejection:

    def test_generating_without_asset_not_complete(self):
        """Job running but no asset yet — shot NOT complete."""
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        diag = verify_shot_completion(sb_id, 0, ORG)
        assert diag["is_complete"] is False
        assert diag["has_asset"] is False

    def test_shot_status_generating_is_not_complete(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        sb = get_storyboard(sb_id, ORG)
        assert sb.shots[0].is_complete is False
        assert sb.shots[0].status == ShotStatus.GENERATING


# =============================================================================
# Partial Batch
# =============================================================================


@pytest.mark.unit
class TestPartialBatch:

    def test_partial_completion(self):
        sb_id = _create_3_shot_storyboard()

        # Shot 0: complete
        start_shot_generation(sb_id, 0, "job-0", ORG)
        complete_shot(sb_id, 0, ORG, "ast-0", "key-0", storage_verified=True)

        # Shot 1: failed
        start_shot_generation(sb_id, 1, "job-1", ORG)
        fail_shot(sb_id, 1, ORG, "provider error")

        # Shot 2: still pending
        sb = get_storyboard(sb_id, ORG)
        assert sb.status == StoryboardStatus.PARTIAL
        assert sb.completion_pct == 33  # 1 of 3

    def test_all_complete(self):
        sb_id = _create_3_shot_storyboard()
        for i in range(3):
            start_shot_generation(sb_id, i, f"job-{i}", ORG)
            complete_shot(sb_id, i, ORG, f"ast-{i}", f"key-{i}", storage_verified=True)

        sb = get_storyboard(sb_id, ORG)
        assert sb.status == StoryboardStatus.COMPLETE
        assert sb.completion_pct == 100

    def test_storyboard_progress(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-0", ORG)
        complete_shot(sb_id, 0, ORG, "ast-0", "key-0", storage_verified=True)

        progress = get_storyboard_progress(sb_id, ORG)
        assert progress["complete_count"] == 1
        assert progress["total_count"] == 3
        assert progress["status"] == "in_progress"


# =============================================================================
# Retry
# =============================================================================


@pytest.mark.unit
class TestRetry:

    def test_retry_resets_shot_to_pending(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        fail_shot(sb_id, 0, ORG, "timeout")

        shot = retry_shot(sb_id, 0, ORG)
        assert shot.status == ShotStatus.PENDING
        assert shot.error is None
        assert shot.verified_asset is None
        assert shot.job_id is None

    def test_retry_non_failed_raises(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        with pytest.raises(InvalidShotOperation):
            retry_shot(sb_id, 0, ORG)

    def test_retry_increments_attempt(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-1", ORG)
        fail_shot(sb_id, 0, ORG, "err")
        retry_shot(sb_id, 0, ORG)
        start_shot_generation(sb_id, 0, "job-2", ORG)

        sb = get_storyboard(sb_id, ORG)
        assert sb.shots[0].attempt_count == 2


# =============================================================================
# Cancel
# =============================================================================


@pytest.mark.unit
class TestCancel:

    def test_cancel_clears_shot(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        shot = cancel_shot(sb_id, 0, ORG)
        assert shot.status == ShotStatus.CANCELLED
        assert shot.verified_asset is None
        assert shot.job_id is None

    def test_cancel_complete_shot_raises(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        complete_shot(sb_id, 0, ORG, "ast-001", "key", storage_verified=True)
        with pytest.raises(ShotAlreadyComplete):
            cancel_shot(sb_id, 0, ORG)


# =============================================================================
# Idempotency
# =============================================================================


@pytest.mark.unit
class TestIdempotency:

    def test_complete_same_asset_idempotent(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        complete_shot(sb_id, 0, ORG, "ast-001", "key-001", storage_verified=True)
        # Same asset again — idempotent
        shot = complete_shot(sb_id, 0, ORG, "ast-001", "key-001", storage_verified=True)
        assert shot.is_complete is True

    def test_complete_different_asset_raises(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        complete_shot(sb_id, 0, ORG, "ast-001", "key-001", storage_verified=True)
        with pytest.raises(ShotAlreadyComplete):
            complete_shot(sb_id, 0, ORG, "ast-002", "key-002", storage_verified=True)


# =============================================================================
# Cross-Tenant Isolation
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_get_returns_none(self):
        sb_id = _create_3_shot_storyboard()
        assert get_storyboard(sb_id, OTHER_ORG) is None

    def test_cross_tenant_start_raises(self):
        sb_id = _create_3_shot_storyboard()
        with pytest.raises(StoryboardNotFound):
            start_shot_generation(sb_id, 0, "job-001", OTHER_ORG)

    def test_cross_tenant_complete_raises(self):
        sb_id = _create_3_shot_storyboard()
        start_shot_generation(sb_id, 0, "job-001", ORG)
        with pytest.raises(StoryboardNotFound):
            complete_shot(sb_id, 0, OTHER_ORG, "ast", "key", storage_verified=True)

    def test_cross_tenant_progress_not_found(self):
        sb_id = _create_3_shot_storyboard()
        progress = get_storyboard_progress(sb_id, OTHER_ORG)
        assert progress == {"error": "not_found"}
