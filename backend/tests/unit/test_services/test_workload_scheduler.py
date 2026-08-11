"""Unit tests for WorkloadScheduler — capacity isolation, worker selection, fairness.

Tests cover:
    - Capacity isolation: heavy workloads blocked when interactive is exhausted
    - Worker eligibility filtering: VRAM, capabilities, health, concurrency
    - Multi-criteria scoring: cache readiness, utilization, health, queue depth
    - Queue fairness: concurrency limits, plan tier weighting, anti-starvation
    - Scheduling decision: assignment vs queuing

Requirements: R65.8, R65.9, R65.10, R87.1, R87.2, R87.5,
             R88.1, R88.2, R88.3, R88.4, A2-039
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from types import ModuleType
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

# =============================================================================
# Mock heavy dependencies before importing application modules.
# =============================================================================

_sa_mock = MagicMock()
_sa_mock.DateTime = MagicMock
_sa_mock.Float = MagicMock
_sa_mock.Integer = MagicMock
_sa_mock.String = MagicMock
_sa_mock.Text = MagicMock
_sa_mock.Boolean = MagicMock
_sa_mock.ForeignKey = MagicMock
_sa_mock.Index = MagicMock
_sa_mock.func = MagicMock()
_sa_mock.select = MagicMock()
_sa_mock.update = MagicMock()

_sa_orm_mock = MagicMock()
_sa_orm_mock.Mapped = MagicMock
_sa_orm_mock.mapped_column = MagicMock(return_value=None)
_sa_orm_mock.relationship = MagicMock(return_value=None)
_sa_orm_mock.DeclarativeBase = type("DeclarativeBase", (), {})

_sa_dialects_pg_mock = MagicMock()
_sa_dialects_pg_mock.UUID = MagicMock
_sa_dialects_pg_mock.JSONB = MagicMock
_sa_dialects_pg_mock.ARRAY = MagicMock

_sa_ext_asyncio_mock = MagicMock()
_sa_ext_asyncio_mock.AsyncSession = MagicMock

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)
sys.modules.setdefault("sqlalchemy.exc", MagicMock())

# Mock structlog before importing app modules
_structlog_mock = MagicMock()
_structlog_mock.stdlib = MagicMock()
_structlog_mock.stdlib.BoundLogger = MagicMock
sys.modules.setdefault("structlog", _structlog_mock)
sys.modules.setdefault("structlog.stdlib", _structlog_mock.stdlib)

from app.schemas.validation import WorkloadClass
from app.schemas.workload_scheduler import (
    CapacityPoolStatus,
    PlanTier,
    QueueFairnessConfig,
    WorkerHealthStatus,
    WorkerInfo,
    WorkloadRequest,
)
from app.services.workload_scheduler import (
    ANTI_STARVATION_THRESHOLD_SECONDS,
    CapacityExhaustedError,
    ConcurrencyLimitExceededError,
    HEAVY_WORKLOAD_CLASSES,
    INTERACTIVE_WORKLOAD_CLASSES,
    NoEligibleWorkersError,
    WorkloadScheduler,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def scheduler() -> WorkloadScheduler:
    """Create a default WorkloadScheduler instance."""
    return WorkloadScheduler()


@pytest.fixture
def org_id() -> UUID:
    """A stable org UUID for tests."""
    return uuid4()


@pytest.fixture
def job_id() -> UUID:
    """A stable job UUID for tests."""
    return uuid4()


def _make_worker(
    org_id: UUID,
    vram_gb: float = 24.0,
    cached_models: list[str] | None = None,
    capabilities: list[str] | None = None,
    health: WorkerHealthStatus = WorkerHealthStatus.HEALTHY,
    utilization: float = 20.0,
    active_jobs: int = 0,
    queue_depth: int = 0,
    max_concurrent: int = 2,
) -> WorkerInfo:
    """Helper to create a WorkerInfo with sensible defaults."""
    return WorkerInfo(
        worker_id=uuid4(),
        org_id=org_id,
        provider_id="vast.ai",
        gpu_type="RTX 4090",
        vram_gb=vram_gb,
        cached_models=cached_models or [],
        capabilities=capabilities or [],
        health_status=health,
        utilization_percent=utilization,
        active_jobs=active_jobs,
        queue_depth=queue_depth,
        max_concurrent_jobs=max_concurrent,
    )


def _make_workload(
    org_id: UUID,
    job_id: UUID,
    workload_class: WorkloadClass = WorkloadClass.IMAGE_GENERATION,
    required_vram_gb: float = 12.0,
    required_models: list[str] | None = None,
    required_capabilities: list[str] | None = None,
    priority: int = 5,
    submitted_at: datetime | None = None,
) -> WorkloadRequest:
    """Helper to create a WorkloadRequest."""
    return WorkloadRequest(
        org_id=org_id,
        job_id=job_id,
        workload_class=workload_class,
        required_vram_gb=required_vram_gb,
        required_models=required_models or [],
        required_capabilities=required_capabilities or [],
        priority=priority,
        submitted_at=submitted_at,
    )


def _make_fairness_config(
    org_id: UUID,
    max_concurrent: int = 5,
    plan_tier: PlanTier = PlanTier.PRO,
) -> QueueFairnessConfig:
    """Helper to create a QueueFairnessConfig."""
    return QueueFairnessConfig(
        org_id=org_id,
        max_concurrent_jobs=max_concurrent,
        plan_tier=plan_tier,
    )


# =============================================================================
# Test: Worker Eligibility Filtering
# =============================================================================


class TestWorkerFiltering:
    """Tests for _filter_eligible_workers."""

    def test_excludes_unhealthy_workers(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Unhealthy workers are excluded from eligibility."""
        workers = [
            _make_worker(org_id, health=WorkerHealthStatus.UNHEALTHY),
            _make_worker(org_id, health=WorkerHealthStatus.HEALTHY),
        ]
        workload = _make_workload(org_id, job_id, required_vram_gb=0)
        eligible = scheduler._filter_eligible_workers(workload, workers)
        assert len(eligible) == 1
        assert eligible[0].health_status == WorkerHealthStatus.HEALTHY

    def test_excludes_workers_with_insufficient_vram(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Workers with less VRAM than required are excluded."""
        workers = [
            _make_worker(org_id, vram_gb=8.0),
            _make_worker(org_id, vram_gb=24.0),
        ]
        workload = _make_workload(org_id, job_id, required_vram_gb=12.0)
        eligible = scheduler._filter_eligible_workers(workload, workers)
        assert len(eligible) == 1
        assert eligible[0].vram_gb == 24.0

    def test_excludes_workers_missing_capabilities(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Workers missing required capabilities are excluded."""
        workers = [
            _make_worker(org_id, capabilities=["persistent_storage"]),
            _make_worker(org_id, capabilities=["persistent_storage", "multi_gpu"]),
        ]
        workload = _make_workload(org_id, job_id, required_vram_gb=0, required_capabilities=["persistent_storage", "multi_gpu"])
        eligible = scheduler._filter_eligible_workers(workload, workers)
        assert len(eligible) == 1
        assert "multi_gpu" in eligible[0].capabilities

    def test_excludes_workers_at_capacity(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Workers already at max concurrent jobs are excluded."""
        workers = [
            _make_worker(org_id, active_jobs=2, max_concurrent=2),
            _make_worker(org_id, active_jobs=1, max_concurrent=2),
        ]
        workload = _make_workload(org_id, job_id, required_vram_gb=0)
        eligible = scheduler._filter_eligible_workers(workload, workers)
        assert len(eligible) == 1
        assert eligible[0].active_jobs == 1

    def test_degraded_workers_are_eligible(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Degraded workers are still eligible (just scored lower)."""
        workers = [
            _make_worker(org_id, health=WorkerHealthStatus.DEGRADED),
        ]
        workload = _make_workload(org_id, job_id, required_vram_gb=0)
        eligible = scheduler._filter_eligible_workers(workload, workers)
        assert len(eligible) == 1

    def test_no_vram_requirement_accepts_all_healthy(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """When no VRAM is required, all healthy workers with capacity pass."""
        workers = [
            _make_worker(org_id, vram_gb=4.0),
            _make_worker(org_id, vram_gb=48.0),
        ]
        workload = _make_workload(org_id, job_id, required_vram_gb=0)
        eligible = scheduler._filter_eligible_workers(workload, workers)
        assert len(eligible) == 2


# =============================================================================
# Test: Worker Scoring
# =============================================================================


class TestWorkerScoring:
    """Tests for _score_workers multi-criteria ranking."""

    def test_prefers_worker_with_cached_models(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Worker with required models cached scores higher."""
        w_cached = _make_worker(org_id, cached_models=["flux_dev.safetensors"])
        w_uncached = _make_worker(org_id, cached_models=[])
        workload = _make_workload(org_id, job_id, required_models=["flux_dev.safetensors"])
        scored = scheduler._score_workers(workload, [w_uncached, w_cached])
        assert scored[0][0] == w_cached.worker_id

    def test_prefers_healthier_worker(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Healthy worker scores higher than degraded."""
        w_healthy = _make_worker(org_id, health=WorkerHealthStatus.HEALTHY)
        w_degraded = _make_worker(org_id, health=WorkerHealthStatus.DEGRADED)
        workload = _make_workload(org_id, job_id, required_vram_gb=0)
        scored = scheduler._score_workers(workload, [w_degraded, w_healthy])
        assert scored[0][0] == w_healthy.worker_id

    def test_prefers_lower_utilization(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Worker with lower utilization scores higher."""
        w_low = _make_worker(org_id, utilization=10.0)
        w_high = _make_worker(org_id, utilization=90.0)
        workload = _make_workload(org_id, job_id, required_vram_gb=0)
        scored = scheduler._score_workers(workload, [w_high, w_low])
        assert scored[0][0] == w_low.worker_id

    def test_prefers_shorter_queue(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Worker with shorter queue scores higher."""
        w_short = _make_worker(org_id, queue_depth=0)
        w_long = _make_worker(org_id, queue_depth=8)
        workload = _make_workload(org_id, job_id, required_vram_gb=0)
        scored = scheduler._score_workers(workload, [w_long, w_short])
        assert scored[0][0] == w_short.worker_id

    def test_vram_exact_match_scores_highest(self, scheduler: WorkloadScheduler) -> None:
        """Worker with VRAM close to requirement scores 1.0."""
        score = scheduler._score_vram_match(12.0, 12.0)
        assert score == 1.0

    def test_vram_moderate_excess_still_high(self, scheduler: WorkloadScheduler) -> None:
        """Worker with moderate VRAM excess scores 1.0 (within 1.5x)."""
        score = scheduler._score_vram_match(12.0, 16.0)
        assert score == 1.0

    def test_vram_large_excess_lower_score(self, scheduler: WorkloadScheduler) -> None:
        """Worker with large VRAM excess scores lower (waste penalty)."""
        score = scheduler._score_vram_match(8.0, 48.0)
        assert score == 0.5

    def test_cache_all_models_cached(self, scheduler: WorkloadScheduler) -> None:
        """All required models cached → score 1.0."""
        score = scheduler._score_cache_readiness(
            ["model_a", "model_b"], ["model_a", "model_b", "model_c"]
        )
        assert score == 1.0

    def test_cache_no_models_cached(self, scheduler: WorkloadScheduler) -> None:
        """No required models cached → score 0.0."""
        score = scheduler._score_cache_readiness(
            ["model_a", "model_b"], ["model_x"]
        )
        assert score == 0.0

    def test_cache_partial_match(self, scheduler: WorkloadScheduler) -> None:
        """Half of required models cached → score 0.5."""
        score = scheduler._score_cache_readiness(
            ["model_a", "model_b"], ["model_a"]
        )
        assert score == 0.5

    def test_no_models_required(self, scheduler: WorkloadScheduler) -> None:
        """Empty required models → all workers score 1.0."""
        score = scheduler._score_cache_readiness([], ["anything"])
        assert score == 1.0


# =============================================================================
# Test: Capacity Isolation
# =============================================================================


class TestCapacityIsolation:
    """Tests for capacity isolation between heavy and interactive workloads."""

    def test_interactive_workload_always_allowed(self, scheduler: WorkloadScheduler) -> None:
        """Interactive workloads pass capacity check even when pools exhausted."""
        pools = {
            WorkloadClass.INTERACTIVE_LANGUAGE: CapacityPoolStatus(
                workload_class=WorkloadClass.INTERACTIVE_LANGUAGE,
                total_capacity=10,
                active_jobs=10,
                queued_jobs=5,
                available_slots=0,
                is_exhausted=True,
            ),
        }
        result = scheduler._check_capacity_isolation(
            WorkloadClass.INTERACTIVE_LANGUAGE, pools
        )
        assert result is True

    def test_heavy_workload_blocked_when_interactive_exhausted(self, scheduler: WorkloadScheduler) -> None:
        """Heavy workloads are blocked when interactive capacity is exhausted (R88.2)."""
        pools = {
            WorkloadClass.INTERACTIVE_LANGUAGE: CapacityPoolStatus(
                workload_class=WorkloadClass.INTERACTIVE_LANGUAGE,
                total_capacity=5,
                active_jobs=5,
                queued_jobs=2,
                available_slots=0,
                is_exhausted=True,
            ),
            WorkloadClass.TRAINING: CapacityPoolStatus(
                workload_class=WorkloadClass.TRAINING,
                total_capacity=5,
                active_jobs=2,
                queued_jobs=0,
                available_slots=3,
                is_exhausted=False,
            ),
        }
        result = scheduler._check_capacity_isolation(
            WorkloadClass.TRAINING, pools
        )
        assert result is False

    def test_heavy_workload_allowed_when_interactive_has_capacity(self, scheduler: WorkloadScheduler) -> None:
        """Heavy workloads proceed when interactive capacity is available."""
        pools = {
            WorkloadClass.INTERACTIVE_LANGUAGE: CapacityPoolStatus(
                workload_class=WorkloadClass.INTERACTIVE_LANGUAGE,
                total_capacity=10,
                active_jobs=3,
                queued_jobs=0,
                available_slots=7,
                is_exhausted=False,
            ),
            WorkloadClass.VIDEO_GENERATION: CapacityPoolStatus(
                workload_class=WorkloadClass.VIDEO_GENERATION,
                total_capacity=5,
                active_jobs=2,
                queued_jobs=0,
                available_slots=3,
                is_exhausted=False,
            ),
        }
        result = scheduler._check_capacity_isolation(
            WorkloadClass.VIDEO_GENERATION, pools
        )
        assert result is True

    def test_heavy_workload_blocked_when_own_pool_exhausted(self, scheduler: WorkloadScheduler) -> None:
        """Heavy workload is blocked if its own class pool is exhausted."""
        pools = {
            WorkloadClass.INTERACTIVE_LANGUAGE: CapacityPoolStatus(
                workload_class=WorkloadClass.INTERACTIVE_LANGUAGE,
                total_capacity=10,
                active_jobs=5,
                queued_jobs=0,
                available_slots=5,
                is_exhausted=False,
            ),
            WorkloadClass.BATCH: CapacityPoolStatus(
                workload_class=WorkloadClass.BATCH,
                total_capacity=3,
                active_jobs=3,
                queued_jobs=2,
                available_slots=0,
                is_exhausted=True,
            ),
        }
        result = scheduler._check_capacity_isolation(
            WorkloadClass.BATCH, pools
        )
        assert result is False

    def test_image_generation_is_interactive(self) -> None:
        """IMAGE_GENERATION is classified as interactive."""
        assert WorkloadClass.IMAGE_GENERATION in INTERACTIVE_WORKLOAD_CLASSES

    def test_training_is_heavy(self) -> None:
        """TRAINING is classified as heavy."""
        assert WorkloadClass.TRAINING in HEAVY_WORKLOAD_CLASSES

    def test_video_is_heavy(self) -> None:
        """VIDEO_GENERATION is classified as heavy."""
        assert WorkloadClass.VIDEO_GENERATION in HEAVY_WORKLOAD_CLASSES

    def test_batch_is_heavy(self) -> None:
        """BATCH is classified as heavy."""
        assert WorkloadClass.BATCH in HEAVY_WORKLOAD_CLASSES


# =============================================================================
# Test: Queue Fairness and Anti-Starvation
# =============================================================================


class TestQueueFairness:
    """Tests for queue fairness: concurrency limits, plan tier, anti-starvation."""

    def test_concurrency_limit_queues_workload(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """When workspace exceeds concurrency limit, workload is queued (A2-039)."""
        workload = _make_workload(org_id, job_id)
        fairness = _make_fairness_config(org_id, max_concurrent=3)
        workers = [_make_worker(org_id)]

        decision = scheduler.schedule(
            workload=workload,
            available_workers=workers,
            fairness_config=fairness,
            active_jobs_for_workspace=3,  # At limit
        )
        assert decision.assigned is False
        assert "concurrency limit" in decision.reason.lower()

    def test_under_concurrency_limit_assigns(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """When workspace is under concurrency limit, workload is assigned."""
        workload = _make_workload(org_id, job_id, required_vram_gb=0)
        fairness = _make_fairness_config(org_id, max_concurrent=5)
        workers = [_make_worker(org_id)]

        decision = scheduler.schedule(
            workload=workload,
            available_workers=workers,
            fairness_config=fairness,
            active_jobs_for_workspace=2,
        )
        assert decision.assigned is True
        assert decision.assignment is not None

    def test_anti_starvation_boost_for_old_jobs(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Jobs waiting longer than threshold get priority boost (A2-039)."""
        old_time = datetime.now(UTC) - timedelta(seconds=ANTI_STARVATION_THRESHOLD_SECONDS * 3)
        boost = scheduler._compute_anti_starvation_boost(old_time)
        assert boost >= 3.0  # 3 thresholds exceeded

    def test_no_boost_for_recent_jobs(self, scheduler: WorkloadScheduler) -> None:
        """Recent jobs get no anti-starvation boost."""
        recent = datetime.now(UTC) - timedelta(seconds=60)
        boost = scheduler._compute_anti_starvation_boost(recent)
        assert boost == 0.0

    def test_no_boost_when_submitted_at_none(self, scheduler: WorkloadScheduler) -> None:
        """No boost when submitted_at is not provided."""
        boost = scheduler._compute_anti_starvation_boost(None)
        assert boost == 0.0

    def test_plan_tier_weighting(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Enterprise plan gets higher effective priority than free tier (A2-039)."""
        workload = _make_workload(org_id, job_id, priority=5)

        enterprise_config = _make_fairness_config(org_id, plan_tier=PlanTier.ENTERPRISE)
        free_config = _make_fairness_config(org_id, plan_tier=PlanTier.FREE)

        enterprise_priority = scheduler._compute_effective_priority(workload, enterprise_config)
        free_priority = scheduler._compute_effective_priority(workload, free_config)

        assert enterprise_priority > free_priority

    def test_interactive_workload_class_boost(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Interactive workloads get priority boost over batch (R65.10)."""
        interactive_wl = _make_workload(org_id, job_id, workload_class=WorkloadClass.INTERACTIVE_LANGUAGE, priority=5)
        batch_wl = _make_workload(org_id, job_id, workload_class=WorkloadClass.BATCH, priority=5)
        config = _make_fairness_config(org_id)

        interactive_prio = scheduler._compute_effective_priority(interactive_wl, config)
        batch_prio = scheduler._compute_effective_priority(batch_wl, config)

        assert interactive_prio > batch_prio

    def test_rank_pending_workloads_ordering(self, scheduler: WorkloadScheduler, org_id: UUID) -> None:
        """Pending workloads are ranked by effective priority (highest first)."""
        high_prio = _make_workload(org_id, uuid4(), priority=10)
        low_prio = _make_workload(org_id, uuid4(), priority=1)
        med_prio = _make_workload(org_id, uuid4(), priority=5)

        configs = {org_id: _make_fairness_config(org_id)}
        ranked = scheduler.rank_pending_workloads(
            [low_prio, high_prio, med_prio], configs
        )

        # Highest priority should come first
        assert ranked[0].priority == 10
        assert ranked[-1].priority == 1


# =============================================================================
# Test: Full Scheduling Decision
# =============================================================================


class TestSchedulingDecision:
    """Tests for the complete schedule() flow."""

    def test_assigns_best_worker(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Scheduler assigns workload to the highest-scoring worker."""
        w_ideal = _make_worker(
            org_id,
            vram_gb=16.0,
            cached_models=["flux_dev"],
            utilization=10.0,
            queue_depth=0,
        )
        w_suboptimal = _make_worker(
            org_id,
            vram_gb=48.0,
            cached_models=[],
            utilization=80.0,
            queue_depth=5,
        )
        workload = _make_workload(
            org_id, job_id,
            required_vram_gb=12.0,
            required_models=["flux_dev"],
        )
        fairness = _make_fairness_config(org_id)

        decision = scheduler.schedule(
            workload=workload,
            available_workers=[w_suboptimal, w_ideal],
            fairness_config=fairness,
        )
        assert decision.assigned is True
        assert decision.assignment is not None
        assert decision.assignment.worker_id == w_ideal.worker_id

    def test_queues_when_no_eligible_workers(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """When no workers are eligible, returns queued decision."""
        w_too_small = _make_worker(org_id, vram_gb=4.0)
        workload = _make_workload(org_id, job_id, required_vram_gb=24.0)
        fairness = _make_fairness_config(org_id)

        decision = scheduler.schedule(
            workload=workload,
            available_workers=[w_too_small],
            fairness_config=fairness,
        )
        assert decision.assigned is False
        assert "no eligible workers" in decision.reason.lower()

    def test_queues_when_no_workers_available(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Empty worker list results in queued decision."""
        workload = _make_workload(org_id, job_id)
        fairness = _make_fairness_config(org_id)

        decision = scheduler.schedule(
            workload=workload,
            available_workers=[],
            fairness_config=fairness,
        )
        assert decision.assigned is False

    def test_capacity_isolation_blocks_heavy_in_scheduling(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Heavy workload is queued when capacity isolation triggers."""
        workers = [_make_worker(org_id)]
        workload = _make_workload(
            org_id, job_id, workload_class=WorkloadClass.TRAINING, required_vram_gb=0,
        )
        fairness = _make_fairness_config(org_id)

        # Interactive is exhausted
        pools = {
            WorkloadClass.INTERACTIVE_LANGUAGE: CapacityPoolStatus(
                workload_class=WorkloadClass.INTERACTIVE_LANGUAGE,
                total_capacity=5,
                active_jobs=5,
                queued_jobs=0,
                available_slots=0,
                is_exhausted=True,
            ),
            WorkloadClass.TRAINING: CapacityPoolStatus(
                workload_class=WorkloadClass.TRAINING,
                total_capacity=5,
                active_jobs=1,
                queued_jobs=0,
                available_slots=4,
                is_exhausted=False,
            ),
        }

        decision = scheduler.schedule(
            workload=workload,
            available_workers=workers,
            fairness_config=fairness,
            capacity_pools=pools,
        )
        assert decision.assigned is False
        assert "capacity" in decision.reason.lower() or "starvation" in decision.reason.lower()

    def test_score_is_positive(self, scheduler: WorkloadScheduler, org_id: UUID, job_id: UUID) -> None:
        """Assigned worker always has a positive score."""
        workers = [_make_worker(org_id)]
        workload = _make_workload(org_id, job_id, required_vram_gb=0)
        fairness = _make_fairness_config(org_id)

        decision = scheduler.schedule(
            workload=workload,
            available_workers=workers,
            fairness_config=fairness,
        )
        assert decision.assigned is True
        assert decision.assignment is not None
        assert decision.assignment.score > 0.0


# =============================================================================
# Test: Capacity Status
# =============================================================================


class TestCapacityStatus:
    """Tests for get_capacity_status."""

    def test_returns_all_workload_classes(self, scheduler: WorkloadScheduler, org_id: UUID) -> None:
        """Capacity status includes all 8 workload classes."""
        workers = [_make_worker(org_id)]
        status = scheduler.get_capacity_status(
            workers=workers,
            active_jobs_by_class={},
            queued_jobs_by_class={},
        )
        assert len(status.pools) == len(WorkloadClass)

    def test_marks_exhausted_pool(self, scheduler: WorkloadScheduler, org_id: UUID) -> None:
        """Pool is marked exhausted when active_jobs >= total_capacity."""
        workers = [_make_worker(org_id, max_concurrent=2)]
        status = scheduler.get_capacity_status(
            workers=workers,
            active_jobs_by_class={WorkloadClass.IMAGE_GENERATION: 2},
            queued_jobs_by_class={},
        )
        img_pool = next(
            p for p in status.pools
            if p.workload_class == WorkloadClass.IMAGE_GENERATION
        )
        assert img_pool.is_exhausted is True
        assert img_pool.available_slots == 0
