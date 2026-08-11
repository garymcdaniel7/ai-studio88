"""Common response schemas used across the platform.

Provides generic paginated response, standard base schemas for CRUD operations,
and common field definitions.

Validates: Requirements R4.1, R4.3, R22.1
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.validation import NameStr

T = TypeVar("T")


# =============================================================================
# Generic Paginated Response
# =============================================================================


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated list response.

    Usage:
        PaginatedResponse[TalentResponse](items=[...], total=100, limit=20, offset=0)
    """

    items: list[T]
    total: int = Field(ge=0, description="Total number of items matching the query")
    limit: int = Field(ge=1, le=100, description="Maximum items per page")
    offset: int = Field(ge=0, description="Number of items skipped")

    model_config = ConfigDict(from_attributes=True)

    @property
    def has_more(self) -> bool:
        """Check if there are more pages available."""
        return self.offset + self.limit < self.total


# =============================================================================
# Base Create/Update/Response Schemas
# =============================================================================


class BaseCreateSchema(BaseModel):
    """Base schema for resource creation requests.

    Note: org_id is NEVER accepted from the client. It is resolved
    from TenantContext (JWT → org_members lookup).
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        from_attributes=True,
    )


class BaseUpdateSchema(BaseModel):
    """Base schema for resource update requests.

    All fields should be Optional to support partial updates (PATCH).
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        from_attributes=True,
    )


class BaseResponseSchema(BaseModel):
    """Base schema for resource responses.

    All responses include the resource ID and org_id (both UUID).
    """

    id: UUID
    org_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Standard ID Reference Schema
# =============================================================================


class IDReference(BaseModel):
    """A reference to a resource by its UUID."""

    id: UUID


class NamedIDReference(BaseModel):
    """A reference to a resource by its UUID with a display name."""

    id: UUID
    name: NameStr
