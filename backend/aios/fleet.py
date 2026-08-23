"""AIOS Fleet Provisioner — queue-driven GPU worker fleet management.

Responsibilities:
- Read queue depth from the ``jobs`` table (``status='queued'``).
- Classify queued work into priority tiers:

    P0 = image / voice / music  (shortest jobs first)
    P1 = video
    P2 = batch / assembly

- Compute the desired worker count from queue depth, bounded by a warm-pool
  minimum (``FLEET_WARM_MIN``) and a hard maximum (``FLEET_MAX_WORKERS``).
- Pause workers that sit idle past ``FLEET_IDLE_TIMEOUT_MIN`` (never below the
  warm floor), and resume paused workers before launching new ones.

Provider integration is behind a pluggable ``WorkerProvider`` interface with
RunPod / Vast stubs. No provider API calls are implemented here — the default
adapter is an in-memory simulation.

Environment:
    FLEET_MAX_WORKERS       hard cap on worker count (default: 8)
    FLEET_WARM_MIN          warm-pool floor (default: 1)
    FLEET_IDLE_TIMEOUT_MIN  idle minutes before pause (default: 10)
    FLEET_JOBS_PER_WORKER   queued jobs per worker for scaling (default: 1)
"""

from __future__ import annotations

import logging
import math
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)


# =============================================================================
# Priority Tiers
# =============================================================================


class PriorityTier(StrEnum):
    """Urgency tiers for queued work.

    P0 jobs (image / voice / music) are shortest-lived and must be serviced
    first; P1 is video generation; P2 is long-running batch / assembly work.
    """

    P0 = "p0"
    P1 = "p1"
    P2 = "p2"


TIER_RANK: dict[PriorityTier, int] = {
    PriorityTier.P0: 0,
    PriorityTier.P1: 1,
    PriorityTier.P2: 2,
}

# Substring tokens matched against workload_class / job_type.
_P0_TOKENS = frozenset({"image", "voice", "music", "audio"})
_P1_TOKENS = frozenset({"video"})
_P2_TOKENS = frozenset({"batch", "assembly", "training", "publish"})


def tier_for_workload(
    workload_class: str | None,
    job_type: str | None = None,
    *,
    default: PriorityTier = PriorityTier.P2,
) -> PriorityTier:
    """Map a job's workload class / type to a priority tier.

    Matching is case-insensitive substring matching over both fields so the
    repository's existing classes (``image_generation``, ``video_generation``,
    ``batch``, ``lora_training``, ``voice``, ...) classify without a lookup
    table. Unknown workloads default to P2.
    """
    haystack = " ".join(part for part in (workload_class, job_type) if part).lower()

    for token in _P0_TOKENS:
        if token in haystack:
            return PriorityTier.P0
    for token in _P1_TOKENS:
        if token in haystack:
            return PriorityTier.P1
    for token in _P2_TOKENS:
        if token in haystack:
            return PriorityTier.P2
    return default


# =============================================================================
# Worker state
# =============================================================================

#: Statuses that hold scheduling capacity.
_ACTIVE_STATUSES = frozenset({"idle", "busy"})
#: Statuses that still occupy fleet quota (everything except terminated).
_LIVE_STATUSES = frozenset({"provisioning", "idle", "busy", "paused"})


@dataclass
class Worker:
    """A single fleet worker (GPU instance) with one job slot.

    ``max_concurrent`` is per-worker concurrency (1 today — one job per
    worker — but kept as a field so co-located inference slots can be
    expressed later without an API change).
    """

    id: str
    provider: str = "simulation"
    status: str = "idle"  # provisioning | idle | busy | paused | terminated
    current_job_id: str | None = None
    idle_since: datetime | None = None
    max_concurrent: int = 1
    labels: dict[str, str] = field(default_factory=dict)


# =============================================================================
# Provider abstraction (pluggable — RunPod / Vast stubs, simulation adapter)
# =============================================================================


