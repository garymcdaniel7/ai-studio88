"""Durable Batch Generation Tests (Story 109).

Proves: batch lifecycle, partial failure, cancellation, retry targeting,
idempotency, cost tracking, and progress computation.

Run with:
    pytest tests/unit/test_batch_generation.py -v
"""
from __future__ import annotations

import pytest

from backend.batch_generation import (
    BatchError,
    BatchState,
    ChildState,
    GenerationBatch,
    VariationJob,
    cancel_batch,
    cancel_variation,
    clear_store,
    complete_variation,
    fail_variation,
    get_batch,
    retry_failed,
    retry_single,
    start_variation,
    submit_batch,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_store()
    yield
    clear_store()


def _submit(count: int = 4, **overrides) -> GenerationBatch:
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "variation_count": count,
        "model": "flux-dev",
        "prompt": "A futuristic city",
        "cost_per_variation_usd": 0.05,
    }
    defaults.update(overrides)
    return submit_batch(**defaults)


# =============================================================================
# Batch Lifecycle
# =============================================================================


class TestBatchLifecycle:

    @pytest.mark.unit
    def test_submission_creates_batch(self):
        """Submission creates a batch with correct child count."""
        batch = _submit(count=4)
        assert batch.state == BatchState.SUBMITTED
        assert len(batch.variations) == 4
        assert batch.requested_count == 4

    @pytest.mark.unit
    def test_start_moves_to_in_progress(self):
        """Starting a child moves batch to IN_PROGRESS."""
        batch = _submit(count=3)
        start_variation(batch.batch_id, batch.variations[0].job_id)
        assert batch.state == BatchState.IN_PROGRESS

    @pytest.mark.unit
    def test_all_complete_moves_to_completed(self):
        """All children completing moves batch to COMPLETED."""
        batch = _submit(count=2)
        for v in batch.variations:
            start_variation(batch.batch_id, v.job_id)
            complete_variation(batch.batch_id, v.job_id, asset_id=f"asset-{v.job_id}")
        assert batch.state == BatchState.COMPLETED
        assert batch.completed_at is not None

    @pytest.mark.unit
    def test_children_have_unique_ids(self):
        """Each child variation has a unique job_id."""
        batch = _submit(count=5)
        ids = [v.job_id for v in batch.variations]
        assert len(set(ids)) == 5

    @pytest.mark.unit
    def test_children_have_sequential_indices(self):
        """Children are numbered 0..N-1."""
        batch = _submit(count=3)
        indices = [v.variation_index for v in batch.variations]
        assert indices == [0, 1, 2]

    @pytest.mark.unit
    def test_progress_pct_computed(self):
        """Progress percentage tracks terminal children."""
        batch = _submit(count=4)
        assert batch.progress_pct == 0.0
        start_variation(batch.batch_id, batch.variations[0].job_id)
        complete_variation(batch.batch_id, batch.variations[0].job_id, asset_id="a1")
        assert batch.progress_pct == 25.0


# =============================================================================
# Partial Failure
# =============================================================================


class TestPartialFailure:

    @pytest.mark.unit
    def test_failed_child_preserves_completed(self):
        """Failed variation doesn't affect completed siblings."""
        batch = _submit(count=3)
        for v in batch.variations:
            start_variation(batch.batch_id, v.job_id)

        complete_variation(batch.batch_id, batch.variations[0].job_id, asset_id="a1")
        fail_variation(batch.batch_id, batch.variations[1].job_id, error="GPU OOM")
        complete_variation(batch.batch_id, batch.variations[2].job_id, asset_id="a3")

        assert batch.completed_count == 2
        assert batch.failed_count == 1
        assert batch.variations[0].asset_id == "a1"
        assert batch.state == BatchState.COMPLETED

    @pytest.mark.unit
    def test_failure_records_error(self):
        """Failed variation records error message."""
        batch = _submit(count=1)
        start_variation(batch.batch_id, batch.variations[0].job_id)
        fail_variation(batch.batch_id, batch.variations[0].job_id, error="Provider timeout")
        assert batch.variations[0].error_message == "Provider timeout"
        assert batch.variations[0].completed_at is not None

    @pytest.mark.unit
    def test_all_failed_batch_still_completes(self):
        """Batch with all failures still reaches COMPLETED (terminal)."""
        batch = _submit(count=2)
        for v in batch.variations:
            start_variation(batch.batch_id, v.job_id)
            fail_variation(batch.batch_id, v.job_id, error="err")
        assert batch.state == BatchState.COMPLETED
        assert batch.failed_count == 2


