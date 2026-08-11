"""Object DNA contract tests — Story 114.

Tests prove:
  - Unanalysed assets are NOT presented as DNA
  - Low confidence is visible (never hidden)
  - User correction creates new version (history preserved)
  - Cross-tenant access denied
  - Reanalysis creates new version
  - Context assembly ONLY uses approved versions
  - Legacy tag-only assets explicitly flagged
  - Analysis lifecycle: analysing → partial/review_required → approved
  - Approval required before context consumption
  - Historical generation pins DNA version
"""

import pytest

from backend.object_dna_contract import (
    DNANotFound,
    DNAStatus,
    DomainType,
    InvalidDNAState,
    _reset_store,
    approve_dna,
    complete_analysis,
    correct_dna,
    get_dna,
    get_dna_status,
    get_for_context,
    get_historical_dna_version,
    list_unanalysed,
    register_asset,
    start_analysis,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
ASSET = "ast-001"


def _analysed_asset(confidence: float = 0.9) -> None:
    """Register and analyse an asset."""
    register_asset(ORG, ASSET)
    start_analysis(ASSET, ORG, "gpt-4-vision", "2024-01")
    complete_analysis(
        ASSET, ORG,
        domain_type=DomainType.PRODUCT,
        attributes=[
            {"key": "color", "value": "red", "confidence": 0.95},
            {"key": "material", "value": "leather", "confidence": 0.88},
            {"key": "brand", "value": "Nike", "confidence": 0.75},
        ],
        overall_confidence=confidence,
        source_model="gpt-4-vision",
        source_model_version="2024-01",
    )


# =============================================================================
# Unanalysed vs Analysed
# =============================================================================


@pytest.mark.unit
class TestUnanalysedDistinction:

    def test_registered_asset_is_unanalysed(self):
        dna = register_asset(ORG, ASSET)
        assert dna.status == DNAStatus.UNANALYSED
        assert dna.has_tags_only is True
        assert dna.is_analysed is False

    def test_analysed_asset_not_tags_only(self):
        _analysed_asset()
        dna = get_dna(ASSET, ORG)
        assert dna.has_tags_only is False
        assert dna.is_analysed is True

    def test_status_api_shows_unanalysed(self):
        register_asset(ORG, ASSET)
        status = get_dna_status(ASSET, ORG)
        assert status["status"] == "unanalysed"
        assert status["has_tags_only"] is True

    def test_list_unanalysed(self):
        register_asset(ORG, "ast-1")
        register_asset(ORG, "ast-2")
        _analysed_asset()  # Analyses ASSET
        unanalysed = list_unanalysed(ORG)
        assert "ast-1" in unanalysed
        assert "ast-2" in unanalysed
        assert ASSET not in unanalysed


# =============================================================================
# Low Confidence Visible
# =============================================================================


@pytest.mark.unit
class TestLowConfidence:

    def test_low_confidence_visible_in_status(self):
        register_asset(ORG, ASSET)
        start_analysis(ASSET, ORG, "model-1")
        complete_analysis(ASSET, ORG, DomainType.PROP, [{"key": "shape", "value": "round"}],
                          overall_confidence=0.5)
        status = get_dna_status(ASSET, ORG)
        assert status["is_low_confidence"] is True
        assert status["confidence"] == 0.5

    def test_low_confidence_goes_to_partial(self):
        register_asset(ORG, ASSET)
        start_analysis(ASSET, ORG, "model-1")
        complete_analysis(ASSET, ORG, DomainType.PROP, [{"key": "x", "value": "y"}],
                          overall_confidence=0.4)
        dna = get_dna(ASSET, ORG)
        assert dna.status == DNAStatus.PARTIAL

    def test_high_confidence_goes_to_review_required(self):
        register_asset(ORG, ASSET)
        start_analysis(ASSET, ORG, "model-1")
        complete_analysis(ASSET, ORG, DomainType.PRODUCT,
                          [{"key": "color", "value": "blue"}],
                          overall_confidence=0.9)
        dna = get_dna(ASSET, ORG)
        assert dna.status == DNAStatus.REVIEW_REQUIRED


# =============================================================================
# User Corrections Preserve History
# =============================================================================


@pytest.mark.unit
class TestCorrections:

    def test_correction_creates_new_version(self):
        _analysed_asset()
        approve_dna(ASSET, ORG, "admin")
        dna_before = get_dna(ASSET, ORG)
        assert dna_before.version_count == 1

        correct_dna(ASSET, ORG, "user-001", [
            {"type": "modify_attribute", "key": "color", "value": "blue", "reason": "wrong color"},
        ])
        dna_after = get_dna(ASSET, ORG)
        assert dna_after.version_count == 2

    def test_correction_preserves_history(self):
        _analysed_asset()
        approve_dna(ASSET, ORG, "admin")
        correct_dna(ASSET, ORG, "user-001", [
            {"type": "modify_attribute", "key": "color", "value": "blue"},
        ])
        dna = get_dna(ASSET, ORG)
        # Version 1 still exists
        v1 = dna.versions[0]
        v2 = dna.versions[1]
        color_v1 = next(a for a in v1.attributes if a.key == "color")
        color_v2 = next(a for a in v2.attributes if a.key == "color")
        assert color_v1.value == "red"   # Original preserved
        assert color_v2.value == "blue"  # Corrected

    def test_correction_auto_approves(self):
        _analysed_asset()
        approve_dna(ASSET, ORG, "admin")
        correct_dna(ASSET, ORG, "user-001", [
            {"type": "add_attribute", "key": "size", "value": "large"},
        ])
        dna = get_dna(ASSET, ORG)
        assert dna.status == DNAStatus.APPROVED

    def test_correction_requires_actor(self):
        _analysed_asset()
        with pytest.raises(ValueError, match="corrected_by"):
            correct_dna(ASSET, ORG, "", [{"type": "add_attribute", "key": "x", "value": "y"}])


# =============================================================================
# Cross-Tenant
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_get_returns_none(self):
        register_asset(ORG, ASSET)
        assert get_dna(ASSET, OTHER_ORG) is None

    def test_cross_tenant_context_returns_none(self):
        _analysed_asset()
        approve_dna(ASSET, ORG, "admin")
        assert get_for_context(ASSET, OTHER_ORG) is None

    def test_cross_tenant_status_shows_unanalysed(self):
        register_asset(ORG, ASSET)
        status = get_dna_status(ASSET, OTHER_ORG)
        assert status["status"] == "unanalysed"


# =============================================================================
# Reanalysis Creates Version
# =============================================================================


@pytest.mark.unit
class TestReanalysis:

    def test_reanalysis_creates_new_version(self):
        _analysed_asset()
        approve_dna(ASSET, ORG, "admin")
        # Reanalyse with new model
        start_analysis(ASSET, ORG, "clip-v2")
        complete_analysis(ASSET, ORG, DomainType.PRODUCT,
                          [{"key": "color", "value": "dark red"}, {"key": "style", "value": "sporty"}],
                          overall_confidence=0.95,
                          source_model="clip-v2")
        dna = get_dna(ASSET, ORG)
        assert dna.version_count == 2
        assert dna.current_version.provenance.source_model == "clip-v2"


# =============================================================================
# Context Only Uses Approved
# =============================================================================


@pytest.mark.unit
class TestContextConsumption:

    def test_unapproved_returns_none(self):
        _analysed_asset()
        # Status is review_required — not approved
        result = get_for_context(ASSET, ORG)
        assert result is None

    def test_approved_returns_data(self):
        _analysed_asset()
        approve_dna(ASSET, ORG, "admin")
        result = get_for_context(ASSET, ORG)
        assert result is not None
        assert result["domain_type"] == "product"
        assert "color" in result["attributes"]
        assert result["attributes"]["color"] == "red"

    def test_unanalysed_returns_none(self):
        register_asset(ORG, ASSET)
        result = get_for_context(ASSET, ORG)
        assert result is None

    def test_context_pins_version(self):
        _analysed_asset()
        approve_dna(ASSET, ORG, "admin")
        result = get_for_context(ASSET, ORG, job_id="job-gen-001")
        version_id = result["version_id"]
        assert get_historical_dna_version("job-gen-001") == version_id


# =============================================================================
# Legacy Tags Not DNA
# =============================================================================


@pytest.mark.unit
class TestLegacyTags:

    def test_unregistered_asset_status_unanalysed(self):
        status = get_dna_status("nonexistent", ORG)
        assert status["status"] == "unanalysed"
        assert status["has_tags_only"] is True

    def test_tag_only_not_consumable_by_context(self):
        register_asset(ORG, ASSET)
        assert get_for_context(ASSET, ORG) is None


# =============================================================================
# Approval
# =============================================================================


@pytest.mark.unit
class TestApproval:

    def test_cannot_approve_unanalysed(self):
        register_asset(ORG, ASSET)
        with pytest.raises(InvalidDNAState):
            approve_dna(ASSET, ORG, "admin")

    def test_approve_idempotent(self):
        _analysed_asset()
        approve_dna(ASSET, ORG, "admin")
        dna = approve_dna(ASSET, ORG, "admin")
        assert dna.status == DNAStatus.APPROVED
