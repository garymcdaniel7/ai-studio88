"""Provider routing governance tests — Story 060.

Tests prove:
  - Evidence recording requires provider + org_id
  - Reputation aggregation is accurate
  - Stale evidence is explicitly marked
  - Sparse evidence has low confidence
  - Suppressions are scoped and time-bound
  - Expired suppressions no longer block
  - Reinstatement ends suppression immediately
  - Routing context reflects suppression state
  - Scope isolation (host failure doesn't suppress provider)
  - Routing decisions are recorded with full context
  - Failure categories are correctly classified
"""

import time

import pytest

from backend.infrastructure.routing_governance import (
    EvidenceScope,
    FailureCategory,
    SuppressionStatus,
    _reset_store,
    expire_stale_suppressions,
    get_active_suppressions,
    get_reputation,
    get_routing_context,
    is_suppressed,
    record_evidence,
    record_routing_decision,
    reinstate,
    suppress,
)

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture(autouse=True)
def clean_store():
    _reset_store()
    yield
    _reset_store()


# =============================================================================
# Evidence Recording
# =============================================================================


@pytest.mark.unit
class TestEvidenceRecording:

    def test_records_success(self):
        ev = record_evidence(TENANT_A, "runpod", FailureCategory.SUCCESS, gpu_type="A100", latency_ms=5000)
        assert ev.provider == "runpod"
        assert ev.outcome == FailureCategory.SUCCESS
        assert ev.latency_ms == 5000

    def test_records_failure(self):
        ev = record_evidence(TENANT_A, "vast", FailureCategory.STARTUP_TIMEOUT, host_id="h-123", detail="SSH unreachable after 300s")
        assert ev.outcome == FailureCategory.STARTUP_TIMEOUT
        assert ev.host_id == "h-123"

    def test_requires_org_id(self):
        with pytest.raises(ValueError, match="org_id"):
            record_evidence("", "runpod", FailureCategory.SUCCESS)

    def test_requires_provider(self):
        with pytest.raises(ValueError, match="provider"):
            record_evidence(TENANT_A, "", FailureCategory.SUCCESS)


# =============================================================================
# Reputation Aggregation
# =============================================================================


@pytest.mark.unit
class TestReputationAggregation:

    def test_empty_reputation_is_stale(self):
        rep = get_reputation(EvidenceScope.PROVIDER, "runpod")
        assert rep.total_attempts == 0
        assert rep.is_stale is True
        assert rep.confidence == 0.0

    def test_success_rate_correct(self):
        for _ in range(8):
            record_evidence(TENANT_A, "runpod", FailureCategory.SUCCESS)
        for _ in range(2):
            record_evidence(TENANT_A, "runpod", FailureCategory.STARTUP_TIMEOUT)
        rep = get_reputation(EvidenceScope.PROVIDER, "runpod")
        assert rep.total_attempts == 10
        assert rep.successes == 8
        assert rep.failures == 2
        assert abs(rep.success_rate - 0.8) < 0.01

    def test_failure_categories_breakdown(self):
        record_evidence(TENANT_A, "vast", FailureCategory.STARTUP_TIMEOUT)
        record_evidence(TENANT_A, "vast", FailureCategory.HEALTH_FAILURE)
        record_evidence(TENANT_A, "vast", FailureCategory.STARTUP_TIMEOUT)
        rep = get_reputation(EvidenceScope.PROVIDER, "vast")
        assert rep.failure_categories["startup_timeout"] == 2
        assert rep.failure_categories["health_failure"] == 1

    def test_confidence_increases_with_evidence(self):
        record_evidence(TENANT_A, "runpod", FailureCategory.SUCCESS)
        rep1 = get_reputation(EvidenceScope.PROVIDER, "runpod")
        for _ in range(9):
            record_evidence(TENANT_A, "runpod", FailureCategory.SUCCESS)
        rep2 = get_reputation(EvidenceScope.PROVIDER, "runpod")
        assert rep2.confidence > rep1.confidence

    def test_scoped_to_specific_id(self):
        record_evidence(TENANT_A, "runpod", FailureCategory.SUCCESS, gpu_type="A100")
        record_evidence(TENANT_A, "runpod", FailureCategory.STARTUP_TIMEOUT, gpu_type="RTX 4090")
        rep_a100 = get_reputation(EvidenceScope.GPU_TYPE, "A100")
        rep_4090 = get_reputation(EvidenceScope.GPU_TYPE, "RTX 4090")
        assert rep_a100.successes == 1
        assert rep_a100.failures == 0
        assert rep_4090.successes == 0
        assert rep_4090.failures == 1

    def test_customer_cancel_not_counted_as_failure(self):
        record_evidence(TENANT_A, "runpod", FailureCategory.CUSTOMER_CANCEL)
        rep = get_reputation(EvidenceScope.PROVIDER, "runpod")
        assert rep.failures == 0  # Cancel is not a provider fault

    def test_avg_latency_computed(self):
        record_evidence(TENANT_A, "runpod", FailureCategory.SUCCESS, latency_ms=1000)
        record_evidence(TENANT_A, "runpod", FailureCategory.SUCCESS, latency_ms=3000)
        rep = get_reputation(EvidenceScope.PROVIDER, "runpod")
        assert rep.avg_latency_ms == 2000.0


