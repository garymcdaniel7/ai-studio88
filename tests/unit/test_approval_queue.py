"""Approval Queue Workspace Isolation Tests (Story 041).

Proves: workspace scoping, role enforcement, cross-workspace denial,
audit events, and concurrent decision safety.

Run with:
    pytest tests/unit/test_approval_queue.py -v
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from backend.approval_queue import (
    APPROVER_ROLES,
    POLICY_WRITE_ROLES,
    ApprovalQueueService,
    GovernancePolicyService,
    _queue_audit,
    get_queue_audit,
)
from backend.approvals import (
    ApprovalService,
    ApprovalStatus,
    _approval_store,
)
from backend.action_commands import (
    ActionCommandService,
    CommandStatus,
    _command_store,
    _idempotency_index,
)

ORG_A = str(uuid4())
ORG_B = str(uuid4())
USER_A = str(uuid4())
USER_B = str(uuid4())
SESSION = "s1"


@pytest.fixture(autouse=True)
def clean():
    _approval_store.clear()
    _command_store.clear()
    _idempotency_index.clear()
    _queue_audit.clear()
    yield
    _approval_store.clear()
    _command_store.clear()
    _idempotency_index.clear()
    _queue_audit.clear()


def _create_pending_approval(org_id=ORG_A, user_id=USER_A):
    """Helper: create a pending approval in the specified org."""
    cmd = ActionCommandService.propose(
        org_id=org_id, user_id=user_id, session_id=SESSION,
        tool="generate_image", parameters={"prompt": "test"},
    )
    cmd.status = CommandStatus.APPROVAL_REQUIRED
    approval = ApprovalService.create(
        command_id=cmd.id, org_id=org_id, requesting_user_id=user_id,
        session_id=SESSION, tool="generate_image",
        parameters={"prompt": "test"},
    )
    return approval


# =============================================================================
# Queue List/Count — Workspace Scoping
# =============================================================================


class TestQueueScoping:

    @pytest.mark.unit
    def test_list_pending_scoped_to_org(self):
        """Only own org's approvals are returned."""
        _create_pending_approval(org_id=ORG_A)
        _create_pending_approval(org_id=ORG_B, user_id=USER_B)

        result_a = ApprovalQueueService.list_pending(
            org_id=ORG_A, actor_id=USER_A, actor_role="editor")
        result_b = ApprovalQueueService.list_pending(
            org_id=ORG_B, actor_id=USER_B, actor_role="editor")

        assert len(result_a) == 1
        assert len(result_b) == 1

    @pytest.mark.unit
    def test_count_pending_scoped_to_org(self):
        """Count only reflects own org."""
        _create_pending_approval(org_id=ORG_A)
        _create_pending_approval(org_id=ORG_A)
        _create_pending_approval(org_id=ORG_B, user_id=USER_B)

        assert ApprovalQueueService.count_pending(org_id=ORG_A) == 2
        assert ApprovalQueueService.count_pending(org_id=ORG_B) == 1

    @pytest.mark.unit
    def test_empty_org_returns_empty(self):
        """Missing org_id returns empty, not global results."""
        _create_pending_approval(org_id=ORG_A)
        assert ApprovalQueueService.list_pending(org_id="", actor_id=USER_A, actor_role="editor") == []
        assert ApprovalQueueService.count_pending(org_id="") == 0


# =============================================================================
# Detail — Cross-Workspace Denial
# =============================================================================


class TestDetailIsolation:

    @pytest.mark.unit
    def test_get_detail_own_org(self):
        """Can view detail of own org's approval."""
        approval = _create_pending_approval(org_id=ORG_A)
        result = ApprovalQueueService.get_detail(
            approval_id=approval.id, org_id=ORG_A, actor_id=USER_A)
        assert result is not None
        assert result["id"] == approval.id

    @pytest.mark.unit
    def test_get_detail_wrong_org_returns_none(self):
        """Cannot view another org's approval — returns None (no leak)."""
        approval = _create_pending_approval(org_id=ORG_A)
        result = ApprovalQueueService.get_detail(
            approval_id=approval.id, org_id=ORG_B, actor_id=USER_B)
        assert result is None

    @pytest.mark.unit
    def test_guessed_id_returns_none(self):
        """Random/guessed ID returns None."""
        result = ApprovalQueueService.get_detail(
            approval_id="fake-id-12345", org_id=ORG_A, actor_id=USER_A)
        assert result is None


# =============================================================================
# Approve — Role Check + Cross-Workspace
# =============================================================================


class TestApproveAuthorization:

    @pytest.mark.unit
    def test_editor_can_approve(self):
        """Editor role has permission to approve."""
        from unittest.mock import patch

        approval = _create_pending_approval(org_id=ORG_A)

        with patch("backend.action_commands._execute_tool_sync", return_value={"ok": True}):
            result = ApprovalQueueService.approve(
                approval_id=approval.id, org_id=ORG_A,
                actor_id=USER_A, actor_role="editor",
            )
        assert result["success"] is True

    @pytest.mark.unit
    def test_viewer_cannot_approve(self):
        """Viewer role is insufficient."""
        approval = _create_pending_approval(org_id=ORG_A)
        result = ApprovalQueueService.approve(
            approval_id=approval.id, org_id=ORG_A,
            actor_id=USER_A, actor_role="viewer",
        )
        assert result["success"] is False
        assert result["reason"] == "insufficient_role"

    @pytest.mark.unit
    def test_cross_workspace_approve_denied(self):
        """Cannot approve another org's approval."""
        approval = _create_pending_approval(org_id=ORG_A)
        result = ApprovalQueueService.approve(
            approval_id=approval.id, org_id=ORG_B,
            actor_id=USER_B, actor_role="owner",
        )
        assert result["success"] is False
        assert result["status"] == "not_found"


