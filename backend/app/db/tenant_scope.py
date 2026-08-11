"""Tenant-scoped query enforcement utilities.

Provides constants, validators, and a base repository class that ensures all
database queries are always scoped to the authenticated organization. This module
is the single enforcement point for requirements R2.2, R2.6, R2.7, R2.8, R2.9, R2.10.

Key rules:
    - org_id is NEVER accepted from client request parameters
    - org_id is ALWAYS derived from TenantContext (JWT → org_members lookup)
    - Cross-tenant access returns 404 (not 403) to prevent information leakage
    - The quarantined UUID (all zeros) is rejected with 422

Usage:
    from app.db.tenant_scope import (
        QUARANTINED_ORG_ID,
        TenantScopedRepository,
        validate_org_id,
        tenant_filter,
        get_tenant_resource,
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, select

from app.core.logging import get_logger
from app.db.base import Base

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

QUARANTINED_ORG_ID: UUID = UUID("00000000-0000-0000-0000-000000000000")
"""Quarantined placeholder UUID that must never be used as an org_id.

Any request referencing this UUID is rejected with HTTP 422.
See R2.8 and the quarantine process defined in R69.
"""

# Type variable for ORM model classes that have an org_id column
TModel = TypeVar("TModel", bound=Base)


# =============================================================================
# Validation
# =============================================================================


def validate_org_id(org_id: UUID) -> None:
    """Reject the quarantined UUID with HTTP 422.

    This MUST be called at the service layer boundary before any query
    that uses org_id. The quarantined UUID is a placeholder from legacy
    data that is never valid for runtime operations.

    Args:
        org_id: The organization UUID to validate (from TenantContext).

    Raises:
        HTTPException: 422 if org_id is the quarantined UUID.

    Validates: R2.8
    """
    if org_id == QUARANTINED_ORG_ID:
        logger.warning(
            "quarantined_org_id_rejected",
            org_id=str(org_id),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid organization identifier. The provided org_id is a reserved placeholder and cannot be used.",
            headers={"X-Error-Code": "QUARANTINED_ORG_ID"},
        )


# =============================================================================
# Query Helpers
# =============================================================================


def tenant_filter(stmt: Select, model: type, org_id: UUID) -> Select:
    """Add a WHERE org_id = :authenticated_org_id clause to a query.

    This helper enforces tenant isolation at the query level. It validates
    the org_id first and then appends the filter.

    Args:
        stmt: An existing SQLAlchemy Select statement.
        model: The ORM model class (must have an org_id column).
        org_id: The authenticated org_id from TenantContext.

    Returns:
        The modified Select with the org_id WHERE clause applied.

    Raises:
        HTTPException: 422 if org_id is the quarantined UUID.

    Validates: R2.2, R2.8
    """
    validate_org_id(org_id)
    return stmt.where(model.org_id == org_id)


async def get_tenant_resource(
    db: "AsyncSession",
    model: type[TModel],
    resource_id: UUID,
    org_id: UUID,
    resource_name: str = "Resource",
) -> TModel:
    """Fetch a single resource scoped to the authenticated tenant.

    If the resource does not exist OR belongs to a different org, returns
    HTTP 404 (not 403) to prevent information leakage about resource existence
    in other tenants.

    Args:
        db: The async database session.
        model: The ORM model class (must have id and org_id columns).
        resource_id: The resource UUID to fetch.
        org_id: The authenticated org_id from TenantContext.
        resource_name: Human-readable name for error messages (e.g., "Talent").

    Returns:
        The ORM model instance if found and owned by the org.

    Raises:
        HTTPException: 422 if org_id is the quarantined UUID.
        HTTPException: 404 if resource not found or belongs to different org.

    Validates: R2.6, R2.8
    """
    validate_org_id(org_id)

    stmt = select(model).where(
        model.id == resource_id,
        model.org_id == org_id,
    )

    # Include soft-delete filter if the model supports it
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))

    result = await db.execute(stmt)
    resource = result.scalar_one_or_none()

    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource_name} not found",
        )

    return resource


# =============================================================================
# Base Repository
# =============================================================================


class TenantScopedRepository:
    """Base repository enforcing tenant isolation on all queries.

    All repository classes should inherit from this base. It provides:
    - Automatic org_id validation (rejects quarantined UUID)
    - Scoped list queries (always filter by org_id)
    - Scoped single-resource fetch (returns 404 for cross-tenant)
    - Scoped count queries

    The org_id is stored at construction time and derived from TenantContext,
    never from client-supplied request parameters.

    Usage:
        class TalentRepository(TenantScopedRepository):
            def __init__(self, db: AsyncSession, org_id: UUID) -> None:
                super().__init__(db, org_id)

            async def get_by_id(self, talent_id: UUID) -> AiTalent:
                return await self._get_one(AiTalent, talent_id, "Talent")

            async def list_all(self, limit: int, offset: int) -> tuple[list[AiTalent], int]:
                stmt = select(AiTalent)
                return await self._list(AiTalent, stmt, limit, offset)

    Validates: R2.2, R2.6, R2.7, R2.8, R2.9, R2.10
    """

    def __init__(self, db: "AsyncSession", org_id: UUID) -> None:
        """Initialize with a database session and the authenticated org_id.

        Args:
            db: SQLAlchemy async session.
            org_id: Organization UUID from TenantContext (never client-supplied).

        Raises:
            HTTPException: 422 if org_id is the quarantined UUID.
        """
        validate_org_id(org_id)
        self._db = db
        self._org_id = org_id

    @property
    def org_id(self) -> UUID:
        """The authenticated org_id for this repository instance."""
        return self._org_id

    @property
    def db(self) -> "AsyncSession":
        """The database session for this repository instance."""
        return self._db

    async def _get_one(
        self,
        model: type[TModel],
        resource_id: UUID,
        resource_name: str = "Resource",
    ) -> TModel:
        """Fetch a single resource with tenant isolation.

        Args:
            model: ORM model class with id and org_id columns.
            resource_id: The resource UUID.
            resource_name: Name for 404 error messages.

        Returns:
            The model instance if found and owned by this tenant.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        return await get_tenant_resource(
            db=self._db,
            model=model,
            resource_id=resource_id,
            org_id=self._org_id,
            resource_name=resource_name,
        )

    async def _list(
        self,
        model: type[TModel],
        stmt: Select,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[TModel], int]:
        """Execute a list query with mandatory tenant filtering.

        Automatically adds WHERE org_id = :authenticated_org_id and
        applies pagination. Returns both items and total count for
        the authenticated tenant only (R2.9).

        Args:
            model: ORM model class.
            stmt: Base select statement (filters will be added).
            limit: Maximum items (default 20, max 100).
            offset: Pagination offset (default 0).

        Returns:
            Tuple of (items list, total count for this tenant).
        """
        from sqlalchemy import func

        # Apply tenant filter
        scoped_stmt = tenant_filter(stmt, model, self._org_id)

        # Apply soft-delete filter if supported
        if hasattr(model, "deleted_at"):
            scoped_stmt = scoped_stmt.where(model.deleted_at.is_(None))

        # Get total count
        count_stmt = select(func.count()).select_from(
            scoped_stmt.subquery()
        )
        total = await self._db.scalar(count_stmt) or 0

        # Apply pagination and ordering
        if hasattr(model, "created_at"):
            scoped_stmt = scoped_stmt.order_by(model.created_at.desc())

        paginated_stmt = scoped_stmt.limit(limit).offset(offset)
        result = await self._db.execute(paginated_stmt)
        items = list(result.scalars().all())

        return items, total

    async def _exists(self, model: type[TModel], resource_id: UUID) -> bool:
        """Check if a resource exists for this tenant.

        Args:
            model: ORM model class.
            resource_id: UUID to check.

        Returns:
            True if the resource exists and belongs to this tenant.
        """
        from sqlalchemy import func

        stmt = select(func.count()).select_from(model).where(
            model.id == resource_id,
            model.org_id == self._org_id,
        )

        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))

        count = await self._db.scalar(stmt) or 0
        return count > 0
