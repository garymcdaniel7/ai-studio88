"""Pydantic schemas for Deployment Repeatability Verification.

Defines request/response models for tracking deployment verification history
and classifying deployment stability.

Classification logic:
    - "not_proven": fewer than 3 verification records exist
    - "demonstrated_but_unstable": some successes but not 3+ consecutive
    - "repeatable_and_stable": 3+ consecutive successful verifications

Validates: Requirements R109.1, R109.2, R109.3, R109.4, R109.5, R82.7, R82.8
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from app.schemas.base import BaseSchema


# =============================================================================
# Enums
# =============================================================================


class DeploymentClassification(str, Enum):
    """Deployment stability classification per R109.2."""

    NOT_PROVEN = "not_proven"
    DEMONSTRATED_BUT_UNSTABLE = "demonstrated_but_unstable"
    REPEATABLE_AND_STABLE = "repeatable_and_stable"


class VerificationCheckName(str, Enum):
    """Individual verification check types."""

    FRONTEND_BUILD = "frontend_build"
    BACKEND_LINT = "backend_lint"
    BACKEND_COMPILE = "backend_compile"
    NO_SUPPRESSED_CHECKS = "no_suppressed_checks"


# =============================================================================
# Verification Record Schemas
# =============================================================================


class VerificationCheck(BaseSchema):
    """Result of a single deployment verification check."""

    check_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Identifier of the verification check",
    )
    passed: bool = Field(
        ...,
        description="Whether this check passed",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Human-readable status message",
    )
    checked_at: datetime = Field(
        ...,
        description="When this check was executed",
    )


class DeploymentVerificationRecord(BaseSchema):
    """A single deployment verification run result."""

    id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique identifier for this verification run",
    )
    timestamp: datetime = Field(
        ...,
        description="When the verification was executed",
    )
    overall_passed: bool = Field(
        ...,
        description="Whether all checks passed",
    )
    checks: list[VerificationCheck] = Field(
        default_factory=list,
        description="Individual check results",
    )
    git_branch: str = Field(
        default="unknown",
        max_length=200,
        description="Git branch the verification was run against",
    )
    git_sha: str = Field(
        default="unknown",
        max_length=40,
        description="Git commit SHA at verification time",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class DeploymentRepeatabilityResponse(BaseSchema):
    """Response for GET /release/repeatability — classification + history.

    Provides the current deployment stability classification along with
    recent verification history and success rate metrics.
    """

    classification: DeploymentClassification = Field(
        ...,
        description="Current deployment stability classification",
    )
    classification_reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Human-readable explanation of the classification",
    )
    total_verifications: int = Field(
        ge=0,
        description="Total number of verification runs recorded",
    )
    successful_verifications: int = Field(
        ge=0,
        description="Number of successful verification runs",
    )
    consecutive_successes: int = Field(
        ge=0,
        description="Current streak of consecutive successful verifications",
    )
    success_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Success rate (0.0 to 1.0)",
    )
    last_verification: DeploymentVerificationRecord | None = Field(
        default=None,
        description="Most recent verification record",
    )
    history: list[DeploymentVerificationRecord] = Field(
        default_factory=list,
        description="Recent verification history (most recent first)",
    )
    meets_production_gate: bool = Field(
        ...,
        description="Whether deployment repeatability meets production gate requirements",
    )


class DeploymentVerificationRunResponse(BaseSchema):
    """Response after running a new deployment verification."""

    verification: DeploymentVerificationRecord = Field(
        ...,
        description="The verification record just created",
    )
    classification: DeploymentClassification = Field(
        ...,
        description="Updated classification after this verification",
    )
    meets_production_gate: bool = Field(
        ...,
        description="Whether production gate is now met",
    )
