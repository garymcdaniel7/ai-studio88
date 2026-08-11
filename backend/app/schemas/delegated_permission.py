"""Pydantic schemas for delegated permission API.

Request/response schemas for the workspace delegated-permissions
endpoints (GET/POST/DELETE /api/v1/workspace/delegated-permissions).

Validates: Requirements R30.14, R98.3
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, PaginatedResponse, StrictBaseSchema


# =============================================================================
# Request Schemas
# =============================================================================


class DelegatedPermissionCreate(StrictBaseSchema):
    """Request schema for granting a delegated permission.

    Used by POST /api/v1/workspace/delegated-permissions.
    """

    action_class: str = Field(
        min_length=1,
        max_length=100,
        description="Action class to delegate (e.g. 'generate_image', 'schedule_post')",
    )
    connection_scope: UUID | None = Field(
        default=None,
        description="Specific connection UUID to scope this delegation, or null for all connections",
    )
    max_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        le=10000.0,
        description="Maximum cost per invocation in USD, or null for no per-action limit",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Optional expiration timestamp. Null means no expiry.",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class DelegatedPermissionResponse(BaseSchema):
    """Response schema for a single delegated permission."""

    id: UUID
    org_id: UUID
    delegated_by: UUID
    action_class: str
    connection_scope: UUID | None = None
    max_cost_usd: float | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    is_active: bool = Field(
        description="Whether this delegation is currently active (not expired/revoked)",
    )


class DelegatedPermissionListResponse(PaginatedResponse):
    """Paginated list of delegated permissions."""

    items: list[DelegatedPermissionResponse]
