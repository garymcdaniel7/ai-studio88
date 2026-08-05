"""Durable Approval Tests (Story 035).

Proves: single-use, expiry, argument binding, cross-tenant denial,
duplicate clicks, authorized approvers, replay prevention.

Run with:
    pytest tests/unit/test_approvals.py -v
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.approvals import (
    ApprovalService,
    ApprovalStatus,
    DurableApproval,
    PersistenceError,
    _approval_audit,
    _approval_store,
    compute_argument_hash,
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
SESSION = "session-1"


@pytest.fixture(autouse=True)
def clean():
    _approval_store.clear()
    _approval_audit.clear()
    _command_store.clear()
    _idempotency_index.clear()
    yield
    _approval_store.clear()
    _approval_audit.clear()
    _command_store.clear()
    _idempotency_index.clear()


def _create_bound_command(org_id=ORG_A, user_id=USER_A, tool="generate_image"):
    """Helper: create a command in APPROVAL_REQUIRED state."""
    cmd = ActionCommandService.propose(
        org_id=org_id, user_id=user_id, session_id=SESSION,
        tool=tool, parameters={"prompt": "test image"},
    )
    cmd.status = CommandStatus.APPROVAL_REQUIRED
    return cmd


# =============================================================================
# Single-Use (Consumed after execution)
# =============================================================================


class TestSingleUse:

    @pytest.mark.unit
    def test_approved_becomes_consumed(self):
        """After successful execution, status is CONSUMED (not re-usable)."""
        from unittest.mock import patch

        cmd = _create_bound_command()
        approval = ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="generate_image",
            parameters={"prompt": "test image"},
        )

        with patch("backend.action_commands._execute_tool_sync", return_value={"success": True}):
            result = ApprovalService.approve(
                approval_id=approval.id, approver_user_id=USER_A,
                approver_org_id=ORG_A, approver_role="owner",
            )

        assert result.status == ApprovalStatus.CONSUMED

    @pytest.mark.unit
    def test_duplicate_approve_returns_consumed_idempotent(self):
        """Second approve click on consumed approval returns same result."""
        from unittest.mock import patch

        cmd = _create_bound_command()
        approval = ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="generate_image",
            parameters={"prompt": "test image"},
        )

        with patch("backend.action_commands._execute_tool_sync", return_value={"done": True}):
            first = ApprovalService.approve(
                approval_id=approval.id, approver_user_id=USER_A,
                approver_org_id=ORG_A, approver_role="owner",
            )

        # Second click — same ID
        second = ApprovalService.approve(
            approval_id=approval.id, approver_user_id=USER_A,
            approver_org_id=ORG_A, approver_role="owner",
        )

        assert first.status == ApprovalStatus.CONSUMED
        assert second.status == ApprovalStatus.CONSUMED
        assert first.id == second.id  # Same record


# =============================================================================
# Expiry
# =============================================================================


class TestExpiry:

    @pytest.mark.unit
    def test_expired_approval_cannot_be_approved(self):
        """Expired approvals reject attempts."""
        cmd = _create_bound_command()
        approval = ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="gen", parameters={},
            expiry_hours=0,  # Expires immediately
        )
        # Force expiry by setting to past
        approval.expires_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        result = ApprovalService.approve(
            approval_id=approval.id, approver_user_id=USER_A,
            approver_org_id=ORG_A, approver_role="owner",
        )
        assert result.status == ApprovalStatus.EXPIRED

    @pytest.mark.unit
    def test_list_pending_excludes_expired(self):
        """Expired approvals don't appear in pending list."""
        cmd = _create_bound_command()
        approval = ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="gen", parameters={},
        )
        approval.expires_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        pending = ApprovalService.list_pending(ORG_A)
        assert len(pending) == 0


# =============================================================================
# Argument Binding
# =============================================================================


class TestArgumentBinding:

    @pytest.mark.unit
    def test_changed_arguments_invalidate(self):
        """If parameters changed since creation, approval is invalidated."""
        cmd = _create_bound_command()
        original_params = {"prompt": "original"}
        approval = ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="gen", parameters=original_params,
        )

        # Approve with different parameters
        result = ApprovalService.approve(
            approval_id=approval.id, approver_user_id=USER_A,
            approver_org_id=ORG_A, approver_role="owner",
            current_parameters={"prompt": "CHANGED"},
        )
        assert result.status == ApprovalStatus.INVALIDATED

    @pytest.mark.unit
    def test_same_arguments_pass_binding_check(self):
        """Matching arguments allow approval to proceed."""
        from unittest.mock import patch

        cmd = _create_bound_command()
        params = {"prompt": "test image"}
        approval = ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="generate_image", parameters=params,
        )

        with patch("backend.action_commands._execute_tool_sync", return_value={"ok": True}):
            result = ApprovalService.approve(
                approval_id=approval.id, approver_user_id=USER_A,
                approver_org_id=ORG_A, approver_role="owner",
                current_parameters=params,
            )
        assert result.status == ApprovalStatus.CONSUMED


