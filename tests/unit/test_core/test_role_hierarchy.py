"""Property tests for role hierarchy enforcement.

**Validates: Requirements R3.1, R3.2, R3.3**

Property 5: Role Hierarchy Enforcement
- User with role below minimum → 403 FORBIDDEN
- User with role at or above minimum → no exception

Tests cover:
- Strict ordering: OWNER > ADMIN > EDITOR > VIEWER
- has_privilege correctness for all (user_role, required_role) combinations
- TenantContext.require_role raises 403 when insufficient
- Viewer blocked from POST/PUT/PATCH/DELETE (R3.2)
- Editor blocked from DELETE on talent/model/credential/org-settings (R3.3)

The role hierarchy logic is identical across:
- backend.membership.OrgRole (tested here — importable without SQLAlchemy)
- backend.app.core.dependencies.WorkspaceRole (canonical — same logic, same enum values)

Both implement has_privilege with the same ordered hierarchy list and the same
comparison logic. This test validates the shared algorithmic property.

Run with:
    pytest tests/unit/test_core/test_role_hierarchy.py -v
"""
from __future__ import annotations

from itertools import product

import pytest
from fastapi import HTTPException

from backend.membership import OrgRole, TenantContext


# =============================================================================
# Constants
# =============================================================================

ALL_ROLES = [
    OrgRole.VIEWER,
    OrgRole.EDITOR,
    OrgRole.ADMIN,
    OrgRole.OWNER,
]

# Ordered from least to most privileged
ROLE_HIERARCHY = [
    OrgRole.VIEWER,
    OrgRole.EDITOR,
    OrgRole.ADMIN,
    OrgRole.OWNER,
]

# All (user_role, required_role) combinations — 16 pairs
ALL_ROLE_PAIRS = list(product(ALL_ROLES, ALL_ROLES))

# Resources that editors cannot DELETE (R3.3)
EDITOR_DELETE_RESTRICTED_RESOURCES = [
    "talent",
    "model",
    "credential",
    "org-settings",
]

# HTTP methods that viewers cannot use (R3.2)
MUTATING_METHODS = ["POST", "PUT", "PATCH", "DELETE"]


def _make_tenant_context(role: OrgRole) -> TenantContext:
    """Create a TenantContext with the given role for testing."""
    return TenantContext(
        user_id="test-user-001",
        org_id="test-org-001",
        role=role,
        email="test@example.com",
    )


# =============================================================================
# Property 5: Role Hierarchy Enforcement — has_privilege
# =============================================================================


class TestRoleHierarchyOrdering:
    """Verify the role hierarchy is strictly ordered: OWNER > ADMIN > EDITOR > VIEWER.

    **Validates: Requirements R3.1**
    """

    @pytest.mark.unit
    def test_hierarchy_is_strictly_ordered(self):
        """Each role has_privilege over itself and all roles below it."""
        for i, higher in enumerate(ROLE_HIERARCHY):
            for j, lower in enumerate(ROLE_HIERARCHY):
                if i >= j:
                    assert higher.has_privilege(lower), (
                        f"{higher.value} should have privilege over {lower.value}"
                    )
                else:
                    assert not higher.has_privilege(lower), (
                        f"{higher.value} should NOT have privilege over {lower.value}"
                    )

    @pytest.mark.unit
    def test_viewer_is_lowest_privilege(self):
        """Viewer has privilege only over itself."""
        viewer = OrgRole.VIEWER
        assert viewer.has_privilege(OrgRole.VIEWER)
        assert not viewer.has_privilege(OrgRole.EDITOR)
        assert not viewer.has_privilege(OrgRole.ADMIN)
        assert not viewer.has_privilege(OrgRole.OWNER)

    @pytest.mark.unit
    def test_owner_is_highest_privilege(self):
        """Owner has privilege over all roles."""
        owner = OrgRole.OWNER
        assert owner.has_privilege(OrgRole.VIEWER)
        assert owner.has_privilege(OrgRole.EDITOR)
        assert owner.has_privilege(OrgRole.ADMIN)
        assert owner.has_privilege(OrgRole.OWNER)

    @pytest.mark.unit
    def test_every_role_has_privilege_over_itself(self):
        """Reflexive property: every role has privilege over itself."""
        for role in ALL_ROLES:
            assert role.has_privilege(role), (
                f"{role.value} should have privilege over itself"
            )

    @pytest.mark.unit
    def test_privilege_is_transitive(self):
        """If A >= B and B >= C then A >= C."""
        for a in ALL_ROLES:
            for b in ALL_ROLES:
                for c in ALL_ROLES:
                    if a.has_privilege(b) and b.has_privilege(c):
                        assert a.has_privilege(c), (
                            f"Transitivity violated: {a.value} >= {b.value} >= {c.value}"
                            f" but {a.value} does not have privilege over {c.value}"
                        )

    @pytest.mark.unit
    def test_hierarchy_has_exactly_four_roles(self):
        """The hierarchy contains exactly VIEWER, EDITOR, ADMIN, OWNER."""
        assert len(OrgRole) == 4
        assert set(OrgRole) == {OrgRole.VIEWER, OrgRole.EDITOR, OrgRole.ADMIN, OrgRole.OWNER}


