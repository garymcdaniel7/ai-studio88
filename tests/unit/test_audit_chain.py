"""Immutable Audit Chain Tests (Story 047).

Proves: full action reconstruction, cross-tenant isolation, redaction,
mandatory-failure behavior, integrity verification, and correlation.

Run with:
    pytest tests/unit/test_audit_chain.py -v
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from backend.audit_chain import (
    MANDATORY_EVENTS,
    AuditChainService,
    AuditEventType,
    AuditPersistenceError,
    _event_store,
    _redact_arguments,
)

ORG_A = str(uuid4())
ORG_B = str(uuid4())
USER_A = str(uuid4())
USER_B = str(uuid4())


@pytest.fixture(autouse=True)
def clean():
    _event_store.clear()
    import backend.audit_chain as mod
    mod._last_hash = "genesis"
    yield
    _event_store.clear()
    mod._last_hash = "genesis"


# =============================================================================
# Full Action Reconstruction
# =============================================================================


class TestFullReconstruction:
    """Prove an entire action lifecycle can be reconstructed from audit events."""

    @pytest.mark.unit
    def test_full_lifecycle_correlated(self):
        """Plan → decision → execution → result all share correlation_id."""
        cor_id = AuditChainService.new_correlation_id()

        AuditChainService.emit(
            event_type=AuditEventType.PLAN_CREATED,
            correlation_id=cor_id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
            tool="generate_image",
        )
        AuditChainService.emit(
            event_type=AuditEventType.GOVERNANCE_DECISION,
            correlation_id=cor_id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
            tool="generate_image", result={"state": "allowed"},
        )
        AuditChainService.emit(
            event_type=AuditEventType.EXECUTION_STARTED,
            correlation_id=cor_id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
            tool="generate_image", command_id="cmd-123",
        )
        AuditChainService.emit(
            event_type=AuditEventType.EXECUTION_COMPLETED,
            correlation_id=cor_id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
            tool="generate_image", command_id="cmd-123",
            resource_ids=["asset-456"], actual_cost_usd=0.02,
            duration_ms=3500,
        )

        chain = AuditChainService.get_chain(cor_id, ORG_A)
        assert len(chain) == 4
        assert chain[0]["event_type"] == "plan_created"
        assert chain[1]["event_type"] == "governance_decision"
        assert chain[2]["event_type"] == "execution_started"
        assert chain[3]["event_type"] == "execution_completed"
        assert chain[3]["resource_ids"] == ["asset-456"]
        assert chain[3]["actual_cost_usd"] == 0.02

    @pytest.mark.unit
    def test_correlation_id_links_approval_flow(self):
        """Approval events are correlated with execution."""
        cor_id = AuditChainService.new_correlation_id()

        AuditChainService.emit(
            event_type=AuditEventType.APPROVAL_REQUESTED,
            correlation_id=cor_id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
            tool="launch_gpu", approval_id="apr-1",
        )
        AuditChainService.emit(
            event_type=AuditEventType.APPROVAL_DECIDED,
            correlation_id=cor_id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="owner",
            approval_id="apr-1", result={"decision": "approved"},
        )

        chain = AuditChainService.get_chain(cor_id, ORG_A)
        assert len(chain) == 2
        assert all(e["approval_id"] == "apr-1" for e in chain)


# =============================================================================
# Cross-Tenant Isolation
# =============================================================================


class TestCrossTenantIsolation:

    @pytest.mark.unit
    def test_get_chain_scoped_to_org(self):
        """Cannot see another org's audit chain."""
        cor_id = AuditChainService.new_correlation_id()

        AuditChainService.emit(
            event_type=AuditEventType.EXECUTION_STARTED,
            correlation_id=cor_id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor", tool="gen",
        )

        # Org B cannot see Org A's chain
        assert AuditChainService.get_chain(cor_id, ORG_B) == []
        # Org A can see it
        assert len(AuditChainService.get_chain(cor_id, ORG_A)) == 1

    @pytest.mark.unit
    def test_query_scoped_to_org(self):
        """Query results are tenant-isolated."""
        AuditChainService.emit(
            event_type=AuditEventType.PLAN_CREATED,
            correlation_id="c1", org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor", tool="gen",
        )
        AuditChainService.emit(
            event_type=AuditEventType.PLAN_CREATED,
            correlation_id="c2", org_id=ORG_B,
            actor_user_id=USER_B, actor_role="editor", tool="gen",
        )

        results_a = AuditChainService.query(org_id=ORG_A)
        results_b = AuditChainService.query(org_id=ORG_B)
        assert len(results_a) == 1
        assert len(results_b) == 1
        assert results_a[0]["org_id"] == ORG_A
        assert results_b[0]["org_id"] == ORG_B


