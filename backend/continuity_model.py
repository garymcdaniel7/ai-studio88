"""Canonical Continuity Domain Model — Story 079.

One understandable continuity model so approved characters, voices, wardrobe,
relationships, and creative rules are applied consistently across every surface.

Canonical Entities:
    TalentProfile       — The root character entity (identity, physical, persona)
    CreativePreferences — Versioned style/generation preferences per talent
    VoiceAssignment     — Voice profile linked to talent with approval
    WardrobeItem        — Versioned wardrobe/outfit record
    Relationship        — Typed link between any two talent entities
    ContinuityRule      — Active rule applied during generation
    ContinuityNote      — Free-text creative note with priority
    LoRAAssignment      — LoRA model version linked to talent

Every entity has:
    - org_id (mandatory tenant scope)
    - created_by / updated_by (actor attribution)
    - version (monotonic increment on mutation)
    - approval_state (draft → approved → retired)
    - lifecycle_state (active/archived/trashed per Story 069)

Generation Context references EXACT versions, not mutable snapshots.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Shared Enums
# =============================================================================


class ApprovalState(StrEnum):
    DRAFT = "draft"           # Created but not approved for generation
    APPROVED = "approved"     # Active and used in generation context
    RETIRED = "retired"       # No longer active, preserved for history


class ContinuityEntityType(StrEnum):
    TALENT_PROFILE = "talent_profile"
    CREATIVE_PREFERENCES = "creative_preferences"
    VOICE_ASSIGNMENT = "voice_assignment"
    WARDROBE_ITEM = "wardrobe_item"
    RELATIONSHIP = "relationship"
    CONTINUITY_RULE = "continuity_rule"
    CONTINUITY_NOTE = "continuity_note"
    LORA_ASSIGNMENT = "lora_assignment"


# =============================================================================
# Base Record (shared fields)
# =============================================================================


@dataclass
class ContinuityRecord:
    """Base fields for all continuity entities."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""                    # Mandatory tenant scope
    talent_id: str = ""                 # Parent talent (if applicable)
    version: int = 1                    # Monotonic version counter
    approval_state: ApprovalState = ApprovalState.DRAFT
    created_by: str = ""                # Actor who created
    updated_by: str = ""                # Actor who last modified
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# =============================================================================
# Talent Profile (root entity)
# =============================================================================


@dataclass
class TalentProfile(ContinuityRecord):
    """The canonical character/talent entity.

    Owns: name, physical attributes, persona, visual style.
    References: CreativePreferences, VoiceAssignment, WardrobeItems, LoRA.
    """
    entity_type: ContinuityEntityType = ContinuityEntityType.TALENT_PROFILE

    # Identity
    name: str = ""
    display_name: str = ""
    persona: str = ""               # Character description/personality

    # Physical attributes
    height: str | None = None
    hair_color: str | None = None
    eye_color: str | None = None
    body_type: str | None = None
    ethnicity: str | None = None
    age_range: str | None = None

    # Visual generation
    visual_style: str = ""          # Primary style descriptor
    negative_prompt: str = ""       # Always-avoid terms
    trigger_word: str = ""          # LoRA trigger word

    # Status
    is_active: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "name": self.name,
            "display_name": self.display_name,
            "persona": self.persona,
            "height": self.height,
            "hair_color": self.hair_color,
            "eye_color": self.eye_color,
            "body_type": self.body_type,
            "visual_style": self.visual_style,
            "trigger_word": self.trigger_word,
            "version": self.version,
            "approval_state": self.approval_state.value,
            "is_active": self.is_active,
        }


# =============================================================================
# Creative Preferences (versioned)
# =============================================================================


