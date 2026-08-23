"""Unit coverage for AIOS failure learning + enhancement recommendations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.aios.failure_learning import (
    DEFAULT_THRESHOLD,
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

NOW = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)


def _row(
    model: str,
    *,
    status: str = "failed",
    error_message: str | None = None,
    params: dict | None = None,
    created_at: datetime | None = NOW,
    duration_ms: int = 100,
) -> dict:
    return {
        "model": model,
        "status": status,
        "error_message": error_message,
        "params": params or {},
        "created_at": created_at,
        "duration_ms": duration_ms,
    }


# =============================================================================
# Failure classification
# =============================================================================


@pytest.mark.unit
@pytest.mark.parametrize(
    ("error", "params", "expected"),
    [
        ("CUDA error: out of memory", {}, FailureReason.OOM),
        ("Request timed out after 300s", {}, FailureReason.TIMEOUT),
        ("Model WAN2.2 not found", {}, FailureReason.MODEL_ERROR),
        ("Inference error from provider", {}, FailureReason.MODEL_ERROR),
        ("Generation failed: 500", {}, FailureReason.MODEL_ERROR),
        ("Prompt rejected by moderation policy", {}, FailureReason.PROMPT_REJECTED),
        ("Queue stale, no worker available", {}, FailureReason.QUEUE_STALE),
        ("Job expired waiting in queue", {}, FailureReason.QUEUE_STALE),
        ("some cryptic provider hiccup", {}, FailureReason.UNKNOWN),
        ("", {"error_message": "CUDA out of memory at 1.5MP"}, FailureReason.OOM),
        ("", {"error": "timed out"}, FailureReason.TIMEOUT),
    ],
)
def test_classify_failure(error: str, params: dict, expected: FailureReason) -> None:
    assert classify_failure(_row("WAN2.2", error_message=error, params=params)) is expected


@pytest.mark.unit
def test_classify_prefers_specific_reason_over_model_error() -> None:
    # "OOM" outranks the generic model_error bucket even in a verbose error.
    assert (
        classify_failure(_row("Klein", error_message="Inference failed: CUDA OOM"))
        is FailureReason.OOM
    )


@pytest.mark.unit
def test_failed_generation_reason_property() -> None:
    gen = FailedGeneration(model="Klein", error_message="out of memory")
    assert gen.reason is FailureReason.OOM


@pytest.mark.unit
def test_failed_generation_from_dict_row() -> None:
    row = _row("WAN2.2", params={"clip_duration_seconds": 10, "error": "oom"})
    gen = failed_generation_from_row(row)
    assert gen.model == "WAN2.2"
    assert gen.params["clip_duration_seconds"] == 10
    assert gen.error_message is None


# =============================================================================
# Aggregation
# =============================================================================


@pytest.mark.unit
def test_aggregate_failures_groups_by_model_and_reason() -> None:
    rows = [
        _row("WAN2.2", error_message="out of memory"),
        _row("WAN2.2", error_message="out of memory"),
        _row("WAN2.2", error_message="timed out"),
        _row("Klein", error_message="out of memory"),
    ]
    aggs = aggregate_failures(rows)
    by_key = {(a.model, a.reason): a for a in aggs}
    assert by_key[("WAN2.2", FailureReason.OOM)].count == 2
    assert by_key[("WAN2.2", FailureReason.TIMEOUT)].count == 1
    assert by_key[("Klein", FailureReason.OOM)].count == 1


@pytest.mark.unit
def test_aggregate_sorts_by_count_desc() -> None:
    rows = [
        _row("A", error_message="timed out"),
        _row("B", error_message="out of memory"),
        _row("B", error_message="out of memory"),
        _row("B", error_message="out of memory"),
    ]
    aggs = aggregate_failures(rows)
    assert [a.count for a in aggs] == [3, 1]


@pytest.mark.unit
def test_aggregate_respects_window() -> None:
    old = NOW - timedelta(days=10)
    rows = [
        _row("WAN2.2", error_message="oom", created_at=NOW),
        _row("WAN2.2", error_message="oom", created_at=old),
    ]
    aggs = aggregate_failures(rows, window=timedelta(days=1), now=NOW)
    assert len(aggs) == 1
    assert aggs[0].count == 1


@pytest.mark.unit
def test_aggregate_no_window_includes_old_failures() -> None:
    old = NOW - timedelta(days=30)
    aggs = aggregate_failures([_row("Klein", error_message="oom", created_at=old)], now=NOW)
    assert aggs[0].count == 1


@pytest.mark.unit
def test_aggregate_keeps_sample_params_of_most_recent_failure() -> None:
    rows = [
        _row("WAN2.2", error_message="oom", params={"clip_duration_seconds": 5}),
        _row("WAN2.2", error_message="oom", params={"clip_duration_seconds": 10}),
    ]
    aggs = aggregate_failures(rows)
    assert aggs[0].sample_params["clip_duration_seconds"] == 10


# =============================================================================
# Recommendation generation + thresholds
# =============================================================================


def _agg(model: str, reason: FailureReason, count: int, params: dict | None = None) -> FailureAggregate:
    return FailureAggregate(
        model=model, reason=reason, count=count, sample_params=params or {}
    )


@pytest.mark.unit
def test_generate_respects_threshold() -> None:
    aggs = [_agg("WAN2.2", FailureReason.OOM, 2), _agg("Klein", FailureReason.TIMEOUT, 3)]
    recs = generate_recommendations(aggs, threshold=3)
    assert len(recs) == 1
    assert recs[0].affected_model == "Klein"


@pytest.mark.unit
def test_default_threshold_is_three() -> None:
    assert DEFAULT_THRESHOLD == 3
    aggs = [_agg("WAN2.2", FailureReason.OOM, 3)]
    assert len(generate_recommendations(aggs)) == 1


@pytest.mark.unit
def test_generate_requires_positive_threshold() -> None:
    with pytest.raises(ValueError):
        generate_recommendations([], threshold=0)


@pytest.mark.unit
def test_recommendation_carries_severity_action_model() -> None:
    recs = generate_recommendations([_agg("WAN2.2", FailureReason.OOM, 12)])
    rec = recs[0]
    assert isinstance(rec, Recommendation)
    assert rec.affected_model == "WAN2.2"
    assert rec.reason is FailureReason.OOM
    assert rec.count == 12
    assert rec.severity is Severity.CRITICAL  # high baseline + >=10 escalation
    assert "12x" in rec.suggested_action


@pytest.mark.unit
def test_recommendation_for_oom_on_short_clips() -> None:
    agg = _agg("WAN2.2", FailureReason.OOM, 12, params={"clip_duration_seconds": 10})
    rec = generate_recommendations([agg])[0]
    assert "10s clips" in rec.suggested_action
    assert "5s clips" in rec.suggested_action


@pytest.mark.unit
def test_recommendation_for_oom_at_resolution() -> None:
    agg = _agg("Klein", FailureReason.OOM, 4, params={"max_resolution": "1.5MP"})
    rec = generate_recommendations([agg])[0]
    assert "1.5MP" in rec.suggested_action
    assert "cap at 1MP" in rec.suggested_action


@pytest.mark.unit
def test_recommendation_for_queue_stale() -> None:
    agg = _agg("WAN2.2", FailureReason.QUEUE_STALE, 5)
    rec = generate_recommendations([agg])[0]
    assert "raise worker count" in rec.suggested_action


# =============================================================================
# Severity ranking
# =============================================================================


@pytest.mark.unit
def test_severity_escalates_with_count() -> None:
    low = generate_recommendations([_agg("A", FailureReason.OOM, 3)])[0]
    high = generate_recommendations([_agg("A", FailureReason.OOM, 12)])[0]
    assert low.severity is Severity.HIGH
    assert high.severity is Severity.CRITICAL


@pytest.mark.unit
def test_recommendations_sorted_by_severity_then_count() -> None:
    aggs = [
        _agg("low", FailureReason.PROMPT_REJECTED, 3),  # low
        _agg("crit", FailureReason.OOM, 12),  # critical
        _agg("high", FailureReason.OOM, 3),  # high
        _agg("med", FailureReason.TIMEOUT, 3),  # medium
    ]
    recs = generate_recommendations(aggs)
    assert [r.affected_model for r in recs] == ["crit", "high", "med", "low"]
    assert recs[0].severity is Severity.CRITICAL
    assert recs[-1].severity is Severity.LOW


@pytest.mark.unit
def test_oom_ranks_above_prompt_rejected_at_same_count() -> None:
    aggs = [
        _agg("Klein", FailureReason.PROMPT_REJECTED, 5),
        _agg("WAN2.2", FailureReason.OOM, 5),
    ]
    recs = generate_recommendations(aggs)
    assert recs[0].affected_model == "WAN2.2"


# =============================================================================
# DB-backed facade (fake client)
# =============================================================================


class _FakeClient:
    """Minimal Supabase-like client returning canned failed rows."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.calls: list[dict] = []

    def table(self, name: str):
        self.calls.append({"table": name})
        return _Query(self._rows, name)


