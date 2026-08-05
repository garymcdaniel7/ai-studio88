"""Unit tests for the Authorized Data Access Boundary (Story 009).

Tests cover:
- TenantContext: authorized same-tenant read/write
- TenantContext: cross-tenant ID rejected
- TenantContext: insufficient role blocked
- SystemContext: system operations work with explicit scope
- WorkerContext: worker operations scoped correctly
- Missing purpose/request_id rejected
- Capability enforcement
- Audit trail recording

Run with:
    pytest tests/unit/test_data_access.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.data_access import (
    SYSTEM_ORG_ID,
    AuthorizationError,
    AuthorizedClient,
    SystemContext,
    WorkerContext,
    authorized_client,
    get_recent_audit_entries,
    system_client,
    worker_client,
)
from backend.membership import OrgRole, TenantContext


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def org_a():
    return str(uuid4())


@pytest.fixture
def org_b():
    return str(uuid4())


@pytest.fixture
def tenant_owner(org_a):
    return TenantContext(user_id=str(uuid4()), org_id=org_a, role=OrgRole.OWNER)


@pytest.fixture
def tenant_viewer(org_a):
    return TenantContext(user_id=str(uuid4()), org_id=org_a, role=OrgRole.VIEWER)


@pytest.fixture
def tenant_editor(org_a):
    return TenantContext(user_id=str(uuid4()), org_id=org_a, role=OrgRole.EDITOR)


@pytest.fixture
def tenant_other_org(org_b):
    return TenantContext(user_id=str(uuid4()), org_id=org_b, role=OrgRole.OWNER)


@pytest.fixture
def mock_supabase():
    with patch("backend.data_access.is_supabase_configured", return_value=True), \
         patch("backend.data_access.get_supabase_client") as mock_fn:
        mock_client = MagicMock()
        mock_fn.return_value = mock_client
        yield mock_client


# =============================================================================
# Tenant Context — Authorized Access
# =============================================================================


class TestTenantAuthorizedAccess:
    """Test that authorized same-tenant operations succeed."""

    @pytest.mark.unit
    def test_select_applies_org_id_filter(self, tenant_owner, mock_supabase):
        """SELECT on tenant table automatically scopes by org_id."""
        client = AuthorizedClient(tenant_owner)

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": "1"}])

        result = client.select("talent")

        # Verify org_id was applied
        mock_supabase.table.assert_called_with("talent")
        mock_table.select.assert_called_with("*")
        mock_table.eq.assert_called_with("org_id", tenant_owner.org_id)

    @pytest.mark.unit
    def test_insert_injects_org_id(self, tenant_editor, mock_supabase):
        """INSERT on tenant table automatically adds org_id to data."""
        client = AuthorizedClient(tenant_editor)

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": "new"}])

        data = {"name": "Test Talent"}
        client.insert("talent", data)

        # Verify org_id was injected
        assert data["org_id"] == tenant_editor.org_id
        mock_table.insert.assert_called_with(data)

    @pytest.mark.unit
    def test_delete_scopes_by_org_id(self, tenant_owner, mock_supabase):
        """DELETE checks both record_id AND org_id."""
        client = AuthorizedClient(tenant_owner)

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": "rec1"}])

        client.delete("talent", "rec1")

        # Verify BOTH id and org_id were applied
        calls = mock_table.eq.call_args_list
        call_args = [(c[0][0], c[0][1]) for c in calls]
        assert ("id", "rec1") in call_args
        assert ("org_id", tenant_owner.org_id) in call_args

    @pytest.mark.unit
    def test_update_scopes_by_org_id(self, tenant_editor, mock_supabase):
        """UPDATE applies org_id filter even when record_id is provided."""
        client = AuthorizedClient(tenant_editor)

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": "rec1"}])

        client.update("talent", {"name": "Updated"}, record_id="rec1")

        calls = mock_table.eq.call_args_list
        call_args = [(c[0][0], c[0][1]) for c in calls]
        assert ("id", "rec1") in call_args
        assert ("org_id", tenant_editor.org_id) in call_args


# =============================================================================
# Cross-Tenant Isolation
# =============================================================================


class TestCrossTenantIsolation:
    """Prove that privileged code cannot access another workspace's data."""

    @pytest.mark.unit
    def test_select_by_id_scoped_to_own_org(self, tenant_owner, tenant_other_org, mock_supabase):
        """A record in org_b cannot be accessed by a user in org_a."""
        client_a = AuthorizedClient(tenant_owner)

        # Simulate: record exists but belongs to org_b (org_id filter returns empty)
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)

        with pytest.raises(AuthorizationError) as exc_info:
            client_a.select_by_id("talent", "record-in-org-b")

        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_delete_fails_cross_tenant(self, tenant_owner, mock_supabase):
        """DELETE on a record in another org returns 'not found' (no data leak)."""
        client = AuthorizedClient(tenant_owner)

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])  # Empty = not found in this org

        with pytest.raises(AuthorizationError) as exc_info:
            client.delete("talent", "record-in-another-org")

        # Must NOT reveal that the record exists in another org
        assert "not found" in exc_info.value.detail.lower() or "denied" in exc_info.value.detail.lower()


