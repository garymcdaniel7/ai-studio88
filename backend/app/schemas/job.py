"""Pydantic schemas for GPU Job."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampedSchema


class JobCreate(BaseSchema):
    job_type: str = Field(
        description="Type of job: image_generation | video_generation | voice_generation | lora_training"
    )
    talent_id: UUID | None = None
    campaign_id: UUID | None = None
    workflow_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=1, le=10)


class JobResponse(TimestampedSchema):
    id: UUID
    org_id: UUID
    job_type: str
    status: str  # queued | provisioning | running | completed | failed | cancelled
    talent_id: UUID | None
    campaign_id: UUID | None
    workflow_id: str | None
    parameters: dict[str, Any]
    priority: int
    gpu_provider: str | None
    gpu_instance_id: str | None
    started_at: str | None
    completed_at: str | None
    error_message: str | None
    output_asset_ids: list[UUID] = Field(default_factory=list)
    cost_usd: float | None