class WorkerProvider(ABC):
    """Provider abstraction for launching/pausing/resuming fleet workers.

    Concrete adapters (RunPod, Vast) implement these methods against their
    APIs. The default ``SimulationWorkerProvider`` tracks workers in memory so
    the fleet logic is fully testable without network access.
    """

    name: str = "base"

    @abstractmethod
    def launch(self, spec: dict[str, Any] | None = None) -> Worker:
        """Provision a new worker from a launch spec (GPU type, labels)."""

    @abstractmethod
    def pause(self, worker_id: str) -> bool:
        """Pause a worker (stop billing, keep the instance). True if changed."""

    @abstractmethod
    def resume(self, worker_id: str) -> bool:
        """Resume a paused worker. True if changed."""

    @abstractmethod
    def terminate(self, worker_id: str) -> bool:
        """Terminate a worker permanently. True if changed."""

    @abstractmethod
    def list_workers(self) -> list[Worker]:
        """Return the current fleet as seen by this provider."""

    def health(self) -> dict[str, Any]:
        """Provider health snapshot (no network I/O required)."""
        return {"provider": self.name, "status": "available"}


class SimulationWorkerProvider(WorkerProvider):
    """In-memory simulation adapter — no real provider API calls.

    Records every lifecycle call in ``calls`` so tests can assert what the
    fleet manager asked the provider to do.
    """

    name = "simulation"

    def __init__(self) -> None:
        self._workers: dict[str, Worker] = {}
        self.calls: list[str] = []

    def launch(self, spec: dict[str, Any] | None = None) -> Worker:
        worker = Worker(
            id=f"sim-{uuid.uuid4().hex[:8]}",
            provider=self.name,
            status="idle",
            idle_since=datetime.now(UTC),
            labels=dict(spec or {}),
        )
        self._workers[worker.id] = worker
        self.calls.append(f"launch:{worker.id}")
        return worker

    def pause(self, worker_id: str) -> bool:
        worker = self._workers.get(worker_id)
        if worker is None or worker.status == "paused":
            return False
        worker.status = "paused"
        self.calls.append(f"pause:{worker_id}")
        return True

    def resume(self, worker_id: str) -> bool:
        worker = self._workers.get(worker_id)
        if worker is None or worker.status != "paused":
            return False
        worker.status = "idle"
        worker.idle_since = datetime.now(UTC)
        self.calls.append(f"resume:{worker_id}")
        return True

    def terminate(self, worker_id: str) -> bool:
        worker = self._workers.get(worker_id)
        if worker is None or worker.status == "terminated":
            return False
        worker.status = "terminated"
        self.calls.append(f"terminate:{worker_id}")
        return True

    def list_workers(self) -> list[Worker]:
        return list(self._workers.values())

    def get(self, worker_id: str) -> Worker | None:
        """Fetch one worker by id (test convenience)."""
        return self._workers.get(worker_id)

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "status": "available",
            "workers": len(self._workers),
        }


class RunPodWorkerProvider(WorkerProvider):
    """RunPod adapter stub — plug in the real API calls here.

    Deliberately raises ``NotImplementedError``: this module does not
    implement provider API calls. Swap the fleet manager's provider for this
    class once a concrete adapter exists.
    """

    name = "runpod"

    def launch(self, spec: dict[str, Any] | None = None) -> Worker:
        raise NotImplementedError("RunPod launch is not implemented — plug in the RunPod API.")

    def pause(self, worker_id: str) -> bool:
        raise NotImplementedError("RunPod pause is not implemented — plug in the RunPod API.")

    def resume(self, worker_id: str) -> bool:
        raise NotImplementedError("RunPod resume is not implemented — plug in the RunPod API.")

    def terminate(self, worker_id: str) -> bool:
        raise NotImplementedError("RunPod terminate is not implemented — plug in the RunPod API.")

    def list_workers(self) -> list[Worker]:
        raise NotImplementedError("RunPod list_workers is not implemented — plug in the RunPod API.")


