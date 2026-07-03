"""Pydantic schemas for User."""
from __future__ import annotations

from uuid import UUID

from app.schemas.base import BaseSchema, TimestampedSchema


class UserResponse(TimestampedSchema):
    id: UUID
    email: str
    full_name: str | None
    org_id: UUID | None
    role: str
    is_active: bool
