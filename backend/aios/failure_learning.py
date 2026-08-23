"""AIOS Failure Learning — classify failures and emit enhancement recommendations.

Reads failed generations from the ``generation_events`` table
(``status='failed'``), classifies each into a coarse failure *reason*
(``oom``, ``timeout``, ``model_error``, ``prompt_rejected``,
``queue_stale``, ``unknown``) from ``error_message`` / ``params``
heuristics, aggregates failure counts by ``(model, reason)``, and turns
aggregates that clear a threshold into structured ``Recommendation``
objects carrying a severity, a suggested action, and the affected model.

This module is pure and synchronous. The ``FailureLearning`` facade reads
rows through an injectable DB client; the classification, aggregation and
recommendation functions operate on plain ``FailedGeneration`` values so
they are fully testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

#: Default minimum number of failures (same model + reason) before a
#: recommendation is emitted.
DEFAULT_THRESHOLD = 3

#: Default lookback window for counting failures (None = no time filter).
DEFAULT_WINDOW: timedelta | None = None


# =============================================================================
# Failure reasons
# =============================================================================


class FailureReason(StrEnum):
    """Coarse classification of why a generation failed."""

    OOM = "oom"
    TIMEOUT = "timeout"
    MODEL_ERROR = "model_error"
    PROMPT_REJECTED = "prompt_rejected"
    QUEUE_STALE = "queue_stale"
    UNKNOWN = "unknown"


#: Ordered keyword groups used by :func:`classify_failure`. The first group
#: whose signal appears in the error text / params wins.
_OOM_TOKENS = (
    "out of memory",
    "cuda oom",
    "cuda error",
    "oom",
    "vram",
    "memory error",
    "not enough memory",
)
_TIMEOUT_TOKENS = (
    "timeout",
    "timed out",
    "deadline exceeded",
    "timedout",
    "request timeout",
)
_PROMPT_TOKENS = (
    "moderation",
    "content policy",
    "prompt rejected",
    "prompt not allowed",
    "safety",
    "blocked by policy",
    "rejected:",
    "policy violation",
)
_QUEUE_TOKENS = (
    "queue",
    "stale",
    "no worker",
    "worker not",
    "provisioning",
    "unassigned",
    "job expired",
)
_MODEL_TOKENS = (
    "model not found",
    "unknown model",
    "invalid model",
    "not found",
    "inference",
    "provider error",
    "upstream",
    " 500 ",
    "internal server error",
    "generation failed",
    "adapter error",
)


def _get(row: Any, key: str, default: Any = None) -> Any:
    """Read an attribute from an ORM row or a key from a dict."""
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _error_text(row: Any) -> str:
    """Collect an error description from ``error_message`` and ``params``."""
    parts: list[str] = []
    direct = _get(row, "error_message")
    if direct:
        parts.append(str(direct))
    params = _get(row, "params") or {}
    if isinstance(params, dict):
        for key in ("error_message", "error", "detail", "message", "status_detail"):
            value = params.get(key)
            if value:
                parts.append(str(value))
        reason = params.get("reason")
        if isinstance(reason, str):
            parts.append(reason)
    return " ".join(parts)


def classify_failure(row: Any) -> FailureReason:
    """Classify a failed-generation row into a coarse failure reason.

    The signal is gathered from ``error_message`` and from ``params``
    (the table has no ``error_message`` column — callers stash the error
    string under a param key such as ``error_message``/``error``/``detail``).
    Matches are evaluated most-specific-first: OOM before timeout before
    prompt-rejected before queue-stale before the broad model_error bucket,
    finally falling back to ``unknown``.
    """
    text = _error_text(row).lower()
    haystack = f"{text} {' '.join(str(v) for v in (_get(row, 'params') or {}).values())}".lower()

    for group in (_OOM_TOKENS, _TIMEOUT_TOKENS, _PROMPT_TOKENS, _QUEUE_TOKENS, _MODEL_TOKENS):
        for token in group:
            if token in haystack:
                if group is _OOM_TOKENS:
                    return FailureReason.OOM
                if group is _TIMEOUT_TOKENS:
                    return FailureReason.TIMEOUT
                if group is _PROMPT_TOKENS:
                    return FailureReason.PROMPT_REJECTED
                if group is _QUEUE_TOKENS:
                    return FailureReason.QUEUE_STALE
                return FailureReason.MODEL_ERROR
    return FailureReason.UNKNOWN


# =============================================================================
# Failed generation view
# =============================================================================


@dataclass(frozen=True)
class FailedGeneration:
    """A failed generation event as seen by the learning loop.

    Attributes:
        model: Model id (e.g. ``WAN2.2``, ``Klein``).
        params: The JSONB ``params`` payload — may carry ``error_message``
            and sizing hints (``clip_duration_seconds``, ``max_resolution``).
        duration_ms: Elapsed time before the failure was recorded.
        created_at: When the failure was recorded.
        error_message: Optional explicit error text.
    """

    model: str
    params: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    created_at: datetime | None = None
    error_message: str | None = None

    @property
    def reason(self) -> FailureReason:
        """Classify this failure's coarse reason."""
        return classify_failure(self)


