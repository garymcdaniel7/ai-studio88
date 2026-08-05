"""Domain Types Tests (Story 089).

Proves: type validation, legacy classification, capability enforcement,
relationship rules, context consumption, and registry completeness.

Run with:
    pytest tests/unit/test_domain_types.py -v
"""
from __future__ import annotations

import pytest

from backend.domain_types import (
    DOMAIN_TYPE_REGISTRY,
    Capability,
    ClassificationResult,
    DomainType,
    LegacyClassification,
    can_relate,
    check_capability,
    classify_legacy_record,
    get_capabilities,
    get_context_role,
    get_prompt_contribution,
    validate_record,
)


# =============================================================================
# Type Validation
# =============================================================================


class TestTypeValidation:

    @pytest.mark.unit
    def test_valid_person_passes(self):
        """Person with required fields passes validation."""
        result = validate_record(DomainType.PERSON, {
            "name": "Melissa", "org_id": "org-123",
        })
        assert result.valid is True
        assert result.missing_required == []

    @pytest.mark.unit
    def test_person_missing_name_fails(self):
        """Person without name fails."""
        result = validate_record(DomainType.PERSON, {"org_id": "org-123"})
        assert result.valid is False
        assert "name" in result.missing_required

    @pytest.mark.unit
    def test_person_missing_org_fails(self):
        """Person without org_id fails."""
        result = validate_record(DomainType.PERSON, {"name": "Melissa"})
        assert result.valid is False
        assert "org_id" in result.missing_required

    @pytest.mark.unit
    def test_person_with_prohibited_field_fails(self):
        """Person with product field (sku) fails."""
        result = validate_record(DomainType.PERSON, {
            "name": "Melissa", "org_id": "org-1", "sku": "SKU-123",
        })
        assert result.valid is False
        assert "sku" in result.prohibited_present

    @pytest.mark.unit
    def test_voice_requires_provider(self):
        """Voice type requires provider field."""
        result = validate_record(DomainType.VOICE, {
            "name": "Deep Voice", "org_id": "org-1",
        })
        assert result.valid is False
        assert "provider" in result.missing_required

    @pytest.mark.unit
    def test_voice_valid_with_provider(self):
        """Voice with all required fields passes."""
        result = validate_record(DomainType.VOICE, {
            "name": "Deep Voice", "org_id": "org-1", "provider": "elevenlabs",
        })
        assert result.valid is True

    @pytest.mark.unit
    def test_wardrobe_requires_category(self):
        """Wardrobe requires category field."""
        result = validate_record(DomainType.WARDROBE, {
            "name": "Red Dress", "org_id": "org-1",
        })
        assert result.valid is False
        assert "category" in result.missing_required

    @pytest.mark.unit
    def test_product_allows_sku(self):
        """Product type allows sku (not prohibited)."""
        result = validate_record(DomainType.PRODUCT, {
            "name": "Widget", "org_id": "org-1", "sku": "W-001",
        })
        assert result.valid is True
        assert "sku" not in result.prohibited_present

    @pytest.mark.unit
    def test_location_prohibits_physical(self):
        """Location cannot have physical fields."""
        result = validate_record(DomainType.LOCATION, {
            "name": "Beach", "org_id": "org-1", "hair_color": "blonde",
        })
        assert result.valid is False
        assert "hair_color" in result.prohibited_present

    @pytest.mark.unit
    def test_empty_prohibited_not_flagged(self):
        """Empty string prohibited field is not flagged."""
        result = validate_record(DomainType.PERSON, {
            "name": "Test", "org_id": "org-1", "sku": "",
        })
        assert result.valid is True  # Empty string = not present


# =============================================================================
# Legacy Classification
# =============================================================================


