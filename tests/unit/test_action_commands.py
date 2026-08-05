"""Backend Action Command Tests (Story 033).

Proves: idempotency, governance gating, tenant isolation,
duplicate submission prevention, status persistence, and lifecycle.

Run with:
    pytest tests/unit/test_action_commands.py -v
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytest

from backend.action_commands import (
    ActionCommand,
    ActionCommandService,
    CommandStatus,
    _command_store,
    _idempotency_index,
)

ORG_A = str(uuid4())
ORG_B = str(uuid4())
USER_A = str(uuid4())
SESSION = str(uuid4())


@pytest.fixture(autouse=True)
def clean():
    _command_store.clear()
    _idempotency_index.clear()
    yield
    _command_store.clear()
    _idempotency_index.clear()


# =============================================================================
# Idempotency
# =============================================================================


class TestIdempotency:

    @pytest.mark.unit
    def test_duplicate_idempotency_key_returns_existing(self):
        """Same idempotency key returns the same command (no duplicate execution)."""
        cmd1 = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="generate_image", parameters={"prompt": "test"},
            idempotency_key="key-123",
        )
        cmd2 = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="generate_image", parameters={"prompt": "test"},
            idempotency_key="key-123",
        )
        assert cmd1.id == cmd2.id  # Same command returned

    @pytest.mark.unit
    def test_different_keys_create_different_commands(self):
        """Different idempotency keys create separate commands."""
        cmd1 = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="generate_image", parameters={"prompt": "a"},
            idempotency_key="key-a",
        )
        cmd2 = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="generate_image", parameters={"prompt": "b"},
            idempotency_key="key-b",
        )
        assert cmd1.id != cmd2.id

    @pytest.mark.unit
    def test_completed_command_not_re_executed(self):
        """A completed command returned by idempotency is not re-processed."""
        cmd = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="generate_image", parameters={},
            idempotency_key="done-key",
        )
        cmd.status = CommandStatus.COMPLETED
        cmd.result = {"success": True}

        # propose_and_run with same key should return completed (not re-execute)
        result = ActionCommandService.propose_and_run(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="generate_image", parameters={},
            idempotency_key="done-key",
        )
        assert result.status == CommandStatus.COMPLETED


# =============================================================================
# Governance Gating
# =============================================================================


class TestGovernanceGating:

    @pytest.mark.unit
    def test_denied_action_not_executed(self):
        """Governance denial prevents execution."""
        with patch("backend.action_commands.ActionCommandService.evaluate_governance") as mock_gov:
            def deny(cmd):
                cmd.status = CommandStatus.DENIED
                cmd.governance_decision = "governance_unavailable"
                return cmd
            mock_gov.side_effect = deny

            result = ActionCommandService.propose_and_run(
                org_id=ORG_A, user_id=USER_A, session_id=SESSION,
                tool="launch_gpu", parameters={},
            )
            assert result.status == CommandStatus.DENIED
            assert result.result == {}  # Never executed

    @pytest.mark.unit
    def test_approval_required_pauses_execution(self):
        """Approval-required status pauses — no execution until human approves."""
        with patch("backend.action_commands.ActionCommandService.evaluate_governance") as mock_gov:
            def require_approval(cmd):
                cmd.status = CommandStatus.APPROVAL_REQUIRED
                cmd.governance_decision = "approval_required"
                return cmd
            mock_gov.side_effect = require_approval

            result = ActionCommandService.propose_and_run(
                org_id=ORG_A, user_id=USER_A, session_id=SESSION,
                tool="publish_post", parameters={},
            )
            assert result.status == CommandStatus.APPROVAL_REQUIRED
            assert result.result == {}

    @pytest.mark.unit
    def test_approved_action_executes(self):
        """Approved command proceeds to execution."""
        with patch("backend.action_commands.ActionCommandService.evaluate_governance") as mock_gov:
            def approve(cmd):
                cmd.status = CommandStatus.APPROVED
                cmd.governance_decision = "allowed"
                return cmd
            mock_gov.side_effect = approve

        with patch("backend.action_commands._execute_tool_sync", return_value={"success": True}):
            result = ActionCommandService.propose_and_run(
                org_id=ORG_A, user_id=USER_A, session_id=SESSION,
                tool="generate_image", parameters={"prompt": "test"},
            )
            assert result.status == CommandStatus.COMPLETED
            assert result.result == {"success": True}


# =============================================================================
# Tenant Isolation
# =============================================================================


class TestTenantIsolation:

    @pytest.mark.unit
    def test_get_command_wrong_org_returns_none(self):
        """Cannot retrieve another org's command."""
        cmd = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="generate_image", parameters={},
        )
        # Org B cannot see it
        assert ActionCommandService.get(cmd.id, ORG_B) is None
        # Org A can see it
        assert ActionCommandService.get(cmd.id, ORG_A) is not None

    @pytest.mark.unit
    def test_cancel_wrong_org_returns_none(self):
        """Cannot cancel another org's command."""
        cmd = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="train_lora", parameters={},
        )
        result = ActionCommandService.cancel(cmd.id, ORG_B)
        assert result is None

    @pytest.mark.unit
    def test_list_scoped_to_session_and_org(self):
        """list_for_session only returns own org's commands."""
        ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id="s1",
            tool="gen", parameters={},
        )
        ActionCommandService.propose(
            org_id=ORG_B, user_id="u-b", session_id="s1",
            tool="gen", parameters={},
        )
        results = ActionCommandService.list_for_session("s1", ORG_A)
        assert len(results) == 1
        assert results[0]["tool"] == "gen"


