"""Pydantic v2 schemas for the Social Analytics API.

Provides request/response validation for social accounts, content, metrics,
watchlists, intelligence insights, experiments, and sync operations.

Data provenance is a first-class enum — UNAVAILABLE is used for missing metrics
(never fabricate values).

Validates: Requirements R107.2, R107.3, R107.4, R107.10, R43.11, R43.12
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Enums
# =============================================================================


class DataProvenance(enum.StrEnum):
    """Data provenance classification per design.md A2-008.

    Tracks the origin and trust level of social intelligence data.
    """

    FIRST_PARTY_CONNECTED = "FIRST_PARTY_CONNECTED"
    PUBLIC_PLATFORM_DATA = "PUBLIC_PLATFORM_DATA"
    THIRD_PARTY_DATA = "THIRD_PARTY_DATA"
    USER_IMPORTED = "USER_IMPORTED"
    DERIVED_ANALYSIS = "DERIVED_ANALYSIS"


class MetricAvailability(enum.StrEnum):
    """Metric value availability status.

    UNAVAILABLE indicates the metric is not available from the platform —
    we NEVER fabricate values.
    """

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"


class SocialPlatform(enum.StrEnum):
    """Supported social platforms."""

    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    X = "x"
    LINKEDIN = "linkedin"
    PINTEREST = "pinterest"


class ContentType(enum.StrEnum):
    """Social content format types."""

    IMAGE = "image"
    VIDEO = "video"
    CAROUSEL = "carousel"
    STORY = "story"
    REEL = "reel"
    SHORT = "short"
    POST = "post"


class WatchType(enum.StrEnum):
    """Watchlist member types."""

    CREATOR = "creator"
    BRAND = "brand"
    COMPETITOR = "competitor"
    TOPIC = "topic"
    HASHTAG = "hashtag"


class InsightType(enum.StrEnum):
    """Derived insight types."""

    TREND = "trend"
    ANOMALY = "anomaly"
    RECOMMENDATION = "recommendation"
    PATTERN = "pattern"
    COMPARISON = "comparison"


class ExperimentStatus(enum.StrEnum):
    """Experiment lifecycle states."""

    DRAFT = "draft"
    ACTIVE = "active"
    OBSERVING = "observing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SyncConnectionState(enum.StrEnum):
    """Social account connection health state."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RATE_LIMITED = "rate_limited"
    AUTH_EXPIRED = "auth_expired"


# =============================================================================
# Response Schemas — Social Accounts
# =============================================================================


class SocialAccountResponse(BaseModel):
    """Response schema for a connected social account."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    connection_id: UUID
    platform: str
    account_external_id: str
    account_name: str | None = None
    account_url: str | None = None
    capabilities: dict = Field(default_factory=dict)
    sync_state: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class SocialAccountListResponse(BaseModel):
    """Paginated list of social accounts."""

    items: list[SocialAccountResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Response Schemas — Social Content
# =============================================================================


class SocialContentResponse(BaseModel):
    """Response schema for a social content item (post)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    social_account_id: UUID
    platform_content_id: str
    asset_id: UUID | None = None
    talent_id: UUID | None = None
    project_id: UUID | None = None
    platform: str
    content_type: str | None = None
    caption: str | None = None
    published_at: datetime | None = None
    metadata: dict = Field(default_factory=dict, alias="extra_metadata")
    created_at: datetime
    updated_at: datetime


class SocialContentListResponse(BaseModel):
    """Paginated list of social content items."""

    items: list[SocialContentResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Response Schemas — Metrics
# =============================================================================


class MetricValue(BaseModel):
    """A single metric value with availability status.

    When availability is UNAVAILABLE, value is None — never fabricated.
    """

    name: str
    value: float | None = None
    availability: MetricAvailability = MetricAvailability.AVAILABLE


class SocialMetricSnapshotResponse(BaseModel):
    """Response schema for a metric observation snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    social_account_id: UUID | None = None
    social_content_id: UUID | None = None
    snapshot_at: datetime
    metrics: dict = Field(default_factory=dict)
    provenance: str
    collection_method: str | None = None
    created_at: datetime
    updated_at: datetime


class SocialMetricListResponse(BaseModel):
    """Paginated list of metric snapshots."""

    items: list[SocialMetricSnapshotResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Request/Response Schemas — Watchlists
# =============================================================================


class WatchlistMemberCreate(BaseModel):
    """Schema for adding a member to a watchlist."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    account_identifier: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="@handle, #hashtag, brand name, or topic",
    )
    watch_type: WatchType = Field(
        ..., description="Type of entity being watched"
    )
    platform: SocialPlatform | None = Field(
        default=None, description="Platform (null = cross-platform)"
    )
    display_name: str | None = Field(
        default=None, max_length=255, description="Human-readable name"
    )
    notes: str | None = Field(
        default=None, max_length=2000, description="User notes"
    )