class VastWorkerProvider(WorkerProvider):
    """Vast.ai adapter stub — plug in the real API calls here.

    Deliberately raises ``NotImplementedError``: this module does not
    implement provider API calls. Swap the fleet manager's provider for this
    class once a concrete adapter exists.
    """

    name = "vast"

    def launch(self, spec: dict[str, Any] | None = None) -> Worker:
        raise NotImplementedError("Vast launch is not implemented — plug in the Vast API.")

    def pause(self, worker_id: str) -> bool:
        raise NotImplementedError("Vast pause is not implemented — plug in the Vast API.")

    def resume(self, worker_id: str) -> bool:
        raise NotImplementedError("Vast resume is not implemented — plug in the Vast API.")

    def terminate(self, worker_id: str) -> bool:
        raise NotImplementedError("Vast terminate is not implemented — plug in the Vast API.")

    def list_workers(self) -> list[Worker]:
        raise NotImplementedError("Vast list_workers is not implemented — plug in the Vast API.")


def build_worker_provider(name: str = "simulation") -> WorkerProvider:
    """Factory for the fleet's provider adapter.

    Only the simulation adapter is fully wired today; RunPod / Vast raise
    ``NotImplementedError`` on use until concrete adapters land.
    """
    providers: dict[str, type[WorkerProvider]] = {
        "simulation": SimulationWorkerProvider,
        "runpod": RunPodWorkerProvider,
        "vast": VastWorkerProvider,
    }
    cls = providers.get(name)
    if cls is None:
        raise ValueError(f"Unknown worker provider '{name}' — expected one of {sorted(providers)}")
    return cls()


# =============================================================================
# Fleet configuration
# =============================================================================


@dataclass(frozen=True)
class FleetConfig:
    """Tunables for fleet sizing.

    Attributes:
        max_workers: Hard cap on simultaneous workers (FLEET_MAX_WORKERS).
        warm_min: Warm-pool floor — workers kept ready even with no queue.
        idle_timeout_min: Minutes a worker may sit idle before it is paused.
        jobs_per_worker: Queued jobs per worker used when scaling up.
    """

    max_workers: int = 8
    warm_min: int = 1
    idle_timeout_min: int = 10
    jobs_per_worker: int = 1

    def __post_init__(self) -> None:
        if self.max_workers < 1:
            raise ValueError("FLEET_MAX_WORKERS must be >= 1")
        if self.warm_min < 0:
            raise ValueError("FLEET_WARM_MIN must be >= 0")
        if self.warm_min > self.max_workers:
            raise ValueError("FLEET_WARM_MIN cannot exceed FLEET_MAX_WORKERS")
        if self.idle_timeout_min < 0:
            raise ValueError("FLEET_IDLE_TIMEOUT_MIN must be >= 0")
        if self.jobs_per_worker < 1:
            raise ValueError("FLEET_JOBS_PER_WORKER must be >= 1")


def fleet_config_from_env(environ: "Mapping[str, str] | None" = None) -> FleetConfig:
    """Build FleetConfig from environment variables with sane defaults."""
    env = os.environ if environ is None else environ

    def _int(name: str, default: int) -> int:
        try:
            return int(env.get(name, str(default)))
        except (TypeError, ValueError):
            logger.warning("Invalid integer for %s (%r) — using default %d", name, env.get(name), default)
            return default

    return FleetConfig(
        max_workers=_int("FLEET_MAX_WORKERS", 8),
        warm_min=_int("FLEET_WARM_MIN", 1),
        idle_timeout_min=_int("FLEET_IDLE_TIMEOUT_MIN", 10),
        jobs_per_worker=_int("FLEET_JOBS_PER_WORKER", 1),
    )


# =============================================================================
# Queue-depth worker scaling
# =============================================================================


