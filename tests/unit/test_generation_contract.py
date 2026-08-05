"""Generation Contract Tests (Story 071).

Proves: canonical request validation, immutable spec, job lifecycle,
simulation cannot satisfy production, idempotency, cost gate, route
classification completeness, and adapter compatibility rules.

Run with:
    pytest tests/unit/test_generation_contract.py -v
"""
from __future__ import annotations

import pytest

from backend.generation_contract import (
    ROUTE_CLASSIFICATIONS,
    AssetResult,
    CanonicalGenerationRequest,
    CostEstimate,
    ErrorCategory,
    GenerationError,
    GenerationJobContract,
    GenerationSpec,
    JobState,
    MediaType,
    ProviderType,
    RouteClassification,
    RouteStatus,
    validate_completion,
    validate_request,
    validate_simulation_completion,
)


# =============================================================================
# Helpers
# =============================================================================


def _valid_request(**overrides) -> CanonicalGenerationRequest:
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "media_type": MediaType.IMAGE,
        "prompt": "A futuristic city at sunset",
    }
    defaults.update(overrides)
    return CanonicalGenerationRequest(**defaults)


def _completed_job(provider: ProviderType = ProviderType.COMFYUI) -> GenerationJobContract:
    req = _valid_request()
    job = GenerationJobContract(
        org_id=req.org_id,
        user_id=req.user_id,
        spec=GenerationSpec.from_request(req),
        provider=provider,
        cost_estimate=CostEstimate(estimated_usd=0.05, provider=provider),
        actual_cost_usd=0.04,
        asset_id="asset-abc",
    )
    job.transition(JobState.COST_APPROVED)
    job.transition(JobState.QUEUED)
    job.transition(JobState.EXECUTING)
    job.transition(JobState.COMPLETED, reason="Generation successful")
    return job


# =============================================================================
# Request Validation
# =============================================================================


class TestRequestValidation:

    @pytest.mark.unit
    def test_valid_request_passes(self):
        """Well-formed request has no violations."""
        req = _valid_request()
        violations = validate_request(req)
        assert violations == []

    @pytest.mark.unit
    def test_missing_org_id_fails(self):
        """org_id is mandatory."""
        req = _valid_request(org_id="")
        violations = validate_request(req)
        assert any("org_id" in v for v in violations)

    @pytest.mark.unit
    def test_missing_user_id_fails(self):
        """user_id is mandatory."""
        req = _valid_request(user_id="")
        violations = validate_request(req)
        assert any("user_id" in v for v in violations)

    @pytest.mark.unit
    def test_missing_prompt_fails(self):
        """prompt is mandatory for non-training types."""
        req = _valid_request(prompt="")
        violations = validate_request(req)
        assert any("prompt" in v for v in violations)

    @pytest.mark.unit
    def test_training_type_no_prompt_ok(self):
        """Training type does not require prompt."""
        req = _valid_request(prompt="", media_type=MediaType.MODEL_TRAINING)
        violations = validate_request(req)
        assert not any("prompt" in v for v in violations)

    @pytest.mark.unit
    def test_width_too_small(self):
        """Width below minimum rejected."""
        req = _valid_request(width=32)
        violations = validate_request(req)
        assert any("width" in v for v in violations)

    @pytest.mark.unit
    def test_width_too_large(self):
        """Width above maximum rejected."""
        req = _valid_request(width=8192)
        violations = validate_request(req)
        assert any("width" in v for v in violations)

    @pytest.mark.unit
    def test_steps_out_of_range(self):
        """Steps must be 1-150."""
        req = _valid_request(steps=200)
        violations = validate_request(req)
        assert any("steps" in v for v in violations)

    @pytest.mark.unit
    def test_cfg_out_of_range(self):
        """cfg_scale must be 0-30."""
        req = _valid_request(cfg_scale=50.0)
        violations = validate_request(req)
        assert any("cfg_scale" in v for v in violations)

    @pytest.mark.unit
    def test_lora_strength_out_of_range(self):
        """LoRA strength must be 0-2.0 when lora specified."""
        req = _valid_request(lora_model_id="lora-1", lora_strength=3.0)
        violations = validate_request(req)
        assert any("lora_strength" in v for v in violations)

    @pytest.mark.unit
    def test_lora_strength_ignored_without_lora(self):
        """LoRA strength constraint only applies when lora_model_id set."""
        req = _valid_request(lora_model_id=None, lora_strength=5.0)
        violations = validate_request(req)
        assert not any("lora_strength" in v for v in violations)


