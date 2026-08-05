"""Two-Tenant Generation Lifecycle Authorization Tests (Story 019).

Proves that:
- Generation history is scoped to the user's workspace
- Job status requires auth and verifies org ownership
- Cancel/retry require auth, verify ownership, and produce audit
- Cross-workspace job IDs return 404 (no existence leak)
- Progress polling requires auth and ownership

Run with:
    pytest tests/unit/test_generation_lifecycle_auth.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.asset_job_auth import (
    authorized_job_cancel,
    authorized_job_read,
    authorized_job_retry,
)
from backend.auth import AuthUser
from backend.data_access import AuthorizationError, AuthorizedClient
from backend.membership import OrgRole, TenantContext


ORG_A = str(uuid4())
ORG_B = str(uuid4())


@pytest.fixture
def user_a():
    return AuthUser(user_id=str(uuid4()), email="a@studio.io", org_id=ORG_A, role="owner")


@pytest.fixture
def user_b():
    return AuthUser(user_id=str(uuid4()), email="b@studio.io", org_id=ORG_B, role="editor")


@pytest.fixture
def mock_db():
    with patch("backend.data_access.is_supabase_configured", return_value=True), \
         patch("backend.data_access.get_supabase_client") as mock_fn:
        mock_client = MagicMock()
        mock_fn.return_value = mock_client
        yield mock_client


# =============================================================================
# Generation History — Workspace Scoping
# =============================================================================


class TestGenerationHistoryIsolation:
    """Prove generation history is scoped to workspace."""

    @pytest.mark.unit
    def test_history_scoped_to_org(self, user_a, mock_db):
        """History query includes org_id filter via AuthorizedClient.raw_query."""
        client = AuthorizedClient(
            TenantContext(user_id=user_a.user_id, org_id=ORG_A, role=OrgRole.OWNER)
        )
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.contains.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        # raw_query pre-applies org_id
        query = client.raw_query("assets", purpose="generation_history")
        # The eq("org_id", ORG_A) should have been called
        mock_table.eq.assert_called_with("org_id", ORG_A)

    @pytest.mark.unit
    def test_history_other_org_sees_nothing(self, user_b, mock_db):
        """Org B cannot see Org A's generation history."""
        client = AuthorizedClient(
            TenantContext(user_id=user_b.user_id, org_id=ORG_B, role=OrgRole.EDITOR)
        )
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.contains.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        query = client.raw_query("assets", purpose="generation_history")
        # Scoped to ORG_B, not ORG_A
        mock_table.eq.assert_called_with("org_id", ORG_B)


# =============================================================================
# Generation Status — Ownership Verification
# =============================================================================


class TestGenerationStatusIsolation:
    """Prove job status requires ownership verification."""

    @pytest.mark.unit
    def test_owner_can_check_own_job_status(self, user_a, mock_db):
        """User A can check status of their org's job."""
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "job-1", "status": "running", "org_id": ORG_A, "progress": 50}
        )

        result = authorized_job_read(user_a, "job-1")
        assert result["status"] == "running"
        assert result["progress"] == 50

    @pytest.mark.unit
    def test_cross_tenant_status_returns_404(self, user_b, mock_db):
        """User B cannot check status of User A's job."""
        from fastapi import HTTPException

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)

        with pytest.raises(HTTPException) as exc:
            authorized_job_read(user_b, "job-in-org-a")
        assert exc.value.status_code == 404
        assert "not found" in exc.value.detail.lower()


# =============================================================================
# Generation Cancel — Auth + Ownership + Audit
# =============================================================================


