"""Storyboard production orchestration tests — Story 110.

Tests prove:
  - Partial failure: some shots complete, some fail
  - Retry single shot without affecting siblings
  - Cancel race: cancel during running doesn't break completed
  - Duplicate submission returns existing (idempotent)
  - Reconnect/recovery returns full server state
  - Ordering immutable after creation
  - Per-shot cost and total aggregation
  - Production lifecycle: queued → running → completed
  - Cross-tenant access denied
  - Cancel production cancels all non-terminal children
"""

import pytest

from backend.storyboard_production import (
    ProductionNotFound,
    ProductionStatus,
    ShotJobStatus,
    ShotNotRetryable,
    _reset_store,
    cancel_production,
    cancel_shot_job,
    complete_shot,
    create_production,
    fail_shot,
    get_production_progress,
    list_productions,
    retry_shot,
    start_shot,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
USER = "user-001"
STORYBOARD = "sb-001"
CTX_PKG = "pkg-001"


def _shots(count: int = 3) -> list[dict]:
    return [{"prompt": f"Shot {i} prompt"} for i in range(count)]


def _create_prod(shots=None, **overrides):
    defaults = dict(
        org_id=ORG, user_id=USER, storyboard_id=STORYBOARD,
        context_package_id=CTX_PKG, shots=shots or _shots(),
    )
    defaults.update(overrides)
    return create_production(**defaults)


# =============================================================================
# Full Lifecycle
# =============================================================================


@pytest.mark.unit
class TestFullLifecycle:

    def test_create_production(self):
        prod = _create_prod()
        assert prod.status == ProductionStatus.QUEUED
        assert prod.shot_count == 3

    def test_all_shots_complete_finishes_production(self):
        prod = _create_prod()
        for i in range(3):
            start_shot(prod.production_id, i, ORG)
            complete_shot(prod.production_id, i, ORG, f"ast-{i}", cost_usd=0.02)
        assert prod.status == ProductionStatus.COMPLETED
        assert prod.progress_pct == 100

    def test_start_shot_transitions_parent_to_running(self):
        prod = _create_prod()
        start_shot(prod.production_id, 0, ORG)
        assert prod.status == ProductionStatus.RUNNING


# =============================================================================
# Partial Failure
# =============================================================================


@pytest.mark.unit
class TestPartialFailure:

    def test_some_complete_some_failed(self):
        prod = _create_prod()
        start_shot(prod.production_id, 0, ORG)
        complete_shot(prod.production_id, 0, ORG, "ast-0", cost_usd=0.02)

        start_shot(prod.production_id, 1, ORG)
        fail_shot(prod.production_id, 1, ORG, "provider error")

        start_shot(prod.production_id, 2, ORG)
        complete_shot(prod.production_id, 2, ORG, "ast-2", cost_usd=0.02)

        assert prod.status == ProductionStatus.PARTIAL
        assert prod.completed_count == 2
        assert prod.failed_count == 1

    def test_all_failed(self):
        prod = _create_prod()
        for i in range(3):
            start_shot(prod.production_id, i, ORG)
            fail_shot(prod.production_id, i, ORG, "err")
        assert prod.status == ProductionStatus.FAILED


# =============================================================================
# Retry Single Shot
# =============================================================================


@pytest.mark.unit
class TestRetrySingleShot:

    def test_retry_failed_shot(self):
        prod = _create_prod()
        start_shot(prod.production_id, 1, ORG)
        fail_shot(prod.production_id, 1, ORG, "timeout")

        shot = retry_shot(prod.production_id, 1, ORG)
        assert shot.status == ShotJobStatus.QUEUED
        assert shot.error is None

    def test_retry_doesnt_affect_completed_sibling(self):
        prod = _create_prod()
        start_shot(prod.production_id, 0, ORG)
        complete_shot(prod.production_id, 0, ORG, "ast-0")

        start_shot(prod.production_id, 1, ORG)
        fail_shot(prod.production_id, 1, ORG, "err")

        retry_shot(prod.production_id, 1, ORG)
        # Sibling unaffected
        assert prod.shots[0].status == ShotJobStatus.COMPLETED
        assert prod.shots[0].output_asset_id == "ast-0"

    def test_retry_queued_raises(self):
        prod = _create_prod()
        with pytest.raises(ShotNotRetryable):
            retry_shot(prod.production_id, 0, ORG)

    def test_retry_resets_parent_to_running(self):
        prod = _create_prod(shots=_shots(2))
        start_shot(prod.production_id, 0, ORG)
        complete_shot(prod.production_id, 0, ORG, "ast-0")
        start_shot(prod.production_id, 1, ORG)
        fail_shot(prod.production_id, 1, ORG, "err")
        assert prod.status == ProductionStatus.PARTIAL

        retry_shot(prod.production_id, 1, ORG)
        assert prod.status == ProductionStatus.RUNNING


# =============================================================================
# Cancel
# =============================================================================


@pytest.mark.unit
class TestCancel:

    def test_cancel_production_cancels_non_terminal(self):
        prod = _create_prod()
        start_shot(prod.production_id, 0, ORG)
        complete_shot(prod.production_id, 0, ORG, "ast-0")
        # Shots 1 and 2 still queued
        cancel_production(prod.production_id, ORG)

        assert prod.status == ProductionStatus.CANCELLED
        assert prod.shots[0].status == ShotJobStatus.COMPLETED  # Preserved
        assert prod.shots[1].status == ShotJobStatus.CANCELLED
        assert prod.shots[2].status == ShotJobStatus.CANCELLED

    def test_cancel_single_shot(self):
        prod = _create_prod()
        cancel_shot_job(prod.production_id, 1, ORG)
        assert prod.shots[1].status == ShotJobStatus.CANCELLED
        assert prod.shots[0].status == ShotJobStatus.QUEUED  # Unaffected

    def test_cancel_already_cancelled_idempotent(self):
        prod = _create_prod()
        cancel_production(prod.production_id, ORG)
        result = cancel_production(prod.production_id, ORG)
        assert result.status == ProductionStatus.CANCELLED

    def test_cancel_race_completed_shot_preserved(self):
        """Shot completes right before cancel — output preserved."""
        prod = _create_prod()
        start_shot(prod.production_id, 0, ORG)
        complete_shot(prod.production_id, 0, ORG, "ast-0", cost_usd=0.03)
        # Now cancel — shot 0 already terminal
        cancel_shot_job(prod.production_id, 0, ORG)
        assert prod.shots[0].status == ShotJobStatus.COMPLETED  # Not overwritten
        assert prod.shots[0].output_asset_id == "ast-0"


# =============================================================================
# Duplicate Submission (Idempotent)
# =============================================================================


@pytest.mark.unit
class TestDuplicateSubmission:

    def test_same_key_returns_existing(self):
        p1 = _create_prod(idempotency_key="key-001")
        p2 = _create_prod(idempotency_key="key-001")
        assert p1.production_id == p2.production_id

    def test_no_key_creates_new(self):
        p1 = _create_prod()
        p2 = _create_prod()
        assert p1.production_id != p2.production_id


# =============================================================================
# Reconnect / Recovery
# =============================================================================


@pytest.mark.unit
class TestReconnectRecovery:

    def test_progress_returns_full_state(self):
        prod = _create_prod()
        start_shot(prod.production_id, 0, ORG)
        complete_shot(prod.production_id, 0, ORG, "ast-0", cost_usd=0.02)

        progress = get_production_progress(prod.production_id, ORG)
        assert progress is not None
        assert progress["status"] == "running"
        assert progress["completed_count"] == 1
        assert progress["shot_count"] == 3
        assert len(progress["shots"]) == 3
        assert progress["shots"][0]["status"] == "completed"
        assert progress["shots"][0]["output_asset_id"] == "ast-0"

    def test_cross_tenant_progress_none(self):
        prod = _create_prod()
        assert get_production_progress(prod.production_id, OTHER_ORG) is None


# =============================================================================
# Ordering Consistency
# =============================================================================


@pytest.mark.unit
class TestOrdering:

    def test_shot_ordering_preserved(self):
        prod = _create_prod(shots=[
            {"prompt": "first"},
            {"prompt": "second"},
            {"prompt": "third"},
        ])
        assert prod.shots[0].prompt == "first"
        assert prod.shots[1].prompt == "second"
        assert prod.shots[2].prompt == "third"
        assert [s.shot_index for s in prod.shots] == [0, 1, 2]

    def test_retry_preserves_ordering(self):
        prod = _create_prod()
        start_shot(prod.production_id, 1, ORG)
        fail_shot(prod.production_id, 1, ORG, "err")
        retry_shot(prod.production_id, 1, ORG)
        # Index unchanged
        assert prod.shots[1].shot_index == 1


# =============================================================================
# Per-Shot Cost
# =============================================================================


@pytest.mark.unit
class TestCost:

    def test_per_shot_cost_tracked(self):
        prod = _create_prod()
        start_shot(prod.production_id, 0, ORG)
        complete_shot(prod.production_id, 0, ORG, "ast-0", cost_usd=0.03)
        assert prod.shots[0].cost_usd == 0.03

    def test_total_cost_aggregated(self):
        prod = _create_prod(shots=_shots(2))
        start_shot(prod.production_id, 0, ORG)
        complete_shot(prod.production_id, 0, ORG, "ast-0", cost_usd=0.02)
        start_shot(prod.production_id, 1, ORG)
        complete_shot(prod.production_id, 1, ORG, "ast-1", cost_usd=0.03)
        assert prod.total_cost_usd == 0.05


# =============================================================================
# Cross-Tenant
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_start_raises(self):
        prod = _create_prod()
        with pytest.raises(ProductionNotFound):
            start_shot(prod.production_id, 0, OTHER_ORG)

    def test_cross_tenant_cancel_raises(self):
        prod = _create_prod()
        with pytest.raises(ProductionNotFound):
            cancel_production(prod.production_id, OTHER_ORG)

    def test_list_scoped_to_org(self):
        _create_prod(org_id=ORG)
        _create_prod(org_id=OTHER_ORG, user_id="other", storyboard_id="sb-2")
        results = list_productions(ORG)
        assert len(results) == 1