# =============================================================================
# Redaction
# =============================================================================


class TestRedaction:

    @pytest.mark.unit
    def test_secrets_redacted_from_arguments(self):
        """Sensitive fields in arguments are redacted before storage."""
        summary = _redact_arguments({
            "prompt": "a portrait",
            "api_key": "sk-super-secret-key-12345",
            "model": "flux-dev",
        })
        assert "sk-super-secret" not in summary
        assert "[REDACTED]" in summary
        assert "flux-dev" in summary

    @pytest.mark.unit
    def test_long_values_truncated(self):
        """Values longer than 200 chars are truncated."""
        summary = _redact_arguments({"long_field": "x" * 500})
        assert len(summary) < 500
        assert "..." in summary

    @pytest.mark.unit
    def test_error_messages_redacted(self):
        """Error messages containing secrets are cleaned."""
        cor_id = AuditChainService.new_correlation_id()
        AuditChainService.emit(
            event_type=AuditEventType.EXECUTION_FAILED,
            correlation_id=cor_id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
            error="Connection failed with key sk-ant-abcdef123456789012345678901234567890",
        )

        chain = AuditChainService.get_chain(cor_id, ORG_A)
        assert "sk-ant-abcdef" not in chain[0]["error"]
        assert "[REDACTED]" in chain[0]["error"]


# =============================================================================
# Mandatory Failure Behavior
# =============================================================================


class TestMandatoryFailure:

    @pytest.mark.unit
    def test_mandatory_events_defined(self):
        """Critical execution events are in the mandatory set."""
        assert AuditEventType.EXECUTION_STARTED in MANDATORY_EVENTS
        assert AuditEventType.EXECUTION_COMPLETED in MANDATORY_EVENTS
        assert AuditEventType.EXECUTION_FAILED in MANDATORY_EVENTS
        assert AuditEventType.SIDE_EFFECT in MANDATORY_EVENTS
        assert AuditEventType.APPROVAL_DECIDED in MANDATORY_EVENTS

    @pytest.mark.unit
    def test_non_mandatory_events_not_in_set(self):
        """Planning events are NOT mandatory (don't block on failure)."""
        assert AuditEventType.PLAN_CREATED not in MANDATORY_EVENTS
        assert AuditEventType.GOVERNANCE_DECISION not in MANDATORY_EVENTS

    @pytest.mark.unit
    def test_mandatory_event_failure_raises(self):
        """If mandatory event can't persist, AuditPersistenceError is raised."""
        import backend.audit_chain as mod
        original_store = mod._event_store

        # Replace store with a broken one
        class BrokenList(list):
            def append(self, item):
                raise RuntimeError("disk full")

        mod._event_store = BrokenList()
        try:
            with pytest.raises(AuditPersistenceError):
                AuditChainService.emit(
                    event_type=AuditEventType.EXECUTION_STARTED,
                    correlation_id="c1", org_id=ORG_A,
                    actor_user_id=USER_A, actor_role="editor",
                    mandatory=True,
                )
        finally:
            mod._event_store = original_store

    @pytest.mark.unit
    def test_non_mandatory_failure_does_not_raise(self):
        """Non-mandatory events don't block on persistence failure."""
        import backend.audit_chain as mod
        original_store = mod._event_store

        class BrokenList(list):
            def append(self, item):
                raise RuntimeError("disk full")

        mod._event_store = BrokenList()
        try:
            # Should NOT raise
            AuditChainService.emit(
                event_type=AuditEventType.PLAN_CREATED,
                correlation_id="c1", org_id=ORG_A,
                actor_user_id=USER_A, actor_role="editor",
                mandatory=False,
            )
        finally:
            mod._event_store = original_store


