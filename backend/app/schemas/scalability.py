"""Pydantic schemas for Scalability Architecture Verification.

Defines request/response models for verifying that the platform architecture
satisfies scalability requirements: user growth independent of GPU scaling,
replaceable job transport, stateless backend, and documented scaling strategy.

Validates: Requirements R91.1, R91.3, R91.4, R76.8, R76.10
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from app.schemas.base import BaseSchema


# =============================================================================
# Enums
# =============================================================================


class ScalabilityVerdict(str, Enum):
    """Verification verdict for a scalability property."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


class ScalingDirection(str, Enum):
    """Component scaling direction classification."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    BOTH = "both"
    MANAGED = "managed"


# =============================================================================
# Property Schemas
# =============================================================================


class ScalabilityProperty(BaseSchema):
    """A single scalability verification property result."""

    property_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Name of the scalability property verified",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Human-readable explanation of what this property verifies",
    )
    verified: bool = Field(
        ...,
        description="Whether the property passed verification",
    )
    verdict: ScalabilityVerdict = Field(
        ...,
        description="Verification verdict (pass/fail/warn)",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Evidence supporting the verification result",
    )
    requirement_ids: list[str] = Field(
        default_factory=list,
        description="Requirement IDs this property validates",
    )


class ComponentScalingInfo(BaseSchema):
    """Scaling strategy for a single system component."""

    component: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name of the system component",
    )
    scaling_direction: ScalingDirection = Field(
        ...,
        description="How this component scales",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Scaling strategy explanation",
    )
    current_constraint: str | None = Field(
        default=None,
        max_length=500,
        description="Known capacity constraint (if any)",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class ScalabilityStatusResponse(BaseSchema):
    """Response for GET /api/v1/scalability/status.

    Reports the current verification status of all scalability architecture
    properties along with the component scaling documentation.
    """

    overall_pass: bool = Field(
        ...,
        description="Whether all critical scalability properties pass",
    )
    properties: list[ScalabilityProperty] = Field(
        ...,
        description="Individual scalability property verification results",
    )
    component_scaling: list[ComponentScalingInfo] = Field(
        ...,
        description="Scaling strategy per component (horizontal vs vertical)",
    )
    documentation_exists: bool = Field(
        ...,
        description="Whether SCALING_STRATEGY.md exists",
    )
    verified_at: datetime = Field(
        ...,
        description="When the verification was last executed",
    )
