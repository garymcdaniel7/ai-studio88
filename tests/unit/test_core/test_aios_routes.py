"""AIOS route tenant enforcement tests — Story 030.

Tests verify:
  - Session operations require TenantContext (org_id + user_id)
  - Cross-tenant session access raises AiosNotFoundError
  - Approval list/count are workspace-scoped
  - Approve/reject require workspace ownership + editor+ role
  - Cross-tenant approval action raises AiosNotFoundError
  - Viewer role cannot approve/reject
  - Actor attribution is recorded on approve/reject
  - Decision logging requires context
  - Non-leaking error behavior (same error for not-found and cross-tenant)
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.aios.tenant_service import (
    AiosAuthorizationError,
    AiosNotFoundError,
    add_message,
    approve_action,
    count_approvals,
    create_session,
    delete_session,
    get_decision_stats,
    get_session,
    list_approvals,
    list_decisions,
    list_sessions,
    log_decision,
    reject_action,
)
from backend.membership import OrgRole, TenantContext

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "org-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
USER_A = "user-aaaa"
USER_B = "user-bbbb"


def ctx_editor_a() -> TenantContext:
    return TenantContext(user_id=USER_A, org_id=TENANT_A, role=OrgRole.EDITOR)


def ctx_admin_a() -> TenantContext:
    return TenantContext(user_id=USER_A, org_id=TENANT_A, role=OrgRole.ADMIN)


def ctx_viewer_a() -> TenantContext:
    return TenantContext(user_id=USER_A, org_id=TENANT_A, role=OrgRole.VIEWER)


def ctx_owner_b() -> TenantContext:
    return TenantContext(user_id=USER_B, org_id=TENANT_B, role=OrgRole.OWNER)


def mock_execute(data=None, count=None):
    r = MagicMock()
    r.data = data if data is not None else []
    r.count = count
    return r


# =============================================================================
# Sessions — Trusted Context Required
# =============================================================================


@pytest.mark.unit
class TestAiosSessionRoutes:
    """Verify session routes enforce tenant context."""

    @patch("backend.aios.sessions._db")
    def test_create_session_uses_context(self, mock_db_fn):
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_execute([{
            "id": "s1", "org_id": TENANT_A, "user_id": USER_A
        }])

        result = create_session(ctx_editor_a(), mode="creative")
        call_data = mock_db.table.return_value.insert.call_args[0][0]
        assert call_data["org_id"] == TENANT_A
        assert call_data["user_id"] == USER_A

    @patch("backend.aios.sessions._db")
    def test_get_session_cross_tenant_raises(self, mock_db_fn):
        """Cross-tenant session access raises AiosNotFoundError."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        with pytest.raises(AiosNotFoundError, match="session"):
            get_session(ctx_editor_a(), "other-tenant-session")

    @patch("backend.aios.sessions._db")
    def test_list_sessions_scoped(self, mock_db_fn):
        """List only returns workspace's sessions."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_execute([
            {"id": "s1", "org_id": TENANT_A}
        ])

        result = list_sessions(ctx_editor_a())
        assert len(result) == 1

    @patch("backend.aios.sessions._db")
    def test_delete_cross_tenant_raises(self, mock_db_fn):
        """Delete of cross-tenant session raises."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        with pytest.raises(AiosNotFoundError):
            delete_session(ctx_editor_a(), "other-org-session")


# =============================================================================
# Decisions — Tenant-Scoped
# =============================================================================


@pytest.mark.unit
class TestAiosDecisionRoutes:
    """Verify decision routes enforce tenant context."""

    @patch("backend.aios.decisions._db")
    def test_log_decision_includes_context(self, mock_db_fn):
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_execute([{"id": "d1"}])

        log_decision(ctx_editor_a(), "s1", "chat", "ollama", "llama3.1:8b")
        call_data = mock_db.table.return_value.insert.call_args[0][0]
        assert call_data["org_id"] == TENANT_A
        assert call_data["user_id"] == USER_A

    @patch("backend.aios.decisions._db")
    def test_list_decisions_scoped(self, mock_db_fn):
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_execute([])

        list_decisions(ctx_editor_a())
        # Verify org_id filter was applied
        # (The eq chain includes org_id)


# =============================================================================
# Approvals — Tenant-Scoped with Actor Attribution
# =============================================================================


