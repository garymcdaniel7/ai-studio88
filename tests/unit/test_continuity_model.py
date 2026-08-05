"""Continuity Domain Model Tests (Story 079).

Proves: ownership validation, versioning, approval transitions, legacy mapping
completeness, drift detection, generation context pinning, and entity registry.

Run with:
    pytest tests/unit/test_continuity_model.py -v
"""
from __future__ import annotations

import pytest

from backend.continuity_model import (
    CANONICAL_ENTITIES,
    LEGACY_MAPPING,
    RELATIONSHIP_TYPES,
    VALID_APPROVAL_TRANSITIONS,
    ApprovalError,
    ApprovalState,
    ContinuityEntityType,
    ContinuityNote,
    ContinuityRecord,
    ContinuityRule,
    CreativePreferences,
    GenerationContext,
    LoRAAssignment,
    Relationship,
    RuleCategory,
    RuleType,
    TalentProfile,
    VoiceAssignment,
    WardrobeItem,
    increment_version,
    transition_approval,
    validate_ownership,
)


# =============================================================================
# Ownership Validation
# =============================================================================


class TestOwnership:

    @pytest.mark.unit
    def test_valid_ownership_passes(self):
        """Record with org_id and created_by is valid."""
        record = ContinuityRecord(org_id="org-1", created_by="user-1")
        assert validate_ownership(record) == []

    @pytest.mark.unit
    def test_missing_org_id_detected(self):
        """Missing org_id is detected."""
        record = ContinuityRecord(org_id="", created_by="user-1")
        missing = validate_ownership(record)
        assert "org_id" in missing

    @pytest.mark.unit
    def test_missing_created_by_detected(self):
        """Missing created_by is detected."""
        record = ContinuityRecord(org_id="org-1", created_by="")
        missing = validate_ownership(record)
        assert "created_by" in missing

    @pytest.mark.unit
    def test_all_entities_require_org_id(self):
        """Every canonical entity requires org_id."""
        for name, config in CANONICAL_ENTITIES.items():
            assert config["requires_org_id"] is True, (
                f"{name} must require org_id"
            )


# =============================================================================
# Versioning
# =============================================================================


class TestVersioning:

    @pytest.mark.unit
    def test_initial_version_is_one(self):
        """New records start at version 1."""
        record = TalentProfile(org_id="org-1", created_by="u-1")
        assert record.version == 1

    @pytest.mark.unit
    def test_increment_version(self):
        """increment_version bumps version and sets updated_by."""
        record = TalentProfile(org_id="org-1", created_by="u-1")
        increment_version(record, "editor-2")
        assert record.version == 2
        assert record.updated_by == "editor-2"
        assert record.updated_at is not None

    @pytest.mark.unit
    def test_multiple_increments(self):
        """Version increments monotonically."""
        record = ContinuityRule(org_id="org-1", created_by="u-1")
        increment_version(record, "u-2")
        increment_version(record, "u-3")
        increment_version(record, "u-4")
        assert record.version == 4

    @pytest.mark.unit
    def test_all_entities_are_versioned(self):
        """Every canonical entity is marked as versioned."""
        for name, config in CANONICAL_ENTITIES.items():
            assert config["versioned"] is True, f"{name} must be versioned"


# =============================================================================
# Approval Transitions
# =============================================================================


class TestApproval:

    @pytest.mark.unit
    def test_draft_to_approved(self):
        """DRAFT → APPROVED is valid."""
        record = TalentProfile(org_id="org-1", created_by="u-1")
        transition_approval(record, ApprovalState.APPROVED, actor="admin-1")
        assert record.approval_state == ApprovalState.APPROVED

    @pytest.mark.unit
    def test_approved_to_retired(self):
        """APPROVED → RETIRED is valid."""
        record = TalentProfile(
            org_id="org-1", created_by="u-1",
            approval_state=ApprovalState.APPROVED,
        )
        transition_approval(record, ApprovalState.RETIRED, actor="admin-1")
        assert record.approval_state == ApprovalState.RETIRED

    @pytest.mark.unit
    def test_retired_to_approved_reactivate(self):
        """RETIRED → APPROVED (re-activate) is valid."""
        record = TalentProfile(
            org_id="org-1", created_by="u-1",
            approval_state=ApprovalState.RETIRED,
        )
        transition_approval(record, ApprovalState.APPROVED, actor="admin-1")
        assert record.approval_state == ApprovalState.APPROVED

    @pytest.mark.unit
    def test_approved_to_draft_invalid(self):
        """APPROVED → DRAFT is invalid."""
        record = TalentProfile(
            org_id="org-1", created_by="u-1",
            approval_state=ApprovalState.APPROVED,
        )
        with pytest.raises(ApprovalError) as exc_info:
            transition_approval(record, ApprovalState.DRAFT, actor="u-1")
        assert "invalid" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_transition_increments_version(self):
        """Approval transition increments version."""
        record = TalentProfile(org_id="org-1", created_by="u-1")
        transition_approval(record, ApprovalState.APPROVED, actor="admin")
        assert record.version == 2

    @pytest.mark.unit
    def test_all_entities_require_approval(self):
        """Every canonical entity uses approval state."""
        for name, config in CANONICAL_ENTITIES.items():
            assert config["requires_approval"] is True, (
                f"{name} must require approval"
            )


