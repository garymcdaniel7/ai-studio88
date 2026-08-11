"""Pydantic v2 schemas for Scheduled Posts (Publishing Service).

Handles request validation and response serialization for the
scheduled post lifecycle: create, list, get, cancel, dispatch.

Requirements: R38.1, R38.2, R38.3, R38.4, R38.5, R38.6, R38.7, R38.8
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


# =============================================================================
# Request Schemas
# =============================================================================


class SchedulePostRequest(BaseSchema):
    """Request to schedule a post for publishing.

    scheduled_at must be at least 5 minutes in the future.
    org_id is resolved from TenantContext — never client-supplied.
    """

    asset_id: UUID = Field(..., description="UUID of the asset to publish")
    talent_id: UUID | None = Field(
        default=None, description="Optional talent ID associated with the content"
    )
    connection_id: UUID | None = Field(
        default=None, description="Connection ID for OAuth credentials"
    )
    platform: str = Field(
        ..., min_length=1, max_length=50, description="Target platform (tiktok, instagram, youtube)"
    )
    caption: str = Field(
        default="", max_length=2200, description="Post caption text"
    )
    scheduled_at: datetime = Field(
        ..., description="Scheduled publish time (must be >= now + 5 minutes)"
    )
    approval_id: UUID | None = Field(
        default=None, description="FK to publishing_approved_packages"
    )


class DispatchPostRequest(BaseSchema):
    """Request to manually trigger dispatch of a scheduled post.

    Used for immediate publish or re-dispatch after failure.
    """

    force: bool = Field(
        default=False, description="Force dispatch even if scheduled_at is in the future"
    )


# =============================================================================
# Response Schemas
# =============================================================================


class ScheduledPostResponse(BaseSchema):
    """Response for a single scheduled post."""

    id: UUID
    org_id: UUID
    asset_id: UUID
    talent_id: UUID | None = None
    connection_id: UUID | None = None
    approval_id: UUID | None = None
    platform: str
    caption: str
    scheduled_at: datetime
    dispatched_at: datetime | None = None
    status: str
    platform_post_id: str | None = None
    error_message: str | None = None
    resize_spec: dict | None = None
    created_at: datetime
    updated_at: datetime


class ScheduledPostListResponse(BaseSchema):
    """Paginated list of scheduled posts."""

    items: list[ScheduledPostResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class ScheduledPostCancelResponse(BaseSchema):
    """Response when cancelling a scheduled post."""

    id: UUID
    status: str
    message: str
