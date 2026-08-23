"""AIOS Fleet Update Coordinator — staged rollout of approved recommendations.

Given approved enhancement recommendations (from
:mod:`backend.aios.failure_learning`), produce a staged rollout plan:
the target model / config change, the affected workers, and the rollout
steps grouped into canary → gradual → full phases.

No provider API calls are made here. Provider interaction sits behind a
pluggable :class:`RolloutProvider` interface; the default adapter is an
in-memory :class:`SimulationRolloutProvider` that records every applied
step so callers (and tests) can observe exactly what would be executed
against a real fleet provider once one is wired in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# =============================================================================
# Rollout phases
# =============================================================================


class RolloutPhase(StrEnum):
    """Progressive rollout phase — each phase reaches more workers."""

    CANARY = "canary"
    GRADUAL = "gradual"
    FULL = "full"


_PHASE_ORDER = {
    RolloutPhase.CANARY: 0,
    RolloutPhase.GRADUAL: 1,
    RolloutPhase.FULL: 2,
}


# =============================================================================
# Rollout plan
# =============================================================================


@dataclass(frozen=True)
class RolloutStep:
    """One applied step of a staged rollout.

    Attributes:
        phase: Which stage this step belongs to.
        index: Ordering within the plan (1-based, phase-ordered).
        action: The operation to run (e.g. ``apply_config``).
        target_model: Model the step modifies.
        config_change: Structured config change being applied.
        workers: Worker ids the step affects (subset of the fleet).
    """

    phase: RolloutPhase
    index: int
    action: str
    target_model: str
    config_change: dict[str, Any]
    workers: tuple[str, ...] = ()


@dataclass
class RolloutPlan:
    """A staged rollout plan for one approved recommendation.

    Attributes:
        target_model: Model the change applies to.
        config_change: Structured config change (from the suggestion).
        affected_workers: All worker ids in scope for the change.
        steps: Ordered rollout steps, phase-grouped (canary → gradual → full).
        source: The recommendation that drove the plan.
    """

    target_model: str
    config_change: dict[str, Any]
    affected_workers: list[str] = field(default_factory=list)
    steps: list[RolloutStep] = field(default_factory=list)
    source: Any = None

    @property
    def phases(self) -> list[RolloutPhase]:
        """Distinct phases present in the plan, in rollout order."""
        seen: list[RolloutPhase] = []
        for step in self.steps:
            if step.phase not in seen:
                seen.append(step.phase)
        seen.sort(key=lambda p: _PHASE_ORDER[p])
        return seen

    @property
    def phase_counts(self) -> dict[RolloutPhase, int]:
        """Number of steps per phase."""
        counts: dict[RolloutPhase, int] = {}
        for step in self.steps:
            counts[step.phase] = counts.get(step.phase, 0) + 1
        return counts

    def workers_in_phase(self, phase: RolloutPhase) -> list[str]:
        """Worker ids reached by a given phase (union of its steps)."""
        reached: list[str] = []
        for step in self.steps:
            if step.phase is phase:
                for worker_id in step.workers:
                    if worker_id not in reached:
                        reached.append(worker_id)
        return reached


# =============================================================================
# Config change derivation
# =============================================================================


def config_change_from_recommendation(recommendation: Any) -> dict[str, Any]:
    """Map a recommendation's reason to a structured config change.

    The mapping is deliberately coarse and keyword-driven: it converts a
    human suggestion into a machine-readable change that a future provider
    adapter would apply. No provider calls happen here.
    """
    reason = getattr(recommendation, "reason", None)
    reason = getattr(reason, "value", reason)
    if reason == "oom":
        return {"max_resolution": "1MP", "max_seconds": 5, "batch_size": 1}
    if reason == "timeout":
        return {"timeout_ms": "+30%", "retry": True}
    if reason == "model_error":
        return {"model_config": "validate", "provider": "recheck"}
    if reason == "prompt_rejected":
        return {"prompt_policy": "relaxed_safety"}
    if reason == "queue_stale":
        return {"worker_count": "+1"}
    return {"note": "investigate"}


def _worker_id(worker: Any) -> str:
    """Read a worker's id from an ORM row or a dict."""
    if isinstance(worker, dict):
        return str(worker.get("id"))
    return str(getattr(worker, "id"))


def _worker_labels(worker: Any) -> dict[str, str]:
    if isinstance(worker, dict):
        labels = worker.get("labels") or {}
        return labels if isinstance(labels, dict) else {}
    return dict(getattr(worker, "labels", {}) or {})


def _select_affected_workers(recommendation: Any, workers: "Sequence[Any]") -> list[str]:
    """Pick workers in scope for a change.

    A worker is in scope when one of its labels matches the affected model
    (e.g. ``model=WAN2.2`` / ``purpose=video``). If nothing matches, all
    workers are considered in scope (the change may be fleet-wide).
    """
    target = getattr(recommendation, "affected_model", "") or ""
    matched: list[str] = []
    for worker in workers:
        labels = _worker_labels(worker)
        if target and (
            labels.get("model") == target
            or labels.get("models") == target
            or target in labels.get("labels", "")
        ):
            matched.append(_worker_id(worker))
    if matched:
        return matched
    return [_worker_id(w) for w in workers]