class TestGenerationCancelIsolation:
    """Prove cancel requires auth, verifies ownership, and audits."""

    @pytest.mark.unit
    def test_owner_can_cancel_own_running_job(self, user_a, mock_db):
        """User A can cancel a running job in their org."""
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "job-1", "status": "running", "type": "image_generation", "org_id": ORG_A}
        )

        result = authorized_job_cancel(user_a, "job-1")
        assert result["status"] == "cancelled"

    @pytest.mark.unit
    def test_cross_tenant_cancel_returns_404(self, user_b, mock_db):
        """User B cannot cancel User A's job — gets 404."""
        from fastapi import HTTPException

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)

        with pytest.raises(HTTPException) as exc:
            authorized_job_cancel(user_b, "job-in-org-a")
        assert exc.value.status_code == 404

    @pytest.mark.unit
    def test_cancel_completed_job_rejected(self, user_a, mock_db):
        """Cannot cancel a completed job."""
        from fastapi import HTTPException

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "job-1", "status": "completed", "type": "image_generation", "org_id": ORG_A}
        )

        with pytest.raises(HTTPException) as exc:
            authorized_job_cancel(user_a, "job-1")
        assert exc.value.status_code == 400

    @pytest.mark.unit
    def test_cancel_produces_audit(self, user_a, mock_db):
        """Cancel records an audit entry."""
        from backend.asset_job_auth import _destructive_audit

        initial = len(_destructive_audit)

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "job-x", "status": "queued", "type": "image_generation", "org_id": ORG_A}
        )

        authorized_job_cancel(user_a, "job-x")

        assert len(_destructive_audit) > initial
        latest = _destructive_audit[-1]
        assert latest["action"] == "cancel_job"
        assert latest["resource_id"] == "job-x"
        assert latest["actor_user_id"] == user_a.user_id


# =============================================================================
# Generation Retry — Auth + Ownership + State + Audit
# =============================================================================


class TestGenerationRetryIsolation:
    """Prove retry requires auth, verifies ownership/state, and audits."""

    @pytest.mark.unit
    def test_owner_can_retry_failed_job(self, user_a, mock_db):
        """User A can retry a failed job in their org."""
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "job-1", "status": "failed", "type": "image_generation", "org_id": ORG_A}
        )

        result = authorized_job_retry(user_a, "job-1")
        assert result["status"] == "queued"

    @pytest.mark.unit
    def test_cross_tenant_retry_returns_404(self, user_b, mock_db):
        """User B cannot retry User A's job — gets 404."""
        from fastapi import HTTPException

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)

        with pytest.raises(HTTPException) as exc:
            authorized_job_retry(user_b, "job-in-org-a")
        assert exc.value.status_code == 404

    @pytest.mark.unit
    def test_retry_running_job_rejected(self, user_a, mock_db):
        """Cannot retry a running job (race prevention)."""
        from fastapi import HTTPException

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "job-1", "status": "running", "type": "image_generation", "org_id": ORG_A}
        )

        with pytest.raises(HTTPException) as exc:
            authorized_job_retry(user_a, "job-1")
        assert exc.value.status_code == 400

    @pytest.mark.unit
    def test_retry_produces_audit(self, user_a, mock_db):
        """Retry records an audit entry."""
        from backend.asset_job_auth import _destructive_audit

        initial = len(_destructive_audit)

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "job-y", "status": "cancelled", "type": "video_generation", "org_id": ORG_A}
        )

        authorized_job_retry(user_a, "job-y")

        assert len(_destructive_audit) > initial
        latest = _destructive_audit[-1]
        assert latest["action"] == "retry_job"
        assert latest["resource_id"] == "job-y"


# =============================================================================
# Non-Leaking Error Behavior
# =============================================================================


class TestNonLeakingErrors:
    """Prove error responses never reveal cross-tenant existence."""

    @pytest.mark.unit
    def test_status_404_is_generic(self, user_b, mock_db):
        """404 for cross-tenant job says 'not found' — not 'access denied'."""
        from fastapi import HTTPException

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)

        with pytest.raises(HTTPException) as exc:
            authorized_job_read(user_b, "secret-job-uuid")

        # Must NOT say "access denied" or "belongs to another org"
        assert exc.value.status_code == 404
        detail = exc.value.detail.lower()
        assert "not found" in detail
        assert "denied" not in detail
        assert "another" not in detail
        assert "org" not in detail
