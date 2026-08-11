"""Pydantic schemas for competitive intelligence and watchlists.

Defines request/response models for:
    - CRUD operations on watchlists
    - CRUD operations on watchlist members
    - Competitive intelligence queries (publicly available metrics)
    - Competitor profile lookups

All competitive intelligence data is publicly available information.
Private analytics from connected accounts are never mixed with public data.

Validates: Requirements R108.1, R108.2, R108.3, R108.4, R108.5,
           R108.6, R108.7, R108.8, R108.10
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, StrictBaseSchema


# =============================================================================
# Enums
# =============================================================================


class WatchType(str, Enum):
    """Valid watch types for watchlist members."""

    CREATOR = "creator"
    BRAND = "brand"
    COMPETITOR = "competitor"
    TOPIC = "topic"
    HASHTAG = "hashtag"


class DataProvenance(str, Enum):
    """Classification for data source of competitive intelligence.

    All competitive intelligence data carries provenance so Brain/Hermes
    can identify the source of each insight and never misrepresent
    estimates as private analytics.
    """

    PUBLIC_PLATFORM_DATA = "PUBLIC_PLATFORM_DATA"
    THIRD_PARTY_DATA = "THIRD_PARTY_DATA"
    DERIVED_ANALYSIS = "DERIVED_ANALYSIS"
    AI_INTERPRETATION = "AI_INTERPRETATION"
    USER_IMPORTED = "USER_IMPORTED"


class InsightType(str, Enum):
    """Types of derived competitive insights."""

    TREND = "trend"
    ANOMALY = "anomaly"
    RECOMMENDATION = "recommendation"
    PATTERN = "pattern"
    COMPARISON = "comparison"


# =============================================================================
# Watchlist Schemas
# =============================================================================


class WatchlistCreateRequest(StrictBaseSchema):
    """Request to create a new watchlist."""

    name: str = Field(min_length=1, max_length=200, description="Watchlist name")
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Watchlist description/purpose",
    )
    category: str | None = Field(
        default=None,
        max_length=50,
        description="Optional category: competitor, inspiration, industry",
    )


class WatchlistUpdateRequest(StrictBaseSchema):
    """Request to update a watchlist."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Updated name",
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Updated description",
    )
    category: str | None = Field(
        default=None,
        max_length=50,
        description="Updated category",
    )


class WatchlistResponse(BaseSchema):
    """Response for a single watchlist."""

    id: UUID
    org_id: UUID
    name: str
    description: str | None = None
    category: str | None = None
    member_count: int = Field(default=0, description="Number of members in this watchlist")
    created_at: datetime
    updated_at: datetime


class WatchlistListResponse(BaseSchema):
    """Paginated list of watchlists."""

    items: list[WatchlistResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Watchlist Member Schemas
# =============================================================================


class WatchlistMemberCreateRequest(StrictBaseSchema):
    """Request to add a member to a watchlist."""

    watch_type: WatchType = Field(description="Type: creator, brand, competitor, topic, hashtag")
    account_identifier: str = Field(
        min_length=1,
        max_length=255,
        description="@handle, #hashtag, brand name, or topic keyword",
    )
    display_name: str | None = Field(
        default=None,
        max_length=255,
        description="Human-readable display name",
    )
    platform: str | None = Field(
        default=None,
        max_length=50,
        description="Platform (NULL = cross-platform): instagram, tiktok, youtube",
    )
    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="User notes about this watchlist member",
    )


class WatchlistMemberUpdateRequest(StrictBaseSchema):
    """Request to update a watchlist member."""

    display_name: str | None = Field(
        default=None,
        max_length=255,
        description="Updated display name",
    )
    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Updated notes",
    )