def desired_worker_count(queue_depth: int, config: FleetConfig) -> int:
    """Compute the desired worker count for a given queue depth.

    Policy:
    - At least ``warm_min`` workers are kept ready at all times (warm pool).
    - Otherwise one worker per ``jobs_per_worker`` queued jobs, rounded up.
    - Never exceeds ``max_workers`` (hard cap).
    """
    if queue_depth <= 0:
        return config.warm_min
    needed = math.ceil(queue_depth / config.jobs_per_worker)
    return min(max(needed, config.warm_min), config.max_workers)


# =============================================================================
# Scale planning
# =============================================================================


@dataclass
class ScalePlan:
    """A reconciliation plan: what the fleet should do next.

    Attributes:
        queue_depth: Queued jobs observed during planning.
        desired_workers: Target worker count from ``desired_worker_count``.
        active_workers: Workers currently idle or busy.
        paused_workers: Workers currently paused.
        launch_count: New workers to launch (after resuming paused ones).
        resume: Worker ids to resume (paused → idle).
        pause: Worker ids to pause (long-idle → paused).
        reason: Human-readable summary of the decision.
    """

    queue_depth: int
    desired_workers: int
    active_workers: int
    paused_workers: int
    launch_count: int
    resume: list[str] = field(default_factory=list)
    pause: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def scale_up(self) -> bool:
        return self.launch_count > 0 or bool(self.resume)

    @property
    def scale_down(self) -> bool:
        return bool(self.pause)


def plan_scale(
    queue_depth: int,
    workers: list[Worker],
    config: FleetConfig,
    now: datetime | None = None,
) -> ScalePlan:
    """Turn a queue depth + fleet snapshot into concrete scaling actions.

    Ordering guarantees:
    - Scale up resumes paused workers before launching new ones (cheaper).
    - Scale down only pauses workers idle past ``idle_timeout_min`` and never
      below the desired floor (which itself respects the warm pool minimum).
    - Launches are capped by ``max_workers`` — never over-provision.
    """
    now = now or datetime.now(UTC)
    desired = desired_worker_count(queue_depth, config)
    active = [w for w in workers if w.status in _ACTIVE_STATUSES]
    paused = [w for w in workers if w.status == "paused"]
    live = [w for w in workers if w.status in _LIVE_STATUSES]

    resume_ids: list[str] = []
    pause_ids: list[str] = []
    launch_count = 0

    # ── Scale up: resume paused workers first, then launch new ones ────────
    deficit = desired - len(active)
    if deficit > 0:
        for worker in sorted(paused, key=lambda w: w.idle_since or now):
            if len(resume_ids) >= deficit:
                break
            resume_ids.append(worker.id)
        remaining = deficit - len(resume_ids)
        room = max(0, config.max_workers - len(live))
        launch_count = min(remaining, room)

    # ── Scale down: pause long-idle workers beyond the desired floor ────────
    excess = len(active) - desired
    if excess > 0:
        idle_workers = sorted(
            (w for w in active if w.status == "idle" and w.idle_since is not None),
            key=lambda w: w.idle_since or now,
        )
        for worker in idle_workers:
            if len(pause_ids) >= excess:
                break
            idle_minutes = (now - worker.idle_since).total_seconds() / 60.0
            if idle_minutes >= config.idle_timeout_min:
                pause_ids.append(worker.id)

    reason = _build_reason(queue_depth, desired, launch_count, resume_ids, pause_ids)
    return ScalePlan(
        queue_depth=queue_depth,
        desired_workers=desired,
        active_workers=len(active),
        paused_workers=len(paused),
        launch_count=launch_count,
        resume=resume_ids,
        pause=pause_ids,
        reason=reason,
    )