# =============================================================================
# Suppression/Blacklist
# =============================================================================


@pytest.mark.unit
class TestSuppression:

    def test_create_suppression(self):
        sup = suppress(EvidenceScope.HOST, "h-bad", "vast", "3 failures in 1 hour", "automated:failure_threshold", duration_hours=24)
        assert sup.status == SuppressionStatus.ACTIVE
        assert sup.is_active is True
        assert len(sup.history) == 1

    def test_suppression_blocks_routing(self):
        suppress(EvidenceScope.HOST, "h-bad", "vast", "fails", "auto", duration_hours=1)
        assert is_suppressed(EvidenceScope.HOST, "h-bad") is True
        assert is_suppressed(EvidenceScope.HOST, "h-good") is False

    def test_suppression_expires(self):
        sup = suppress(EvidenceScope.HOST, "h-temp", "vast", "temp", "auto", duration_hours=0.001)
        sup.expires_at = time.time() - 10  # Force expire
        expired = expire_stale_suppressions()
        assert sup.suppression_id in expired
        assert sup.status == SuppressionStatus.EXPIRED
        assert is_suppressed(EvidenceScope.HOST, "h-temp") is False

    def test_reinstatement(self):
        sup = suppress(EvidenceScope.HOST, "h-review", "vast", "investigating", "manual:admin", duration_hours=48)
        reinstate(sup.suppression_id, "admin-user", "Issue resolved")
        assert sup.status == SuppressionStatus.REINSTATED
        assert sup.reinstated_by == "admin-user"
        assert is_suppressed(EvidenceScope.HOST, "h-review") is False
        assert len(sup.history) == 2

    def test_requires_reason_and_authority(self):
        with pytest.raises(ValueError):
            suppress(EvidenceScope.HOST, "h-x", "vast", "", "auto")
        with pytest.raises(ValueError):
            suppress(EvidenceScope.HOST, "h-x", "vast", "reason", "")

    def test_scope_isolation_host_vs_provider(self):
        """Suppressing a host does NOT suppress the entire provider."""
        suppress(EvidenceScope.HOST, "h-bad", "vast", "bad host", "auto")
        assert is_suppressed(EvidenceScope.HOST, "h-bad") is True
        assert is_suppressed(EvidenceScope.PROVIDER, "vast") is False


# =============================================================================
# Routing Context
# =============================================================================


@pytest.mark.unit
class TestRoutingContext:

    def test_unsuppressed_provider(self):
        ctx = get_routing_context("runpod")
        assert ctx["suppressed"] is False
        assert ctx["evidence_available"] is False

    def test_suppressed_provider_blocks(self):
        suppress(EvidenceScope.PROVIDER, "vast", "vast", "outage", "manual:ops")
        ctx = get_routing_context("vast")
        assert ctx["suppressed"] is True
        assert "suppressed" in ctx["suppression_reason"]

    def test_context_includes_reputation(self):
        for _ in range(5):
            record_evidence(TENANT_A, "runpod", FailureCategory.SUCCESS)
        ctx = get_routing_context("runpod")
        assert ctx["evidence_available"] is True
        assert ctx["reputation"]["success_rate"] == 1.0
        assert ctx["reputation"]["total_attempts"] == 5


# =============================================================================
# Routing Decision Recording
# =============================================================================


@pytest.mark.unit
class TestRoutingDecisions:

    def test_records_decision(self):
        dec = record_routing_decision(
            org_id=TENANT_A,
            selected_provider="runpod",
            candidates_considered=3,
            candidates_suppressed=1,
            reason="Highest success rate",
            confidence=0.85,
            evidence_count=20,
            policy_version="v1.0",
        )
        assert dec.selected_provider == "runpod"
        assert dec.candidates_considered == 3
        assert dec.candidates_suppressed == 1
        assert dec.confidence == 0.85
