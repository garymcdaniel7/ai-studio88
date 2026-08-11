"""Pydantic v2 schemas for the Notification service.

Provides request/response validation for notification CRUD operations.
Categories are strongly typed via NotificationCategory enum.

Validates: Requirements R101.1, R101.2, R101.3
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Enums
# =============================================================================


class NotificationCategory(str, enum.Enum):
    """Canonical notification categories per R101.1."""

    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    CONNECTION_EXPIRED = "connection_expired"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PUBLISHING_RESULT = "publishing_result"
    BUDGET_THRESHOLD = "budget_threshold"
    SAFETY_ACTION = "safety_action"
    HERMES_NEEDS_INPUT = "hermes_needs_input"


# Categories that are mandatory — cannot be disabled by user preferences
MANDATORY_CATEGORIES: frozenset[NotificationCategory] = frozenset({
    NotificationCategory.SAFETY_ACTION,
})


# =============================================================================
# Request Schemas
# =============================================================================


class NotificationCreate(BaseModel):
    """Internal schema for creating a notification.

    Used by the NotificationService — not exposed as an API endpoint.
    org_id and user_id are provided by the service layer, not the client.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    user_id: UUID = Field(..., description="Target user for this notification")
    category: NotificationCategory = Field(
        ..., description="Notification category"
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Short notification title",
    )
    body: str | None = Field(
        default=None,
        max_length=5000,
        description="Extended notification body",
    )
    action_url: str | None = Field(
        default=None,
        max_length=2000,
        description="Deep link within the application",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional structured data (job_id, asset_id, etc.)",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class NotificationResponse(BaseModel):
    """Response schema for a single notification."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    user_id: UUID
    category: str
    title: str
    body: str | None = None
    action_url: str | None = None
    is_read: bool
    is_mandatory: bool
    metadata: dict = Field(default_factory=dict, alias="extra_data")
    created_at: datetime
    updated_at: datetime


class NotificationListResponse(BaseModel):
    """Response schema for notification list with unread count."""

    model_config = ConfigDict(from_attributes=True)

    items: list[NotificationResponse]
    total: int = Field(ge=0)
    unread_count: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class NotificationCountResponse(BaseModel):
    """Response schema for notification count."""

    model_config = ConfigDict(from_attributes=True)

    unread_count: int = Field(ge=0)
    total: int = Field(ge=0)
