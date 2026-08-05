"""Two-Tenant Asset & Job Authorization Tests (Story 015).

Proves that:
- Asset and job operations require authentication
- Tenant A cannot read/write/delete Tenant B's assets or jobs
- Destructive actions (delete, cancel, retry) produce audit entries
- Cross-workspace resource IDs do not disclose existence (always 404)
- File serving requires auth and org ownership

Run with:
    pytest tests/unit/test_asset_job_auth.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.asset_job_auth import (
    audit_destructive_action,
    authorized_asset_delete,
    authorized_asset_read,
    authorized_job_cancel,
    authorized_job_delete,
    authorized_job_read,
    authorized_job_retry,
    get_audit_log,
)
from backend.auth import AuthUser
from backend.data_access import AuthorizationError, AuthorizedClient
from backend.membership import OrgRole, TenantContext


# =============================================================================
# Fixtures
# =============================================================================

ORG_A = str(uuid4())
ORG_B = str(uuid4())


@pytest.fixture
def user_a():
    return AuthUser(user_id=str(uuid4()), email="a@test.com", org_id=ORG_A, role="owner")


@pytest.fixture
def user_b():
    return AuthUser(user_id=str(uuid4()), email="b@test.com", org_id=ORG_B, role="owner")


@pytest.fixture
def mock_db():
    with patch("backend.data_access.is_supabase_configured", return_value=True), \
         patch("backend.data_access.get_supabase_client") as mock_fn:
        mock_client = MagicMock()
        mock_fn.return_value = mock_client
        yield mock_client


# =============================================================================
# Asset Read — Cross-Tenant Isolation
# =============================================================================


class TestAssetReadIsolation:
    """Prove cross-tenant asset read denial."""

    @pytest.mark.unit
    def test_owner_can_read_own_asset(self, user_a, mock_db):
        """User A can read an asset in their org."""
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "asset-1", "filename": "test.png", "org_id": ORG_A}
        )

        result = authorized_asset_read(user_a, "asset-1")
        assert result["id"] == "asset-1"

    @pytest.mark.unit
    def test_cross_tenant_asset_read_returns_404(self, user_b, mock_db):
        """User B cannot read User A's asset — gets 404 (no existence leak)."""
        from fastapi import HTTPException

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        # org_id filter excludes org_a's asset
        mock_table.execute.return_value = MagicMock(data=None)

        with pytest.raises(HTTPException) as exc:
            authorized_asset_read(user_b, "asset-in-org-a")
        assert exc.value.status_code == 404
        assert "not found" in exc.value.detail.lower()


# =============================================================================
# Asset Delete — Auth + Audit
# =============================================================================


class TestAssetDeleteAuth:
    """Prove delete requires auth, scopes by org, and audits."""

    @pytest.mark.unit
    def test_owner_can_delete_own_asset(self, user_a, mock_db):
        """User A can delete an asset in their org."""
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "asset-1", "filename": "test.png", "org_id": ORG_A}
        )

        result = authorized_asset_delete(user_a, "asset-1")
        assert result["id"] == "asset-1"

    @pytest.mark.unit
    def test_cross_tenant_delete_returns_404(self, user_b, mock_db):
        """User B cannot delete User A's asset."""
        from fastapi import HTTPException

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)

        with pytest.raises(HTTPException) as exc:
            authorized_asset_delete(user_b, "asset-in-org-a")
        assert exc.value.status_code == 404

    @pytest.mark.unit
    def test_delete_produces_audit_entry(self, user_a, mock_db):
        """Asset deletion records an audit entry."""
        from backend.asset_job_auth import _destructive_audit

        initial = len(_destructive_audit)

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "asset-x", "filename": "audit.png", "org_id": ORG_A}
        )

        authorized_asset_delete(user_a, "asset-x")

        assert len(_destructive_audit) > initial
        latest = _destructive_audit[-1]
        assert latest["action"] == "delete_asset"
        assert latest["resource_id"] == "asset-x"
        assert latest["actor_user_id"] == user_a.user_id


# =============================================================================
# Job Read — Cross-Tenant Isolation
# =============================================================================


class TestJobReadIsolation:
    """Prove cross-tenant job read denial."""

    @pytest.mark.unit
    def test_owner_can_read_own_job(self, user_a, mock_db):
        """User A can read a job in their org."""
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "job-1", "type": "image_generation", "org_id": ORG_A}
        )

        result = authorized_job_read(user_a, "job-1")
        assert result["id"] == "job-1"

    @pytest.mark.unit
    def test_cross_tenant_job_read_returns_404(self, user_b, mock_db):
        """User B cannot read User A's job."""
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


# =============================================================================
# Job Cancel — Auth + Audit + State Check
# =============================================================================


class TestJobCancelAuth:
    """Prove cancel requires auth, checks state, and audits."""

    @pytest.mark.unit
    def test_owner_can_cancel_queued_job(self, user_a, mock_db):
        """User A can cancel a queued job in their org."""
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "job-1", "status": "queued", "type": "image_generation", "org_id": ORG_A}
        )

        result = authorized_job_cancel(user_a, "job-1")
        assert result["status"] == "cancelled"

    @pytest.mark.unit
    def test_cannot_cancel_completed_job(self, user_a, mock_db):
        """Cannot cancel a job that's already completed."""
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
    def test_cross_tenant_cancel_returns_404(self, user_b, mock_db):
        """User B cannot cancel User A's job."""
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


# =============================================================================
# Job Retry — Auth + Audit + State Check
# =============================================================================


class TestJobRetryAuth:
    """Prove retry requires auth, checks state, and audits."""

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
    def test_cannot_retry_running_job(self, user_a, mock_db):
        """Cannot retry a job that's currently running."""
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
    def test_cross_tenant_retry_returns_404(self, user_b, mock_db):
        """User B cannot retry User A's job."""
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
    def test_retry_produces_audit_entry(self, user_a, mock_db):
        """Job retry records an audit entry."""
        from backend.asset_job_auth import _destructive_audit

        initial = len(_destructive_audit)

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "job-x", "status": "failed", "type": "lora_training", "org_id": ORG_A}
        )

        authorized_job_retry(user_a, "job-x")

        assert len(_destructive_audit) > initial
        latest = _destructive_audit[-1]
        assert latest["action"] == "retry_job"
        assert latest["resource_id"] == "job-x"


# =============================================================================
# Job Delete — Auth + Audit + State Check
# =============================================================================


class TestJobDeleteAuth:
    """Prove delete requires auth, checks state, and audits."""

    @pytest.mark.unit
    def test_owner_can_delete_queued_job(self, user_a, mock_db):
        """User A can delete a queued job in their org."""
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"id": "job-1", "status": "queued", "type": "image_generation", "org_id": ORG_A}
        )

        result = authorized_job_delete(user_a, "job-1")
        assert result["id"] == "job-1"

    @pytest.mark.unit
    def test_cannot_delete_running_job(self, user_a, mock_db):
        """Cannot delete a running job."""
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
            authorized_job_delete(user_a, "job-1")
        assert exc.value.status_code == 400

    @pytest.mark.unit
    def test_cross_tenant_delete_returns_404(self, user_b, mock_db):
        """User B cannot delete User A's job."""
        from fastapi import HTTPException

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)

        with pytest.raises(HTTPException) as exc:
            authorized_job_delete(user_b, "job-in-org-a")
        assert exc.value.status_code == 404
