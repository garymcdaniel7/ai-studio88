"""Pydantic v2 schemas for Rights/Takedown Cases.

Request/response validation for the rights case management subsystem.
Includes both public intake (POST /api/v1/takedowns) and Platform Operator
management endpoints (GET/PATCH /platform-admin/rights-cases).

Validates: Requirements R40.1, R40.2, R40.3, R40.7, R40.8, R40.9, A2-005
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


class RightsCaseTypeEnum(str, enum.Enum):
    """Valid complaint types for rights/takedown cases."""

    COPYRIGHT = "copyright"
    TRADEMARK = "trademark"
    LIKENESS = "likeness"
    PRIVACY = "privacy"
    ILLEGAL = "illegal"
    CSAM = "csam"
    OTHER = "other"


class RightsCaseStatusEnum(str, enum.Enum):
    """Case lifecycle statuses."""

    RECEIVED = "received"
    TRIAGED = "triaged"
    ACTION_REQUIRED = "action_required"
    NO_ACTION = "no_action"
    RESTRICTED = "restricted"
    REMOVED = "removed"
    RESOLVED = "resolved"
    APPEALED = "appealed"
    RE_REVIEWED = "re_reviewed"
    CLOSED = "closed"


class RightsCasePriorityEnum(str, enum.Enum):
    """Case priority levels."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


# =============================================================================
# Public Intake Request (POST /api/v1/takedowns)
# =============================================================================


class TakedownReportRequest(BaseSchema):
    """Public-facing takedown report intake schema.

    This is the schema for external reporters submitting complaints.
    No authentication required for submitting — the endpoint is public.

    Fields correspond to R40.1: reporter_email, content_url_or_id,
    complaint_type, description, and optional evidence_urls.
    """

    reporter_email: str = Field(
        ...,
        min_length=5,
        max_length=255,
        description="Reporter's contact email",
    )
    reporter_name: str | None = Field(
        default=None,
        max_length=255,
        description="Reporter's name (optional)",
    )
    complaint_type: RightsCaseTypeEnum = Field(
        ...,
        description="Type of complaint: copyright, trademark, likeness, privacy, illegal, csam, other",
    )
    content_url_or_id: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="URL or asset ID of the reported content",
    )
    description: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Description of the complaint (max 5000 chars)",
    )
    evidence_urls: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Optional list of evidence URLs (max 20)",
    )

    @field_validator("reporter_email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        """Basic email format check."""
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v

    @field_validator("description")
    @classmethod
    def validate_description_not_whitespace(cls, v: str) -> str:
        """Ensure description has meaningful content."""
        if not v.strip():
            raise ValueError("Description must contain meaningful content")
        return v


class TakedownReportResponse(BaseSchema):
    """Response returned to the reporter after successful intake."""

    case_id: UUID
    status: str = "received"
    message: str = "Your report has been received and will be reviewed."


# =============================================================================
# Platform Operator Request Schemas
# =============================================================================


class RightsCaseUpdateRequest(BaseSchema):
    """Platform Operator schema for updating a rights case.

    Supports status transitions, priority changes, assignment,
    resolution, and legal holds.
    """

    status: RightsCaseStatusEnum | None = Field(
        default=None,
        description="New status (must be valid transition from current status)",
    )
    priority: RightsCasePriorityEnum | None = Field(
        default=None,
        description="Update priority level",
    )
    assigned_operator: UUID | None = Field(
        default=None,
        description="Assign to a Platform Operator",
    )
    resolution: str | None = Field(
        default=None,
        max_length=5000,
        description="Resolution description (required for closing)",
    )
    legal_hold_active: bool | None = Field(
        default=None,
        description="Enable/disable legal hold on affected content",
    )
    action_note: str | None = Field(
        default=None,
        max_length=2000,
        description="Note to append to actions_taken audit trail",
    )


# =============================================================================
# Appeal Request (POST /api/v1/takedowns/{case_id}/appeal)
# =============================================================================


class TakedownAppealRequest(BaseSchema):
    """Schema for appealing a takedown action.

    Users whose content was restricted/removed can submit an appeal.
    """

    appellant_email: str = Field(
        ...,
        min_length=5,
        max_length=255,
        description="Appellant's contact email",
    )
    reason: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Reason for the appeal",
    )
    evidence_urls: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Supporting evidence URLs",
    )

    @field_validator("appellant_email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        """Basic email format check."""
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v


# =============================================================================
# Response Schemas
# =============================================================================


class RightsCaseResponse(BaseSchema):
    """Full response schema for a rights case (Platform Operator view)."""

    id: UUID
    case_type: str
    status: str
    priority: str
    reporter_contact: dict | None = None
    target_org_id: UUID | None = None
    target_talent_ids: list[UUID] | None = None
    target_asset_ids: list[UUID] | None = None
    reported_urls: list[str] | None = None
    evidence_refs: list[dict] = Field(default_factory=list)
    assigned_operator: UUID | None = None
    actions_taken: list[dict] = Field(default_factory=list)
    resolution: str | None = None
    appeal_state: str | None = None
    legal_hold_active: bool = False
    created_at: datetime
    updated_at: datetime


class RightsCaseListResponse(BaseSchema):
    """Paginated list of rights cases."""

    items: list[RightsCaseResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