# =============================================================================
# Integrity Verification
# =============================================================================


class TestIntegrityVerification:

    @pytest.mark.unit
    def test_valid_chain_passes_integrity(self):
        """Unmodified chain passes integrity verification."""
        cor_id = AuditChainService.new_correlation_id()
        AuditChainService.emit(
            event_type=AuditEventType.PLAN_CREATED,
            correlation_id=cor_id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor", tool="gen",
        )
        AuditChainService.emit(
            event_type=AuditEventType.EXECUTION_STARTED,
            correlation_id=cor_id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor", tool="gen",
        )

        result = AuditChainService.verify_integrity(ORG_A)
        assert result["valid"] is True
        assert result["events_checked"] == 2

    @pytest.mark.unit
    def test_empty_chain_is_valid(self):
        """Empty audit chain is considered valid."""
        result = AuditChainService.verify_integrity(ORG_A)
        assert result["valid"] is True
        assert result["events_checked"] == 0

    @pytest.mark.unit
    def test_events_have_hash_chain(self):
        """Each event references the previous event's hash."""
        AuditChainService.emit(
            event_type=AuditEventType.PLAN_CREATED,
            correlation_id="c1", org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
        )
        AuditChainService.emit(
            event_type=AuditEventType.EXECUTION_STARTED,
            correlation_id="c1", org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
        )

        assert _event_store[0].previous_hash == "genesis"
        assert _event_store[1].previous_hash != "genesis"
        assert _event_store[1].previous_hash != ""


# =============================================================================
# Query Capabilities
# =============================================================================


class TestQueryCapabilities:

    @pytest.mark.unit
    def test_query_by_event_type(self):
        """Can filter audit events by type."""
        AuditChainService.emit(
            event_type=AuditEventType.PLAN_CREATED,
            correlation_id="c1", org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
        )
        AuditChainService.emit(
            event_type=AuditEventType.EXECUTION_COMPLETED,
            correlation_id="c1", org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
        )

        plans = AuditChainService.query(
            org_id=ORG_A, event_type=AuditEventType.PLAN_CREATED)
        assert len(plans) == 1
        assert plans[0]["event_type"] == "plan_created"

    @pytest.mark.unit
    def test_query_by_tool(self):
        """Can filter by tool name."""
        AuditChainService.emit(
            event_type=AuditEventType.EXECUTION_COMPLETED,
            correlation_id="c1", org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor", tool="generate_image",
        )
        AuditChainService.emit(
            event_type=AuditEventType.EXECUTION_COMPLETED,
            correlation_id="c2", org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor", tool="train_lora",
        )

        results = AuditChainService.query(org_id=ORG_A, tool="train_lora")
        assert len(results) == 1

    @pytest.mark.unit
    def test_query_limit(self):
        """Query respects limit parameter."""
        for i in range(10):
            AuditChainService.emit(
                event_type=AuditEventType.PLAN_CREATED,
                correlation_id=f"c{i}", org_id=ORG_A,
                actor_user_id=USER_A, actor_role="editor",
            )

        results = AuditChainService.query(org_id=ORG_A, limit=3)
        assert len(results) == 3


# =============================================================================
# Correlation ID
# =============================================================================


class TestCorrelationId:

    @pytest.mark.unit
    def test_new_correlation_id_unique(self):
        """Each correlation ID is unique."""
        ids = {AuditChainService.new_correlation_id() for _ in range(100)}
        assert len(ids) == 100

    @pytest.mark.unit
    def test_correlation_id_format(self):
        """Correlation IDs have expected prefix."""
        cid = AuditChainService.new_correlation_id()
        assert cid.startswith("cor-")
        assert len(cid) > 10
