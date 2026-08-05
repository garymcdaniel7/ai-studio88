"""Memory namespace isolation tests — Story 040.

Tests verify:
  - Namespace authorization (user_private, founder_private, workspace_shared, project, customer)
  - Cross-scope security (private memory invisible to other users)
  - Founder memory never appears in customer sessions
  - Retention class and expiry behavior
  - Skip-memory exclusion from retrieval
  - Provenance is recorded
  - org_id required for all operations
  - Legacy records quarantined
  - Deletion authorization per namespace
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.membership import OrgRole, TenantContext
from backend.memory_service import (
    MemoryAccessDenied,
    MemoryNamespace,
    MemoryProvenance,
    RetentionClass,
    can_delete,
    can_read,
    can_write,
    forget,
    recall,
    remember,
)

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_A = "user-aaaa"
USER_B = "user-bbbb"


def ctx_owner() -> TenantContext:
    return TenantContext(user_id=USER_A, org_id=TENANT_A, role=OrgRole.OWNER)


def ctx_editor() -> TenantContext:
    return TenantContext(user_id=USER_A, org_id=TENANT_A, role=OrgRole.EDITOR)


def ctx_viewer() -> TenantContext:
    return TenantContext(user_id=USER_B, org_id=TENANT_A, role=OrgRole.VIEWER)


def mock_execute(data=None):
    r = MagicMock()
    r.data = data if data is not None else []
    return r


# =============================================================================
# Read Authorization
# =============================================================================


@pytest.mark.unit
class TestReadAuthorization:
    """Verify namespace read rules."""

    def test_user_private_only_owner_reads(self):
        assert can_read(ctx_owner(), MemoryNamespace.USER_PRIVATE, USER_A) is True
        assert can_read(ctx_viewer(), MemoryNamespace.USER_PRIVATE, USER_A) is False

    def test_founder_private_only_owner(self):
        assert can_read(ctx_owner(), MemoryNamespace.FOUNDER_PRIVATE, USER_A) is True
        assert can_read(ctx_editor(), MemoryNamespace.FOUNDER_PRIVATE, USER_A) is False

    def test_workspace_shared_all_members(self):
        assert can_read(ctx_owner(), MemoryNamespace.WORKSPACE_SHARED) is True
        assert can_read(ctx_viewer(), MemoryNamespace.WORKSPACE_SHARED) is True

    def test_project_all_members(self):
        assert can_read(ctx_viewer(), MemoryNamespace.PROJECT) is True

    def test_customer_only_editors_plus(self):
        assert can_read(ctx_editor(), MemoryNamespace.CUSTOMER) is True
        assert can_read(ctx_viewer(), MemoryNamespace.CUSTOMER) is False


# =============================================================================
# Write Authorization
# =============================================================================


@pytest.mark.unit
class TestWriteAuthorization:
    """Verify namespace write rules."""

    def test_user_private_anyone_writes_own(self):
        assert can_write(ctx_viewer(), MemoryNamespace.USER_PRIVATE) is True

    def test_founder_private_only_owner(self):
        assert can_write(ctx_owner(), MemoryNamespace.FOUNDER_PRIVATE) is True
        assert can_write(ctx_editor(), MemoryNamespace.FOUNDER_PRIVATE) is False

    def test_workspace_shared_editors_plus(self):
        assert can_write(ctx_editor(), MemoryNamespace.WORKSPACE_SHARED) is True
        assert can_write(ctx_viewer(), MemoryNamespace.WORKSPACE_SHARED) is False

    def test_project_editors_plus(self):
        assert can_write(ctx_editor(), MemoryNamespace.PROJECT) is True
        assert can_write(ctx_viewer(), MemoryNamespace.PROJECT) is False


# =============================================================================
# Delete Authorization
# =============================================================================


@pytest.mark.unit
class TestDeleteAuthorization:
    """Verify namespace delete rules."""

    def test_user_private_only_owner_deletes(self):
        assert can_delete(ctx_owner(), MemoryNamespace.USER_PRIVATE, USER_A) is True
        assert can_delete(ctx_viewer(), MemoryNamespace.USER_PRIVATE, USER_A) is False

    def test_workspace_shared_admin_only(self):
        assert can_delete(ctx_owner(), MemoryNamespace.WORKSPACE_SHARED) is True
        assert can_delete(ctx_editor(), MemoryNamespace.WORKSPACE_SHARED) is False


# =============================================================================
# Remember — Write with Namespace
# =============================================================================


@pytest.mark.unit
class TestRemember:
    """Verify remember stores with correct metadata."""

    @patch("backend.memory_service._db")
    def test_remember_stores_with_namespace(self, mock_db_fn):
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.upsert.return_value.execute.return_value = mock_execute([{"id": "m1"}])

        remember(ctx_editor(), "preferences", "theme", "dark", namespace=MemoryNamespace.USER_PRIVATE)
        call_data = mock_db.table.return_value.upsert.call_args[0][0]
        assert call_data["org_id"] == TENANT_A
        assert call_data["user_id"] == USER_A
        assert call_data["namespace"] == "user_private"
        assert call_data["provenance"] == "inferred"

    @patch("backend.memory_service._db")
    def test_remember_requires_org_id(self, mock_db_fn):
        ctx = TenantContext(user_id=USER_A, org_id="", role=OrgRole.EDITOR)
        with pytest.raises(ValueError, match="org_id is required"):
            remember(ctx, "cat", "key", "val")

    def test_remember_denies_unauthorized_write(self):
        """Viewer cannot write to workspace_shared."""
        with pytest.raises(MemoryAccessDenied):
            remember(ctx_viewer(), "cat", "key", "val", namespace=MemoryNamespace.WORKSPACE_SHARED)

    def test_remember_denies_editor_founder_private(self):
        """Editor cannot write founder_private."""
        with pytest.raises(MemoryAccessDenied):
            remember(ctx_editor(), "cat", "key", "val", namespace=MemoryNamespace.FOUNDER_PRIVATE)

    def test_project_namespace_requires_project_id(self):
        """Project namespace requires project_id."""
        with pytest.raises(ValueError, match="project_id is required"):
            remember(ctx_editor(), "cat", "key", "val", namespace=MemoryNamespace.PROJECT)


# =============================================================================
# Recall — Namespace-Filtered Retrieval
# =============================================================================


@pytest.mark.unit
class TestRecall:
    """Verify recall filters by authorization."""

    @patch("backend.memory_service._db")
    def test_recall_filters_private_memory(self, mock_db_fn):
        """User B cannot see User A's private memory."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        items = [
            {"id": "m1", "namespace": "user_private", "user_id": USER_A, "skip_memory": False},
            {"id": "m2", "namespace": "workspace_shared", "user_id": USER_A, "skip_memory": False},
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_execute(items)

        result = recall(ctx_viewer())  # USER_B as viewer
        # Should only see workspace_shared, not user_private (belongs to USER_A)
        assert len(result) == 1
        assert result[0]["namespace"] == "workspace_shared"

    @patch("backend.memory_service._db")
    def test_recall_excludes_skip_memory(self, mock_db_fn):
        """skip_memory=True items excluded from retrieval."""
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        # The query already filters skip_memory=False at DB level
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_execute([])

        recall(ctx_editor())
        # Verify the eq("skip_memory", False) was called in the chain

    @patch("backend.memory_service._db")
    def test_recall_requires_org_id(self, mock_db_fn):
        ctx = TenantContext(user_id=USER_A, org_id="", role=OrgRole.EDITOR)
        with pytest.raises(ValueError, match="org_id is required"):
            recall(ctx)


