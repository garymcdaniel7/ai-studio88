"""Quick Edit Transform Job Tests (Story 111).

Proves: source validation, durable lifecycle, cancellation, retry,
cross-tenant denial, output requirement, and idempotency.

Run with:
    pytest tests/unit/test_transform_job.py -v
"""
from __future__ import annotations

import pytest

from backend.transform_job import (
    SourceAsset,
    SourceValidationError,
    TransformError,
    TransformJob,
    TransformOperation,
    TransformState,
    cancel_transform,
    clear_store,
    complete_transform,
    fail_transform,
    get_job,
    retry_transform,
    start_execution,
    submit_transform,
    update_progress,
    validate_source,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_store()
    yield
    clear_store()


def _valid_source(org_id: str = "org-123", **overrides) -> SourceAsset:
    defaults = {
        "asset_id": "asset-src-1",
        "org_id": org_id,
        "storage_key": "/org-123/images/_/job-1/photo.jpg",
        "checksum": "sha256abc",
        "mime_type": "image/jpeg",
        "size_bytes": 500_000,
        "is_finalized": True,
    }
    defaults.update(overrides)
    return SourceAsset(**defaults)


def _submit(**overrides) -> TransformJob:
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "source": _valid_source(),
        "operation": TransformOperation.UPSCALE,
        "scale_factor": 2.0,
        "cost_estimated_usd": 0.03,
    }
    defaults.update(overrides)
    return submit_transform(**defaults)


# =============================================================================
# Source Validation
# =============================================================================


class TestSourceValidation:

    @pytest.mark.unit
    def test_valid_source_passes(self):
        """Valid finalized source from same org passes."""
        source = _valid_source()
        validate_source(source, "org-123")  # No exception

    @pytest.mark.unit
    def test_cross_tenant_source_denied(self):
        """Source from different org is denied."""
        source = _valid_source(org_id="org-other")
        with pytest.raises(SourceValidationError) as exc_info:
            validate_source(source, "org-123")
        assert exc_info.value.code == "CROSS_TENANT"

    @pytest.mark.unit
    def test_unfinalized_source_denied(self):
        """Source without confirmed storage is denied."""
        source = _valid_source(is_finalized=False)
        with pytest.raises(SourceValidationError) as exc_info:
            validate_source(source, "org-123")
        assert exc_info.value.code == "NOT_FINALIZED"

    @pytest.mark.unit
    def test_missing_storage_key_denied(self):
        """Source without storage_key is denied."""
        source = _valid_source(storage_key="")
        with pytest.raises(SourceValidationError) as exc_info:
            validate_source(source, "org-123")
        assert exc_info.value.code == "NO_STORAGE"

    @pytest.mark.unit
    def test_unsupported_mime_denied(self):
        """Non-image MIME type is denied."""
        source = _valid_source(mime_type="application/pdf")
        with pytest.raises(SourceValidationError) as exc_info:
            validate_source(source, "org-123")
        assert exc_info.value.code == "UNSUPPORTED_MIME"

    @pytest.mark.unit
    def test_missing_asset_id_denied(self):
        """Empty asset_id is denied."""
        source = _valid_source(asset_id="")
        with pytest.raises(SourceValidationError):
            validate_source(source, "org-123")

    @pytest.mark.unit
    def test_webp_source_accepted(self):
        """WebP source is accepted."""
        source = _valid_source(mime_type="image/webp")
        validate_source(source, "org-123")

    @pytest.mark.unit
    def test_png_source_accepted(self):
        """PNG source is accepted."""
        source = _valid_source(mime_type="image/png")
        validate_source(source, "org-123")


# =============================================================================
# Durable Lifecycle
# =============================================================================


