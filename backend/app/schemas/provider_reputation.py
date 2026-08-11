"""Pydantic v2 schemas for Provider Reputation system.

Request/response validation for recording job outcomes, querying
provider metrics, dynamic rankings, and quarantine management.

Validates: Requirements R65.1, R65.2, R65.3, R65.4, R65.5, R65.6
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, PaginatedResponse, TenantResponseSchema


# =============================================================================
# Enums
# =============================================================================


class ProviderType(str, enum.Enum):
    """Provider type classification."""

    COMPUTE = "compute"
    LLM = "llm"
    STORAGE = "storage"
    VOICE = "voice"


class JobOutcomeStatus(str, enum.Enum):
    """Status of a completed job for reputation tracking."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CONNECTION_FAILURE = "connection_failure"
    CLEANUP_FAILURE = "cleanup_failure"


# =============================================================================
# Request Schemas
# =============================================================================


class RecordJobOutcomeRequest(BaseSchema):
    """Request to record a job outcome for a provider.

    Called after every job completion to update provider reputation.
    """

    provider_name: str = Field(
        min_length=1,
        max_length=100,
        description="Provider identifier (e.g., 'runpod', 'fluidstack')",
    )
    provider_type: ProviderType = Field(
        default=ProviderType.COMPUTE,
        description="Provider type classification",
    )
    status: JobOutcomeStatus = Field(
        description="Job outcome status",
    )
    startup_latency_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Time to boot/connect (seconds)",
    )
    queue_latency_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Time spent waiting in queue (seconds)",
    )
    generation_duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Job execution duration (seconds)",
    )
    estimated_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        description="Pre-execution cost estimate (USD)",
    )
    actual_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        description="Actual cost incurred (USD)",
    )
    quality_accepted: bool | None = Field(
        default=None,
        description="Whether user accepted the output quality",
    )
    metadata: dict | None = Field(
        default=None,
        description="Extended metadata (gpu_type, region, vram_gb, etc.)",
    )


class QuarantineProviderRequest(BaseSchema):
    """Request to manually quarantine or unquarantine a provider."""

    provider_name: str = Field(
        min_length=1,
        max_length=100,
        description="Provider identifier",
    )
    quarantine: bool = Field(
        description="True to quarantine, False to release",
    )
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Reason for quarantine/release action",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class ProviderMetricsResponse(TenantResponseSchema):
    """Full provider reputation metrics response."""

    provider_name: str
    provider_type: str

    # Positive signals
    startup_latency_seconds: float
    queue_latency_seconds: float
    generation_duration_seconds: float
    failure_rate_24h: float
    cost_variance: float
    availability_7d: float
    model_cache_readiness: float
    quality_acceptance_rate: float

    # Negative signals
    cleanup_failures: int
    cost_overruns: int
    timeout_rate: float
    connection_failures: int

    # Aggregates
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    total_cost_usd: float

    # Quarantine
    is_quarantined: bool
    quarantined_at: datetime | None
    quarantine_reason: str | None

    # Ranking
    overall_score: float
    last_job_at: datetime | None

    # Metadata
    metadata: dict | None = None


class ProviderRankingEntry(BaseSchema):
    """A single entry in the provider ranking list."""

    provider_name: str
    provider_type: str
    overall_score: float = Field(ge=0.0, le=1.0)
    failure_rate_24h: float
    availability_7d: float
    startup_latency_seconds: float
    total_jobs: int
    is_quarantined: bool


class ProviderRankingResponse(BaseSchema):
    """Dynamic ranking of providers by reputation score."""

    rankings: list[ProviderRankingEntry]
    total_providers: int
    quarantined_count: int


class QuarantineCheckResponse(BaseSchema):
    """Result of checking whether a provider should be quarantined."""

    provider_name: str
    is_quarantined: bool
    failure_rate_24h: float
    threshold: float
    action_taken: str | None = Field(
        default=None,
        description="Action taken: 'quarantined', 'released', or None (no change)",
    )
    reason: str | None = None


class RecordOutcomeResponse(BaseSchema):
    """Response after recording a job outcome."""

    provider_name: str
    updated_score: float
    is_quarantined: bool
    total_jobs: int