class WatchlistCreate(BaseModel):
    """Request schema for creating a watchlist."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(
        ..., min_length=1, max_length=200, description="Watchlist name"
    )
    description: str | None = Field(
        default=None, max_length=2000, description="Watchlist purpose/description"
    )
    category: str | None = Field(
        default=None,
        max_length=50,
        description="Category: competitor, inspiration, industry",
    )
    members: list[WatchlistMemberCreate] = Field(
        default_factory=list,
        description="Initial members to add (optional)",
    )


class WatchlistMemberResponse(BaseModel):
    """Response schema for a watchlist member."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    watchlist_id: UUID
    account_identifier: str
    watch_type: str
    platform: str | None = None
    display_name: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class WatchlistResponse(BaseModel):
    """Response schema for a watchlist."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    name: str
    description: str | None = None
    category: str | None = None
    created_at: datetime
    updated_at: datetime
    members: list[WatchlistMemberResponse] = Field(default_factory=list)


class WatchlistListResponse(BaseModel):
    """Paginated list of watchlists."""

    items: list[WatchlistResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Response Schemas — Intelligence (Derived Insights)
# =============================================================================


class DerivedInsightResponse(BaseModel):
    """Response schema for a derived analytics insight."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    insight_type: str
    subject_id: UUID | None = None
    content: dict = Field(default_factory=dict)
    confidence: float | None = None
    source_metrics_ids: list[UUID] | None = None
    provenance: str
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DerivedInsightListResponse(BaseModel):
    """Paginated list of derived insights."""

    items: list[DerivedInsightResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Request/Response Schemas — Experiments
# =============================================================================


class ExperimentCreate(BaseModel):
    """Request schema for creating a content experiment."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(
        ..., min_length=1, max_length=200, description="Experiment name"
    )
    hypothesis: str = Field(
        ..., min_length=1, max_length=5000, description="Hypothesis being tested"
    )
    content_variants: dict = Field(
        default_factory=dict,
        description="Content variant descriptions (baseline and variants)",
    )
    target_metric: str | None = Field(
        default=None,
        max_length=100,
        description="Primary metric being measured",
    )
    observation_window: dict | None = Field(
        default=None,
        description="Start/end dates for measurement period",
    )
    linked_content_ids: list[UUID] | None = Field(
        default=None,
        description="social_content rows in this experiment",
    )


class ExperimentResponse(BaseModel):
    """Response schema for a content experiment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    name: str
    hypothesis: str
    status: str
    content_variants: dict = Field(default_factory=dict)
    target_metric: str | None = None
    observation_window: dict | None = None
    linked_content_ids: list[UUID] | None = None
    results: dict | None = None
    created_at: datetime
    updated_at: datetime


class ExperimentListResponse(BaseModel):
    """Paginated list of experiments."""

    items: list[ExperimentResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Request/Response Schemas — Sync
# =============================================================================


class SyncTriggerRequest(BaseModel):
    """Request schema for triggering a manual metrics sync."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    account_id: UUID | None = Field(
        default=None,
        description="Specific account to sync (null = sync all)",
    )
    platform: SocialPlatform | None = Field(
        default=None,
        description="Filter sync to a specific platform",
    )


class SyncStatusResponse(BaseModel):
    """Response schema for sync trigger result."""

    status: str = Field(description="Sync status: queued, in_progress, completed")
    message: str = Field(description="Human-readable status message")
    accounts_queued: int = Field(
        ge=0, description="Number of accounts queued for sync"
    )
