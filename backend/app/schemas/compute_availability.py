"""Pydantic schemas for compute availability API.

Request/response schemas for the platform-admin compute state management
endpoints. These schemas validate all inputs and structure all responses
for the compute availability system.

Validates: Requirements R86.1, R86.2, R86.3, R86.5
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, PaginatedResponse


# =============================================================================
# Enums
# =============================================================================


class ComputeAvailabilityStateEnum(str, Enum):
    """Compute availability state values."""

    DISABLED = "disabled"
    SELECTIVE = "selective"
    ENABLED = "enabled"


class GrantTypeEnum(str, Enum):
    """Selective grant type values."""

    WORKSPACE = "workspace"
    PLAN = "plan"
    COHORT = "cohort"
    WORKLOAD = "workload"
    PROVIDER = "provider"
    PROMOTION = "promotion"


# =============================================================================
# Request Schemas
# =============================================================================


class ComputeStateUpdate(BaseSchema):
    """Request schema for changing compute availability state."""

    state: ComputeAvailabilityStateEnum = Field(
        ...,
        description="New compute availability state",
    )
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason for the state change",
    )


class SelectiveGrantCreate(BaseSchema):
    """Request schema for creating a selective compute grant."""

    grant_type: GrantTypeEnum = Field(
        ...,
        description="Type of selective grant",
    )
    grant_target: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Target identifier (workspace_id, plan_name, cohort_id, etc.)",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="When the grant expires (NULL = permanent until revoked)",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class ComputeStateResponse(BaseSchema):
    """Response schema for current compute availability state."""

    state: ComputeAvailabilityStateEnum
    changed_by: UUID
    changed_at: datetime
    reason: str | None = None


class SelectiveGrantResponse(BaseSchema):
    """Response schema for a selective grant record."""

    id: UUID
    grant_type: GrantTypeEnum
    grant_target: str
    expires_at: datetime | None = None
    granted_by: UUID
    revoked_at: datetime | None = None
    revoked_by: UUID | None = None
    created_at: datetime


class ComputeStateWithGrantsResponse(BaseSchema):
    """Combined response: current state + active selective grants."""

    state: ComputeAvailabilityStateEnum
    changed_by: UUID
    changed_at: datetime
    reason: str | None = None
    selective_grants: list[SelectiveGrantResponse] = Field(default_factory=list)


class SelectiveGrantListResponse(PaginatedResponse):
    """Paginated list of selective grants."""

    items: list[SelectiveGrantResponse]  # type: ignore[assignment]
