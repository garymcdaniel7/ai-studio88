"""AIOS — AI Studio Intelligence Operating System.

The intelligence layer between all clients and backend services.

Exposes the fleet provisioner, priority scheduler, failure learning and
rollout coordinator at package level.
"""

from __future__ import annotations

from .failure_learning import (  # noqa: F401
    DEFAULT_THRESHOLD,
    DEFAULT_WINDOW,
    FailureAggregate,
    FailureLearning,
    FailureReason,
    FailedGeneration,
    Recommendation,
    Severity,
    aggregate_failures,
    classify_failure,
    failed_generation_from_row,
    generate_recommendations,
)
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
from .rollout import (  # noqa: F401
    RolloutCoordinator,
    RolloutPhase,
    RolloutPlan,
    RolloutProvider,
    RolloutStep,
    SimulationRolloutProvider,
    build_rollout_provider,
    config_change_from_recommendation,
    staged_rollout,
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
    # failure learning
    "DEFAULT_THRESHOLD",
    "DEFAULT_WINDOW",
    "FailureAggregate",
    "FailureLearning",
    "FailureReason",
    "FailedGeneration",
    "Recommendation",
    "Severity",
    "aggregate_failures",
    "classify_failure",
    "failed_generation_from_row",
    "generate_recommendations",
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
    # rollout
    "RolloutCoordinator",
    "RolloutPhase",
    "RolloutPlan",
    "RolloutProvider",
    "RolloutStep",
    "SimulationRolloutProvider",
    "build_rollout_provider",
    "config_change_from_recommendation",
    "staged_rollout",
    # scheduler
    "Assignment",
    "AssignmentPlan",
    "PriorityScheduler",
    "QueuedJob",
    "assign_jobs",
    "queued_job_from_job",
    "sort_queued",
]