# =============================================================================
# Cancellation
# =============================================================================


class TestCancellation:

    @pytest.mark.unit
    def test_cancel_batch_marks_queued(self):
        """Cancel marks all QUEUED children as CANCELLED."""
        batch = _submit(count=4)
        cancel_batch(batch.batch_id)
        assert batch.state == BatchState.CANCELLED
        assert all(v.state == ChildState.CANCELLED for v in batch.variations)

    @pytest.mark.unit
    def test_cancel_preserves_executing(self):
        """Cancel doesn't stop executing children."""
        batch = _submit(count=3)
        start_variation(batch.batch_id, batch.variations[0].job_id)
        cancel_batch(batch.batch_id)

        assert batch.variations[0].state == ChildState.EXECUTING  # Still running
        assert batch.variations[1].state == ChildState.CANCELLED
        assert batch.variations[2].state == ChildState.CANCELLED

    @pytest.mark.unit
    def test_cancel_preserves_completed(self):
        """Cancel doesn't touch already-completed children."""
        batch = _submit(count=2)
        start_variation(batch.batch_id, batch.variations[0].job_id)
        complete_variation(batch.batch_id, batch.variations[0].job_id, asset_id="a1")
        cancel_batch(batch.batch_id)

        assert batch.variations[0].state == ChildState.COMPLETED
        assert batch.variations[0].asset_id == "a1"

    @pytest.mark.unit
    def test_cancel_single_variation(self):
        """Can cancel a single queued variation."""
        batch = _submit(count=3)
        cancel_variation(batch.batch_id, batch.variations[1].job_id)
        assert batch.variations[0].state == ChildState.QUEUED  # Untouched
        assert batch.variations[1].state == ChildState.CANCELLED
        assert batch.variations[2].state == ChildState.QUEUED  # Untouched

    @pytest.mark.unit
    def test_cancel_idempotent(self):
        """Cancelling already-cancelled batch is a no-op."""
        batch = _submit(count=2)
        cancel_batch(batch.batch_id)
        cancel_batch(batch.batch_id)  # No error
        assert batch.state == BatchState.CANCELLED


# =============================================================================
# Retry Targeting
# =============================================================================


class TestRetry:

    @pytest.mark.unit
    def test_retry_targets_only_failed(self):
        """Retry replaces only FAILED/CANCELLED variations."""
        batch = _submit(count=3)
        for v in batch.variations:
            start_variation(batch.batch_id, v.job_id)

        complete_variation(batch.batch_id, batch.variations[0].job_id, asset_id="a1")
        fail_variation(batch.batch_id, batch.variations[1].job_id, error="err")
        fail_variation(batch.batch_id, batch.variations[2].job_id, error="err")

        retried = retry_failed(batch.batch_id)
        assert len(retried) == 2
        # Completed variation preserved
        assert batch.variations[0].state == ChildState.COMPLETED
        assert batch.variations[0].asset_id == "a1"
        # Retried are new QUEUED jobs
        assert batch.variations[1].state == ChildState.QUEUED
        assert batch.variations[2].state == ChildState.QUEUED

    @pytest.mark.unit
    def test_retry_increments_attempt(self):
        """Retried jobs have incremented attempt counter."""
        batch = _submit(count=1)
        start_variation(batch.batch_id, batch.variations[0].job_id)
        fail_variation(batch.batch_id, batch.variations[0].job_id, error="err")
        retried = retry_failed(batch.batch_id)
        assert retried[0].attempt == 2

    @pytest.mark.unit
    def test_retry_preserves_parent_lineage(self):
        """Retried job references its parent job_id."""
        batch = _submit(count=1)
        original_id = batch.variations[0].job_id
        start_variation(batch.batch_id, original_id)
        fail_variation(batch.batch_id, original_id, error="err")
        retried = retry_failed(batch.batch_id)
        assert retried[0].parent_job_id == original_id

    @pytest.mark.unit
    def test_retry_resets_batch_state(self):
        """Retry resets batch from COMPLETED back to SUBMITTED."""
        batch = _submit(count=1)
        start_variation(batch.batch_id, batch.variations[0].job_id)
        fail_variation(batch.batch_id, batch.variations[0].job_id, error="err")
        assert batch.state == BatchState.COMPLETED

        retry_failed(batch.batch_id)
        assert batch.state == BatchState.SUBMITTED

    @pytest.mark.unit
    def test_retry_single_variation(self):
        """Can retry a single failed variation."""
        batch = _submit(count=2)
        for v in batch.variations:
            start_variation(batch.batch_id, v.job_id)
        fail_variation(batch.batch_id, batch.variations[0].job_id, error="err")
        complete_variation(batch.batch_id, batch.variations[1].job_id, asset_id="a2")

        original_id = batch.variations[0].job_id
        result = retry_single(batch.batch_id, original_id)
        assert result is not None
        assert result.state == ChildState.QUEUED
        assert result.parent_job_id == original_id

    @pytest.mark.unit
    def test_retry_completed_returns_none(self):
        """Cannot retry a completed variation."""
        batch = _submit(count=1)
        start_variation(batch.batch_id, batch.variations[0].job_id)
        complete_variation(batch.batch_id, batch.variations[0].job_id, asset_id="a1")
        result = retry_single(batch.batch_id, batch.variations[0].job_id)
        assert result is None  # Not retryable


