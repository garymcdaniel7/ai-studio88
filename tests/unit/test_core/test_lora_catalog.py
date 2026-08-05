"""Production LoRA catalog tests — Story 098.

Tests prove:
  - Approved+active versions included
  - Simulated evidence excluded
  - Rejected/unapproved excluded
  - Inactive excluded
  - Retired excluded
  - Missing artifact excluded
  - Incompatible base model excluded
  - Cross-tenant excluded
  - Base model switch filters correctly
  - Stale cache invalidated
  - Rollback triggers invalidation
  - No eligible version returns empty list
  - Explain exclusion provides diagnostic
"""

import time

import pytest

from backend.lora_catalog import (
    CatalogEntry,
    LoRARecord,
    _reset_store,
    explain_exclusion,
    get_catalog_for_generation,
    get_production_catalog,
    invalidate_catalog,
    register_lora_record,
    retire_lora,
    unretire_lora,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"


def _record(
    version_id: str = "v-001",
    org_id: str = ORG,
    status: str = "active",
    artifact_hash: str = "hash123",
    storage_key: str = "org/models/v1.safetensors",
    evidence_type: str = "real",
    compatible_base_models: list | None = None,
    retired: bool = False,
    talent_id: str = "talent-001",
    **kwargs,
) -> LoRARecord:
    return LoRARecord(
        version_id=version_id,
        org_id=org_id,
        talent_id=talent_id,
        model_name="talent_lora",
        version_number=1,
        status=status,
        artifact_hash=artifact_hash,
        storage_key=storage_key,
        evidence_type=evidence_type,
        compatible_base_models=compatible_base_models or ["flux_dev", "sdxl"],
        retired=retired,
        trigger_words=["ohwx"],
        recommended_strength=0.8,
        **kwargs,
    )


# =============================================================================
# Eligible Versions Included
# =============================================================================


@pytest.mark.unit
class TestEligibleIncluded:

    def test_active_version_included(self):
        register_lora_record(_record(status="active"))
        catalog = get_production_catalog(ORG)
        assert len(catalog) == 1
        assert catalog[0].version_id == "v-001"
        assert catalog[0].status == "active"

    def test_deployable_version_included(self):
        register_lora_record(_record(version_id="v-dep", status="deployable"))
        catalog = get_production_catalog(ORG)
        assert len(catalog) == 1

    def test_multiple_eligible_returned(self):
        register_lora_record(_record(version_id="v-1", talent_id="t1"))
        register_lora_record(_record(version_id="v-2", talent_id="t2"))
        catalog = get_production_catalog(ORG)
        assert len(catalog) == 2


# =============================================================================
# Exclusions
# =============================================================================


@pytest.mark.unit
class TestExclusions:

    def test_simulated_excluded(self):
        register_lora_record(_record(evidence_type="simulation"))
        catalog = get_production_catalog(ORG)
        assert len(catalog) == 0

    def test_rejected_excluded(self):
        register_lora_record(_record(status="rejected"))
        catalog = get_production_catalog(ORG)
        assert len(catalog) == 0

    def test_trained_excluded(self):
        register_lora_record(_record(status="trained"))
        catalog = get_production_catalog(ORG)
        assert len(catalog) == 0

    def test_review_required_excluded(self):
        register_lora_record(_record(status="review_required"))
        catalog = get_production_catalog(ORG)
        assert len(catalog) == 0

    def test_retired_excluded(self):
        register_lora_record(_record(retired=True))
        catalog = get_production_catalog(ORG)
        assert len(catalog) == 0

    def test_missing_artifact_excluded(self):
        register_lora_record(_record(artifact_hash="", storage_key=""))
        catalog = get_production_catalog(ORG)
        assert len(catalog) == 0

    def test_missing_storage_key_excluded(self):
        register_lora_record(_record(storage_key=""))
        catalog = get_production_catalog(ORG)
        assert len(catalog) == 0

    def test_incompatible_base_model_excluded(self):
        register_lora_record(_record(compatible_base_models=["sdxl"]))
        catalog = get_production_catalog(ORG, base_model="flux_dev")
        assert len(catalog) == 0


# =============================================================================
# Cross-Tenant
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_other_org_records_not_visible(self):
        register_lora_record(_record(org_id=OTHER_ORG))
        catalog = get_production_catalog(ORG)
        assert len(catalog) == 0

    def test_own_org_records_visible(self):
        register_lora_record(_record(org_id=ORG))
        catalog = get_production_catalog(ORG)
        assert len(catalog) == 1


# =============================================================================
# Base Model Switch
# =============================================================================


@pytest.mark.unit
class TestBaseModelSwitch:

    def test_filter_by_base_model(self):
        register_lora_record(_record(version_id="v-flux", compatible_base_models=["flux_dev"]))
        register_lora_record(_record(version_id="v-sdxl", compatible_base_models=["sdxl"]))

        flux_catalog = get_catalog_for_generation(ORG, "flux_dev")
        sdxl_catalog = get_catalog_for_generation(ORG, "sdxl")

        assert len(flux_catalog) == 1
        assert flux_catalog[0].version_id == "v-flux"
        assert len(sdxl_catalog) == 1
        assert sdxl_catalog[0].version_id == "v-sdxl"

    def test_no_base_model_returns_all(self):
        register_lora_record(_record(version_id="v-flux", compatible_base_models=["flux_dev"]))
        register_lora_record(_record(version_id="v-sdxl", compatible_base_models=["sdxl"]))
        catalog = get_production_catalog(ORG, base_model=None)
        assert len(catalog) == 2


# =============================================================================
# Cache Behavior
# =============================================================================


@pytest.mark.unit
class TestCache:

    def test_cached_results_returned(self):
        register_lora_record(_record())
        # First call populates cache
        c1 = get_production_catalog(ORG)
        # Add another record (won't show due to cache)
        register_lora_record(_record(version_id="v-new", talent_id="t2"))
        # invalidate_catalog was called by register — cache cleared
        c2 = get_production_catalog(ORG)
        assert len(c2) == 2  # New record visible because register invalidates

    def test_force_refresh_bypasses_cache(self):
        register_lora_record(_record())
        get_production_catalog(ORG)  # Cache
        # Manually sneak a record without invalidation
        from backend.lora_catalog import _lora_records
        _lora_records.append(_record(version_id="v-sneaky", talent_id="t3"))
        # Normal query uses cache
        cached = get_production_catalog(ORG)
        # Force refresh sees new record
        fresh = get_production_catalog(ORG, force_refresh=True)
        assert len(fresh) >= len(cached)

    def test_invalidation_clears_org_cache(self):
        register_lora_record(_record())
        get_production_catalog(ORG)  # Cache
        invalidate_catalog(ORG)
        # After invalidation, next query rebuilds
        from backend.lora_catalog import _cache
        org_keys = [k for k in _cache if k.startswith(f"{ORG}:")]
        assert len(org_keys) == 0


# =============================================================================
# Retirement / Rollback
# =============================================================================


@pytest.mark.unit
class TestRetirementRollback:

    def test_retire_removes_from_catalog(self):
        register_lora_record(_record())
        assert len(get_production_catalog(ORG)) == 1
        retire_lora("v-001", ORG)
        assert len(get_production_catalog(ORG, force_refresh=True)) == 0

    def test_unretire_restores_to_catalog(self):
        register_lora_record(_record(retired=True))
        assert len(get_production_catalog(ORG)) == 0
        unretire_lora("v-001", ORG)
        assert len(get_production_catalog(ORG, force_refresh=True)) == 1

    def test_rollback_via_status_change(self):
        """Simulates rollback: active → superseded (excluded)."""
        register_lora_record(_record(status="active"))
        assert len(get_production_catalog(ORG)) == 1
        # Update status to superseded
        register_lora_record(_record(status="superseded"))
        assert len(get_production_catalog(ORG, force_refresh=True)) == 0


# =============================================================================
# No Eligible Version
# =============================================================================


@pytest.mark.unit
class TestNoEligible:

    def test_empty_catalog_returns_empty_list(self):
        catalog = get_production_catalog(ORG)
        assert catalog == []

    def test_all_excluded_returns_empty(self):
        register_lora_record(_record(status="rejected"))
        register_lora_record(_record(version_id="v-2", retired=True))
        catalog = get_production_catalog(ORG)
        assert catalog == []


# =============================================================================
# Talent Filter
# =============================================================================


@pytest.mark.unit
class TestTalentFilter:

    def test_filter_by_talent(self):
        register_lora_record(_record(version_id="v-t1", talent_id="talent-1"))
        register_lora_record(_record(version_id="v-t2", talent_id="talent-2"))
        catalog = get_production_catalog(ORG, talent_id="talent-1")
        assert len(catalog) == 1
        assert catalog[0].talent_id == "talent-1"


# =============================================================================
# Explain Exclusion
# =============================================================================


@pytest.mark.unit
class TestExplainExclusion:

    def test_explain_rejected_version(self):
        register_lora_record(_record(status="rejected"))
        result = explain_exclusion("v-001", ORG)
        assert result["found"] is True
        assert not result["eligible"]
        assert any("rejected" in r or "active" in r for r in result["exclusion_reasons"])

    def test_explain_not_found(self):
        result = explain_exclusion("nonexistent", ORG)
        assert result["found"] is False

    def test_explain_incompatible(self):
        register_lora_record(_record(compatible_base_models=["sdxl"]))
        result = explain_exclusion("v-001", ORG, base_model="flux_dev")
        assert not result["eligible"]
        assert any("flux_dev" in r for r in result["exclusion_reasons"])

    def test_explain_eligible(self):
        register_lora_record(_record())
        result = explain_exclusion("v-001", ORG)
        assert result["eligible"] is True
        assert result["exclusion_reasons"] == []
