"""Talent repository — tenant-scoped database access for AI Talent.

All queries are automatically filtered by org_id from TenantContext.
Cross-tenant access returns 404. The quarantined UUID is rejected with 422.

Requirements: R2.2, R2.6, R2.7, R2.8, R2.9, R2.10, R10.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update

from app.db.tenant_scope import TenantScopedRepository
from app.models.talent import AiTalent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TalentRepository(TenantScopedRepository):
    """Tenant-scoped repository for AI Talent entities.

    All operations are automatically scoped to the authenticated org_id.
    The org_id is resolved from TenantContext (JWT → org_members lookup)
    and never accepted from client request parameters.

    Usage:
        repo = TalentRepository(db=session, org_id=tenant.org_id)
        talent = await repo.get_by_id(talent_id)
        items, total = await repo.list_all(limit=20, offset=0)
    """

    def __init__(self, db: "AsyncSession", org_id: UUID) -> None:
        """Initialize with DB session and authenticated org_id.

        Args:
            db: SQLAlchemy async session.
            org_id: Organization UUID from TenantContext (never client-supplied).

        Raises:
            HTTPException: 422 if org_id is the quarantined UUID.
        """
        super().__init__(db, org_id)

    async def get_by_id(self, talent_id: UUID) -> AiTalent:
        """Fetch a single talent by ID, scoped to authenticated org.

        Args:
            talent_id: The talent UUID.

        Returns:
            AiTalent instance if found and owned by this tenant.

        Raises:
            HTTPException: 404 if not found or belongs to different org.
        """
        return await self._get_one(AiTalent, talent_id, "Talent")

    async def list_all(
        self,
        limit: int = 20,
        offset: int = 0,
        is_active: bool | None = None,
        talent_type: str | None = None,
    ) -> tuple[list[AiTalent], int]:
        """List talent for the authenticated org with optional filters.

        Args:
            limit: Maximum items per page (1-100).
            offset: Pagination offset.
            is_active: Filter by active status.
            talent_type: Filter by talent type.

        Returns:
            Tuple of (items, total_count) for this tenant only.
        """
        stmt = select(AiTalent)

        if is_active is not None:
            stmt = stmt.where(AiTalent.is_active == is_active)

        if talent_type is not None:
            stmt = stmt.where(AiTalent.talent_type == talent_type)

        return await self._list(AiTalent, stmt, limit, offset)

    async def create(self, **kwargs: object) -> AiTalent:
        """Create a new talent record for the authenticated org.

        The org_id is automatically set from the repository's authenticated
        context — never from client-supplied values.

        Args:
            **kwargs: Talent attributes (name, description, type, etc.)

        Returns:
            The created AiTalent instance.
        """
        talent = AiTalent(org_id=self._org_id, **kwargs)
        self._db.add(talent)
        await self._db.flush()
        return talent

    async def update(self, talent_id: UUID, **kwargs: object) -> AiTalent:
        """Update a talent record owned by the authenticated org.

        Fetches first to verify ownership (returns 404 for cross-tenant),
        then applies the update.

        Args:
            talent_id: The talent UUID to update.
            **kwargs: Fields to update.

        Returns:
            The updated AiTalent instance.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        talent = await self.get_by_id(talent_id)

        for key, value in kwargs.items():
            if hasattr(talent, key):
                setattr(talent, key, value)

        await self._db.flush()
        return talent

    async def soft_delete(self, talent_id: UUID) -> None:
        """Soft-delete a talent record owned by the authenticated org.

        Sets deleted_at timestamp. The record is excluded from subsequent
        queries via the SoftDeleteMixin filter in _list and _get_one.

        Args:
            talent_id: The talent UUID to delete.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        from datetime import UTC, datetime

        # Verify ownership first (raises 404 for cross-tenant)
        await self.get_by_id(talent_id)

        stmt = (
            update(AiTalent)
            .where(AiTalent.id == talent_id, AiTalent.org_id == self._org_id)
            .values(deleted_at=datetime.now(UTC))
        )
        await self._db.execute(stmt)

    async def exists(self, talent_id: UUID) -> bool:
        """Check if talent exists for the authenticated org.

        Args:
            talent_id: The talent UUID.

        Returns:
            True if exists and belongs to this tenant.
        """
        return await self._exists(AiTalent, talent_id)
