"""Unified Generation Platform tests — Story 072.

Tests prove:
  - All 4 surfaces submit through canonical API
  - Authentication is required (server-derived)
  - Jobs are durable (retrievable after submission)
  - Cancel, retry, and progress work correctly
  - Completed jobs register authoritative assets
  - Idempotency prevents duplicate work
  - Cross-tenant access returns None (no existence leak)
  - Storyboard batch creates linked jobs
  - Hermes requires approval token
  - Cancel race: output discarded if cancelled during execution
  - Reconnect: client can poll status at any time
  - Legacy telemetry records adapter usage
"""

import pytest

from backend.generation_platform import (
    AuthenticationRequired,
    AuthorizationDenied,
    GenerationSpec,
    GenerationType,
    InvalidOperation,
    JobNotFound,
    JobStatus,
    Surface,
    ValidationError,
    _reset_store,
    cancel_job,
    get_job_status,
    get_legacy_usage_summary,
    get_registered_asset,
    get_storyboard_jobs,
    list_jobs,
    mark_completed,
    mark_failed,
    mark_running,
    record_legacy_call,
    retry_job,
    submit_from_create,
    submit_from_hermes,
    submit_from_quick_edit,
    submit_from_storyboard,
    submit_generation,
    update_progress,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
USER = "user-test-001"
OTHER_ORG = "org-other-999"


# =============================================================================
# Cross-Surface Contract
# =============================================================================


@pytest.mark.unit
class TestCrossSurfaceContract:

    def test_create_surface(self):
        job = submit_from_create(ORG, USER, prompt="a cat in space")
        assert job.surface == Surface.CREATE
        assert job.status == JobStatus.QUEUED
        assert job.org_id == ORG
        assert job.spec.prompt == "a cat in space"

    def test_storyboard_surface(self):
        shots = [
            {"prompt": "shot 1", "model": "sdxl"},
            {"prompt": "shot 2", "model": "flux_dev"},
        ]
        jobs = submit_from_storyboard(ORG, USER, "sb-001", shots)
        assert len(jobs) == 2
        assert all(j.surface == Surface.STORYBOARD for j in jobs)
        assert jobs[0].spec.storyboard_id == "sb-001"
        assert jobs[0].spec.shot_index == 0
        assert jobs[1].spec.shot_index == 1

    def test_quick_edit_surface(self):
        job = submit_from_quick_edit(ORG, USER, "asset-001", "upscale")
        assert job.surface == Surface.QUICK_EDIT
        assert job.spec.source_asset_id == "asset-001"
        assert job.spec.generation_type == GenerationType.UPSCALE

    def test_hermes_surface(self):
        job = submit_from_hermes(ORG, USER, "a portrait", approval_token="tok-123")
        assert job.surface == Surface.HERMES
        assert job.spec.approval_token == "tok-123"

    def test_all_surfaces_produce_durable_jobs(self):
        j1 = submit_from_create(ORG, USER, prompt="test1")
        j2 = submit_from_quick_edit(ORG, USER, "ast-1", "img2img", prompt="test2")
        j3 = submit_from_hermes(ORG, USER, "test3", approval_token="t-1")

        # All retrievable
        assert get_job_status(j1.job_id, ORG) is not None
        assert get_job_status(j2.job_id, ORG) is not None
        assert get_job_status(j3.job_id, ORG) is not None


# =============================================================================
# Authentication & Authorization
# =============================================================================


@pytest.mark.unit
class TestAuthentication:

    def test_missing_org_id_raises(self):
        spec = GenerationSpec(prompt="test")
        with pytest.raises(AuthenticationRequired):
            submit_generation("", USER, Surface.CREATE, spec)

    def test_missing_user_id_raises(self):
        spec = GenerationSpec(prompt="test")
        with pytest.raises(AuthenticationRequired):
            submit_generation(ORG, "", Surface.CREATE, spec)

    def test_hermes_without_token_raises(self):
        with pytest.raises(AuthorizationDenied):
            submit_from_hermes(ORG, USER, "test", approval_token="")

    def test_empty_prompt_raises(self):
        spec = GenerationSpec(prompt="")
        with pytest.raises(ValidationError):
            submit_generation(ORG, USER, Surface.CREATE, spec)

    def test_upscale_allows_empty_prompt(self):
        spec = GenerationSpec(prompt="", generation_type=GenerationType.UPSCALE, source_asset_id="a1")
        job = submit_generation(ORG, USER, Surface.QUICK_EDIT, spec)
        assert job.status == JobStatus.QUEUED


# =============================================================================
# Tenant Isolation
# =============================================================================


@pytest.mark.unit
class TestTenantIsolation:

    def test_cross_tenant_get_returns_none(self):
        job = submit_from_create(ORG, USER, prompt="private")
        result = get_job_status(job.job_id, OTHER_ORG)
        assert result is None

    def test_cross_tenant_cancel_raises(self):
        job = submit_from_create(ORG, USER, prompt="private")
        with pytest.raises(JobNotFound):
            cancel_job(job.job_id, OTHER_ORG)

    def test_cross_tenant_retry_raises(self):
        job = submit_from_create(ORG, USER, prompt="private")
        mark_failed(job.job_id, "test error")
        with pytest.raises(JobNotFound):
            retry_job(job.job_id, OTHER_ORG)

    def test_list_jobs_scoped_to_org(self):
        submit_from_create(ORG, USER, prompt="mine")
        submit_from_create(OTHER_ORG, "other-user", prompt="theirs")
        results = list_jobs(ORG)
        assert len(results) == 1
        assert results[0].org_id == ORG

    def test_asset_cross_tenant_returns_none(self):
        job = submit_from_create(ORG, USER, prompt="test")
        mark_running(job.job_id)
        mark_completed(job.job_id, "url", "key", actual_cost_usd=0.01)
        asset_id = job.output_asset_id
        assert get_registered_asset(asset_id, OTHER_ORG) is None
        assert get_registered_asset(asset_id, ORG) is not None


# =============================================================================
# Reconnect (poll status at any time)
# =============================================================================


@pytest.mark.unit
class TestReconnect:

    def test_get_status_after_submission(self):
        job = submit_from_create(ORG, USER, prompt="reconnect test")
        # Simulate browser close and re-open
        retrieved = get_job_status(job.job_id, ORG)
        assert retrieved is not None
        assert retrieved.status == JobStatus.QUEUED

    def test_get_status_while_running(self):
        job = submit_from_create(ORG, USER, prompt="running test")
        mark_running(job.job_id)
        update_progress(job.job_id, 50)
        retrieved = get_job_status(job.job_id, ORG)
        assert retrieved.status == JobStatus.RUNNING
        assert retrieved.progress_pct == 50

    def test_get_status_after_completion(self):
        job = submit_from_create(ORG, USER, prompt="done test")
        mark_running(job.job_id)
        mark_completed(job.job_id, "url", "key")
        retrieved = get_job_status(job.job_id, ORG)
        assert retrieved.status == JobStatus.COMPLETED
        assert retrieved.output_asset_id is not None


# =============================================================================
# Cancel & Cancel Race
# =============================================================================


@pytest.mark.unit
class TestCancel:

    def test_cancel_queued_job(self):
        job = submit_from_create(ORG, USER, prompt="cancel me")
        result = cancel_job(job.job_id, ORG)
        assert result.status == JobStatus.CANCELLED

    def test_cancel_running_job(self):
        job = submit_from_create(ORG, USER, prompt="cancel mid")
        mark_running(job.job_id)
        result = cancel_job(job.job_id, ORG)
        assert result.status == JobStatus.CANCELLED

    def test_cancel_completed_raises(self):
        job = submit_from_create(ORG, USER, prompt="done")
        mark_running(job.job_id)
        mark_completed(job.job_id, "url", "key")
        with pytest.raises(InvalidOperation):
            cancel_job(job.job_id, ORG)

    def test_cancel_race_discards_output(self):
        """Provider completes AFTER user cancels — output not registered."""
        job = submit_from_create(ORG, USER, prompt="race")
        mark_running(job.job_id)
        cancel_job(job.job_id, ORG)
        # Provider sends completion after cancel
        mark_completed(job.job_id, "url", "key")
        # Job stays cancelled, no asset registered
        assert job.status == JobStatus.CANCELLED
        assert job.output_asset_id is None

    def test_cancel_idempotent(self):
        job = submit_from_create(ORG, USER, prompt="idem cancel")
        cancel_job(job.job_id, ORG)
        result = cancel_job(job.job_id, ORG)
        assert result.status == JobStatus.CANCELLED


# =============================================================================
# Retry
# =============================================================================


@pytest.mark.unit
class TestRetry:

    def test_retry_failed_job(self):
        job = submit_from_create(ORG, USER, prompt="retry me")
        mark_running(job.job_id)
        mark_failed(job.job_id, "provider error")
        result = retry_job(job.job_id, ORG)
        assert result.status == JobStatus.QUEUED
        assert result.retries == 1

    def test_retry_exceeded_raises(self):
        job = submit_from_create(ORG, USER, prompt="exhaust")
        mark_running(job.job_id)
        mark_failed(job.job_id, "err")
        retry_job(job.job_id, ORG)
        mark_running(job.job_id)
        mark_failed(job.job_id, "err")
        retry_job(job.job_id, ORG)
        mark_running(job.job_id)
        mark_failed(job.job_id, "err")
        # Max retries (2) exceeded
        with pytest.raises(InvalidOperation):
            retry_job(job.job_id, ORG)

    def test_retry_queued_raises(self):
        job = submit_from_create(ORG, USER, prompt="not failed")
        with pytest.raises(InvalidOperation):
            retry_job(job.job_id, ORG)


# =============================================================================
# Idempotency
# =============================================================================


@pytest.mark.unit
class TestIdempotency:

    def test_same_key_returns_existing(self):
        j1 = submit_from_create(ORG, USER, prompt="test", idempotency_key="key-001")
        j2 = submit_from_create(ORG, USER, prompt="test", idempotency_key="key-001")
        assert j1.job_id == j2.job_id

    def test_different_key_creates_new(self):
        j1 = submit_from_create(ORG, USER, prompt="test", idempotency_key="key-001")
        j2 = submit_from_create(ORG, USER, prompt="test", idempotency_key="key-002")
        assert j1.job_id != j2.job_id

    def test_no_key_always_creates_new(self):
        j1 = submit_from_create(ORG, USER, prompt="test")
        j2 = submit_from_create(ORG, USER, prompt="test")
        assert j1.job_id != j2.job_id


# =============================================================================
# Asset Registration
# =============================================================================


@pytest.mark.unit
class TestAssetRegistration:

    def test_completed_job_registers_asset(self):
        job = submit_from_create(ORG, USER, prompt="asset test", talent_id="t-1")
        mark_running(job.job_id)
        mark_completed(job.job_id, "https://cdn/img.webp", "org/images/img.webp",
                       content_type="image/webp", file_size_bytes=50000, seed=42)
        assert job.output_asset_id is not None
        asset = get_registered_asset(job.output_asset_id, ORG)
        assert asset is not None
        assert asset.org_id == ORG
        assert asset.talent_id == "t-1"
        assert asset.model_used == "flux_dev"
        assert asset.seed == 42
        assert asset.storage_key == "org/images/img.webp"

    def test_cancelled_job_no_asset(self):
        job = submit_from_create(ORG, USER, prompt="no asset")
        mark_running(job.job_id)
        cancel_job(job.job_id, ORG)
        mark_completed(job.job_id, "url", "key")
        assert job.output_asset_id is None

    def test_failed_job_no_asset(self):
        job = submit_from_create(ORG, USER, prompt="fail test")
        mark_running(job.job_id)
        mark_failed(job.job_id, "oops")
        assert job.output_asset_id is None


# =============================================================================
# Storyboard Batch
# =============================================================================


@pytest.mark.unit
class TestStoryboardBatch:

    def test_batch_creates_linked_jobs(self):
        shots = [{"prompt": f"shot {i}"} for i in range(5)]
        jobs = submit_from_storyboard(ORG, USER, "sb-100", shots)
        assert len(jobs) == 5
        retrieved = get_storyboard_jobs(ORG, "sb-100")
        assert len(retrieved) == 5
        assert [j.spec.shot_index for j in retrieved] == [0, 1, 2, 3, 4]

    def test_partial_batch_success(self):
        shots = [{"prompt": "s1"}, {"prompt": "s2"}, {"prompt": "s3"}]
        jobs = submit_from_storyboard(ORG, USER, "sb-partial", shots)
        # Complete first, fail second, leave third queued
        mark_running(jobs[0].job_id)
        mark_completed(jobs[0].job_id, "url1", "key1")
        mark_running(jobs[1].job_id)
        mark_failed(jobs[1].job_id, "err")
        # Query shows mixed status
        sb_jobs = get_storyboard_jobs(ORG, "sb-partial")
        statuses = {j.status for j in sb_jobs}
        assert JobStatus.COMPLETED in statuses
        assert JobStatus.FAILED in statuses
        assert JobStatus.QUEUED in statuses


# =============================================================================
# Legacy Telemetry
# =============================================================================


@pytest.mark.unit
class TestLegacyTelemetry:

    def test_record_legacy_call(self):
        record_legacy_call("create", "/api/v1/generate/image", ORG)
        record_legacy_call("create", "/api/v1/generate/image", ORG)
        summary = get_legacy_usage_summary()
        assert summary["create"] == 2

    def test_empty_initially(self):
        summary = get_legacy_usage_summary()
        assert summary == {}
