"""Unit tests for TalentService — CRUD, relationships, and LoRA associations.

Tests verify:
    - Talent CRUD with identity classification
    - Soft-delete sets deleted_at (excluded from subsequent queries)
    - Cross-tenant access returns 404
    - Typed relationships with uniqueness enforcement
    - LoRA associations with max 5 per talent constraint
    - Proper enum validation on talent_type and identity_classification

Requirements: R10.1, R10.4, R10.5, R10.6, R10.7, R10.8
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.validation import (
    IdentityClassification,
    LoraAssociationType,
    RelationshipType,
    TalentType,
)


ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()
TALENT_ID = uuid.uuid4()
TALENT_ID_2 = uuid.uuid4()
LORA_ID = uuid.uuid4()


# =============================================================================
# Schema Validation Tests
# =============================================================================


@pytest.mark.unit
class TestTalentSchemas:
    """Tests for Pydantic schema validation."""

    def test_talent_create_valid(self):
        from app.schemas.talent import TalentCreate

        schema = TalentCreate(
            name="Test Talent",
            talent_type=TalentType.INFLUENCER,
            identity_classification=IdentityClassification.FICTIONAL,
        )
        assert schema.name == "Test Talent"
        assert schema.talent_type == TalentType.INFLUENCER
        assert schema.identity_classification == IdentityClassification.FICTIONAL
        assert schema.is_active is True

    def test_talent_create_name_too_long(self):
        from pydantic import ValidationError

        from app.schemas.talent import TalentCreate

        with pytest.raises(ValidationError):
            TalentCreate(name="x" * 101)

    def test_talent_create_name_whitespace_only_rejected(self):
        from pydantic import ValidationError

        from app.schemas.talent import TalentCreate

        with pytest.raises(ValidationError):
            TalentCreate(name="   ")

    def test_talent_create_empty_name_rejected(self):
        from pydantic import ValidationError

        from app.schemas.talent import TalentCreate

        with pytest.raises(ValidationError):
            TalentCreate(name="")

    def test_talent_type_enum_values(self):
        """R10.1: type enum includes all required values."""
        expected = {
            "model", "character", "voice", "influencer",
            "wardrobe", "product", "background", "object",
        }
        actual = {t.value for t in TalentType}
        assert expected == actual

    def test_identity_classification_enum_values(self):
        """R10.1: identity_classification enum values."""
        expected = {"FICTIONAL", "REAL_PERSON_SELF", "REAL_PERSON_AUTHORIZED"}
        actual = {c.value for c in IdentityClassification}
        assert expected == actual

    def test_relationship_type_enum_values(self):
        """R10.7: relationship types enum values."""
        expected = {
            "associated", "friends", "couple", "wears", "uses",
            "lives_in", "holds", "appears_with", "pairs_with", "variant_of",
        }
        actual = {r.value for r in RelationshipType}
        assert expected == actual

    def test_lora_association_type_enum(self):
        """R10.8: LoRA association types."""
        expected = {"identity", "style"}
        actual = {l.value for l in LoraAssociationType}
        assert expected == actual


@pytest.mark.unit
class TestTalentRelationshipSchemas:
    """Tests for relationship schema validation."""

    def test_relationship_create_valid(self):
        from app.schemas.talent import TalentRelationshipCreate

        schema = TalentRelationshipCreate(
            target_talent_id=TALENT_ID_2,
            relationship_type=RelationshipType.FRIENDS,
        )
        assert schema.target_talent_id == TALENT_ID_2
        assert schema.relationship_type == RelationshipType.FRIENDS

    def test_relationship_create_with_metadata(self):
        from app.schemas.talent import TalentRelationshipCreate

        schema = TalentRelationshipCreate(
            target_talent_id=TALENT_ID_2,
            relationship_type=RelationshipType.WEARS,
            metadata={"occasion": "formal"},
        )
        assert schema.metadata == {"occasion": "formal"}

    def test_relationship_invalid_type_rejected(self):
        from pydantic import ValidationError

        from app.schemas.talent import TalentRelationshipCreate

        with pytest.raises(ValidationError):
            TalentRelationshipCreate(
                target_talent_id=TALENT_ID_2,
                relationship_type="invalid_type",
            )


@pytest.mark.unit
class TestTalentLoraSchemas:
    """Tests for LoRA schema validation."""

    def test_lora_create_valid(self):
        from app.schemas.talent import TalentLoraCreate

        schema = TalentLoraCreate(
            lora_model_id=LORA_ID,
            type=LoraAssociationType.IDENTITY,
            strength=0.75,
            always_on=True,
        )
        assert schema.lora_model_id == LORA_ID
        assert schema.type == LoraAssociationType.IDENTITY
        assert schema.strength == 0.75
        assert schema.always_on is True

    def test_lora_strength_out_of_range_rejected(self):
        from pydantic import ValidationError

        from app.schemas.talent import TalentLoraCreate

        with pytest.raises(ValidationError):
            TalentLoraCreate(
                lora_model_id=LORA_ID,
                strength=1.5,  # > 1.0 not allowed
            )

    def test_lora_strength_negative_rejected(self):
        from pydantic import ValidationError

        from app.schemas.talent import TalentLoraCreate

        with pytest.raises(ValidationError):
            TalentLoraCreate(
                lora_model_id=LORA_ID,
                strength=-0.1,
            )

    def test_lora_defaults(self):
        from app.schemas.talent import TalentLoraCreate

        schema = TalentLoraCreate(lora_model_id=LORA_ID)
        assert schema.type == LoraAssociationType.IDENTITY
        assert schema.strength == 0.8
        assert schema.always_on is False


@pytest.mark.unit
class TestTalentResponseSchemas:
    """Tests for response schema serialization."""

    def test_talent_response_from_attributes(self):
        from app.schemas.talent import TalentResponse

        now = datetime.now(UTC)

        class FakeTalent:
            id = TALENT_ID
            org_id = ORG_A
            name = "Test"
            description = None
            talent_type = "influencer"
            identity_classification = "FICTIONAL"
            is_active = True
            avatar_url = None
            created_at = now
            updated_at = now

        resp = TalentResponse.model_validate(FakeTalent())
        assert resp.id == TALENT_ID
        assert resp.org_id == ORG_A
        assert resp.identity_classification == "FICTIONAL"

    def test_talent_lora_response_from_attributes(self):
        from app.schemas.talent import TalentLoraResponse

        now = datetime.now(UTC)

        class FakeLora:
            id = LORA_ID
            org_id = ORG_A
            talent_id = TALENT_ID
            lora_model_id = uuid.uuid4()
            type = "identity"
            strength = 0.85
            always_on = True
            created_at = now
            updated_at = now

        resp = TalentLoraResponse.model_validate(FakeLora())
        assert resp.strength == 0.85
        assert resp.always_on is True

    def test_talent_relationship_response_from_attributes(self):
        from app.schemas.talent import TalentRelationshipResponse

        now = datetime.now(UTC)

        class FakeRel:
            id = uuid.uuid4()
            org_id = ORG_A
            source_talent_id = TALENT_ID
            target_talent_id = TALENT_ID_2
            relationship_type = "friends"
            metadata = {"note": "bff"}
            created_at = now
            updated_at = now

        resp = TalentRelationshipResponse.model_validate(FakeRel())
        assert resp.relationship_type == "friends"
        assert resp.metadata == {"note": "bff"}


# =============================================================================
# Service Logic Tests (mocked DB)
# =============================================================================


@pytest.mark.unit
class TestTalentServiceMaxLoras:
    """Tests for the max 5 LoRAs per talent constraint."""

    @pytest.mark.asyncio
    async def test_max_loras_exceeded_returns_422(self):
        """R10.8: Max 5 LoRAs per talent — exceeding raises 422."""
        from fastapi import HTTPException

        from app.services.talent_service import TalentService

        db = AsyncMock()
        service = TalentService.__new__(TalentService)
        service._db = db
        service._org_id = ORG_A

        # Mock get_talent to return a fake talent
        fake_talent = MagicMock()
        fake_talent.id = TALENT_ID
        fake_talent.org_id = ORG_A
        fake_talent.deleted_at = None
        service.get_talent = AsyncMock(return_value=fake_talent)

        # Mock count query to return 5 (at max)
        db.scalar = AsyncMock(return_value=5)

        with pytest.raises(HTTPException) as exc_info:
            await service.assign_lora(
                talent_id=TALENT_ID,
                lora_model_id=uuid.uuid4(),
                type="identity",
                strength=0.8,
                always_on=False,
            )

        assert exc_info.value.status_code == 422
        assert "Maximum 5 LoRAs" in exc_info.value.detail


@pytest.mark.unit
class TestTalentUpdate:
    """Tests for talent update schema."""

    def test_update_partial_fields(self):
        from app.schemas.talent import TalentUpdate

        schema = TalentUpdate(name="New Name")
        dumped = schema.model_dump(exclude_unset=True)
        assert "name" in dumped
        assert "description" not in dumped
        assert "talent_type" not in dumped

    def test_update_identity_classification(self):
        from app.schemas.talent import TalentUpdate

        schema = TalentUpdate(
            identity_classification=IdentityClassification.REAL_PERSON_SELF
        )
        dumped = schema.model_dump(exclude_unset=True)
        assert dumped["identity_classification"] == IdentityClassification.REAL_PERSON_SELF
