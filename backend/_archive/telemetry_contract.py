"""Production Telemetry Contract — Story 134.

Structured observability connecting browser → API → jobs → workers → providers.
Every critical path carries a correlation ID. Secrets redacted. Error ingestion
authenticated and rate-limited.

Telemetry layers:
    1. Correlation — propagate request_id/job_id/trace_id end-to-end
    2. Structured logs — typed context fields, never raw user content
    3. Metrics — latency, errors, queue depth, provider failures, GPU spend
    4. Traces — span hierarchy connecting surfaces to final outcomes
    5. Error ingestion — authenticated, tenant-scoped, rate-limited
    6. Audit evidence — immutable, distinct from operational telemetry

Security:
    - Secrets redacted before any persistence (uses error_contract.redact_secrets)
    - Prompt/media content NEVER logged (only hashes/IDs)
    - Tenant-scoped: telemetry for org X invisible to org Y
    - Authenticated ingestion: anonymous error reports rejected
    - Rate-limited: max events per org per minute
    - Oversized payloads truncated with indicator
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Correlation Context
# =============================================================================


@dataclass
class CorrelationContext:
    """Propagated context for distributed tracing."""
    request_id: str = ""          # Per-HTTP-request ID
    trace_id: str = ""            # Distributed trace (spans share this)
    span_id: str = ""             # Current span in the trace
    parent_span_id: str = ""      # Parent span (for hierarchy)
    job_id: str = ""              # Background job reference
    org_id: str = ""              # Workspace (tenant)
    user_id: str = ""             # Actor
    environment: str = ""         # production | staging | development
    release_id: str = ""          # Release version
    surface: str = ""             # create | brain | storyboard | admin
    provider: str = ""            # vast.ai | runpod | elevenlabs | etc.
    resource_type: str = ""       # job | asset | talent | model
    resource_id: str = ""         # Specific resource


def create_correlation(
    org_id: str = "",
    user_id: str = "",
    surface: str = "",
    request_id: str = "",
    job_id: str = "",
    environment: str = "production",
    release_id: str = "",
) -> CorrelationContext:
    """Create a new correlation context for a request or job."""
    return CorrelationContext(
        request_id=request_id or f"req-{uuid.uuid4().hex[:16]}",
        trace_id=f"trace-{uuid.uuid4().hex[:16]}",
        span_id=f"span-{uuid.uuid4().hex[:12]}",
        org_id=org_id,
        user_id=user_id,
        surface=surface,
        job_id=job_id,
        environment=environment,
        release_id=release_id,
    )


def create_child_span(parent: CorrelationContext, resource_type: str = "", resource_id: str = "") -> CorrelationContext:
    """Create a child span inheriting the parent's trace."""
    return CorrelationContext(
        request_id=parent.request_id,
        trace_id=parent.trace_id,
        span_id=f"span-{uuid.uuid4().hex[:12]}",
        parent_span_id=parent.span_id,
        job_id=parent.job_id,
        org_id=parent.org_id,
        user_id=parent.user_id,
        environment=parent.environment,
        release_id=parent.release_id,
        surface=parent.surface,
        provider=parent.provider,
        resource_type=resource_type or parent.resource_type,
        resource_id=resource_id or parent.resource_id,
    )


# =============================================================================
# Structured Log Entry
# =============================================================================


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class StructuredLog:
    """A structured log entry with full context."""
    timestamp: float = field(default_factory=time.time)
    level: LogLevel = LogLevel.INFO
    message: str = ""
    event_type: str = ""          # e.g. "generation_submitted", "worker_heartbeat_lost"
    correlation: CorrelationContext = field(default_factory=CorrelationContext)
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None  # For timing spans


# =============================================================================
# Metrics
# =============================================================================


class MetricType(str, Enum):
    COUNTER = "counter"           # Monotonically increasing
    GAUGE = "gauge"               # Point-in-time value
    HISTOGRAM = "histogram"       # Distribution of values


@dataclass
class MetricDefinition:
    """A defined metric in the telemetry system."""
    name: str
    metric_type: MetricType
    unit: str = ""                # ms, count, usd, bytes
    description: str = ""
    labels: list[str] = field(default_factory=list)  # Dimensions


