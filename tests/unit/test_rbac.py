"""Unit tests for Role-Based Access Control enforcement (Task 4.2).

Validates: Requirements R3.1, R3.2, R3.3, R3.4, R3.5, R3.6

Tests cover:
    - Role hierarchy ordering: owner > admin > editor > viewer
    - Viewer cannot POST (403)
    - Viewer cannot DELETE (403)
    - Editor can POST (allowed)
    - Editor cannot DELETE talent (403)
    - Editor cannot DELETE credential (403)
    - Admin can DELETE anything (allowed)
    - Owner can do anything (allowed)
    - Unknown role defaults to viewer (least privilege)
    - Role resolution from org_members lookup
    - RoleChecker factory dependency
    - RequireRole middleware dependency

Run with:
    pytest tests/unit/test_rbac.py -v
"""

from __future__ import annotations

import os
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root and backend/ are on path for transitive imports
_project_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, "backend"))


# =============================================================================
# Tests: Role Hierarchy (R3.1)
# =============================================================================


@pytest.mark.unit
class TestRoleHierarchy:
    """Tests for the Role enum hierarchy ordering."""

    def test_role_levels_are_correct(self):
        """OWNER(4) > ADMIN(3) > EDITOR(2) > VIEWER(1)."""
        from backend.app.core.rbac import Role

        assert Role.VIEWER.level == 1
        assert Role.EDITOR.level == 2
        assert Role.ADMIN.level == 3
        assert Role.OWNER.level == 4

    def test_owner_greater_than_admin(self):
        """Owner has higher privilege than admin."""
        from backend.app.core.rbac import Role

        assert Role.OWNER > Role.ADMIN
        assert Role.OWNER >= Role.ADMIN
        assert not (Role.OWNER < Role.ADMIN)

    def test_admin_greater_than_editor(self):
        """Admin has higher privilege than editor."""
        from backend.app.core.rbac import Role

        assert Role.ADMIN > Role.EDITOR
        assert Role.ADMIN >= Role.EDITOR

    def test_editor_greater_than_viewer(self):
        """Editor has higher privilege than viewer."""
        from backend.app.core.rbac import Role

        assert Role.EDITOR > Role.VIEWER
        assert Role.EDITOR >= Role.VIEWER

    def test_viewer_is_lowest(self):
        """Viewer is the lowest privilege level."""
        from backend.app.core.rbac import Role

        assert Role.VIEWER < Role.EDITOR
        assert Role.VIEWER < Role.ADMIN
        assert Role.VIEWER < Role.OWNER

    def test_equal_roles(self):
        """Same role satisfies >= check."""
        from backend.app.core.rbac import Role

        assert Role.EDITOR >= Role.EDITOR
        assert Role.ADMIN >= Role.ADMIN
        assert Role.OWNER >= Role.OWNER
        assert Role.VIEWER >= Role.VIEWER

    def test_owner_greater_than_all(self):
        """Owner is greater than every other role."""
        from backend.app.core.rbac import Role

        assert Role.OWNER > Role.ADMIN
        assert Role.OWNER > Role.EDITOR
        assert Role.OWNER > Role.VIEWER


# =============================================================================
# Tests: has_permission function
# =============================================================================


@pytest.mark.unit
class TestHasPermission:
    """Tests for the has_permission() utility function."""

    def test_owner_has_all_permissions(self):
        """Owner meets or exceeds every role requirement."""
        from backend.app.core.rbac import Role, has_permission

        assert has_permission(Role.OWNER, Role.OWNER) is True
        assert has_permission(Role.OWNER, Role.ADMIN) is True
        assert has_permission(Role.OWNER, Role.EDITOR) is True
        assert has_permission(Role.OWNER, Role.VIEWER) is True

    def test_admin_has_admin_editor_viewer(self):
        """Admin meets admin, editor, and viewer requirements."""
        from backend.app.core.rbac import Role, has_permission

        assert has_permission(Role.ADMIN, Role.ADMIN) is True
        assert has_permission(Role.ADMIN, Role.EDITOR) is True
        assert has_permission(Role.ADMIN, Role.VIEWER) is True
        assert has_permission(Role.ADMIN, Role.OWNER) is False

    def test_editor_has_editor_viewer(self):
        """Editor meets editor and viewer but not admin/owner."""
        from backend.app.core.rbac import Role, has_permission

        assert has_permission(Role.EDITOR, Role.EDITOR) is True
        assert has_permission(Role.EDITOR, Role.VIEWER) is True
        assert has_permission(Role.EDITOR, Role.ADMIN) is False
        assert has_permission(Role.EDITOR, Role.OWNER) is False

    def test_viewer_only_meets_viewer(self):
        """Viewer only meets viewer requirement."""
        from backend.app.core.rbac import Role, has_permission

        assert has_permission(Role.VIEWER, Role.VIEWER) is True
        assert has_permission(Role.VIEWER, Role.EDITOR) is False
        assert has_permission(Role.VIEWER, Role.ADMIN) is False
        assert has_permission(Role.VIEWER, Role.OWNER) is False


