"""Durable lineage capture tests — Story 078.

Tests prove:
  - Lineage capture steps execute independently
  - Transient failures are retried (up to max_attempts)
  - Permanent failures raise alerts and are visible
  - Retry preserves original immutable generation values
  - Repair is authorized and audited
  - Duplicate repair is idempotent
  - Batch partial: some assets capture, some fail
  - Tenant isolation: cross-org access denied
  - Initiation is idempotent (same asset → same record)
  - Incomplete lineage is queryable
"""

import pytest

from backend.lineage_capture import (
    CaptureStatus,
    CaptureStep,
    ImmutableGenerationValues,
    LineageStatus,
    NoRetryableSteps,
    PermissionDenied,
    _reset_store,
    _set_permanent_failure,
    _set_step_failure,
    execute_capture,
    get_active_alerts,
    get_lineage_status,
    initiate_capture,
    list_incomplete_lineages,
    repair_step,
    retry_capture,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
ASSET = "ast-test-001"
JOB = "job-test-001"


def _gen_values(**overrides) -> ImmutableGenerationValues:
    defaults = dict(
        job_id=JOB,
        effective_prompt="a beautiful sunset over mountains, 8k, detailed",
        original_prompt="sunset over mountains",
        model_id="flux_dev",
        model_version="1.0.0",
        actual_seed=42,
        actual_width=1024,
        actual_height=1024,
        actual_steps=25,
        actual_cfg=7.5,
        provider="vast.ai",
        actual_cost_usd=0.03,
    )
    defaults.update(overrides)
    return ImmutableGenerationValues(**defaults)


# =============================================================================
# Happy Path
# =============================================================================


@pytest.mark.unit
class TestHappyPath:

    def test_full_capture_succeeds(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        record = execute_capture(record.capture_id)

        assert record.is_complete is True
        assert record.lineage_status == LineageStatus.COMPLETE
        assert record.completed_at is not None

    def test_all_steps_captured(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        record = execute_capture(record.capture_id)

        for step_record in record.steps.values():
            assert step_record.status == CaptureStatus.CAPTURED
            assert step_record.captured_at is not None

    def test_generation_values_preserved(self):
        gv = _gen_values(effective_prompt="specific prompt", actual_seed=99999)
        record = initiate_capture(ORG, ASSET, JOB, gv)

        assert record.generation_values.effective_prompt == "specific prompt"
        assert record.generation_values.actual_seed == 99999


# =============================================================================
# Transient Failure & Retry
# =============================================================================


@pytest.mark.unit
class TestTransientFailureRetry:

    def test_step_failure_is_retryable(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        _set_step_failure(CaptureStep.PROMPT_HISTORY)
        record = execute_capture(record.capture_id)

        # prompt_history failed, others succeeded
        assert record.steps[CaptureStep.CONTEXT_PACKAGE].status == CaptureStatus.CAPTURED
        assert record.steps[CaptureStep.PROMPT_HISTORY].status == CaptureStatus.FAILED
        assert record.steps[CaptureStep.PROVENANCE_LINK].status == CaptureStatus.CAPTURED
        assert record.is_complete is False

    def test_retry_recovers_failed_step(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        _set_step_failure(CaptureStep.PROMPT_HISTORY)
        record = execute_capture(record.capture_id)

        # Disable failure and retry
        _set_step_failure(CaptureStep.PROMPT_HISTORY, enabled=False)
        record = retry_capture(record.capture_id)

        assert record.steps[CaptureStep.PROMPT_HISTORY].status == CaptureStatus.CAPTURED
        assert record.is_complete is True

    def test_retry_preserves_immutable_values(self):
        """Retry uses original generation values, not current mutable state."""
        gv = _gen_values(effective_prompt="original truth", actual_seed=12345)
        record = initiate_capture(ORG, ASSET, JOB, gv)
        _set_step_failure(CaptureStep.CONTEXT_PACKAGE)
        execute_capture(record.capture_id)

        # After failure, the immutable values are unchanged
        assert record.generation_values.effective_prompt == "original truth"
        assert record.generation_values.actual_seed == 12345

        # Retry still uses same values
        _set_step_failure(CaptureStep.CONTEXT_PACKAGE, enabled=False)
        retry_capture(record.capture_id)
        assert record.generation_values.effective_prompt == "original truth"


# =============================================================================
# Permanent Failure & Alerts
# =============================================================================


@pytest.mark.unit
class TestPermanentFailure:

    def test_max_retries_marks_permanently_failed(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        _set_step_failure(CaptureStep.PROVENANCE_LINK)

        # Exhaust retries
        execute_capture(record.capture_id)  # attempt 1
        retry_capture(record.capture_id)    # attempt 2
        retry_capture(record.capture_id)    # attempt 3

        step = record.steps[CaptureStep.PROVENANCE_LINK]
        assert step.status == CaptureStatus.PERMANENTLY_FAILED
        assert step.attempts == 3

    def test_permanent_failure_raises_alert(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        _set_step_failure(CaptureStep.PROVENANCE_LINK)

        execute_capture(record.capture_id)
        retry_capture(record.capture_id)
        retry_capture(record.capture_id)

        alerts = get_active_alerts(ORG)
        assert len(alerts) > 0
        assert alerts[0]["type"] == "lineage_capture_failed"
        assert alerts[0]["step"] == "provenance_link"

    def test_no_retryable_steps_raises(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        execute_capture(record.capture_id)  # All succeed

        with pytest.raises(NoRetryableSteps):
            retry_capture(record.capture_id)

    def test_lineage_status_failed(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        _set_permanent_failure()

        execute_capture(record.capture_id)
        try:
            retry_capture(record.capture_id)
        except NoRetryableSteps:
            pass
        try:
            retry_capture(record.capture_id)
        except NoRetryableSteps:
            pass

        assert record.lineage_status == LineageStatus.FAILED


# =============================================================================
# Repair
# =============================================================================


@pytest.mark.unit
class TestRepair:

    def test_repair_permanently_failed_step(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        _set_step_failure(CaptureStep.PROMPT_HISTORY)

        execute_capture(record.capture_id)
        retry_capture(record.capture_id)
        retry_capture(record.capture_id)

        # Manually repair
        record = repair_step(
            record.capture_id, CaptureStep.PROMPT_HISTORY, ORG, "admin-user-001"
        )
        step = record.steps[CaptureStep.PROMPT_HISTORY]
        assert step.status == CaptureStatus.REPAIRED
        assert step.repaired_by == "admin-user-001"
        assert step.repaired_at is not None

    def test_repair_completes_lineage(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        _set_step_failure(CaptureStep.PROMPT_HISTORY)

        execute_capture(record.capture_id)
        retry_capture(record.capture_id)
        retry_capture(record.capture_id)

        repair_step(record.capture_id, CaptureStep.PROMPT_HISTORY, ORG, "admin")
        assert record.is_complete is True

    def test_repair_cross_tenant_denied(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        with pytest.raises(PermissionDenied):
            repair_step(record.capture_id, CaptureStep.CONTEXT_PACKAGE, OTHER_ORG, "hacker")

    def test_repair_without_actor_denied(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        with pytest.raises(PermissionDenied):
            repair_step(record.capture_id, CaptureStep.CONTEXT_PACKAGE, ORG, "")

    def test_duplicate_repair_idempotent(self):
        gv = _gen_values()
        record = initiate_capture(ORG, ASSET, JOB, gv)
        _set_step_failure(CaptureStep.CONTEXT_PACKAGE)
        execute_capture(record.capture_id)
        retry_capture(record.capture_id)
        retry_capture(record.capture_id)

        repair_step(record.capture_id, CaptureStep.CONTEXT_PACKAGE, ORG, "admin")
        # Second repair is idempotent
        record = repair_step(record.capture_id, CaptureStep.CONTEXT_PACKAGE, ORG, "admin")
        assert record.steps[CaptureStep.CONTEXT_PACKAGE].status == CaptureStatus.REPAIRED


# =============================================================================
# Batch Partial
# =============================================================================


@pytest.mark.unit
class TestBatchPartial:

    def test_partial_batch_some_complete_some_failed(self):
        """Multiple assets: some capture fine, some fail."""
        gv1 = _gen_values(job_id="j1")
        gv2 = _gen_values(job_id="j2")

        r1 = initiate_capture(ORG, "ast-1", "j1", gv1)
        r2 = initiate_capture(ORG, "ast-2", "j2", gv2)

        # Asset 1 captures fine
        execute_capture(r1.capture_id)
        assert r1.is_complete is True

        # Asset 2 has failures
        _set_step_failure(CaptureStep.PROVENANCE_LINK)
        execute_capture(r2.capture_id)
        assert r2.is_complete is False

        # Query incomplete
        incomplete = list_incomplete_lineages(ORG)
        assert len(incomplete) == 1
        assert incomplete[0]["asset_id"] == "ast-2"


# =============================================================================
# Tenant Isolation
# =============================================================================


@pytest.mark.unit
class TestTenantIsolation:

    def test_cross_tenant_status_returns_none(self):
        gv = _gen_values()
        initiate_capture(ORG, ASSET, JOB, gv)
        assert get_lineage_status(ASSET, OTHER_ORG) is None

    def test_same_tenant_status_returns_data(self):
        gv = _gen_values()
        initiate_capture(ORG, ASSET, JOB, gv)
        status = get_lineage_status(ASSET, ORG)
        assert status is not None
        assert status["asset_id"] == ASSET

    def test_list_incomplete_scoped_to_org(self):
        initiate_capture(ORG, "ast-a", "j-a", _gen_values(job_id="j-a"))
        initiate_capture(OTHER_ORG, "ast-b", "j-b", _gen_values(job_id="j-b"))

        _set_step_failure(CaptureStep.CONTEXT_PACKAGE)
        # Both will have failures
        execute_capture(_get_capture_id("ast-a"))
        execute_capture(_get_capture_id("ast-b"))

        results = list_incomplete_lineages(ORG)
        assert all(r["asset_id"].startswith("ast-a") for r in results)


# =============================================================================
# Idempotency
# =============================================================================


@pytest.mark.unit
class TestIdempotency:

    def test_initiate_same_asset_returns_existing(self):
        gv = _gen_values()
        r1 = initiate_capture(ORG, ASSET, JOB, gv)
        r2 = initiate_capture(ORG, ASSET, JOB, gv)
        assert r1.capture_id == r2.capture_id


# =============================================================================
# Helpers
# =============================================================================


def _get_capture_id(asset_id: str) -> str:
    from backend.lineage_capture import _asset_index
    return _asset_index[asset_id]