# =============================================================================
# Role Enforcement
# =============================================================================


class TestRoleEnforcement:
    """Test that mutations require sufficient role."""

    @pytest.mark.unit
    def test_viewer_cannot_insert(self, tenant_viewer, mock_supabase):
        """Viewers cannot create records."""
        from fastapi import HTTPException

        client = AuthorizedClient(tenant_viewer)

        with pytest.raises(HTTPException) as exc_info:
            client.insert("talent", {"name": "Blocked"})

        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_viewer_cannot_delete(self, tenant_viewer, mock_supabase):
        """Viewers cannot delete records."""
        from fastapi import HTTPException

        client = AuthorizedClient(tenant_viewer)

        with pytest.raises(HTTPException) as exc_info:
            client.delete("talent", "some-id")

        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_viewer_can_select(self, tenant_viewer, mock_supabase):
        """Viewers CAN read records."""
        client = AuthorizedClient(tenant_viewer)

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        # Should NOT raise
        client.select("talent")

    @pytest.mark.unit
    def test_editor_can_insert(self, tenant_editor, mock_supabase):
        """Editors CAN create records."""
        client = AuthorizedClient(tenant_editor)

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": "new"}])

        # Should NOT raise
        client.insert("talent", {"name": "New Talent"})


# =============================================================================
# System Context
# =============================================================================


class TestSystemContext:
    """Test system operations with explicit scope."""

    @pytest.mark.unit
    def test_system_context_requires_purpose(self):
        """SystemContext without purpose is rejected."""
        with pytest.raises(AuthorizationError):
            ctx = SystemContext(purpose="", actor="test")
            AuthorizedClient(ctx)

    @pytest.mark.unit
    def test_system_context_requires_actor(self):
        """SystemContext without actor is rejected."""
        with pytest.raises(AuthorizationError):
            ctx = SystemContext(purpose="test_op", actor="")
            AuthorizedClient(ctx)

    @pytest.mark.unit
    def test_system_client_factory(self, mock_supabase):
        """system_client() factory creates valid AuthorizedClient."""
        client = system_client(
            purpose="seed_default_models",
            actor="cli:seed",
            target_org_id=str(SYSTEM_ORG_ID),
        )
        assert client.org_id == str(SYSTEM_ORG_ID)

    @pytest.mark.unit
    def test_system_can_write_without_role_check(self, mock_supabase):
        """System context bypasses role checks (it has no interactive role)."""
        client = system_client(purpose="seed", actor="cli:seed")

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": "new"}])

        # Should NOT raise (no role check for system context)
        client.insert("service_settings", {"key": "value"})


# =============================================================================
# Worker Context
# =============================================================================


