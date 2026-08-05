"""Authoritative asset metadata tests — Story 074.

Tests prove:
  - Metadata derived from backend execution record (not caller)
  - UI-supplied values cannot overwrite execution fields
  - Random seed captured as actual value
  - Provider-normalized dimensions recorded
  - Enriched prompts preserved (not original UI text)
  - Recipe overrides tracked
  - Save is idempotent (same job → same metadata)
  - Retry attempts get distinct metadata
  - Stale browser state rejected
  - Cross-tenant denied
  - LoRA versions captured exactly
"""

import pytest

from backend.asset_metadata import (
    AssetMetadata,
    ExecutionRecord,
    ExecutionRecordNotFound,
    _reset_store,
    get_asset_metadata,
    register_execution_record,
    save_asset_metadata,
    validate_caller_metadata,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
JOB = "job-gen-001"
ASSET = "ast-output-001"


def _make_record(**overrides) -> ExecutionRecord:
    """Helper to create an execution record with defaults."""
    defaults = dict(
        job_id=JOB,
        org_id=ORG,
        effective_prompt="a futuristic cat in neon city, detailed, 8k",
        effective_negative_prompt="blurry, low quality",
        original_prompt="a cat in the city",
        enrichment_applied=True,
        model_id="flux_dev",
        model_version="1.0.0",
        actual_seed=8675309,
        actual_width=1024,
        actual_height=1024,
        actual_steps=25,
        actual_cfg=7.5,
        provider="vast.ai",
        gpu_type="RTX 4090",
        generation_time_seconds=12.5,
        actual_cost_usd=0.035,
        attempt_number=1,
    )
    defaults.update(overrides)
    return ExecutionRecord(**defaults)


# =============================================================================
# Backend Truth Enforcement
# =============================================================================


@pytest.mark.unit
class TestBackendTruth:

    def test_metadata_from_execution_record(self):
        record = _make_record()
        register_execution_record(record)
        meta = save_asset_metadata(JOB, ASSET, ORG)

        assert meta.effective_prompt == "a futuristic cat in neon city, detailed, 8k"
        assert meta.original_prompt == "a cat in the city"
        assert meta.enrichment_applied is True
        assert meta.model_id == "flux_dev"
        assert meta.model_version == "1.0.0"
        assert meta.actual_seed == 8675309
        assert meta.actual_width == 1024
        assert meta.actual_steps == 25
        assert meta.actual_cfg == 7.5
        assert meta.provider == "vast.ai"
        assert meta.actual_cost_usd == 0.035

    def test_ui_values_cannot_override_execution(self):
        """Caller sends stale UI state — backend truth wins."""
        record = _make_record(actual_seed=42, actual_width=1024, actual_height=1024)
        register_execution_record(record)

        # Caller sends different values (stale browser state)
        caller = {
            "seed": 99999,       # User had "random" selected — different from actual
            "width": 512,        # UI showed 512 but provider normalized to 1024
            "prompt": "original input",  # Pre-enrichment text
            "model": "sdxl",     # Wrong model
        }
        meta = save_asset_metadata(JOB, ASSET, ORG, caller_metadata=caller)

        # Backend truth wins
        assert meta.actual_seed == 42
        assert meta.actual_width == 1024
        assert meta.effective_prompt == "a futuristic cat in neon city, detailed, 8k"
        assert meta.model_id == "flux_dev"

    def test_missing_execution_record_raises(self):
        with pytest.raises(ExecutionRecordNotFound):
            save_asset_metadata("nonexistent-job", ASSET, ORG)


# =============================================================================
# Random Seeds
# =============================================================================


@pytest.mark.unit
class TestRandomSeeds:

    def test_random_seed_captured(self):
        """When user selects 'random', the actual seed is still recorded."""
        record = _make_record(actual_seed=123456789)
        register_execution_record(record)
        meta = save_asset_metadata(JOB, ASSET, ORG)
        assert meta.actual_seed == 123456789

    def test_seed_zero_is_valid(self):
        record = _make_record(actual_seed=0)
        register_execution_record(record)
        meta = save_asset_metadata(JOB, ASSET, ORG)
        assert meta.actual_seed == 0

    def test_caller_seed_ignored(self):
        """Caller sends -1 (random placeholder) — actual seed preserved."""
        record = _make_record(actual_seed=777)
        register_execution_record(record)
        meta = save_asset_metadata(JOB, ASSET, ORG, caller_metadata={"seed": -1})
        assert meta.actual_seed == 777


# =============================================================================
# Provider Normalization
# =============================================================================


@pytest.mark.unit
class TestProviderNormalization:

    def test_provider_normalized_dimensions(self):
        """Provider may round dimensions to nearest 64."""
        record = _make_record(actual_width=1024, actual_height=768)
        register_execution_record(record)
        # Caller thought they requested 1000x750
        meta = save_asset_metadata(JOB, ASSET, ORG, caller_metadata={"width": 1000, "height": 750})
        assert meta.actual_width == 1024
        assert meta.actual_height == 768

    def test_provider_defaults_recorded(self):
        """Provider-selected cfg and guidance preserved."""
        record = _make_record(actual_cfg=4.5, actual_guidance=3.5)
        register_execution_record(record)
        meta = save_asset_metadata(JOB, ASSET, ORG)
        assert meta.actual_cfg == 4.5
        assert meta.actual_guidance == 3.5


# =============================================================================
# Enrichment & Recipes
# =============================================================================


@pytest.mark.unit
class TestEnrichmentAndRecipes:

    def test_enriched_prompt_preserved(self):
        record = _make_record(
            original_prompt="a dog",
            effective_prompt="a golden retriever, professional photo, 85mm lens, bokeh",
            enrichment_applied=True,
        )
        register_execution_record(record)
        meta = save_asset_metadata(JOB, ASSET, ORG)
        assert meta.effective_prompt == "a golden retriever, professional photo, 85mm lens, bokeh"
        assert meta.original_prompt == "a dog"
        assert meta.enrichment_applied is True

    def test_recipe_id_tracked(self):
        record = _make_record(recipe_id="recipe-portrait-v2")
        register_execution_record(record)
        meta = save_asset_metadata(JOB, ASSET, ORG)
        assert meta.recipe_id == "recipe-portrait-v2"

    def test_no_enrichment_preserves_original(self):
        record = _make_record(
            original_prompt="exact prompt",
            effective_prompt="exact prompt",
            enrichment_applied=False,
        )
        register_execution_record(record)
        meta = save_asset_metadata(JOB, ASSET, ORG)
        assert meta.effective_prompt == meta.original_prompt
        assert meta.enrichment_applied is False


# =============================================================================
# LoRA Versions
# =============================================================================


@pytest.mark.unit
class TestLoraVersions:

    def test_exact_lora_versions_captured(self):
        record = _make_record(
            lora_ids=["lora-001", "lora-002"],
            lora_versions=["v3.2", "v1.0"],
            lora_strengths=[0.8, 0.5],
        )
        register_execution_record(record)
        meta = save_asset_metadata(JOB, ASSET, ORG)
        assert meta.lora_ids == ["lora-001", "lora-002"]
        assert meta.lora_versions == ["v3.2", "v1.0"]
        assert meta.lora_strengths == [0.8, 0.5]

    def test_no_lora_is_empty_list(self):
        record = _make_record(lora_ids=[], lora_versions=[], lora_strengths=[])
        register_execution_record(record)
        meta = save_asset_metadata(JOB, ASSET, ORG)
        assert meta.lora_ids == []


# =============================================================================
# Idempotency
# =============================================================================


@pytest.mark.unit
class TestIdempotency:

    def test_save_idempotent(self):
        record = _make_record()
        register_execution_record(record)
        meta1 = save_asset_metadata(JOB, ASSET, ORG)
        meta2 = save_asset_metadata(JOB, "different-asset-id", ORG)
        # Same job → same metadata returned
        assert meta1.metadata_id == meta2.metadata_id
        assert meta1.asset_id == meta2.asset_id

    def test_different_jobs_different_metadata(self):
        register_execution_record(_make_record(job_id="job-1", actual_seed=111))
        register_execution_record(_make_record(job_id="job-2", actual_seed=222))
        meta1 = save_asset_metadata("job-1", "ast-1", ORG)
        meta2 = save_asset_metadata("job-2", "ast-2", ORG)
        assert meta1.actual_seed == 111
        assert meta2.actual_seed == 222
        assert meta1.metadata_id != meta2.metadata_id


# =============================================================================
# Retry Attempts
# =============================================================================


@pytest.mark.unit
class TestRetryAttempts:

    def test_retry_gets_distinct_metadata(self):
        """Each retry attempt has its own seed and attempt number."""
        register_execution_record(_make_record(job_id="job-attempt-1", actual_seed=100, attempt_number=1))
        register_execution_record(_make_record(job_id="job-attempt-2", actual_seed=200, attempt_number=2))

        meta1 = save_asset_metadata("job-attempt-1", "ast-a1", ORG)
        meta2 = save_asset_metadata("job-attempt-2", "ast-a2", ORG)

        assert meta1.actual_seed == 100
        assert meta1.attempt_number == 1
        assert meta2.actual_seed == 200
        assert meta2.attempt_number == 2


# =============================================================================
# Cross-Tenant Protection
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_save_denied(self):
        record = _make_record(org_id=ORG)
        register_execution_record(record)
        with pytest.raises(ValueError, match="cross-tenant"):
            save_asset_metadata(JOB, ASSET, "org-evil-999")

    def test_cross_tenant_get_returns_none(self):
        record = _make_record()
        register_execution_record(record)
        save_asset_metadata(JOB, ASSET, ORG)
        assert get_asset_metadata(ASSET, "org-evil-999") is None

    def test_same_tenant_get_returns_metadata(self):
        record = _make_record()
        register_execution_record(record)
        save_asset_metadata(JOB, ASSET, ORG)
        meta = get_asset_metadata(ASSET, ORG)
        assert meta is not None
        assert meta.org_id == ORG


# =============================================================================
# Caller Metadata Validation
# =============================================================================


@pytest.mark.unit
class TestCallerValidation:

    def test_authoritative_fields_rejected(self):
        caller = {
            "seed": 999,
            "prompt": "override attempt",
            "title": "My Cool Image",  # Display-only — accepted
            "tags": ["portrait"],       # Display-only — accepted
        }
        accepted = validate_caller_metadata(caller)
        assert "title" in accepted
        assert "tags" in accepted
        assert "seed" not in accepted
        assert "prompt" not in accepted

    def test_display_fields_accepted(self):
        caller = {"title": "Sunset", "tags": ["nature"], "notes": "For campaign X"}
        accepted = validate_caller_metadata(caller)
        assert accepted == caller

    def test_empty_caller_metadata(self):
        accepted = validate_caller_metadata({})
        assert accepted == {}


# =============================================================================
# Remix Readiness
# =============================================================================


@pytest.mark.unit
class TestRemixReadiness:

    def test_complete_metadata_is_remix_ready(self):
        record = _make_record()
        register_execution_record(record)
        meta = save_asset_metadata(JOB, ASSET, ORG)
        assert meta.is_remix_ready is True

    def test_missing_prompt_not_remix_ready(self):
        record = _make_record(effective_prompt="")
        register_execution_record(record)
        meta = save_asset_metadata(JOB, ASSET, ORG)
        assert meta.is_remix_ready is False
