"""Video Assembly & Export Tests (Story 077).

Proves: completion requires persisted asset, simulation distinct from production,
duplicate callbacks idempotent, cancel races, partial failures recoverable,
source verification, and signed URL handling.

Run with:
    pytest tests/unit/test_video_assembly.py -v
"""
from __future__ import annotations

import pytest

from backend.video_assembly import (
    AssemblyJob,
    AssemblyOutput,
    AssemblyState,
    AssemblyType,
    CompletionError,
    SourceAssetRef,
    SourceVerificationError,
    cancel_assembly,
    fail_assembly,
    finalize_assembly,
    generate_signed_url,
    refresh_signed_url,
    retry_assembly,
    update_progress,
    validate_completion,
    verify_sources,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_job(
    is_simulation: bool = False,
    state: AssemblyState = AssemblyState.SUBMITTED,
    **kwargs,
) -> AssemblyJob:
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "assembly_type": AssemblyType.VIDEO_ASSEMBLY,
    }
    defaults.update(kwargs)
    job = AssemblyJob(**defaults)
    job.is_simulation = is_simulation
    job.state = state
    return job


def _valid_output() -> AssemblyOutput:
    return AssemblyOutput(
        asset_id="asset-out-1",
        storage_key="/org-123/videos/_/asm-abc/final.mp4",
        checksum_sha256="abcdef123456",
        mime_type="video/mp4",
        size_bytes=5_000_000,
        duration_seconds=30.0,
        width=1920,
        height=1080,
        signed_url="https://cdn.ai-studio.app/org-123/videos/final.mp4?token=xyz",
        signed_url_expires_at="2027-01-01T01:00:00Z",
    )


# =============================================================================
# Completion Requires Asset
# =============================================================================


class TestCompletionRequiresAsset:

    @pytest.mark.unit
    def test_valid_output_completes(self):
        """Job with valid output can be completed."""
        job = _make_job(state=AssemblyState.UPLOADING)
        output = _valid_output()
        result = finalize_assembly(job, output=output)
        assert result.state == AssemblyState.COMPLETED
        assert result.output is not None
        assert result.output.asset_id == "asset-out-1"

    @pytest.mark.unit
    def test_no_output_fails_completion(self):
        """Job without output cannot be completed."""
        job = _make_job(state=AssemblyState.UPLOADING)
        output = AssemblyOutput()  # Empty output
        with pytest.raises(CompletionError) as exc_info:
            finalize_assembly(job, output=output)
        assert "asset_id" in exc_info.value.message

    @pytest.mark.unit
    def test_missing_storage_key_fails(self):
        """Output without storage_key fails validation."""
        job = _make_job(state=AssemblyState.UPLOADING)
        output = _valid_output()
        output.storage_key = ""
        with pytest.raises(CompletionError):
            finalize_assembly(job, output=output)

    @pytest.mark.unit
    def test_missing_checksum_fails(self):
        """Output without checksum fails validation."""
        job = _make_job(state=AssemblyState.UPLOADING)
        output = _valid_output()
        output.checksum_sha256 = ""
        with pytest.raises(CompletionError):
            finalize_assembly(job, output=output)

    @pytest.mark.unit
    def test_zero_size_fails(self):
        """Output with zero bytes fails validation."""
        job = _make_job(state=AssemblyState.UPLOADING)
        output = _valid_output()
        output.size_bytes = 0
        with pytest.raises(CompletionError):
            finalize_assembly(job, output=output)

    @pytest.mark.unit
    def test_missing_signed_url_fails(self):
        """Output without signed URL fails validation."""
        job = _make_job(state=AssemblyState.UPLOADING)
        output = _valid_output()
        output.signed_url = None
        with pytest.raises(CompletionError):
            finalize_assembly(job, output=output)

    @pytest.mark.unit
    def test_completed_sets_timestamp(self):
        """Completion sets completed_at."""
        job = _make_job(state=AssemblyState.UPLOADING)
        finalize_assembly(job, output=_valid_output())
        assert job.completed_at is not None


# =============================================================================
# Simulation Distinct
# =============================================================================


class TestSimulationDistinct:

    @pytest.mark.unit
    def test_simulation_gets_simulation_done(self):
        """Simulation job gets SIMULATION_DONE, not COMPLETED."""
        job = _make_job(is_simulation=True, state=AssemblyState.UPLOADING)
        output = _valid_output()
        result = finalize_assembly(job, output=output)
        assert result.state == AssemblyState.SIMULATION_DONE
        assert result.state != AssemblyState.COMPLETED

    @pytest.mark.unit
    def test_simulation_not_production_complete(self):
        """SIMULATION_DONE is not production-complete."""
        assert not AssemblyState.SIMULATION_DONE.is_production_complete

    @pytest.mark.unit
    def test_production_is_production_complete(self):
        """Only COMPLETED is production-complete."""
        assert AssemblyState.COMPLETED.is_production_complete

    @pytest.mark.unit
    def test_validate_completion_rejects_simulation(self):
        """validate_completion explicitly rejects simulation."""
        job = _make_job(is_simulation=True)
        job.output = _valid_output()
        violations = validate_completion(job)
        assert any("simulation" in v.lower() for v in violations)

    @pytest.mark.unit
    def test_simulation_with_incomplete_output_still_finishes(self):
        """Simulation with minimal output gets SIMULATION_DONE (relaxed)."""
        job = _make_job(is_simulation=True, state=AssemblyState.UPLOADING)
        # Even with incomplete output, simulation can finish
        output = AssemblyOutput(asset_id="sim-1", storage_key="/sim")
        result = finalize_assembly(job, output=output)
        assert result.state == AssemblyState.SIMULATION_DONE