class TestWorkerContext:
    """Test background worker operations."""

    @pytest.mark.unit
    def test_worker_context_requires_job_id(self):
        """WorkerContext without job_id is rejected."""
        with pytest.raises(AuthorizationError):
            ctx = WorkerContext(job_id="", org_id="org-1", user_id="u-1", purpose="gen")
            AuthorizedClient(ctx)

    @pytest.mark.unit
    def test_worker_context_requires_org_id(self):
        """WorkerContext without org_id is rejected."""
        with pytest.raises(AuthorizationError):
            ctx = WorkerContext(job_id="j-1", org_id="", user_id="u-1", purpose="gen")
            AuthorizedClient(ctx)

    @pytest.mark.unit
    def test_worker_scoped_to_job_org(self, org_a, mock_supabase):
        """Worker operations are scoped to the job's org_id."""
        client = worker_client(
            job_id="job-123",
            org_id=org_a,
            user_id="user-456",
            purpose="image_generation:flux_dev",
        )

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        client.select("assets")

        # Verify org_id scoping
        mock_table.eq.assert_called_with("org_id", org_a)


# =============================================================================
# Capability Enforcement
# =============================================================================


class TestCapabilityEnforcement:
    """Test that restricted contexts are limited to declared capabilities."""

    @pytest.mark.unit
    def test_worker_with_restricted_capabilities(self, org_a, mock_supabase):
        """Worker with explicit caps cannot access tables outside its scope."""
        client = worker_client(
            job_id="job-1",
            org_id=org_a,
            user_id="u-1",
            purpose="training",
            capabilities=frozenset({"select:training_jobs", "insert:training_jobs"}),
        )

        with pytest.raises(AuthorizationError) as exc_info:
            client.select("talent")  # Not in capabilities

        assert "lacks capability" in exc_info.value.detail

    @pytest.mark.unit
    def test_worker_with_allowed_capability(self, org_a, mock_supabase):
        """Worker with matching capability succeeds."""
        client = worker_client(
            job_id="job-1",
            org_id=org_a,
            user_id="u-1",
            purpose="training",
            capabilities=frozenset({"select:training_jobs", "insert:training_jobs"}),
        )

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        # Should NOT raise
        client.select("training_jobs")


# =============================================================================
# Audit Trail
# =============================================================================


class TestAuditTrail:
    """Test that operations are recorded for audit."""

    @pytest.mark.unit
    def test_operations_are_audited(self, tenant_owner, mock_supabase):
        """Each operation produces an audit entry."""
        from backend.data_access import _audit_log

        initial_count = len(_audit_log)

        client = AuthorizedClient(tenant_owner)

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        client.select("talent")

        assert len(_audit_log) > initial_count
        latest = _audit_log[-1]
        assert latest.table == "talent"
        assert latest.operation == "select"
        assert latest.authorized is True
        assert latest.org_id == tenant_owner.org_id


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and safety boundaries."""

    @pytest.mark.unit
    def test_update_without_id_or_filters_rejected(self, tenant_editor, mock_supabase):
        """UPDATE without record_id or filters is rejected (prevents mass updates)."""
        client = AuthorizedClient(tenant_editor)

        with pytest.raises(AuthorizationError) as exc_info:
            client.update("talent", {"name": "Mass Update"})

        assert "bulk unscoped" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_raw_query_requires_purpose(self, tenant_owner, mock_supabase):
        """raw_query() without purpose is rejected."""
        client = AuthorizedClient(tenant_owner)

        with pytest.raises(AuthorizationError) as exc_info:
            client.raw_query("talent", purpose="")

        assert "purpose" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_system_table_not_scoped(self, tenant_owner, mock_supabase):
        """System tables (service_settings) are NOT scoped by org_id."""
        client = AuthorizedClient(tenant_owner)

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        client.select("service_settings")

        # eq should NOT have been called (no org_id scoping)
        mock_table.eq.assert_not_called()