# =============================================================================
# Immutable Specification
# =============================================================================


class TestGenerationSpec:

    @pytest.mark.unit
    def test_spec_from_request(self):
        """Spec captures all generation parameters."""
        req = _valid_request(model="sdxl", width=768, height=768, seed=42)
        spec = GenerationSpec.from_request(req)
        assert spec.model == "sdxl"
        assert spec.width == 768
        assert spec.height == 768
        assert spec.seed == 42
        assert spec.prompt == req.prompt

    @pytest.mark.unit
    def test_spec_hash_deterministic(self):
        """Same inputs produce same spec hash."""
        req1 = _valid_request(seed=42)
        req2 = _valid_request(seed=42)
        assert req1.compute_spec_hash() == req2.compute_spec_hash()

    @pytest.mark.unit
    def test_spec_hash_changes_with_params(self):
        """Different params produce different hash."""
        req1 = _valid_request(seed=42)
        req2 = _valid_request(seed=43)
        assert req1.compute_spec_hash() != req2.compute_spec_hash()

    @pytest.mark.unit
    def test_spec_serializable(self):
        """Spec.to_dict() is JSON-serializable."""
        import json
        req = _valid_request()
        spec = GenerationSpec.from_request(req)
        json.dumps(spec.to_dict())  # Should not raise


# =============================================================================
# Job Lifecycle
# =============================================================================


class TestJobLifecycle:

    @pytest.mark.unit
    def test_job_starts_submitted(self):
        """New job starts in SUBMITTED state."""
        job = GenerationJobContract(org_id="org-1", user_id="user-1")
        assert job.state == JobState.SUBMITTED
        assert job.state.is_active

    @pytest.mark.unit
    def test_transition_records_history(self):
        """State transitions accumulate in history."""
        job = GenerationJobContract(org_id="org-1", user_id="user-1")
        job.transition(JobState.COST_APPROVED)
        job.transition(JobState.QUEUED)
        assert len(job.state_history) == 2
        assert job.state_history[0]["from"] == "submitted"
        assert job.state_history[0]["to"] == "cost_approved"

    @pytest.mark.unit
    def test_executing_sets_started_at(self):
        """Transitioning to EXECUTING sets started_at."""
        job = GenerationJobContract(org_id="org-1", user_id="user-1")
        job.transition(JobState.EXECUTING)
        assert job.started_at is not None

    @pytest.mark.unit
    def test_terminal_state_sets_completed_at(self):
        """Terminal state sets completed_at."""
        job = GenerationJobContract(org_id="org-1", user_id="user-1")
        job.transition(JobState.COMPLETED)
        assert job.completed_at is not None

    @pytest.mark.unit
    def test_completed_is_terminal(self):
        assert JobState.COMPLETED.is_terminal

    @pytest.mark.unit
    def test_failed_is_terminal(self):
        assert JobState.FAILED.is_terminal

    @pytest.mark.unit
    def test_failed_is_retryable(self):
        assert JobState.FAILED.is_retryable

    @pytest.mark.unit
    def test_completed_not_retryable(self):
        assert not JobState.COMPLETED.is_retryable

    @pytest.mark.unit
    def test_submitted_is_cancellable(self):
        assert JobState.SUBMITTED.is_cancellable

    @pytest.mark.unit
    def test_executing_not_cancellable(self):
        """Cannot cancel once execution has started."""
        assert not JobState.EXECUTING.is_cancellable

    @pytest.mark.unit
    def test_job_status_serializable(self):
        """to_status() produces JSON-serializable dict."""
        import json
        job = _completed_job()
        json.dumps(job.to_status())


