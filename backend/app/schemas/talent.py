"""Pydantic v2 schemas for AI Talent with comprehensive input validation.

All inputs validated via explicit constraints:
    - UUID type for all IDs
    - min_length=1 for required strings (whitespace-only rejected)
    - max_length constraints on all string fields
    - Enum types for fixed option sets
    - No raw strings for IDs

Validates: Requirements R4.1, R4.2, R4.3, R4.10, R10.1, R10.7, R10.8
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampedSchema
from app.schemas.validation import (
    DescriptionStr,
    IdentityClassification,
    LoraAssociationType,
    NameStr,
    RelationshipType,
    TalentType,
)


class TalentCreate(BaseSchema):
    """Request schema for creating AI Talent.

    org_id is NEVER accepted from client — resolved from TenantContext.
    """

    name: NameStr = Field(..., description="Display name (1-100 chars, no whitespace-only)")
    description: DescriptionStr | None = Field(
        default=None, description="Talent description (max 1000 chars)"
    )
    talent_type: TalentType | None = Field(
        default=None, description="Type of AI persona"
    )
    identity_classification: IdentityClassification | None = Field(
        default=None,
        description="Identity classification (required for consent enforcement)",
    )
    is_active: bool = Field(default=True, description="Whether talent is active")


class TalentUpdate(BaseSchema):
    """Request schema for updating AI Talent (PATCH — partial update).

    All fields Optional. Only provided fields are updated.
    """

    name: NameStr | None = Field(
        default=None, description="Display name (1-100 chars)"
    )
    description: DescriptionStr | None = Field(
        default=None, description="Talent description (max 1000 chars)"
    )
    talent_type: TalentType | None = None
    identity_classification: IdentityClassification | None = None
    is_active: bool | None = None


class TalentResponse(TimestampedSchema):
    """Response schema for AI Talent."""

    id: UUID
    org_id: UUID
    name: str
    description: str | None = None
    talent_type: str | None = None
    identity_classification: str | None = None
    is_active: bool
    avatar_url: str | None = None


class TalentListResponse(BaseSchema):
    """Paginated list of talent."""

    items: list[TalentResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Talent Relationship schemas (R10.7)
# =============================================================================


class TalentRelationshipCreate(BaseSchema):
    """Request schema for creating a talent relationship."""

    target_talent_id: UUID = Field(
        ..., description="UUID of the target talent in the relationship"
    )
    relationship_type: RelationshipType = Field(
        ..., description="Type of relationship between talents"
    )
    metadata: dict | None = Field(
        default=None, description="Optional metadata for this relationship"
    )


class TalentRelationshipResponse(TimestampedSchema):
    """Response schema for a talent relationship."""

    id: UUID
    org_id: UUID
    source_talent_id: UUID
    target_talent_id: UUID
    relationship_type: str
    metadata: dict | None = None


class TalentRelationshipListResponse(BaseSchema):
    """Paginated list of talent relationships."""

    items: list[TalentRelationshipResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Talent LoRA schemas (R10.8)
# =============================================================================


class TalentLoraCreate(BaseSchema):
    """Request schema for associating a LoRA model with a talent.

    Max 5 LoRAs per talent (enforced at service layer).
    """

    lora_model_id: UUID = Field(
        ..., description="UUID of the LoRA model to associate"
    )
    type: LoraAssociationType = Field(
        default=LoraAssociationType.IDENTITY,
        description="Type of LoRA association (identity or style)",
    )
    strength: float = Field(
        default=0.8, ge=0.0, le=1.0, description="LoRA strength (0.0-1.0)"
    )
    always_on: bool = Field(
        default=False,
        description="Whether this LoRA should be auto-injected in generation",
    )


class TalentLoraUpdate(BaseSchema):
    """Request schema for updating a LoRA association."""

    type: LoraAssociationType | None = None
    strength: float | None = Field(
        default=None, ge=0.0, le=1.0, description="LoRA strength (0.0-1.0)"
    )
    always_on: bool | None = None


class TalentLoraResponse(TimestampedSchema):
    """Response schema for a talent LoRA association."""

    id: UUID
    org_id: UUID
    talent_id: UUID
    lora_model_id: UUID
    type: str
    strength: float
    always_on: bool


class TalentLoraListResponse(BaseSchema):
    """List of LoRAs associated with a talent."""

    items: list[TalentLoraResponse]
    total: int = Field(ge=0)

