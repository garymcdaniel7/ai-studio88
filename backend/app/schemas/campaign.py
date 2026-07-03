"""Pydantic schemas for Campaign."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampedSchema


class CampaignCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    talent_id: UUID
    brand_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None


class CampaignResponse(TimestampedSchema):
    id: UUID
    org_id: UUID
    name: str
    description: str | None
    talent_id: UUID
    brand_id: UUID | None
    status: str
    start_date: date | None
    end_date: date | None
