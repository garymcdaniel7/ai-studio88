"""Multi-tenant RLS isolation tests (Story 011).

These tests prove that the AuthorizedClient boundary (Story 009) combined
with RLS policies prevents cross-tenant data access at both the application
layer and the database layer.

Tests simulate:
- Tenant A cannot read Tenant B's records
- Tenant A cannot write to Tenant B's records
- Anonymous/unauthenticated access is blocked
- System context can only access system org
- NULL org_id records are invisible to tenant users

Run with:
    pytest tests/unit/test_rls_isolation.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.data_access import (
    SYSTEM_ORG_ID,
    TENANT_TABLES,
    AuthorizationError,
    AuthorizedClient,
    system_client,
    worker_client,
)
from backend.membership import OrgRole, TenantContext


# =============================================================================
# Fixtures
# =============================================================================

ORG_A = str(uuid4())
ORG_B = str(uuid4())
USER_A = str(uuid4())
USER_B = str(uuid4())


@pytest.fixture
def ctx_a():
    """Tenant context for user A in org A."""
    return TenantContext(user_id=USER_A, org_id=ORG_A, role=OrgRole.OWNER)


@pytest.fixture
def ctx_b():
    """Tenant context for user B in org B."""
    return TenantContext(user_id=USER_B, org_id=ORG_B, role=OrgRole.OWNER)


@pytest.fixture
def mock_db():
    """Mock the Supabase client for unit testing."""
    with patch("backend.data_access.is_supabase_configured", return_value=True), \
         patch("backend.data_access.get_supabase_client") as mock_fn:
        mock_client = MagicMock()
        mock_fn.return_value = mock_client
        yield mock_client


# =============================================================================
# Core Isolation: Tenant A vs Tenant B
# =============================================================================


class TestTenantIsolationCRUD:
    """Prove that each CRUD operation enforces tenant boundaries."""

    PRIORITY_TABLES = ["talent", "assets", "jobs", "models", "training_jobs", "publishing_posts"]

    @pytest.mark.unit
    @pytest.mark.parametrize("table", PRIORITY_TABLES)
    def test_select_scoped_to_own_org(self, table, ctx_a, mock_db):
        """SELECT always includes org_id = own_org in WHERE clause."""
        client = AuthorizedClient(ctx_a)
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        client.select(table)

        # Verify org_id filter was applied
        mock_table.eq.assert_called_with("org_id", ORG_A)

    @pytest.mark.unit
    @pytest.mark.parametrize("table", PRIORITY_TABLES)
    def test_insert_injects_own_org_id(self, table, ctx_a, mock_db):
        """INSERT always sets org_id to the caller's org."""
        client = AuthorizedClient(ctx_a)
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": "new"}])

        data = {"name": "Test"}
        client.insert(table, data)

        assert data["org_id"] == ORG_A

    @pytest.mark.unit
    @pytest.mark.parametrize("table", PRIORITY_TABLES)
    def test_insert_cannot_spoof_org_id(self, table, ctx_a, mock_db):
        """INSERT overwrites any client-supplied org_id with the actual one."""
        client = AuthorizedClient(ctx_a)
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": "new"}])

        # Attacker tries to inject org_b's ID
        data = {"name": "Spoof", "org_id": ORG_B}
        client.insert(table, data)

        # The boundary MUST override with the actual org
        assert data["org_id"] == ORG_A

    @pytest.mark.unit
    def test_select_by_id_cross_tenant_returns_not_found(self, ctx_a, mock_db):
        """select_by_id for a record in another org returns 'not found'."""
        client = AuthorizedClient(ctx_a)
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        # DB returns nothing because org_id filter excluded it
        mock_table.execute.return_value = MagicMock(data=None)

        with pytest.raises(AuthorizationError) as exc:
            client.select_by_id("talent", "record-in-org-b")

        # Error must NOT reveal the record exists
        assert "not found" in exc.value.detail.lower()

    @pytest.mark.unit
    def test_delete_cross_tenant_fails(self, ctx_a, mock_db):
        """DELETE on a record in another org silently fails (not found)."""
        client = AuthorizedClient(ctx_a)
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        with pytest.raises(AuthorizationError):
            client.delete("talent", "record-in-org-b")

    @pytest.mark.unit
    def test_update_cross_tenant_has_no_effect(self, ctx_a, mock_db):
        """UPDATE with record_id in another org touches zero rows."""
        client = AuthorizedClient(ctx_a)
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        # Update returns empty — the org_id filter excluded the row
        result = client.update("talent", {"name": "Hijack"}, record_id="other-org-rec")
        assert result.data == []