def failed_generation_from_row(row: Any) -> FailedGeneration:
    """Build a FailedGeneration from an ORM row or a dict-like mapping."""
    params = _get(row, "params") or {}
    if not isinstance(params, dict):
        params = {}
    return FailedGeneration(
        model=str(_get(row, "model", "")),
        params=params,
        duration_ms=int(_get(row, "duration_ms", 0) or 0),
        created_at=_get(row, "created_at"),
        error_message=_get(row, "error_message"),
    )


# =============================================================================
# Aggregation
# =============================================================================


@dataclass(frozen=True)
class FailureAggregate:
    """Failure count for a single (model, reason) bucket.

    Attributes:
        model: Affected model id.
        reason: Classified failure reason.
        count: Number of failures observed in the window.
        sample_params: Params of the most recent failure (for suggestion
            heuristics such as clip duration / resolution).
        sample_error: Error text of the most recent failure (diagnostic).
    """

    model: str
    reason: FailureReason
    count: int
    sample_params: dict[str, Any] = field(default_factory=dict)
    sample_error: str | None = None


def _within_window(created_at: datetime | None, window: timedelta | None, now: datetime) -> bool:
    if window is None:
        return True
    if created_at is None:
        return True  # no timestamp — assume recent rather than dropping
    return created_at >= now - window


def aggregate_failures(
    rows: "Iterable[Any]",
    *,
    window: timedelta | None = DEFAULT_WINDOW,
    now: datetime | None = None,
) -> list[FailureAggregate]:
    """Group failed generations by (model, reason) and count them.

    Args:
        rows: Failed generation rows / FailedGeneration values.
        window: Only count failures within this lookback of ``now``.
        now: Reference timestamp for the window (default: now in UTC).

    Returns:
        Aggregates sorted by count descending, then model, then reason.
    """
    now = now or datetime.now(UTC)
    buckets: dict[tuple[str, FailureReason], dict[str, Any]] = {}

    for row in rows:
        gen = row if isinstance(row, FailedGeneration) else failed_generation_from_row(row)
        if not gen.model or not _within_window(gen.created_at, window, now):
            continue
        reason = gen.reason
        key = (gen.model, reason)
        bucket = buckets.setdefault(
            key,
            {"model": gen.model, "reason": reason, "count": 0, "params": {}, "error": None},
        )
        bucket["count"] += 1
        bucket["params"] = gen.params  # last seen wins (most recent)
        bucket["error"] = gen.error_message

    aggregates = [
        FailureAggregate(
            model=info["model"],
            reason=info["reason"],
            count=info["count"],
            sample_params=info["params"],
            sample_error=info["error"],
        )
        for info in buckets.values()
    ]
    aggregates.sort(key=lambda a: (-a.count, a.model, a.reason.value))
    return aggregates


# =============================================================================
# Recommendations
# =============================================================================