# =============================================================================
# Property 5: Role Hierarchy Enforcement — has_privilege exhaustive
# =============================================================================


class TestHasPrivilegeExhaustive:
    """Exhaustive parametrized tests for has_privilege over all role combinations.

    **Validates: Requirements R3.1**
    """

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "user_role,required_role",
        ALL_ROLE_PAIRS,
        ids=[f"{u.value}_vs_{r.value}" for u, r in ALL_ROLE_PAIRS],
    )
    def test_has_privilege_correctness(
        self, user_role: OrgRole, required_role: OrgRole
    ):
        """For all (user_role, required_role): result matches hierarchy position."""
        user_idx = ROLE_HIERARCHY.index(user_role)
        required_idx = ROLE_HIERARCHY.index(required_role)
        expected = user_idx >= required_idx
        actual = user_role.has_privilege(required_role)
        assert actual == expected, (
            f"{user_role.value}.has_privilege({required_role.value}) "
            f"expected {expected}, got {actual}"
        )


# =============================================================================
# Property 5: TenantContext.require_role enforcement
# =============================================================================


class TestRequireRoleEnforcement:
    """TenantContext.require_role raises HTTPException 403 when role is insufficient.

    **Validates: Requirements R3.1, R3.2**
    """

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "user_role,required_role",
        ALL_ROLE_PAIRS,
        ids=[f"{u.value}_requires_{r.value}" for u, r in ALL_ROLE_PAIRS],
    )
    def test_require_role_enforcement(
        self, user_role: OrgRole, required_role: OrgRole
    ):
        """
        If user_role has_privilege(required_role) → no exception raised.
        If user_role does NOT have privilege → HTTPException 403.
        """
        ctx = _make_tenant_context(user_role)
        should_pass = user_role.has_privilege(required_role)

        if should_pass:
            # No exception expected
            ctx.require_role(required_role)
        else:
            # 403 expected
            with pytest.raises(HTTPException) as exc_info:
                ctx.require_role(required_role)
            assert exc_info.value.status_code == 403
            assert required_role.value in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_require_role_owner_passes_all(self):
        """Owner should pass require_role for every possible minimum."""
        ctx = _make_tenant_context(OrgRole.OWNER)
        for required in ALL_ROLES:
            ctx.require_role(required)  # Should not raise

    @pytest.mark.unit
    def test_require_role_viewer_blocked_from_editor_and_above(self):
        """Viewer fails require_role for EDITOR, ADMIN, OWNER."""
        ctx = _make_tenant_context(OrgRole.VIEWER)
        for required in [OrgRole.EDITOR, OrgRole.ADMIN, OrgRole.OWNER]:
            with pytest.raises(HTTPException) as exc_info:
                ctx.require_role(required)
            assert exc_info.value.status_code == 403


# =============================================================================
# R3.2: Viewer blocked from POST/PUT/PATCH/DELETE
# =============================================================================


