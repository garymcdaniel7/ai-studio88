"""Unit coverage for the AIOS fleet update coordinator (staged rollout)."""

from __future__ import annotations

import pytest

from backend.aios.failure_learning import FailureReason, Recommendation, Severity
from backend.aios.rollout import (
    RolloutCoordinator,
    RolloutPhase,
    RolloutPlan,
    RolloutStep,
    SimulationRolloutProvider,
    build_rollout_provider,
    config_change_from_recommendation,
    staged_rollout,
)


def _rec(
    model: str = "WAN2.2",
    reason: FailureReason = FailureReason.OOM,
    count: int = 5,
    severity: Severity = Severity.HIGH,
) -> Recommendation:
    return Recommendation(
        affected_model=model,
        reason=reason,
        count=count,
        severity=severity,
        suggested_action=f"{model} OOM: lower max resolution",
    )


def _worker(worker_id: str, model: str | None = None) -> dict:
    labels = {}
    if model:
        labels["model"] = model
    return {"id": worker_id, "labels": labels}


# =============================================================================
# Config change derivation
# =============================================================================


@pytest.mark.unit
@pytest.mark.parametrize(
    ("reason", "expected_key"),
    [
        (FailureReason.OOM, "max_resolution"),
        (FailureReason.TIMEOUT, "timeout_ms"),
        (FailureReason.MODEL_ERROR, "model_config"),
        (FailureReason.PROMPT_REJECTED, "prompt_policy"),
        (FailureReason.QUEUE_STALE, "worker_count"),
        (FailureReason.UNKNOWN, "note"),
    ],
)
def test_config_change_from_reason(reason: FailureReason, expected_key: str) -> None:
    change = config_change_from_recommendation(_rec(reason=reason))
    assert expected_key in change


@pytest.mark.unit
def test_oom_config_change_caps_resolution() -> None:
    change = config_change_from_recommendation(_rec(reason=FailureReason.OOM))
    assert change["max_resolution"] == "1MP"
    assert change["max_seconds"] == 5


# =============================================================================
# Staged plan structure
# =============================================================================


@pytest.mark.unit
def test_staged_rollout_selects_matching_workers() -> None:
    workers = [
        _worker("w1", model="WAN2.2"),
        _worker("w2", model="WAN2.2"),
        _worker("w3", model="Klein"),
    ]
    plan = staged_rollout(_rec(model="WAN2.2"), workers)
    assert plan.target_model == "WAN2.2"
    assert plan.affected_workers == ["w1", "w2"]


@pytest.mark.unit
def test_staged_rollout_falls_back_to_all_workers_when_no_match() -> None:
    workers = [_worker("w1", model="Klein"), _worker("w2", model="Klein")]
    plan = staged_rollout(_rec(model="WAN2.2"), workers)
    assert set(plan.affected_workers) == {"w1", "w2"}


@pytest.mark.unit
def test_staged_rollout_orders_phases_canary_gradual_full() -> None:
    workers = [_worker(f"w{i}", model="WAN2.2") for i in range(1, 9)]
    plan = staged_rollout(_rec(), workers)
    assert plan.phases == [RolloutPhase.CANARY, RolloutPhase.GRADUAL, RolloutPhase.FULL]
    assert [s.phase for s in plan.steps] == [
        RolloutPhase.CANARY,
        RolloutPhase.GRADUAL,
        RolloutPhase.FULL,
    ]


@pytest.mark.unit
def test_canary_step_touches_one_worker_first() -> None:
    workers = [_worker(f"w{i}", model="WAN2.2") for i in range(1, 9)]
    plan = staged_rollout(_rec(), workers)
    canary = plan.steps[0]
    assert canary.phase is RolloutPhase.CANARY
    assert canary.index == 1
    assert len(canary.workers) == 1


@pytest.mark.unit
def test_single_worker_plan_has_canary_only() -> None:
    plan = staged_rollout(_rec(), [_worker("w1", model="WAN2.2")])
    assert plan.phases == [RolloutPhase.CANARY]
    assert len(plan.steps) == 1
    assert plan.phase_counts[RolloutPhase.CANARY] == 1


@pytest.mark.unit
def test_phase_counts_and_workers_in_phase() -> None:
    workers = [_worker(f"w{i}", model="WAN2.2") for i in range(1, 7)]  # 6 workers
    plan = staged_rollout(_rec(), workers)
    # canary=1, gradual=3 (half of 6), full=6
    assert plan.phase_counts[RolloutPhase.CANARY] == 1
    assert plan.phase_counts[RolloutPhase.GRADUAL] == 1
    assert plan.phase_counts[RolloutPhase.FULL] == 1
    assert len(plan.workers_in_phase(RolloutPhase.CANARY)) == 1
    assert len(plan.workers_in_phase(RolloutPhase.GRADUAL)) == 3
    assert len(plan.workers_in_phase(RolloutPhase.FULL)) == 6


@pytest.mark.unit
def test_staged_rollout_requires_positive_canary_size() -> None:
    with pytest.raises(ValueError):
        staged_rollout(_rec(), [_worker("w1")], canary_size=0)


@pytest.mark.unit
def test_all_steps_share_target_and_config_change() -> None:
    workers = [_worker(f"w{i}", model="WAN2.2") for i in range(1, 6)]
    plan = staged_rollout(_rec(), workers)
    for step in plan.steps:
        assert step.target_model == "WAN2.2"
        assert step.config_change == plan.config_change
        assert isinstance(step, RolloutStep)


# =============================================================================
# Coordinator + simulation provider
# =============================================================================


@pytest.mark.unit
def test_rollout_coordinator_plan_returns_staged_plan() -> None:
    coordinator = RolloutCoordinator()
    plan = coordinator.plan(_rec(), [_worker(f"w{i}", model="WAN2.2") for i in range(1, 5)])
    assert isinstance(plan, RolloutPlan)
    assert len(plan.steps) >= 2


@pytest.mark.unit
def test_dry_run_does_not_apply_steps() -> None:
    coordinator = RolloutCoordinator()
    plan = coordinator.plan(_rec(), [_worker("w1", model="WAN2.2")])
    result = coordinator.execute(plan, dry_run=True)
    assert result["dry_run"] is True
    assert result["applied"] is False
    assert result["applied_step_indexes"] == []
    assert coordinator.provider.applied == []


@pytest.mark.unit
def test_execute_applies_all_steps_through_provider() -> None:
    provider = SimulationRolloutProvider()
    coordinator = RolloutCoordinator(provider=provider)
    plan = coordinator.plan(_rec(), [_worker(f"w{i}", model="WAN2.2") for i in range(1, 5)])
    result = coordinator.execute(plan)
    assert result["applied"] is True
    assert result["provider"] == "simulation"
    assert len(provider.applied) == len(plan.steps)
    assert [s.index for s in provider.applied] == [s.index for s in plan.steps]


@pytest.mark.unit
def test_simulation_provider_apply_plan_applies_in_order() -> None:
    provider = SimulationRolloutProvider()
    plan = staged_rollout(_rec(), [_worker(f"w{i}", model="WAN2.2") for i in range(1, 6)])
    provider.apply_plan(plan)
    assert [s.phase for s in provider.applied] == [
        RolloutPhase.CANARY,
        RolloutPhase.GRADUAL,
        RolloutPhase.FULL,
    ]


@pytest.mark.unit
def test_build_rollout_provider_unknown_name() -> None:
    with pytest.raises(ValueError):
        build_rollout_provider("nope")


@pytest.mark.unit
def test_build_rollout_provider_default_is_simulation() -> None:
    provider = build_rollout_provider()
    assert isinstance(provider, SimulationRolloutProvider)
