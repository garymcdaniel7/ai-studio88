"""Durable deletion workflow tests — Story 070.

Tests prove:
  - Full purge workflow executes through all states
  - Duplicate requests are idempotent (return existing)
  - Cross-tenant access returns None (no existence leak)
  - Legal hold blocks purge
  - Dependency blocks purge
  - B2 failure makes targets retryable
  - Provider timeout makes targets retryable
  - Already-deleted resources are idempotent success
  - Retry advances failed targets
  - Cancel prevents further cleanup
  - Audit tombstones are never deleted
  - Reconciliation verifies all targets
  - Alerts raised on failure
"""

import pytest

from backend.deletion_workflow import (
    EntityType,
    InvalidStateError,
    PurgeState,
    TargetStatus,
    TargetType,
    _inject_failure,
    _reset_store,
    cancel_purge,
    check_eligibility,
    execute_cleanup,
    execute_full_purge,
    get_deletion_alerts,
    get_purge_request,
    list_purge_requests,
    persist_targets,
    reconcile,
    request_purge,
    retry_failed,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
ACTOR = "user-actor-001"
ENTITY = "entity-uuid-001"


# =============================================================================
# Full Workflow
# =============================================================================


@pytest.mark.unit
class TestFullWorkflow:

    def test_complete_purge_asset(self):
        result = execute_full_purge(ORG, ACTOR, EntityType.ASSET, ENTITY)
        assert result.state == PurgeState.PURGED
        assert result.completed_at is not None
        assert result.tombstone_preserved is True

    def test_complete_purge_talent(self):
        result = execute_full_purge(ORG, ACTOR, EntityType.TALENT, "talent-001")
        assert result.state == PurgeState.PURGED
        # Talent has DB + 2 B2 targets + audit
        assert len(result.targets) >= 4

    def test_complete_purge_job(self):
        result = execute_full_purge(ORG, ACTOR, EntityType.JOB, "job-001")
        assert result.state == PurgeState.PURGED
        # Job has DB + B2 outputs + provider + audit
        assert len(result.targets) >= 4

    def test_complete_purge_model(self):
        result = execute_full_purge(ORG, ACTOR, EntityType.MODEL, "model-001")
        assert result.state == PurgeState.PURGED


# =============================================================================
# Idempotency
# =============================================================================


@pytest.mark.unit
class TestIdempotency:

    def test_duplicate_request_returns_existing(self):
        r1 = request_purge(ORG, ACTOR, EntityType.ASSET, ENTITY)
        r2 = request_purge(ORG, ACTOR, EntityType.ASSET, ENTITY)
        assert r1.purge_id == r2.purge_id

    def test_already_deleted_resource_is_success(self):
        _inject_failure("already_deleted")
        result = execute_full_purge(ORG, ACTOR, EntityType.ASSET, ENTITY)
        # Already deleted = verified (idempotent)
        assert result.state == PurgeState.PURGED
        b2_targets = [t for t in result.targets if t.target_type == TargetType.B2_OBJECT]
        for t in b2_targets:
            assert t.status == TargetStatus.VERIFIED
            assert t.receipt == "already_deleted"


# =============================================================================
# Cross-Tenant Protection
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_get_returns_none(self):
        r = request_purge(ORG, ACTOR, EntityType.ASSET, ENTITY)
        # Different org trying to access
        result = get_purge_request(r.purge_id, "org-other")
        assert result is None

    def test_same_tenant_get_returns_request(self):
        r = request_purge(ORG, ACTOR, EntityType.ASSET, ENTITY)
        result = get_purge_request(r.purge_id, ORG)
        assert result is not None
        assert result.purge_id == r.purge_id

    def test_list_scoped_to_org(self):
        request_purge(ORG, ACTOR, EntityType.ASSET, "a1")
        request_purge("org-other", "user-2", EntityType.ASSET, "a2")
        results = list_purge_requests(ORG)
        assert len(results) == 1
        assert results[0].entity_id == "a1"


# =============================================================================
# Legal Hold & Dependencies
# =============================================================================


@pytest.mark.unit
class TestBlocking:

    def test_legal_hold_blocks_purge(self):
        _inject_failure("legal_hold")
        result = execute_full_purge(ORG, ACTOR, EntityType.ASSET, ENTITY)
        assert result.state == PurgeState.BLOCKED
        assert result.legal_hold is True
        assert "legal hold" in result.error.lower()

    def test_dependency_blocks_purge(self):
        _inject_failure("dependency")
        result = execute_full_purge(ORG, ACTOR, EntityType.ASSET, ENTITY)
        assert result.state == PurgeState.BLOCKED
        assert result.dependencies_clear is False

    def test_legal_hold_raises_alert(self):
        _inject_failure("legal_hold")
        execute_full_purge(ORG, ACTOR, EntityType.ASSET, ENTITY)
        alerts = get_deletion_alerts(ORG)
        assert any(a["type"] == "legal_hold_blocked" for a in alerts)


# =============================================================================
# Failure Injection & Retry
# =============================================================================


@pytest.mark.unit
class TestFailureAndRetry:

    def test_b2_failure_makes_request_failed(self):
        _inject_failure("b2")
        result = execute_full_purge(ORG, ACTOR, EntityType.ASSET, ENTITY)
        # B2 target failed, but DB target succeeded
        assert result.state == PurgeState.FAILED or result.has_failed_targets

    def test_provider_timeout_retryable(self):
        _inject_failure("provider")
        result = execute_full_purge(ORG, ACTOR, EntityType.JOB, "job-002")
        provider_targets = [t for t in result.targets if t.target_type == TargetType.PROVIDER_RESOURCE]
        for t in provider_targets:
            assert t.status == TargetStatus.FAILED
            assert t.is_retryable  # Under max attempts

    def test_retry_advances_failed_targets(self):
        _inject_failure("b2")
        result = execute_full_purge(ORG, ACTOR, EntityType.ASSET, "retry-entity")

        # Disable failure and retry
        _inject_failure("b2", enabled=False)
        result = retry_failed(result.purge_id)

        # Should now be reconciling or purged
        assert result.state in (PurgeState.RECONCILING, PurgeState.PURGED, PurgeState.CLEANING)

    def test_max_retries_exhausted(self):
        _inject_failure("b2")
        r = request_purge(ORG, ACTOR, EntityType.ASSET, "exhaust-entity")
        check_eligibility(r.purge_id)
        persist_targets(r.purge_id)

        # Execute 3 times to exhaust retries
        execute_cleanup(r.purge_id)  # attempt 1
        r = _reset_for_retry(r.purge_id)
        execute_cleanup(r.purge_id)  # attempt 2
        r = _reset_for_retry(r.purge_id)
        execute_cleanup(r.purge_id)  # attempt 3

        result = _get_for_test(r.purge_id)
        b2_targets = [t for t in result.targets if t.target_type == TargetType.B2_OBJECT]
        for t in b2_targets:
            assert t.attempts >= 3
            assert not t.is_retryable


# =============================================================================
# Cancel
# =============================================================================


@pytest.mark.unit
class TestCancel:

    def test_cancel_before_cleanup(self):
        r = request_purge(ORG, ACTOR, EntityType.ASSET, "cancel-entity")
        result = cancel_purge(r.purge_id, "user restored")
        assert result.state == PurgeState.CANCELLED

    def test_cancel_already_purged_is_noop(self):
        r = execute_full_purge(ORG, ACTOR, EntityType.ASSET, "done-entity")
        result = cancel_purge(r.purge_id)
        assert result.state == PurgeState.PURGED  # Unchanged

    def test_cancel_during_cleanup_raises(self):
        r = request_purge(ORG, ACTOR, EntityType.ASSET, "mid-entity")
        check_eligibility(r.purge_id)
        persist_targets(r.purge_id)
        # Manually set to cleaning
        from backend.deletion_workflow import _purge_store
        _purge_store[r.purge_id].state = PurgeState.CLEANING

        with pytest.raises(InvalidStateError):
            cancel_purge(r.purge_id)


# =============================================================================
# Audit Preservation
# =============================================================================


@pytest.mark.unit
class TestAuditPreservation:

    def test_audit_tombstone_never_deleted(self):
        result = execute_full_purge(ORG, ACTOR, EntityType.ASSET, ENTITY)
        audit_targets = [t for t in result.targets if t.target_type == TargetType.AUDIT_TOMBSTONE]
        assert len(audit_targets) > 0
        for t in audit_targets:
            assert t.status == TargetStatus.SKIPPED


# =============================================================================
# Reconciliation
# =============================================================================


@pytest.mark.unit
class TestReconciliation:

    def test_reconciliation_verifies_all_targets(self):
        result = execute_full_purge(ORG, ACTOR, EntityType.ASSET, ENTITY)
        assert result.state == PurgeState.PURGED
        non_audit = [t for t in result.targets if t.target_type != TargetType.AUDIT_TOMBSTONE]
        for t in non_audit:
            assert t.status == TargetStatus.VERIFIED


# =============================================================================
# Helpers
# =============================================================================


def _reset_for_retry(purge_id: str) -> "PurgeRequest":
    """Reset failed targets for re-execution in tests."""
    from backend.deletion_workflow import _purge_store
    r = _purge_store[purge_id]
    for t in r.targets:
        if t.status == TargetStatus.FAILED:
            t.status = TargetStatus.PENDING
    r.state = PurgeState.CLEANING
    return r


def _get_for_test(purge_id: str) -> "PurgeRequest":
    from backend.deletion_workflow import _purge_store
    return _purge_store[purge_id]