@dataclass
class CreativePreferences(ContinuityRecord):
    """Versioned creative preferences for a talent.

    Replaces the mutable creative_dna JSONB column.
    Each mutation creates a new version for generation pinning.
    """
    entity_type: ContinuityEntityType = ContinuityEntityType.CREATIVE_PREFERENCES

    # Preference categories
    preferred_styles: list[str] = field(default_factory=list)
    avoided_styles: list[str] = field(default_factory=list)
    color_palette: list[str] = field(default_factory=list)
    camera_preferences: dict = field(default_factory=dict)
    wardrobe_preferences: dict = field(default_factory=dict)
    setting_preferences: dict = field(default_factory=dict)
    lighting_preferences: dict = field(default_factory=dict)

    # Prompt modifiers
    prompt_additions: list[str] = field(default_factory=list)
    negative_additions: list[str] = field(default_factory=list)

    # Model preferences
    preferred_model: str = ""
    preferred_lora: str = ""
    lora_strength: float = 0.7

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "talent_id": self.talent_id,
            "version": self.version,
            "approval_state": self.approval_state.value,
            "preferred_styles": self.preferred_styles,
            "avoided_styles": self.avoided_styles,
            "color_palette": self.color_palette,
            "preferred_model": self.preferred_model,
            "preferred_lora": self.preferred_lora,
        }


# =============================================================================
# Voice Assignment
# =============================================================================


@dataclass
class VoiceAssignment(ContinuityRecord):
    """Voice profile linked to a talent with approval."""

    entity_type: ContinuityEntityType = ContinuityEntityType.VOICE_ASSIGNMENT

    voice_profile_id: str = ""      # External voice ID (ElevenLabs, MOSS)
    provider: str = ""              # elevenlabs, moss, custom
    is_primary: bool = False        # Primary voice for this talent
    voice_name: str = ""            # Human-readable name
    sample_url: str | None = None   # Reference audio sample

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "talent_id": self.talent_id,
            "voice_profile_id": self.voice_profile_id,
            "provider": self.provider,
            "is_primary": self.is_primary,
            "voice_name": self.voice_name,
            "version": self.version,
            "approval_state": self.approval_state.value,
        }


# =============================================================================
# Wardrobe Item
# =============================================================================


@dataclass
class WardrobeItem(ContinuityRecord):
    """A versioned wardrobe/outfit record for a talent."""

    entity_type: ContinuityEntityType = ContinuityEntityType.WARDROBE_ITEM

    name: str = ""
    description: str = ""
    category: str = ""          # top, bottom, full_outfit, accessory, footwear
    prompt_fragment: str = ""   # Text injected into generation prompt
    reference_asset_id: str | None = None  # Visual reference image
    color: str | None = None
    style: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "talent_id": self.talent_id,
            "name": self.name,
            "category": self.category,
            "prompt_fragment": self.prompt_fragment,
            "version": self.version,
            "approval_state": self.approval_state.value,
        }


# =============================================================================
# Relationship
# =============================================================================


RELATIONSHIP_TYPES = {
    "friends", "couple", "siblings", "parent_child",
    "wears", "uses", "holds", "lives_in",
    "pairs_with", "appears_with", "variant_of", "associated",
}


@dataclass
class Relationship(ContinuityRecord):
    """Typed link between two talent entities."""

    entity_type: ContinuityEntityType = ContinuityEntityType.RELATIONSHIP

    source_talent_id: str = ""
    target_talent_id: str = ""
    relationship_type: str = "associated"
    notes: str = ""
    is_bidirectional: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "source_talent_id": self.source_talent_id,
            "target_talent_id": self.target_talent_id,
            "relationship_type": self.relationship_type,
            "is_bidirectional": self.is_bidirectional,
            "version": self.version,
            "approval_state": self.approval_state.value,
        }


# =============================================================================
# Continuity Rule
# =============================================================================


class RuleType(StrEnum):
    INCLUDE = "include"     # Always add to prompt
    AVOID = "avoid"         # Always add to negative prompt
    PREFER = "prefer"       # Soft preference (weighted)
    REQUIRE = "require"     # Hard requirement (block if violated)


class RuleCategory(StrEnum):
    PROMPT = "prompt"
    STYLE = "style"
    LIGHTING = "lighting"
    WARDROBE = "wardrobe"
    CAMERA = "camera"
    MODEL = "model"
    WORKFLOW = "workflow"
    SETTING = "setting"