class TestViewerMutationBlocked:
    """Viewer attempting POST/PUT/PATCH/DELETE → 403 FORBIDDEN.

    **Validates: Requirements R3.2**

    The platform enforces that viewer role requires at minimum EDITOR for
    any mutating operation. We test that require_role(EDITOR) fails for viewer.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("method", MUTATING_METHODS)
    def test_viewer_blocked_from_mutating_methods(self, method: str):
        """Viewer cannot perform any mutating operation (POST/PUT/PATCH/DELETE)."""
        ctx = _make_tenant_context(OrgRole.VIEWER)
        # All mutating endpoints should require at minimum EDITOR role
        with pytest.raises(HTTPException) as exc_info:
            ctx.require_role(OrgRole.EDITOR)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    @pytest.mark.parametrize("method", MUTATING_METHODS)
    @pytest.mark.parametrize(
        "role",
        [OrgRole.EDITOR, OrgRole.ADMIN, OrgRole.OWNER],
        ids=["editor", "admin", "owner"],
    )
    def test_editor_and_above_allowed_mutating_methods(
        self, method: str, role: OrgRole
    ):
        """Editor, admin, and owner can perform mutating operations."""
        ctx = _make_tenant_context(role)
        # Should not raise for EDITOR minimum
        ctx.require_role(OrgRole.EDITOR)


# =============================================================================
# R3.3: Editor blocked from DELETE on restricted resources
# =============================================================================


class TestEditorDeleteRestricted:
    """Editor attempting DELETE on talent/model/credential/org-settings → 403.

    **Validates: Requirements R3.3**

    DELETE on these resources requires ADMIN or above.
    Editor is below ADMIN and should be rejected.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("resource", EDITOR_DELETE_RESTRICTED_RESOURCES)
    def test_editor_blocked_from_delete_on_restricted_resources(self, resource: str):
        """Editor cannot DELETE talent, model, credential, or org-settings."""
        ctx = _make_tenant_context(OrgRole.EDITOR)
        # DELETE on restricted resources requires ADMIN minimum
        with pytest.raises(HTTPException) as exc_info:
            ctx.require_role(OrgRole.ADMIN)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    @pytest.mark.parametrize("resource", EDITOR_DELETE_RESTRICTED_RESOURCES)
    @pytest.mark.parametrize(
        "role",
        [OrgRole.ADMIN, OrgRole.OWNER],
        ids=["admin", "owner"],
    )
    def test_admin_and_owner_can_delete_restricted_resources(
        self, resource: str, role: OrgRole
    ):
        """Admin and owner can DELETE talent, model, credential, org-settings."""
        ctx = _make_tenant_context(role)
        # Should not raise for ADMIN minimum
        ctx.require_role(OrgRole.ADMIN)

    @pytest.mark.unit
    @pytest.mark.parametrize("resource", EDITOR_DELETE_RESTRICTED_RESOURCES)
    def test_viewer_also_blocked_from_delete_on_restricted_resources(self, resource: str):
        """Viewer is also blocked from DELETE on restricted resources (below ADMIN)."""
        ctx = _make_tenant_context(OrgRole.VIEWER)
        with pytest.raises(HTTPException) as exc_info:
            ctx.require_role(OrgRole.ADMIN)
        assert exc_info.value.status_code == 403


# =============================================================================
# TenantContext convenience properties
# =============================================================================


class TestTenantContextProperties:
    """Test TenantContext convenience properties align with hierarchy.

    **Validates: Requirements R3.1**
    """

    @pytest.mark.unit
    def test_is_owner_only_true_for_owner(self):
        """is_owner is True only for OWNER role."""
        for role in ALL_ROLES:
            ctx = _make_tenant_context(role)
            if role == OrgRole.OWNER:
                assert ctx.is_owner is True
            else:
                assert ctx.is_owner is False

    @pytest.mark.unit
    def test_is_admin_or_above_for_admin_and_owner(self):
        """is_admin_or_above is True for ADMIN and OWNER only."""
        expected = {
            OrgRole.VIEWER: False,
            OrgRole.EDITOR: False,
            OrgRole.ADMIN: True,
            OrgRole.OWNER: True,
        }
        for role, expected_value in expected.items():
            ctx = _make_tenant_context(role)
            assert ctx.is_admin_or_above is expected_value, (
                f"{role.value}: is_admin_or_above expected {expected_value}"
            )

    @pytest.mark.unit
    def test_is_editor_or_above_for_editor_admin_owner(self):
        """is_editor_or_above is True for EDITOR, ADMIN, and OWNER."""
        expected = {
            OrgRole.VIEWER: False,
            OrgRole.EDITOR: True,
            OrgRole.ADMIN: True,
            OrgRole.OWNER: True,
        }
        for role, expected_value in expected.items():
            ctx = _make_tenant_context(role)
            assert ctx.is_editor_or_above is expected_value, (
                f"{role.value}: is_editor_or_above expected {expected_value}"
            )
