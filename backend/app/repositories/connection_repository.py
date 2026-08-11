"""Connection repository — tenant-scoped database access for connections.

All queries are automatically filtered by org_id from TenantContext.
USER_CONNECTIONs additionally filter by user_id for ownership enforcement.
Cross-tenant access returns 404.

Requirements: R2.2, R2.6, R85.1, R85.3, R92.1, R92.2, R92.3
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select, update

from app.core.logging import get_logger
from app.db.tenant_scope import TenantScopedRepository, tenant_filter
from app.models.connection import Connection, ConnectionLifecycle

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


class ConnectionRepository(TenantScopedRepository):
    """Tenant-scoped repository for Connection entities.

    All operations are automatically scoped to the authenticated org_id.
    USER_CONNECTIONs are additionally filtered by user_id where appropriate.

    Requirements: R2.2, R85.1, R92.1, R92.2
    """

    def __init__(self, db: "AsyncSession", org_id: UUID) -> None:
        """Initialize with DB session and authenticated org_id."""
        super().__init__(db, org_id)

    async def get_by_id(self, connection_id: UUID) -> Connection:
        """Fetch a single connection by ID, scoped to authenticated org.

        Returns 404 if not found or belongs to different org (R2.6).
        """
        return await self._get_one(Connection, connection_id, "Connection")

    async def list_all(
        self,
        limit: int = 20,
        offset: int = 0,
        category: str | None = None,
        ownership: str | None = None,
        lifecycle_state: str | None = None,
        user_id: UUID | None = None,
    ) -> tuple[list[Connection], int]:
        """List connections with optional filters.

        Args:
            limit: Maximum items to return.
            offset: Pagination offset.
            category: Filter by connection category.
            ownership: Filter by ownership type (user/workspace).
            lifecycle_state: Filter by lifecycle state.
            user_id: Filter by user_id (for user connections).

        Returns:
            Tuple of (items, total_count).
        """
        stmt = select(Connection)

        if category:
            stmt = stmt.where(Connection.category == category)
        if ownership:
            stmt = stmt.where(Connection.ownership == ownership)
        if lifecycle_state:
            stmt = stmt.where(Connection.lifecycle_state == lifecycle_state)
        if user_id:
            stmt = stmt.where(Connection.user_id == user_id)

        return await self._list(Connection, stmt, limit, offset)

    async def create(self, **kwargs: object) -> Connection:
        """Create a new connection record.

        org_id is set from the repository's authenticated context.

        Args:
            **kwargs: Connection field values.

        Returns:
            The created Connection instance.
        """
        connection = Connection(org_id=self._org_id, **kwargs)
        self._db.add(connection)
        await self._db.flush()
        await self._db.refresh(connection)
        logger.info(
            "connection_created",
            connection_id=str(connection.id),
            org_id=str(self._org_id),
            provider_name=str(kwargs.get("provider_name", "")),
            auth_method=str(kwargs.get("auth_method", "")),
        )
        return connection

    async def update_lifecycle_state(
        self,
        connection_id: UUID,
        new_state: str,
    ) -> Connection:
        """Update the lifecycle state of a connection.

        Args:
            connection_id: The connection UUID.
            new_state: The new lifecycle state value.

        Returns:
            The updated Connection instance.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        connection = await self.get_by_id(connection_id)
        connection.lifecycle_state = new_state
        connection.updated_at = datetime.now(tz=UTC)
        await self._db.flush()
        await self._db.refresh(connection)
        logger.info(
            "connection_lifecycle_updated",
            connection_id=str(connection_id),
            org_id=str(self._org_id),
            new_state=new_state,
        )
        return connection

    async def update_fields(
        self,
        connection_id: UUID,
        **kwargs: object,
    ) -> Connection:
        """Update arbitrary fields on a connection.

        Args:
            connection_id: The connection UUID.
            **kwargs: Field name/value pairs to update.

        Returns:
            The updated Connection instance.
        """
        connection = await self.get_by_id(connection_id)
        for field, value in kwargs.items():
            if value is not None:
                setattr(connection, field, value)
        connection.updated_at = datetime.now(tz=UTC)
        await self._db.flush()
        await self._db.refresh(connection)
        return connection

    async def update_health(
        self,
        connection_id: UUID,
        health_status: str,
    ) -> Connection:
        """Update health check results for a connection.

        Args:
            connection_id: The connection UUID.
            health_status: The health check result (healthy/degraded/unreachable).

        Returns:
            The updated Connection instance.
        """
        connection = await self.get_by_id(connection_id)
        connection.health_status = health_status
        connection.last_health_check_at = datetime.now(tz=UTC)
        connection.updated_at = datetime.now(tz=UTC)
        await self._db.flush()
        await self._db.refresh(connection)
        return connection

    async def delete(self, connection_id: UUID) -> None:
        """Hard-delete a connection.

        Connections are hard-deleted (no soft-delete) because revocation
        is handled via lifecycle state. The deletion removes the record
        entirely including any credential references.

        Args:
            connection_id: The connection UUID to delete.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        connection = await self.get_by_id(connection_id)
        await self._db.delete(connection)
        await self._db.flush()
        logger.info(
            "connection_deleted",
            connection_id=str(connection_id),
            org_id=str(self._org_id),
        )

    async def find_by_provider(
        self,
        provider_name: str,
        ownership: str | None = None,
        user_id: UUID | None = None,
    ) -> Connection | None:
        """Find an existing connection for a provider.

        Used for deduplication — avoids duplicate connections to the same
        provider within a workspace.

        Args:
            provider_name: The provider identifier.
            ownership: Optional ownership filter.
            user_id: Optional user_id filter.

        Returns:
            The Connection if found, else None.
        """
        stmt = select(Connection).where(
            Connection.org_id == self._org_id,
            Connection.provider_name == provider_name,
        )
        if ownership:
            stmt = stmt.where(Connection.ownership == ownership)
        if user_id:
            stmt = stmt.where(Connection.user_id == user_id)

        # Exclude revoked/disconnected from dedup
        stmt = stmt.where(
            Connection.lifecycle_state.notin_([
                ConnectionLifecycle.DISCONNECTED.value,
                ConnectionLifecycle.REVOKED.value,
            ])
        )

        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