class TestLegacyClassification:

    @pytest.mark.unit
    def test_physical_attributes_classify_as_person(self):
        """Record with physical attributes → PERSON."""
        result = classify_legacy_record({
            "name": "Melissa", "height": "5'7\"", "hair_color": "brown",
        })
        assert result.domain_type == DomainType.PERSON
        assert result.classification == LegacyClassification.CONFIDENT
        assert result.confidence >= 0.8

    @pytest.mark.unit
    def test_voice_profile_classifies_as_voice(self):
        """Record with voice_profile_id → VOICE."""
        result = classify_legacy_record({
            "name": "Deep Voice", "voice_profile_id": "v-123", "provider": "elevenlabs",
        })
        assert result.domain_type == DomainType.VOICE
        assert result.classification == LegacyClassification.CONFIDENT

    @pytest.mark.unit
    def test_sku_classifies_as_product(self):
        """Record with sku → PRODUCT."""
        result = classify_legacy_record({
            "name": "Widget Pro", "sku": "SKU-001", "price": "29.99",
        })
        assert result.domain_type == DomainType.PRODUCT
        assert result.classification == LegacyClassification.CONFIDENT

    @pytest.mark.unit
    def test_wardrobe_category_classifies(self):
        """Record with wardrobe category → WARDROBE."""
        result = classify_legacy_record({
            "name": "Red Dress", "category": "dress",
        })
        assert result.domain_type == DomainType.WARDROBE
        assert result.classification == LegacyClassification.CONFIDENT

    @pytest.mark.unit
    def test_setting_type_classifies_as_location(self):
        """Record with setting_type → LOCATION."""
        result = classify_legacy_record({
            "name": "Beach Sunset", "setting_type": "outdoor",
        })
        assert result.domain_type == DomainType.LOCATION
        assert result.classification == LegacyClassification.INFERRED

    @pytest.mark.unit
    def test_persona_only_classifies_as_character(self):
        """Record with persona but no physical → CHARACTER."""
        result = classify_legacy_record({
            "name": "Robot Helper", "persona": "A friendly robot assistant",
        })
        assert result.domain_type == DomainType.CHARACTER
        assert result.classification == LegacyClassification.INFERRED
        assert DomainType.PERSON in result.alternative_types

    @pytest.mark.unit
    def test_name_only_is_ambiguous(self):
        """Record with only name → AMBIGUOUS."""
        result = classify_legacy_record({"name": "Something"})
        assert result.classification == LegacyClassification.AMBIGUOUS
        assert result.confidence < 0.5

    @pytest.mark.unit
    def test_empty_record_is_unknown(self):
        """Record with no fields → UNKNOWN."""
        result = classify_legacy_record({})
        assert result.classification == LegacyClassification.UNKNOWN
        assert result.domain_type is None

    @pytest.mark.unit
    def test_classification_serializable(self):
        """ClassificationResult.to_dict() is JSON-serializable."""
        import json
        result = classify_legacy_record({"name": "Test", "height": "6ft"})
        json.dumps(result.to_dict())


# =============================================================================
# Capability Enforcement
# =============================================================================


class TestCapabilities:

    @pytest.mark.unit
    def test_person_has_lora(self):
        """Person can have LoRA training."""
        assert check_capability(DomainType.PERSON, Capability.HAS_LORA)

    @pytest.mark.unit
    def test_person_has_voice(self):
        """Person can have voice assignment."""
        assert check_capability(DomainType.PERSON, Capability.HAS_VOICE)

    @pytest.mark.unit
    def test_wardrobe_no_lora(self):
        """Wardrobe cannot have LoRA training."""
        assert not check_capability(DomainType.WARDROBE, Capability.HAS_LORA)

    @pytest.mark.unit
    def test_wardrobe_no_voice(self):
        """Wardrobe cannot have voice."""
        assert not check_capability(DomainType.WARDROBE, Capability.HAS_VOICE)

    @pytest.mark.unit
    def test_product_has_product_dna(self):
        """Product has product DNA capability."""
        assert check_capability(DomainType.PRODUCT, Capability.HAS_PRODUCT_DNA)

    @pytest.mark.unit
    def test_person_no_product_dna(self):
        """Person does not have product DNA."""
        assert not check_capability(DomainType.PERSON, Capability.HAS_PRODUCT_DNA)

    @pytest.mark.unit
    def test_location_is_trainable(self):
        """Location can be trained (LoRA for environments)."""
        assert check_capability(DomainType.LOCATION, Capability.IS_TRAINABLE)

    @pytest.mark.unit
    def test_voice_generates_audio(self):
        """Voice can generate audio."""
        assert check_capability(DomainType.VOICE, Capability.GENERATES_AUDIO)

    @pytest.mark.unit
    def test_voice_no_images(self):
        """Voice cannot generate images."""
        assert not check_capability(DomainType.VOICE, Capability.GENERATES_IMAGES)

    @pytest.mark.unit
    def test_get_capabilities_returns_set(self):
        """get_capabilities returns full capability set."""
        caps = get_capabilities(DomainType.PERSON)
        assert Capability.HAS_LORA in caps
        assert Capability.HAS_VOICE in caps
        assert len(caps) >= 8

    @pytest.mark.unit
    def test_unknown_type_no_capabilities(self):
        """Unknown type returns empty capabilities."""
        caps = get_capabilities("nonexistent")  # type: ignore
        assert caps == set()