class _Query:
    def __init__(self, rows: list[dict], name: str) -> None:
        self._rows = rows
        self._name = name
        self._filters: list[str] = []

    def select(self, _cols: str):
        return self

    def eq(self, key: str, value: str):
        if key == "status":
            self._rows = [r for r in self._rows if r.get("status") == value]
        elif key == "org_id":
            self._rows = [r for r in self._rows if r.get("org_id") == value]
        return self

    def execute(self):
        return _Result(self._rows)


class _Result:
    def __init__(self, rows: list[dict]) -> None:
        self.data = rows


@pytest.mark.unit
def test_failure_learning_analyze_queries_failed_and_emits() -> None:
    rows = [
        _row("WAN2.2", error_message="out of memory", params={"clip_duration_seconds": 10}),
        _row("WAN2.2", error_message="out of memory", params={"clip_duration_seconds": 10}),
        _row("WAN2.2", error_message="out of memory", params={"clip_duration_seconds": 10}),
        _row("Klein", error_message="timed out"),  # below threshold
        _row("WAN2.2", status="completed", error_message="out of memory"),  # filtered out
    ]
    client = _FakeClient(rows)
    learning = FailureLearning(db_client=client, threshold=3)
    recs = learning.analyze()

    assert client.calls[0]["table"] == "generation_events"
    assert len(recs) == 1
    assert recs[0].affected_model == "WAN2.2"
    assert recs[0].count == 3
    assert "10s clips" in recs[0].suggested_action


@pytest.mark.unit
def test_failure_learning_analyze_org_scoping() -> None:
    client = _FakeClient([_row("Klein", error_message="oom")])
    learning = FailureLearning(db_client=client)
    learning.analyze(org_id="org-123")
    assert any(call["table"] == "generation_events" for call in client.calls)