# =============================================================================
# Cross-Tenant Isolation
# =============================================================================


class TestCrossTenantIsolation:

    @pytest.mark.unit
    def test_approve_wrong_org_returns_none(self):
        """Cannot approve another workspace's approval."""
        cmd = _create_bound_command(org_id=ORG_A)
        approval = ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="gen", parameters={},
        )

        result = ApprovalService.approve(
            approval_id=approval.id, approver_user_id=USER_B,
            approver_org_id=ORG_B, approver_role="owner",
        )
        assert result is None

    @pytest.mark.unit
    def test_get_wrong_org_returns_none(self):
        """Cannot view another workspace's approval."""
        cmd = _create_bound_command(org_id=ORG_A)
        approval = ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="gen", parameters={},
        )

        assert ApprovalService.get(approval.id, ORG_B) is None
        assert ApprovalService.get(approval.id, ORG_A) is not None

    @pytest.mark.unit
    def test_list_pending_scoped_to_org(self):
        """Pending list only shows own org's approvals."""
        cmd_a = _create_bound_command(org_id=ORG_A)
        cmd_b = _create_bound_command(org_id=ORG_B, user_id=USER_B)

        ApprovalService.create(
            command_id=cmd_a.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="gen", parameters={},
        )
        ApprovalService.create(
            command_id=cmd_b.id, org_id=ORG_B, requesting_user_id=USER_B,
            session_id=SESSION, tool="gen", parameters={},
        )

        assert len(ApprovalService.list_pending(ORG_A)) == 1
        assert len(ApprovalService.list_pending(ORG_B)) == 1


# =============================================================================
# Approver Authorization
# =============================================================================


class TestApproverAuthorization:

    @pytest.mark.unit
    def test_viewer_cannot_approve(self):
        """Viewer role is insufficient to approve."""
        cmd = _create_bound_command()
        approval = ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="gen", parameters={},
        )

        result = ApprovalService.approve(
            approval_id=approval.id, approver_user_id=USER_A,
            approver_org_id=ORG_A, approver_role="viewer",
        )
        assert result is None  # Denied

    @pytest.mark.unit
    def test_editor_can_approve(self):
        """Editor role is sufficient."""
        from unittest.mock import patch

        cmd = _create_bound_command()
        approval = ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="generate_image", parameters={"prompt": "test image"},
        )

        with patch("backend.action_commands._execute_tool_sync", return_value={"ok": True}):
            result = ApprovalService.approve(
                approval_id=approval.id, approver_user_id=USER_A,
                approver_org_id=ORG_A, approver_role="editor",
            )
        assert result.status == ApprovalStatus.CONSUMED


# =============================================================================
# Rejection
# =============================================================================


class TestRejection:

    @pytest.mark.unit
    def test_reject_is_terminal(self):
        """Rejected approval cannot be later approved."""
        cmd = _create_bound_command()
        approval = ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="gen", parameters={},
        )

        ApprovalService.reject(
            approval_id=approval.id, approver_user_id=USER_A,
            approver_org_id=ORG_A, approver_role="owner", reason="Not now",
        )

        # Try to approve after rejection
        result = ApprovalService.approve(
            approval_id=approval.id, approver_user_id=USER_A,
            approver_org_id=ORG_A, approver_role="owner",
        )
        assert result.status == ApprovalStatus.REJECTED  # Still rejected


# =============================================================================
# Audit
# =============================================================================


class TestAudit:

    @pytest.mark.unit
    def test_create_produces_audit(self):
        cmd = _create_bound_command()
        ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="gen", parameters={},
        )
        audit = ApprovalService.get_audit(ORG_A)
        assert any(e["action"] == "create" for e in audit)

    @pytest.mark.unit
    def test_approve_produces_audit(self):
        from unittest.mock import patch

        cmd = _create_bound_command()
        approval = ApprovalService.create(
            command_id=cmd.id, org_id=ORG_A, requesting_user_id=USER_A,
            session_id=SESSION, tool="generate_image", parameters={"prompt": "test image"},
        )

        with patch("backend.action_commands._execute_tool_sync", return_value={}):
            ApprovalService.approve(
                approval_id=approval.id, approver_user_id=USER_A,
                approver_org_id=ORG_A, approver_role="owner",
            )

        audit = ApprovalService.get_audit(ORG_A)
        assert any(e["action"] == "approve" for e in audit)


# =============================================================================
# Argument Hash
# =============================================================================


class TestArgumentHash:

    @pytest.mark.unit
    def test_same_params_same_hash(self):
        h1 = compute_argument_hash({"a": 1, "b": "two"})
        h2 = compute_argument_hash({"b": "two", "a": 1})  # Different order
        assert h1 == h2  # Canonical sort makes them equal

    @pytest.mark.unit
    def test_different_params_different_hash(self):
        h1 = compute_argument_hash({"prompt": "hello"})
        h2 = compute_argument_hash({"prompt": "world"})
        assert h1 != h2
