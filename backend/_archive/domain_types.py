"""Domain Types — Story 089.

Explicit entity types for creative talent records. Each domain type has clear
semantics, required/prohibited fields, allowed capabilities, and participates
in shared assets, projects, context, and relationships predictably.

Domain Types:
    PERSON      — A real or fictional human character (AI influencer)
    CHARACTER   — A non-human character (mascot, creature, avatar)
    VOICE       — A voice profile (may exist independently of a person)
    WARDROBE    — A clothing item, outfit, or accessory
    PRODUCT     — A commercial product (for product photography/commercials)
    PROP        — A reusable object/item in scenes
    LOCATION    — A place, setting, or environment

Each type defines:
    - Required fields (validation fails without them)
    - Prohibited fields (fields that don't apply to this type)
    - Allowed capabilities (what this type can do)
    - Context assembly role (how it participates in generation)
    - Relationship rules (what it can connect to)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# =============================================================================
# Domain Types
# =============================================================================


class DomainType(StrEnum):
    PERSON = "person"           # Human character / AI influencer
    CHARACTER = "character"     # Non-human character
    VOICE = "voice"             # Voice profile
    WARDROBE = "wardrobe"       # Clothing / outfit / accessory
    PRODUCT = "product"         # Commercial product
    PROP = "prop"               # Reusable scene object
    LOCATION = "location"       # Place / environment


# =============================================================================
# Capabilities (what a domain type can do)
# =============================================================================


class Capability(StrEnum):
    HAS_LORA = "has_lora"                   # Can have LoRA training
    HAS_VOICE = "has_voice"                 # Can have voice assignment
    HAS_CREATIVE_DNA = "has_creative_dna"   # Can have creative preferences
    HAS_WARDROBE = "has_wardrobe"           # Can wear wardrobe items
    HAS_RELATIONSHIPS = "has_relationships" # Can have typed relationships
    GENERATES_IMAGES = "generates_images"   # Can be subject of image gen
    GENERATES_VIDEO = "generates_video"     # Can be subject of video gen
    GENERATES_AUDIO = "generates_audio"     # Can be used for audio gen
    HAS_CONTINUITY = "has_continuity"       # Can have continuity rules
    IS_SCENE_ELEMENT = "is_scene_element"   # Can appear in scene composition
    IS_TRAINABLE = "is_trainable"           # Can be trained (LoRA)
    HAS_PRODUCT_DNA = "has_product_dna"     # Object/product intelligence


# =============================================================================
# Type Definitions
# =============================================================================


@dataclass
class DomainTypeDefinition:
    """Contract for a domain type."""

    domain_type: DomainType
    display_name: str
    description: str

    # Field rules
    required_fields: set[str] = field(default_factory=set)
    prohibited_fields: set[str] = field(default_factory=set)
    optional_fields: set[str] = field(default_factory=set)

    # Capabilities
    capabilities: set[Capability] = field(default_factory=set)

    # Context assembly
    context_role: str = ""          # How it participates in generation context
    prompt_contribution: str = ""   # What it adds to prompts (subject, modifier, setting)

    # Relationship rules
    can_relate_to: set[DomainType] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "domain_type": self.domain_type.value,
            "display_name": self.display_name,
            "description": self.description,
            "required_fields": sorted(self.required_fields),
            "prohibited_fields": sorted(self.prohibited_fields),
            "capabilities": sorted(c.value for c in self.capabilities),
            "context_role": self.context_role,
            "prompt_contribution": self.prompt_contribution,
            "can_relate_to": sorted(t.value for t in self.can_relate_to),
        }


# =============================================================================
# Type Registry
# =============================================================================

DOMAIN_TYPE_REGISTRY: dict[DomainType, DomainTypeDefinition] = {
    DomainType.PERSON: DomainTypeDefinition(
        domain_type=DomainType.PERSON,
        display_name="Person",
        description="A real or fictional human character (AI influencer, model)",
        required_fields={"name", "org_id"},
        prohibited_fields={"sku", "price", "dimensions"},
        optional_fields={
            "height", "hair_color", "eye_color", "body_type", "ethnicity",
            "age_range", "persona", "visual_style", "negative_prompt", "trigger_word",
        },
        capabilities={
            Capability.HAS_LORA, Capability.HAS_VOICE, Capability.HAS_CREATIVE_DNA,
            Capability.HAS_WARDROBE, Capability.HAS_RELATIONSHIPS,
            Capability.GENERATES_IMAGES, Capability.GENERATES_VIDEO,
            Capability.HAS_CONTINUITY, Capability.IS_TRAINABLE,
            Capability.IS_SCENE_ELEMENT,
        },
        context_role="primary_subject",
        prompt_contribution="subject",
        can_relate_to={
            DomainType.PERSON, DomainType.CHARACTER, DomainType.WARDROBE,
            DomainType.PROP, DomainType.LOCATION, DomainType.PRODUCT,
        },
    ),
    DomainType.CHARACTER: DomainTypeDefinition(
        domain_type=DomainType.CHARACTER,
        display_name="Character",
        description="A non-human character (mascot, creature, avatar, stylized entity)",
        required_fields={"name", "org_id"},
        prohibited_fields={"sku", "price", "height", "ethnicity"},
        optional_fields={
            "persona", "visual_style", "negative_prompt", "trigger_word",
            "body_type", "hair_color", "eye_color",
        },
        capabilities={
            Capability.HAS_LORA, Capability.HAS_VOICE, Capability.HAS_CREATIVE_DNA,
            Capability.HAS_RELATIONSHIPS, Capability.GENERATES_IMAGES,
            Capability.GENERATES_VIDEO, Capability.HAS_CONTINUITY,
            Capability.IS_TRAINABLE, Capability.IS_SCENE_ELEMENT,
        },
        context_role="primary_subject",
        prompt_contribution="subject",
        can_relate_to={
            DomainType.PERSON, DomainType.CHARACTER, DomainType.WARDROBE,
            DomainType.PROP, DomainType.LOCATION,
        },
    ),
    DomainType.VOICE: DomainTypeDefinition(
        domain_type=DomainType.VOICE,
        display_name="Voice",
        description="A voice profile (can exist independently or linked to a person/character)",
        required_fields={"name", "org_id", "provider"},
        prohibited_fields={
            "height", "hair_color", "eye_color", "body_type",
            "sku", "price", "dimensions",
        },
        optional_fields={"voice_profile_id", "sample_url", "persona"},
        capabilities={
            Capability.GENERATES_AUDIO, Capability.HAS_RELATIONSHIPS,
        },
        context_role="voice_source",
        prompt_contribution="voice",
        can_relate_to={DomainType.PERSON, DomainType.CHARACTER},
    ),
    DomainType.WARDROBE: DomainTypeDefinition(
        domain_type=DomainType.WARDROBE,
        display_name="Wardrobe",
        description="A clothing item, outfit, or accessory",
        required_fields={"name", "org_id", "category"},
        prohibited_fields={
            "height", "hair_color", "eye_color", "body_type", "ethnicity",
            "persona", "sku", "price",
        },
        optional_fields={
            "visual_style", "negative_prompt", "prompt_fragment",
            "color", "style", "reference_asset_id",
        },
        capabilities={
            Capability.HAS_RELATIONSHIPS, Capability.IS_SCENE_ELEMENT,
            Capability.GENERATES_IMAGES, Capability.HAS_CONTINUITY,
        },
        context_role="wardrobe_modifier",
        prompt_contribution="modifier",
        can_relate_to={DomainType.PERSON, DomainType.CHARACTER, DomainType.WARDROBE},
    ),
    DomainType.PRODUCT: DomainTypeDefinition(
        domain_type=DomainType.PRODUCT,
        display_name="Product",
        description="A commercial product for photography, commercials, or catalogues",
        required_fields={"name", "org_id"},
        prohibited_fields={
            "height", "hair_color", "eye_color", "body_type", "ethnicity", "persona",
        },
        optional_fields={
            "sku", "price", "dimensions", "visual_style", "negative_prompt",
            "trigger_word", "brand_id",
        },
        capabilities={
            Capability.HAS_LORA, Capability.HAS_PRODUCT_DNA,
            Capability.HAS_RELATIONSHIPS, Capability.GENERATES_IMAGES,
            Capability.IS_SCENE_ELEMENT, Capability.IS_TRAINABLE,
            Capability.HAS_CONTINUITY,
        },
        context_role="product_subject",
        prompt_contribution="subject",
        can_relate_to={
            DomainType.PERSON, DomainType.CHARACTER, DomainType.PROP,
            DomainType.LOCATION, DomainType.PRODUCT,
        },
    ),
    DomainType.PROP: DomainTypeDefinition(
        domain_type=DomainType.PROP,
        display_name="Prop",
        description="A reusable object or item that appears in scenes",
        required_fields={"name", "org_id"},
        prohibited_fields={
            "height", "hair_color", "eye_color", "body_type", "ethnicity",
            "persona", "sku", "price",
        },
        optional_fields={
            "visual_style", "negative_prompt", "prompt_fragment", "category",
        },
        capabilities={
            Capability.HAS_RELATIONSHIPS, Capability.IS_SCENE_ELEMENT,
            Capability.GENERATES_IMAGES, Capability.HAS_CONTINUITY,
        },
        context_role="scene_element",
        prompt_contribution="modifier",
        can_relate_to={
            DomainType.PERSON, DomainType.CHARACTER, DomainType.PRODUCT,
            DomainType.LOCATION, DomainType.PROP,
        },
    ),
    DomainType.LOCATION: DomainTypeDefinition(
        domain_type=DomainType.LOCATION,
        display_name="Location",
        description="A place, setting, or environment for scene composition",
        required_fields={"name", "org_id"},
        prohibited_fields={
            "height", "hair_color", "eye_color", "body_type", "ethnicity",
            "persona", "sku", "price",
        },
        optional_fields={
            "visual_style", "negative_prompt", "prompt_fragment",
            "setting_type", "time_of_day", "weather",
        },
        capabilities={
            Capability.HAS_LORA, Capability.HAS_RELATIONSHIPS,
            Capability.IS_SCENE_ELEMENT, Capability.GENERATES_IMAGES,
            Capability.HAS_CONTINUITY, Capability.IS_TRAINABLE,
        },
        context_role="scene_setting",
        prompt_contribution="setting",
        can_relate_to={
            DomainType.PERSON, DomainType.CHARACTER, DomainType.PRODUCT,
            DomainType.PROP, DomainType.LOCATION,
        },
    ),
}


# =============================================================================
# Validation
# =============================================================================


@dataclass
class ValidationResult:
    """Result of validating a record against its domain type."""

    valid: bool = True
    missing_required: list[str] = field(default_factory=list)
    prohibited_present: list[str] = field(default_factory=list)
    capability_violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_record(
    domain_type: DomainType,
    record_fields: dict[str, Any],
) -> ValidationResult:
    """Validate a record's fields against its domain type definition.

    Returns ValidationResult with missing/prohibited/capability issues.
    """
    definition = DOMAIN_TYPE_REGISTRY.get(domain_type)
    if definition is None:
        return ValidationResult(
            valid=False,
            warnings=[f"Unknown domain type: {domain_type}"],
        )

    result = ValidationResult()

    # Check required fields
    for req_field in definition.required_fields:
        value = record_fields.get(req_field)
        if value is None or value == "":
            result.missing_required.append(req_field)

    # Check prohibited fields
    for prohibited in definition.prohibited_fields:
        value = record_fields.get(prohibited)
        if value is not None and value != "":
            result.prohibited_present.append(prohibited)

    if result.missing_required or result.prohibited_present:
        result.valid = False

    return result


def check_capability(domain_type: DomainType, capability: Capability) -> bool:
    """Check if a domain type has a specific capability."""
    definition = DOMAIN_TYPE_REGISTRY.get(domain_type)
    if definition is None:
        return False
    return capability in definition.capabilities


def get_capabilities(domain_type: DomainType) -> set[Capability]:
    """Get all capabilities for a domain type."""
    definition = DOMAIN_TYPE_REGISTRY.get(domain_type)
    if definition is None:
        return set()
    return definition.capabilities


# =============================================================================
# Relationship Validation
# =============================================================================


def can_relate(source_type: DomainType, target_type: DomainType) -> bool:
    """Check if source domain type can form a relationship with target type."""
    definition = DOMAIN_TYPE_REGISTRY.get(source_type)
    if definition is None:
        return False
    return target_type in definition.can_relate_to


# =============================================================================
# Legacy Classification
# =============================================================================


class LegacyClassification(StrEnum):
    CONFIDENT = "confident"         # Clear mapping based on fields
    INFERRED = "inferred"           # Best guess from available data
    AMBIGUOUS = "ambiguous"         # Cannot determine, needs user input
    UNKNOWN = "unknown"             # No matching type


@dataclass
class ClassificationResult:
    """Result of classifying a legacy generic talent record."""

    domain_type: DomainType | None = None
    classification: LegacyClassification = LegacyClassification.UNKNOWN
    confidence: float = 0.0
    reason: str = ""
    alternative_types: list[DomainType] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "domain_type": self.domain_type.value if self.domain_type else None,
            "classification": self.classification.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "alternative_types": [t.value for t in self.alternative_types],
        }


def classify_legacy_record(record: dict[str, Any]) -> ClassificationResult:
    """Classify a legacy generic talent record into a domain type.

    Uses heuristics based on available fields:
    - Has height/hair/eye/body → PERSON
    - Has voice_profile_id/provider → VOICE
    - Has category in wardrobe terms → WARDROBE
    - Has sku/price/dimensions → PRODUCT
    - Has setting_type/time_of_day → LOCATION
    - Has persona but no physical → CHARACTER
    - Otherwise → AMBIGUOUS
    """
    # Physical attributes → PERSON
    physical_fields = {"height", "hair_color", "eye_color", "body_type", "ethnicity"}
    has_physical = any(record.get(f) for f in physical_fields)

    # Voice indicators
    has_voice = bool(record.get("voice_profile_id") or record.get("provider"))

    # Product indicators
    has_product = bool(record.get("sku") or record.get("price") or record.get("dimensions"))

    # Location indicators
    has_location = bool(record.get("setting_type") or record.get("time_of_day"))

    # Wardrobe indicators
    wardrobe_categories = {"top", "bottom", "full_outfit", "accessory", "footwear", "dress", "shirt"}
    category = str(record.get("category", "")).lower()
    has_wardrobe = category in wardrobe_categories

    # Classification logic
    if has_physical:
        return ClassificationResult(
            domain_type=DomainType.PERSON,
            classification=LegacyClassification.CONFIDENT,
            confidence=0.9,
            reason="Has physical attributes (height/hair/eye/body)",
        )

    if has_voice and not has_physical:
        return ClassificationResult(
            domain_type=DomainType.VOICE,
            classification=LegacyClassification.CONFIDENT,
            confidence=0.85,
            reason="Has voice_profile_id or provider without physical attributes",
        )

    if has_product:
        return ClassificationResult(
            domain_type=DomainType.PRODUCT,
            classification=LegacyClassification.CONFIDENT,
            confidence=0.9,
            reason="Has product fields (sku/price/dimensions)",
        )

    if has_location:
        return ClassificationResult(
            domain_type=DomainType.LOCATION,
            classification=LegacyClassification.INFERRED,
            confidence=0.7,
            reason="Has location fields (setting_type/time_of_day)",
        )

    if has_wardrobe:
        return ClassificationResult(
            domain_type=DomainType.WARDROBE,
            classification=LegacyClassification.CONFIDENT,
            confidence=0.85,
            reason=f"Category '{category}' matches wardrobe taxonomy",
        )

    # Persona without physical → CHARACTER
    if record.get("persona") and not has_physical:
        return ClassificationResult(
            domain_type=DomainType.CHARACTER,
            classification=LegacyClassification.INFERRED,
            confidence=0.6,
            reason="Has persona but no physical attributes",
            alternative_types=[DomainType.PERSON],
        )

    # Name only → AMBIGUOUS
    if record.get("name"):
        return ClassificationResult(
            domain_type=DomainType.PERSON,
            classification=LegacyClassification.AMBIGUOUS,
            confidence=0.3,
            reason="Only name available — cannot determine type",
            alternative_types=[DomainType.CHARACTER, DomainType.PROP],
        )

    return ClassificationResult(
        domain_type=None,
        classification=LegacyClassification.UNKNOWN,
        confidence=0.0,
        reason="No identifying fields present",
    )


# =============================================================================
# Context Assembly Role
# =============================================================================


def get_context_role(domain_type: DomainType) -> str:
    """Get the context assembly role for a domain type."""
    definition = DOMAIN_TYPE_REGISTRY.get(domain_type)
    return definition.context_role if definition else ""


def get_prompt_contribution(domain_type: DomainType) -> str:
    """Get how this type contributes to generation prompts."""
    definition = DOMAIN_TYPE_REGISTRY.get(domain_type)
    return definition.prompt_contribution if definition else ""