# =============================================================================
# Legacy Mapping
# =============================================================================


class TestLegacyMapping:

    @pytest.mark.unit
    def test_creative_dna_jsonb_mapped(self):
        """talent.creative_dna JSONB column is mapped to canonical entity."""
        entry = LEGACY_MAPPING["talent.creative_dna"]
        assert entry["canonical"] == "CreativePreferences"
        assert entry["status"] == "deprecated"

    @pytest.mark.unit
    def test_creative_dna_table_mapped(self):
        """creative_dna table is mapped to canonical entity."""
        entry = LEGACY_MAPPING["creative_dna (table)"]
        assert entry["canonical"] == "CreativePreferences"

    @pytest.mark.unit
    def test_continuity_notes_mapped(self):
        """continuity_notes table mapped."""
        entry = LEGACY_MAPPING["continuity_notes (table)"]
        assert entry["canonical"] == "ContinuityNote"

    @pytest.mark.unit
    def test_creative_rules_mapped(self):
        """creative_rules table mapped."""
        entry = LEGACY_MAPPING["creative_rules (table)"]
        assert entry["canonical"] == "ContinuityRule"

    @pytest.mark.unit
    def test_style_preferences_mapped(self):
        """style_preferences merged into CreativePreferences."""
        entry = LEGACY_MAPPING["style_preferences (table)"]
        assert entry["canonical"] == "CreativePreferences"
        assert entry["status"] == "deprecated"

    @pytest.mark.unit
    def test_talent_voices_mapped(self):
        """talent_voices mapped to VoiceAssignment."""
        entry = LEGACY_MAPPING["talent_voices (table)"]
        assert entry["canonical"] == "VoiceAssignment"

    @pytest.mark.unit
    def test_all_legacy_have_migration_plan(self):
        """Every legacy entry has a migration description."""
        for key, entry in LEGACY_MAPPING.items():
            assert entry["migration"], f"Legacy '{key}' missing migration plan"

    @pytest.mark.unit
    def test_all_legacy_reference_canonical_entity(self):
        """Every legacy mapping references a real canonical entity."""
        canonical_names = set(CANONICAL_ENTITIES.keys())
        for key, entry in LEGACY_MAPPING.items():
            assert entry["canonical"] in canonical_names, (
                f"Legacy '{key}' references unknown '{entry['canonical']}'"
            )


# =============================================================================
# Drift Detection (Entity Registry)
# =============================================================================


class TestDriftDetection:

    @pytest.mark.unit
    def test_all_entity_types_in_registry(self):
        """Every ContinuityEntityType has a registry entry."""
        registered_types = {v["type"] for v in CANONICAL_ENTITIES.values()}
        for et in ContinuityEntityType:
            assert et in registered_types, (
                f"ContinuityEntityType.{et.value} not in CANONICAL_ENTITIES"
            )

    @pytest.mark.unit
    def test_entity_count_matches_enum(self):
        """Registry entry count matches entity type enum count."""
        assert len(CANONICAL_ENTITIES) == len(ContinuityEntityType)

    @pytest.mark.unit
    def test_parent_references_valid(self):
        """Parent references in registry are valid entity names or None."""
        valid_names = set(CANONICAL_ENTITIES.keys()) | {None}
        for name, config in CANONICAL_ENTITIES.items():
            assert config["parent"] in valid_names, (
                f"{name} has invalid parent: {config['parent']}"
            )

    @pytest.mark.unit
    def test_relationship_types_non_empty(self):
        """Relationship types set is populated."""
        assert len(RELATIONSHIP_TYPES) >= 10


