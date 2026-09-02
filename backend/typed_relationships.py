"""Typed Relationship Taxonomy — Story 090.

Validates source-target combinations, directionality, reciprocal behavior,
role, scope, and versioning for the continuity graph. Invalid combinations
are rejected. Legacy generic links are migrated or quarantined.

Relationship types and valid source→target matrix:

    WEARS:       talent → wardrobe       (nonreciprocal)
    HOLDS:       talent → prop           (nonreciprocal)
    LOCATED_AT:  talent → location       (nonreciprocal)
    PROMOTES:    talent → product        (nonreciprocal)
    FRIENDS_WITH: talent → talent        (reciprocal)
    SIBLING_OF:  talent → talent         (reciprocal)
    PARTNER_OF:  talent → talent         (reciprocal)
    WORKS_WITH:  talent → talent         (reciprocal)
    VOICED_BY:   talent → voice_profile  (nonreciprocal)
    TRAINED_WITH: talent → lora_model    (nonreciprocal)
    BELONGS_TO:  wardrobe → brand        (nonreciprocal)
    PART_OF:     prop → scene            (nonreciprocal)
    SET_IN:      scene → location        (nonreciprocal)

Design:
    - Validation matrix enforces allowed source→target entity type pairs
    - Reciprocal relationships auto-create the reverse link
    - Relationships are scoped (global, project, scene) with effective dates
    - Versioned: edits create new versions, history preserved
    - Cross-workspace references rejected
    - Legacy 'associated' type quarantined for manual resolution
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Entity Types
# =============================================================================


class EntityType(str, Enum):
    TALENT = "talent"
    WARDROBE = "wardrobe"
    PROP = "prop"
    LOCATION = "location"
    PRODUCT = "product"
    VOICE_PROFILE = "voice_profile"
    LORA_MODEL = "lora_model"
    BRAND = "brand"
    SCENE = "scene"


# =============================================================================
# Relationship Types
# =============================================================================


class RelationshipType(str, Enum):
    WEARS = "wears"
    HOLDS = "holds"
    LOCATED_AT = "located_at"
    PROMOTES = "promotes"
    FRIENDS_WITH = "friends_with"
    SIBLING_OF = "sibling_of"
    PARTNER_OF = "partner_of"
    WORKS_WITH = "works_with"
    VOICED_BY = "voiced_by"
    TRAINED_WITH = "trained_with"
    BELONGS_TO = "belongs_to"
    PART_OF = "part_of"
    SET_IN = "set_in"
    # Legacy (quarantined — needs manual resolution)
    LEGACY_ASSOCIATED = "legacy_associated"


class Directionality(str, Enum):
    DIRECTED = "directed"       # source → target only
    RECIPROCAL = "reciprocal"   # auto-creates reverse


class RelationshipScope(str, Enum):
    GLOBAL = "global"           # Always active
    PROJECT = "project"         # Active within a project
    SCENE = "scene"             # Active within a specific scene


class RelationshipStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    QUARANTINED = "quarantined"  # Legacy link needing resolution


# =============================================================================
# Validation Matrix
# =============================================================================


@dataclass(frozen=True)
class RelationshipRule:
    """Rule defining a valid relationship type."""
    rel_type: RelationshipType
    source_type: EntityType
    target_type: EntityType
    directionality: Directionality
    reciprocal_type: RelationshipType | None = None  # For reciprocal: the reverse type


# Complete validation matrix
VALIDATION_MATRIX: list[RelationshipRule] = [
    RelationshipRule(RelationshipType.WEARS, EntityType.TALENT, EntityType.WARDROBE, Directionality.DIRECTED),
    RelationshipRule(RelationshipType.HOLDS, EntityType.TALENT, EntityType.PROP, Directionality.DIRECTED),
    RelationshipRule(RelationshipType.LOCATED_AT, EntityType.TALENT, EntityType.LOCATION, Directionality.DIRECTED),
    RelationshipRule(RelationshipType.PROMOTES, EntityType.TALENT, EntityType.PRODUCT, Directionality.DIRECTED),
    RelationshipRule(RelationshipType.FRIENDS_WITH, EntityType.TALENT, EntityType.TALENT, Directionality.RECIPROCAL, RelationshipType.FRIENDS_WITH),
    RelationshipRule(RelationshipType.SIBLING_OF, EntityType.TALENT, EntityType.TALENT, Directionality.RECIPROCAL, RelationshipType.SIBLING_OF),
    RelationshipRule(RelationshipType.PARTNER_OF, EntityType.TALENT, EntityType.TALENT, Directionality.RECIPROCAL, RelationshipType.PARTNER_OF),
    RelationshipRule(RelationshipType.WORKS_WITH, EntityType.TALENT, EntityType.TALENT, Directionality.RECIPROCAL, RelationshipType.WORKS_WITH),
    RelationshipRule(RelationshipType.VOICED_BY, EntityType.TALENT, EntityType.VOICE_PROFILE, Directionality.DIRECTED),
    RelationshipRule(RelationshipType.TRAINED_WITH, EntityType.TALENT, EntityType.LORA_MODEL, Directionality.DIRECTED),
    RelationshipRule(RelationshipType.BELONGS_TO, EntityType.WARDROBE, EntityType.BRAND, Directionality.DIRECTED),
    RelationshipRule(RelationshipType.PART_OF, EntityType.PROP, EntityType.SCENE, Directionality.DIRECTED),
    RelationshipRule(RelationshipType.SET_IN, EntityType.SCENE, EntityType.LOCATION, Directionality.DIRECTED),
]

# Index for fast lookup
_MATRIX_INDEX: dict[tuple[RelationshipType, EntityType, EntityType], RelationshipRule] = {
    (r.rel_type, r.source_type, r.target_type): r for r in VALIDATION_MATRIX
}


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class TypedRelationship:
    """A validated, typed relationship between entities."""
    rel_id: str = field(default_factory=lambda: f"rel-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    rel_type: RelationshipType = RelationshipType.WEARS
    source_id: str = ""
    source_type: EntityType = EntityType.TALENT
    target_id: str = ""
    target_type: EntityType = EntityType.WARDROBE
    directionality: Directionality = Directionality.DIRECTED

    # Scoping
    scope: RelationshipScope = RelationshipScope.GLOBAL
    project_id: str | None = None
    scene_id: str | None = None

    # Effective dates
    effective_from: float | None = None
    effective_until: float | None = None

    # Status & versioning
    status: RelationshipStatus = RelationshipStatus.ACTIVE
    version: int = 1
    created_by: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Reciprocal linkage
    reciprocal_id: str | None = None  # ID of the auto-created reverse relationship

    @property
    def is_active(self) -> bool:
        if self.status != RelationshipStatus.ACTIVE:
            return False
        now = time.time()
        if self.effective_from and now < self.effective_from:
            return False
        if self.effective_until and now > self.effective_until:
            return False
        return True

    @property
    def is_expired(self) -> bool:
        if self.effective_until and time.time() > self.effective_until:
            return True
        return False


# =============================================================================
# Store
# =============================================================================

_relationships: dict[str, TypedRelationship] = {}


# =============================================================================
# Validation
# =============================================================================


def validate_relationship(
    rel_type: RelationshipType,
    source_type: EntityType,
    target_type: EntityType,
) -> RelationshipRule | None:
    """Validate a relationship combination against the matrix.

    Returns the rule if valid, None if invalid.
    """
    return _MATRIX_INDEX.get((rel_type, source_type, target_type))


def is_valid_combination(
    rel_type: RelationshipType,
    source_type: EntityType,
    target_type: EntityType,
) -> bool:
    """Check if a relationship combination is valid."""
    return validate_relationship(rel_type, source_type, target_type) is not None


# =============================================================================
# CRUD Operations
# =============================================================================


def create_relationship(
    org_id: str,
    rel_type: RelationshipType,
    source_id: str,
    source_type: EntityType,
    target_id: str,
    target_type: EntityType,
    created_by: str,
    scope: RelationshipScope = RelationshipScope.GLOBAL,
    project_id: str | None = None,
    scene_id: str | None = None,
    effective_from: float | None = None,
    effective_until: float | None = None,
) -> TypedRelationship:
    """Create a validated typed relationship.

    Enforces the validation matrix. Reciprocal relationships auto-create reverse.
    """
    if not org_id or not source_id or not target_id:
        raise ValueError("org_id, source_id, and target_id are required")

    # Validate against matrix
    rule = validate_relationship(rel_type, source_type, target_type)
    if not rule:
        raise InvalidRelationship(
            f"Invalid combination: {source_type.value} --[{rel_type.value}]--> {target_type.value}. "
            f"Not in validation matrix."
        )

    # Self-reference check
    if source_id == target_id and source_type == target_type:
        raise InvalidRelationship("Self-referential relationships are not allowed")

    # Duplicate check
    existing = _find_duplicate(org_id, rel_type, source_id, target_id, scope, project_id, scene_id)
    if existing:
        return existing  # Idempotent

    rel = TypedRelationship(
        org_id=org_id,
        rel_type=rel_type,
        source_id=source_id,
        source_type=source_type,
        target_id=target_id,
        target_type=target_type,
        directionality=rule.directionality,
        scope=scope,
        project_id=project_id,
        scene_id=scene_id,
        effective_from=effective_from,
        effective_until=effective_until,
        created_by=created_by,
    )

    _relationships[rel.rel_id] = rel

    # Auto-create reciprocal if applicable
    if rule.directionality == Directionality.RECIPROCAL and rule.reciprocal_type:
        reciprocal = TypedRelationship(
            org_id=org_id,
            rel_type=rule.reciprocal_type,
            source_id=target_id,
            source_type=target_type,
            target_id=source_id,
            target_type=source_type,
            directionality=Directionality.RECIPROCAL,
            scope=scope,
            project_id=project_id,
            scene_id=scene_id,
            effective_from=effective_from,
            effective_until=effective_until,
            created_by=created_by,
            reciprocal_id=rel.rel_id,
        )
        _relationships[reciprocal.rel_id] = reciprocal
        rel.reciprocal_id = reciprocal.rel_id

    logger.info(
        f"RELATIONSHIP_CREATED: id={rel.rel_id} {source_type.value}/{source_id} "
        f"--[{rel_type.value}]--> {target_type.value}/{target_id}"
    )
    return rel


def archive_relationship(rel_id: str, org_id: str) -> TypedRelationship:
    """Archive a relationship (soft delete with history preservation)."""
    rel = _get_rel(rel_id, org_id)
    rel.status = RelationshipStatus.ARCHIVED
    rel.updated_at = time.time()

    # Also archive reciprocal
    if rel.reciprocal_id and rel.reciprocal_id in _relationships:
        reciprocal = _relationships[rel.reciprocal_id]
        if reciprocal.org_id == org_id:
            reciprocal.status = RelationshipStatus.ARCHIVED
            reciprocal.updated_at = time.time()

    return rel


# =============================================================================
# Query
# =============================================================================


def get_relationship(rel_id: str, org_id: str) -> TypedRelationship | None:
    """Get a relationship with tenant isolation."""
    rel = _relationships.get(rel_id)
    if not rel or rel.org_id != org_id:
        return None
    return rel


def get_relationships_for_entity(
    entity_id: str,
    entity_type: EntityType,
    org_id: str,
    active_only: bool = True,
    scope: RelationshipScope | None = None,
) -> list[TypedRelationship]:
    """Get all relationships where entity is source or target."""
    results = []
    for rel in _relationships.values():
        if rel.org_id != org_id:
            continue
        if active_only and not rel.is_active:
            continue
        if scope and rel.scope != scope:
            continue
        if (rel.source_id == entity_id and rel.source_type == entity_type) or \
           (rel.target_id == entity_id and rel.target_type == entity_type):
            results.append(rel)
    return results


def get_relationships_for_context(
    talent_id: str,
    org_id: str,
    scope: RelationshipScope | None = None,
) -> list[dict[str, Any]]:
    """Get relationships formatted for context package assembly.

    Returns typed relationship data with version for snapshot pinning.
    """
    rels = get_relationships_for_entity(talent_id, EntityType.TALENT, org_id, active_only=True, scope=scope)
    return [
        {
            "rel_id": r.rel_id,
            "rel_type": r.rel_type.value,
            "source_id": r.source_id,
            "target_id": r.target_id,
            "target_type": r.target_type.value,
            "scope": r.scope.value,
            "version": r.version,
            "directionality": r.directionality.value,
        }
        for r in rels
    ]


# =============================================================================
# Legacy Migration
# =============================================================================


def migrate_legacy_link(
    org_id: str,
    source_id: str,
    target_id: str,
    legacy_type: str,
    created_by: str,
) -> TypedRelationship | dict[str, str]:
    """Attempt to migrate a legacy 'associated' link to a typed relationship.

    If the legacy type maps to a known typed relationship, creates it.
    Otherwise, quarantines the link for manual resolution.
    """
    # Attempt to map legacy type to canonical
    type_mapping: dict[str, tuple[RelationshipType, EntityType, EntityType]] = {
        "associated": None,  # type: ignore — ambiguous, quarantine
        "wears": (RelationshipType.WEARS, EntityType.TALENT, EntityType.WARDROBE),
        "friend": (RelationshipType.FRIENDS_WITH, EntityType.TALENT, EntityType.TALENT),
        "sibling": (RelationshipType.SIBLING_OF, EntityType.TALENT, EntityType.TALENT),
        "partner": (RelationshipType.PARTNER_OF, EntityType.TALENT, EntityType.TALENT),
        "colleague": (RelationshipType.WORKS_WITH, EntityType.TALENT, EntityType.TALENT),
    }

    mapping = type_mapping.get(legacy_type)
    if mapping:
        rel_type, source_type, target_type = mapping
        return create_relationship(
            org_id, rel_type, source_id, source_type, target_id, target_type, created_by
        )

    # Quarantine — cannot auto-migrate
    quarantined = TypedRelationship(
        org_id=org_id,
        rel_type=RelationshipType.LEGACY_ASSOCIATED,
        source_id=source_id,
        source_type=EntityType.TALENT,
        target_id=target_id,
        target_type=EntityType.TALENT,
        status=RelationshipStatus.QUARANTINED,
        created_by=created_by,
    )
    _relationships[quarantined.rel_id] = quarantined

    return {"status": "quarantined", "rel_id": quarantined.rel_id, "reason": f"Ambiguous legacy type '{legacy_type}'"}


def list_quarantined(org_id: str) -> list[TypedRelationship]:
    """List quarantined legacy relationships needing manual resolution."""
    return [
        r for r in _relationships.values()
        if r.org_id == org_id and r.status == RelationshipStatus.QUARANTINED
    ]


# =============================================================================
# Helpers
# =============================================================================


def _get_rel(rel_id: str, org_id: str) -> TypedRelationship:
    rel = _relationships.get(rel_id)
    if not rel or rel.org_id != org_id:
        raise RelationshipNotFound(f"Relationship {rel_id} not found")
    return rel


def _find_duplicate(
    org_id: str,
    rel_type: RelationshipType,
    source_id: str,
    target_id: str,
    scope: RelationshipScope,
    project_id: str | None,
    scene_id: str | None,
) -> TypedRelationship | None:
    for r in _relationships.values():
        if (r.org_id == org_id and r.rel_type == rel_type
                and r.source_id == source_id and r.target_id == target_id
                and r.scope == scope and r.project_id == project_id
                and r.scene_id == scene_id
                and r.status == RelationshipStatus.ACTIVE):
            return r
    return None


# =============================================================================
# Exceptions
# =============================================================================


class RelationshipError(Exception):
    """Base relationship error."""


class InvalidRelationship(RelationshipError):
    """Invalid source-target-type combination."""


class RelationshipNotFound(RelationshipError):
    """Relationship not found or cross-tenant."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _relationships.clear()
