"""Base schema classes shared across all schemas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from datetime import datetime


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,  # Allow creating from ORM models
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class TimestampedSchema(BaseSchema):
    """Schema with standard timestamp fields."""

    created_at: datetime
    updated_at: datetime


class PaginatedResponse(BaseSchema):
    """Standard paginated list response wrapper."""

    items: list
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + self.limit < self.total
