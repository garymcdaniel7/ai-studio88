"""AIOS Priority Scheduler — order queued jobs and assign them to workers.

Ordering: queued jobs are sorted by ``(priority tier, priority int desc,
enqueued_at)`` — P0 before P1 before P2, higher explicit priority first
within a tier, and FIFO (oldest enqueued first) within that.

Assignment: jobs are placed onto worker slots respecting:
- per-worker ``max_concurrent`` (1 today — one job per worker), and
- per-provider caps (``provider_caps``), e.g. RunPod may only run 2 jobs.
- optional provider affinity (a job pinned to a provider only uses that
  provider's workers and is left unassigned when that provider is saturated).

This module is pure and synchronous — feed it rows from the ``jobs`` table
(``queued_job_from_job``) plus the fleet snapshot, and it returns a plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.aios.fleet import PriorityTier, TIER_RANK, Worker, tier_for_workload

#: Worker statuses that expose a schedulable slot.
_SLOT_STATUSES = frozenset({"idle", "active"})


# =============================================================================
# Queued job view
# =============================================================================


@dataclass(frozen=True)
class QueuedJob:
    """Scheduler's view of a queued job row.

    Attributes:
        job_id: Job id (UUID string).
        enqueued_at: When the job entered the queue (FIFO within a tier).
        priority: Explicit integer priority (higher wins within a tier).
        workload_class: Scheduling workload class (e.g. ``image_generation``).
        job_type: Job type (e.g. ``voice``).
        tier: Explicit tier override; otherwise derived from workload fields.
        provider: Optional provider affinity (only that provider's workers).
    """

    job_id: str
    enqueued_at: datetime
    priority: int = 0
    workload_class: str | None = None
    job_type: str | None = None
    tier: PriorityTier | None = None
    provider: str | None = None

    def effective_tier(self) -> PriorityTier:
        """Resolve the tier, honoring an explicit override first."""
        return self.tier or tier_for_workload(self.workload_class, self.job_type)


def _get(job: Any, key: str, default: Any = None) -> Any:
    """Read an attribute from an ORM row or a key from a dict."""
    if isinstance(job, dict):
        return job.get(key, default)
    return getattr(job, key, default)


def queued_job_from_job(job: Any) -> QueuedJob:
    """Build a QueuedJob view from a Job ORM row or a dict-like mapping.

    ``enqueued_at`` falls back to ``created_at`` (the jobs table's timestamp
    mixin) when the caller has no explicit enqueue timestamp.
    """
    enqueued = _get(job, "enqueued_at") or _get(job, "created_at")
    if enqueued is None:
        enqueued = datetime.now(UTC)
    priority = _get(job, "priority", 0)
    return QueuedJob(
        job_id=str(_get(job, "id")),
        enqueued_at=enqueued,
        priority=int(priority or 0),
        workload_class=_get(job, "workload_class"),
        job_type=_get(job, "job_type"),
        provider=_get(job, "provider"),
    )


def _order_key(job: QueuedJob) -> tuple[int, int, float]:
    return (TIER_RANK[job.effective_tier()], -job.priority, job.enqueued_at.timestamp())


def sort_queued(jobs: list[QueuedJob]) -> list[QueuedJob]:
    """Order queued jobs by (tier, priority desc, enqueued_at asc).

    P0 before P1 before P2; within a tier, higher explicit priority first,
    then oldest-first (FIFO). Returns a new list; input is not mutated.
    """
    return sorted(jobs, key=_order_key)


# =============================================================================
# Assignment
# =============================================================================


@dataclass(frozen=True)
class Assignment:
    """A job placed on a worker slot."""

    job: QueuedJob
    worker_id: str
    provider: str


@dataclass
class AssignmentPlan:
    """Result of assigning queued jobs to worker slots."""

    assignments: list[Assignment] = field(default_factory=list)
    unassigned: list[QueuedJob] = field(default_factory=list)

    @property
    def assigned_count(self) -> int:
        return len(self.assignments)

    @property
    def unassigned_count(self) -> int:
        return len(self.unassigned)

    @property
    def total(self) -> int:
        return self.assigned_count + self.unassigned_count


def _has_free_slot(worker: Worker) -> bool:
    return (
        worker.status in _SLOT_STATUSES
        and worker.current_job_id is None
        and worker.max_concurrent >= 1
    )


def assign_jobs(
    jobs: list[QueuedJob],
    workers: list[Worker],
    provider_caps: dict[str, int] | None = None,
) -> AssignmentPlan:
    """Assign sorted queued jobs to free worker slots.

    Args:
        jobs: Queued jobs (sorted internally by priority).
        workers: Fleet snapshot; only idle workers with a free slot are used.
        provider_caps: Max concurrent jobs per provider, e.g.
            ``{"runpod": 2, "vast": 4}``. Providers not listed are uncapped.

    Returns:
        AssignmentPlan with per-job assignments and any jobs that could not
        be placed (no compatible slot or provider cap reached).
    """
    ordered = sort_queued(jobs)
    caps = dict(provider_caps or {})
    used_by_provider: dict[str, int] = {}
    slots = [w for w in workers if _has_free_slot(w)]

    assignments: list[Assignment] = []
    unassigned: list[QueuedJob] = []

    for job in ordered:
        chosen = _pick_slot(job, slots, used_by_provider, caps)
        if chosen is None:
            unassigned.append(job)
            continue
        slots.remove(chosen)  # worker now holds a job — one slot per worker
        used_by_provider[chosen.provider] = used_by_provider.get(chosen.provider, 0) + 1
        assignments.append(Assignment(job=job, worker_id=chosen.id, provider=chosen.provider))

    return AssignmentPlan(assignments=assignments, unassigned=unassigned)


def _pick_slot(
    job: QueuedJob,
    slots: list[Worker],
    used_by_provider: dict[str, int],
    caps: dict[str, int],
) -> Worker | None:
    """Pick the first compatible, uncapped slot for a job (stable order)."""
    for worker in slots:
        if job.provider is not None and worker.provider != job.provider:
            continue
        cap = caps.get(worker.provider)
        if cap is not None and used_by_provider.get(worker.provider, 0) >= cap:
            continue
        return worker
    return None


# =============================================================================
# Scheduler facade
# =============================================================================


class PriorityScheduler:
    """Priority scheduler facade: sort queued jobs, assign to worker slots.

    Holds per-provider caps so callers don't re-pass them on every call.

    Example:
        scheduler = PriorityScheduler(provider_caps={"runpod": 2})
        plan = scheduler.schedule(jobs, fleet_workers)
    """

    def __init__(self, provider_caps: dict[str, int] | None = None) -> None:
        self.provider_caps = dict(provider_caps or {})

    def schedule(self, jobs: list[QueuedJob], workers: list[Worker]) -> AssignmentPlan:
        """Sort ``jobs`` and assign them to free slots in ``workers``."""
        return assign_jobs(jobs, workers, self.provider_caps)