# =============================================================================
# Idempotency
# =============================================================================


class TestIdempotency:

    @pytest.mark.unit
    def test_duplicate_key_returns_existing(self):
        """Same idempotency_key returns existing batch."""
        batch1 = _submit(idempotency_key="idem-001")
        batch2 = _submit(idempotency_key="idem-001", count=10)  # Different count
        assert batch1.batch_id == batch2.batch_id
        assert len(batch2.variations) == 4  # Original count preserved

    @pytest.mark.unit
    def test_different_keys_create_separate(self):
        """Different keys create separate batches."""
        b1 = _submit(idempotency_key="key-A")
        b2 = _submit(idempotency_key="key-B")
        assert b1.batch_id != b2.batch_id

    @pytest.mark.unit
    def test_no_key_always_creates(self):
        """No idempotency key always creates new batch."""
        b1 = _submit(idempotency_key="")
        b2 = _submit(idempotency_key="")
        assert b1.batch_id != b2.batch_id


# =============================================================================
# Cost Tracking
# =============================================================================


class TestCostTracking:

    @pytest.mark.unit
    def test_estimated_cost_aggregated(self):
        """Total estimated cost is sum of per-variation estimates."""
        batch = _submit(count=4, cost_per_variation_usd=0.10)
        assert batch.total_estimated_usd == pytest.approx(0.40)

    @pytest.mark.unit
    def test_actual_cost_accumulated(self):
        """Actual cost accumulates as children complete."""
        batch = _submit(count=2, cost_per_variation_usd=0.10)
        for v in batch.variations:
            start_variation(batch.batch_id, v.job_id)
        complete_variation(batch.batch_id, batch.variations[0].job_id, asset_id="a1", cost_actual_usd=0.08)
        complete_variation(batch.batch_id, batch.variations[1].job_id, asset_id="a2", cost_actual_usd=0.09)
        assert batch.total_actual_usd == pytest.approx(0.17)

    @pytest.mark.unit
    def test_per_variation_cost_visible(self):
        """Each variation tracks its own cost."""
        batch = _submit(count=1, cost_per_variation_usd=0.05)
        start_variation(batch.batch_id, batch.variations[0].job_id)
        complete_variation(batch.batch_id, batch.variations[0].job_id, asset_id="a1", cost_actual_usd=0.04)
        assert batch.variations[0].cost_estimated_usd == 0.05
        assert batch.variations[0].cost_actual_usd == 0.04


# =============================================================================
# Validation & Serialization
# =============================================================================


class TestValidation:

    @pytest.mark.unit
    def test_count_too_large_rejected(self):
        """Variation count > 50 rejected."""
        with pytest.raises(BatchError) as exc_info:
            _submit(count=100)
        assert exc_info.value.code == "INVALID_COUNT"

    @pytest.mark.unit
    def test_count_zero_rejected(self):
        """Variation count 0 rejected."""
        with pytest.raises(BatchError):
            _submit(count=0)

    @pytest.mark.unit
    def test_missing_auth_rejected(self):
        """Missing org_id raises error."""
        with pytest.raises(BatchError) as exc_info:
            submit_batch(org_id="", user_id="u", variation_count=1)
        assert exc_info.value.code == "AUTH_REQUIRED"

    @pytest.mark.unit
    def test_batch_serializable(self):
        """GenerationBatch.to_dict() is JSON-serializable."""
        import json
        batch = _submit(count=2)
        json.dumps(batch.to_dict())

    @pytest.mark.unit
    def test_seeds_assigned_per_variation(self):
        """Custom seeds are assigned to each variation."""
        batch = _submit(count=3, seeds=[42, 99, 7])
        assert batch.variations[0].seed == 42
        assert batch.variations[1].seed == 99
        assert batch.variations[2].seed == 7
