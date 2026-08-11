"""Pydantic v2 schemas for External Deletion Tracking.

Provides request/response validation for deletion tracking CRUD operations
and admin endpoints.

Validates: Requirements R105.1, R105.2, R105.3
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.external_deletion import DeletionState


# =============================================================================
# Response Schemas
# =============================================================================


class ExternalDeletionResponse(BaseModel):
    """Response schema for a single external deletion tracking record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    asset_id: UUID
    storage_key: str
    deletion_state: DeletionState
    provider: str
    requested_at: datetime | None = None
    confirmed_at: datetime | None = None
    failed_at: datetime | None = None
    retry_count: int = Field(ge=0)
    last_error: str | None = None
    legal_hold_ref: str | None = None
    created_at: datetime
    updated_at: datetime


class ExternalDeletionListResponse(BaseModel):
    """Response schema for paginated list of external deletion records."""

    model_config = ConfigDict(from_attributes=True)

    items: list[ExternalDeletionResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Request Schemas
# =============================================================================


class ExternalDeletionCreate(BaseModel):
    """Schema for initiating external deletion tracking.

    Used internally by services when an asset is soft-deleted.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    asset_id: UUID = Field(..., description="Asset UUID to track deletion for")
    storage_key: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Storage key in external provider",
    )
    provider: str = Field(
        default="b2",
        min_length=1,
        max_length=50,
        description="Storage provider identifier",
    )
    legal_hold_ref: str | None = Field(
        default=None,
        max_length=500,
        description="Legal hold case reference, if applicable",
    )


class ExternalDeletionRetryResponse(BaseModel):
    """Response schema for retry action."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deletion_state: DeletionState
    retry_count: int
    message: str
