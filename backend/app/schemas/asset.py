"""Pydantic schemas for Asset."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.schemas.base import TimestampedSchema

if TYPE_CHECKING:
    from uuid import UUID


class AssetResponse(TimestampedSchema):
    id: UUID
    org_id: UUID
    talent_id: UUID | None
    job_id: UUID | None
    filename: str
    content_type: str
    file_size_bytes: int
    storage_key: str
    cdn_url: str | None
    asset_type: str  # image | video | audio | model
    width: int | None
    height: int | None
    duration_seconds: float | None
