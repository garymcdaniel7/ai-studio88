"""Unit tests for the canonical membership model (Story 005).

Tests cover:
- OrgRole privilege hierarchy
- TenantContext role checking
- Membership resolution (mocked DB)
- Cross-tenant isolation
- Edge cases: no membership, suspended, multi-workspace, system org

Run with:
    pytest tests/unit/test_membership.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.membership import (
    SYSTEM_ORG_ID,
    MembershipError,
    MembershipStatus,
    OrgRole,
    TenantContext,
    resolve_membership,
    resolve_membership_or_none,
)


# =============================================================================
# OrgRole Tests
# =============================================================================


class TestOrgRole:
    """Test role hierarchy and privilege checks."""

    @pytest.mark.unit
    def test_owner_has_all_privileges(self):
        assert OrgRole.OWNER.has_privilege(OrgRole.OWNER)
        assert OrgRole.OWNER.has_privilege(OrgRole.ADMIN)
        assert OrgRole.OWNER.has_privilege(OrgRole.EDITOR)
        assert OrgRole.OWNER.has_privilege(OrgRole.VIEWER)

    @pytest.mark.unit
    def test_admin_has_admin_and_below(self):
        assert OrgRole.ADMIN.has_privilege(OrgRole.ADMIN)
        assert OrgRole.ADMIN.has_privilege(OrgRole.EDITOR)
        assert OrgRole.ADMIN.has_privilege(OrgRole.VIEWER)
        assert not OrgRole.ADMIN.has_privilege(OrgRole.OWNER)

    @pytest.mark.unit
    def test_editor_has_editor_and_below(self):
        assert OrgRole.EDITOR.has_privilege(OrgRole.EDITOR)
        assert OrgRole.EDITOR.has_privilege(OrgRole.VIEWER)
        assert not OrgRole.EDITOR.has_privilege(OrgRole.ADMIN)
        assert not OrgRole.EDITOR.has_privilege(OrgRole.OWNER)

    @pytest.mark.unit
    def test_viewer_only_has_viewer(self):
        assert OrgRole.VIEWER.has_privilege(OrgRole.VIEWER)
        assert not OrgRole.VIEWER.has_privilege(OrgRole.EDITOR)
        assert not OrgRole.VIEWER.has_privilege(OrgRole.ADMIN)
        assert not OrgRole.VIEWER.has_privilege(OrgRole.OWNER)

    @pytest.mark.unit
    def test_role_string_values(self):
        assert OrgRole.OWNER.value == "owner"
        assert OrgRole.ADMIN.value == "admin"
        assert OrgRole.EDITOR.value == "editor"
        assert OrgRole.VIEWER.value == "viewer"


# =============================================================================
# TenantContext Tests
# =============================================================================


class TestTenantContext:
    """Test the trusted execution context."""

    @pytest.mark.unit
    def test_owner_context_properties(self):
        ctx = TenantContext(
            user_id="user-1",
            org_id="org-1",
            role=OrgRole.OWNER,
            email="test@example.com",
        )
        assert ctx.is_owner
        assert ctx.is_admin_or_above
        assert ctx.is_editor_or_above

    @pytest.mark.unit
    def test_admin_context_properties(self):
        ctx = TenantContext(
            user_id="user-1",
            org_id="org-1",
            role=OrgRole.ADMIN,
        )
        assert not ctx.is_owner
        assert ctx.is_admin_or_above
        assert ctx.is_editor_or_above

    @pytest.mark.unit
    def test_viewer_context_properties(self):
        ctx = TenantContext(
            user_id="user-1",
            org_id="org-1",
            role=OrgRole.VIEWER,
        )
        assert not ctx.is_owner
        assert not ctx.is_admin_or_above
        assert not ctx.is_editor_or_above

    @pytest.mark.unit
    def test_require_role_passes_for_sufficient_privilege(self):
        ctx = TenantContext(user_id="u", org_id="o", role=OrgRole.ADMIN)
        # Should not raise
        ctx.require_role(OrgRole.EDITOR)
        ctx.require_role(OrgRole.VIEWER)
        ctx.require_role(OrgRole.ADMIN)

    @pytest.mark.unit
    def test_require_role_raises_for_insufficient_privilege(self):
        ctx = TenantContext(user_id="u", org_id="o", role=OrgRole.VIEWER)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            ctx.require_role(OrgRole.EDITOR)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_context_is_frozen(self):
        ctx = TenantContext(user_id="u", org_id="o", role=OrgRole.VIEWER)
        with pytest.raises(Exception):  # FrozenInstanceError
            ctx.user_id = "tampered"  # type: ignore[misc]


# =============================================================================
# Membership Resolution Tests (mocked DB)
# =============================================================================


class TestResolveMembership:
    """Test membership resolution with mocked Supabase client."""

    @pytest.mark.unit
    @patch("backend.membership.is_supabase_configured", return_value=True)
    @patch("backend.database.get_supabase_client")
    def test_single_active_membership(self, mock_client_fn, mock_configured):
        """User with one active membership → returns that org/role."""
        org_id = str(uuid4())
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        mock_result = MagicMock()
        mock_result.data = [{"org_id": org_id, "role": "editor", "status": "active"}]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result

        ctx = resolve_membership("user-123")

        assert ctx.user_id == "user-123"
        assert ctx.org_id == org_id
        assert ctx.role == OrgRole.EDITOR

    @pytest.mark.unit
    @patch("backend.membership.is_supabase_configured", return_value=True)
    @patch("backend.database.get_supabase_client")
    def test_no_membership_raises_error(self, mock_client_fn, mock_configured):
        """User with no memberships → MembershipError raised."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        mock_result = MagicMock()
        mock_result.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result

        with pytest.raises(MembershipError) as exc_info:
            resolve_membership("user-no-org")
        assert "No active" in exc_info.value.detail

    @pytest.mark.unit
    @patch("backend.membership.is_supabase_configured", return_value=True)
    @patch("backend.database.get_supabase_client")
    def test_multi_workspace_prefers_hint(self, mock_client_fn, mock_configured):
        """User with multiple memberships + preferred_org_id → uses preferred."""
        org_a = str(uuid4())
        org_b = str(uuid4())
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        mock_result = MagicMock()
        mock_result.data = [
            {"org_id": org_a, "role": "viewer", "status": "active"},
            {"org_id": org_b, "role": "owner", "status": "active"},
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result

        ctx = resolve_membership("user-multi", preferred_org_id=org_b)
        assert ctx.org_id == org_b
        assert ctx.role == OrgRole.OWNER

    @pytest.mark.unit
    @patch("backend.membership.is_supabase_configured", return_value=True)
    @patch("backend.database.get_supabase_client")
    def test_multi_workspace_no_hint_uses_first(self, mock_client_fn, mock_configured):
        """User with multiple memberships but no hint → uses first result."""
        org_a = str(uuid4())
        org_b = str(uuid4())
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        mock_result = MagicMock()
        mock_result.data = [
            {"org_id": org_a, "role": "admin", "status": "active"},
            {"org_id": org_b, "role": "viewer", "status": "active"},
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result

        ctx = resolve_membership("user-multi")
        assert ctx.org_id == org_a

    @pytest.mark.unit
    @patch("backend.membership.is_supabase_configured", return_value=True)
    @patch("backend.database.get_supabase_client")
    def test_system_org_excluded_from_resolution(self, mock_client_fn, mock_configured):
        """Membership in system org is excluded from normal resolution."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        mock_result = MagicMock()
        mock_result.data = [
            {"org_id": str(SYSTEM_ORG_ID), "role": "owner", "status": "active"},
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result

        with pytest.raises(MembershipError):
            resolve_membership("system-only-user")

    @pytest.mark.unit
    @patch("backend.membership.is_supabase_configured", return_value=True)
    @patch("backend.database.get_supabase_client")
    def test_wrong_workspace_hint_falls_through(self, mock_client_fn, mock_configured):
        """preferred_org_id for a workspace user doesn't belong to → uses first."""
        real_org = str(uuid4())
        wrong_org = str(uuid4())
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        mock_result = MagicMock()
        mock_result.data = [
            {"org_id": real_org, "role": "editor", "status": "active"},
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result

        ctx = resolve_membership("user-x", preferred_org_id=wrong_org)
        assert ctx.org_id == real_org  # Falls through to first active

    @pytest.mark.unit
    @patch("backend.membership.is_supabase_configured", return_value=False)
    def test_db_not_configured_raises(self, mock_configured):
        """If DB is not configured, raises MembershipError with 503."""
        with pytest.raises(MembershipError) as exc_info:
            resolve_membership("user-1")
        assert exc_info.value.status_code == 503

    @pytest.mark.unit
    def test_resolve_or_none_returns_none_for_no_user(self):
        """resolve_membership_or_none(None) → None."""
        result = resolve_membership_or_none(None)
        assert result is None

    @pytest.mark.unit
    @patch("backend.membership.is_supabase_configured", return_value=True)
    @patch("backend.database.get_supabase_client")
    def test_resolve_or_none_returns_none_on_error(self, mock_client_fn, mock_configured):
        """resolve_membership_or_none returns None when no membership found."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        mock_result = MagicMock()
        mock_result.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result

        result = resolve_membership_or_none("user-no-org")
        assert result is None


# =============================================================================
# Cross-Tenant Isolation Tests
# =============================================================================


class TestCrossTenantIsolation:
    """Verify that membership resolution prevents cross-tenant access."""

    @pytest.mark.unit
    @patch("backend.membership.is_supabase_configured", return_value=True)
    @patch("backend.database.get_supabase_client")
    def test_user_cannot_access_other_org(self, mock_client_fn, mock_configured):
        """User can only resolve to orgs they have active membership in."""
        user_org = str(uuid4())
        other_org = str(uuid4())
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        mock_result = MagicMock()
        mock_result.data = [
            {"org_id": user_org, "role": "viewer", "status": "active"},
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result

        # Even if they pass other_org as preferred, they get their own org
        ctx = resolve_membership("user-1", preferred_org_id=other_org)
        assert ctx.org_id == user_org
        assert ctx.org_id != other_org

    @pytest.mark.unit
    def test_role_downgrade_enforcement(self):
        """A viewer context cannot escalate to admin operations."""
        from fastapi import HTTPException

        ctx = TenantContext(user_id="u", org_id="o", role=OrgRole.VIEWER)

        with pytest.raises(HTTPException) as exc_info:
            ctx.require_role(OrgRole.ADMIN)
        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_editor_cannot_perform_owner_actions(self):
        """An editor cannot escalate to owner."""
        from fastapi import HTTPException

        ctx = TenantContext(user_id="u", org_id="o", role=OrgRole.EDITOR)

        with pytest.raises(HTTPException):
            ctx.require_role(OrgRole.OWNER)


# =============================================================================
# MembershipStatus Tests
# =============================================================================


class TestMembershipStatus:
    """Test membership status enum values."""

    @pytest.mark.unit
    def test_all_statuses_defined(self):
        assert MembershipStatus.ACTIVE.value == "active"
        assert MembershipStatus.INVITED.value == "invited"
        assert MembershipStatus.SUSPENDED.value == "suspended"
        assert MembershipStatus.DEACTIVATED.value == "deactivated"

    @pytest.mark.unit
    def test_status_count(self):
        """Exactly 4 statuses defined — no accidental additions."""
        assert len(MembershipStatus) == 4
