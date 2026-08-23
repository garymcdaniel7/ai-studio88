"""AIOS — AI Studio Intelligence Operating System.

The intelligence layer between all clients and backend services.

Exposes the fleet provisioner and priority scheduler at package level.
"""

from __future__ import annotations

from .fleet import (  # noqa: F401
    FleetConfig,
    FleetManager,
    PriorityTier,
    RunPodWorkerProvider,
    ScalePlan,
    SimulationWorkerProvider,
    TIER_RANK,
    VastWorkerProvider,
    Worker,
    WorkerProvider,
    build_worker_provider,
    count_queued_jobs,
    desired_worker_count,
    fleet_config_from_env,
    make_queue_reader,
    plan_scale,
    tier_for_workload,
)
from .scheduler import (  # noqa: F401
    Assignment,
    AssignmentPlan,
    PriorityScheduler,
    QueuedJob,
    assign_jobs,
    queued_job_from_job,
    sort_queued,
)

__all__ = [
    # fleet
    "FleetConfig",
    "FleetManager",
    "PriorityTier",
    "RunPodWorkerProvider",
    "ScalePlan",
    "SimulationWorkerProvider",
    "TIER_RANK",
    "VastWorkerProvider",
    "Worker",
    "WorkerProvider",
    "build_worker_provider",
    "count_queued_jobs",
    "desired_worker_count",
    "fleet_config_from_env",
    "make_queue_reader",
    "plan_scale",
    "tier_for_workload",
    # scheduler
    "Assignment",
    "AssignmentPlan",
    "PriorityScheduler",
    "QueuedJob",
    "assign_jobs",
    "queued_job_from_job",
    "sort_queued",
]