@dataclass
class ContinuityRule(ContinuityRecord):
    """A rule applied during generation for consistency."""

    entity_type: ContinuityEntityType = ContinuityEntityType.CONTINUITY_RULE

    rule_type: RuleType = RuleType.INCLUDE
    category: RuleCategory = RuleCategory.PROMPT
    rule_text: str = ""             # The actual rule content
    reason: str = ""                # Why this rule exists
    confidence: float = 0.8         # 0-1, used for soft preferences
    source: str = "manual"          # manual, learned, dna, feedback
    active: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "talent_id": self.talent_id,
            "rule_type": self.rule_type.value,
            "category": self.category.value,
            "rule_text": self.rule_text,
            "confidence": self.confidence,
            "source": self.source,
            "active": self.active,
            "version": self.version,
            "approval_state": self.approval_state.value,
        }


# =============================================================================
# Continuity Note
# =============================================================================


@dataclass
class ContinuityNote(ContinuityRecord):
    """Free-text creative note with priority."""

    entity_type: ContinuityEntityType = ContinuityEntityType.CONTINUITY_NOTE

    title: str = ""
    content: str = ""
    category: str = "general"       # general, physical, style, voice, wardrobe
    priority: int = 5               # 1=highest, 10=lowest
    active: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "talent_id": self.talent_id,
            "title": self.title,
            "category": self.category,
            "priority": self.priority,
            "active": self.active,
            "version": self.version,
            "approval_state": self.approval_state.value,
        }


# =============================================================================
# LoRA Assignment
# =============================================================================


@dataclass
class LoRAAssignment(ContinuityRecord):
    """LoRA model version linked to a talent."""

    entity_type: ContinuityEntityType = ContinuityEntityType.LORA_ASSIGNMENT

    lora_model_id: str = ""
    lora_version: str = ""          # Specific version/checkpoint
    strength: float = 0.7
    trigger_word: str = ""
    is_primary: bool = False
    training_asset_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "talent_id": self.talent_id,
            "lora_model_id": self.lora_model_id,
            "lora_version": self.lora_version,
            "strength": self.strength,
            "trigger_word": self.trigger_word,
            "is_primary": self.is_primary,
            "version": self.version,
            "approval_state": self.approval_state.value,
        }


# =============================================================================
# Generation Context Snapshot (version-pinned)
# =============================================================================


@dataclass
class GenerationContext:
    """A frozen snapshot of continuity data for one generation.

    References EXACT versions so historical outputs can be reproduced.
    Never references mutable records directly.
    """

    talent_id: str = ""
    talent_version: int = 0
    preferences_version: int = 0
    lora_assignment_version: int = 0
    active_rules: list[dict] = field(default_factory=list)  # rule_id + version
    active_wardrobe: list[dict] = field(default_factory=list)  # item_id + version
    voice_assignment_version: int | None = None
    snapshot_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "talent_id": self.talent_id,
            "talent_version": self.talent_version,
            "preferences_version": self.preferences_version,
            "lora_assignment_version": self.lora_assignment_version,
            "active_rules_count": len(self.active_rules),
            "active_wardrobe_count": len(self.active_wardrobe),
            "voice_assignment_version": self.voice_assignment_version,
            "snapshot_at": self.snapshot_at,
        }


# =============================================================================
# Versioning
# =============================================================================


def increment_version(record: ContinuityRecord, updated_by: str) -> ContinuityRecord:
    """Increment version on mutation. Returns the same record (mutated)."""
    record.version += 1
    record.updated_by = updated_by
    record.updated_at = datetime.now(UTC).isoformat()
    return record


# =============================================================================
# Approval Transitions
# =============================================================================


VALID_APPROVAL_TRANSITIONS: dict[tuple[ApprovalState, ApprovalState], bool] = {
    (ApprovalState.DRAFT, ApprovalState.APPROVED): True,
    (ApprovalState.DRAFT, ApprovalState.RETIRED): True,
    (ApprovalState.APPROVED, ApprovalState.RETIRED): True,
    (ApprovalState.RETIRED, ApprovalState.APPROVED): True,  # Re-activate
}