class TestLifecycle:

    @pytest.mark.unit
    def test_submit_creates_job(self):
        """Submission creates a durable job in SOURCE_VERIFIED state."""
        job = _submit()
        assert job.state == TransformState.SOURCE_VERIFIED
        assert job.spec is not None
        assert job.spec.operation == TransformOperation.UPSCALE

    @pytest.mark.unit
    def test_start_execution(self):
        """Start moves to EXECUTING state."""
        job = _submit()
        start_execution(job.job_id)
        assert job.state == TransformState.EXECUTING
        assert job.started_at is not None

    @pytest.mark.unit
    def test_complete_with_output(self):
        """Completion with valid output sets COMPLETED."""
        job = _submit()
        start_execution(job.job_id)
        complete_transform(
            job.job_id,
            output_asset_id="out-1",
            output_storage_key="/org-123/edited/out.webp",
            output_checksum="hashxyz",
            output_size_bytes=300_000,
            cost_actual_usd=0.02,
        )
        assert job.state == TransformState.COMPLETED
        assert job.output_asset_id == "out-1"
        assert job.completed_at is not None

    @pytest.mark.unit
    def test_job_survives_retrieval(self):
        """Job can be retrieved by ID (survives browser refresh)."""
        job = _submit()
        retrieved = get_job(job.job_id)
        assert retrieved is not None
        assert retrieved.job_id == job.job_id

    @pytest.mark.unit
    def test_spec_hash_computed(self):
        """Spec hash is computed at submission."""
        job = _submit()
        assert job.spec_hash != ""
        assert len(job.spec_hash) == 20

    @pytest.mark.unit
    def test_spec_immutable_after_submit(self):
        """Spec is set at submission and doesn't change."""
        job = _submit(scale_factor=4.0)
        assert job.spec.scale_factor == 4.0


# =============================================================================
# Output Requirement
# =============================================================================


class TestOutputRequirement:

    @pytest.mark.unit
    def test_complete_without_asset_id_fails(self):
        """Completion without output_asset_id raises error."""
        job = _submit()
        start_execution(job.job_id)
        with pytest.raises(TransformError) as exc_info:
            complete_transform(job.job_id, output_asset_id="", output_storage_key="/k", output_checksum="h")
        assert exc_info.value.code == "NO_OUTPUT"

    @pytest.mark.unit
    def test_complete_without_storage_key_fails(self):
        """Completion without storage_key raises error."""
        job = _submit()
        start_execution(job.job_id)
        with pytest.raises(TransformError) as exc_info:
            complete_transform(job.job_id, output_asset_id="a", output_storage_key="", output_checksum="h")
        assert exc_info.value.code == "NO_STORAGE"

    @pytest.mark.unit
    def test_complete_without_checksum_fails(self):
        """Completion without checksum raises error."""
        job = _submit()
        start_execution(job.job_id)
        with pytest.raises(TransformError) as exc_info:
            complete_transform(job.job_id, output_asset_id="a", output_storage_key="/k", output_checksum="")
        assert exc_info.value.code == "NO_CHECKSUM"

    @pytest.mark.unit
    def test_complete_idempotent(self):
        """Completing already-completed job returns it unchanged."""
        job = _submit()
        start_execution(job.job_id)
        complete_transform(job.job_id, output_asset_id="a", output_storage_key="/k", output_checksum="h")
        # Second call — idempotent
        result = complete_transform(job.job_id, output_asset_id="b", output_storage_key="/k2", output_checksum="h2")
        assert result.output_asset_id == "a"  # Original preserved


# =============================================================================
# Cancellation
# =============================================================================


class TestCancellation:

    @pytest.mark.unit
    def test_cancel_before_execution(self):
        """Can cancel before execution starts."""
        job = _submit()
        cancel_transform(job.job_id)
        assert job.state == TransformState.CANCELLED

    @pytest.mark.unit
    def test_cancel_during_execution_blocked(self):
        """Cannot cancel once executing."""
        job = _submit()
        start_execution(job.job_id)
        cancel_transform(job.job_id)
        assert job.state == TransformState.EXECUTING  # Unchanged

    @pytest.mark.unit
    def test_cancel_completed_noop(self):
        """Cancelling completed job is a no-op."""
        job = _submit()
        start_execution(job.job_id)
        complete_transform(job.job_id, output_asset_id="a", output_storage_key="/k", output_checksum="h")
        cancel_transform(job.job_id)
        assert job.state == TransformState.COMPLETED

    @pytest.mark.unit
    def test_cancel_idempotent(self):
        """Cancelling already-cancelled job is a no-op."""
        job = _submit()
        cancel_transform(job.job_id)
        cancel_transform(job.job_id)  # No error
        assert job.state == TransformState.CANCELLED