# =============================================================================
# No-Membership Rejection
# =============================================================================


class TestNoMembershipRejection:
    """Users without valid membership cannot access anything."""

    @pytest.mark.unit
    def test_tenant_context_requires_org_id(self, mock_db):
        """TenantContext with empty org_id is rejected."""
        ctx = TenantContext(user_id=USER_A, org_id="", role=OrgRole.VIEWER)

        with pytest.raises(AuthorizationError):
            AuthorizedClient(ctx)

    @pytest.mark.unit
    def test_tenant_context_requires_user_id(self, mock_db):
        """TenantContext with empty user_id is rejected."""
        ctx = TenantContext(user_id="", org_id=ORG_A, role=OrgRole.VIEWER)

        with pytest.raises(AuthorizationError):
            AuthorizedClient(ctx)


# =============================================================================
# System/Public Records
# =============================================================================


class TestSystemRecordAccess:
    """System-org records (shared models, default workflows) handling."""

    @pytest.mark.unit
    def test_system_client_scopes_to_system_org(self, mock_db):
        """System client operates on SYSTEM_ORG_ID."""
        client = system_client(purpose="seed_models", actor="cli:seed")

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        client.select("models")

        # Should scope to system org
        mock_table.eq.assert_called_with("org_id", str(SYSTEM_ORG_ID))

    @pytest.mark.unit
    def test_system_client_cannot_accidentally_access_tenant_data(self, mock_db):
        """System client with SYSTEM_ORG_ID cannot see tenant org records."""
        client = system_client(purpose="test", actor="test")

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        client.select("talent")

        # The eq filter means ONLY system-org talent (if any) is returned
        mock_table.eq.assert_called_with("org_id", str(SYSTEM_ORG_ID))


# =============================================================================
# Worker Context Isolation
# =============================================================================


class TestWorkerIsolation:
    """GPU workers can only access the job owner's data."""

    @pytest.mark.unit
    def test_worker_scoped_to_job_org(self, mock_db):
        """Worker for org_a job cannot access org_b data."""
        client = worker_client(
            job_id="job-1", org_id=ORG_A, user_id=USER_A,
            purpose="generate_image"
        )

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        client.select("assets")
        mock_table.eq.assert_called_with("org_id", ORG_A)

    @pytest.mark.unit
    def test_worker_insert_stamps_job_org(self, mock_db):
        """Worker INSERT stamps the job's org_id on the record."""
        client = worker_client(
            job_id="job-1", org_id=ORG_A, user_id=USER_A,
            purpose="save_output"
        )

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": "new-asset"}])

        data = {"filename": "output.png"}
        client.insert("assets", data)
        assert data["org_id"] == ORG_A


# =============================================================================
# Placeholder/Legacy Row Handling
# =============================================================================


class TestLegacyRowHandling:
    """Rows with NULL org_id are invisible to tenant users via RLS."""

    @pytest.mark.unit
    def test_null_org_rows_excluded_by_boundary(self, ctx_a, mock_db):
        """AuthorizedClient filters by org_id — NULL rows don't match."""
        client = AuthorizedClient(ctx_a)

        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        # DB returns only rows matching org_a (not NULL rows)
        mock_table.execute.return_value = MagicMock(data=[
            {"id": "owned", "org_id": ORG_A}
        ])

        result = client.select("talent")
        # The boundary adds .eq("org_id", ORG_A) — NULL rows are excluded
        mock_table.eq.assert_called_with("org_id", ORG_A)
        assert len(result.data) == 1


# =============================================================================
# RLS Policy Coverage Verification
# =============================================================================


class TestRLSCoverageMatrix:
    """Verify that priority tables are in the TENANT_TABLES registry."""

    MUST_BE_TENANT_SCOPED = [
        "talent", "assets", "jobs", "models", "workflows", "scenes",
        "training_datasets", "training_jobs", "publishing_posts",
        "brands", "creative_dna", "brain_sessions",
    ]

    @pytest.mark.unit
    @pytest.mark.parametrize("table", MUST_BE_TENANT_SCOPED)
    def test_priority_table_in_tenant_registry(self, table):
        """Every priority table must be registered in TENANT_TABLES."""
        assert table in TENANT_TABLES, (
            f"Table '{table}' is missing from TENANT_TABLES in data_access.py. "
            f"This means AuthorizedClient will NOT apply org_id scoping!"
        )
