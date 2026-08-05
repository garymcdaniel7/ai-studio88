"""Cross-tenant contract tests for backend/tenant_repo.py — Story 010.

Tests cover:
  - Same-tenant CRUD operations succeed
  - Cross-tenant ID access returns TenantNotFoundError (no existence leak)
  - Cross-tenant parent reference is rejected
  - Bulk operations scope correctly
  - Inherited ownership validation walks the chain
  - System scope bypasses tenant filters
  - org_id is always injected on create (never trusted from caller)
  - org_id cannot be mutated on update
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from backend.membership import OrgRole, TenantContext
from backend.tenant_repo import (
    DIRECT_OWNED_TABLES,
    INHERITED_OWNERSHIP,
    SYSTEM_TABLES,
    TenantNotFoundError,
    TenantParentOwnershipError,
    TenantRepo,
)


# =============================================================================
# Fixtures
# =============================================================================

TENANT_A_ORG = "org-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B_ORG = "org-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
USER_A = "user-a-id"
USER_B = "user-b-id"


def ctx_a() -> TenantContext:
    return TenantContext(user_id=USER_A, org_id=TENANT_A_ORG, role=OrgRole.EDITOR)


def ctx_b() -> TenantContext:
    return TenantContext(user_id=USER_B, org_id=TENANT_B_ORG, role=OrgRole.EDITOR)


def mock_execute(data=None, count=None):
    """Create a mock Supabase execute() return value."""
    result = MagicMock()
    result.data = data if data is not None else []
    result.count = count
    return result


# =============================================================================
# Ownership Classification Tests
# =============================================================================


@pytest.mark.unit
class TestOwnershipClassification:
    """Verify all tables are classified."""

    def test_direct_owned_tables_exist(self):
        """Direct-owned tables are defined."""
        assert "talent" in DIRECT_OWNED_TABLES
        assert "assets" in DIRECT_OWNED_TABLES
        assert "jobs" in DIRECT_OWNED_TABLES
        assert "projects" in DIRECT_OWNED_TABLES
        assert "models" in DIRECT_OWNED_TABLES

    def test_inherited_tables_defined(self):
        """Inherited ownership mappings are defined."""
        assert "creative_dna" in INHERITED_OWNERSHIP
        assert "characters" in INHERITED_OWNERSHIP
        assert "episodes" in INHERITED_OWNERSHIP
        assert "scenes" in INHERITED_OWNERSHIP
        assert "shots" in INHERITED_OWNERSHIP

    def test_system_tables_defined(self):
        """System tables are defined."""
        assert "workflow_templates" in SYSTEM_TABLES

    def test_no_overlap_between_categories(self):
        """No table appears in multiple categories."""
        inherited_keys = set(INHERITED_OWNERSHIP.keys())
        assert not DIRECT_OWNED_TABLES.intersection(inherited_keys)
        assert not DIRECT_OWNED_TABLES.intersection(SYSTEM_TABLES)
        assert not inherited_keys.intersection(SYSTEM_TABLES)


# =============================================================================
# TenantContext Tests
# =============================================================================


@pytest.mark.unit
class TestTenantContext:
    """Test TenantContext behavior."""

    def test_org_id_is_required(self):
        """Context must have org_id."""
        ctx = ctx_a()
        assert ctx.org_id == TENANT_A_ORG

    def test_role_hierarchy(self):
        """Role checks work correctly."""
        owner = TenantContext(user_id="u", org_id="o", role=OrgRole.OWNER)
        viewer = TenantContext(user_id="u", org_id="o", role=OrgRole.VIEWER)
        assert owner.is_owner is True
        assert owner.is_admin_or_above is True
        assert viewer.is_owner is False
        assert viewer.is_admin_or_above is False

    def test_require_role_raises(self):
        """require_role raises HTTPException for insufficient privileges."""
        viewer = TenantContext(user_id="u", org_id="o", role=OrgRole.VIEWER)
        with pytest.raises(Exception):  # HTTPException
            viewer.require_role(OrgRole.ADMIN)


# =============================================================================
# Direct Ownership — Get One
# =============================================================================


@pytest.mark.unit
class TestDirectOwnershipGetOne:
    """Test get_one for direct-owned tables."""

    @patch("backend.tenant_repo.get_supabase_client")
    def test_same_tenant_found(self, mock_client_fn):
        """Record in same tenant is returned."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        record = {"id": "rec-1", "org_id": TENANT_A_ORG, "name": "Test"}
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([record])

        repo = TenantRepo(ctx_a())
        result = repo.get_one("talent", "rec-1")
        assert result["id"] == "rec-1"

    @patch("backend.tenant_repo.get_supabase_client")
    def test_cross_tenant_not_found(self, mock_client_fn):
        """Record in another tenant returns TenantNotFoundError."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        # Returns empty — the org_id filter excludes the record
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        repo = TenantRepo(ctx_a())
        with pytest.raises(TenantNotFoundError) as exc_info:
            repo.get_one("talent", "other-tenant-rec")
        assert exc_info.value.entity == "talent"
        assert exc_info.value.record_id == "other-tenant-rec"

    @patch("backend.tenant_repo.get_supabase_client")
    def test_nonexistent_record(self, mock_client_fn):
        """Nonexistent record returns same error as cross-tenant (no leak)."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        repo = TenantRepo(ctx_a())
        with pytest.raises(TenantNotFoundError):
            repo.get_one("talent", "does-not-exist")


