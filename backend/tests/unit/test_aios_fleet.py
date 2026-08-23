"""Unit coverage for the AIOS Fleet Provisioner (queue-depth scaling, pause-on-idle)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.aios.fleet import (
    FleetConfig,
    FleetManager,
    PriorityTier,
    ScalePlan,
    SimulationWorkerProvider,
    Worker,
    build_worker_provider,
    count_queued_jobs,
    desired_worker_count,
    fleet_config_from_env,
    make_queue_reader,
    plan_scale,
    tier_for_workload,
)

NOW = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)


def _cfg(**overrides) -> FleetConfig:
    values = {"max_workers": 8, "warm_min": 1, "idle_timeout_min": 10, "jobs_per_worker": 1}
    values.update(overrides)
    return FleetConfig(**values)


def _worker(
    worker_id: str,
    *,
    status: str = "idle",
    idle_since: datetime | None = None,
    current_job_id: str | None = None,
) -> Worker:
    return Worker(
        id=worker_id,
        provider="simulation",
        status=status,
        idle_since=idle_since,
        current_job_id=current_job_id,
    )


# =============================================================================
# Priority tiers
# =============================================================================


@pytest.mark.unit
def test_tier_for_workload_maps_known_classes() -> None:
    # P0 = image / voice / music
    assert tier_for_workload("image_generation") is PriorityTier.P0
    assert tier_for_workload(None, "voice") is PriorityTier.P0
    assert tier_for_workload("music") is PriorityTier.P0
    assert tier_for_workload(None, "audio_mix") is PriorityTier.P0
    # P1 = video
    assert tier_for_workload("video_generation") is PriorityTier.P1
    assert tier_for_workload(None, "video") is PriorityTier.P1
    # P2 = batch / assembly / training / publishing
    assert tier_for_workload("batch") is PriorityTier.P2
    assert tier_for_workload("assembly") is PriorityTier.P2
    assert tier_for_workload("lora_training") is PriorityTier.P2
    assert tier_for_workload("publishing_dispatch") is PriorityTier.P2


@pytest.mark.unit
def test_tier_defaults_to_p2_for_unknown_workload() -> None:
    assert tier_for_workload("mystery_workload") is PriorityTier.P2
    assert tier_for_workload(None) is PriorityTier.P2
    assert tier_for_workload("", "") is PriorityTier.P2
    # Explicit default is honored
    assert tier_for_workload("mystery", default=PriorityTier.P1) is PriorityTier.P1


# =============================================================================
# Queue-depth worker scaling
# =============================================================================


@pytest.mark.unit
def test_desired_workers_floor_at_warm_min() -> None:
    cfg = _cfg(warm_min=2)
    assert desired_worker_count(0, cfg) == 2
    assert desired_worker_count(1, cfg) == 2
    assert desired_worker_count(2, cfg) == 2


@pytest.mark.unit
def test_desired_workers_scales_with_queue_depth() -> None:
    cfg = _cfg(warm_min=1)
    assert desired_worker_count(3, cfg) == 3
    assert desired_worker_count(8, cfg) == 8


@pytest.mark.unit
def test_desired_workers_capped_at_max_workers() -> None:
    cfg = _cfg(max_workers=4, warm_min=1)
    assert desired_worker_count(4, cfg) == 4
    assert desired_worker_count(50, cfg) == 4


@pytest.mark.unit
def test_desired_workers_honors_jobs_per_worker() -> None:
    cfg = _cfg(jobs_per_worker=3)
    assert desired_worker_count(1, cfg) == 1
    assert desired_worker_count(3, cfg) == 1
    assert desired_worker_count(4, cfg) == 2
    assert desired_worker_count(7, cfg) == 3


@pytest.mark.unit
def test_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("FLEET_MAX_WORKERS", "6")
    monkeypatch.setenv("FLEET_WARM_MIN", "2")
    monkeypatch.setenv("FLEET_IDLE_TIMEOUT_MIN", "25")
    monkeypatch.setenv("FLEET_JOBS_PER_WORKER", "2")
    cfg = fleet_config_from_env()
    assert cfg.max_workers == 6
    assert cfg.warm_min == 2
    assert cfg.idle_timeout_min == 25
    assert cfg.jobs_per_worker == 2


@pytest.mark.unit
def test_config_from_env_uses_defaults_when_unset(monkeypatch) -> None:
    for name in ("FLEET_MAX_WORKERS", "FLEET_WARM_MIN", "FLEET_IDLE_TIMEOUT_MIN", "FLEET_JOBS_PER_WORKER"):
        monkeypatch.delenv(name, raising=False)
    cfg = fleet_config_from_env()
    assert cfg.max_workers == 8
    assert cfg.warm_min == 1
    assert cfg.idle_timeout_min == 10
    assert cfg.jobs_per_worker == 1


@pytest.mark.unit
def test_config_rejects_warm_min_above_max() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        FleetConfig(max_workers=2, warm_min=5)


@pytest.mark.unit
def test_config_rejects_nonpositive_max_workers() -> None:
    with pytest.raises(ValueError):
        FleetConfig(max_workers=0)


# =============================================================================
# Scale planning
# =============================================================================


@pytest.mark.unit
def test_plan_launches_when_queue_exceeds_active_capacity() -> None:
    workers = [_worker("w1", idle_since=NOW - timedelta(minutes=30))]
    plan = plan_scale(queue_depth=6, workers=workers, config=_cfg(), now=NOW)
    assert plan.desired_workers == 6
    assert plan.launch_count == 5
    assert plan.scale_up is True
    assert plan.resume == []
    assert plan.pause == []


@pytest.mark.unit
def test_plan_resumes_paused_workers_before_launching() -> None:
    workers = [_worker("w1", status="paused"), _worker("w2", idle_since=NOW - timedelta(minutes=1))]
    plan = plan_scale(queue_depth=4, workers=workers, config=_cfg(), now=NOW)
    # desired 4, one active → resume the paused worker, then launch 2 more
    assert plan.desired_workers == 4
    assert plan.resume == ["w1"]
    assert plan.launch_count == 2


@pytest.mark.unit
def test_plan_never_launches_beyond_max_workers() -> None:
    cfg = _cfg(max_workers=2, warm_min=1)
    workers = [_worker("w1"), _worker("w2")]
    plan = plan_scale(queue_depth=10, workers=workers, config=cfg, now=NOW)
    assert plan.desired_workers == 2
    assert plan.launch_count == 0
    assert plan.resume == []


@pytest.mark.unit
def test_plan_pauses_idle_workers_beyond_warm_floor_after_timeout() -> None:
    workers = [
        _worker("w1", idle_since=NOW - timedelta(minutes=30)),
        _worker("w2", idle_since=NOW - timedelta(minutes=25)),
        _worker("w3", status="busy", current_job_id="j9"),
    ]
    plan = plan_scale(queue_depth=0, workers=workers, config=_cfg(warm_min=1), now=NOW)
    # desired = warm floor = 1; active = 3 → pause the 2 long-idle workers,
    # longest idle first
    assert plan.desired_workers == 1
    assert plan.pause == ["w1", "w2"]
    assert plan.scale_down is True
    assert plan.launch_count == 0


@pytest.mark.unit
def test_plan_does_not_pause_before_idle_timeout() -> None:
    workers = [_worker("w1", idle_since=NOW - timedelta(minutes=5))]
    plan = plan_scale(queue_depth=0, workers=workers, config=_cfg(), now=NOW)
    assert plan.desired_workers == 1
    assert plan.pause == []
    assert plan.scale_down is False


@pytest.mark.unit
def test_plan_never_pauses_below_warm_floor() -> None:
    workers = [_worker("w1", idle_since=NOW - timedelta(minutes=45))]
    plan = plan_scale(queue_depth=0, workers=workers, config=_cfg(warm_min=1), now=NOW)
    # active == desired == warm_min → no excess, nothing to pause
    assert plan.desired_workers == 1
    assert plan.pause == []


@pytest.mark.unit
def test_plan_does_not_pause_busy_workers() -> None:
    workers = [
        _worker("w1", status="busy", current_job_id="j1", idle_since=NOW - timedelta(minutes=60)),
        _worker("w2", idle_since=NOW - timedelta(minutes=60)),
    ]
    plan = plan_scale(queue_depth=1, workers=workers, config=_cfg(warm_min=1), now=NOW)
    # desired 1, active 2 → only the idle worker is a pause candidate
    assert plan.pause == ["w2"]


@pytest.mark.unit
def test_plan_is_stable_noop_when_fleet_matches_demand() -> None:
    workers = [_worker("w1", idle_since=NOW - timedelta(minutes=1))]
    plan = plan_scale(queue_depth=1, workers=workers, config=_cfg(), now=NOW)
    assert plan.desired_workers == 1
    assert plan.launch_count == 0
    assert plan.resume == []
    assert plan.pause == []
    assert plan.scale_up is False
    assert plan.scale_down is False


# =============================================================================
# Simulation provider adapter
# =============================================================================


@pytest.mark.unit
def test_simulation_provider_launch_pause_resume_terminate_cycle() -> None:
    provider = SimulationWorkerProvider()
    worker = provider.launch({"gpu": "RTX_3090"})
    assert worker.status == "idle"
    assert worker.labels == {"gpu": "RTX_3090"}
    assert len(provider.list_workers()) == 1

    assert provider.pause(worker.id) is True
    assert provider.get(worker.id).status == "paused"
    assert provider.pause(worker.id) is False  # already paused

    assert provider.resume(worker.id) is True
    assert provider.get(worker.id).status == "idle"
    assert provider.resume(worker.id) is False  # not paused

    assert provider.terminate(worker.id) is True
    assert provider.get(worker.id).status == "terminated"
    assert provider.terminate(worker.id) is False  # still in map, but idempotent no-op


@pytest.mark.unit
def test_simulation_provider_records_lifecycle_calls() -> None:
    provider = SimulationWorkerProvider()
    worker = provider.launch()
    provider.pause(worker.id)
    provider.resume(worker.id)
    assert provider.calls == [f"launch:{worker.id}", f"pause:{worker.id}", f"resume:{worker.id}"]


@pytest.mark.unit
def test_build_worker_provider_factory() -> None:
    assert isinstance(build_worker_provider("simulation"), SimulationWorkerProvider)
    with pytest.raises(NotImplementedError):
        build_worker_provider("runpod").launch()
    with pytest.raises(NotImplementedError):
        build_worker_provider("vast").pause("x")
    with pytest.raises(ValueError):
        build_worker_provider("nonsense")


# =============================================================================
# Fleet manager reconciliation
# =============================================================================


@pytest.mark.unit
async def test_fleet_manager_reconcile_scales_up_and_executes() -> None:
    provider = SimulationWorkerProvider()
    provider.launch()  # one idle worker already warm

    async def reader() -> int:
        return 5

    manager = FleetManager(
        provider=provider,
        config=_cfg(),
        queue_reader=reader,
        now_fn=lambda: NOW,
    )
    plan = await manager.reconcile()
    assert isinstance(plan, ScalePlan)
    assert plan.launch_count == 4
    assert len(provider.list_workers()) == 5
    assert manager.last_plan is plan


@pytest.mark.unit
async def test_fleet_manager_reconcile_pauses_idle_workers_via_provider() -> None:
    provider = SimulationWorkerProvider()
    w1 = provider.launch()
    w1.idle_since = NOW - timedelta(minutes=45)
    w2 = provider.launch()
    w2.idle_since = NOW - timedelta(minutes=45)

    async def reader() -> int:
        return 0

    manager = FleetManager(
        provider=provider,
        config=_cfg(warm_min=1, idle_timeout_min=10),
        queue_reader=reader,
        now_fn=lambda: NOW,
    )
    plan = await manager.reconcile()
    # warm floor 1 → pause exactly one long-idle worker
    assert len(plan.pause) == 1
    paused = [w for w in provider.list_workers() if w.status == "paused"]
    assert len(paused) == 1
    assert paused[0].id == plan.pause[0]


@pytest.mark.unit
async def test_fleet_manager_reconcile_resumes_paused_then_launches() -> None:
    provider = SimulationWorkerProvider()
    paused = provider.launch()
    provider.pause(paused.id)

    async def reader() -> int:
        return 3

    manager = FleetManager(provider=provider, config=_cfg(), queue_reader=reader, now_fn=lambda: NOW)
    plan = await manager.reconcile()
    assert plan.resume == [paused.id]
    assert plan.launch_count == 2
    assert [w.status for w in provider.list_workers()].count("idle") == 3


@pytest.mark.unit
async def test_fleet_manager_requires_queue_reader() -> None:
    manager = FleetManager(provider=SimulationWorkerProvider(), config=_cfg())
    with pytest.raises(ValueError, match="queue_reader"):
        await manager.reconcile()


@pytest.mark.unit
def test_fleet_manager_snapshot_shape() -> None:
    provider = SimulationWorkerProvider()
    provider.launch()
    manager = FleetManager(provider=provider, config=_cfg(), queue_reader=lambda: 0)
    snap = manager.snapshot()
    assert snap["provider"] == "simulation"
    assert snap["config"]["max_workers"] == 8
    assert len(snap["workers"]) == 1


# =============================================================================
# Queue depth reader (jobs table)
# =============================================================================


class _FakeResult:
    def __init__(self, value: int) -> None:
        self._value = value

    def scalar_one(self) -> int:
        return self._value


class _FakeSession:
    """Minimal AsyncSession stand-in capturing the executed statement."""

    def __init__(self, count: int) -> None:
        self.count = count
        self.statements: list = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _FakeResult(self.count)


@pytest.mark.unit
async def test_count_queued_jobs_queries_jobs_table_for_queued() -> None:
    session = _FakeSession(7)
    assert await count_queued_jobs(session) == 7
    assert len(session.statements) == 1
    compiled = str(session.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "jobs" in compiled
    assert "queued" in compiled


@pytest.mark.unit
async def test_make_queue_reader_binds_session() -> None:
    session = _FakeSession(3)
    reader = make_queue_reader(session)
    assert await reader() == 3
