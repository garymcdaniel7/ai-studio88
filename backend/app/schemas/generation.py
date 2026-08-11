"""Pydantic v2 schemas for image/video generation with comprehensive validation.

All inputs validated via explicit constraints:
    - prompt: max 2000 chars, whitespace-only rejected
    - dimensions: 256-2048px
    - model: enum of supported models
    - UUID for talent_id

Validates: Requirements R4.1, R4.2, R4.3, R12.1, R12.2
"""

from __future__ import annotations

import enum
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.base import BaseSchema
from app.schemas.validation import DimensionPx, PromptStr


class GenerationModel(str, enum.Enum):
    """Supported generation models."""

    FLUX_DEV = "flux_dev"
    SDXL_TURBO = "sdxl_turbo"
    SD15 = "sd15"


class ImageGenerateRequest(BaseSchema):
    """Request schema for image generation.

    Validates:
        - prompt: 1-2000 chars, whitespace-only rejected
        - width/height: 256-2048px, multiples of 64 (enforced by model_validator)
        - model: one of supported enum values
        - talent_id: valid UUID if provided
    """

    prompt: PromptStr = Field(
        ..., description="Generation prompt (1-2000 chars)"
    )
    negative_prompt: str | None = Field(
        default=None,
        max_length=2000,
        description="Negative prompt (optional, max 2000 chars)",
    )
    model: GenerationModel = Field(
        default=GenerationModel.FLUX_DEV,
        description="Model to use for generation",
    )
    width: DimensionPx = Field(
        default=1024, description="Image width in pixels (256-2048)"
    )
    height: DimensionPx = Field(
        default=1024, description="Image height in pixels (256-2048)"
    )
    num_steps: int = Field(
        default=20, ge=1, le=100, description="Number of inference steps (1-100)"
    )
    guidance_scale: float = Field(
        default=7.5, ge=0.0, le=30.0, description="Guidance scale (0.0-30.0)"
    )
    seed: int | None = Field(
        default=None, ge=0, le=2147483647, description="Random seed (optional)"
    )
    talent_id: UUID | None = Field(
        default=None, description="Associated talent UUID (optional)"
    )
    lora_model_id: UUID | None = Field(
        default=None, description="LoRA model UUID to apply (optional)"
    )
    lora_strength: float = Field(
        default=0.8, ge=0.0, le=1.0, description="LoRA strength (0.0-1.0)"
    )

    @model_validator(mode="after")
    def validate_dimensions(self) -> "ImageGenerateRequest":
        """Ensure dimensions are multiples of 64 (required by most models)."""
        if self.width % 64 != 0:
            raise ValueError(
                f"Width must be a multiple of 64, got {self.width}"
            )
        if self.height % 64 != 0:
            raise ValueError(
                f"Height must be a multiple of 64, got {self.height}"
            )
        return self


class ImageGenerateResponse(BaseSchema):
    """Response schema for image generation request (202 Accepted)."""

    job_id: UUID
    status: str = "queued"
    estimated_duration_seconds: int | None = None
    estimated_cost_usd: float | None = None