# =============================================================================
# Tests: role_from_string and unknown role handling
# =============================================================================


@pytest.mark.unit
class TestRoleFromString:
    """Tests for role_from_string with unknown role defaulting."""

    def test_valid_roles_are_parsed(self):
        """All valid role strings convert correctly."""
        from backend.app.core.rbac import Role, role_from_string

        assert role_from_string("owner") == Role.OWNER
        assert role_from_string("admin") == Role.ADMIN
        assert role_from_string("editor") == Role.EDITOR
        assert role_from_string("viewer") == Role.VIEWER

    def test_case_insensitive(self):
        """Role parsing is case-insensitive."""
        from backend.app.core.rbac import Role, role_from_string

        assert role_from_string("OWNER") == Role.OWNER
        assert role_from_string("Admin") == Role.ADMIN
        assert role_from_string("EDITOR") == Role.EDITOR

    def test_strips_whitespace(self):
        """Role parsing strips leading/trailing whitespace."""
        from backend.app.core.rbac import Role, role_from_string

        assert role_from_string("  owner  ") == Role.OWNER
        assert role_from_string("\tadmin\n") == Role.ADMIN

    def test_unknown_role_defaults_to_viewer(self):
        """Unknown role strings default to VIEWER (least privilege)."""
        from backend.app.core.rbac import Role, role_from_string

        assert role_from_string("superuser") == Role.VIEWER
        assert role_from_string("root") == Role.VIEWER
        assert role_from_string("") == Role.VIEWER
        assert role_from_string("unknown") == Role.VIEWER

    def test_none_defaults_to_viewer(self):
        """None input defaults to VIEWER."""
        from backend.app.core.rbac import Role, role_from_string

        assert role_from_string(None) == Role.VIEWER


# =============================================================================
# Tests: RoleChecker dependency factory
# =============================================================================