# =============================================================================
# Duplicate Callbacks (Idempotent)
# =============================================================================


class TestDuplicateCallbacks:

    @pytest.mark.unit
    def test_duplicate_finalize_is_noop(self):
        """Second finalize on completed job returns without change."""
        job = _make_job(state=AssemblyState.UPLOADING)
        output1 = _valid_output()
        finalize_assembly(job, output=output1)
        assert job.state == AssemblyState.COMPLETED

        # Second callback with different output — should be ignored
        output2 = _valid_output()
        output2.asset_id = "different-asset"
        finalize_assembly(job, output=output2)
        # Original output preserved
        assert job.output.asset_id == "asset-out-1"

    @pytest.mark.unit
    def test_duplicate_simulation_finalize_is_noop(self):
        """Second finalize on simulation-done job is idempotent."""
        job = _make_job(is_simulation=True, state=AssemblyState.UPLOADING)
        finalize_assembly(job, output=_valid_output())
        assert job.state == AssemblyState.SIMULATION_DONE

        finalize_assembly(job, output=AssemblyOutput(asset_id="other"))
        assert job.output.asset_id == "asset-out-1"  # Unchanged


# =============================================================================
# Cancel Races
# =============================================================================


class TestCancelRaces:

    @pytest.mark.unit
    def test_cancel_from_submitted(self):
        """Can cancel from SUBMITTED state."""
        job = _make_job(state=AssemblyState.SUBMITTED)
        cancel_assembly(job, reason="Changed my mind")
        assert job.state == AssemblyState.CANCELLED

    @pytest.mark.unit
    def test_cancel_from_queued(self):
        """Can cancel from QUEUED state."""
        job = _make_job(state=AssemblyState.QUEUED)
        cancel_assembly(job, reason="No longer needed")
        assert job.state == AssemblyState.CANCELLED

    @pytest.mark.unit
    def test_cannot_cancel_during_execution(self):
        """Cannot cancel once EXECUTING (partial state recoverable)."""
        job = _make_job(state=AssemblyState.EXECUTING)
        cancel_assembly(job, reason="Try to cancel")
        assert job.state == AssemblyState.EXECUTING  # Unchanged

    @pytest.mark.unit
    def test_cancel_on_completed_is_noop(self):
        """Cancel on already-completed job is a no-op."""
        job = _make_job(state=AssemblyState.COMPLETED)
        cancel_assembly(job, reason="Too late")
        assert job.state == AssemblyState.COMPLETED

    @pytest.mark.unit
    def test_cancel_sets_timestamp(self):
        """Cancel sets completed_at."""
        job = _make_job(state=AssemblyState.SUBMITTED)
        cancel_assembly(job)
        assert job.completed_at is not None


# =============================================================================
# Partial Failures
# =============================================================================


class TestPartialFailures:

    @pytest.mark.unit
    def test_fail_records_error(self):
        """Failure records error message."""
        job = _make_job(state=AssemblyState.EXECUTING)
        fail_assembly(job, error="Provider timeout after 300s")
        assert job.state == AssemblyState.FAILED
        assert job.error_message == "Provider timeout after 300s"
        assert job.last_error_at is not None

    @pytest.mark.unit
    def test_retry_after_failure(self):
        """Failed job can be retried."""
        job = _make_job(state=AssemblyState.EXECUTING)
        fail_assembly(job, error="Transient error")
        result = retry_assembly(job)
        assert result.state == AssemblyState.SUBMITTED
        assert result.attempt == 2
        assert result.error_message is None

    @pytest.mark.unit
    def test_retry_exhausted(self):
        """Job with max attempts exhausted cannot retry."""
        job = _make_job(state=AssemblyState.FAILED)
        job.attempt = 3
        job.max_attempts = 3
        result = retry_assembly(job)
        assert result.state == AssemblyState.FAILED  # Unchanged

    @pytest.mark.unit
    def test_fail_on_terminal_is_noop(self):
        """Cannot fail an already-terminal job."""
        job = _make_job(state=AssemblyState.COMPLETED)
        fail_assembly(job, error="Late error")
        assert job.state == AssemblyState.COMPLETED
        assert job.error_message is None

    @pytest.mark.unit
    def test_retry_only_from_failed(self):
        """Can only retry from FAILED state."""
        job = _make_job(state=AssemblyState.EXECUTING)
        result = retry_assembly(job)
        assert result.state == AssemblyState.EXECUTING  # Unchanged


