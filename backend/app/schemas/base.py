"""Base schema classes shared across all schemas.

Provides strict base models that:
- Strip whitespace from strings
- Reject unknown/extra fields with 422
- Support ORM attribute loading

Validates: Requirements R4.1, R4.2, R4.3, R4.10
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseSchema(BaseModel):
    """Strict base schema that rejects extra fields.

    Use this for request schemas where unknown fields should be rejected
    with HTTP 422.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        from_attributes=True,
        populate_by_name=True,
    )


class BaseSchema(BaseModel):
    """Base schema with common configuration.

    Strips whitespace and rejects extra fields. Used for all request
    and response schemas across the platform.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        extra="forbid",
    )


class TimestampedSchema(BaseSchema):
    """Schema with standard timestamp fields."""

    created_at: datetime
    updated_at: datetime


class TenantResponseSchema(BaseSchema):
    """Response schema for tenant-scoped resources.

    All tenant-scoped responses include id, org_id, and timestamps.
    """

    id: UUID
    org_id: UUID
    created_at: datetime
    updated_at: datetime


class PaginatedResponse(BaseSchema):
    """Standard paginated list response wrapper."""

    items: list
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)

    @property
    def has_more(self) -> bool:
        return self.offset + self.limit < self.total
