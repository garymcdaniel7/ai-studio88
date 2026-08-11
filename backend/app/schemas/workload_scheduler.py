"""Pydantic v2 schemas for workload scheduling requests/responses.

Defines the data contracts for:
    - WorkloadRequest: what a caller submits to the scheduler
    - WorkerInfo: worker state representation for scoring
    - WorkerAssignment: the scheduler's decision
    - CapacityStatus: per-class capacity snapshot
    - QueueFairnessConfig: fairness policy per workspace

Validates: Requirements R65.8, R65.9, R65.10, R87.1, R87.2, R87.5,
           R88.1, R88.2, R88.3, R88.4, A2-039
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema
from app.schemas.validation import WorkloadClass


class WorkerHealthStatus(str, Enum):
    """Worker health states."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class PlanTier(str, Enum):
    """Workspace plan tiers for fairness weighting."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class WorkloadRequest(BaseSchema):
    """Request to schedule a workload onto an eligible worker.

    Used by the job leasing system when claiming a job to determine
    which worker should execute it.
    """

    org_id: UUID = Field(..., description="Workspace owning this workload")
    job_id: UUID = Field(..., description="Job being scheduled")
    workload_class: WorkloadClass = Field(
        ..., description="Workload class for capacity isolation"
    )
    required_vram_gb: float = Field(
        default=0.0, ge=0.0, description="Minimum VRAM required in GB"
    )
    required_models: list[str] = Field(
        default_factory=list,
        description="Model identifiers needed (for cache readiness scoring)",
    )
    required_capabilities: list[str] = Field(
        default_factory=list,
        description="Required provider capabilities (e.g., persistent_storage)",
    )
    priority: int = Field(
        default=5, ge=1, le=10, description="Job priority (1=lowest, 10=highest)"
    )
    submitted_at: datetime | None = Field(
        default=None, description="When the job was queued (for anti-starvation)"
    )


class WorkerInfo(BaseSchema):
    """Representation of a worker's current state for scheduling decisions.

    Workers are reported by the provider/connection registry and enriched
    with real-time metrics.
    """

    worker_id: UUID = Field(..., description="Unique worker identifier")
    org_id: UUID = Field(..., description="Workspace owning this worker")
    provider_id: str = Field(..., description="Provider identifier (e.g., vast.ai)")
    gpu_type: str = Field(default="unknown", description="GPU model name")
    vram_gb: float = Field(default=0.0, ge=0.0, description="Available VRAM in GB")
    cached_models: list[str] = Field(
        default_factory=list, description="Models pre-loaded on this worker"
    )
    capabilities: list[str] = Field(
        default_factory=list, description="Supported capabilities"
    )
    health_status: WorkerHealthStatus = Field(
        default=WorkerHealthStatus.UNKNOWN,
        description="Current health assessment",
    )
    utilization_percent: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Current GPU utilization %"
    )
    active_jobs: int = Field(
        default=0, ge=0, description="Number of jobs currently running"
    )
    queue_depth: int = Field(
        default=0, ge=0, description="Pending jobs queued on this worker"
    )
    max_concurrent_jobs: int = Field(
        default=1, ge=1, description="Max parallel jobs this worker supports"
    )


class WorkerAssignment(BaseSchema):
    """Scheduling decision: which worker to assign the job to."""

    worker_id: UUID = Field(..., description="Selected worker")
    score: float = Field(
        ..., ge=0.0, description="Composite scoring result (higher=better)"
    )
    reason: str = Field(
        default="", description="Human-readable explanation of selection"
    )


class CapacityPoolStatus(BaseSchema):
    """Capacity snapshot for a single workload class."""

    workload_class: WorkloadClass
    total_capacity: int = Field(ge=0, description="Total available worker slots")
    active_jobs: int = Field(ge=0, description="Currently executing jobs")
    queued_jobs: int = Field(ge=0, description="Jobs waiting for capacity")
    available_slots: int = Field(ge=0, description="Remaining capacity slots")
    is_exhausted: bool = Field(
        default=False, description="True when no capacity remains"
    )


class CapacityStatus(BaseSchema):
    """Overall capacity view across all workload classes."""

    pools: list[CapacityPoolStatus] = Field(default_factory=list)
    timestamp: datetime | None = None


class QueueFairnessConfig(BaseSchema):
    """Fairness policy for a workspace's queue behavior.

    Controls concurrency limits and priority weighting.
    """

    org_id: UUID
    max_concurrent_jobs: int = Field(
        default=5, ge=1, le=100, description="Hard cap on simultaneous jobs"
    )
    plan_tier: PlanTier = Field(
        default=PlanTier.STARTER, description="Plan tier for weighted fairness"
    )
    priority_weight: float = Field(
        default=1.0, ge=0.1, le=10.0, description="Relative scheduling weight"
    )


class SchedulingDecision(BaseSchema):
    """Complete scheduling result including assignment or queue position."""

    assigned: bool = Field(
        ..., description="True if workload was assigned to a worker"
    )
    assignment: WorkerAssignment | None = Field(
        default=None, description="Worker assignment (if assigned=True)"
    )
    queue_position: int | None = Field(
        default=None, ge=0, description="Position in queue (if assigned=False)"
    )
    estimated_wait_seconds: int | None = Field(
        default=None, ge=0, description="Estimated wait time in seconds"
    )
    reason: str = Field(
        default="", description="Explanation of scheduling decision"
    )
