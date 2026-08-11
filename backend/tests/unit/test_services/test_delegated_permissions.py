"""Unit tests for the DelegatedPermissionService.

Tests:
- Grant: creates permission with correct fields
- Revoke: marks permission as revoked, blocks double-revoke
- Check: validates active delegation considering expiry, revocation, cost, connection
- List: pagination, revoked filtering, tenant isolation

No I/O, no DB — all tested in-memory.

Validates: Requirements R30.14, R98.3
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.services.delegated_permission_service import (
    DelegatedPermission,
    DelegatedPermissionAlreadyRevokedError,
    DelegatedPermissionNotFoundError,
    DelegatedPermissionService,
)


# =============================================================================
# Helpers
# =============================================================================

ORG_A = uuid4()
ORG_B = uuid4()
USER_ID = uuid4()
CONNECTION_ID = uuid4()


def _make_service(permissions: list[DelegatedPermission] | None = None) -> DelegatedPermissionService:
    """Create an in-memory service for testing."""
    return DelegatedPermissionService(permissions=permissions or [])


# =============================================================================
# Tests — Grant Permission
# =============================================================================


@pytest.mark.unit
class TestGrantPermission:
    """Tests for DelegatedPermissionService.grant_permission."""

    @pytest.mark.asyncio
    async def test_grant_creates_permission(self) -> None:
        """Granting creates a permission with correct fields."""
        service = _make_service()

        perm = await service.grant_permission(
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            connection_scope=CONNECTION_ID,
            max_cost_usd=5.0,
            expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        )

        assert perm.org_id == ORG_A
        assert perm.delegated_by == USER_ID
        assert perm.action_class == "generate_image"
        assert perm.connection_scope == CONNECTION_ID
        assert perm.max_cost_usd == 5.0
        assert perm.expires_at == datetime(2030, 1, 1, tzinfo=timezone.utc)
        assert perm.revoked_at is None
        assert perm.is_active is True

    @pytest.mark.asyncio
    async def test_grant_without_optional_fields(self) -> None:
        """Granting without optional fields defaults to None."""
        service = _make_service()

        perm = await service.grant_permission(
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="schedule_post",
        )

        assert perm.connection_scope is None
        assert perm.max_cost_usd is None
        assert perm.expires_at is None
        assert perm.is_active is True

    @pytest.mark.asyncio
    async def test_grant_multiple_permissions(self) -> None:
        """Multiple permissions can be granted for different actions."""
        service = _make_service()

        p1 = await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )
        p2 = await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="schedule_post"
        )

        assert p1.id != p2.id
        assert p1.action_class == "generate_image"
        assert p2.action_class == "schedule_post"

        items, total = await service.list_permissions(org_id=ORG_A)
        assert total == 2


# =============================================================================
# Tests — Revoke Permission
# =============================================================================


@pytest.mark.unit
class TestRevokePermission:
    """Tests for DelegatedPermissionService.revoke_permission."""

    @pytest.mark.asyncio
    async def test_revoke_marks_permission_inactive(self) -> None:
        """Revoking sets revoked_at and makes permission inactive."""
        service = _make_service()
        perm = await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )

        revoked = await service.revoke_permission(
            permission_id=perm.id, org_id=ORG_A, revoked_by=USER_ID
        )

        assert revoked.revoked_at is not None
        assert revoked.is_active is False

    @pytest.mark.asyncio
    async def test_revoke_not_found_raises(self) -> None:
        """Revoking non-existent permission raises NotFoundError."""
        service = _make_service()

        with pytest.raises(DelegatedPermissionNotFoundError):
            await service.revoke_permission(
                permission_id=uuid4(), org_id=ORG_A, revoked_by=USER_ID
            )

    @pytest.mark.asyncio
    async def test_revoke_already_revoked_raises(self) -> None:
        """Revoking an already-revoked permission raises AlreadyRevokedError."""
        service = _make_service()
        perm = await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )
        await service.revoke_permission(
            permission_id=perm.id, org_id=ORG_A, revoked_by=USER_ID
        )

        with pytest.raises(DelegatedPermissionAlreadyRevokedError):
            await service.revoke_permission(
                permission_id=perm.id, org_id=ORG_A, revoked_by=USER_ID
            )

    @pytest.mark.asyncio
    async def test_revoke_wrong_org_raises_not_found(self) -> None:
        """Revoking with wrong org_id returns not found (tenant isolation)."""
        service = _make_service()
        perm = await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )

        with pytest.raises(DelegatedPermissionNotFoundError):
            await service.revoke_permission(
                permission_id=perm.id, org_id=ORG_B, revoked_by=USER_ID
            )


# =============================================================================
# Tests — Check Delegation
# =============================================================================


@pytest.mark.unit
class TestCheckDelegation:
    """Tests for DelegatedPermissionService.check_delegation."""

    @pytest.mark.asyncio
    async def test_check_active_delegation_returns_true(self) -> None:
        """Active delegation for matching action_class returns True."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )

        result = await service.check_delegation(org_id=ORG_A, action_class="generate_image")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_no_delegation_returns_false(self) -> None:
        """Missing delegation returns False."""
        service = _make_service()

        result = await service.check_delegation(org_id=ORG_A, action_class="generate_image")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_revoked_delegation_returns_false(self) -> None:
        """Revoked delegation returns False."""
        service = _make_service()
        perm = await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )
        await service.revoke_permission(
            permission_id=perm.id, org_id=ORG_A, revoked_by=USER_ID
        )

        result = await service.check_delegation(org_id=ORG_A, action_class="generate_image")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_expired_delegation_returns_false(self) -> None:
        """Expired delegation returns False."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),  # past
        )

        result = await service.check_delegation(org_id=ORG_A, action_class="generate_image")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_future_expiry_returns_true(self) -> None:
        """Delegation with future expiry returns True."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(days=30),
        )

        result = await service.check_delegation(org_id=ORG_A, action_class="generate_image")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_cost_within_limit_returns_true(self) -> None:
        """Cost within max_cost_usd returns True."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            max_cost_usd=5.0,
        )

        result = await service.check_delegation(
            org_id=ORG_A, action_class="generate_image", cost_usd=3.0
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_check_cost_exceeds_limit_returns_false(self) -> None:
        """Cost exceeding max_cost_usd returns False."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            max_cost_usd=5.0,
        )

        result = await service.check_delegation(
            org_id=ORG_A, action_class="generate_image", cost_usd=10.0
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_check_connection_scope_matches_returns_true(self) -> None:
        """Connection matching connection_scope returns True."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            connection_scope=CONNECTION_ID,
        )

        result = await service.check_delegation(
            org_id=ORG_A, action_class="generate_image", connection_id=CONNECTION_ID
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_check_connection_scope_mismatch_returns_false(self) -> None:
        """Connection not matching connection_scope returns False."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            connection_scope=CONNECTION_ID,
        )

        other_connection = uuid4()
        result = await service.check_delegation(
            org_id=ORG_A, action_class="generate_image", connection_id=other_connection
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_check_null_connection_scope_matches_any(self) -> None:
        """Delegation with NULL connection_scope matches any connection."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            connection_scope=None,
        )

        result = await service.check_delegation(
            org_id=ORG_A, action_class="generate_image", connection_id=uuid4()
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_check_wrong_org_returns_false(self) -> None:
        """Delegation for different org returns False (tenant isolation)."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )

        result = await service.check_delegation(org_id=ORG_B, action_class="generate_image")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_wrong_action_class_returns_false(self) -> None:
        """Delegation for different action class returns False."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )

        result = await service.check_delegation(org_id=ORG_A, action_class="schedule_post")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_scoped_delegation_no_connection_provided_returns_false(self) -> None:
        """Delegation scoped to connection but no connection_id provided returns False."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            connection_scope=CONNECTION_ID,
        )

        result = await service.check_delegation(
            org_id=ORG_A, action_class="generate_image", connection_id=None
        )
        assert result is False