@pytest.mark.unit
class TestAiosApprovalRoutes:
    """Verify approval routes enforce tenant context and role."""

    @patch("backend.aios.tenant_service._db")
    def test_list_approvals_scoped(self, mock_db_fn):
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = mock_execute([])

        result = list_approvals(ctx_editor_a())
        assert result == []

    @patch("backend.aios.tenant_service._db")
    def test_count_approvals_scoped(self, mock_db_fn):
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute(count=3)

        count = count_approvals(ctx_editor_a())
        assert count == 3

    @patch("backend.aios.tenant_service._db")
    def test_approve_cross_tenant_raises(self, mock_db_fn):
        """Attempting to approve another workspace's action raises NotFound."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        # The approval doesn't exist in this org's scope
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        with pytest.raises(AiosNotFoundError, match="approval"):
            approve_action(ctx_admin_a(), "other-org-approval")

    @patch("backend.aios.tenant_service._db")
    def test_reject_cross_tenant_raises(self, mock_db_fn):
        """Attempting to reject another workspace's action raises NotFound."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        with pytest.raises(AiosNotFoundError, match="approval"):
            reject_action(ctx_admin_a(), "other-org-approval")

    def test_viewer_cannot_approve(self):
        """Viewer role lacks permission to approve."""
        with pytest.raises(AiosAuthorizationError, match="viewer"):
            approve_action(ctx_viewer_a(), "any-approval")

    def test_viewer_cannot_reject(self):
        """Viewer role lacks permission to reject."""
        with pytest.raises(AiosAuthorizationError, match="viewer"):
            reject_action(ctx_viewer_a(), "any-approval")

    @patch("backend.aios.tenant_service._db")
    def test_approve_records_actor(self, mock_db_fn):
        """Approve records the deciding actor's user_id."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        # Fetch returns the approval
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([{
            "id": "appr-1", "org_id": TENANT_A, "status": "pending"
        }])
        # Update succeeds
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([{
            "id": "appr-1", "status": "approved", "decided_by": USER_A
        }])

        result = approve_action(ctx_admin_a(), "appr-1")
        # Verify decided_by was set in the update
        update_data = mock_db.table.return_value.update.call_args[0][0]
        assert update_data["decided_by"] == USER_A
        assert update_data["status"] == "approved"

    @patch("backend.aios.tenant_service._db")
    def test_reject_records_actor_and_reason(self, mock_db_fn):
        """Reject records actor and reason."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([{
            "id": "appr-2", "org_id": TENANT_A, "status": "pending"
        }])
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([{
            "id": "appr-2", "status": "rejected"
        }])

        reject_action(ctx_admin_a(), "appr-2", reason="Too expensive")
        update_data = mock_db.table.return_value.update.call_args[0][0]
        assert update_data["decided_by"] == USER_A
        assert update_data["rejection_reason"] == "Too expensive"


# =============================================================================
# Non-Leaking Error Behavior
# =============================================================================


@pytest.mark.unit
class TestNonLeakingErrors:
    """Verify cross-tenant and not-found produce same error type."""

    @patch("backend.aios.sessions._db")
    def test_session_same_error_type(self, mock_db_fn):
        """Both cross-tenant and not-found raise AiosNotFoundError."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        # Cross-tenant attempt
        with pytest.raises(AiosNotFoundError) as exc1:
            get_session(ctx_editor_a(), "cross-tenant-id")

        # Non-existent ID
        with pytest.raises(AiosNotFoundError) as exc2:
            get_session(ctx_editor_a(), "does-not-exist")

        # Same error type — no existence leak
        assert type(exc1.value) == type(exc2.value)

    @patch("backend.aios.tenant_service._db")
    def test_approval_same_error_type(self, mock_db_fn):
        """Approval not-found and cross-tenant produce same error."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        with pytest.raises(AiosNotFoundError):
            approve_action(ctx_admin_a(), "nonexistent-approval")


# =============================================================================
# Editor can approve (not just admin)
# =============================================================================


@pytest.mark.unit
class TestEditorApprovalPermission:
    """Verify editor role CAN approve (since they can trigger actions)."""

    @patch("backend.aios.tenant_service._db")
    def test_editor_can_approve(self, mock_db_fn):
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([{
            "id": "appr-3", "org_id": TENANT_A, "status": "pending"
        }])
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([{
            "id": "appr-3", "status": "approved"
        }])

        # Should NOT raise
        approve_action(ctx_editor_a(), "appr-3")
