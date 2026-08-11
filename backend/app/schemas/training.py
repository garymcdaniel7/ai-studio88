"""Pydantic v2 schemas for the LoRA Training Pipeline.

Provides validated request/response models for:
    - Training job submission (POST /api/v1/training/jobs)
    - Cost estimation (GET /api/v1/training/estimate)
    - Training job cancellation (POST /api/v1/training/jobs/{id}/cancel)
    - Training job listing and detail responses

All inputs validated via explicit constraints:
    - UUID type for all IDs
    - ge/le bounds for numeric training parameters
    - Enum types for fixed option sets

Validates: Requirements R35.1, R35.2, R35.5, R35.10
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampedSchema
from app.schemas.validation import NameStr, NonEmptyStr


class TrainingBaseModel(str, enum.Enum):
    """Supported base models for LoRA training."""

    FLUX_DEV = "flux-dev"
    FLUX_DEV_FP8 = "flux-dev-fp8"
    SDXL = "sdxl"
    SD15 = "sd15"


class TrainingJobStatus(str, enum.Enum):
    """Valid training job statuses."""

    QUEUED = "queued"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class TrainingJobCreate(BaseSchema):
    """Request schema for submitting a new LoRA training job.

    The org_id is NEVER accepted from client — resolved from TenantContext.
    Returns 202 Accepted.

    Validates: R35.1, R35.10
    """

    talent_id: UUID = Field(
        ..., description="UUID of the talent to train a LoRA for (must belong to requesting org)"
    )
    manifest_id: UUID = Field(
        ..., description="UUID of the immutable dataset manifest containing 10-200 training images"
    )
    base_model: TrainingBaseModel = Field(
        default=TrainingBaseModel.FLUX_DEV,
        description="Base model to fine-tune",
    )
    trigger_word: NonEmptyStr = Field(
        default="ohwx",
        max_length=50,
        description="Trigger word for the trained LoRA",
    )
    steps: int = Field(
        default=1000,
        ge=100,
        le=5000,
        description="Number of training steps (100-5000)",
    )
    rank: int = Field(
        default=16,
        ge=4,
        le=128,
        description="LoRA rank/dimension (4-128)",
    )
    learning_rate: float = Field(
        default=1e-4,
        gt=0,
        le=1e-2,
        description="Learning rate",
    )
    resolution: int = Field(
        default=1024,
        ge=256,
        le=2048,
        description="Training resolution in pixels (256-2048)",
    )
    idempotency_key: NonEmptyStr | None = Field(
        default=None,
        max_length=255,
        description="Idempotency key for dedup",
    )


class TrainingEstimateRequest(BaseSchema):
    """Request schema for training cost estimation.

    Validates: R35.2
    """

    base_model: TrainingBaseModel = Field(
        default=TrainingBaseModel.FLUX_DEV,
        description="Base model for training",
    )
    steps: int = Field(
        default=1000,
        ge=100,
        le=5000,
        description="Number of training steps",
    )
    resolution: int = Field(
        default=1024,
        ge=256,
        le=2048,
        description="Training resolution in pixels",
    )
    image_count: int = Field(
        default=20,
        ge=10,
        le=200,
        description="Number of training images",
    )


class TrainingEstimateResponse(BaseSchema):
    """Response schema for training cost estimation.

    Validates: R35.2
    """

    base_model: str
    steps: int
    resolution: int
    image_count: int
    estimated_time_seconds: int
    estimated_cost_usd: float = Field(ge=0)
    hourly_rate_usd: float = Field(ge=0)
    gpu_type: str = Field(
        default="RTX 4090",
        description="Estimated GPU type for the training",
    )
    note: str = Field(
        default="Estimate based on current provider rates. Actual cost may vary.",
    )


class TrainingJobResponse(TimestampedSchema):
    """Response schema for a training job record.

    Validates: R35.1, R35.4
    """

    id: UUID
    org_id: UUID
    talent_id: UUID
    manifest_id: UUID
    status: str
    base_model: str
    trigger_word: str
    steps: int
    rank: int
    learning_rate: float
    resolution: int
    progress_percent: int | None = None
    progress_message: str | None = None
    error_message: str | None = None
    cost_usd: float | None = None
    model_id: UUID | None = Field(
        default=None,
        description="UUID of the created model record (populated on completion)",
    )
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None


class TrainingJobListResponse(BaseSchema):
    """Paginated list of training jobs."""

    items: list[TrainingJobResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class TrainingCancelResponse(BaseSchema):
    """Response schema for training job cancellation.

    Validates: R35.5, R35.6
    """

    id: UUID
    status: str
    cancelled_at: datetime
    message: str = "Training job cancelled successfully"