# =============================================================================
# Tests — List Permissions
# =============================================================================


@pytest.mark.unit
class TestListPermissions:
    """Tests for DelegatedPermissionService.list_permissions."""

    @pytest.mark.asyncio
    async def test_list_empty_returns_empty(self) -> None:
        """Empty workspace returns no items."""
        service = _make_service()

        items, total = await service.list_permissions(org_id=ORG_A)
        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_returns_active_permissions(self) -> None:
        """List returns active permissions for the workspace."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )
        await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="schedule_post"
        )

        items, total = await service.list_permissions(org_id=ORG_A)
        assert total == 2
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_list_excludes_revoked_by_default(self) -> None:
        """List excludes revoked permissions by default."""
        service = _make_service()
        perm = await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )
        await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="schedule_post"
        )
        await service.revoke_permission(
            permission_id=perm.id, org_id=ORG_A, revoked_by=USER_ID
        )

        items, total = await service.list_permissions(org_id=ORG_A)
        assert total == 1
        assert items[0].action_class == "schedule_post"

    @pytest.mark.asyncio
    async def test_list_includes_revoked_when_requested(self) -> None:
        """List includes revoked permissions when include_revoked=True."""
        service = _make_service()
        perm = await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )
        await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="schedule_post"
        )
        await service.revoke_permission(
            permission_id=perm.id, org_id=ORG_A, revoked_by=USER_ID
        )

        items, total = await service.list_permissions(
            org_id=ORG_A, include_revoked=True
        )
        assert total == 2

    @pytest.mark.asyncio
    async def test_list_tenant_isolation(self) -> None:
        """List only returns permissions for the requested org."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )
        await service.grant_permission(
            org_id=ORG_B, delegated_by=USER_ID, action_class="schedule_post"
        )

        items_a, total_a = await service.list_permissions(org_id=ORG_A)
        items_b, total_b = await service.list_permissions(org_id=ORG_B)

        assert total_a == 1
        assert items_a[0].action_class == "generate_image"
        assert total_b == 1
        assert items_b[0].action_class == "schedule_post"

    @pytest.mark.asyncio
    async def test_list_pagination(self) -> None:
        """Pagination works correctly with limit and offset."""
        service = _make_service()
        for i in range(5):
            await service.grant_permission(
                org_id=ORG_A, delegated_by=USER_ID, action_class=f"action_{i}"
            )

        items, total = await service.list_permissions(org_id=ORG_A, limit=2, offset=0)
        assert total == 5
        assert len(items) == 2

        items2, total2 = await service.list_permissions(org_id=ORG_A, limit=2, offset=2)
        assert total2 == 5
        assert len(items2) == 2
        assert items[0].id != items2[0].id

    @pytest.mark.asyncio
    async def test_list_offset_beyond_total(self) -> None:
        """Offset beyond total returns empty items with correct total."""
        service = _make_service()
        await service.grant_permission(
            org_id=ORG_A, delegated_by=USER_ID, action_class="generate_image"
        )

        items, total = await service.list_permissions(org_id=ORG_A, limit=20, offset=100)
        assert total == 1
        assert items == []


