"""Pydantic v2 schemas for GPU Jobs with comprehensive input validation.

All inputs validated via explicit constraints:
    - UUID type for all IDs
    - Enum type for job_type (rejects unknown values)
    - ge/le bounds for priority and progress
    - Optional idempotency_key for deduplication

Validates: Requirements R4.1, R4.2, R4.3, R21.1, R21.11
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampedSchema
from app.schemas.validation import (
    JobStatus,
    JobType,
    NonEmptyStr,
    Priority,
    ProgressPercent,
    WorkloadClass,
)


class JobCreate(BaseSchema):
    """Request schema for submitting a new job.

    org_id is NEVER accepted from client — resolved from TenantContext.
    Returns 202 Accepted within 2 seconds.
    """

    job_type: JobType = Field(
        ..., description="Type of job to execute"
    )
    talent_id: UUID | None = Field(
        default=None, description="Associated talent UUID"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Job-specific parameters (validated per job_type)",
    )
    priority: Priority = Field(
        default=5, description="Priority level (1=lowest, 10=highest)"
    )
    idempotency_key: NonEmptyStr | None = Field(
        default=None,
        max_length=255,
        description="Idempotency key for dedup (same org+key → return existing non-terminal job)",
    )
    workload_class: WorkloadClass | None = Field(
        default=None, description="Scheduling workload class"
    )
    max_duration_seconds: int = Field(
        default=1800,
        ge=60,
        le=14400,
        description="Maximum job duration before timeout (60-14400 seconds)",
    )


class JobUpdateProgress(BaseSchema):
    """Request schema for updating job progress (internal use)."""

    progress_percent: ProgressPercent | None = None
    progress_message: str | None = Field(default=None, max_length=500)


class JobCancel(BaseSchema):
    """Request schema for cancelling a job."""

    reason: str | None = Field(default=None, max_length=500)


class JobResponse(TimestampedSchema):
    """Response schema for a single job."""

    id: UUID
    org_id: UUID
    job_type: str
    status: str
    talent_id: UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int
    idempotency_key: str | None = None
    workload_class: str | None = None
    progress_percent: int | None = None
    progress_message: str | None = None
    progress_metadata: dict[str, Any] | None = None
    error_message: str | None = None
    output_asset_ids: list[UUID] = Field(default_factory=list)
    cost_usd: float | None = None
    attempt_count: int = 0
    max_attempts: int = 3
    max_duration_seconds: int = 1800
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobListResponse(BaseSchema):
    """Paginated list of jobs."""

    items: list[JobResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