class WatchlistMemberResponse(BaseSchema):
    """Response for a single watchlist member."""

    id: UUID
    org_id: UUID
    watchlist_id: UUID
    watch_type: WatchType
    account_identifier: str
    display_name: str | None = None
    platform: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class WatchlistMemberListResponse(BaseSchema):
    """Paginated list of watchlist members."""

    items: list[WatchlistMemberResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Competitive Intelligence Schemas
# =============================================================================


class PublicMetrics(BaseSchema):
    """Publicly available metrics for a social profile or entity.

    These metrics are only from public data (PUBLIC_PLATFORM_DATA provenance).
    Never represents private analytics from connected accounts.
    """

    followers: int | None = Field(default=None, description="Public follower count")
    following: int | None = Field(default=None, description="Public following count")
    posts_count: int | None = Field(default=None, description="Total public posts")
    avg_likes: float | None = Field(default=None, description="Average likes (estimated)")
    avg_comments: float | None = Field(default=None, description="Average comments (estimated)")
    engagement_rate: float | None = Field(
        default=None,
        description="Estimated engagement rate (public calculation)",
    )
    growth_rate_percent: float | None = Field(
        default=None,
        description="Estimated follower growth rate (%)",
    )
    posting_frequency: str | None = Field(
        default=None,
        description="Estimated posting frequency (e.g., '3x/week')",
    )
    top_formats: list[str] | None = Field(
        default=None,
        description="Most-used content formats (e.g., ['reel', 'carousel'])",
    )


class CompetitorProfileResponse(BaseSchema):
    """Public profile information for a tracked entity.

    All data is from publicly available sources. Source attribution
    is always included so Brain/Hermes can identify the origin.
    """

    member_id: UUID = Field(description="Watchlist member ID")
    account_identifier: str
    display_name: str | None = None
    platform: str | None = None
    watch_type: WatchType
    metrics: PublicMetrics
    data_source: DataProvenance = Field(
        default=DataProvenance.PUBLIC_PLATFORM_DATA,
        description="Source attribution for this data",
    )
    data_freshness: str = Field(
        default="estimated",
        description="How fresh this data is: current, stale_hours, stale_days, estimated",
    )
    last_observed_at: datetime | None = Field(
        default=None,
        description="When this data was last observed/updated",
    )
    disclaimers: list[str] = Field(
        default_factory=lambda: [
            "Metrics are publicly available estimates, not private analytics."
        ],
        description="Attribution and accuracy disclaimers",
    )


class CompetitiveInsightResponse(BaseSchema):
    """A derived competitive insight with full source attribution.

    Brain/Hermes uses this to answer competitive questions while
    identifying the source of each insight (R108.7).
    """

    id: UUID | None = None
    insight_type: InsightType
    subject_identifier: str = Field(description="Who/what this insight is about")
    content: dict[str, Any] = Field(description="Structured insight data")
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score 0.0-1.0",
    )
    provenance: DataProvenance = Field(
        description="Source classification for this insight",
    )
    reasoning_class: str = Field(
        default="DERIVED_METRIC",
        description="Reasoning class: OBSERVED_FACT, DERIVED_METRIC, "
        "STATISTICAL_PATTERN, AI_INTERPRETATION, RECOMMENDATION",
    )
    evidence_summary: str | None = Field(
        default=None,
        description="Brief description of what evidence supports this insight",
    )
    created_at: datetime | None = None


class CompetitiveIntelligenceResponse(BaseSchema):
    """Aggregated competitive intelligence response for a watchlist.

    Includes profiles and derived insights with full provenance tracking.
    All data is from publicly available sources only.
    """

    watchlist_id: UUID
    watchlist_name: str
    profiles: list[CompetitorProfileResponse]
    insights: list[CompetitiveInsightResponse]
    data_sources: list[str] = Field(
        default_factory=lambda: ["PUBLIC_PLATFORM_DATA"],
        description="All data sources used in this response",
    )
    rate_limit_status: str = Field(
        default="ok",
        description="Rate limit awareness: ok, approaching_limit, rate_limited",
    )
    disclaimers: list[str] = Field(
        default_factory=lambda: [
            "All metrics are from publicly available data.",
            "Engagement rates are estimates based on public observations.",
            "This is not private analytics from connected accounts.",
        ],
        description="Mandatory attribution and accuracy disclaimers (R108.8)",
    )