# =============================================================================
# Source Verification
# =============================================================================


class TestSourceVerification:

    @pytest.mark.unit
    def test_all_sources_present_passes(self):
        """All sources found transitions to SOURCES_VERIFIED."""
        job = _make_job()
        job.source_assets = [
            SourceAssetRef(asset_id="a-1", role="shot", sequence_order=0),
            SourceAssetRef(asset_id="a-2", role="shot", sequence_order=1),
        ]
        available = {"a-1", "a-2", "a-3"}
        verify_sources(job, available)
        assert job.state == AssemblyState.SOURCES_VERIFIED
        assert job.all_sources_verified is True
        assert all(ref.verified for ref in job.source_assets)

    @pytest.mark.unit
    def test_missing_source_raises(self):
        """Missing source asset raises SourceVerificationError."""
        job = _make_job()
        job.source_assets = [
            SourceAssetRef(asset_id="a-1"),
            SourceAssetRef(asset_id="a-missing"),
        ]
        available = {"a-1"}
        with pytest.raises(SourceVerificationError) as exc_info:
            verify_sources(job, available)
        assert "a-missing" in exc_info.value.missing_assets

    @pytest.mark.unit
    def test_empty_sources_passes(self):
        """Job with no sources (e.g., export from single input) passes."""
        job = _make_job()
        job.source_assets = []
        verify_sources(job, set())
        assert job.state == AssemblyState.SOURCES_VERIFIED

    @pytest.mark.unit
    def test_verification_marks_individual_refs(self):
        """Each source ref gets individual verified status."""
        job = _make_job()
        job.source_assets = [
            SourceAssetRef(asset_id="a-1"),
            SourceAssetRef(asset_id="a-gone"),
        ]
        available = {"a-1"}
        with pytest.raises(SourceVerificationError):
            verify_sources(job, available)
        assert job.source_assets[0].verified is True
        assert job.source_assets[1].verified is False
        assert job.source_assets[1].verification_error is not None


# =============================================================================
# Signed URL
# =============================================================================


class TestSignedUrl:

    @pytest.mark.unit
    def test_generate_signed_url(self):
        """Signed URL is generated with token."""
        url, expires_at = generate_signed_url("/org-1/videos/out.mp4")
        assert "token=" in url
        assert "/org-1/videos/out.mp4" in url
        assert expires_at is not None

    @pytest.mark.unit
    def test_refresh_updates_url(self):
        """Refresh replaces the signed URL on output."""
        job = _make_job(state=AssemblyState.COMPLETED)
        job.output = _valid_output()
        old_url = job.output.signed_url

        refresh_signed_url(job)
        assert job.output.signed_url is not None
        assert job.output.signed_url != old_url

    @pytest.mark.unit
    def test_refresh_no_output_is_noop(self):
        """Refresh on job without output is a no-op."""
        job = _make_job(state=AssemblyState.SUBMITTED)
        refresh_signed_url(job)
        assert job.output is None


# =============================================================================
# Progress
# =============================================================================


class TestProgress:

    @pytest.mark.unit
    def test_update_progress(self):
        """Progress can be updated during execution."""
        job = _make_job(state=AssemblyState.EXECUTING)
        update_progress(job, 45.0)
        assert job.progress_pct == 45.0

    @pytest.mark.unit
    def test_progress_clamped(self):
        """Progress is clamped to 0-100."""
        job = _make_job(state=AssemblyState.EXECUTING)
        update_progress(job, 150.0)
        assert job.progress_pct == 100.0
        update_progress(job, -10.0)
        assert job.progress_pct == 0.0

    @pytest.mark.unit
    def test_progress_on_terminal_is_noop(self):
        """Cannot update progress on terminal job."""
        job = _make_job(state=AssemblyState.COMPLETED)
        job.progress_pct = 100.0
        update_progress(job, 50.0)
        assert job.progress_pct == 100.0  # Unchanged


# =============================================================================
# State Properties
# =============================================================================


class TestStateProperties:

    @pytest.mark.unit
    def test_terminal_states(self):
        """Terminal states are correctly identified."""
        assert AssemblyState.COMPLETED.is_terminal
        assert AssemblyState.FAILED.is_terminal
        assert AssemblyState.CANCELLED.is_terminal
        assert AssemblyState.SIMULATION_DONE.is_terminal
        assert not AssemblyState.EXECUTING.is_terminal

    @pytest.mark.unit
    def test_active_states(self):
        """Active states are correctly identified."""
        assert AssemblyState.SUBMITTED.is_active
        assert AssemblyState.EXECUTING.is_active
        assert AssemblyState.UPLOADING.is_active
        assert not AssemblyState.COMPLETED.is_active

    @pytest.mark.unit
    def test_job_serializable(self):
        """AssemblyJob.to_status() is JSON-serializable."""
        import json
        job = _make_job(state=AssemblyState.COMPLETED)
        job.output = _valid_output()
        json.dumps(job.to_status())
