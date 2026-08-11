"""Production telemetry contract tests — Story 134.

Tests prove:
  - Correlation IDs propagate through child spans
  - Redaction removes secrets and content from telemetry
  - Rate limiting enforced per org
  - Tenant-scoped error events
  - Telemetry failure blocks audit-required actions
  - Duplicate events rejected
  - Oversized payloads truncated
  - Anonymous ingestion rejected
  - Metrics recorded with labels
  - Structured logs carry context
"""

import pytest

from backend.telemetry_contract import (
    AUDIT_REQUIRED_ACTIONS,
    MAX_EVENTS_PER_ORG_PER_MINUTE,
    CorrelationContext,
    LogLevel,
    _reset_store,
    create_child_span,
    create_correlation,
    emit_log,
    emit_metric,
    get_error_events,
    get_logs,
    get_metrics_samples,
    ingest_error_event,
    redact_for_telemetry,
    should_block_on_telemetry_failure,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
USER = "user-001"


# =============================================================================
# Correlation Propagation
# =============================================================================


@pytest.mark.unit
class TestCorrelationPropagation:

    def test_create_correlation_has_ids(self):
        ctx = create_correlation(org_id=ORG, user_id=USER, surface="create")
        assert ctx.request_id.startswith("req-")
        assert ctx.trace_id.startswith("trace-")
        assert ctx.span_id.startswith("span-")
        assert ctx.org_id == ORG

    def test_child_span_inherits_trace(self):
        parent = create_correlation(org_id=ORG, user_id=USER)
        child = create_child_span(parent, resource_type="job", resource_id="j-001")
        assert child.trace_id == parent.trace_id
        assert child.parent_span_id == parent.span_id
        assert child.span_id != parent.span_id
        assert child.org_id == ORG
        assert child.resource_type == "job"
        assert child.resource_id == "j-001"

    def test_nested_spans(self):
        root = create_correlation(org_id=ORG)
        child = create_child_span(root)
        grandchild = create_child_span(child, resource_type="asset")
        assert grandchild.trace_id == root.trace_id
        assert grandchild.parent_span_id == child.span_id


# =============================================================================
# Redaction
# =============================================================================


@pytest.mark.unit
class TestRedaction:

    def test_secrets_redacted(self):
        data = {"api_key": "sk-12345", "name": "safe", "password": "hunter2"}
        redacted = redact_for_telemetry(data)
        assert redacted["api_key"] == "***REDACTED***"
        assert redacted["password"] == "***REDACTED***"
        assert redacted["name"] == "safe"

    def test_content_hashed(self):
        data = {"prompt": "a beautiful sunset over mountains"}
        redacted = redact_for_telemetry(data)
        assert redacted["prompt"].startswith("[hash:")
        assert "sunset" not in redacted["prompt"]

    def test_oversized_truncated(self):
        data = {"description": "x" * 1000}
        redacted = redact_for_telemetry(data)
        assert len(redacted["description"]) <= 510
        assert "[truncated]" in redacted["description"]

    def test_normal_values_unchanged(self):
        data = {"status": "completed", "count": 42}
        redacted = redact_for_telemetry(data)
        assert redacted == data

    def test_token_field_redacted(self):
        data = {"authorization": "Bearer xxx", "session_id": "sess-123"}
        redacted = redact_for_telemetry(data)
        assert redacted["authorization"] == "***REDACTED***"
        assert redacted["session_id"] == "***REDACTED***"


# =============================================================================
# Rate Limiting
# =============================================================================


@pytest.mark.unit
class TestRateLimiting:

    def test_within_limit_accepted(self):
        event = ingest_error_event(ORG, USER, "frontend", "unknown", "oops")
        assert event.accepted is True

    def test_exceeding_limit_rejected(self):
        # Fill up rate limit
        for i in range(MAX_EVENTS_PER_ORG_PER_MINUTE):
            ingest_error_event(ORG, USER, "frontend", "error", f"event {i}",
                               event_id=f"evt-{i}")

        # Next one should be rejected
        event = ingest_error_event(ORG, USER, "frontend", "error", "too many",
                                   event_id="evt-overflow")
        assert event.accepted is False
        assert event.rejection_reason == "rate_limited"

    def test_different_orgs_independent_limits(self):
        for i in range(MAX_EVENTS_PER_ORG_PER_MINUTE):
            ingest_error_event(ORG, USER, "api", "err", f"e{i}", event_id=f"a-{i}")

        # Other org still has capacity
        event = ingest_error_event(OTHER_ORG, "u2", "api", "err", "ok", event_id="b-1")
        assert event.accepted is True


# =============================================================================
# Tenant Scope
# =============================================================================


@pytest.mark.unit
class TestTenantScope:

    def test_error_events_scoped_to_org(self):
        ingest_error_event(ORG, USER, "frontend", "error", "my error")
        ingest_error_event(OTHER_ORG, "other-user", "frontend", "error", "their error")

        my_events = get_error_events(ORG)
        their_events = get_error_events(OTHER_ORG)
        assert len(my_events) == 1
        assert len(their_events) == 1
        assert my_events[0].org_id == ORG

    def test_logs_filterable_by_org(self):
        ctx1 = create_correlation(org_id=ORG)
        ctx2 = create_correlation(org_id=OTHER_ORG)
        emit_log(LogLevel.INFO, "msg1", correlation=ctx1)
        emit_log(LogLevel.INFO, "msg2", correlation=ctx2)

        my_logs = get_logs(org_id=ORG)
        assert len(my_logs) == 1


# =============================================================================
# Telemetry Failure Behavior
# =============================================================================


@pytest.mark.unit
class TestTelemetryFailure:

    def test_audit_required_actions_block(self):
        assert should_block_on_telemetry_failure("approval_decision") is True
        assert should_block_on_telemetry_failure("credential_rotation") is True
        assert should_block_on_telemetry_failure("data_deletion") is True

    def test_normal_actions_dont_block(self):
        assert should_block_on_telemetry_failure("generation_submit") is False
        assert should_block_on_telemetry_failure("read_talent") is False
        assert should_block_on_telemetry_failure("list_assets") is False


# =============================================================================
# Duplicate Events
# =============================================================================


@pytest.mark.unit
class TestDuplicateEvents:

    def test_duplicate_event_id_rejected(self):
        e1 = ingest_error_event(ORG, USER, "frontend", "err", "first", event_id="evt-dup-001")
        e2 = ingest_error_event(ORG, USER, "frontend", "err", "second", event_id="evt-dup-001")
        assert e1.accepted is True
        assert e2.accepted is False
        assert e2.rejection_reason == "duplicate_event"

    def test_different_event_ids_both_accepted(self):
        e1 = ingest_error_event(ORG, USER, "api", "err", "a", event_id="evt-1")
        e2 = ingest_error_event(ORG, USER, "api", "err", "b", event_id="evt-2")
        assert e1.accepted is True
        assert e2.accepted is True


# =============================================================================
# Oversized Payload
# =============================================================================


@pytest.mark.unit
class TestOversizedPayload:

    def test_oversized_message_truncated(self):
        big_message = "x" * 20_000
        event = ingest_error_event(ORG, USER, "worker", "error", big_message)
        assert event.accepted is True
        assert len(event.message) < 20_000
        assert "[truncated]" in event.message


# =============================================================================
# Anonymous Rejected
# =============================================================================


@pytest.mark.unit
class TestAnonymousRejected:

    def test_no_org_rejected(self):
        event = ingest_error_event("", USER, "frontend", "error", "anon")
        assert event.accepted is False
        assert event.rejection_reason == "anonymous_rejected"

    def test_no_user_rejected(self):
        event = ingest_error_event(ORG, "", "frontend", "error", "no user")
        assert event.accepted is False
        assert event.rejection_reason == "anonymous_rejected"


# =============================================================================
# Metrics
# =============================================================================


@pytest.mark.unit
class TestMetrics:

    def test_emit_metric(self):
        emit_metric("api_request_duration_ms", 150.5, {"endpoint": "/talent", "status": "200"})
        samples = get_metrics_samples("api_request_duration_ms")
        assert len(samples) == 1
        assert samples[0].value == 150.5
        assert samples[0].labels["endpoint"] == "/talent"

    def test_metrics_scoped_by_org(self):
        emit_metric("gpu_spend_usd", 0.05, org_id=ORG)
        emit_metric("gpu_spend_usd", 0.10, org_id=OTHER_ORG)
        my_metrics = get_metrics_samples("gpu_spend_usd", org_id=ORG)
        assert len(my_metrics) == 1
        assert my_metrics[0].value == 0.05


# =============================================================================
# Structured Logs
# =============================================================================


@pytest.mark.unit
class TestStructuredLogs:

    def test_log_carries_correlation(self):
        ctx = create_correlation(org_id=ORG, user_id=USER, surface="brain")
        emit_log(LogLevel.INFO, "Chat submitted", event_type="brain_chat", correlation=ctx)
        logs = get_logs(event_type="brain_chat")
        assert len(logs) == 1
        assert logs[0].correlation.org_id == ORG
        assert logs[0].correlation.surface == "brain"

    def test_log_metadata_redacted(self):
        emit_log(LogLevel.ERROR, "Failed", metadata={"api_key": "secret123", "job_id": "j-1"})
        logs = get_logs()
        assert logs[0].metadata["api_key"] == "***REDACTED***"
        assert logs[0].metadata["job_id"] == "j-1"

    def test_log_with_duration(self):
        emit_log(LogLevel.INFO, "Request complete", duration_ms=245.3)
        logs = get_logs()
        assert logs[0].duration_ms == 245.3