@pytest.mark.unit
class TestRoleChecker:
    """Tests for the RoleChecker FastAPI dependency factory."""

    @pytest.mark.asyncio
    async def test_owner_passes_admin_check(self):
        """Owner passes a check requiring admin."""
        from backend.app.core.rbac import Role, RoleChecker

        checker = RoleChecker(Role.ADMIN)
        tenant_ctx = _make_tenant_context("owner")
        request = _make_request("DELETE", "/api/v1/talent/123", tenant_ctx)

        result = await checker(request, tenant_ctx)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_editor_passes_editor_check(self):
        """Editor passes a check requiring editor."""
        from backend.app.core.rbac import Role, RoleChecker

        checker = RoleChecker(Role.EDITOR)
        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("POST", "/api/v1/talent", tenant_ctx)

        result = await checker(request, tenant_ctx)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_viewer_fails_editor_check(self):
        """Viewer is blocked by a check requiring editor (403)."""
        from fastapi import HTTPException

        from backend.app.core.rbac import Role, RoleChecker

        checker = RoleChecker(Role.EDITOR)
        tenant_ctx = _make_tenant_context("viewer")
        request = _make_request("POST", "/api/v1/talent", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await checker(request, tenant_ctx)

        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_editor_fails_admin_check(self):
        """Editor is blocked by a check requiring admin (403)."""
        from fastapi import HTTPException

        from backend.app.core.rbac import Role, RoleChecker

        checker = RoleChecker(Role.ADMIN)
        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("DELETE", "/api/v1/talent/123", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await checker(request, tenant_ctx)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_checker_with_resource_type(self):
        """RoleChecker with resource_type includes it in error message."""
        from fastapi import HTTPException

        from backend.app.core.rbac import Role, RoleChecker

        checker = RoleChecker(Role.ADMIN, resource_type="talent")
        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("DELETE", "/api/v1/talent/123", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await checker(request, tenant_ctx)

        assert exc_info.value.status_code == 403
        assert "talent" in exc_info.value.detail


# =============================================================================
# Tests: Viewer read-only enforcement (R3.2, R3.3)
# =============================================================================


@pytest.mark.unit
class TestViewerReadOnly:
    """Tests that viewers are blocked from POST/PUT/PATCH/DELETE."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_post(self):
        """Viewer is blocked from POST (403). Validates: R3.2"""
        from fastapi import HTTPException

        from backend.middleware.rbac_middleware import enforce_viewer_read_only

        tenant_ctx = _make_tenant_context("viewer")
        request = _make_request("POST", "/api/v1/talent", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await enforce_viewer_read_only(request, tenant_ctx)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_put(self):
        """Viewer is blocked from PUT (403). Validates: R3.2"""
        from fastapi import HTTPException

        from backend.middleware.rbac_middleware import enforce_viewer_read_only

        tenant_ctx = _make_tenant_context("viewer")
        request = _make_request("PUT", "/api/v1/talent/123", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await enforce_viewer_read_only(request, tenant_ctx)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_patch(self):
        """Viewer is blocked from PATCH (403). Validates: R3.2"""
        from fastapi import HTTPException

        from backend.middleware.rbac_middleware import enforce_viewer_read_only

        tenant_ctx = _make_tenant_context("viewer")
        request = _make_request("PATCH", "/api/v1/talent/123", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await enforce_viewer_read_only(request, tenant_ctx)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete(self):
        """Viewer is blocked from DELETE (403). Validates: R3.2"""
        from fastapi import HTTPException

        from backend.middleware.rbac_middleware import enforce_viewer_read_only

        tenant_ctx = _make_tenant_context("viewer")
        request = _make_request("DELETE", "/api/v1/talent/123", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await enforce_viewer_read_only(request, tenant_ctx)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_can_get(self):
        """Viewer is allowed to GET (read). Validates: R3.2"""
        from backend.middleware.rbac_middleware import enforce_viewer_read_only

        tenant_ctx = _make_tenant_context("viewer")
        request = _make_request("GET", "/api/v1/talent", tenant_ctx)

        result = await enforce_viewer_read_only(request, tenant_ctx)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_editor_can_post(self):
        """Editor is allowed to POST. Validates: R3.3"""
        from backend.middleware.rbac_middleware import enforce_viewer_read_only

        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("POST", "/api/v1/talent", tenant_ctx)

        result = await enforce_viewer_read_only(request, tenant_ctx)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_admin_can_post(self):
        """Admin is allowed to POST."""
        from backend.middleware.rbac_middleware import enforce_viewer_read_only

        tenant_ctx = _make_tenant_context("admin")
        request = _make_request("POST", "/api/v1/talent", tenant_ctx)

        result = await enforce_viewer_read_only(request, tenant_ctx)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_owner_can_delete(self):
        """Owner is allowed to DELETE anything."""
        from backend.middleware.rbac_middleware import enforce_viewer_read_only

        tenant_ctx = _make_tenant_context("owner")
        request = _make_request("DELETE", "/api/v1/talent/123", tenant_ctx)

        result = await enforce_viewer_read_only(request, tenant_ctx)
        assert result == tenant_ctx


# =============================================================================
# Tests: Editor DELETE restrictions on sensitive resources (R3.4)
# =============================================================================


@pytest.mark.unit
class TestEditorDeleteRestriction:
    """Tests that editors cannot DELETE talent, model, credential, org-settings."""

    @pytest.mark.asyncio
    async def test_editor_cannot_delete_talent(self):
        """Editor blocked from DELETE on talent resource (403). Validates: R3.4"""
        from fastapi import HTTPException

        from backend.middleware.rbac_middleware import (
            enforce_editor_delete_restriction,
        )

        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("DELETE", "/api/v1/talent/123", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await enforce_editor_delete_restriction(request, tenant_ctx)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_cannot_delete_credential(self):
        """Editor blocked from DELETE on credentials (403). Validates: R3.4"""
        from fastapi import HTTPException

        from backend.middleware.rbac_middleware import (
            enforce_editor_delete_restriction,
        )

        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("DELETE", "/api/v1/credentials/abc", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await enforce_editor_delete_restriction(request, tenant_ctx)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_cannot_delete_model(self):
        """Editor blocked from DELETE on models (403). Validates: R3.4"""
        from fastapi import HTTPException

        from backend.middleware.rbac_middleware import (
            enforce_editor_delete_restriction,
        )

        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("DELETE", "/api/v1/models/xyz", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await enforce_editor_delete_restriction(request, tenant_ctx)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_cannot_delete_org_settings(self):
        """Editor blocked from DELETE on org-settings (403). Validates: R3.4"""
        from fastapi import HTTPException

        from backend.middleware.rbac_middleware import (
            enforce_editor_delete_restriction,
        )

        tenant_ctx = _make_tenant_context("editor")
        request = _make_request(
            "DELETE", "/api/v1/org-settings/abc", tenant_ctx
        )

        with pytest.raises(HTTPException) as exc_info:
            await enforce_editor_delete_restriction(request, tenant_ctx)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_delete_talent(self):
        """Admin is allowed to DELETE talent. Validates: R3.5"""
        from backend.middleware.rbac_middleware import (
            enforce_editor_delete_restriction,
        )

        tenant_ctx = _make_tenant_context("admin")
        request = _make_request("DELETE", "/api/v1/talent/123", tenant_ctx)

        result = await enforce_editor_delete_restriction(request, tenant_ctx)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_admin_can_delete_credential(self):
        """Admin is allowed to DELETE credentials."""
        from backend.middleware.rbac_middleware import (
            enforce_editor_delete_restriction,
        )

        tenant_ctx = _make_tenant_context("admin")
        request = _make_request("DELETE", "/api/v1/credentials/abc", tenant_ctx)

        result = await enforce_editor_delete_restriction(request, tenant_ctx)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_owner_can_delete_anything(self):
        """Owner is allowed to DELETE any resource. Validates: R3.6"""
        from backend.middleware.rbac_middleware import (
            enforce_editor_delete_restriction,
        )

        tenant_ctx = _make_tenant_context("owner")
        request = _make_request("DELETE", "/api/v1/talent/123", tenant_ctx)

        result = await enforce_editor_delete_restriction(request, tenant_ctx)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_editor_can_delete_non_sensitive_resource(self):
        """Editor CAN delete non-sensitive resources (e.g., jobs)."""
        from backend.middleware.rbac_middleware import (
            enforce_editor_delete_restriction,
        )

        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("DELETE", "/api/v1/jobs/123", tenant_ctx)

        result = await enforce_editor_delete_restriction(request, tenant_ctx)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_editor_can_post_to_talent(self):
        """Editor can POST (create) talent — only DELETE is restricted."""
        from backend.middleware.rbac_middleware import (
            enforce_editor_delete_restriction,
        )

        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("POST", "/api/v1/talent", tenant_ctx)

        result = await enforce_editor_delete_restriction(request, tenant_ctx)
        assert result == tenant_ctx


# =============================================================================
# Tests: RequireRole middleware dependency
# =============================================================================


@pytest.mark.unit
class TestRequireRole:
    """Tests for the RequireRole middleware dependency class."""

    @pytest.mark.asyncio
    async def test_require_editor_allows_editor(self):
        """RequireRole(EDITOR) allows editor role."""
        from backend.app.core.rbac import Role

        from backend.middleware.rbac_middleware import RequireRole

        dep = RequireRole(Role.EDITOR)
        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("POST", "/api/v1/talent", tenant_ctx)

        result = await dep(request)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_require_editor_allows_admin(self):
        """RequireRole(EDITOR) allows admin role (higher privilege)."""
        from backend.app.core.rbac import Role

        from backend.middleware.rbac_middleware import RequireRole

        dep = RequireRole(Role.EDITOR)
        tenant_ctx = _make_tenant_context("admin")
        request = _make_request("POST", "/api/v1/talent", tenant_ctx)

        result = await dep(request)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_require_editor_blocks_viewer(self):
        """RequireRole(EDITOR) blocks viewer role (403)."""
        from fastapi import HTTPException

        from backend.app.core.rbac import Role

        from backend.middleware.rbac_middleware import RequireRole

        dep = RequireRole(Role.EDITOR)
        tenant_ctx = _make_tenant_context("viewer")
        request = _make_request("POST", "/api/v1/talent", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await dep(request)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_admin_blocks_editor(self):
        """RequireRole(ADMIN) blocks editor role (403)."""
        from fastapi import HTTPException

        from backend.app.core.rbac import Role

        from backend.middleware.rbac_middleware import RequireRole

        dep = RequireRole(Role.ADMIN)
        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("DELETE", "/api/v1/talent/123", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await dep(request)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_owner_allows_owner(self):
        """RequireRole(OWNER) allows owner role."""
        from backend.app.core.rbac import Role

        from backend.middleware.rbac_middleware import RequireRole

        dep = RequireRole(Role.OWNER)
        tenant_ctx = _make_tenant_context("owner")
        request = _make_request("DELETE", "/api/v1/org/123", tenant_ctx)

        result = await dep(request)
        assert result == tenant_ctx


# =============================================================================
# Tests: Role resolution from org_members (R3.5)
# =============================================================================


@pytest.mark.unit
class TestRoleResolution:
    """Tests for role resolution from org_members via get_user_role."""

    @pytest.mark.asyncio
    async def test_resolves_owner_role(self):
        """get_user_role returns Role.OWNER when tenant has owner role."""
        from backend.app.core.rbac import Role

        from backend.middleware.rbac_middleware import get_user_role

        tenant_ctx = _make_tenant_context("owner")
        request = _make_request("GET", "/api/v1/talent", tenant_ctx)

        role = await get_user_role(request)
        assert role == Role.OWNER

    @pytest.mark.asyncio
    async def test_resolves_admin_role(self):
        """get_user_role returns Role.ADMIN when tenant has admin role."""
        from backend.app.core.rbac import Role

        from backend.middleware.rbac_middleware import get_user_role

        tenant_ctx = _make_tenant_context("admin")
        request = _make_request("GET", "/api/v1/talent", tenant_ctx)

        role = await get_user_role(request)
        assert role == Role.ADMIN

    @pytest.mark.asyncio
    async def test_resolves_editor_role(self):
        """get_user_role returns Role.EDITOR when tenant has editor role."""
        from backend.app.core.rbac import Role

        from backend.middleware.rbac_middleware import get_user_role

        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("GET", "/api/v1/talent", tenant_ctx)

        role = await get_user_role(request)
        assert role == Role.EDITOR

    @pytest.mark.asyncio
    async def test_resolves_viewer_role(self):
        """get_user_role returns Role.VIEWER when tenant has viewer role."""
        from backend.app.core.rbac import Role

        from backend.middleware.rbac_middleware import get_user_role

        tenant_ctx = _make_tenant_context("viewer")
        request = _make_request("GET", "/api/v1/talent", tenant_ctx)

        role = await get_user_role(request)
        assert role == Role.VIEWER

    @pytest.mark.asyncio
    async def test_caches_role_on_request_state(self):
        """get_user_role caches the resolved role on request.state."""
        from backend.app.core.rbac import Role

        from backend.middleware.rbac_middleware import get_user_role

        tenant_ctx = _make_tenant_context("admin")
        request = _make_request("GET", "/api/v1/talent", tenant_ctx)

        role = await get_user_role(request)
        assert role == Role.ADMIN
        # Verify it's cached
        assert request.state.resolved_role == Role.ADMIN

    @pytest.mark.asyncio
    async def test_uses_cached_role_on_second_call(self):
        """Second call to get_user_role uses cached value."""
        from backend.app.core.rbac import Role

        from backend.middleware.rbac_middleware import get_user_role

        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("GET", "/api/v1/talent", tenant_ctx)

        # First call sets cache
        role1 = await get_user_role(request)
        # Second call uses cache
        role2 = await get_user_role(request)

        assert role1 == role2 == Role.EDITOR


# =============================================================================
# Tests: enforce_method_role (method-aware enforcement)
# =============================================================================


@pytest.mark.unit
class TestEnforceMethodRole:
    """Tests for the enforce_method_role dependency."""

    @pytest.mark.asyncio
    async def test_viewer_allowed_get(self):
        """Viewer can perform GET."""
        from backend.app.core.rbac import enforce_method_role

        tenant_ctx = _make_tenant_context("viewer")
        request = _make_request("GET", "/api/v1/talent", tenant_ctx)

        result = await enforce_method_role(request, tenant_ctx)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_viewer_blocked_post(self):
        """Viewer blocked from POST (403)."""
        from fastapi import HTTPException

        from backend.app.core.rbac import enforce_method_role

        tenant_ctx = _make_tenant_context("viewer")
        request = _make_request("POST", "/api/v1/talent", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await enforce_method_role(request, tenant_ctx)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_blocked_delete(self):
        """Viewer blocked from DELETE (403)."""
        from fastapi import HTTPException

        from backend.app.core.rbac import enforce_method_role

        tenant_ctx = _make_tenant_context("viewer")
        request = _make_request("DELETE", "/api/v1/talent/123", tenant_ctx)

        with pytest.raises(HTTPException) as exc_info:
            await enforce_method_role(request, tenant_ctx)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_allowed_post(self):
        """Editor can perform POST."""
        from backend.app.core.rbac import enforce_method_role

        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("POST", "/api/v1/talent", tenant_ctx)

        result = await enforce_method_role(request, tenant_ctx)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_editor_allowed_delete(self):
        """Editor can perform DELETE (generic; sensitive resource
        restrictions are handled separately)."""
        from backend.app.core.rbac import enforce_method_role

        tenant_ctx = _make_tenant_context("editor")
        request = _make_request("DELETE", "/api/v1/jobs/123", tenant_ctx)

        result = await enforce_method_role(request, tenant_ctx)
        assert result == tenant_ctx

    @pytest.mark.asyncio
    async def test_admin_allowed_all_methods(self):
        """Admin can perform all HTTP methods."""
        from backend.app.core.rbac import enforce_method_role

        tenant_ctx = _make_tenant_context("admin")

        for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            request = _make_request(method, "/api/v1/talent/123", tenant_ctx)
            result = await enforce_method_role(request, tenant_ctx)
            assert result == tenant_ctx


# =============================================================================
# Tests: Resource path extraction helper
# =============================================================================


@pytest.mark.unit
class TestExtractResourceType:
    """Tests for the _extract_resource_type helper."""

    def test_extracts_talent(self):
        """Extracts 'talent' from /api/v1/talent/123."""
        from backend.middleware.rbac_middleware import _extract_resource_type

        assert _extract_resource_type("/api/v1/talent/123") == "talent"

    def test_extracts_models(self):
        """Extracts 'models' from /api/v1/models/abc."""
        from backend.middleware.rbac_middleware import _extract_resource_type

        assert _extract_resource_type("/api/v1/models/abc") == "models"

    def test_extracts_credentials(self):
        """Extracts 'credentials' from /api/v1/credentials/xyz."""
        from backend.middleware.rbac_middleware import _extract_resource_type

        assert _extract_resource_type("/api/v1/credentials/xyz") == "credentials"

    def test_extracts_org_settings(self):
        """Extracts 'org-settings' from /api/v1/org-settings."""
        from backend.middleware.rbac_middleware import _extract_resource_type

        assert _extract_resource_type("/api/v1/org-settings") == "org-settings"

    def test_extracts_jobs(self):
        """Extracts 'jobs' from /api/v1/jobs/123."""
        from backend.middleware.rbac_middleware import _extract_resource_type

        assert _extract_resource_type("/api/v1/jobs/123") == "jobs"

    def test_empty_path_returns_empty(self):
        """Empty or root path returns empty string."""
        from backend.middleware.rbac_middleware import _extract_resource_type

        assert _extract_resource_type("/") == ""
        assert _extract_resource_type("/api/v1") == ""

    def test_no_prefix(self):
        """Path without /api/v1 prefix still works."""
        from backend.middleware.rbac_middleware import _extract_resource_type

        assert _extract_resource_type("/talent/123") == "talent"


# =============================================================================
# Test Helpers
# =============================================================================


def _make_tenant_context(role: str) -> "TenantContext":
    """Create a mock TenantContext with the specified role."""
    from backend.app.core.dependencies import TenantContext, TrustDomain, WorkspaceRole

    role_enum = WorkspaceRole(role)
    trust_domain = (
        TrustDomain.WORKSPACE_ADMIN
        if role in ("owner", "admin")
        else TrustDomain.CUSTOMER_USER
    )

    return TenantContext(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=role_enum,
        trust_domain=trust_domain,
        email=f"{role}@test.example",
    )


def _make_request(
    method: str, path: str, tenant_ctx: "TenantContext"
) -> MagicMock:
    """Create a mock Request object with the given method and path."""
    request = MagicMock()
    request.method = method
    request.url = MagicMock()
    request.url.path = path

    # Store tenant_context on state for role resolution
    state = MagicMock()
    state.tenant_context = tenant_ctx
    # Allow setting new attributes
    state.resolved_role = None
    request.state = state

    return request
