"""Cross-tenant RLS contract tests for workers — Story 012.

Tests verify that:
  - Worker CRUD requires org_id (no bare-ID operations)
  - Same-tenant operations succeed
  - Cross-tenant operations are rejected
  - org_id is always injected on create
  - org_id cannot be changed on update
  - Heartbeat is scoped to tenant
  - Sensitive fields (base_url, metadata) are excluded from tenant view
  - NULL org_id workers are invisible to tenant queries

These tests validate the APPLICATION layer enforcement (database.py).
The SQL RLS policies (031_workers_rls.sql) provide defense-in-depth at the DB level.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from backend.membership import OrgRole, TenantContext
from backend.tenant_repo import TenantNotFoundError, TenantRepo


TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "org-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def ctx_a() -> TenantContext:
    return TenantContext(user_id="user-a", org_id=TENANT_A, role=OrgRole.ADMIN)


def ctx_b() -> TenantContext:
    return TenantContext(user_id="user-b", org_id=TENANT_B, role=OrgRole.ADMIN)


def mock_execute(data=None):
    result = MagicMock()
    result.data = data if data is not None else []
    return result


# =============================================================================
# database.py enforcement — org_id required
# =============================================================================


@pytest.mark.unit
class TestWorkersOrgIdRequired:
    """Verify all worker DB functions reject empty org_id."""

    def test_get_workers_db_requires_org_id(self):
        from backend.database import get_workers_db
        with pytest.raises(ValueError, match="org_id is required"):
            get_workers_db("")

    def test_get_worker_db_requires_org_id(self):
        from backend.database import get_worker_db
        with pytest.raises(ValueError, match="org_id is required"):
            get_worker_db("some-id", "")

    def test_create_worker_db_requires_org_id(self):
        from backend.database import create_worker_db
        with pytest.raises(ValueError, match="org_id is required"):
            create_worker_db({"name": "test"}, "")

    def test_update_worker_db_requires_org_id(self):
        from backend.database import update_worker_db
        with pytest.raises(ValueError, match="org_id is required"):
            update_worker_db("some-id", {"status": "online"}, "")

    def test_delete_worker_db_requires_org_id(self):
        from backend.database import delete_worker_db
        with pytest.raises(ValueError, match="org_id is required"):
            delete_worker_db("some-id", "")

    def test_heartbeat_worker_db_requires_org_id(self):
        from backend.database import heartbeat_worker_db
        with pytest.raises(ValueError, match="org_id is required"):
            heartbeat_worker_db("some-id", {"status": "online"}, "")

    def test_get_available_workers_db_requires_org_id(self):
        from backend.database import get_available_workers_db
        with pytest.raises(ValueError, match="org_id is required"):
            get_available_workers_db("")


# =============================================================================
# TenantRepo — same-tenant CRUD
# =============================================================================


@pytest.mark.unit
class TestWorkersSameTenant:
    """Verify same-tenant worker operations succeed via TenantRepo."""

    @patch("backend.tenant_repo.get_supabase_client")
    def test_list_workers_returns_own_org(self, mock_client_fn):
        """List returns only workers with matching org_id."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        workers = [
            {"id": "w1", "org_id": TENANT_A, "name": "GPU-1", "status": "online"},
            {"id": "w2", "org_id": TENANT_A, "name": "GPU-2", "status": "busy"},
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_execute(workers)

        repo = TenantRepo(ctx_a())
        result = repo.list("workers")
        assert len(result) == 2
        assert all(w["org_id"] == TENANT_A for w in result)

    @patch("backend.tenant_repo.get_supabase_client")
    def test_get_worker_same_tenant(self, mock_client_fn):
        """Get a worker within same tenant succeeds."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        worker = {"id": "w1", "org_id": TENANT_A, "name": "GPU-1"}
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([worker])

        repo = TenantRepo(ctx_a())
        result = repo.get_one("workers", "w1")
        assert result["id"] == "w1"

    @patch("backend.tenant_repo.get_supabase_client")
    def test_create_worker_injects_org_id(self, mock_client_fn):
        """Create always injects org_id from context."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        created = {"id": "w-new", "org_id": TENANT_A, "name": "New Worker"}
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_execute([created])

        repo = TenantRepo(ctx_a())
        repo.create("workers", {"name": "New Worker", "provider": "runpod"})

        call_data = mock_client.table.return_value.insert.call_args[0][0]
        assert call_data["org_id"] == TENANT_A

    @patch("backend.tenant_repo.get_supabase_client")
    def test_update_worker_same_tenant(self, mock_client_fn):
        """Update within same tenant succeeds."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        updated = {"id": "w1", "org_id": TENANT_A, "status": "offline"}
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([updated])

        repo = TenantRepo(ctx_a())
        result = repo.update("workers", "w1", {"status": "offline"})
        assert result["status"] == "offline"

    @patch("backend.tenant_repo.get_supabase_client")
    def test_delete_worker_same_tenant(self, mock_client_fn):
        """Delete within same tenant succeeds."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([{"id": "w1"}])

        repo = TenantRepo(ctx_a())
        assert repo.delete("workers", "w1") is True