def _build_reason(
    queue_depth: int,
    desired: int,
    launch_count: int,
    resume: list[str],
    pause: list[str],
) -> str:
    parts: list[str] = [f"queue_depth={queue_depth} desired={desired}"]
    if launch_count:
        parts.append(f"launch {launch_count}")
    if resume:
        parts.append(f"resume {len(resume)}")
    if pause:
        parts.append(f"pause {len(pause)}")
    return ", ".join(parts) if parts else f"queue_depth={queue_depth} desired={desired}"


# =============================================================================
# Queue depth reader (jobs table)
# =============================================================================


async def count_queued_jobs(session: Any) -> int:
    """Count rows in ``jobs`` with ``status='queued'``.

    Imported lazily so this module stays importable without the ORM stack.
    """
    from sqlalchemy import func, select

    from app.models.job import Job

    stmt = select(func.count()).select_from(Job).where(Job.status == "queued")
    result = await session.execute(stmt)
    return int(result.scalar_one())


def make_queue_reader(session: Any) -> Callable[[], Any]:
    """Bind an async queue-depth reader to a SQLAlchemy async session.

    Returns an awaitable callable returning the queued job count, suitable
    for ``FleetManager(queue_reader=...)``.
    """

    async def reader() -> int:
        return await count_queued_jobs(session)

    return reader


# =============================================================================
# Fleet manager
# =============================================================================


class FleetManager:
    """Reconciles the fleet with queue demand.

    Each ``reconcile()`` reads queue depth (via ``queue_reader``), snapshots
    the fleet (via ``provider.list_workers()``), plans scaling actions, and
    executes them through the provider adapter.

    Example:
        manager = FleetManager(
            provider=build_worker_provider("simulation"),
            queue_reader=make_queue_reader(session),
        )
        plan = await manager.reconcile()
    """

    def __init__(
        self,
        provider: WorkerProvider | None = None,
        config: FleetConfig | None = None,
        queue_reader: Callable[[], Any] | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.provider = provider or SimulationWorkerProvider()
        self.config = config or fleet_config_from_env()
        self.queue_reader = queue_reader
        self.now_fn = now_fn
        self.last_plan: ScalePlan | None = None

    async def reconcile(self) -> ScalePlan:
        """Read queue depth, plan, and execute a full fleet reconciliation."""
        queue_depth = await self._read_queue_depth()
        workers = self.provider.list_workers()
        now = self.now_fn() if self.now_fn else None
        plan = plan_scale(queue_depth, workers, self.config, now=now)
        self._execute(plan)
        self.last_plan = plan
        return plan

    def snapshot(self) -> dict[str, Any]:
        """Current fleet + config snapshot for observability."""
        workers = self.provider.list_workers()
        return {
            "provider": self.provider.name,
            "config": {
                "max_workers": self.config.max_workers,
                "warm_min": self.config.warm_min,
                "idle_timeout_min": self.config.idle_timeout_min,
                "jobs_per_worker": self.config.jobs_per_worker,
            },
            "workers": [
                {
                    "id": w.id,
                    "provider": w.provider,
                    "status": w.status,
                    "current_job_id": w.current_job_id,
                }
                for w in workers
            ],
            "last_plan": self.last_plan,
        }

    # ── Internal ────────────────────────────────────────────────────────────

    async def _read_queue_depth(self) -> int:
        if self.queue_reader is None:
            raise ValueError(
                "FleetManager needs a queue_reader (e.g. make_queue_reader(session)) "
                "to read queue depth from the jobs table."
            )
        result = self.queue_reader()
        if hasattr(result, "__await__"):
            result = await result
        depth = int(result)
        if depth < 0:
            raise ValueError(f"Queue depth cannot be negative: {depth}")
        return depth

    def _execute(self, plan: ScalePlan) -> None:
        for worker_id in plan.resume:
            self.provider.resume(worker_id)
        for _ in range(plan.launch_count):
            self.provider.launch({"gpu": "RTX_3090", "purpose": "aios-fleet"})
        for worker_id in plan.pause:
            self.provider.pause(worker_id)
