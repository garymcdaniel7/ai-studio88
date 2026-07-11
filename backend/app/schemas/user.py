"""Pydantic schemas for User."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.schemas.base import TimestampedSchema

if TYPE_CHECKING:
    from uuid import UUID


class UserResponse(TimestampedSchema):
    id: UUID
    email: str
    full_name: str | None
    org_id: UUID | None
    role: str
    is_active: bool
