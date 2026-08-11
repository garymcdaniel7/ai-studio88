"""Competitive intelligence service — watchlist management and public insights.

Provides business logic for:
    - CRUD on watchlists and watchlist members
    - Querying publicly available competitive metrics
    - Generating derived insights from public data
    - Source attribution for all intelligence data

All data is from publicly available sources. Private analytics from connected
accounts are never exposed through this service.

Rate limit awareness: external platform data requests respect ToS and limits.

Validates: Requirements R108.1, R108.2, R108.3, R108.4, R108.5,
           R108.6, R108.7, R108.8, R108.10
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.social_analytics import (
    SocialDerivedInsight,
    SocialWatchlist,
    SocialWatchlistMember,
)


# =============================================================================
# Exceptions
# =============================================================================


class WatchlistNotFoundError(Exception):
    """Raised when a watchlist does not exist or belongs to another org."""

    pass


class WatchlistMemberNotFoundError(Exception):
    """Raised when a watchlist member does not exist."""

    pass


class RateLimitExceededError(Exception):
    """Raised when external platform rate limits are hit."""

    def __init__(self, platform: str, retry_after_seconds: int | None = None) -> None:
        self.platform = platform
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Rate limit exceeded for {platform}. "
            f"Retry after {retry_after_seconds}s." if retry_after_seconds else ""
        )


# =============================================================================
# Service
# =============================================================================


class CompetitiveIntelligenceService:
    """Service for competitive intelligence and watchlist management.

    All competitive intelligence data comes from publicly available sources.
    This service never accesses private analytics from connected accounts.
    Source attribution is mandatory for all returned data.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─────────────────────────────────────────────────────────────────────────
    # Watchlist CRUD
    # ─────────────────────────────────────────────────────────────────────────

    async def create_watchlist(
        self,
        org_id: UUID,
        name: str,
        description: str | None = None,
        category: str | None = None,
    ) -> SocialWatchlist:
        """Create a new watchlist for the workspace.

        Args:
            org_id: Workspace org ID (from TenantContext).
            name: Watchlist name.
            description: Optional description.
            category: Optional category label.

        Returns:
            The created SocialWatchlist instance.
        """
        watchlist = SocialWatchlist(
            org_id=org_id,
            name=name,
            description=description,
            category=category,
        )
        self.db.add(watchlist)
        await self.db.flush()
        await self.db.refresh(watchlist)
        return watchlist

    async def get_watchlist(self, org_id: UUID, watchlist_id: UUID) -> SocialWatchlist:
        """Get a single watchlist by ID, scoped to org.

        Raises:
            WatchlistNotFoundError: If not found for this org.
        """
        stmt = select(SocialWatchlist).where(
            SocialWatchlist.org_id == org_id,
            SocialWatchlist.id == watchlist_id,
        )
        result = await self.db.execute(stmt)
        watchlist = result.scalar_one_or_none()
        if watchlist is None:
            raise WatchlistNotFoundError(
                f"Watchlist {watchlist_id} not found"
            )
        return watchlist

    async def list_watchlists(
        self,
        org_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SocialWatchlist], int]:
        """List watchlists for the workspace with pagination.

        Returns:
            Tuple of (items, total_count).
        """
        count_stmt = (
            select(func.count())
            .select_from(SocialWatchlist)
            .where(SocialWatchlist.org_id == org_id)
        )
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            select(SocialWatchlist)
            .where(SocialWatchlist.org_id == org_id)
            .order_by(SocialWatchlist.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def update_watchlist(
        self,
        org_id: UUID,
        watchlist_id: UUID,
        name: str | None = None,
        description: str | None = None,
        category: str | None = None,
    ) -> SocialWatchlist:
        """Update a watchlist's metadata.

        Raises:
            WatchlistNotFoundError: If not found for this org.
        """
        watchlist = await self.get_watchlist(org_id, watchlist_id)
        if name is not None:
            watchlist.name = name
        if description is not None:
            watchlist.description = description
        if category is not None:
            watchlist.category = category
        await self.db.flush()
        await self.db.refresh(watchlist)
        return watchlist

    async def delete_watchlist(self, org_id: UUID, watchlist_id: UUID) -> None:
        """Delete a watchlist and all its members.

        Raises:
            WatchlistNotFoundError: If not found for this org.
        """
        watchlist = await self.get_watchlist(org_id, watchlist_id)

        # Delete all members first
        members_stmt = select(SocialWatchlistMember).where(
            SocialWatchlistMember.watchlist_id == watchlist_id,
            SocialWatchlistMember.org_id == org_id,
        )
        result = await self.db.execute(members_stmt)
        for member in result.scalars().all():
            await self.db.delete(member)

        await self.db.delete(watchlist)
        await self.db.flush()

    # ─────────────────────────────────────────────────────────────────────────
    # Watchlist Member CRUD
    # ─────────────────────────────────────────────────────────────────────────

    async def add_member(
        self,
        org_id: UUID,
        watchlist_id: UUID,
        watch_type: str,
        account_identifier: str,
        display_name: str | None = None,
        platform: str | None = None,
        notes: str | None = None,
    ) -> SocialWatchlistMember:
        """Add a member to a watchlist.

        Validates that the watchlist exists and belongs to the org.

        Raises:
            WatchlistNotFoundError: If watchlist not found for this org.
        """
        # Verify watchlist belongs to this org
        await self.get_watchlist(org_id, watchlist_id)

        member = SocialWatchlistMember(
            org_id=org_id,
            watchlist_id=watchlist_id,
            watch_type=watch_type,
            account_identifier=account_identifier,
            display_name=display_name,
            platform=platform,
            notes=notes,
        )
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def get_member(
        self,
        org_id: UUID,
        member_id: UUID,
    ) -> SocialWatchlistMember:
        """Get a single watchlist member by ID, scoped to org.

        Raises:
            WatchlistMemberNotFoundError: If not found for this org.
        """
        stmt = select(SocialWatchlistMember).where(
            SocialWatchlistMember.org_id == org_id,
            SocialWatchlistMember.id == member_id,
        )
        result = await self.db.execute(stmt)
        member = result.scalar_one_or_none()
        if member is None:
            raise WatchlistMemberNotFoundError(
                f"Watchlist member {member_id} not found"
            )
        return member

    async def list_members(
        self,
        org_id: UUID,
        watchlist_id: UUID,
        limit: int = 20,
        offset: int = 0,
        watch_type: str | None = None,
    ) -> tuple[list[SocialWatchlistMember], int]:
        """List members for a watchlist with optional type filter.

        Raises:
            WatchlistNotFoundError: If watchlist not found for this org.

        Returns:
            Tuple of (items, total_count).
        """
        # Verify watchlist exists
        await self.get_watchlist(org_id, watchlist_id)

        base_filter = [
            SocialWatchlistMember.org_id == org_id,
            SocialWatchlistMember.watchlist_id == watchlist_id,
        ]
        if watch_type:
            base_filter.append(SocialWatchlistMember.watch_type == watch_type)

        count_stmt = (
            select(func.count())
            .select_from(SocialWatchlistMember)
            .where(*base_filter)
        )
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            select(SocialWatchlistMember)
            .where(*base_filter)
            .order_by(SocialWatchlistMember.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def update_member(
        self,
        org_id: UUID,
        member_id: UUID,
        display_name: str | None = None,
        notes: str | None = None,
    ) -> SocialWatchlistMember:
        """Update a watchlist member's display name or notes.

        Raises:
            WatchlistMemberNotFoundError: If not found for this org.
        """
        member = await self.get_member(org_id, member_id)
        if display_name is not None:
            member.display_name = display_name
        if notes is not None:
            member.notes = notes
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def remove_member(self, org_id: UUID, member_id: UUID) -> None:
        """Remove a member from a watchlist.

        Raises:
            WatchlistMemberNotFoundError: If not found for this org.
        """
        member = await self.get_member(org_id, member_id)
        await self.db.delete(member)
        await self.db.flush()

    async def get_member_count(self, org_id: UUID, watchlist_id: UUID) -> int:
        """Get count of members in a watchlist."""
        stmt = (
            select(func.count())
            .select_from(SocialWatchlistMember)
            .where(
                SocialWatchlistMember.org_id == org_id,
                SocialWatchlistMember.watchlist_id == watchlist_id,
            )
        )
        return await self.db.scalar(stmt) or 0

    # ─────────────────────────────────────────────────────────────────────────
    # Competitive Intelligence Queries
    # ─────────────────────────────────────────────────────────────────────────

    async def get_competitor_profile(
        self,
        org_id: UUID,
        member_id: UUID,
    ) -> dict[str, Any]:
        """Get publicly available profile data for a watchlist member.

        Returns estimated public metrics. Never returns private analytics.
        All data includes source attribution (R108.7).

        Raises:
            WatchlistMemberNotFoundError: If member not found.
        """
        member = await self.get_member(org_id, member_id)

        # Generate public metrics based on watch_type.
        # In a full implementation, this would query external public APIs
        # or cached public data. For now, we return a structured response
        # that can be populated by social intelligence providers.
        metrics = self._build_public_metrics(member)

        return {
            "member_id": member.id,
            "account_identifier": member.account_identifier,
            "display_name": member.display_name,
            "platform": member.platform,
            "watch_type": member.watch_type,
            "metrics": metrics,
            "data_source": "PUBLIC_PLATFORM_DATA",
            "data_freshness": "estimated",
            "last_observed_at": None,
            "disclaimers": [
                "Metrics are publicly available estimates, not private analytics.",
                "Engagement rates are calculated from publicly visible data.",
            ],
        }

    async def get_watchlist_intelligence(
        self,
        org_id: UUID,
        watchlist_id: UUID,
    ) -> dict[str, Any]:
        """Get aggregated competitive intelligence for a watchlist.

        Collects public profiles and derived insights for all members
        in the watchlist. All data includes provenance attribution.

        Raises:
            WatchlistNotFoundError: If watchlist not found.
        """
        watchlist = await self.get_watchlist(org_id, watchlist_id)

        # Get all members
        members_stmt = (
            select(SocialWatchlistMember)
            .where(
                SocialWatchlistMember.org_id == org_id,
                SocialWatchlistMember.watchlist_id == watchlist_id,
            )
            .order_by(SocialWatchlistMember.created_at.desc())
        )
        result = await self.db.execute(members_stmt)
        members = list(result.scalars().all())

        # Build profiles for each member
        profiles = []
        for member in members:
            metrics = self._build_public_metrics(member)
            profiles.append({
                "member_id": member.id,
                "account_identifier": member.account_identifier,
                "display_name": member.display_name,
                "platform": member.platform,
                "watch_type": member.watch_type,
                "metrics": metrics,
                "data_source": "PUBLIC_PLATFORM_DATA",
                "data_freshness": "estimated",
                "last_observed_at": None,
                "disclaimers": [
                    "Metrics are publicly available estimates, not private analytics."
                ],
            })

        # Get derived insights for this watchlist's members
        insights = await self._get_derived_insights(org_id, watchlist_id)

        return {
            "watchlist_id": watchlist.id,
            "watchlist_name": watchlist.name,
            "profiles": profiles,
            "insights": insights,
            "data_sources": ["PUBLIC_PLATFORM_DATA"],
            "rate_limit_status": "ok",
            "disclaimers": [
                "All metrics are from publicly available data.",
                "Engagement rates are estimates based on public observations.",
                "This is not private analytics from connected accounts.",
            ],
        }

    async def _get_derived_insights(
        self,
        org_id: UUID,
        watchlist_id: UUID,
    ) -> list[dict[str, Any]]:
        """Get derived insights related to watchlist members.

        Only returns non-expired insights with full provenance.
        """
        # Get member IDs for this watchlist
        member_ids_stmt = (
            select(SocialWatchlistMember.id)
            .where(
                SocialWatchlistMember.org_id == org_id,
                SocialWatchlistMember.watchlist_id == watchlist_id,
            )
        )
        result = await self.db.execute(member_ids_stmt)
        member_ids = [row[0] for row in result.all()]

        if not member_ids:
            return []

        # Query derived insights for these members
        now = datetime.now(UTC)
        insights_stmt = (
            select(SocialDerivedInsight)
            .where(
                SocialDerivedInsight.org_id == org_id,
                SocialDerivedInsight.subject_id.in_(member_ids),
            )
            .where(
                # Only non-expired insights
                (SocialDerivedInsight.expires_at.is_(None))
                | (SocialDerivedInsight.expires_at > now)
            )
            .order_by(SocialDerivedInsight.created_at.desc())
            .limit(20)
        )
        result = await self.db.execute(insights_stmt)
        insight_rows = list(result.scalars().all())

        return [
            {
                "id": insight.id,
                "insight_type": insight.insight_type,
                "subject_identifier": str(insight.subject_id),
                "content": insight.content,
                "confidence": float(insight.confidence) if insight.confidence else None,
                "provenance": insight.provenance,
                "reasoning_class": "DERIVED_METRIC",
                "evidence_summary": None,
                "created_at": insight.created_at,
            }
            for insight in insight_rows
        ]

    def _build_public_metrics(self, member: SocialWatchlistMember) -> dict[str, Any]:
        """Build a public metrics dict for a watchlist member.

        In a full implementation, this would query cached public data
        or invoke a SocialIntelligenceProvider. For now, returns the
        schema structure with null values indicating data not yet collected.

        The architecture supports future population via:
        - Platform public APIs (respecting ToS and rate limits)
        - Third-party intelligence providers
        - Manual user import

        IMPORTANT: Never populate from private/connected account analytics.
        """
        return {
            "followers": None,
            "following": None,
            "posts_count": None,
            "avg_likes": None,
            "avg_comments": None,
            "engagement_rate": None,
            "growth_rate_percent": None,
            "posting_frequency": None,
            "top_formats": None,
        }