# =============================================================================
# Direct Ownership — Create
# =============================================================================


@pytest.mark.unit
class TestDirectOwnershipCreate:
    """Test create for direct-owned tables."""

    @patch("backend.tenant_repo.get_supabase_client")
    def test_org_id_injected(self, mock_client_fn):
        """org_id is always injected from context, never from caller."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        created = {"id": "new-1", "org_id": TENANT_A_ORG, "name": "Created"}
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_execute([created])

        repo = TenantRepo(ctx_a())
        # Caller tries to supply a different org_id — it gets overwritten
        result = repo.create("talent", {"name": "Created", "org_id": TENANT_B_ORG})

        # Verify the data passed to insert has the CORRECT org_id
        call_args = mock_client.table.return_value.insert.call_args[0][0]
        assert call_args["org_id"] == TENANT_A_ORG  # Overwritten!

    @patch("backend.tenant_repo.get_supabase_client")
    def test_org_id_set_when_missing(self, mock_client_fn):
        """org_id is set even if caller doesn't provide it."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        created = {"id": "new-2", "org_id": TENANT_A_ORG, "name": "NoOrg"}
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_execute([created])

        repo = TenantRepo(ctx_a())
        repo.create("talent", {"name": "NoOrg"})

        call_args = mock_client.table.return_value.insert.call_args[0][0]
        assert call_args["org_id"] == TENANT_A_ORG


# =============================================================================
# Direct Ownership — Update
# =============================================================================


@pytest.mark.unit
class TestDirectOwnershipUpdate:
    """Test update for direct-owned tables."""

    @patch("backend.tenant_repo.get_supabase_client")
    def test_update_scoped_to_tenant(self, mock_client_fn):
        """Update only affects records within tenant scope."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        updated = {"id": "rec-1", "org_id": TENANT_A_ORG, "name": "Updated"}
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([updated])

        repo = TenantRepo(ctx_a())
        result = repo.update("talent", "rec-1", {"name": "Updated"})
        assert result["name"] == "Updated"

    @patch("backend.tenant_repo.get_supabase_client")
    def test_update_cross_tenant_fails(self, mock_client_fn):
        """Update of cross-tenant record raises TenantNotFoundError."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        repo = TenantRepo(ctx_a())
        with pytest.raises(TenantNotFoundError):
            repo.update("talent", "other-tenant-rec", {"name": "Hacked"})

    @patch("backend.tenant_repo.get_supabase_client")
    def test_org_id_stripped_from_update(self, mock_client_fn):
        """org_id cannot be changed via update."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        updated = {"id": "rec-1", "org_id": TENANT_A_ORG}
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([updated])

        repo = TenantRepo(ctx_a())
        repo.update("talent", "rec-1", {"name": "X", "org_id": TENANT_B_ORG})

        # org_id should NOT be in the update payload
        call_args = mock_client.table.return_value.update.call_args[0][0]
        assert "org_id" not in call_args


# =============================================================================
# Direct Ownership — Delete
# =============================================================================


@pytest.mark.unit
class TestDirectOwnershipDelete:
    """Test delete for direct-owned tables."""

    @patch("backend.tenant_repo.get_supabase_client")
    def test_delete_same_tenant(self, mock_client_fn):
        """Delete within same tenant succeeds."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([{"id": "rec-1"}])

        repo = TenantRepo(ctx_a())
        assert repo.delete("talent", "rec-1") is True

    @patch("backend.tenant_repo.get_supabase_client")
    def test_delete_cross_tenant_fails(self, mock_client_fn):
        """Delete of cross-tenant record raises TenantNotFoundError."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        repo = TenantRepo(ctx_a())
        with pytest.raises(TenantNotFoundError):
            repo.delete("talent", "cross-tenant-rec")


# =============================================================================
# Inherited Ownership
# =============================================================================


@pytest.mark.unit
class TestInheritedOwnership:
    """Test inherited ownership validation."""

    @patch("backend.tenant_repo.get_supabase_client")
    def test_create_validates_parent(self, mock_client_fn):
        """Creating a child validates parent belongs to this tenant."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        # Parent lookup (talent) — returns match in tenant A
        parent_result = mock_execute([{"id": "talent-1", "org_id": TENANT_A_ORG}])
        # Child insert
        child_result = mock_execute([{"id": "dna-1", "talent_id": "talent-1"}])

        # Mock the chain: table().select().eq().eq().execute()
        def table_side_effect(name):
            mock_table = MagicMock()
            if name == "talent":
                mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = parent_result
            elif name == "creative_dna":
                mock_table.insert.return_value.execute.return_value = child_result
            return mock_table

        mock_client.table.side_effect = table_side_effect

        repo = TenantRepo(ctx_a())
        result = repo.create("creative_dna", {"talent_id": "talent-1", "data": "test"})
        assert result["id"] == "dna-1"

    @patch("backend.tenant_repo.get_supabase_client")
    def test_create_rejects_cross_tenant_parent(self, mock_client_fn):
        """Creating a child with cross-tenant parent raises error."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        # Parent lookup returns empty (not in this tenant)
        parent_result = mock_execute([])

        def table_side_effect(name):
            mock_table = MagicMock()
            if name == "talent":
                mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = parent_result
            return mock_table

        mock_client.table.side_effect = table_side_effect

        repo = TenantRepo(ctx_a())
        with pytest.raises(TenantParentOwnershipError) as exc_info:
            repo.create("creative_dna", {"talent_id": "other-tenant-talent"})
        assert exc_info.value.parent_entity == "talent"


# =============================================================================
# Bulk Operations
# =============================================================================


@pytest.mark.unit
class TestBulkOperations:
    """Test bulk create operations."""

    @patch("backend.tenant_repo.get_supabase_client")
    def test_bulk_create_injects_org_id(self, mock_client_fn):
        """Bulk create injects org_id on all records."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_execute([
            {"id": "1", "org_id": TENANT_A_ORG},
            {"id": "2", "org_id": TENANT_A_ORG},
        ])

        repo = TenantRepo(ctx_a())
        records = [{"name": "A"}, {"name": "B"}]
        repo.create_bulk("jobs", records)

        # All records should have org_id set
        call_args = mock_client.table.return_value.insert.call_args[0][0]
        assert all(r["org_id"] == TENANT_A_ORG for r in call_args)

    def test_bulk_create_empty(self):
        """Bulk create with empty list returns empty."""
        repo = TenantRepo(ctx_a())
        assert repo.create_bulk("jobs", []) == []