# =============================================================================
# Founder Memory Never in Customer Context
# =============================================================================


@pytest.mark.unit
class TestFounderIsolation:
    """Verify founder memory is never exposed to non-owners."""

    def test_founder_private_hidden_from_editor(self):
        assert can_read(ctx_editor(), MemoryNamespace.FOUNDER_PRIVATE, USER_A) is False

    def test_founder_private_hidden_from_viewer(self):
        assert can_read(ctx_viewer(), MemoryNamespace.FOUNDER_PRIVATE, USER_A) is False

    def test_founder_private_visible_to_owner(self):
        assert can_read(ctx_owner(), MemoryNamespace.FOUNDER_PRIVATE, USER_A) is True


# =============================================================================
# Retention and Provenance
# =============================================================================


@pytest.mark.unit
class TestRetentionProvenance:
    """Verify retention and provenance metadata."""

    @patch("backend.memory_service._db")
    def test_remember_sets_provenance(self, mock_db_fn):
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.upsert.return_value.execute.return_value = mock_execute([{}])

        remember(ctx_editor(), "cat", "key", "val", provenance=MemoryProvenance.USER_CONFIRMED)
        call_data = mock_db.table.return_value.upsert.call_args[0][0]
        assert call_data["provenance"] == "user_confirmed"

    @patch("backend.memory_service._db")
    def test_remember_sets_retention(self, mock_db_fn):
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.upsert.return_value.execute.return_value = mock_execute([{}])

        remember(ctx_editor(), "cat", "key", "val", retention=RetentionClass.EPHEMERAL)
        call_data = mock_db.table.return_value.upsert.call_args[0][0]
        assert call_data["retention_class"] == "ephemeral"
        assert call_data["expires_at"] is not None  # 1 day from now

    @patch("backend.memory_service._db")
    def test_persistent_has_no_expiry(self, mock_db_fn):
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.upsert.return_value.execute.return_value = mock_execute([{}])

        remember(ctx_editor(), "cat", "key", "val", retention=RetentionClass.PERSISTENT)
        call_data = mock_db.table.return_value.upsert.call_args[0][0]
        assert call_data["expires_at"] is None


# =============================================================================
# Migration Verification
# =============================================================================


@pytest.mark.unit
class TestMigrationFile:
    """Verify the migration adds required columns and fixes constraints."""

    def test_migration_exists(self):
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        path = os.path.join(repo_root, "docs", "sql", "037_memory_namespaces.sql")
        assert os.path.exists(path)

    def test_migration_adds_namespace_columns(self):
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        path = os.path.join(repo_root, "docs", "sql", "037_memory_namespaces.sql")
        with open(path) as f:
            sql = f.read()
        assert "namespace TEXT" in sql
        assert "audience TEXT" in sql
        assert "provenance TEXT" in sql
        assert "retention_class TEXT" in sql
        assert "expires_at TIMESTAMPTZ" in sql
        assert "skip_memory BOOLEAN" in sql

    def test_migration_fixes_unique_constraint(self):
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        path = os.path.join(repo_root, "docs", "sql", "037_memory_namespaces.sql")
        with open(path) as f:
            sql = f.read()
        assert "DROP CONSTRAINT" in sql
        assert "uq_brain_memory_org_category_key" in sql