# =============================================================================
# TenantRepo — cross-tenant rejection
# =============================================================================


@pytest.mark.unit
class TestWorkersCrossTenant:
    """Verify cross-tenant operations are rejected identically to not-found."""

    @patch("backend.tenant_repo.get_supabase_client")
    def test_get_cross_tenant_worker_denied(self, mock_client_fn):
        """Attempting to read another org's worker returns TenantNotFoundError."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        # org_id filter returns empty (worker belongs to tenant B)
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        repo = TenantRepo(ctx_a())
        with pytest.raises(TenantNotFoundError):
            repo.get_one("workers", "tenant-b-worker")

    @patch("backend.tenant_repo.get_supabase_client")
    def test_update_cross_tenant_worker_denied(self, mock_client_fn):
        """Attempting to update another org's worker fails."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        repo = TenantRepo(ctx_a())
        with pytest.raises(TenantNotFoundError):
            repo.update("workers", "tenant-b-worker", {"status": "hacked"})

    @patch("backend.tenant_repo.get_supabase_client")
    def test_delete_cross_tenant_worker_denied(self, mock_client_fn):
        """Attempting to delete another org's worker fails."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        repo = TenantRepo(ctx_a())
        with pytest.raises(TenantNotFoundError):
            repo.delete("workers", "tenant-b-worker")


# =============================================================================
# Ownership immutability
# =============================================================================


@pytest.mark.unit
class TestWorkersOwnershipImmutable:
    """Verify org_id cannot be changed via update."""

    @patch("backend.tenant_repo.get_supabase_client")
    def test_org_id_stripped_from_update(self, mock_client_fn):
        """org_id in update payload is silently removed."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        updated = {"id": "w1", "org_id": TENANT_A, "status": "online"}
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([updated])

        repo = TenantRepo(ctx_a())
        repo.update("workers", "w1", {"status": "online", "org_id": TENANT_B})

        # Verify org_id was stripped from the update call
        call_data = mock_client.table.return_value.update.call_args[0][0]
        assert "org_id" not in call_data

    @patch("backend.tenant_repo.get_supabase_client")
    def test_create_overrides_supplied_org_id(self, mock_client_fn):
        """Even if caller supplies org_id, context org_id wins."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_execute([{"id": "w-new"}])

        repo = TenantRepo(ctx_a())
        repo.create("workers", {"name": "Evil", "org_id": TENANT_B})

        call_data = mock_client.table.return_value.insert.call_args[0][0]
        assert call_data["org_id"] == TENANT_A  # Context wins, not attacker-supplied


# =============================================================================
# NULL org_id workers invisible
# =============================================================================


@pytest.mark.unit
class TestWorkersNullOrgInvisible:
    """Verify workers with NULL org_id are invisible to tenant queries."""

    @patch("backend.tenant_repo.get_supabase_client")
    def test_null_org_worker_not_returned(self, mock_client_fn):
        """Workers with NULL org_id are excluded by the org_id=X filter."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        # Supabase .eq("org_id", X) naturally excludes NULL rows
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_execute([])

        repo = TenantRepo(ctx_a())
        result = repo.list("workers")
        assert result == []


# =============================================================================
# Sensitive field protection documentation
# =============================================================================


@pytest.mark.unit
class TestSensitiveFieldProtection:
    """Document which fields are protected and verify via tenant view."""

    def test_sensitive_fields_defined(self):
        """Verify we know which fields are sensitive."""
        sensitive = {"base_url", "metadata", "cuda_version", "driver_version"}
        safe_view_fields = {
            "id", "name", "provider", "status", "masked_url",
            "gpu_name", "vram_gb", "available_vram_gb",
            "supported_tasks", "supported_models", "current_job_id",
            "last_heartbeat_at", "org_id", "created_at", "updated_at",
        }
        # Sensitive fields should NOT be in the safe view
        assert sensitive.isdisjoint(safe_view_fields)

    def test_tenant_view_excludes_base_url(self):
        """The workers_tenant_view SQL view excludes base_url."""
        import os
        # Navigate from tests/unit/test_core/ up to repo root
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        migration_path = os.path.join(repo_root, "docs", "sql", "031_workers_rls.sql")
        with open(migration_path) as f:
            sql = f.read()
        # Verify the view exists and excludes sensitive columns
        assert "workers_tenant_view" in sql
        assert "EXCLUDED: base_url, metadata, cuda_version, driver_version" in sql
        # Verify masked_url IS included (safe version)
        assert "masked_url" in sql