# Standard metrics
METRICS_REGISTRY: list[MetricDefinition] = [
    MetricDefinition("api_request_duration_ms", MetricType.HISTOGRAM, "ms", "API request latency", ["endpoint", "method", "status"]),
    MetricDefinition("api_error_total", MetricType.COUNTER, "count", "Total API errors", ["endpoint", "status", "error_category"]),
    MetricDefinition("generation_queue_depth", MetricType.GAUGE, "count", "Pending generation jobs"),
    MetricDefinition("generation_queue_age_seconds", MetricType.GAUGE, "seconds", "Age of oldest queued job"),
    MetricDefinition("generation_duration_ms", MetricType.HISTOGRAM, "ms", "Generation execution time", ["model", "surface"]),
    MetricDefinition("provider_failure_total", MetricType.COUNTER, "count", "Provider failures", ["provider", "error_type"]),
    MetricDefinition("provider_latency_ms", MetricType.HISTOGRAM, "ms", "Provider response time", ["provider"]),
    MetricDefinition("gpu_spend_usd", MetricType.COUNTER, "usd", "Cumulative GPU spend", ["provider", "org_id"]),
    MetricDefinition("worker_heartbeat_age_seconds", MetricType.GAUGE, "seconds", "Time since last worker heartbeat"),
    MetricDefinition("retry_total", MetricType.COUNTER, "count", "Total retries", ["operation", "outcome"]),
    MetricDefinition("cleanup_debt_count", MetricType.GAUGE, "count", "Pending cleanup tasks"),
    MetricDefinition("telemetry_ingestion_total", MetricType.COUNTER, "count", "Error events ingested", ["org_id", "accepted"]),
]


@dataclass
class MetricSample:
    """A single metric measurement."""
    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    org_id: str = ""


# =============================================================================
# Error Ingestion (authenticated, rate-limited)
# =============================================================================


MAX_PAYLOAD_BYTES = 10_000
MAX_EVENTS_PER_ORG_PER_MINUTE = 100


@dataclass
class ErrorEvent:
    """An ingested error event from frontend or service."""
    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    user_id: str = ""
    correlation_id: str = ""
    source: str = ""              # "frontend" | "api" | "worker" | "scheduler"
    error_category: str = ""
    message: str = ""             # Redacted before storage
    stack_hash: str = ""          # Hash of stack trace (not the trace itself)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    accepted: bool = True
    rejection_reason: str = ""


# =============================================================================
# Stores
# =============================================================================

_logs: list[StructuredLog] = []
_metrics: list[MetricSample] = []
_error_events: list[ErrorEvent] = []
_rate_limit_windows: dict[str, list[float]] = {}  # org_id → [timestamps]
_seen_event_ids: set[str] = set()  # Deduplication


# =============================================================================
# Redaction (extends error_contract)
# =============================================================================

# Patterns that must NEVER appear in telemetry
REDACT_PATTERNS = [
    "password", "secret", "token", "api_key", "apikey",
    "authorization", "cookie", "session_id",
]

CONTENT_FIELDS = {"prompt", "caption", "message_content", "body", "payload"}


