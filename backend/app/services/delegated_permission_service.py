"""Delegated Permission Service.

Manages capability-specific delegated permissions that allow Hermes
to execute actions autonomously within configured limits.

Delegated permissions are:
    - Capability-specific (scoped to named action classes)
    - Connection-specific (scoped to named integrations, or NULL for all)
    - Revocable (immediately via revoked_at timestamp)
    - Auditable (full trail of grants and revocations)
    - Role-scoped (cannot exceed delegator's own permissions)
    - Subject to the Governance Boundary (R59)

Validates: Requirements R30.14, R98.3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(frozen=True)
class DelegatedPermission:
    """Represents a single delegated permission grant.

    Attributes:
        id: Unique identifier.
        org_id: Workspace this delegation belongs to.
        delegated_by: User who granted the delegation.
        action_class: The action type delegated (e.g. 'generate_image').
        connection_scope: Specific connection UUID, or None for any.
        max_cost_usd: Per-action cost limit, or None for no limit.
        expires_at: Expiration timestamp, or None for no expiry.
        revoked_at: Revocation timestamp, or None if still active.
        created_at: When the delegation was granted.
        updated_at: Last update timestamp.
    """

    id: UUID
    org_id: UUID
    delegated_by: UUID
    action_class: str
    connection_scope: UUID | None = None
    max_cost_usd: float | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    @property
    def is_active(self) -> bool:
        """Check whether this delegation is currently active.

        A delegation is active when it has not been revoked and has not
        expired (or has no expiry set).
        """
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            now = datetime.now(tz=timezone.utc)
            return now < self.expires_at
        return True


# =============================================================================
# Errors
# =============================================================================


class DelegatedPermissionNotFoundError(Exception):
    """Raised when a delegated permission is not found."""

    def __init__(self, permission_id: UUID) -> None:
        self.permission_id = permission_id
        super().__init__(f"Delegated permission not found: {permission_id}")


class DelegatedPermissionAlreadyRevokedError(Exception):
    """Raised when attempting to revoke an already-revoked permission."""

    def __init__(self, permission_id: UUID) -> None:
        self.permission_id = permission_id
        super().__init__(f"Delegated permission already revoked: {permission_id}")


# =============================================================================
# Service
# =============================================================================


class DelegatedPermissionService:
    """Manages delegated permission lifecycle.

    Provides:
    1. grant_permission() — create a new delegation
    2. revoke_permission() — immediately revoke a delegation
    3. check_delegation() — check if a specific action is delegated
    4. list_permissions() — paginated listing of all delegations

    Constructor modes:
    - DelegatedPermissionService(db=session) — production, DB-backed
    - DelegatedPermissionService(permissions=...) — testing, in-memory

    Validates: Requirements R30.14, R98.3
    """

    def __init__(
        self,
        db: "AsyncSession | None" = None,
        permissions: list[DelegatedPermission] | None = None,
    ) -> None:
        self._db = db
        if permissions is not None:
            self._in_memory = True
            self._permissions: list[DelegatedPermission] = list(permissions)
        else:
            self._in_memory = False
            self._permissions = []

    # =========================================================================
    # Grant
    # =========================================================================

    async def grant_permission(
        self,
        org_id: UUID,
        delegated_by: UUID,
        action_class: str,
        connection_scope: UUID | None = None,
        max_cost_usd: float | None = None,
        expires_at: datetime | None = None,
    ) -> DelegatedPermission:
        """Grant a new delegated permission.

        Creates a new delegation allowing Hermes to autonomously execute
        the specified action_class within the configured limits.

        Args:
            org_id: Workspace granting the delegation.
            delegated_by: User granting the delegation.
            action_class: Action class to delegate (e.g. 'generate_image').
            connection_scope: Optional specific connection to scope to.
            max_cost_usd: Optional per-action cost limit.
            expires_at: Optional expiration timestamp.

        Returns:
            The created DelegatedPermission.
        """
        if self._in_memory:
            import uuid as _uuid

            now = datetime.now(tz=timezone.utc)
            perm = DelegatedPermission(
                id=_uuid.uuid4(),
                org_id=org_id,
                delegated_by=delegated_by,
                action_class=action_class,
                connection_scope=connection_scope,
                max_cost_usd=max_cost_usd,
                expires_at=expires_at,
                revoked_at=None,
                created_at=now,
                updated_at=now,
            )
            self._permissions.append(perm)

            logger.info(
                "delegated_permission_granted",
                org_id=str(org_id),
                delegated_by=str(delegated_by),
                action_class=action_class,
                connection_scope=str(connection_scope) if connection_scope else None,
                max_cost_usd=max_cost_usd,
                permission_id=str(perm.id),
            )
            return perm

        if self._db is None:
            raise RuntimeError("No database session available")

        from app.models.delegated_permission import DelegatedPermissionModel

        row = DelegatedPermissionModel(
            org_id=org_id,
            delegated_by=delegated_by,
            action_class=action_class,
            connection_scope=connection_scope,
            max_cost_usd=max_cost_usd,
            expires_at=expires_at,
            revoked_at=None,
        )
        self._db.add(row)
        await self._db.flush()

        logger.info(
            "delegated_permission_granted",
            org_id=str(org_id),
            delegated_by=str(delegated_by),
            action_class=action_class,
            connection_scope=str(connection_scope) if connection_scope else None,
            max_cost_usd=max_cost_usd,
            permission_id=str(row.id),
        )

        return DelegatedPermission(
            id=row.id,
            org_id=row.org_id,
            delegated_by=row.delegated_by,
            action_class=row.action_class,
            connection_scope=row.connection_scope,
            max_cost_usd=float(row.max_cost_usd) if row.max_cost_usd is not None else None,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    # =========================================================================
    # Revoke
    # =========================================================================

    async def revoke_permission(
        self,
        permission_id: UUID,
        org_id: UUID,
        revoked_by: UUID,
    ) -> DelegatedPermission:
        """Revoke a delegated permission immediately.

        Sets revoked_at to the current timestamp, making the delegation
        inactive. Revocation is immediate and cannot be undone.

        Args:
            permission_id: The delegation to revoke.
            org_id: Workspace scope (enforces tenant isolation).
            revoked_by: User revoking the delegation.

        Returns:
            The updated DelegatedPermission.

        Raises:
            DelegatedPermissionNotFoundError: If permission not found for this org.
            DelegatedPermissionAlreadyRevokedError: If already revoked.
        """
        if self._in_memory:
            for i, perm in enumerate(self._permissions):
                if perm.id == permission_id and perm.org_id == org_id:
                    if perm.revoked_at is not None:
                        raise DelegatedPermissionAlreadyRevokedError(permission_id)

                    now = datetime.now(tz=timezone.utc)
                    revoked = DelegatedPermission(
                        id=perm.id,
                        org_id=perm.org_id,
                        delegated_by=perm.delegated_by,
                        action_class=perm.action_class,
                        connection_scope=perm.connection_scope,
                        max_cost_usd=perm.max_cost_usd,
                        expires_at=perm.expires_at,
                        revoked_at=now,
                        created_at=perm.created_at,
                        updated_at=now,
                    )
                    self._permissions[i] = revoked

                    logger.info(
                        "delegated_permission_revoked",
                        org_id=str(org_id),
                        permission_id=str(permission_id),
                        revoked_by=str(revoked_by),
                        action_class=perm.action_class,
                    )
                    return revoked

            raise DelegatedPermissionNotFoundError(permission_id)

        if self._db is None:
            raise RuntimeError("No database session available")

        from sqlalchemy import select

        from app.models.delegated_permission import DelegatedPermissionModel

        stmt = select(DelegatedPermissionModel).where(
            DelegatedPermissionModel.id == permission_id,
            DelegatedPermissionModel.org_id == org_id,
        )
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            raise DelegatedPermissionNotFoundError(permission_id)

        if row.revoked_at is not None:
            raise DelegatedPermissionAlreadyRevokedError(permission_id)

        now = datetime.now(tz=timezone.utc)
        row.revoked_at = now
        await self._db.flush()

        logger.info(
            "delegated_permission_revoked",
            org_id=str(org_id),
            permission_id=str(permission_id),
            revoked_by=str(revoked_by),
            action_class=row.action_class,
        )

        return DelegatedPermission(
            id=row.id,
            org_id=row.org_id,
            delegated_by=row.delegated_by,
            action_class=row.action_class,
            connection_scope=row.connection_scope,
            max_cost_usd=float(row.max_cost_usd) if row.max_cost_usd is not None else None,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    # =========================================================================
    # Check Delegation
    # =========================================================================

    async def check_delegation(
        self,
        org_id: UUID,
        action_class: str,
        cost_usd: float | None = None,
        connection_id: UUID | None = None,
    ) -> bool:
        """Check if a specific action is delegated and within limits.

        Evaluates whether the action_class has an active (non-expired,
        non-revoked) delegation for the workspace, optionally checking
        that cost_usd does not exceed max_cost_usd and that connection_id
        matches the connection_scope.

        Args:
            org_id: Workspace to check delegation for.
            action_class: The action being evaluated.
            cost_usd: The cost of the proposed action (optional).
            connection_id: The connection being used (optional).

        Returns:
            True if a valid active delegation exists, False otherwise.
        """
        if self._in_memory:
            return self._check_in_memory(org_id, action_class, cost_usd, connection_id)

        if self._db is None:
            return False

        from sqlalchemy import select

        from app.models.delegated_permission import DelegatedPermissionModel

        now = datetime.now(tz=timezone.utc)

        stmt = select(DelegatedPermissionModel).where(
            DelegatedPermissionModel.org_id == org_id,
            DelegatedPermissionModel.action_class == action_class,
            DelegatedPermissionModel.revoked_at.is_(None),
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        for row in rows:
            # Check expiration
            if row.expires_at is not None and now >= row.expires_at:
                continue

            # Check connection scope
            if row.connection_scope is not None and connection_id is not None:
                if row.connection_scope != connection_id:
                    continue
            elif row.connection_scope is not None and connection_id is None:
                # Delegation scoped to specific connection but no connection provided
                continue

            # Check cost limit
            if row.max_cost_usd is not None and cost_usd is not None:
                if cost_usd > float(row.max_cost_usd):
                    continue

            # All checks passed — delegation is valid
            return True

        return False

    def _check_in_memory(
        self,
        org_id: UUID,
        action_class: str,
        cost_usd: float | None,
        connection_id: UUID | None,
    ) -> bool:
        """In-memory check for testing."""
        now = datetime.now(tz=timezone.utc)

        for perm in self._permissions:
            if perm.org_id != org_id:
                continue
            if perm.action_class != action_class:
                continue
            if perm.revoked_at is not None:
                continue
            if perm.expires_at is not None and now >= perm.expires_at:
                continue

            # Check connection scope
            if perm.connection_scope is not None and connection_id is not None:
                if perm.connection_scope != connection_id:
                    continue
            elif perm.connection_scope is not None and connection_id is None:
                continue

            # Check cost limit
            if perm.max_cost_usd is not None and cost_usd is not None:
                if cost_usd > perm.max_cost_usd:
                    continue

            return True

        return False

    # =========================================================================
    # List
    # =========================================================================

    async def list_permissions(
        self,
        org_id: UUID,
        limit: int = 20,
        offset: int = 0,
        include_revoked: bool = False,
    ) -> tuple[list[DelegatedPermission], int]:
        """List delegated permissions for a workspace with pagination.

        Args:
            org_id: Workspace to list delegations for.
            limit: Maximum items to return (1-100).
            offset: Number of items to skip.
            include_revoked: If True, include revoked delegations.

        Returns:
            Tuple of (items, total_count).
        """
        if self._in_memory:
            return self._list_in_memory(org_id, limit, offset, include_revoked)

        if self._db is None:
            return [], 0

        from sqlalchemy import func as sa_func
        from sqlalchemy import select

        from app.models.delegated_permission import DelegatedPermissionModel

        # Build base filter
        base_filter = [DelegatedPermissionModel.org_id == org_id]
        if not include_revoked:
            base_filter.append(DelegatedPermissionModel.revoked_at.is_(None))

        # Count query
        count_stmt = (
            select(sa_func.count())
            .select_from(DelegatedPermissionModel)
            .where(*base_filter)
        )
        total = await self._db.scalar(count_stmt) or 0

        # Data query
        stmt = (
            select(DelegatedPermissionModel)
            .where(*base_filter)
            .order_by(DelegatedPermissionModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        rows = list(result.scalars().all())

        items = [
            DelegatedPermission(
                id=row.id,
                org_id=row.org_id,
                delegated_by=row.delegated_by,
                action_class=row.action_class,
                connection_scope=row.connection_scope,
                max_cost_usd=float(row.max_cost_usd) if row.max_cost_usd is not None else None,
                expires_at=row.expires_at,
                revoked_at=row.revoked_at,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

        return items, total

    def _list_in_memory(
        self,
        org_id: UUID,
        limit: int,
        offset: int,
        include_revoked: bool,
    ) -> tuple[list[DelegatedPermission], int]:
        """In-memory list for testing."""
        filtered = [
            p for p in self._permissions
            if p.org_id == org_id and (include_revoked or p.revoked_at is None)
        ]
        # Sort by created_at descending
        filtered.sort(key=lambda p: p.created_at, reverse=True)
        total = len(filtered)
        items = filtered[offset : offset + limit]
        return items, total