# =============================================================================
# Generation Context (Version Pinning)
# =============================================================================


class TestGenerationContext:

    @pytest.mark.unit
    def test_context_pins_versions(self):
        """GenerationContext captures exact version numbers."""
        ctx = GenerationContext(
            talent_id="t-1",
            talent_version=3,
            preferences_version=2,
            lora_assignment_version=1,
            active_rules=[
                {"rule_id": "r-1", "version": 4},
                {"rule_id": "r-2", "version": 1},
            ],
            active_wardrobe=[
                {"item_id": "w-1", "version": 2},
            ],
        )
        assert ctx.talent_version == 3
        assert ctx.preferences_version == 2
        assert len(ctx.active_rules) == 2
        assert ctx.active_rules[0]["version"] == 4

    @pytest.mark.unit
    def test_context_has_snapshot_timestamp(self):
        """Context records when snapshot was taken."""
        ctx = GenerationContext(talent_id="t-1")
        assert ctx.snapshot_at is not None

    @pytest.mark.unit
    def test_context_serializable(self):
        """GenerationContext.to_dict() is JSON-serializable."""
        import json
        ctx = GenerationContext(
            talent_id="t-1", talent_version=1,
            preferences_version=1, lora_assignment_version=1,
        )
        json.dumps(ctx.to_dict())


# =============================================================================
# Entity Instantiation
# =============================================================================


class TestEntityInstantiation:

    @pytest.mark.unit
    def test_talent_profile_defaults(self):
        """TalentProfile has correct entity_type."""
        t = TalentProfile(org_id="org-1", name="Melissa", created_by="u-1")
        assert t.entity_type == ContinuityEntityType.TALENT_PROFILE
        assert t.name == "Melissa"
        assert t.approval_state == ApprovalState.DRAFT

    @pytest.mark.unit
    def test_creative_preferences_defaults(self):
        """CreativePreferences linked to talent."""
        p = CreativePreferences(org_id="org-1", talent_id="t-1", created_by="u-1")
        assert p.entity_type == ContinuityEntityType.CREATIVE_PREFERENCES
        assert p.preferred_styles == []

    @pytest.mark.unit
    def test_voice_assignment_defaults(self):
        """VoiceAssignment has provider field."""
        v = VoiceAssignment(
            org_id="org-1", talent_id="t-1", created_by="u-1",
            voice_profile_id="voice-123", provider="elevenlabs",
        )
        assert v.provider == "elevenlabs"
        assert v.is_primary is False

    @pytest.mark.unit
    def test_wardrobe_item_defaults(self):
        """WardrobeItem has category and prompt_fragment."""
        w = WardrobeItem(
            org_id="org-1", talent_id="t-1", created_by="u-1",
            name="Red Dress", category="full_outfit",
            prompt_fragment="wearing elegant red dress",
        )
        assert w.category == "full_outfit"
        assert "red dress" in w.prompt_fragment

    @pytest.mark.unit
    def test_continuity_rule_defaults(self):
        """ContinuityRule has type and category."""
        r = ContinuityRule(
            org_id="org-1", talent_id="t-1", created_by="u-1",
            rule_type=RuleType.AVOID, category=RuleCategory.WARDROBE,
            rule_text="never wear green",
        )
        assert r.rule_type == RuleType.AVOID
        assert r.category == RuleCategory.WARDROBE

    @pytest.mark.unit
    def test_lora_assignment_defaults(self):
        """LoRAAssignment has model_id and strength."""
        l = LoRAAssignment(
            org_id="org-1", talent_id="t-1", created_by="u-1",
            lora_model_id="lora-melissa-v3", lora_version="v3",
            strength=0.8, trigger_word="mlss",
        )
        assert l.strength == 0.8
        assert l.trigger_word == "mlss"

    @pytest.mark.unit
    def test_all_entities_serializable(self):
        """All entity to_dict() methods produce JSON-serializable output."""
        import json
        entities = [
            TalentProfile(org_id="o", created_by="u", name="Test"),
            CreativePreferences(org_id="o", created_by="u"),
            VoiceAssignment(org_id="o", created_by="u"),
            WardrobeItem(org_id="o", created_by="u"),
            Relationship(org_id="o", created_by="u"),
            ContinuityRule(org_id="o", created_by="u"),
            ContinuityNote(org_id="o", created_by="u"),
            LoRAAssignment(org_id="o", created_by="u"),
        ]
        for e in entities:
            json.dumps(e.to_dict())
