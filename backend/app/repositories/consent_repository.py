"""Consent repository — tenant-scoped database access for consent records.

All queries are automatically filtered by org_id from TenantContext.
Cross-tenant access returns 404. The quarantined UUID is rejected with 422.

Requirements: R2.2, R2.6, R10.2, R10.3, A2-004
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update

from app.db.tenant_scope import TenantScopedRepository
from app.models.consent import ConsentRecord

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ConsentRepository(TenantScopedRepository):
    """Tenant-scoped repository for consent records.

    All operations are automatically scoped to the authenticated org_id.
    The org_id is resolved from TenantContext (JWT → org_members lookup)
    and never accepted from client request parameters.

    Usage:
        repo = ConsentRepository(db=session, org_id=tenant.org_id)
        record = await repo.get_by_id(consent_id)
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

    async def get_by_id(self, consent_id: UUID) -> ConsentRecord:
        """Fetch a single consent record by ID, scoped to authenticated org.

        Args:
            consent_id: The consent record UUID.

        Returns:
            ConsentRecord instance if found and owned by this tenant.

        Raises:
            HTTPException: 404 if not found or belongs to different org.
        """
        return await self._get_one(ConsentRecord, consent_id, "Consent record")

    async def list_all(
        self,
        limit: int = 20,
        offset: int = 0,
        talent_id: UUID | None = None,
        scope: str | None = None,
        active_only: bool = False,
    ) -> tuple[list[ConsentRecord], int]:
        """List consent records for the authenticated org with optional filters.

        Args:
            limit: Maximum items per page (1-100).
            offset: Pagination offset.
            talent_id: Filter by specific talent.
            scope: Filter by scope (contains).
            active_only: If True, exclude revoked/expired records.

        Returns:
            Tuple of (items, total_count) for this tenant only.
        """
        stmt = select(ConsentRecord)

        if talent_id is not None:
            stmt = stmt.where(ConsentRecord.talent_id == talent_id)

        if scope is not None:
            stmt = stmt.where(ConsentRecord.scopes.any(scope))

        if active_only:
            stmt = stmt.where(ConsentRecord.revoked_at.is_(None))

        return await self._list(ConsentRecord, stmt, limit, offset)

    async def create(self, **kwargs: object) -> ConsentRecord:
        """Create a new consent record for the authenticated org.

        The org_id is automatically set from the repository's authenticated
        context — never from client-supplied values.

        Args:
            **kwargs: ConsentRecord attributes.

        Returns:
            The created ConsentRecord instance.
        """
        record = ConsentRecord(org_id=self._org_id, **kwargs)
        self._db.add(record)
        await self._db.flush()
        return record

    async def update(self, consent_id: UUID, **kwargs: object) -> ConsentRecord:
        """Update a consent record owned by the authenticated org.

        Fetches first to verify ownership (returns 404 for cross-tenant),
        then applies the update.

        Args:
            consent_id: The consent record UUID to update.
            **kwargs: Fields to update.

        Returns:
            The updated ConsentRecord instance.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        record = await self.get_by_id(consent_id)

        for key, value in kwargs.items():
            if hasattr(record, key):
                setattr(record, key, value)

        await self._db.flush()
        return record

    async def revoke(
        self, consent_id: UUID, revocation_reason: str
    ) -> ConsentRecord:
        """Revoke a consent record. Preserves the record for audit.

        Revocation prevents FUTURE use but does NOT falsify historical
        audit records. The record remains with revoked_at timestamp.

        Args:
            consent_id: The consent record UUID to revoke.
            revocation_reason: Reason for revocation.

        Returns:
            The revoked ConsentRecord instance.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        record = await self.get_by_id(consent_id)
        record.revoked_at = datetime.now(UTC)
        record.revocation_reason = revocation_reason
        await self._db.flush()
        return record

    async def get_next_version(self, talent_id: UUID) -> int:
        """Get the next version number for a talent's consent records.

        Args:
            talent_id: The talent UUID.

        Returns:
            The next version number (max existing + 1, or 1 if none exist).
        """
        from sqlalchemy import func

        stmt = (
            select(func.coalesce(func.max(ConsentRecord.version), 0))
            .where(
                ConsentRecord.org_id == self._org_id,
                ConsentRecord.talent_id == talent_id,
            )
        )
        max_version = await self._db.scalar(stmt) or 0
        return max_version + 1

    async def get_active_for_talent(
        self, talent_id: UUID, scope: str | None = None
    ) -> list[ConsentRecord]:
        """Get active (non-revoked, non-expired) consent records for a talent.

        Used by the enforcement layer to check consent before operations.

        Args:
            talent_id: The talent UUID.
            scope: Optional scope to filter by.

        Returns:
            List of active consent records.
        """
        stmt = (
            select(ConsentRecord)
            .where(
                ConsentRecord.org_id == self._org_id,
                ConsentRecord.talent_id == talent_id,
                ConsentRecord.revoked_at.is_(None),
            )
        )

        if scope is not None:
            stmt = stmt.where(ConsentRecord.scopes.any(scope))

        # Exclude expired records
        stmt = stmt.where(
            (ConsentRecord.expires_at.is_(None))
            | (ConsentRecord.expires_at > datetime.now(UTC))
        )

        result = await self._db.execute(stmt)
        return list(result.scalars().all())
