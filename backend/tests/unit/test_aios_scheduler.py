"""Unit coverage for the AIOS priority scheduler (ordering + slot assignment)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.aios.fleet import PriorityTier, Worker
from backend.aios.scheduler import (
    Assignment,
    AssignmentPlan,
    PriorityScheduler,
    QueuedJob,
    assign_jobs,
    queued_job_from_job,
    sort_queued,
)

NOW = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)


def _job(
    job_id: str,
    enqueued_at: datetime,
    *,
    priority: int = 0,
    workload_class: str | None = None,
    job_type: str | None = None,
    tier: PriorityTier | None = None,
    provider: str | None = None,
) -> QueuedJob:
    return QueuedJob(
        job_id=job_id,
        enqueued_at=enqueued_at,
        priority=priority,
        workload_class=workload_class,
        job_type=job_type,
        tier=tier,
        provider=provider,
    )


def _worker(
    worker_id: str,
    *,
    provider: str = "runpod",
    status: str = "idle",
    current_job_id: str | None = None,
) -> Worker:
    return Worker(id=worker_id, provider=provider, status=status, current_job_id=current_job_id)


# =============================================================================
# Priority ordering
# =============================================================================


@pytest.mark.unit
def test_p0_before_p1_before_p2_regardless_of_enqueue_time() -> None:
    jobs = [
        _job("p2", NOW - timedelta(minutes=30), workload_class="batch"),
        _job("p0", NOW - timedelta(minutes=5), workload_class="image_generation"),
        _job("p1", NOW - timedelta(minutes=2), workload_class="video_generation"),
    ]
    ordered = sort_queued(jobs)
    assert [j.job_id for j in ordered] == ["p0", "p1", "p2"]


@pytest.mark.unit
def test_fifo_within_tier_by_enqueued_at() -> None:
    jobs = [
        _job("c", NOW - timedelta(minutes=1), workload_class="music"),
        _job("a", NOW - timedelta(minutes=10), workload_class="voice"),
        _job("b", NOW - timedelta(minutes=5), workload_class="image_generation"),
    ]
    ordered = sort_queued(jobs)
    assert [j.job_id for j in ordered] == ["a", "b", "c"]


@pytest.mark.unit
def test_higher_explicit_priority_wins_within_tier() -> None:
    jobs = [
        _job("low", NOW - timedelta(minutes=10), priority=1, workload_class="image_generation"),
        _job("high", NOW - timedelta(minutes=5), priority=9, workload_class="image_generation"),
    ]
    ordered = sort_queued(jobs)
    assert [j.job_id for j in ordered] == ["high", "low"]


@pytest.mark.unit
def test_explicit_tier_overrides_workload_derivation() -> None:
    job = _job("x", NOW, tier=PriorityTier.P0, workload_class="batch")
    assert job.effective_tier() is PriorityTier.P0
    assert sort_queued([job])[0].job_id == "x"


@pytest.mark.unit
def test_sort_does_not_mutate_input() -> None:
    jobs = [
        _job("p2", NOW, workload_class="batch"),
        _job("p0", NOW, workload_class="voice"),
    ]
    sort_queued(jobs)
    assert [j.job_id for j in jobs] == ["p2", "p0"]


@pytest.mark.unit
def test_queued_job_from_orm_row_dict() -> None:
    row = {
        "id": "abc-123",
        "created_at": NOW,
        "priority": 5,
        "workload_class": "video_generation",
        "job_type": "video_generation",
    }
    job = queued_job_from_job(row)
    assert job.job_id == "abc-123"
    assert job.priority == 5
    assert job.effective_tier() is PriorityTier.P1


# =============================================================================
# Assignment to worker slots
# =============================================================================


@pytest.mark.unit
def test_assigns_each_job_to_an_idle_slot_in_priority_order() -> None:
    jobs = [
        _job("p0", NOW, workload_class="image_generation"),
        _job("p1", NOW, workload_class="video_generation"),
        _job("p2", NOW, workload_class="batch"),
    ]
    workers = [_worker("w1"), _worker("w2"), _worker("w3")]
    plan = assign_jobs(jobs, workers)
    assert isinstance(plan, AssignmentPlan)
    assert plan.assigned_count == 3
    assert plan.unassigned == []
    # First assignment goes to the P0 job
    assert plan.assignments[0].job.job_id == "p0"
    assert {a.worker_id for a in plan.assignments} == {"w1", "w2", "w3"}
    assert all(isinstance(a, Assignment) for a in plan.assignments)


@pytest.mark.unit
def test_respects_per_worker_max_concurrent_one() -> None:
    jobs = [
        _job("j1", NOW, workload_class="voice"),
        _job("j2", NOW, workload_class="music"),
    ]
    workers = [
        _worker("busy", status="busy", current_job_id="other"),
        _worker("free"),
    ]
    plan = assign_jobs(jobs, workers)
    assert plan.assigned_count == 1
    assert plan.assignments[0].worker_id == "free"
    assert [j.job_id for j in plan.unassigned] == ["j2"]


@pytest.mark.unit
def test_respects_per_provider_caps() -> None:
    jobs = [
        _job("a", NOW, workload_class="image_generation"),
        _job("b", NOW, workload_class="voice"),
        _job("c", NOW, workload_class="music"),
    ]
    workers = [_worker("rp1", provider="runpod"), _worker("rp2", provider="runpod"), _worker("v1", provider="vast")]
    plan = assign_jobs(jobs, workers, provider_caps={"runpod": 2})
    assert plan.assigned_count == 3  # runpod takes 2, vast absorbs the third
    runpod_assignments = [a for a in plan.assignments if a.provider == "runpod"]
    vast_assignments = [a for a in plan.assignments if a.provider == "vast"]
    assert len(runpod_assignments) == 2
    assert len(vast_assignments) == 1


@pytest.mark.unit
def test_provider_affinity_restricts_worker_pool() -> None:
    jobs = [
        _job("video", NOW, provider="vast", workload_class="video_generation"),
        _job("image", NOW, provider="runpod", workload_class="image_generation"),
    ]
    workers = [_worker("rp1", provider="runpod"), _worker("v1", provider="vast")]
    plan = assign_jobs(jobs, workers)
    assert plan.assigned_count == 2
    video_assignment = next(a for a in plan.assignments if a.job.job_id == "video")
    assert video_assignment.worker_id == "v1"


@pytest.mark.unit
def test_cap_saturates_affinity_provider_and_job_stays_unassigned() -> None:
    jobs = [
        _job("v1", NOW, provider="vast", workload_class="video_generation"),
        _job("v2", NOW, provider="vast", workload_class="video_generation"),
    ]
    workers = [_worker("v1", provider="vast")]
    plan = assign_jobs(jobs, workers, provider_caps={"vast": 1})
    assert plan.assigned_count == 1
    assert [j.job_id for j in plan.unassigned] == ["v2"]


@pytest.mark.unit
def test_p0_wins_contended_slot_over_earlier_p1() -> None:
    jobs = [
        _job("p1-early", NOW - timedelta(minutes=30), workload_class="video_generation"),
        _job("p0-late", NOW - timedelta(minutes=1), workload_class="voice"),
    ]
    workers = [_worker("only-slot")]
    plan = assign_jobs(jobs, workers)
    assert plan.assigned_count == 1
    assert plan.assignments[0].job.job_id == "p0-late"
    assert [j.job_id for j in plan.unassigned] == ["p1-early"]


@pytest.mark.unit
def test_all_jobs_unassigned_when_no_capacity() -> None:
    jobs = [_job("a", NOW, workload_class="image_generation")]
    plan = assign_jobs(jobs, [])
    assert plan.assigned_count == 0
    assert plan.unassigned_count == 1
    assert plan.total == 1
    assert plan.unassigned == jobs


@pytest.mark.unit
def test_paused_and_terminated_workers_offer_no_slots() -> None:
    jobs = [_job("a", NOW, workload_class="image_generation")]
    workers = [
        _worker("paused", status="paused"),
        _worker("terminated", status="terminated"),
    ]
    plan = assign_jobs(jobs, workers)
    assert plan.assigned_count == 0
    assert plan.unassigned == jobs


# =============================================================================
# PriorityScheduler facade
# =============================================================================


@pytest.mark.unit
def test_priority_scheduler_facade_holds_provider_caps() -> None:
    jobs = [
        _job("a", NOW, workload_class="image_generation"),
        _job("b", NOW, workload_class="voice"),
        _job("c", NOW, workload_class="music"),
    ]
    workers = [_worker("rp1", provider="runpod"), _worker("v1", provider="vast")]
    scheduler = PriorityScheduler(provider_caps={"runpod": 1})
    plan = scheduler.schedule(jobs, workers)
    runpod_count = len([a for a in plan.assignments if a.provider == "runpod"])
    assert runpod_count == 1
    assert plan.assigned_count == 2
    assert [j.job_id for j in plan.unassigned] == ["c"]
