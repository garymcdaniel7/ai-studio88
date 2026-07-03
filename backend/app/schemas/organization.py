"""Pydantic schemas for Organisation."""
from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampedSchema


class OrganizationCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$")


class OrganizationResponse(TimestampedSchema):
    id: UUID
    name: str
    slug: str
    plan: str
    is_active: bool
