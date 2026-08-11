"""Social Analytics Service — business logic for social intelligence.

Provides CRUD and query operations for social accounts, content, metrics,
watchlists, derived insights, and experiments.

Key rules:
    - All queries scoped by org_id (tenant isolation)
    - Missing metrics represented as UNAVAILABLE — never fabricated
    - Provenance tracked on all metric observations
    - DERIVED_ANALYSIS never presented as FIRST_PARTY_CONNECTED

Validates: Requirements R107.2, R107.3, R107.4, R107.10, R43.11, R43.12
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, select

from app.core.logging import get_logger
from app.models.social_analytics import (
    SocialAccount,
    SocialContent,
    SocialDerivedInsight,
    SocialExperiment,
    SocialMetricSnapshot,
    SocialWatchlist,
    SocialWatchlistMember,
)
from backend.social_analytics.schemas import (
    ExperimentCreate,
    SyncTriggerRequest,
    WatchlistCreate,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


class SocialAnalyticsService:
    """Service for social analytics operations.

    All queries enforce tenant isolation via org_id filtering.
    Missing metrics use UNAVAILABLE — values are never fabricated.

    Args:
        db: SQLAlchemy async session.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # =========================================================================
    # Social Accounts
    # =========================================================================

    async def list_accounts(
        self,
        org_id: UUID,
        *,
        platform: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SocialAccount], int]:
        """List connected social accounts for a workspace.

        Args:
            org_id: Organisation scope for tenant isolation.
            platform: Optional platform filter.
            limit: Max items to return.
            offset: Pagination offset.

        Returns:
            Tuple of (items, total_count).
        """
        conditions = [SocialAccount.org_id == org_id]
        if platform:
            conditions.append(SocialAccount.platform == platform)

        count_stmt = (
            select(func.count())
            .select_from(SocialAccount)
            .where(and_(*conditions))
        )
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            select(SocialAccount)
            .where(and_(*conditions))
            .order_by(SocialAccount.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        logger.info(
            "social_accounts_listed",
            org_id=str(org_id),
            total=total,
            platform=platform,
        )
        return items, total

    # =========================================================================
    # Social Content
    # =========================================================================

    async def list_content(
        self,
        org_id: UUID,
        *,
        platform: str | None = None,
        account_id: UUID | None = None,
        talent_id: UUID | None = None,
        content_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SocialContent], int]:
        """List social content items for a workspace.

        Args:
            org_id: Organisation scope for tenant isolation.
            platform: Optional platform filter.
            account_id: Optional social account filter.
            talent_id: Optional talent filter.
            content_type: Optional content type filter.
            limit: Max items to return.
            offset: Pagination offset.

        Returns:
            Tuple of (items, total_count).
        """
        conditions = [SocialContent.org_id == org_id]
        if platform:
            conditions.append(SocialContent.platform == platform)
        if account_id:
            conditions.append(SocialContent.social_account_id == account_id)
        if talent_id:
            conditions.append(SocialContent.talent_id == talent_id)
        if content_type:
            conditions.append(SocialContent.content_type == content_type)

        count_stmt = (
            select(func.count())
            .select_from(SocialContent)
            .where(and_(*conditions))
        )
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            select(SocialContent)
            .where(and_(*conditions))
            .order_by(SocialContent.published_at.desc().nulls_last())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # =========================================================================
    # Metrics
    # =========================================================================

    async def list_metrics(
        self,
        org_id: UUID,
        *,
        account_id: UUID | None = None,
        content_id: UUID | None = None,
        provenance: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SocialMetricSnapshot], int]:
        """List metric snapshots for a workspace.

        Missing metrics are represented as UNAVAILABLE in the response layer —
        this service returns only metrics that exist. The API layer adds
        UNAVAILABLE markers for requested-but-absent metrics.

        Args:
            org_id: Organisation scope for tenant isolation.
            account_id: Optional filter by social account.
            content_id: Optional filter by content item.
            provenance: Optional filter by data provenance.
            limit: Max items to return.
            offset: Pagination offset.

        Returns:
            Tuple of (items, total_count).
        """
        conditions = [SocialMetricSnapshot.org_id == org_id]
        if account_id:
            conditions.append(SocialMetricSnapshot.social_account_id == account_id)
        if content_id:
            conditions.append(SocialMetricSnapshot.social_content_id == content_id)
        if provenance:
            conditions.append(SocialMetricSnapshot.provenance == provenance)

        count_stmt = (
            select(func.count())
            .select_from(SocialMetricSnapshot)
            .where(and_(*conditions))
        )
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            select(SocialMetricSnapshot)
            .where(and_(*conditions))
            .order_by(SocialMetricSnapshot.snapshot_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # =========================================================================
    # Watchlists
    # =========================================================================

    async def list_watchlists(
        self,
        org_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SocialWatchlist], int]:
        """List watchlists for a workspace.

        Args:
            org_id: Organisation scope for tenant isolation.
            limit: Max items to return.
            offset: Pagination offset.

        Returns:
            Tuple of (items, total_count).
        """
        conditions = [SocialWatchlist.org_id == org_id]

        count_stmt = (
            select(func.count())
            .select_from(SocialWatchlist)
            .where(and_(*conditions))
        )
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            select(SocialWatchlist)
            .where(and_(*conditions))
            .order_by(SocialWatchlist.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def create_watchlist(
        self,
        org_id: UUID,
        data: WatchlistCreate,
    ) -> SocialWatchlist:
        """Create a new watchlist with optional initial members.

        Args:
            org_id: Organisation scope for tenant isolation.
            data: Watchlist creation data.

        Returns:
            The created watchlist ORM instance.
        """
        watchlist = SocialWatchlist(
            org_id=org_id,
            name=data.name,
            description=data.description,
            category=data.category,
        )
        self.db.add(watchlist)
        await self.db.flush()

        # Add initial members if provided
        for member_data in data.members:
            member = SocialWatchlistMember(
                org_id=org_id,
                watchlist_id=watchlist.id,
                account_identifier=member_data.account_identifier,
                watch_type=member_data.watch_type.value,
                platform=member_data.platform.value if member_data.platform else None,
                display_name=member_data.display_name,
                notes=member_data.notes,
            )
            self.db.add(member)

        await self.db.commit()
        await self.db.refresh(watchlist)

        logger.info(
            "watchlist_created",
            org_id=str(org_id),
            watchlist_id=str(watchlist.id),
            name=data.name,
            member_count=len(data.members),
        )
        return watchlist

    async def get_watchlist_members(
        self,
        org_id: UUID,
        watchlist_id: UUID,
    ) -> list[SocialWatchlistMember]:
        """Get members for a specific watchlist.

        Args:
            org_id: Organisation scope for tenant isolation.
            watchlist_id: The watchlist to retrieve members for.

        Returns:
            List of watchlist members.
        """
        stmt = (
            select(SocialWatchlistMember)
            .where(
                SocialWatchlistMember.org_id == org_id,
                SocialWatchlistMember.watchlist_id == watchlist_id,
            )
            .order_by(SocialWatchlistMember.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # =========================================================================
    # Intelligence (Derived Insights)
    # =========================================================================

    async def list_insights(
        self,
        org_id: UUID,
        *,
        insight_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SocialDerivedInsight], int]:
        """List derived intelligence insights for a workspace.

        Provenance is preserved — DERIVED_ANALYSIS is never misrepresented
        as FIRST_PARTY_CONNECTED.

        Args:
            org_id: Organisation scope for tenant isolation.
            insight_type: Optional filter by insight type.
            limit: Max items to return.
            offset: Pagination offset.

        Returns:
            Tuple of (items, total_count).
        """
        conditions = [SocialDerivedInsight.org_id == org_id]
        if insight_type:
            conditions.append(SocialDerivedInsight.insight_type == insight_type)

        count_stmt = (
            select(func.count())
            .select_from(SocialDerivedInsight)
            .where(and_(*conditions))
        )
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            select(SocialDerivedInsight)
            .where(and_(*conditions))
            .order_by(SocialDerivedInsight.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # =========================================================================
    # Experiments
    # =========================================================================

    async def list_experiments(
        self,
        org_id: UUID,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SocialExperiment], int]:
        """List content experiments for a workspace.

        Args:
            org_id: Organisation scope for tenant isolation.
            status: Optional status filter.
            limit: Max items to return.
            offset: Pagination offset.

        Returns:
            Tuple of (items, total_count).
        """
        conditions = [SocialExperiment.org_id == org_id]
        if status:
            conditions.append(SocialExperiment.status == status)

        count_stmt = (
            select(func.count())
            .select_from(SocialExperiment)
            .where(and_(*conditions))
        )
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            select(SocialExperiment)
            .where(and_(*conditions))
            .order_by(SocialExperiment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def create_experiment(
        self,
        org_id: UUID,
        data: ExperimentCreate,
    ) -> SocialExperiment:
        """Create a new content experiment.

        Args:
            org_id: Organisation scope for tenant isolation.
            data: Experiment creation data.

        Returns:
            The created experiment ORM instance.
        """
        experiment = SocialExperiment(
            org_id=org_id,
            name=data.name,
            hypothesis=data.hypothesis,
            status="draft",
            content_variants=data.content_variants,
            target_metric=data.target_metric,
            observation_window=data.observation_window,
            linked_content_ids=data.linked_content_ids,
        )
        self.db.add(experiment)
        await self.db.commit()
        await self.db.refresh(experiment)

        logger.info(
            "experiment_created",
            org_id=str(org_id),
            experiment_id=str(experiment.id),
            name=data.name,
        )
        return experiment

    # =========================================================================
    # Sync
    # =========================================================================

    async def trigger_sync(
        self,
        org_id: UUID,
        data: SyncTriggerRequest,
    ) -> tuple[str, int]:
        """Trigger a manual metrics sync for connected accounts.

        This queues sync operations for the specified accounts. In the current
        implementation, sync is simulated (no real provider connected yet).

        Args:
            org_id: Organisation scope for tenant isolation.
            data: Sync trigger parameters.

        Returns:
            Tuple of (status_message, accounts_queued_count).
        """
        conditions = [SocialAccount.org_id == org_id]
        if data.account_id:
            conditions.append(SocialAccount.id == data.account_id)
        if data.platform:
            conditions.append(SocialAccount.platform == data.platform.value)

        count_stmt = (
            select(func.count())
            .select_from(SocialAccount)
            .where(and_(*conditions))
        )
        accounts_count = await self.db.scalar(count_stmt) or 0

        if accounts_count == 0:
            return "No matching accounts found for sync", 0

        logger.info(
            "sync_triggered",
            org_id=str(org_id),
            accounts_count=accounts_count,
            account_id=str(data.account_id) if data.account_id else None,
            platform=data.platform.value if data.platform else None,
        )

        return "Sync queued for processing", accounts_count