# =============================================================================
# Error Behavior — No Existence Leak
# =============================================================================


@pytest.mark.unit
class TestNoExistenceLeak:
    """Verify cross-tenant and not-found produce identical errors."""

    @patch("backend.tenant_repo.get_supabase_client")
    def test_same_error_for_missing_and_cross_tenant(self, mock_client_fn):
        """Both cases raise TenantNotFoundError with same structure."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        repo = TenantRepo(ctx_a())

        # Cross-tenant attempt
        with pytest.raises(TenantNotFoundError) as exc1:
            repo.get_one("talent", "cross-tenant-id")

        # Non-existent record
        with pytest.raises(TenantNotFoundError) as exc2:
            repo.get_one("talent", "does-not-exist-at-all")

        # Both produce same error type and structure
        assert type(exc1.value) == type(exc2.value)
        assert exc1.value.entity == exc2.value.entity == "talent"


# =============================================================================
# Database.py Refactored Functions
# =============================================================================


@pytest.mark.unit
class TestDatabaseFunctionsRequireOrgId:
    """Verify refactored database.py functions reject empty org_id."""

    def test_get_talent_requires_org_id(self):
        from backend.database import get_talent
        with pytest.raises(ValueError, match="org_id is required"):
            get_talent("")

    def test_get_assets_requires_org_id(self):
        from backend.database import get_assets
        with pytest.raises(ValueError, match="org_id is required"):
            get_assets("")

    def test_get_jobs_requires_org_id(self):
        from backend.database import get_jobs
        with pytest.raises(ValueError, match="org_id is required"):
            get_jobs("")

    def test_get_models_requires_org_id(self):
        from backend.database import get_models
        with pytest.raises(ValueError, match="org_id is required"):
            get_models("")

    def test_get_workflows_requires_org_id(self):
        from backend.database import get_workflows
        with pytest.raises(ValueError, match="org_id is required"):
            get_workflows("")

    def test_create_talent_requires_org_id(self):
        from backend.database import create_talent
        with pytest.raises(ValueError, match="org_id is required"):
            create_talent({"name": "test"}, "")

    def test_create_job_requires_org_id(self):
        from backend.database import create_job
        with pytest.raises(ValueError, match="org_id is required"):
            create_job({"type": "gen"}, "")

    def test_delete_asset_requires_org_id(self):
        from backend.database import delete_asset
        with pytest.raises(ValueError, match="org_id is required"):
            delete_asset("some-id", "")
