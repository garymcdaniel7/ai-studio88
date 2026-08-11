"""Pydantic v2 schemas for Consent Records.

Consent is a first-class subsystem — versioned, scoped, revocable, auditable.
All inputs validated via explicit constraints.

Requirements: R10.2, R10.3, A2-004
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


# =============================================================================
# Enums
# =============================================================================


class ConsentScope(str, enum.Enum):
    """Valid consent scopes.

    Scope-specific evaluation: only relevant scopes checked per operation type.
    """

    LIKENESS = "likeness"
    VOICE = "voice"
    TRAINING = "training"
    GENERATION = "generation"
    ADULT_CONTENT = "adult_content"
    COMMERCIAL = "commercial"
    PUBLISHING = "publishing"
    CLIENT_WORK = "client_work"


class ConsentProvenance(str, enum.Enum):
    """How consent was obtained/verified."""

    SELF_ATTESTED = "SELF_ATTESTED"
    REPRESENTATIVE = "REPRESENTATIVE"
    PLATFORM_VERIFIED = "PLATFORM_VERIFIED"
    IMPORTED = "IMPORTED"


class ConsentVerificationState(str, enum.Enum):
    """Verification status of a consent record."""

    UNVERIFIED = "unverified"
    PENDING_REVIEW = "pending_review"
    VERIFIED = "verified"
    DISPUTED = "disputed"


class ConsentEvidenceType(str, enum.Enum):
    """Type of evidence supporting the consent."""

    SIGNED_DOCUMENT = "signed_document"
    EMAIL = "email"
    PLATFORM_ATTESTATION = "platform_attestation"
    VERBAL_RECORDED = "verbal_recorded"


# =============================================================================
# Request Schemas
# =============================================================================


class ConsentCreateRequest(BaseSchema):
    """Request schema for creating a consent record.

    org_id is NEVER accepted from client — resolved from TenantContext.
    """

    talent_id: UUID = Field(..., description="UUID of the talent this consent applies to")
    scopes: list[ConsentScope] = Field(
        ..., min_length=1, description="Consent scopes being granted"
    )
    evidence_type: ConsentEvidenceType | None = Field(
        default=None, description="Type of supporting evidence"
    )
    evidence_url: str | None = Field(
        default=None, max_length=2000, description="URL to stored evidence"
    )
    grantor_identity: str | None = Field(
        default=None, max_length=255, description="Who granted consent (name/email)"
    )
    granted_at: datetime | None = Field(
        default=None, description="When consent was granted (defaults to now)"
    )
    expires_at: datetime | None = Field(
        default=None, description="When consent expires (NULL = no expiry)"
    )
    restrictions: dict = Field(
        default_factory=dict, description="JSON conditions/limitations"
    )
    provenance: ConsentProvenance = Field(
        ..., description="How consent was obtained"
    )
    verification_state: ConsentVerificationState = Field(
        default=ConsentVerificationState.UNVERIFIED,
        description="Verification status",
    )

    @field_validator("scopes")
    @classmethod
    def scopes_not_empty(cls, v: list[ConsentScope]) -> list[ConsentScope]:
        """Ensure at least one scope is provided."""
        if not v:
            raise ValueError("At least one consent scope is required")
        return v


class ConsentUpdateRequest(BaseSchema):
    """Request schema for updating a consent record.

    Only mutable fields can be updated. Core fields (talent_id, scopes,
    granted_at, provenance) are immutable after creation.
    """

    evidence_type: ConsentEvidenceType | None = None
    evidence_url: str | None = Field(default=None, max_length=2000)
    grantor_identity: str | None = Field(default=None, max_length=255)
    expires_at: datetime | None = None
    restrictions: dict | None = None
    verification_state: ConsentVerificationState | None = None


class ConsentRevokeRequest(BaseSchema):
    """Request schema for revoking a consent record."""

    revocation_reason: str = Field(
        ..., min_length=1, max_length=1000, description="Reason for revocation"
    )


# =============================================================================
# Response Schemas
# =============================================================================


class ConsentResponse(BaseSchema):
    """Response schema for a single consent record."""

    id: UUID
    org_id: UUID
    talent_id: UUID
    scopes: list[str]
    evidence_type: str | None = None
    evidence_url: str | None = None
    grantor_identity: str | None = None
    granted_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    restrictions: dict = Field(default_factory=dict)
    provenance: str
    version: int
    verification_state: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ConsentListResponse(BaseSchema):
    """Paginated list of consent records."""

    items: list[ConsentResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