class ApprovalError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def transition_approval(
    record: ContinuityRecord,
    new_state: ApprovalState,
    *,
    actor: str,
) -> ContinuityRecord:
    """Transition approval state with validation.

    Raises ApprovalError on invalid transition.
    """
    key = (record.approval_state, new_state)
    if key not in VALID_APPROVAL_TRANSITIONS:
        raise ApprovalError(
            f"Invalid approval transition: {record.approval_state.value} → {new_state.value}"
        )

    record.approval_state = new_state
    increment_version(record, actor)
    return record


# =============================================================================
# Ownership Validation
# =============================================================================


def validate_ownership(record: ContinuityRecord) -> list[str]:
    """Validate that a continuity record has required ownership fields.

    Returns list of missing fields. Empty = valid.
    """
    missing: list[str] = []
    if not record.org_id:
        missing.append("org_id")
    if not record.created_by:
        missing.append("created_by")
    return missing


# =============================================================================
# Legacy Mapping
# =============================================================================

# Maps legacy table/column to canonical entity
LEGACY_MAPPING: dict[str, dict] = {
    "talent.creative_dna": {
        "canonical": "CreativePreferences",
        "status": "deprecated",
        "migration": "Extract JSONB fields into versioned CreativePreferences record",
    },
    "creative_dna (table)": {
        "canonical": "CreativePreferences",
        "status": "compatibility",
        "migration": "Rows become versioned CreativePreferences with org_id backfill",
    },
    "continuity_notes (table)": {
        "canonical": "ContinuityNote",
        "status": "compatibility",
        "migration": "Add org_id, version, approval_state columns",
    },
    "creative_rules (table)": {
        "canonical": "ContinuityRule",
        "status": "compatibility",
        "migration": "Add org_id, version, approval_state columns",
    },
    "style_preferences (table)": {
        "canonical": "CreativePreferences",
        "status": "deprecated",
        "migration": "Merge atomic preferences into versioned CreativePreferences",
    },
    "talent_relationships (table)": {
        "canonical": "Relationship",
        "status": "compatibility",
        "migration": "Confirm org_id present; add version + approval_state",
    },
    "talent_voices (table)": {
        "canonical": "VoiceAssignment",
        "status": "compatibility",
        "migration": "Add org_id, version, approval_state, provider columns",
    },
}


# =============================================================================
# Entity Registry (for contract tests)
# =============================================================================

CANONICAL_ENTITIES: dict[str, dict] = {
    "TalentProfile": {
        "type": ContinuityEntityType.TALENT_PROFILE,
        "versioned": True,
        "requires_org_id": True,
        "requires_approval": True,
        "parent": None,
    },
    "CreativePreferences": {
        "type": ContinuityEntityType.CREATIVE_PREFERENCES,
        "versioned": True,
        "requires_org_id": True,
        "requires_approval": True,
        "parent": "TalentProfile",
    },
    "VoiceAssignment": {
        "type": ContinuityEntityType.VOICE_ASSIGNMENT,
        "versioned": True,
        "requires_org_id": True,
        "requires_approval": True,
        "parent": "TalentProfile",
    },
    "WardrobeItem": {
        "type": ContinuityEntityType.WARDROBE_ITEM,
        "versioned": True,
        "requires_org_id": True,
        "requires_approval": True,
        "parent": "TalentProfile",
    },
    "Relationship": {
        "type": ContinuityEntityType.RELATIONSHIP,
        "versioned": True,
        "requires_org_id": True,
        "requires_approval": True,
        "parent": None,  # Links two talents
    },
    "ContinuityRule": {
        "type": ContinuityEntityType.CONTINUITY_RULE,
        "versioned": True,
        "requires_org_id": True,
        "requires_approval": True,
        "parent": "TalentProfile",
    },
    "ContinuityNote": {
        "type": ContinuityEntityType.CONTINUITY_NOTE,
        "versioned": True,
        "requires_org_id": True,
        "requires_approval": True,
        "parent": "TalentProfile",
    },
    "LoRAAssignment": {
        "type": ContinuityEntityType.LORA_ASSIGNMENT,
        "versioned": True,
        "requires_org_id": True,
        "requires_approval": True,
        "parent": "TalentProfile",
    },
}