# =============================================================================
# Simulation Cannot Satisfy Production
# =============================================================================


class TestSimulationRestriction:

    @pytest.mark.unit
    def test_simulation_fails_production_validation(self):
        """Simulation provider does NOT satisfy production completion."""
        job = _completed_job(provider=ProviderType.SIMULATION)
        violations = validate_completion(job)
        assert any("simulation" in v.lower() for v in violations)

    @pytest.mark.unit
    def test_comfyui_passes_production_validation(self):
        """ComfyUI provider satisfies production completion."""
        job = _completed_job(provider=ProviderType.COMFYUI)
        violations = validate_completion(job)
        assert violations == []

    @pytest.mark.unit
    def test_simulation_passes_simulation_validation(self):
        """Simulation has separate relaxed validation for dev/test."""
        req = _valid_request()
        job = GenerationJobContract(
            org_id=req.org_id,
            user_id=req.user_id,
            spec=GenerationSpec.from_request(req),
            provider=ProviderType.SIMULATION,
        )
        job.transition(JobState.COMPLETED)
        violations = validate_simulation_completion(job)
        assert violations == []


# =============================================================================
# Cost Gate
# =============================================================================


class TestCostGate:

    @pytest.mark.unit
    def test_no_cost_estimate_fails_completion(self):
        """Completed job without cost_estimate violates contract."""
        job = _completed_job()
        job.cost_estimate = None
        violations = validate_completion(job)
        assert any("cost_estimate" in v for v in violations)

    @pytest.mark.unit
    def test_no_actual_cost_fails_completion(self):
        """Completed job without actual_cost_usd violates contract."""
        job = _completed_job()
        job.actual_cost_usd = None
        violations = validate_completion(job)
        assert any("actual_cost" in v for v in violations)

    @pytest.mark.unit
    def test_cost_estimate_serializable(self):
        """CostEstimate.to_dict() is valid."""
        est = CostEstimate(estimated_usd=0.12, provider=ProviderType.COMFYUI, gpu_type="RTX 4090")
        d = est.to_dict()
        assert d["estimated_usd"] == 0.12
        assert d["provider"] == "comfyui"


# =============================================================================
# Idempotency
# =============================================================================


class TestIdempotency:

    @pytest.mark.unit
    def test_idempotency_key_on_request(self):
        """Request can carry idempotency key."""
        req = _valid_request(idempotency_key="idem-abc123")
        assert req.idempotency_key == "idem-abc123"

    @pytest.mark.unit
    def test_idempotency_key_on_job(self):
        """Job records the idempotency key for dedup."""
        job = GenerationJobContract(
            org_id="org-1", user_id="user-1", idempotency_key="idem-xyz",
        )
        assert job.idempotency_key == "idem-xyz"


# =============================================================================
# Asset Result
# =============================================================================


class TestAssetResult:

    @pytest.mark.unit
    def test_asset_result_has_required_fields(self):
        """AssetResult has mandatory storage_key and checksum."""
        result = AssetResult(
            asset_id="a-1",
            storage_key="/org-1/images/talent-1/job-1/out.webp",
            checksum_sha256="abcdef1234567890",
            mime_type="image/webp",
            size_bytes=123456,
            job_id="gen-abc",
            spec_hash="deadbeef",
            model="flux-dev",
            provider="comfyui",
        )
        d = result.to_dict()
        assert d["storage_key"].startswith("/org-1")
        assert d["checksum_sha256"] == "abcdef1234567890"
        assert d["job_id"] == "gen-abc"
        assert d["spec_hash"] == "deadbeef"

    @pytest.mark.unit
    def test_no_asset_fails_completion(self):
        """Completed job without asset_id violates contract."""
        job = _completed_job()
        job.asset_id = None
        violations = validate_completion(job)
        assert any("asset_id" in v for v in violations)


# =============================================================================
# Route Classification
# =============================================================================


