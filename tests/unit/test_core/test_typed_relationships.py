"""Typed relationship taxonomy tests — Story 090.

Tests prove:
  - Valid combinations pass matrix validation
  - Invalid combinations are rejected
  - Reciprocal relationships auto-create reverse
  - Nonreciprocal relationships don't create reverse
  - Expired scope detected
  - Archived (deleted target) relationships handled
  - Cross-tenant access rejected
  - Legacy 'associated' links quarantined
  - Legacy mappable links migrated
  - Context integration returns typed data
  - Duplicate creation is idempotent
  - Self-reference rejected
"""

import time

import pytest

from backend.typed_relationships import (
    Directionality,
    EntityType,
    InvalidRelationship,
    RelationshipNotFound,
    RelationshipScope,
    RelationshipStatus,
    RelationshipType,
    _reset_store,
    archive_relationship,
    create_relationship,
    get_relationship,
    get_relationships_for_context,
    get_relationships_for_entity,
    is_valid_combination,
    list_quarantined,
    migrate_legacy_link,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
USER = "user-001"


# =============================================================================
# Valid Combinations
# =============================================================================


@pytest.mark.unit
class TestValidCombinations:

    def test_talent_wears_wardrobe(self):
        assert is_valid_combination(RelationshipType.WEARS, EntityType.TALENT, EntityType.WARDROBE)

    def test_talent_holds_prop(self):
        assert is_valid_combination(RelationshipType.HOLDS, EntityType.TALENT, EntityType.PROP)

    def test_talent_located_at_location(self):
        assert is_valid_combination(RelationshipType.LOCATED_AT, EntityType.TALENT, EntityType.LOCATION)

    def test_talent_promotes_product(self):
        assert is_valid_combination(RelationshipType.PROMOTES, EntityType.TALENT, EntityType.PRODUCT)

    def test_talent_friends_with_talent(self):
        assert is_valid_combination(RelationshipType.FRIENDS_WITH, EntityType.TALENT, EntityType.TALENT)

    def test_talent_voiced_by_voice_profile(self):
        assert is_valid_combination(RelationshipType.VOICED_BY, EntityType.TALENT, EntityType.VOICE_PROFILE)

    def test_talent_trained_with_lora(self):
        assert is_valid_combination(RelationshipType.TRAINED_WITH, EntityType.TALENT, EntityType.LORA_MODEL)

    def test_scene_set_in_location(self):
        assert is_valid_combination(RelationshipType.SET_IN, EntityType.SCENE, EntityType.LOCATION)


# =============================================================================
# Invalid Combinations
# =============================================================================


@pytest.mark.unit
class TestInvalidCombinations:

    def test_prop_cannot_wear_wardrobe(self):
        assert not is_valid_combination(RelationshipType.WEARS, EntityType.PROP, EntityType.WARDROBE)

    def test_voice_cannot_be_located(self):
        assert not is_valid_combination(RelationshipType.LOCATED_AT, EntityType.VOICE_PROFILE, EntityType.LOCATION)

    def test_wardrobe_cannot_promote_product(self):
        assert not is_valid_combination(RelationshipType.PROMOTES, EntityType.WARDROBE, EntityType.PRODUCT)

    def test_location_cannot_wear(self):
        assert not is_valid_combination(RelationshipType.WEARS, EntityType.LOCATION, EntityType.WARDROBE)

    def test_invalid_combination_raises_on_create(self):
        with pytest.raises(InvalidRelationship, match="Not in validation matrix"):
            create_relationship(
                ORG, RelationshipType.WEARS,
                "obj-1", EntityType.PROP,
                "w-1", EntityType.WARDROBE,
                USER,
            )

    def test_self_reference_rejected(self):
        with pytest.raises(InvalidRelationship, match="Self-referential"):
            create_relationship(
                ORG, RelationshipType.FRIENDS_WITH,
                "talent-1", EntityType.TALENT,
                "talent-1", EntityType.TALENT,
                USER,
            )


# =============================================================================
# Reciprocal Relationships
# =============================================================================


@pytest.mark.unit
class TestReciprocal:

    def test_friends_with_creates_reverse(self):
        rel = create_relationship(
            ORG, RelationshipType.FRIENDS_WITH,
            "alice", EntityType.TALENT,
            "bob", EntityType.TALENT,
            USER,
        )
        assert rel.reciprocal_id is not None
        reciprocal = get_relationship(rel.reciprocal_id, ORG)
        assert reciprocal is not None
        assert reciprocal.source_id == "bob"
        assert reciprocal.target_id == "alice"
        assert reciprocal.rel_type == RelationshipType.FRIENDS_WITH

    def test_wears_does_not_create_reverse(self):
        rel = create_relationship(
            ORG, RelationshipType.WEARS,
            "talent-1", EntityType.TALENT,
            "dress-1", EntityType.WARDROBE,
            USER,
        )
        assert rel.reciprocal_id is None

    def test_archive_archives_reciprocal(self):
        rel = create_relationship(
            ORG, RelationshipType.SIBLING_OF,
            "a", EntityType.TALENT,
            "b", EntityType.TALENT,
            USER,
        )
        archive_relationship(rel.rel_id, ORG)
        reciprocal = get_relationship(rel.reciprocal_id, ORG)
        assert reciprocal.status == RelationshipStatus.ARCHIVED


# =============================================================================
# Expired Scope
# =============================================================================


@pytest.mark.unit
class TestExpiredScope:

    def test_expired_relationship_not_active(self):
        rel = create_relationship(
            ORG, RelationshipType.WEARS,
            "t-1", EntityType.TALENT,
            "w-1", EntityType.WARDROBE,
            USER,
            effective_until=time.time() - 3600,  # Expired 1 hour ago
        )
        assert rel.is_active is False
        assert rel.is_expired is True

    def test_future_relationship_not_yet_active(self):
        rel = create_relationship(
            ORG, RelationshipType.LOCATED_AT,
            "t-1", EntityType.TALENT,
            "loc-1", EntityType.LOCATION,
            USER,
            effective_from=time.time() + 3600,  # Starts in 1 hour
        )
        assert rel.is_active is False

    def test_active_only_filter_excludes_expired(self):
        create_relationship(
            ORG, RelationshipType.WEARS,
            "t-1", EntityType.TALENT,
            "w-1", EntityType.WARDROBE,
            USER,
            effective_until=time.time() - 100,
        )
        create_relationship(
            ORG, RelationshipType.HOLDS,
            "t-1", EntityType.TALENT,
            "p-1", EntityType.PROP,
            USER,
        )
        active = get_relationships_for_entity("t-1", EntityType.TALENT, ORG, active_only=True)
        assert len(active) == 1
        assert active[0].rel_type == RelationshipType.HOLDS


# =============================================================================
# Cross-Tenant
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_get_returns_none(self):
        rel = create_relationship(
            ORG, RelationshipType.WEARS,
            "t-1", EntityType.TALENT, "w-1", EntityType.WARDROBE, USER,
        )
        assert get_relationship(rel.rel_id, OTHER_ORG) is None

    def test_cross_tenant_archive_raises(self):
        rel = create_relationship(
            ORG, RelationshipType.WEARS,
            "t-1", EntityType.TALENT, "w-1", EntityType.WARDROBE, USER,
        )
        with pytest.raises(RelationshipNotFound):
            archive_relationship(rel.rel_id, OTHER_ORG)

    def test_cross_tenant_entity_query_empty(self):
        create_relationship(
            ORG, RelationshipType.WEARS,
            "t-1", EntityType.TALENT, "w-1", EntityType.WARDROBE, USER,
        )
        results = get_relationships_for_entity("t-1", EntityType.TALENT, OTHER_ORG)
        assert results == []


# =============================================================================
# Legacy Migration
# =============================================================================


@pytest.mark.unit
class TestLegacyMigration:

    def test_mappable_legacy_link_migrated(self):
        result = migrate_legacy_link(ORG, "alice", "bob", "friend", USER)
        assert isinstance(result, TypedRelationship)  # noqa: F821
        assert result.rel_type == RelationshipType.FRIENDS_WITH

    def test_ambiguous_legacy_link_quarantined(self):
        result = migrate_legacy_link(ORG, "a", "b", "associated", USER)
        assert isinstance(result, dict)
        assert result["status"] == "quarantined"

    def test_quarantined_links_listable(self):
        migrate_legacy_link(ORG, "a", "b", "associated", USER)
        migrate_legacy_link(ORG, "c", "d", "associated", USER)
        quarantined = list_quarantined(ORG)
        assert len(quarantined) == 2
        assert all(q.status == RelationshipStatus.QUARANTINED for q in quarantined)

    def test_quarantined_scoped_to_org(self):
        migrate_legacy_link(ORG, "a", "b", "associated", USER)
        migrate_legacy_link(OTHER_ORG, "x", "y", "associated", "other")
        assert len(list_quarantined(ORG)) == 1
        assert len(list_quarantined(OTHER_ORG)) == 1


# =============================================================================
# Context Integration
# =============================================================================


@pytest.mark.unit
class TestContextIntegration:

    def test_context_returns_typed_data(self):
        create_relationship(
            ORG, RelationshipType.WEARS,
            "talent-1", EntityType.TALENT, "dress-1", EntityType.WARDROBE, USER,
        )
        create_relationship(
            ORG, RelationshipType.LOCATED_AT,
            "talent-1", EntityType.TALENT, "beach", EntityType.LOCATION, USER,
        )
        context = get_relationships_for_context("talent-1", ORG)
        assert len(context) == 2
        assert all("rel_type" in c for c in context)
        assert all("version" in c for c in context)

    def test_context_excludes_expired(self):
        create_relationship(
            ORG, RelationshipType.WEARS,
            "t-1", EntityType.TALENT, "w-1", EntityType.WARDROBE, USER,
            effective_until=time.time() - 100,
        )
        context = get_relationships_for_context("t-1", ORG)
        assert len(context) == 0


# =============================================================================
# Idempotency
# =============================================================================


@pytest.mark.unit
class TestIdempotency:

    def test_duplicate_creation_returns_existing(self):
        r1 = create_relationship(
            ORG, RelationshipType.WEARS,
            "t-1", EntityType.TALENT, "w-1", EntityType.WARDROBE, USER,
        )
        r2 = create_relationship(
            ORG, RelationshipType.WEARS,
            "t-1", EntityType.TALENT, "w-1", EntityType.WARDROBE, USER,
        )
        assert r1.rel_id == r2.rel_id


# Import the TypedRelationship type for isinstance check
from backend.typed_relationships import TypedRelationship  # noqa: E402
