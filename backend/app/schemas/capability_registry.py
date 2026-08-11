"""Pydantic response schemas for the Capability Registry API.

Defines the response models for GET /api/v1/capabilities including
individual capability details and the list response envelope.

Validates: Requirements R19.1, R19.2, R19.3
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class CapabilityClassificationSchema(str, Enum):
    """Classification states for platform capabilities (R19.1)."""

    PRODUCTION = "production"
    PARTIAL = "partial"
    SIMULATED = "simulated"
    MISSING = "missing"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
    UNVERIFIED = "unverified"


class HealthStatusSchema(str, Enum):
    """Health status for a capability's required providers."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class CapabilityResponse(BaseModel):
    """Response schema for a single capability.

    R19.2: Returns classification, required provider, and health status.
    """

    name: str = Field(
        description="Unique identifier for the capability",
    )
    classification: CapabilityClassificationSchema = Field(
        description="Current classification state of the capability",
    )
    required_providers: list[str] = Field(
        default_factory=list,
        description="List of provider names required for this capability",
    )
    health_status: HealthStatusSchema = Field(
        description="Current health of the capability's dependencies",
    )
    description: str = Field(
        default="",
        description="Human-readable description of the capability",
    )

    model_config = {"from_attributes": True}


class CapabilityTransitionResponse(BaseModel):
    """Response schema for a classification transition audit record (R19.6)."""

    capability_name: str = Field(
        description="Name of the capability that transitioned",
    )
    previous_classification: CapabilityClassificationSchema = Field(
        description="Classification before the transition",
    )
    new_classification: CapabilityClassificationSchema = Field(
        description="Classification after the transition",
    )
    actor: str = Field(
        description="Identifier of the person/system that made the change",
    )
    reason: str = Field(
        description="Human-readable reason for the transition",
    )
    timestamp: datetime = Field(
        description="When the transition occurred",
    )


class CapabilityListResponse(BaseModel):
    """Response schema for GET /api/v1/capabilities (R19.2)."""

    items: list[CapabilityResponse] = Field(
        description="All registered capabilities with current state",
    )
    total: int = Field(
        description="Total number of registered capabilities",
    )