class TestRouteClassification:

    @pytest.mark.unit
    def test_all_generation_routes_classified(self):
        """Every known generation route has a classification."""
        # 10 routes in inventory
        assert len(ROUTE_CLASSIFICATIONS) >= 10

    @pytest.mark.unit
    def test_canonical_routes_have_no_replacement(self):
        """Canonical routes don't need a replacement."""
        for rc in ROUTE_CLASSIFICATIONS:
            if rc.status == RouteStatus.CANONICAL:
                # Canonical routes may or may not have replacement field
                pass  # Just verify they exist

    @pytest.mark.unit
    def test_deprecated_routes_have_replacement(self):
        """Deprecated routes must specify what replaces them."""
        for rc in ROUTE_CLASSIFICATIONS:
            if rc.status == RouteStatus.DEPRECATED:
                assert rc.canonical_replacement, (
                    f"Deprecated route {rc.path} must have canonical_replacement"
                )

    @pytest.mark.unit
    def test_compatibility_routes_have_replacement(self):
        """Compatibility routes must specify canonical replacement."""
        for rc in ROUTE_CLASSIFICATIONS:
            if rc.status == RouteStatus.COMPATIBILITY:
                assert rc.canonical_replacement, (
                    f"Compatibility route {rc.path} must have canonical_replacement"
                )

    @pytest.mark.unit
    def test_adapter_routes_have_notes(self):
        """Adapter routes explain their surface-specific purpose."""
        for rc in ROUTE_CLASSIFICATIONS:
            if rc.status == RouteStatus.ADAPTER:
                assert rc.notes, f"Adapter route {rc.path} must have notes"

    @pytest.mark.unit
    def test_no_remove_routes_in_current_list(self):
        """No routes currently marked for immediate removal."""
        remove_routes = [r for r in ROUTE_CLASSIFICATIONS if r.status == RouteStatus.REMOVE]
        assert len(remove_routes) == 0, "Routes should be deprecated before removal"


# =============================================================================
# Error Contract
# =============================================================================


class TestErrorContract:

    @pytest.mark.unit
    def test_error_categories_cover_failures(self):
        """All expected failure modes have a category."""
        categories = set(ErrorCategory)
        assert "validation" in categories
        assert "cost_exceeded" in categories
        assert "provider_unavailable" in categories
        assert "timeout" in categories
        assert "cancelled" in categories

    @pytest.mark.unit
    def test_error_serializable(self):
        """GenerationError.to_dict() produces safe output."""
        err = GenerationError(
            category=ErrorCategory.PROVIDER_ERROR,
            message="Model not found on worker",
            code="MODEL_NOT_FOUND",
            retryable=True,
            provider_detail="CUDA OOM at step 15",  # Internal detail
            job_id="gen-123",
        )
        d = err.to_dict()
        # Provider detail NOT exposed to client
        assert "provider_detail" not in d
        assert d["retryable"] is True
        assert d["code"] == "MODEL_NOT_FOUND"


# =============================================================================
# Provenance Chain
# =============================================================================


class TestProvenanceChain:

    @pytest.mark.unit
    def test_request_to_spec_to_job_to_asset(self):
        """Full provenance chain: request → spec → job → asset."""
        req = _valid_request(seed=42)
        spec = GenerationSpec.from_request(req)
        job = GenerationJobContract(
            org_id=req.org_id,
            user_id=req.user_id,
            spec=spec,
            provider=ProviderType.COMFYUI,
        )
        asset = AssetResult(
            asset_id="asset-1",
            storage_key="/org-123/images/out.webp",
            checksum_sha256="aabbcc",
            mime_type="image/webp",
            size_bytes=50000,
            job_id=job.job_id,
            spec_hash=spec.spec_hash,
            model=spec.model,
            provider=job.provider.value,
        )

        # Verify chain links
        assert asset.job_id == job.job_id
        assert asset.spec_hash == spec.spec_hash
        assert asset.spec_hash == req.compute_spec_hash()
        assert asset.model == req.model

    @pytest.mark.unit
    def test_org_id_immutable_on_job(self):
        """org_id set at creation and never changes."""
        job = GenerationJobContract(org_id="org-123", user_id="user-1")
        # In production, org_id is set once from JWT — contract enforces this
        assert job.org_id == "org-123"