# =============================================================================
# Staged planning
# =============================================================================


def staged_rollout(
    recommendation: Any,
    workers: "Sequence[Any]",
    *,
    canary_size: int = 1,
) -> RolloutPlan:
    """Build a staged canary → gradual → full rollout for a recommendation.

    Args:
        recommendation: Approved Recommendation (or duck-typed equivalent).
        workers: Current fleet workers to stage the change across.
        canary_size: Number of workers in the first (canary) phase.

    Returns:
        A RolloutPlan with phase-grouped steps; no provider calls are made.
    """
    if canary_size < 1:
        raise ValueError("canary_size must be >= 1")

    target = getattr(recommendation, "affected_model", "") or "unknown"
    change = config_change_from_recommendation(recommendation)
    affected = _select_affected_workers(recommendation, workers)
    steps: list[RolloutStep] = []

    # Phase 1 — canary: a single worker validates the change.
    canary = affected[:canary_size]
    steps.append(
        RolloutStep(
            phase=RolloutPhase.CANARY,
            index=len(steps) + 1,
            action="apply_config",
            target_model=target,
            config_change=change,
            workers=tuple(canary),
        )
    )

    # Phase 2 — gradual: roughly half the affected workers.
    gradual_size = max(canary_size, len(affected) // 2)
    gradual = affected[:gradual_size]
    if len(gradual) > len(canary):
        steps.append(
            RolloutStep(
                phase=RolloutPhase.GRADUAL,
                index=len(steps) + 1,
                action="apply_config",
                target_model=target,
                config_change=change,
                workers=tuple(gradual),
            )
        )

    # Phase 3 — full: every affected worker.
    if len(affected) > len(gradual):
        steps.append(
            RolloutStep(
                phase=RolloutPhase.FULL,
                index=len(steps) + 1,
                action="apply_config",
                target_model=target,
                config_change=change,
                workers=tuple(affected),
            )
        )

    return RolloutPlan(
        target_model=target,
        config_change=change,
        affected_workers=affected,
        steps=steps,
        source=recommendation,
    )


# =============================================================================
# Pluggable provider
# =============================================================================


class RolloutProvider(ABC):
    """Abstraction for applying rollout steps to a fleet.

    Concrete adapters implement :meth:`apply` against a real fleet provider.
    The default :class:`SimulationRolloutProvider` records steps in memory,
    so the coordinator is fully testable without network access.
    """

    name: str = "base"

    @abstractmethod
    def apply(self, step: RolloutStep) -> bool:
        """Apply a single rollout step. True if applied/changed."""

    def health(self) -> dict[str, Any]:
        """Provider health snapshot (no network I/O required)."""
        return {"provider": self.name, "status": "available"}


class SimulationRolloutProvider(RolloutProvider):
    """In-memory simulation adapter — records applied steps, no provider calls."""

    name = "simulation"

    def __init__(self) -> None:
        self.applied: list[RolloutStep] = []

    def apply(self, step: RolloutStep) -> bool:
        self.applied.append(step)
        return True

    def apply_plan(self, plan: RolloutPlan) -> RolloutPlan:
        """Apply every step of a plan in order and return the plan."""
        for step in plan.steps:
            self.apply(step)
        return plan


def build_rollout_provider(name: str = "simulation") -> RolloutProvider:
    """Factory for the rollout provider adapter (simulation today)."""
    providers: dict[str, type[RolloutProvider]] = {
        "simulation": SimulationRolloutProvider,
    }
    cls = providers.get(name)
    if cls is None:
        raise ValueError(f"Unknown rollout provider '{name}' — expected one of {sorted(providers)}")
    return cls()


# =============================================================================
# Coordinator facade
# =============================================================================


class RolloutCoordinator:
    """Coordinates a fleet update: plan a rollout, then optionally apply it.

    ``plan`` is always safe (no side effects). ``execute`` applies the
    plan through the configured provider unless ``dry_run=True``, in which
    case it only reports what would happen.

    Example:
        coordinator = RolloutCoordinator()
        plan = coordinator.plan(recommendation, fleet_workers)
        result = coordinator.execute(plan, dry_run=True)
    """

    def __init__(self, provider: RolloutProvider | None = None) -> None:
        self.provider = provider or SimulationRolloutProvider()

    def plan(self, recommendation: Any, workers: "Sequence[Any]") -> RolloutPlan:
        """Produce a staged rollout plan for an approved recommendation."""
        return staged_rollout(recommendation, workers)

    def execute(self, plan: RolloutPlan, *, dry_run: bool = False) -> dict[str, Any]:
        """Apply a plan through the provider (unless ``dry_run``).

        Returns:
            A summary dict describing the plan and whether it was applied.
        """
        applied = []
        if not dry_run:
            for step in plan.steps:
                if self.provider.apply(step):
                    applied.append(step.index)
        return {
            "plan": plan,
            "applied": not dry_run,
            "dry_run": dry_run,
            "applied_step_indexes": applied,
            "provider": self.provider.name,
        }
