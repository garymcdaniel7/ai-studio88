"""Social analytics ORM models.

Models for social performance analytics and market intelligence.
Tracks connected social accounts, published content, metric snapshots,
competitive watchlists, derived insights, and content experiments.

All tables are workspace-scoped (org_id NOT NULL) with appropriate indexes
and RLS policies for tenant isolation.

Validates: Requirements R107.1, R107.2, R43.7, A2-007
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class SocialAccount(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A social platform account connected to a workspace.

    Links to the connections table via connection_id. Tracks platform-specific
    account identifiers, sync state, and capabilities.
    """

    __tablename__ = "social_accounts"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="FK to connections table providing this account",
    )
    platform: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Platform identifier: instagram, tiktok, youtube",
    )
    account_external_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Platform's unique account identifier",
    )
    account_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Display name on the platform",
    )
    account_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="URL to the account profile on the platform",
    )
    capabilities: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment="What this account connection can do (JSON object)",
    )
    sync_state: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Sync lifecycle state: last_sync, cursor, rate_limit_state, etc.",
    )

    __table_args__ = (
        Index("ix_social_accounts_org_id", "org_id"),
        Index("ix_social_accounts_connection_id", "connection_id"),
        Index("ix_social_accounts_org_platform", "org_id", "platform"),
    )

    def __repr__(self) -> str:
        return (
            f"<SocialAccount(id={self.id}, org_id={self.org_id}, "
            f"platform={self.platform}, account_name={self.account_name})>"
        )


class SocialContent(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A content item (post) linked to a social platform account.

    Tracks published content with references to AI Studio assets and talent.
    """

    __tablename__ = "social_content"

    social_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="FK to social_accounts table",
    )
    platform_content_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Platform's unique post/content identifier",
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Linked AI Studio asset (if published from here)",
    )
    talent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Associated talent entity",
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Associated project",
    )
    platform: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Platform identifier: instagram, tiktok, youtube",
    )
    content_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Content type: image, video, carousel, story, reel",
    )
    caption: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Post caption/text",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the content was published on the platform",
    )
    extra_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Additional platform-specific metadata (JSON)",
    )

    __table_args__ = (
        Index("ix_social_content_org_platform", "org_id", "platform"),
        Index("ix_social_content_account_id", "social_account_id"),
        Index("ix_social_content_org_talent", "org_id", "talent_id"),
        Index("ix_social_content_published_at", "org_id", "published_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<SocialContent(id={self.id}, org_id={self.org_id}, "
            f"platform={self.platform}, content_type={self.content_type})>"
        )


class SocialMetricSnapshot(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A point-in-time metric observation for a social account or content item.

    Stores normalized metrics with provenance tracking and timestamps from
    both the platform and our observation time.
    """

    __tablename__ = "social_metric_snapshots"

    social_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="FK to social_accounts (account-level metrics)",
    )
    social_content_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="FK to social_content (content-level metrics)",
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When we recorded this observation",
    )
    metrics: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Metric values: views, likes, comments, shares, reach, etc.",
    )
    provenance: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Data provenance: FIRST_PARTY_CONNECTED, PUBLIC_PLATFORM_DATA, etc.",
    )
    collection_method: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="How metrics were collected: api_sync, manual_import, public_scrape",
    )

    __table_args__ = (
        Index(
            "ix_social_metric_snapshots_org_time",
            "org_id",
            "snapshot_at",
        ),
        Index(
            "ix_social_metric_snapshots_content",
            "social_content_id",
            "snapshot_at",
        ),
        Index(
            "ix_social_metric_snapshots_account",
            "social_account_id",
            "snapshot_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SocialMetricSnapshot(id={self.id}, org_id={self.org_id}, "
            f"snapshot_at={self.snapshot_at}, provenance={self.provenance})>"
        )


class SocialWatchlist(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A named watchlist for tracking creators, brands, competitors, or topics.

    Workspace-level entity for organizing market intelligence targets.
    """

    __tablename__ = "social_watchlists"

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Watchlist name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Watchlist description/purpose",
    )
    category: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Optional category: competitor, inspiration, industry, etc.",
    )

    __table_args__ = (
        Index("ix_social_watchlists_org_id", "org_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SocialWatchlist(id={self.id}, org_id={self.org_id}, "
            f"name={self.name})>"
        )


class SocialWatchlistMember(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A member entry within a social watchlist.

    Represents a tracked entity: creator, brand, competitor, topic, or hashtag.
    """

    __tablename__ = "social_watchlist_members"

    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="FK to social_watchlists",
    )
    platform: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Platform (NULL = cross-platform)",
    )
    account_identifier: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="@handle, #hashtag, brand name, or topic",
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Human-readable display name for this member",
    )
    watch_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type: creator, brand, competitor, topic, hashtag",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="User notes about this watchlist member",
    )

    __table_args__ = (
        Index("ix_social_watchlist_members_watchlist", "watchlist_id"),
        Index("ix_social_watchlist_members_org", "org_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SocialWatchlistMember(id={self.id}, "
            f"watchlist_id={self.watchlist_id}, "
            f"account_identifier={self.account_identifier})>"
        )


class SocialDerivedInsight(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A derived analytics insight generated from observed metrics.

    Stores analysis results including trends, anomalies, recommendations,
    patterns, and comparisons with provenance and confidence tracking.
    """

    __tablename__ = "social_derived_insights"

    insight_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Insight type: trend, anomaly, recommendation, pattern, comparison",
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Subject entity ID (talent, content, account, watchlist member)",
    )
    content: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Structured insight data",
    )
    confidence: Mapped[float | None] = mapped_column(
        Numeric(3, 2),
        nullable=True,
        comment="Confidence score 0.00-1.00",
    )
    source_metrics_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment="References to metric snapshots supporting this insight",
    )
    provenance: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Provenance: DERIVED_ANALYSIS, AI_INTERPRETATION, STATISTICAL_PATTERN",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this insight becomes stale (NULL = no expiry)",
    )

    __table_args__ = (
        Index("ix_social_derived_insights_org_type", "org_id", "insight_type"),
        Index("ix_social_derived_insights_subject", "org_id", "subject_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SocialDerivedInsight(id={self.id}, org_id={self.org_id}, "
            f"insight_type={self.insight_type}, confidence={self.confidence})>"
        )


class SocialExperiment(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A content experiment (A/B test) for performance comparison.

    Tracks hypothesis, content variants, target metrics, observation windows,
    and results for data-driven content strategy optimization.
    """

    __tablename__ = "social_experiments"

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Experiment name",
    )
    hypothesis: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Hypothesis being tested",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="draft",
        comment="Status: draft, active, observing, completed, cancelled",
    )
    content_variants: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Content variant descriptions (baseline and variants)",
    )
    target_metric: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Primary metric being measured",
    )
    observation_window: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Start/end dates for measurement period",
    )
    linked_content_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment="social_content rows in this experiment",
    )
    results: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Experiment results once observation is complete",
    )

    __table_args__ = (
        Index("ix_social_experiments_org_status", "org_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<SocialExperiment(id={self.id}, org_id={self.org_id}, "
            f"name={self.name}, status={self.status})>"
        )