class Severity(StrEnum):
    """Priority of an enhancement recommendation."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


@dataclass(frozen=True)
class Recommendation:
    """A structured enhancement recommendation for a failing model.

    Attributes:
        affected_model: Model the recommendation targets.
        reason: Failure reason that triggered it.
        count: Number of failures observed.
        severity: Priority rank (critical > high > medium > low).
        suggested_action: Human-readable suggested mitigation.
        detail: Optional richer diagnostic (e.g. a recent error sample).
    """

    affected_model: str
    reason: FailureReason
    count: int
    severity: Severity
    suggested_action: str
    detail: str = ""


def _base_severity(reason: FailureReason) -> Severity:
    """Baseline severity for a reason, escalated by count in the caller."""
    return {
        FailureReason.OOM: Severity.HIGH,
        FailureReason.TIMEOUT: Severity.MEDIUM,
        FailureReason.MODEL_ERROR: Severity.MEDIUM,
        FailureReason.PROMPT_REJECTED: Severity.LOW,
        FailureReason.QUEUE_STALE: Severity.MEDIUM,
        FailureReason.UNKNOWN: Severity.LOW,
    }[reason]


def _escalated_severity(reason: FailureReason, count: int) -> Severity:
    """Severity for a bucket, escalating the baseline with failure volume.

    - ``count >= 10`` pushes every bucket up one step (low→medium,
      medium→high, high→critical).
    - ``count >= 25`` pushes medium and high buckets up a further step.
    """
    sev = _base_severity(reason)
    if count >= 10:
        sev = {
            Severity.LOW: Severity.MEDIUM,
            Severity.MEDIUM: Severity.HIGH,
            Severity.HIGH: Severity.CRITICAL,
            Severity.CRITICAL: Severity.CRITICAL,
        }[sev]
    if count >= 25 and sev in (Severity.MEDIUM, Severity.HIGH):
        sev = Severity.CRITICAL if sev == Severity.HIGH else Severity.HIGH
    return sev


def _fmt_seconds(value: Any) -> str:
    """Render a seconds value (int/float/str) into a clip-label."""
    return f"{value}s" if str(value).lstrip("-").isdigit() else str(value)


def _suggest_action(agg: FailureAggregate) -> str:
    """Build a human-readable suggested action from a failure aggregate."""
    model = agg.model
    count = agg.count
    params = agg.sample_params or {}
    reason = agg.reason

    if reason is FailureReason.OOM:
        secs = (
            params.get("clip_duration_seconds")
            or params.get("clip_seconds")
            or params.get("seconds")
            or params.get("duration_seconds")
        )
        res = (
            params.get("max_resolution")
            or params.get("resolution")
            or params.get("megapixels")
            or params.get("mp")
        )
        if secs is not None:
            return (
                f"{model} failed {count}x on {_fmt_seconds(secs)} clips (OOM): "
                "lower max resolution or switch to 5s clips"
            )
        if res is not None:
            return f"{model} OOM at {res}: cap at 1MP"
        return f"{model} OOM {count}x: lower max resolution or reduce batch size"

    if reason is FailureReason.TIMEOUT:
        return f"{model} timed out {count}x: raise generation timeout or add retry"
    if reason is FailureReason.MODEL_ERROR:
        return f"{model} errored {count}x: verify model availability / provider config"
    if reason is FailureReason.PROMPT_REJECTED:
        return f"{model} rejected {count}x prompts: adjust prompt safety profile"
    if reason is FailureReason.QUEUE_STALE:
        return f"timeout on queue_stale ({model}, {count}x): raise worker count"
    return f"{model} failed {count}x with unknown cause: investigate"


def generate_recommendations(
    aggregates: "Iterable[FailureAggregate]",
    *,
    threshold: int = DEFAULT_THRESHOLD,
) -> list[Recommendation]:
    """Turn failure aggregates into recommendations.

    Only buckets with ``count >= threshold`` produce a recommendation.
    Results are ordered by severity (critical first), then count desc.

    Args:
        aggregates: Aggregates from :func:`aggregate_failures`.
        threshold: Minimum failure count to emit a recommendation.

    Returns:
        Sorted list of recommendations for the passing buckets.
    """
    if threshold < 1:
        raise ValueError("threshold must be >= 1")

    recommendations: list[Recommendation] = []
    for agg in aggregates:
        if agg.count < threshold:
            continue
        recommendations.append(
            Recommendation(
                affected_model=agg.model,
                reason=agg.reason,
                count=agg.count,
                severity=_escalated_severity(agg.reason, agg.count),
                suggested_action=_suggest_action(agg),
                detail=agg.sample_error or "",
            )
        )

    recommendations.sort(
        key=lambda r: (_SEVERITY_ORDER[r.severity], -r.count, r.affected_model)
    )
    return recommendations


# =============================================================================
# DB-backed facade
# =============================================================================


class FailureLearning:
    """Read failed generations and produce enhancement recommendations.

    Wraps aggregation + recommendation over the ``generation_events``
    table. An injectable ``db_client`` keeps this unit-testable without a
    live Supabase connection; when omitted it falls back to the global
    ``backend.database.supabase`` client.
    """

    def __init__(
        self,
        db_client: Any | None = None,
        *,
        threshold: int = DEFAULT_THRESHOLD,
        window: timedelta | None = DEFAULT_WINDOW,
    ) -> None:
        self._db_client = db_client
        self.threshold = threshold
        self.window = window

    def _db(self) -> Any:
        if self._db_client is not None:
            return self._db_client
        from backend.database import supabase

        return supabase

    def fetch_failed(self, org_id: str | None = None) -> list[dict]:
        """Return ``generation_events`` rows with ``status='failed'``."""
        query = self._db().table("generation_events").select("*").eq("status", "failed")
        if org_id is not None:
            query = query.eq("org_id", org_id)
        result = query.execute()
        return result.data or []

    def analyze(
        self,
        org_id: str | None = None,
        *,
        threshold: int | None = None,
        window: timedelta | None = None,
    ) -> list[Recommendation]:
        """Fetch failed rows, aggregate them, and emit recommendations.

        Args:
            org_id: Restrict to one tenant when given.
            threshold: Override the failure threshold for this run.
            window: Override the lookback window for this run.

        Returns:
            Recommendations sorted by severity for buckets above threshold.
        """
        rows = self.fetch_failed(org_id=org_id)
        aggregates = aggregate_failures(rows, window=window if window is not None else self.window)
        return generate_recommendations(
            aggregates, threshold=threshold if threshold is not None else self.threshold
        )
