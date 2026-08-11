"""Pydantic schemas for workspace autonomy profile API.

Request/response schemas for the workspace autonomy configuration
endpoints (GET/PUT /api/v1/workspace/autonomy).

Validates: Requirements R98.1, R98.2, R30.12, R30.13
"""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, StrictBaseSchema


# =============================================================================
# Enums
# =============================================================================


class AutonomyLevelEnum(str, Enum):
    """Workspace agent autonomy level for API serialization.

    ADVISORY: Recommend only — no mutations without explicit user instruction.
    ASSISTED: Low-risk actions auto-execute, high-risk requires confirmation.
    AUTONOMOUS_WITHIN_LIMITS: Delegated actions within configured limits.
    """

    ADVISORY = "advisory"
    ASSISTED = "assisted"
    AUTONOMOUS_WITHIN_LIMITS = "autonomous_within_limits"


# =============================================================================
# Request Schemas
# =============================================================================


class AutonomyProfileUpdate(StrictBaseSchema):
    """Request schema for updating workspace autonomy profile.

    Used by PUT /api/v1/workspace/autonomy.
    """

    autonomy_level: AutonomyLevelEnum = Field(
        default=AutonomyLevelEnum.ADVISORY,
        description=(
            "Agent autonomy level. ADVISORY: recommend only. "
            "ASSISTED: low-risk auto-execute. "
            "AUTONOMOUS_WITHIN_LIMITS: delegated within configured limits."
        ),
    )


# =============================================================================
# Response Schemas
# =============================================================================


class MandatoryControlsResponse(BaseSchema):
    """Mandatory controls that are always enforced regardless of autonomy level."""

    safety_kernel: bool = Field(
        default=True,
        description="Safety kernel actions are always enforced",
    )
    security_sensitive: bool = Field(
        default=True,
        description="Security-sensitive operations always require approval",
    )
    consent_verification: bool = Field(
        default=True,
        description="Consent verification is always enforced",
    )
    budget_exceeding: bool = Field(
        default=True,
        description="Budget-exceeding operations always require approval",
    )
    destructive_operations: bool = Field(
        default=True,
        description="Destructive operations always require approval",
    )


class AutonomyProfileResponse(BaseSchema):
    """Response schema for workspace autonomy profile."""

    org_id: UUID
    autonomy_level: AutonomyLevelEnum
    mandatory_controls: MandatoryControlsResponse = Field(
        default_factory=MandatoryControlsResponse,
    )
