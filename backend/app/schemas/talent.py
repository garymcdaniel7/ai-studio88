"""Pydantic schemas for AI Talent."""
from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampedSchema


class TalentCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    gender: str | None = Field(default=None, max_length=50)
    age_range: str | None = Field(default=None, max_length=20)
    style_tags: list[str] = Field(default_factory=list)
    is_active: bool = True


class TalentUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    gender: str | None = None
    age_range: str | None = None
    style_tags: list[str] | None = None
    is_active: bool | None = None


class TalentResponse(TimestampedSchema):
    id: UUID
    org_id: UUID
    name: str
    description: str | None
    gender: str | None
    age_range: str | None
    style_tags: list[str]
    is_active: bool
    avatar_url: str | None = None
