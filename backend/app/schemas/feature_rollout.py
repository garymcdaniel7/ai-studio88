"""Pydantic schemas for Feature Rollout API.

Request/response schemas for the platform-admin feature rollout management
endpoints. These schemas validate all inputs and structure all responses.

Validates: Requirements R106.1, R106.2, R106.3, R19.9, R19.10
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


class RolloutScopeEnum(str, Enum):
    """Valid rollout scope values."""

    GLOBAL = "global"
    PLAN = "plan"
    WORKSPACE = "workspace"
    COHORT = "cohort"
    USER = "user"
    WORKLOAD = "workload"
    PROVIDER = "provider"


# =============================================================================
# Request Schemas
# =============================================================================


class FeatureRolloutCreate(BaseSchema):
    """Request schema for creating a feature rollout rule."""

    capability_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Name of the capability to control",
    )
    rollout_scope: RolloutScopeEnum = Field(
        ...,
        description="Scope of the rollout rule",
    )
    scope_target: str | None = Field(
        default=None,
        max_length=255,
        description="Target for the scope (plan name, workspace_id, etc.). Required for non-global scopes.",
    )
    enabled: bool = Field(
        default=True,
        description="Whether the capability is enabled or disabled for this scope/target",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="When this rule expires. NULL = permanent until deleted.",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class FeatureRolloutResponse(BaseSchema):
    """Response schema for a feature rollout record."""

    id: UUID
    capability_name: str
    rollout_scope: RolloutScopeEnum
    scope_target: str | None = None
    enabled: bool
    expires_at: datetime | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class FeatureRolloutListResponse(PaginatedResponse):
    """Paginated list of feature rollout records."""

    items: list[FeatureRolloutResponse]  # type: ignore[assignment]