# =============================================================================
# Retry
# =============================================================================


class TestRetry:

    @pytest.mark.unit
    def test_retry_failed_job(self):
        """Failed job can be retried."""
        job = _submit()
        start_execution(job.job_id)
        fail_transform(job.job_id, error="Provider timeout")
        retry_transform(job.job_id)
        assert job.state == TransformState.SOURCE_VERIFIED
        assert job.attempt == 2
        assert job.error_message is None

    @pytest.mark.unit
    def test_retry_exhausted(self):
        """Cannot retry beyond max attempts."""
        job = _submit()
        job.attempt = 3
        job.max_attempts = 3
        job.state = TransformState.FAILED
        retry_transform(job.job_id)
        assert job.state == TransformState.FAILED  # Unchanged

    @pytest.mark.unit
    def test_retry_completed_noop(self):
        """Cannot retry completed job."""
        job = _submit()
        start_execution(job.job_id)
        complete_transform(job.job_id, output_asset_id="a", output_storage_key="/k", output_checksum="h")
        retry_transform(job.job_id)
        assert job.state == TransformState.COMPLETED

    @pytest.mark.unit
    def test_failure_records_error(self):
        """Failure records the error message."""
        job = _submit()
        start_execution(job.job_id)
        fail_transform(job.job_id, error="GPU OOM")
        assert job.error_message == "GPU OOM"
        assert job.state == TransformState.FAILED


# =============================================================================
# Cross-Tenant Denial
# =============================================================================


class TestCrossTenant:

    @pytest.mark.unit
    def test_submit_with_cross_tenant_source_denied(self):
        """Cannot submit transform with source from different org."""
        source = _valid_source(org_id="org-evil")
        with pytest.raises(SourceValidationError) as exc_info:
            submit_transform(
                org_id="org-123", user_id="user-1",
                source=source, operation=TransformOperation.UPSCALE,
            )
        assert exc_info.value.code == "CROSS_TENANT"

    @pytest.mark.unit
    def test_same_org_source_allowed(self):
        """Source from same org passes."""
        source = _valid_source(org_id="org-123")
        job = submit_transform(
            org_id="org-123", user_id="user-1",
            source=source, operation=TransformOperation.ENHANCE,
        )
        assert job.state == TransformState.SOURCE_VERIFIED


# =============================================================================
# Idempotency
# =============================================================================


class TestIdempotency:

    @pytest.mark.unit
    def test_duplicate_key_returns_existing(self):
        """Same idempotency_key returns existing job."""
        job1 = _submit(idempotency_key="idem-001")
        job2 = _submit(idempotency_key="idem-001")
        assert job1.job_id == job2.job_id

    @pytest.mark.unit
    def test_different_keys_create_separate(self):
        """Different keys create separate jobs."""
        j1 = _submit(idempotency_key="key-A")
        j2 = _submit(idempotency_key="key-B")
        assert j1.job_id != j2.job_id

    @pytest.mark.unit
    def test_no_key_always_creates(self):
        """No key always creates new job."""
        j1 = _submit(idempotency_key="")
        j2 = _submit(idempotency_key="")
        assert j1.job_id != j2.job_id


# =============================================================================
# Progress & Serialization
# =============================================================================


class TestProgressAndSerialization:

    @pytest.mark.unit
    def test_progress_update(self):
        """Progress updates during execution."""
        job = _submit()
        start_execution(job.job_id)
        update_progress(job.job_id, 50.0)
        assert job.progress_pct == 50.0

    @pytest.mark.unit
    def test_progress_clamped(self):
        """Progress clamped to 0-100."""
        job = _submit()
        start_execution(job.job_id)
        update_progress(job.job_id, 150.0)
        assert job.progress_pct == 100.0

    @pytest.mark.unit
    def test_job_serializable(self):
        """TransformJob.to_dict() is JSON-serializable."""
        import json
        job = _submit()
        json.dumps(job.to_dict())

    @pytest.mark.unit
    def test_spec_serializable(self):
        """TransformSpec.to_dict() is JSON-serializable."""
        import json
        job = _submit()
        json.dumps(job.spec.to_dict())