# =============================================================================
# Tests — is_active property
# =============================================================================


@pytest.mark.unit
class TestIsActiveProperty:
    """Tests for DelegatedPermission.is_active property."""

    def test_active_when_no_revoke_no_expiry(self) -> None:
        """Permission with no revoke and no expiry is active."""
        perm = DelegatedPermission(
            id=uuid4(),
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            revoked_at=None,
            expires_at=None,
        )
        assert perm.is_active is True

    def test_inactive_when_revoked(self) -> None:
        """Revoked permission is inactive."""
        perm = DelegatedPermission(
            id=uuid4(),
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            revoked_at=datetime.now(tz=timezone.utc),
            expires_at=None,
        )
        assert perm.is_active is False

    def test_inactive_when_expired(self) -> None:
        """Expired permission is inactive."""
        perm = DelegatedPermission(
            id=uuid4(),
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            revoked_at=None,
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        assert perm.is_active is False

    def test_active_when_future_expiry(self) -> None:
        """Permission with future expiry is active."""
        perm = DelegatedPermission(
            id=uuid4(),
            org_id=ORG_A,
            delegated_by=USER_ID,
            action_class="generate_image",
            revoked_at=None,
            expires_at=datetime.now(tz=timezone.utc) + timedelta(days=30),
        )
        assert perm.is_active is True