# =============================================================================
# Relationship Rules
# =============================================================================


class TestRelationships:

    @pytest.mark.unit
    def test_person_can_relate_to_wardrobe(self):
        """Person can relate to wardrobe (wears)."""
        assert can_relate(DomainType.PERSON, DomainType.WARDROBE)

    @pytest.mark.unit
    def test_person_can_relate_to_location(self):
        """Person can relate to location (lives_in, appears_at)."""
        assert can_relate(DomainType.PERSON, DomainType.LOCATION)

    @pytest.mark.unit
    def test_wardrobe_cannot_relate_to_location(self):
        """Wardrobe cannot directly relate to location."""
        assert not can_relate(DomainType.WARDROBE, DomainType.LOCATION)

    @pytest.mark.unit
    def test_voice_can_relate_to_person(self):
        """Voice can relate to person (voice_of)."""
        assert can_relate(DomainType.VOICE, DomainType.PERSON)

    @pytest.mark.unit
    def test_voice_cannot_relate_to_product(self):
        """Voice cannot relate to product."""
        assert not can_relate(DomainType.VOICE, DomainType.PRODUCT)

    @pytest.mark.unit
    def test_product_can_relate_to_location(self):
        """Product can relate to location (displayed_at)."""
        assert can_relate(DomainType.PRODUCT, DomainType.LOCATION)


# =============================================================================
# Context Consumption
# =============================================================================


class TestContextConsumption:

    @pytest.mark.unit
    def test_person_is_primary_subject(self):
        """Person's context role is primary_subject."""
        assert get_context_role(DomainType.PERSON) == "primary_subject"

    @pytest.mark.unit
    def test_wardrobe_is_modifier(self):
        """Wardrobe contributes as modifier to prompt."""
        assert get_prompt_contribution(DomainType.WARDROBE) == "modifier"

    @pytest.mark.unit
    def test_location_is_setting(self):
        """Location contributes as setting to prompt."""
        assert get_prompt_contribution(DomainType.LOCATION) == "setting"

    @pytest.mark.unit
    def test_voice_contributes_voice(self):
        """Voice contributes as voice."""
        assert get_prompt_contribution(DomainType.VOICE) == "voice"

    @pytest.mark.unit
    def test_product_is_subject(self):
        """Product contributes as subject."""
        assert get_prompt_contribution(DomainType.PRODUCT) == "subject"

    @pytest.mark.unit
    def test_unknown_type_empty_role(self):
        """Unknown type returns empty context role."""
        assert get_context_role("fake_type") == ""  # type: ignore


# =============================================================================
# Registry Completeness
# =============================================================================


class TestRegistry:

    @pytest.mark.unit
    def test_all_domain_types_registered(self):
        """Every DomainType enum value has a registry entry."""
        for dt in DomainType:
            assert dt in DOMAIN_TYPE_REGISTRY, f"{dt.value} missing from registry"

    @pytest.mark.unit
    def test_all_definitions_have_required_fields(self):
        """Every definition has at least name and org_id required."""
        for dt, defn in DOMAIN_TYPE_REGISTRY.items():
            assert "name" in defn.required_fields, f"{dt.value} missing 'name' required"
            assert "org_id" in defn.required_fields, f"{dt.value} missing 'org_id' required"

    @pytest.mark.unit
    def test_all_definitions_serializable(self):
        """Every definition's to_dict() is JSON-serializable."""
        import json
        for defn in DOMAIN_TYPE_REGISTRY.values():
            json.dumps(defn.to_dict())

    @pytest.mark.unit
    def test_no_overlapping_required_prohibited(self):
        """No field is both required AND prohibited."""
        for dt, defn in DOMAIN_TYPE_REGISTRY.items():
            overlap = defn.required_fields & defn.prohibited_fields
            assert overlap == set(), (
                f"{dt.value} has fields both required and prohibited: {overlap}"
            )