# =============================================================================
# Status Lifecycle
# =============================================================================


class TestStatusLifecycle:

    @pytest.mark.unit
    def test_propose_starts_as_proposed(self):
        """New command starts in PROPOSED status."""
        cmd = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="generate_image", parameters={},
        )
        assert cmd.status == CommandStatus.PROPOSED

    @pytest.mark.unit
    def test_execution_failure_sets_failed(self):
        """Failed execution transitions to FAILED status."""
        cmd = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="generate_image", parameters={},
        )
        cmd.status = CommandStatus.APPROVED

        with patch("backend.action_commands._execute_tool_sync", side_effect=RuntimeError("GPU offline")):
            cmd = ActionCommandService.execute(cmd)

        assert cmd.status == CommandStatus.FAILED
        assert "GPU offline" in cmd.error

    @pytest.mark.unit
    def test_cannot_execute_non_approved_command(self):
        """Only APPROVED commands can be executed."""
        cmd = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="generate_image", parameters={},
        )
        # Still in PROPOSED status
        with pytest.raises(ValueError, match="Cannot execute"):
            ActionCommandService.execute(cmd)

    @pytest.mark.unit
    def test_approve_then_execute(self):
        """Human approval transitions to APPROVED then executes."""
        cmd = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="publish_post", parameters={},
        )
        cmd.status = CommandStatus.APPROVAL_REQUIRED

        with patch("backend.action_commands._execute_tool_sync", return_value={"published": True}):
            result = ActionCommandService.approve(cmd.id)

        assert result.status == CommandStatus.COMPLETED
        assert result.result == {"published": True}

    @pytest.mark.unit
    def test_reject_sets_rejected(self):
        """Rejection transitions to REJECTED."""
        cmd = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="delete_asset", parameters={},
        )
        cmd.status = CommandStatus.APPROVAL_REQUIRED

        result = ActionCommandService.reject(cmd.id, "Not now")
        assert result.status == CommandStatus.REJECTED
        assert result.error == "Not now"

    @pytest.mark.unit
    def test_cancel_non_terminal_command(self):
        """Can cancel a command that's not yet executing or completed."""
        cmd = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="train_lora", parameters={},
        )
        result = ActionCommandService.cancel(cmd.id, ORG_A)
        assert result.status == CommandStatus.CANCELLED

    @pytest.mark.unit
    def test_cannot_cancel_completed_command(self):
        """Cannot cancel a completed command."""
        cmd = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="gen", parameters={},
        )
        cmd.status = CommandStatus.COMPLETED
        result = ActionCommandService.cancel(cmd.id, ORG_A)
        assert result.status == CommandStatus.COMPLETED  # Unchanged


# =============================================================================
# Status View (Client Safety)
# =============================================================================


class TestStatusView:

    @pytest.mark.unit
    def test_status_view_has_required_fields(self):
        """to_status_view() returns all observable fields."""
        cmd = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="generate_image", parameters={"prompt": "secret prompt"},
        )
        view = cmd.to_status_view()
        assert "id" in view
        assert "tool" in view
        assert "status" in view
        assert "is_terminal" in view
        assert view["tool"] == "generate_image"
        # Parameters NOT exposed in status view
        assert "parameters" not in view
        assert "secret prompt" not in str(view)

    @pytest.mark.unit
    def test_list_pending_shows_approval_required(self):
        """list_pending shows commands awaiting approval."""
        cmd = ActionCommandService.propose(
            org_id=ORG_A, user_id=USER_A, session_id=SESSION,
            tool="launch_gpu", parameters={},
        )
        cmd.status = CommandStatus.APPROVAL_REQUIRED

        pending = ActionCommandService.list_pending(ORG_A)
        assert len(pending) == 1
        assert pending[0]["status"] == "approval_required"
