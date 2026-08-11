"""Pydantic v2 schemas for Platform Operators.

Request/response validation for the capability-based Platform Operator
model. Platform Operators receive granular capability grants rather than
undifferentiated god-level access.

Validates: Requirements R33.5, R33.6, R33.7, R97.1, R97.2, R97.3, R97.4
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


class CapabilityGroupEnum(enum.StrEnum):
    """Platform Operator capability groups.

    Each operator may receive any permitted subset of these groups.
    Founder Authority is the broadest — implicitly includes all others.
    """

    PLATFORM_OBSERVE = "platform_observe"
    TENANT_SUPPORT = "tenant_support"
    TENANT_ACCESS_ESCALATION = "tenant_access_escalation"
    PLATFORM_CONFIGURATION = "platform_configuration"
    FINANCIAL_CONTROLS = "financial_controls"
    SAFETY_AND_RIGHTS = "safety_and_rights"
    SECURITY_ADMINISTRATION = "security_administration"
    DEPLOYMENT_OPERATIONS = "deployment_operations"
    RELEASE_MANAGEMENT = "release_management"
    DESTRUCTIVE_PLATFORM_ACTIONS = "destructive_platform_actions"
    FOUNDER_AUTHORITY = "founder_authority"


# =============================================================================
# Request Schemas
# =============================================================================


class PlatformOperatorCreate(BaseSchema):
    """Request schema for granting Platform Operator capabilities.

    The granted_by field is server-derived from the authenticated
    operator's identity — never client-supplied.
    """

    user_id: UUID = Field(
        ...,
        description="User UUID to grant operator capabilities to",
    )
    capability_grants: list[CapabilityGroupEnum] = Field(
        ...,
        min_length=1,
        description="Capability groups to grant (at least one required)",
    )

    @field_validator("capability_grants")
    @classmethod
    def validate_unique_capabilities(
        cls, v: list[CapabilityGroupEnum],
    ) -> list[CapabilityGroupEnum]:
        """Ensure no duplicate capability grants."""
        if len(v) != len(set(v)):
            msg = "Duplicate capability grants are not allowed"
            raise ValueError(msg)
        return v


class PlatformOperatorUpdate(BaseSchema):
    """Request schema for updating operator capability grants.

    Used when modifying the set of capabilities for an existing operator.
    """

    capability_grants: list[CapabilityGroupEnum] = Field(
        ...,
        min_length=1,
        description="New set of capability groups for this operator",
    )

    @field_validator("capability_grants")
    @classmethod
    def validate_unique_capabilities(
        cls, v: list[CapabilityGroupEnum],
    ) -> list[CapabilityGroupEnum]:
        """Ensure no duplicate capability grants."""
        if len(v) != len(set(v)):
            msg = "Duplicate capability grants are not allowed"
            raise ValueError(msg)
        return v


class PlatformOperatorActionLog(BaseSchema):
    """Request schema for logging an operator action.

    operator_user_id is server-derived from the authenticated identity.
    """

    capability_used: CapabilityGroupEnum = Field(
        ...,
        description="Which capability group authorized this action",
    )
    target_org_id: UUID | None = Field(
        default=None,
        description="Target tenant UUID (if action is tenant-scoped)",
    )
    action_type: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Type of action performed",
    )
    action_detail: dict | None = Field(
        default=None,
        description="Structured detail about the action",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class PlatformOperatorResponse(BaseSchema):
    """Response schema for a single Platform Operator record."""

    id: UUID
    user_id: UUID
    capability_grants: list[str]
    granted_by: UUID
    granted_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @property
    def is_active(self) -> bool:
        """Whether this operator record is currently active."""
        return self.revoked_at is None


class PlatformOperatorActionResponse(BaseSchema):
    """Response schema for a single operator action audit entry."""

    id: UUID
    operator_user_id: UUID
    capability_used: str
    target_org_id: UUID | None = None
    action_type: str
    action_detail: dict | None = None
    created_at: datetime


class PlatformOperatorListResponse(BaseSchema):
    """Paginated list of Platform Operators."""

    items: list[PlatformOperatorResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class PlatformOperatorActionListResponse(BaseSchema):
    """Paginated list of operator actions."""

    items: list[PlatformOperatorActionResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
