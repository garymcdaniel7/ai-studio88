"""Worker dispatch cost-gate coverage for Phase 2 Task 15.3."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from backend import cost_ledger
from backend.handlers.base import BaseHandler
from backend.worker import Worker

ORG_A = "12345678-1234-5678-1234-567812345678"
ORG_B = "87654321-4321-8765-4321-876543218765"


class RecordingHandler(BaseHandler):
    """Provider double that records execution after the real worker gate."""

    events: list[str] = []
    result: dict[str, Any] = {"actual_cost_usd": 0.007}
    error: BaseException | None = None

    @property
    def name(self) -> str:
        """Return the provider-backed handler name."""
        return "image_generation"

    def execute(self, job: dict, report_progress: Callable[[int], None]) -> dict:
        """Record provider execution and return or raise the scripted result."""
        del job, report_progress
        self.events.append("provider")
        if self.error is not None:
            raise self.error
        return dict(self.result)


@pytest.fixture(autouse=True)
def reset_cost_state() -> None:
    """Keep the in-memory ledger and handler script isolated per test."""
    cost_ledger._reset_store()
    RecordingHandler.events.clear()
    RecordingHandler.result = {"actual_cost_usd": 0.007}
    RecordingHandler.error = None
    yield
    cost_ledger._reset_store()


def _job(org_id: str, job_id: str = "job-15-3") -> dict[str, Any]:
    """Build a persisted worker job with a positive provider estimate."""
    return {
        "id": job_id,
        "org_id": org_id,
        "type": "image_generation",
        "input": {"prompt": "a portrait", "estimated_cost_usd": 0.01},
    }


def test_real_worker_boundary_reserves_before_provider_execution() -> None:
    """The polling worker reserves tenant+job budget before handler execution."""
    import backend.worker as worker_module

    real_reserve = cost_ledger.reserve_cost
    reservation_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def record_reservation(*args: Any, **kwargs: Any) -> Any:
        RecordingHandler.events.append("reserve")
        reservation_calls.append((args, kwargs))
        return real_reserve(*args, **kwargs)

    worker = Worker(org_id=ORG_A)
    with (
        patch.dict(worker_module.JOB_HANDLERS, {"image_generation": RecordingHandler}),
        patch.object(worker_module.cost_ledger, "reserve_cost", side_effect=record_reservation),
        patch.object(worker_module, "complete_job"),
    ):
        worker._process_job(_job(ORG_A))

    assert RecordingHandler.events == ["reserve", "provider"]
    assert reservation_calls == [
        (
            (ORG_A, 0.01),
            {
                "operation": "worker:image_generation",
                "job_id": "job-15-3",
                "provider": "image_generation",
            },
        )
    ]
    summary = cost_ledger.get_spend_summary(ORG_A)
    assert summary["active_reservations_usd"] == 0.0
    assert summary["daily_spend_usd"] == 0.007


def test_cost_rejection_prevents_provider_execution() -> None:
    """A hard-limit rejection fails the job before the provider is called."""
    import backend.worker as worker_module

    cost_ledger.set_workspace_limits(
        ORG_A,
        cost_ledger.BudgetLimits(daily_hard_usd=0.001, daily_soft_usd=0.001),
    )
    worker = Worker(org_id=ORG_A)
    with (
        patch.dict(worker_module.JOB_HANDLERS, {"image_generation": RecordingHandler}),
        patch.object(worker_module, "fail_job") as fail_job,
    ):
        worker._process_job(_job(ORG_A, "rejected-job"))

    assert RecordingHandler.events == []
    fail_job.assert_called_once()
    assert cost_ledger.get_spend_summary(ORG_A)["active_reservations_usd"] == 0.0


def test_success_finalizes_with_actual_cost() -> None:
    """Successful provider execution finalizes the reservation with actual spend."""
    import backend.worker as worker_module

    worker = Worker(org_id=ORG_A)
    with (
        patch.dict(worker_module.JOB_HANDLERS, {"image_generation": RecordingHandler}),
        patch.object(worker_module, "complete_job") as complete_job,
    ):
        worker._process_job(_job(ORG_A, "success-job"))

    complete_job.assert_called_once()
    summary = cost_ledger.get_spend_summary(ORG_A)
    assert summary["daily_spend_usd"] == 0.007
    assert summary["active_reservations_usd"] == 0.0


def test_provider_failure_releases_reservation_in_finally() -> None:
    """Provider failure releases the active hold and records no spend."""
    import backend.worker as worker_module

    RecordingHandler.error = RuntimeError("provider unavailable")
    worker = Worker(org_id=ORG_A)
    with (
        patch.dict(worker_module.JOB_HANDLERS, {"image_generation": RecordingHandler}),
        patch.object(worker_module, "fail_job") as fail_job,
    ):
        worker._process_job(_job(ORG_A, "failed-job"))

    fail_job.assert_called_once()
    summary = cost_ledger.get_spend_summary(ORG_A)
    assert summary["active_reservations_usd"] == 0.0
    assert summary["daily_spend_usd"] == 0.0


def test_cost_gate_isolated_between_org_a_and_org_b() -> None:
    """A's rejected budget cannot block or spend B's tenant-scoped budget."""
    import backend.worker as worker_module

    cost_ledger.set_workspace_limits(
        ORG_A,
        cost_ledger.BudgetLimits(daily_hard_usd=0.001, daily_soft_usd=0.001),
    )
    cost_ledger.set_workspace_limits(
        ORG_B,
        cost_ledger.BudgetLimits(daily_hard_usd=1.0, daily_soft_usd=0.8),
    )
    worker_a = Worker(org_id=ORG_A)
    worker_b = Worker(org_id=ORG_B)
    with patch.dict(worker_module.JOB_HANDLERS, {"image_generation": RecordingHandler}):
        with patch.object(worker_module, "fail_job"):
            worker_a._process_job(_job(ORG_A, "org-a-job"))
        with patch.object(worker_module, "complete_job"):
            worker_b._process_job(_job(ORG_B, "org-b-job"))

    assert RecordingHandler.events == ["provider"]
    assert cost_ledger.get_spend_summary(ORG_A)["daily_spend_usd"] == 0.0
    assert cost_ledger.get_spend_summary(ORG_B)["daily_spend_usd"] == 0.007
    assert cost_ledger.get_spend_summary(ORG_B)["active_reservations_usd"] == 0.0
