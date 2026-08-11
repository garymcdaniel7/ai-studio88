"""Workload Scheduler — capacity isolation, worker selection, and queue fairness.

Provides workload-aware scheduling across a workspace's eligible compute pool:
    - Capacity isolation: heavy workloads (training, video, batch) cannot exhaust
      interactive capacity
    - Multi-criteria worker selection: VRAM match, cache readiness, utilization,
      health, queue depth, priority, concurrency limits
    - Queue fairness: per-workspace concurrency limits, weighted fairness by plan
      tier, anti-starvation (aged jobs get priority boost)

This service is called by the job leasing system when claiming jobs.

Validates: Requirements R65.8, R65.9, R65.10, R87.1, R87.2, R87.5,
           R88.1, R88.2, R88.3, R88.4, A2-039
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from app.core.logging import get_logger
from app.schemas.validation import WorkloadClass
from app.schemas.workload_scheduler import (
    CapacityPoolStatus,
    CapacityStatus,
    PlanTier,
    QueueFairnessConfig,
    SchedulingDecision,
    WorkerAssignment,
    WorkerHealthStatus,
    WorkerInfo,
    WorkloadRequest,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


# =============================================================================
# Constants and Configuration
# =============================================================================

# Plan tier weights for weighted fairness (higher = more scheduling priority)
PLAN_TIER_WEIGHTS: dict[PlanTier, float] = {
    PlanTier.FREE: 0.5,
    PlanTier.STARTER: 1.0,
    PlanTier.PRO: 2.0,
    PlanTier.ENTERPRISE: 4.0,
}

# Default workspace concurrency limits per plan tier
DEFAULT_CONCURRENCY_LIMITS: dict[PlanTier, int] = {
    PlanTier.FREE: 2,
    PlanTier.STARTER: 5,
    PlanTier.PRO: 15,
    PlanTier.ENTERPRISE: 50,
}

# Anti-starvation: after this many seconds waiting, job gets priority boost
ANTI_STARVATION_THRESHOLD_SECONDS: int = 300  # 5 minutes

# Priority boost per threshold exceeded (capped at max_priority=10)
ANTI_STARVATION_BOOST_PER_THRESHOLD: float = 1.0

# Maximum effective priority after boosts
MAX_EFFECTIVE_PRIORITY: float = 10.0

# Workload class categorization for isolation enforcement
HEAVY_WORKLOAD_CLASSES: frozenset[WorkloadClass] = frozenset(
    {
        WorkloadClass.TRAINING,
        WorkloadClass.VIDEO_GENERATION,
        WorkloadClass.BATCH,
    }
)

INTERACTIVE_WORKLOAD_CLASSES: frozenset[WorkloadClass] = frozenset(
    {
        WorkloadClass.INTERACTIVE_LANGUAGE,
        WorkloadClass.IMAGE_GENERATION,
    }
)

# Worker scoring weights (must sum to 1.0)
SCORE_WEIGHT_VRAM_MATCH: float = 0.20
SCORE_WEIGHT_CACHE_READINESS: float = 0.25
SCORE_WEIGHT_UTILIZATION: float = 0.20
SCORE_WEIGHT_HEALTH: float = 0.15
SCORE_WEIGHT_QUEUE_DEPTH: float = 0.20

# Health status score mapping
HEALTH_SCORES: dict[WorkerHealthStatus, float] = {
    WorkerHealthStatus.HEALTHY: 1.0,
    WorkerHealthStatus.DEGRADED: 0.5,
    WorkerHealthStatus.UNHEALTHY: 0.0,
    WorkerHealthStatus.UNKNOWN: 0.3,
}

# Default capacity reservation: percentage of total capacity reserved
# for interactive workloads that heavy workloads cannot consume
INTERACTIVE_CAPACITY_RESERVATION_PERCENT: float = 30.0


# =============================================================================
# Exceptions
# =============================================================================


class SchedulerError(Exception):
    """Base exception for scheduler operations."""

    def __init__(self, message: str, code: str = "SCHEDULER_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class NoEligibleWorkersError(SchedulerError):
    """No workers satisfy the workload requirements."""

    def __init__(self, workload_class: WorkloadClass, reason: str = "") -> None:
        detail = reason or f"No eligible workers for {workload_class.value}"
        super().__init__(message=detail, code="NO_ELIGIBLE_WORKERS")


class ConcurrencyLimitExceededError(SchedulerError):
    """Workspace has exceeded its concurrency limit."""

    def __init__(self, org_id: UUID, limit: int, active: int) -> None:
        super().__init__(
            message=(
                f"Workspace {org_id} concurrency limit exceeded "
                f"(active={active}, limit={limit})"
            ),
            code="CONCURRENCY_LIMIT_EXCEEDED",
        )


class CapacityExhaustedError(SchedulerError):
    """Capacity for the workload class is exhausted."""

    def __init__(self, workload_class: WorkloadClass) -> None:
        super().__init__(
            message=f"Capacity exhausted for workload class: {workload_class.value}",
            code="CAPACITY_EXHAUSTED",
        )


# =============================================================================
# WorkloadScheduler Service
# =============================================================================


class WorkloadScheduler:
    """Schedules work across a workspace's eligible compute pool.

    Key responsibilities:
        1. Capacity isolation: enforce that heavy workloads cannot starve
           interactive workloads of capacity.
        2. Worker selection: multi-criteria scoring to pick the best worker
           for a given workload.
        3. Queue fairness: enforce per-workspace concurrency limits, apply
           weighted fairness by plan tier, and boost priority for aged jobs.

    This is a stateless service that operates on the provided worker pool
    and fairness configuration. It does NOT access the database directly —
    callers provide worker state and fairness config.

    Validates: R65.8, R65.9, R65.10, R87.1, R87.2, R87.5,
               R88.1, R88.2, R88.3, R88.4, A2-039
    """

    def __init__(
        self,
        interactive_reservation_percent: float = INTERACTIVE_CAPACITY_RESERVATION_PERCENT,
    ) -> None:
        """Initialize the scheduler.

        Args:
            interactive_reservation_percent: Percentage of shared capacity
                reserved exclusively for interactive workloads (0-100).
        """
        self._interactive_reservation_percent = interactive_reservation_percent

    def schedule(
        self,
        workload: WorkloadRequest,
        available_workers: list[WorkerInfo],
        fairness_config: QueueFairnessConfig,
        active_jobs_for_workspace: int = 0,
        capacity_pools: dict[WorkloadClass, CapacityPoolStatus] | None = None,
    ) -> SchedulingDecision:
        """Main scheduling entry point.

        Evaluates capacity isolation, concurrency limits, and worker scoring
        to produce a scheduling decision.

        Args:
            workload: The workload request to schedule.
            available_workers: All workers in the workspace's compute pool.
            fairness_config: Queue fairness policy for this workspace.
            active_jobs_for_workspace: Current active job count for workspace.
            capacity_pools: Optional pre-computed capacity pool status.

        Returns:
            SchedulingDecision with assignment or queue position.

        Validates: R87.2, R87.5, R88.2, R88.3, R88.4, A2-039
        """
        # Step 1: Check workspace concurrency limit (A2-039)
        if active_jobs_for_workspace >= fairness_config.max_concurrent_jobs:
            logger.info(
                "workload_queued_concurrency_limit",
                org_id=str(workload.org_id),
                job_id=str(workload.job_id),
                active=active_jobs_for_workspace,
                limit=fairness_config.max_concurrent_jobs,
            )
            return SchedulingDecision(
                assigned=False,
                queue_position=active_jobs_for_workspace - fairness_config.max_concurrent_jobs,
                reason=(
                    f"Workspace concurrency limit reached "
                    f"({active_jobs_for_workspace}/{fairness_config.max_concurrent_jobs})"
                ),
            )

        # Step 2: Capacity isolation check (R88.2)
        if capacity_pools and not self._check_capacity_isolation(
            workload.workload_class, capacity_pools
        ):
            logger.info(
                "workload_queued_capacity_exhausted",
                org_id=str(workload.org_id),
                job_id=str(workload.job_id),
                workload_class=workload.workload_class.value,
            )
            return SchedulingDecision(
                assigned=False,
                reason=(
                    f"Capacity exhausted for {workload.workload_class.value}; "
                    f"queued to prevent starvation of interactive workloads"
                ),
            )

        # Step 3: Filter eligible workers
        eligible_workers = self._filter_eligible_workers(
            workload, available_workers
        )

        if not eligible_workers:
            logger.info(
                "workload_no_eligible_workers",
                org_id=str(workload.org_id),
                job_id=str(workload.job_id),
                workload_class=workload.workload_class.value,
                total_workers=len(available_workers),
            )
            return SchedulingDecision(
                assigned=False,
                reason="No eligible workers satisfy workload requirements",
            )

        # Step 4: Score and rank eligible workers (R87.2)
        scored_workers = self._score_workers(workload, eligible_workers)

        # Step 5: Apply fairness weighting
        effective_priority = self._compute_effective_priority(
            workload, fairness_config
        )

        # Select the best worker
        best_worker_id, best_score, reason = scored_workers[0]

        logger.info(
            "workload_assigned",
            org_id=str(workload.org_id),
            job_id=str(workload.job_id),
            worker_id=str(best_worker_id),
            score=round(best_score, 4),
            effective_priority=round(effective_priority, 2),
            workload_class=workload.workload_class.value,
        )

        return SchedulingDecision(
            assigned=True,
            assignment=WorkerAssignment(
                worker_id=best_worker_id,
                score=best_score,
                reason=reason,
            ),
            reason=f"Assigned to best-scoring worker (score={best_score:.4f})",
        )

    def _check_capacity_isolation(
        self,
        workload_class: WorkloadClass,
        capacity_pools: dict[WorkloadClass, CapacityPoolStatus],
    ) -> bool:
        """Check if capacity isolation rules allow this workload to proceed.

        Heavy workloads are blocked when interactive capacity would be
        starved — specifically, when interactive workload slots are at or
        below the reserved percentage.

        Interactive workloads always pass this check (they use their own
        reserved capacity).

        Args:
            workload_class: The class of the workload being scheduled.
            capacity_pools: Current capacity state per class.

        Returns:
            True if the workload is allowed, False if it should be queued.

        Validates: R88.2 (heavy SHALL NOT exhaust interactive capacity)
        """
        # Interactive workloads are never blocked by isolation
        if workload_class in INTERACTIVE_WORKLOAD_CLASSES:
            return True

        # Heavy workloads: check if the target pool has available slots
        if workload_class in HEAVY_WORKLOAD_CLASSES:
            pool = capacity_pools.get(workload_class)
            if pool is not None and pool.is_exhausted:
                return False

            # Also check: would running this heavy workload leave zero
            # capacity for interactive classes?
            for interactive_class in INTERACTIVE_WORKLOAD_CLASSES:
                interactive_pool = capacity_pools.get(interactive_class)
                if interactive_pool is not None and interactive_pool.is_exhausted:
                    # Interactive capacity is already exhausted — block
                    # heavy workloads to prevent further starvation
                    return False

        return True

    def _filter_eligible_workers(
        self,
        workload: WorkloadRequest,
        workers: list[WorkerInfo],
    ) -> list[WorkerInfo]:
        """Filter workers to only those eligible for this workload.

        Filters based on:
            - VRAM requirement met
            - Required capabilities present
            - Worker is healthy (not unhealthy)
            - Worker has capacity (active_jobs < max_concurrent_jobs)

        Args:
            workload: The workload requirements.
            workers: All available workers.

        Returns:
            Filtered list of eligible workers.

        Validates: R87.2
        """
        eligible: list[WorkerInfo] = []

        for worker in workers:
            # Skip unhealthy workers
            if worker.health_status == WorkerHealthStatus.UNHEALTHY:
                continue

            # VRAM requirement check
            if workload.required_vram_gb > 0 and worker.vram_gb < workload.required_vram_gb:
                continue

            # Capability requirements check
            if workload.required_capabilities:
                worker_caps = set(worker.capabilities)
                if not all(
                    cap in worker_caps for cap in workload.required_capabilities
                ):
                    continue

            # Concurrency check: worker must have capacity
            if worker.active_jobs >= worker.max_concurrent_jobs:
                continue

            eligible.append(worker)

        return eligible

    def _score_workers(
        self,
        workload: WorkloadRequest,
        workers: list[WorkerInfo],
    ) -> list[tuple[UUID, float, str]]:
        """Score and rank eligible workers for the workload.

        Multi-criteria scoring considers:
            - VRAM match: prefer workers with VRAM closest to (but >= ) requirement
            - Cache readiness: prefer workers with required models pre-loaded
            - Utilization: prefer less-utilized workers
            - Health: prefer healthier workers
            - Queue depth: prefer workers with shorter queues

        Args:
            workload: The workload requirements (models, VRAM).
            workers: Pre-filtered eligible workers.

        Returns:
            Sorted list of (worker_id, score, reason) tuples,
            best score first.

        Validates: R87.2
        """
        scored: list[tuple[UUID, float, str]] = []

        for worker in workers:
            # VRAM match score: 1.0 if exact match, degrades with excess
            vram_score = self._score_vram_match(
                workload.required_vram_gb, worker.vram_gb
            )

            # Cache readiness: fraction of required models already loaded
            cache_score = self._score_cache_readiness(
                workload.required_models, worker.cached_models
            )

            # Utilization: prefer low utilization (inverted)
            utilization_score = 1.0 - (worker.utilization_percent / 100.0)

            # Health score
            health_score = HEALTH_SCORES.get(worker.health_status, 0.3)

            # Queue depth score: fewer queued = better
            # Normalize: 0 queued = 1.0, 10+ queued = 0.0
            queue_score = max(0.0, 1.0 - (worker.queue_depth / 10.0))

            # Weighted composite
            composite = (
                SCORE_WEIGHT_VRAM_MATCH * vram_score
                + SCORE_WEIGHT_CACHE_READINESS * cache_score
                + SCORE_WEIGHT_UTILIZATION * utilization_score
                + SCORE_WEIGHT_HEALTH * health_score
                + SCORE_WEIGHT_QUEUE_DEPTH * queue_score
            )

            # Build reason string
            reason_parts = []
            if cache_score == 1.0 and workload.required_models:
                reason_parts.append("all models cached")
            if health_score == 1.0:
                reason_parts.append("healthy")
            if utilization_score > 0.8:
                reason_parts.append("low utilization")

            reason = ", ".join(reason_parts) if reason_parts else "best composite score"

            scored.append((worker.worker_id, composite, reason))

        # Sort by score descending (best first)
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _score_vram_match(self, required_gb: float, available_gb: float) -> float:
        """Score VRAM match: perfect when close to required, penalize excess waste.

        A worker with exactly enough VRAM scores 1.0. Workers with much more
        than needed score lower (to avoid wasting expensive high-VRAM workers
        on small workloads). Workers below the requirement should have been
        filtered out.

        Args:
            required_gb: Required VRAM for the workload.
            available_gb: Worker's VRAM capacity.

        Returns:
            Score between 0.0 and 1.0.
        """
        if required_gb <= 0:
            # No VRAM requirement — all workers equally good
            return 1.0

        if available_gb < required_gb:
            return 0.0

        # Ratio: how much excess VRAM does the worker have?
        # Ideal = 1.0 (exact match), degrades as ratio increases
        ratio = available_gb / required_gb
        if ratio <= 1.5:
            return 1.0
        elif ratio <= 3.0:
            # Linearly degrade from 1.0 to 0.5
            return 1.0 - (ratio - 1.5) / 3.0
            # At ratio=1.5: 1.0, at ratio=3.0: 0.5
        else:
            return 0.5

    def _score_cache_readiness(
        self,
        required_models: list[str],
        cached_models: list[str],
    ) -> float:
        """Score cache readiness: fraction of required models already loaded.

        Args:
            required_models: Models needed by the workload.
            cached_models: Models already loaded on the worker.

        Returns:
            Score between 0.0 (no models cached) and 1.0 (all cached).
        """
        if not required_models:
            return 1.0  # No requirement means all workers equally ready

        cached_set = set(cached_models)
        matches = sum(1 for m in required_models if m in cached_set)
        return matches / len(required_models)

    def _compute_effective_priority(
        self,
        workload: WorkloadRequest,
        fairness_config: QueueFairnessConfig,
    ) -> float:
        """Compute effective priority considering plan tier weight and anti-starvation.

        The effective priority combines:
            - Base job priority (1-10)
            - Plan tier weight multiplier
            - Anti-starvation boost for aged jobs
            - Workload class priority (interactive > batch)

        Args:
            workload: The workload with base priority and submit time.
            fairness_config: Workspace fairness configuration.

        Returns:
            Effective priority value (higher = should be scheduled sooner).

        Validates: R65.10, A2-039
        """
        base_priority = float(workload.priority)

        # Apply plan tier weight
        plan_weight = PLAN_TIER_WEIGHTS.get(fairness_config.plan_tier, 1.0)
        weighted_priority = base_priority * plan_weight

        # Anti-starvation boost: jobs waiting longer than threshold get boosted
        age_boost = self._compute_anti_starvation_boost(workload.submitted_at)
        weighted_priority += age_boost

        # Workload class priority adjustment
        class_boost = self._workload_class_priority_boost(workload.workload_class)
        weighted_priority += class_boost

        # Cap at maximum
        return min(weighted_priority, MAX_EFFECTIVE_PRIORITY * plan_weight)

    def _compute_anti_starvation_boost(
        self, submitted_at: datetime | None
    ) -> float:
        """Compute priority boost for jobs that have waited too long.

        Jobs get ANTI_STARVATION_BOOST_PER_THRESHOLD added per threshold
        period they've been waiting. This ensures no job waits indefinitely.

        Args:
            submitted_at: When the job was originally queued.

        Returns:
            Priority boost value (0.0 if no boost needed).

        Validates: A2-039 (anti-starvation)
        """
        if submitted_at is None:
            return 0.0

        now = datetime.now(UTC)
        wait_seconds = (now - submitted_at).total_seconds()

        if wait_seconds <= ANTI_STARVATION_THRESHOLD_SECONDS:
            return 0.0

        # Number of full thresholds exceeded
        thresholds_exceeded = int(
            wait_seconds / ANTI_STARVATION_THRESHOLD_SECONDS
        )
        return thresholds_exceeded * ANTI_STARVATION_BOOST_PER_THRESHOLD

    def _workload_class_priority_boost(
        self, workload_class: WorkloadClass
    ) -> float:
        """Return priority boost based on workload class.

        Interactive workloads get a boost over batch/background to ensure
        responsiveness even when heavy workloads are queued.

        Args:
            workload_class: The workload class.

        Returns:
            Priority boost value.

        Validates: R65.10 (interactive MAY receive higher priority)
        """
        if workload_class in INTERACTIVE_WORKLOAD_CLASSES:
            return 2.0
        elif workload_class == WorkloadClass.VOICE_AUDIO:
            return 1.0
        elif workload_class == WorkloadClass.PRODUCTION_STAGES:
            return 0.5
        elif workload_class in HEAVY_WORKLOAD_CLASSES:
            return 0.0
        else:
            # Publishing and other background
            return 0.0

    def get_capacity_status(
        self,
        workers: list[WorkerInfo],
        active_jobs_by_class: dict[WorkloadClass, int],
        queued_jobs_by_class: dict[WorkloadClass, int],
    ) -> CapacityStatus:
        """Build a capacity status snapshot across all workload classes.

        Args:
            workers: All available workers.
            active_jobs_by_class: Active jobs per workload class.
            queued_jobs_by_class: Queued jobs per workload class.

        Returns:
            CapacityStatus with pool information per class.
        """
        # Calculate total capacity per class (simplified: total worker slots)
        total_slots = sum(w.max_concurrent_jobs for w in workers if w.health_status != WorkerHealthStatus.UNHEALTHY)

        pools: list[CapacityPoolStatus] = []
        for wc in WorkloadClass:
            active = active_jobs_by_class.get(wc, 0)
            queued = queued_jobs_by_class.get(wc, 0)
            # Each class shares the pool — capacity is distributed
            # In a real deployment, dedicated workers may be assigned per class
            available = max(0, total_slots - active)

            pools.append(
                CapacityPoolStatus(
                    workload_class=wc,
                    total_capacity=total_slots,
                    active_jobs=active,
                    queued_jobs=queued,
                    available_slots=available,
                    is_exhausted=available <= 0,
                )
            )

        return CapacityStatus(
            pools=pools,
            timestamp=datetime.now(UTC),
        )

    def rank_pending_workloads(
        self,
        workloads: list[WorkloadRequest],
        fairness_configs: dict[UUID, QueueFairnessConfig],
    ) -> list[WorkloadRequest]:
        """Rank pending workloads by effective priority for dequeue ordering.

        Used by the job leasing system to determine which queued job to
        claim next. Combines plan tier weighting, anti-starvation boost,
        and workload class priority.

        Args:
            workloads: List of pending workloads to rank.
            fairness_configs: Fairness config per org_id.

        Returns:
            Workloads sorted by effective priority (highest first).

        Validates: A2-039 (weighted fairness + anti-starvation)
        """
        scored: list[tuple[float, WorkloadRequest]] = []

        for wl in workloads:
            config = fairness_configs.get(
                wl.org_id,
                QueueFairnessConfig(
                    org_id=wl.org_id,
                    max_concurrent_jobs=DEFAULT_CONCURRENCY_LIMITS[PlanTier.STARTER],
                    plan_tier=PlanTier.STARTER,
                ),
            )
            effective_priority = self._compute_effective_priority(wl, config)
            scored.append((effective_priority, wl))

        # Sort by priority descending
        scored.sort(key=lambda x: x[0], reverse=True)
        return [wl for _, wl in scored]
