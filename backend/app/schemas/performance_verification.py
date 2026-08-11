"""Pydantic response schemas for the Performance Verification API.

Defines response models for:
    - GET /api/v1/performance/targets (list all targets)
    - POST /api/v1/performance/verify (run verification checks)

Validates: Requirements R76.1, R76.2, R76.3, R76.4, R76.5, R76.6
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PerformanceCategorySchema(str, Enum):
    """Categories of performance targets per R76."""

    NAVIGATION = "navigation"
    DATA_LOADING = "data_loading"
    BRAIN_CHAT = "brain_chat"
    GENERATION = "generation"
    ADMIN = "admin"
    REALTIME = "realtime"


class VerificationStatusSchema(str, Enum):
    """Pass/fail status for a performance verification check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class PerformanceTargetResponse(BaseModel):
    """Response schema for a single performance target definition."""

    name: str = Field(description="Unique identifier for the performance target")
    target_ms: float = Field(
        description="Maximum acceptable latency in milliseconds",
        ge=0,
    )
    category: PerformanceCategorySchema = Field(
        description="R76 category this target belongs to",
    )
    requirement_id: str = Field(
        description="Traceability to R76 acceptance criterion",
    )
    description: str = Field(
        description="Human-readable explanation of what is measured",
    )
    endpoint: str | None = Field(
        default=None,
        description="API endpoint used for measurement (None for client-side targets)",
    )
    is_async: bool = Field(
        default=False,
        description="Whether this operation is inherently async",
    )

    model_config = {"from_attributes": True}


class PerformanceTargetListResponse(BaseModel):
    """Response schema for GET /api/v1/performance/targets."""

    items: list[PerformanceTargetResponse] = Field(
        description="All defined performance targets",
    )
    total: int = Field(description="Total number of performance targets")
    categories: list[PerformanceCategorySchema] = Field(
        description="Distinct categories represented in targets",
    )


class PerformanceMeasurementResponse(BaseModel):
    """Response schema for a single measurement result."""

    target_name: str = Field(description="Name of the target being measured")
    measured_ms: float | None = Field(
        default=None,
        description="Actual measured latency in milliseconds (None if skipped)",
    )
    target_ms: float = Field(
        description="Target threshold in milliseconds",
    )
    status: VerificationStatusSchema = Field(
        description="Pass/fail/skipped/error status",
    )
    detail: str = Field(
        default="",
        description="Additional context about the measurement",
    )


class OptimizationRecommendationResponse(BaseModel):
    """Response schema for an optimization recommendation."""

    target_name: str = Field(
        description="Which target this recommendation addresses",
    )
    category: PerformanceCategorySchema = Field(
        description="Performance category",
    )
    recommendation: str = Field(
        description="Human-readable action to take",
    )
    explain_analyze_query: str | None = Field(
        default=None,
        description="Suggested EXPLAIN ANALYZE query for DB-related targets (R76.6)",
    )
    priority: str = Field(
        description="HIGH / MEDIUM / LOW based on how far over target",
    )


class PerformanceVerificationResponse(BaseModel):
    """Response schema for POST /api/v1/performance/verify."""

    measurements: list[PerformanceMeasurementResponse] = Field(
        description="Measurement results for each target",
    )
    summary: PerformanceVerificationSummary = Field(
        description="Aggregate pass/fail summary",
    )
    recommendations: list[OptimizationRecommendationResponse] = Field(
        default_factory=list,
        description="Optimization recommendations for failed targets",
    )


class PerformanceVerificationSummary(BaseModel):
    """Summary statistics for a verification run."""

    total_targets: int = Field(description="Total number of targets checked")
    passed: int = Field(description="Number of targets that passed")
    failed: int = Field(description="Number of targets that failed")
    skipped: int = Field(description="Number of targets skipped (not measurable)")
    errors: int = Field(description="Number of measurement errors")
    overall_status: VerificationStatusSchema = Field(
        description="PASSED if all measurable targets pass, FAILED otherwise",
    )


# Fix forward reference — redefine PerformanceVerificationResponse after Summary
PerformanceVerificationResponse.model_rebuild()
