"""Asset repository — tenant-scoped database access for Assets.

All queries are automatically filtered by org_id from TenantContext.
Cross-tenant access returns 404. The quarantined UUID is rejected with 422.

Requirements: R2.2, R2.6, R2.7, R2.8, R2.9, R2.10, R11.3, R11.10
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update

from app.db.tenant_scope import TenantScopedRepository
from app.models.asset import Asset

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AssetRepository(TenantScopedRepository):
    """Tenant-scoped repository for Asset entities.

    All operations are automatically scoped to the authenticated org_id.
    The org_id is resolved from TenantContext (JWT → org_members lookup)
    and never accepted from client request parameters.
    """

    def __init__(self, db: "AsyncSession", org_id: UUID) -> None:
        """Initialize with DB session and authenticated org_id."""
        super().__init__(db, org_id)

    async def get_by_id(self, asset_id: UUID) -> Asset:
        """Fetch a single asset by ID, scoped to authenticated org.

        Returns 404 if not found or belongs to different org (R2.6).
        """
        return await self._get_one(Asset, asset_id, "Asset")

    async def list_all(
        self,
        limit: int = 20,
        offset: int = 0,
        asset_type: str | None = None,
        talent_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> tuple[list[Asset], int]:
        """List assets for the authenticated org with optional filters.

        Args:
            limit: Maximum items per page (1-100).
            offset: Pagination offset.
            asset_type: Filter by asset type (image, video, audio, model).
            talent_id: Filter by associated talent.
            job_id: Filter by originating job.

        Returns:
            Tuple of (items, total_count) for this tenant only.
        """
        stmt = select(Asset)

        if asset_type is not None:
            stmt = stmt.where(Asset.asset_type == asset_type)

        if talent_id is not None:
            stmt = stmt.where(Asset.talent_id == talent_id)

        if job_id is not None:
            stmt = stmt.where(Asset.job_id == job_id)

        return await self._list(Asset, stmt, limit, offset)

    async def create(self, **kwargs: object) -> Asset:
        """Create a new asset record for the authenticated org.

        The org_id is automatically set from the repository context.
        """
        asset = Asset(org_id=self._org_id, **kwargs)
        self._db.add(asset)
        await self._db.flush()
        return asset

    async def soft_delete(self, asset_id: UUID) -> None:
        """Soft-delete an asset (sets deleted_at, doesn't remove storage)."""
        from datetime import UTC, datetime

        await self.get_by_id(asset_id)  # Verify ownership

        stmt = (
            update(Asset)
            .where(Asset.id == asset_id, Asset.org_id == self._org_id)
            .values(deleted_at=datetime.now(UTC))
        )
        await self._db.execute(stmt)

    async def exists(self, asset_id: UUID) -> bool:
        """Check if asset exists for the authenticated org."""
        return await self._exists(Asset, asset_id)