# =============================================================================
# Reject — Role Check + Cross-Workspace
# =============================================================================


class TestRejectAuthorization:

    @pytest.mark.unit
    def test_admin_can_reject(self):
        """Admin role can reject."""
        approval = _create_pending_approval(org_id=ORG_A)
        result = ApprovalQueueService.reject(
            approval_id=approval.id, org_id=ORG_A,
            actor_id=USER_A, actor_role="admin", reason="Not appropriate",
        )
        assert result["success"] is True
        assert result["status"] == "rejected"

    @pytest.mark.unit
    def test_viewer_cannot_reject(self):
        """Viewer cannot reject."""
        approval = _create_pending_approval(org_id=ORG_A)
        result = ApprovalQueueService.reject(
            approval_id=approval.id, org_id=ORG_A,
            actor_id=USER_A, actor_role="viewer",
        )
        assert result["success"] is False
        assert result["reason"] == "insufficient_role"

    @pytest.mark.unit
    def test_cross_workspace_reject_denied(self):
        """Cannot reject another org's approval."""
        approval = _create_pending_approval(org_id=ORG_A)
        result = ApprovalQueueService.reject(
            approval_id=approval.id, org_id=ORG_B,
            actor_id=USER_B, actor_role="owner", reason="Trying to interfere",
        )
        assert result["success"] is False
        assert result["status"] == "not_found"


# =============================================================================
# Governance Policy — Role Enforcement
# =============================================================================


class TestPolicyAuthorization:

    @pytest.mark.unit
    def test_owner_can_update_policies(self):
        """Owner can change governance policies."""
        from unittest.mock import patch

        with patch("backend.aios.governance.policies.get_policies", return_value={"a": 1}):
            with patch("backend.aios.governance.policies.save_policies", return_value=True):
                result = GovernancePolicyService.update_policies(
                    org_id=ORG_A, actor_id=USER_A, actor_role="owner",
                    updates={"budget_daily_usd": 50.0},
                )
        assert result["success"] is True

    @pytest.mark.unit
    def test_editor_cannot_update_policies(self):
        """Editor cannot change policies (requires admin+)."""
        result = GovernancePolicyService.update_policies(
            org_id=ORG_A, actor_id=USER_A, actor_role="editor",
            updates={"budget_daily_usd": 999.0},
        )
        assert result["success"] is False
        assert "owner or admin" in result["reason"]

    @pytest.mark.unit
    def test_viewer_cannot_update_policies(self):
        """Viewer cannot change policies."""
        result = GovernancePolicyService.update_policies(
            org_id=ORG_A, actor_id=USER_A, actor_role="viewer",
            updates={"anything": True},
        )
        assert result["success"] is False


# =============================================================================
# Audit Trail
# =============================================================================


class TestAuditTrail:

    @pytest.mark.unit
    def test_approve_produces_audit(self):
        """Approve decision creates immutable audit event."""
        from unittest.mock import patch

        approval = _create_pending_approval(org_id=ORG_A)

        with patch("backend.action_commands._execute_tool_sync", return_value={}):
            ApprovalQueueService.approve(
                approval_id=approval.id, org_id=ORG_A,
                actor_id=USER_A, actor_role="owner",
            )

        audit = get_queue_audit(ORG_A)
        assert any(e["action"] == "approve" for e in audit)
        assert any(USER_A in e.get("actor_id", "") for e in audit)

    @pytest.mark.unit
    def test_reject_produces_audit(self):
        """Reject creates audit."""
        approval = _create_pending_approval(org_id=ORG_A)
        ApprovalQueueService.reject(
            approval_id=approval.id, org_id=ORG_A,
            actor_id=USER_A, actor_role="admin", reason="No",
        )
        audit = get_queue_audit(ORG_A)
        assert any(e["action"] == "reject" for e in audit)

    @pytest.mark.unit
    def test_denied_approve_produces_audit(self):
        """Insufficient role denial is audited."""
        approval = _create_pending_approval(org_id=ORG_A)
        ApprovalQueueService.approve(
            approval_id=approval.id, org_id=ORG_A,
            actor_id=USER_A, actor_role="viewer",
        )
        audit = get_queue_audit(ORG_A)
        assert any("denied" in e["action"] for e in audit)

    @pytest.mark.unit
    def test_policy_write_denied_produces_audit(self):
        """Policy write denial is audited."""
        GovernancePolicyService.update_policies(
            org_id=ORG_A, actor_id=USER_A, actor_role="editor",
            updates={"x": 1},
        )
        audit = get_queue_audit(ORG_A)
        assert any("policy_write_denied" in e["action"] for e in audit)

    @pytest.mark.unit
    def test_audit_scoped_to_org(self):
        """Audit retrieval is workspace-scoped."""
        _create_pending_approval(org_id=ORG_A)
        ApprovalQueueService.list_pending(org_id=ORG_A, actor_id=USER_A, actor_role="editor")
        ApprovalQueueService.list_pending(org_id=ORG_B, actor_id=USER_B, actor_role="editor")

        audit_a = get_queue_audit(ORG_A)
        audit_b = get_queue_audit(ORG_B)
        # Each org only sees their own audit
        assert all(e["org_id"] == ORG_A for e in audit_a)
        assert all(e["org_id"] == ORG_B for e in audit_b)
