"""Pydantic v2 schemas for Model/LoRA Promotion Gates.

Covers request/response schemas for:
    - Model registration
    - Lifecycle state promotion
    - Quarantine
    - Deprecation
    - Transition audit log queries

Requirements: R67.1, R67.2, R67.3, R67.4, R67.5, R67.6, R67.7, R67.8, R34.8
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


# =============================================================================
# Enums
# =============================================================================


class ModelLifecycleState(str, enum.Enum):
    """Model lifecycle states per R67.1."""

    IMPORTED = "imported"
    TRAINED = "trained"
    INTEGRITY_VERIFIED = "integrity_verified"
    EVALUATED = "evaluated"
    APPROVED = "approved"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    QUARANTINED = "quarantined"


class ModelRiskClass(str, enum.Enum):
    """Risk classification for promotion gate behavior per R67.4."""

    STANDARD = "standard"
    HIGH_RISK = "high_risk"


class ModelType(str, enum.Enum):
    """Type of model artifact."""

    LORA = "lora"
    CHECKPOINT = "checkpoint"
    EMBEDDING = "embedding"


# =============================================================================
# Request Schemas
# =============================================================================


class ModelRegisterRequest(BaseSchema):
    """Request schema for registering a new model in the lifecycle system.

    org_id is NEVER accepted from client — resolved from TenantContext.
    """

    name: str = Field(
        ..., min_length=1, max_length=200, description="Human-readable model name"
    )
    model_type: ModelType = Field(
        default=ModelType.LORA, description="Type of model artifact"
    )
    risk_class: ModelRiskClass = Field(
        default=ModelRiskClass.STANDARD,
        description="Risk classification for gate behavior",
    )
    initial_state: ModelLifecycleState = Field(
        default=ModelLifecycleState.IMPORTED,
        description="Initial state (imported or trained)",
    )
    base_model_id: str | None = Field(
        default=None, max_length=200, description="Base model identifier"
    )
    checksum_sha256: str | None = Field(
        default=None, max_length=64, description="SHA-256 hash of model file"
    )
    storage_key: str | None = Field(
        default=None, max_length=500, description="B2 storage key"
    )
    file_size_bytes: int | None = Field(
        default=None, ge=0, description="File size in bytes"
    )
    metadata: dict | None = Field(
        default=None, description="Additional metadata"
    )


class ModelPromoteRequest(BaseSchema):
    """Request schema for promoting a model to the next lifecycle state.

    The service validates that the transition is valid and that
    any required human approval gates are satisfied.
    """

    target_state: ModelLifecycleState = Field(
        ..., description="Target lifecycle state to promote to"
    )
    evidence: dict | None = Field(
        default=None,
        description="Supporting evidence for the transition (gate check results)",
    )
    actor: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Identity performing the promotion",
    )
    actor_type: str = Field(
        default="human",
        description="Actor type: human or system",
    )


class ModelQuarantineRequest(BaseSchema):
    """Request schema for quarantining a model from any state."""

    reason: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Reason for quarantine",
    )
    actor: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Identity performing the quarantine",
    )
    evidence: dict | None = Field(
        default=None, description="Supporting evidence"
    )


class ModelDeprecateRequest(BaseSchema):
    """Request schema for deprecating an ACTIVE model."""

    reason: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Reason for deprecation",
    )
    actor: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Identity performing the deprecation",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class ModelRegistryResponse(BaseSchema):
    """Response schema for a model registry entry."""

    id: UUID
    org_id: UUID
    name: str
    model_type: str
    lifecycle_state: str
    risk_class: str
    base_model_id: str | None = None
    checksum_sha256: str | None = None
    storage_key: str | None = None
    file_size_bytes: int | None = None
    metadata: dict | None = None
    quarantine_reason: str | None = None
    quarantined_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ModelTransitionResponse(BaseSchema):
    """Response schema for a model transition audit record."""

    id: UUID
    org_id: UUID
    model_id: UUID
    from_state: str
    to_state: str
    actor: str
    actor_type: str
    risk_class: str
    evidence: dict | None = None
    gate_checks_performed: list[str] | None = None
    gate_checks_passed: list[str] | None = None
    success: bool
    error_message: str | None = None
    created_at: datetime


class ModelRegistryListResponse(BaseSchema):
    """Paginated list of model registry entries."""

    items: list[ModelRegistryResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class ModelTransitionListResponse(BaseSchema):
    """Paginated list of model transition audit records."""

    items: list[ModelTransitionResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