def redact_for_telemetry(data: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive fields from telemetry data.

    Rules:
    - Known secret field names → "***REDACTED***"
    - Content fields (prompts, captions) → hash only
    - Values > 500 chars → truncated with "[truncated]"
    """
    redacted = {}
    for key, value in data.items():
        key_lower = key.lower()

        # Secret fields
        if any(p in key_lower for p in REDACT_PATTERNS):
            redacted[key] = "***REDACTED***"
            continue

        # Content fields — store hash only
        if key_lower in CONTENT_FIELDS and isinstance(value, str) and value:
            redacted[key] = f"[hash:{hashlib.sha256(value.encode()).hexdigest()[:12]}]"
            continue

        # Truncate oversized values
        if isinstance(value, str) and len(value) > 500:
            redacted[key] = value[:497] + "[truncated]"
            continue

        redacted[key] = value

    return redacted


# =============================================================================
# Telemetry API
# =============================================================================


def emit_log(
    level: LogLevel,
    message: str,
    event_type: str = "",
    correlation: CorrelationContext | None = None,
    metadata: dict[str, Any] | None = None,
    duration_ms: float | None = None,
) -> StructuredLog:
    """Emit a structured log entry."""
    log = StructuredLog(
        level=level,
        message=message,
        event_type=event_type,
        correlation=correlation or CorrelationContext(),
        metadata=redact_for_telemetry(metadata or {}),
        duration_ms=duration_ms,
    )
    _logs.append(log)
    return log


def emit_metric(
    name: str,
    value: float,
    labels: dict[str, str] | None = None,
    org_id: str = "",
) -> MetricSample:
    """Record a metric sample."""
    sample = MetricSample(name=name, value=value, labels=labels or {}, org_id=org_id)
    _metrics.append(sample)
    return sample


def ingest_error_event(
    org_id: str,
    user_id: str,
    source: str,
    error_category: str,
    message: str,
    correlation_id: str = "",
    stack_trace: str = "",
    metadata: dict[str, Any] | None = None,
    event_id: str = "",
) -> ErrorEvent:
    """Ingest an error event with authentication, rate-limiting, and redaction.

    Rejects:
    - Anonymous (no org_id or user_id)
    - Rate-limited orgs
    - Duplicate event_ids
    - Oversized payloads
    """
    event = ErrorEvent(
        event_id=event_id or f"evt-{uuid.uuid4().hex[:12]}",
        org_id=org_id,
        user_id=user_id,
        correlation_id=correlation_id,
        source=source,
        error_category=error_category,
    )

    # Gate 1: Authentication
    if not org_id or not user_id:
        event.accepted = False
        event.rejection_reason = "anonymous_rejected"
        _error_events.append(event)
        return event

    # Gate 2: Deduplication
    if event.event_id in _seen_event_ids:
        event.accepted = False
        event.rejection_reason = "duplicate_event"
        _error_events.append(event)
        return event

    # Gate 3: Rate limiting
    if not _check_rate_limit(org_id):
        event.accepted = False
        event.rejection_reason = "rate_limited"
        _error_events.append(event)
        return event

    # Gate 4: Payload size
    total_size = len(message) + len(stack_trace) + len(str(metadata or {}))
    if total_size > MAX_PAYLOAD_BYTES:
        message = message[:1000] + "[truncated]"

    # Redact message
    from backend.error_contract import redact_secrets
    event.message = redact_secrets(message)

    # Hash stack trace (never store raw)
    if stack_trace:
        event.stack_hash = hashlib.sha256(stack_trace.encode()).hexdigest()[:16]

    # Redact metadata
    event.metadata = redact_for_telemetry(metadata or {})

    # Accept
    _seen_event_ids.add(event.event_id)
    _error_events.append(event)

    emit_metric("telemetry_ingestion_total", 1, {"org_id": org_id, "accepted": "true"})
    return event


# =============================================================================
# Rate Limiting
# =============================================================================


def _check_rate_limit(org_id: str) -> bool:
    """Check if org is within rate limit (sliding window)."""
    now = time.time()
    window_start = now - 60  # 1-minute window

    if org_id not in _rate_limit_windows:
        _rate_limit_windows[org_id] = []

    # Clean old entries
    _rate_limit_windows[org_id] = [t for t in _rate_limit_windows[org_id] if t > window_start]

    if len(_rate_limit_windows[org_id]) >= MAX_EVENTS_PER_ORG_PER_MINUTE:
        return False

    _rate_limit_windows[org_id].append(now)
    return True


# =============================================================================
# Telemetry Failure Behavior
# =============================================================================


class TelemetryFailurePolicy(str, Enum):
    LOG_AND_CONTINUE = "log_and_continue"      # Default: don't block
    BLOCK_HIGH_RISK = "block_high_risk"        # Block the action if audit required


# Actions that MUST have telemetry (block if telemetry backend down)
AUDIT_REQUIRED_ACTIONS = frozenset({
    "approval_decision",
    "credential_rotation",
    "data_deletion",
    "role_change",
    "budget_override",
})


def should_block_on_telemetry_failure(action: str) -> bool:
    """Determine if an action should be blocked when telemetry is unavailable.

    Most actions continue without telemetry (operational degradation).
    Audit-required actions MUST be recorded — block if telemetry is down.
    """
    return action in AUDIT_REQUIRED_ACTIONS


# =============================================================================
# Query (for testing and ops)
# =============================================================================


def get_logs(org_id: str | None = None, event_type: str | None = None, limit: int = 100) -> list[StructuredLog]:
    """Get logs, optionally filtered."""
    results = _logs
    if org_id:
        results = [l for l in results if l.correlation.org_id == org_id]
    if event_type:
        results = [l for l in results if l.event_type == event_type]
    return results[-limit:]


def get_metrics_samples(name: str | None = None, org_id: str | None = None) -> list[MetricSample]:
    """Get metric samples."""
    results = _metrics
    if name:
        results = [m for m in results if m.name == name]
    if org_id:
        results = [m for m in results if m.org_id == org_id]
    return results


def get_error_events(org_id: str, accepted_only: bool = True) -> list[ErrorEvent]:
    """Get error events for an org (tenant-scoped)."""
    events = [e for e in _error_events if e.org_id == org_id]
    if accepted_only:
        events = [e for e in events if e.accepted]
    return events


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _logs.clear()
    _metrics.clear()
    _error_events.clear()
    _rate_limit_windows.clear()
    _seen_event_ids.clear()
