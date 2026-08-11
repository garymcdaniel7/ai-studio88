"""Pydantic v2 schemas for Generation Context Packages.

Provides request/response validation for the immutable generation context
package system. Context packages are snapshots of all inputs at the moment
of job creation — once created, they are NEVER modified.

All generation surfaces (Brain, API, MCP, scheduled, batch) use the same
canonical boundary. Stale references are detected at validation time.

Validates: Requirements R60.1, R60.2, R60.3, R60.4, R60.5, R60.6
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


# =============================================================================
# Enums
# =============================================================================


class GenerationSurface(str, enum.Enum):
    """The surface that initiated the generation request."""

    BRAIN = "brain"
    API = "api"
    MCP = "mcp"
    SCHEDULED = "scheduled"
    BATCH = "batch"


# =============================================================================
# Nested Schemas for JSONB Fields
# =============================================================================


class TalentSnapshot(BaseSchema):
    """Frozen talent data at time of context package creation."""

    talent_id: UUID
    name: str = Field(max_length=100)
    talent_type: str = Field(max_length=50)
    identity_classification: str = Field(max_length=50)
    adult_status: str | None = Field(default=None, max_length=50)


class SourceAssetRef(BaseSchema):
    """Reference to a source asset included in the context package."""

    asset_id: UUID
    storage_key: str = Field(max_length=500)
    checksum: str | None = Field(default=None, max_length=128)
    role: str = Field(max_length=50)


class LoraSelection(BaseSchema):
    """A single LoRA selection within the model configuration."""

    lora_id: UUID
    version: str | None = Field(default=None, max_length=100)
    strength: float = Field(ge=0.0, le=2.0)
    lora_type: str = Field(max_length=50, default="identity")


class ModelLoraSelections(BaseSchema):
    """Model and LoRA configuration for generation."""

    model_id: UUID | None = None
    model_name: str | None = Field(default=None, max_length=200)
    model_version: str | None = Field(default=None, max_length=100)
    base_model: str | None = Field(default=None, max_length=50)
    loras: list[LoraSelection] = Field(default_factory=list, max_length=5)


class PromptInstructions(BaseSchema):
    """Prompt and generation parameter configuration."""

    positive_prompt: str = Field(max_length=5000)
    negative_prompt: str | None = Field(default=None, max_length=5000)
    cfg_scale: float | None = Field(default=None, ge=1.0, le=30.0)
    steps: int | None = Field(default=None, ge=1, le=150)
    sampler: str | None = Field(default=None, max_length=50)
    scheduler: str | None = Field(default=None, max_length=50)
    seed: int | None = None
    width: int | None = Field(default=None, ge=256, le=2048)
    height: int | None = Field(default=None, ge=256, le=2048)


class ConsentVerificationResult(BaseSchema):
    """Result of consent verification during context assembly."""

    verified: bool
    scopes_checked: list[str] = Field(default_factory=list)
    scopes_present: list[str] = Field(default_factory=list)
    fictional_exemption: bool = False
    evaluated_at: datetime | None = None


class SafetyEvaluationResult(BaseSchema):
    """Result of safety policy evaluation during context assembly."""

    passed: bool
    content_rating: str | None = Field(default=None, max_length=20)
    policy_level: str | None = Field(default=None, max_length=50)
    checks_performed: list[str] = Field(default_factory=list)
    evaluated_at: datetime | None = None


class WorkflowTemplateRef(BaseSchema):
    """Reference to the workflow template used for generation."""

    workflow_id: UUID | None = None
    workflow_version: str | None = Field(default=None, max_length=100)
    template_name: str | None = Field(default=None, max_length=200)
    parameters_injected: dict | None = None


class ProjectConstraints(BaseSchema):
    """Project-level constraints that bound the generation."""

    project_id: UUID | None = None
    budget_limit_usd: Decimal | None = Field(default=None, ge=Decimal("0"))
    quality_tier: str | None = Field(default=None, max_length=50)
    privacy_restrictions: list[str] = Field(default_factory=list)
    deadline: datetime | None = None


# =============================================================================
# Request Schemas
# =============================================================================


class GenerationContextPackageCreate(BaseSchema):
    """Request schema for creating a generation context package.

    org_id is NEVER accepted from client — resolved from TenantContext.
    Once created, the package is immutable — no update endpoint exists.
    """

    talent_record: TalentSnapshot | None = None
    creative_dna_version: str | None = Field(
        default=None, max_length=100
    )
    source_assets: list[SourceAssetRef] | None = None
    model_lora_selections: ModelLoraSelections | None = None
    prompt_instructions: PromptInstructions | None = None
    consent_verification_result: ConsentVerificationResult | None = None
    safety_evaluation_result: SafetyEvaluationResult | None = None
    workflow_template: WorkflowTemplateRef | None = None
    project_constraints: ProjectConstraints | None = None
    initiated_by: GenerationSurface | None = None


# =============================================================================
# Response Schemas
# =============================================================================


class GenerationContextPackageResponse(BaseSchema):
    """Response schema for a single generation context package."""

    id: UUID
    org_id: UUID
    version: int
    talent_record: dict | None = None
    creative_dna_version: str | None = None
    source_assets: dict | None = None
    model_lora_selections: dict | None = None
    prompt_instructions: dict | None = None
    consent_verification_result: dict | None = None
    safety_evaluation_result: dict | None = None
    workflow_template: dict | None = None
    project_constraints: dict | None = None
    initiated_by: str | None = None
    user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class GenerationContextPackageListResponse(BaseSchema):
    """Paginated list of generation context packages."""

    items: list[GenerationContextPackageResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Validation Result Schema
# =============================================================================


class StaleReference(BaseSchema):
    """A single stale reference detected during validation."""

    entity_type: str = Field(max_length=50)
    entity_id: UUID
    reason: str = Field(max_length=200)


class ContextPackageValidationResult(BaseSchema):
    """Result of validating a generation context package for staleness."""

    is_valid: bool
    stale_references: list[StaleReference] = Field(default_factory=list)
    validated_at: datetime
