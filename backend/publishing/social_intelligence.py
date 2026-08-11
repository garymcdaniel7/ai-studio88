"""Social Intelligence Provider Interface and Sync Lifecycle.

Defines the provider-agnostic social intelligence interface (A2-008) and
per-account sync state tracking (A2-012). Providers implement metrics
retrieval, content discovery, and public profile lookup without coupling
to any specific social platform.

Key design principles:
    - Analytics failure does NOT disable publishing
    - Publishing failure does NOT destroy analytics
    - Providers are NOT required to implement all capabilities
    - Missing capabilities return UNAVAILABLE status
    - Data provenance is tracked for every metric/insight

Requirements: R107.11, A2-008, A2-012
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4


# =============================================================================
# Data Provenance Classifications (per design.md A2-008)
# =============================================================================


class DataProvenance(StrEnum):
    """Data provenance classification for social intelligence data.

    Determines the trust level and how data may be presented.
    """

    FIRST_PARTY_CONNECTED = "FIRST_PARTY_CONNECTED"
    PUBLIC_PLATFORM_DATA = "PUBLIC_PLATFORM_DATA"
    THIRD_PARTY_DATA = "THIRD_PARTY_DATA"
    USER_IMPORTED = "USER_IMPORTED"
    DERIVED_ANALYSIS = "DERIVED_ANALYSIS"


class ReasoningClass(StrEnum):
    """Reasoning classification for Brain context injection (A2-009).

    When social intelligence data enters Brain context, BOTH provenance
    and reasoning class must survive.
    """

    OBSERVED_FACT = "OBSERVED_FACT"
    DERIVED_METRIC = "DERIVED_METRIC"
    STATISTICAL_PATTERN = "STATISTICAL_PATTERN"
    AI_INTERPRETATION = "AI_INTERPRETATION"
    RECOMMENDATION = "RECOMMENDATION"


class CollectionMethod(StrEnum):
    """How social data was collected."""

    API_SYNC = "api_sync"
    MANUAL_IMPORT = "manual_import"
    PUBLIC_SCRAPE = "public_scrape"
    CALCULATED = "calculated"


# =============================================================================
# Sync Lifecycle State (per design.md A2-012)
# =============================================================================


class ConnectionState(StrEnum):
    """Health state of a social account connection."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RATE_LIMITED = "rate_limited"
    AUTH_EXPIRED = "auth_expired"
    OFFLINE = "offline"


class DataFreshness(StrEnum):
    """How fresh the synced data is."""

    CURRENT = "current"
    STALE_HOURS = "stale_hours"
    STALE_DAYS = "stale_days"
    UNKNOWN = "unknown"


@dataclass
class SyncState:
    """Per-account sync tracking stored in social_accounts.sync_state JSONB.

    Tracks the full lifecycle of metric synchronization for a connected
    social account. Updated after each sync attempt.
    """

    last_successful_sync: datetime | None = None
    last_attempted_sync: datetime | None = None
    next_scheduled_sync: datetime | None = None
    cursor: str | None = None
    rate_limit_state: dict[str, int | str] = field(default_factory=dict)
    connection_state: ConnectionState = ConnectionState.HEALTHY
    data_freshness: DataFreshness = DataFreshness.UNKNOWN
    partial_sync: bool = False
    error_state: str | None = None

    def mark_sync_started(self) -> None:
        """Record that a sync attempt has begun."""
        self.last_attempted_sync = datetime.now(timezone.utc)
        self.error_state = None

    def mark_sync_success(self, cursor: str | None = None) -> None:
        """Record a successful sync completion."""
        now = datetime.now(timezone.utc)
        self.last_successful_sync = now
        self.last_attempted_sync = now
        self.cursor = cursor
        self.connection_state = ConnectionState.HEALTHY
        self.data_freshness = DataFreshness.CURRENT
        self.partial_sync = False
        self.error_state = None

    def mark_sync_partial(self, cursor: str | None = None) -> None:
        """Record a partial sync (incomplete but not failed)."""
        now = datetime.now(timezone.utc)
        self.last_attempted_sync = now
        if cursor is not None:
            self.cursor = cursor
        self.partial_sync = True
        self.data_freshness = DataFreshness.CURRENT

    def mark_sync_failed(self, error: str) -> None:
        """Record a sync failure."""
        self.last_attempted_sync = datetime.now(timezone.utc)
        self.error_state = error
        self.connection_state = ConnectionState.DEGRADED

    def mark_rate_limited(self, remaining: int, reset_at: str) -> None:
        """Record that the provider hit a rate limit."""
        self.rate_limit_state = {"remaining": remaining, "reset_at": reset_at}
        self.connection_state = ConnectionState.RATE_LIMITED

    def mark_auth_expired(self) -> None:
        """Record that the connection's auth has expired."""
        self.connection_state = ConnectionState.AUTH_EXPIRED
        self.error_state = "Authentication expired — reauthorization required"

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict for JSONB storage."""
        return {
            "last_successful_sync": (
                self.last_successful_sync.isoformat()
                if self.last_successful_sync
                else None
            ),
            "last_attempted_sync": (
                self.last_attempted_sync.isoformat()
                if self.last_attempted_sync
                else None
            ),
            "next_scheduled_sync": (
                self.next_scheduled_sync.isoformat()
                if self.next_scheduled_sync
                else None
            ),
            "cursor": self.cursor,
            "rate_limit_state": self.rate_limit_state,
            "connection_state": self.connection_state.value,
            "data_freshness": self.data_freshness.value,
            "partial_sync": self.partial_sync,
            "error_state": self.error_state,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SyncState:
        """Deserialize from JSONB dict."""
        if not data:
            return cls()

        def _parse_dt(value: str | None) -> datetime | None:
            if value is None:
                return None
            return datetime.fromisoformat(value)

        return cls(
            last_successful_sync=_parse_dt(data.get("last_successful_sync")),
            last_attempted_sync=_parse_dt(data.get("last_attempted_sync")),
            next_scheduled_sync=_parse_dt(data.get("next_scheduled_sync")),
            cursor=data.get("cursor"),
            rate_limit_state=data.get("rate_limit_state", {}),
            connection_state=ConnectionState(
                data.get("connection_state", "healthy")
            ),
            data_freshness=DataFreshness(data.get("data_freshness", "unknown")),
            partial_sync=data.get("partial_sync", False),
            error_state=data.get("error_state"),
        )


# =============================================================================
# Provider Data Types
# =============================================================================


@dataclass
class ProviderCapabilities:
    """What a social intelligence provider can do.

    Providers are NOT required to implement all capabilities.
    Unavailable capabilities are reported here so callers can
    gracefully degrade.
    """

    can_fetch_owned_metrics: bool = False
    can_fetch_owned_content: bool = False
    can_fetch_public_profiles: bool = False
    can_fetch_public_content: bool = False
    can_sync_incrementally: bool = False
    supported_platforms: list[str] = field(default_factory=list)
    supported_metric_types: list[str] = field(default_factory=list)


@dataclass
class AccountInfo:
    """Information about a connected social account."""

    account_external_id: str
    account_name: str
    platform: str
    account_url: str | None = None
    follower_count: int | None = None
    is_verified: bool = False
    capabilities: dict[str, bool] = field(default_factory=dict)


@dataclass
class ContentItem:
    """A piece of social content (post, reel, video, etc.)."""

    external_post_id: str
    platform: str
    content_type: str
    caption: str | None = None
    published_at: datetime | None = None
    url: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class MetricSnapshot:
    """A single metric observation at a point in time."""

    metric_type: str
    metric_value: float
    provenance: DataProvenance
    collection_method: CollectionMethod
    provider_timestamp: datetime | None = None
    observation_timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass
class PublicProfile:
    """Publicly available profile information."""

    identifier: str
    platform: str
    display_name: str | None = None
    follower_count: int | None = None
    following_count: int | None = None
    post_count: int | None = None
    bio: str | None = None
    is_verified: bool = False
    provenance: DataProvenance = DataProvenance.PUBLIC_PLATFORM_DATA


@dataclass
class DateRange:
    """Date range for metric/content queries."""

    start: datetime
    end: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SyncResult:
    """Result of a metrics sync operation."""

    success: bool
    metrics_synced: int = 0
    content_synced: int = 0
    new_cursor: str | None = None
    partial: bool = False
    error: str | None = None
    rate_limit_remaining: int | None = None
    rate_limit_reset_at: str | None = None


# =============================================================================
# SocialIntelligenceProvider Protocol (A2-008)
# =============================================================================


@runtime_checkable
class SocialIntelligenceProvider(Protocol):
    """Provider-agnostic social intelligence interface.

    Providers are NOT required to implement all capabilities.
    Missing capabilities should return appropriate defaults or raise
    NotImplementedError. The caller checks capabilities first via
    get_capabilities().

    Critical rules:
        - Analytics failure SHALL NOT disable publishing
        - Publishing failure SHALL NOT destroy analytics
        - These are independent capabilities sharing a connection

    Validates: Requirements R107.11, A2-008
    """

    async def get_capabilities(self) -> ProviderCapabilities:
        """Return what this provider can do.

        Callers MUST check capabilities before invoking other methods.
        """
        ...

    async def get_connected_account(
        self, connection_id: UUID, credentials: dict
    ) -> AccountInfo:
        """Retrieve account information for a connected social account.

        Args:
            connection_id: The workspace connection ID.
            credentials: Decrypted credentials for the connection.

        Returns:
            Account information including name, platform, and capabilities.

        Raises:
            ConnectionError: If the provider is unreachable.
            PermissionError: If credentials are invalid or expired.
        """
        ...

    async def get_owned_content(
        self, account_id: str, period: DateRange
    ) -> list[ContentItem]:
        """Retrieve content owned by the connected account within a date range.

        Args:
            account_id: The platform's external account identifier.
            period: Date range for content retrieval.

        Returns:
            List of content items published within the period.
        """
        ...

    async def get_owned_metrics(
        self, content_id: str
    ) -> list[MetricSnapshot]:
        """Retrieve metrics for a specific piece of owned content.

        Args:
            content_id: The platform's external post/content identifier.

        Returns:
            List of metric observations for the content.
        """
        ...

    async def get_public_profile(
        self, identifier: str, platform: str
    ) -> PublicProfile | None:
        """Retrieve publicly available profile information.

        Args:
            identifier: The handle, username, or account ID.
            platform: The social platform name.

        Returns:
            Public profile data if available, None if not found.
        """
        ...

    async def sync_metrics(
        self, account_id: str, cursor: str | None = None
    ) -> SyncResult:
        """Synchronize metrics for an account, resuming from cursor.

        Incremental sync: uses cursor to resume from last position.
        Full sync: cursor=None starts from the beginning.

        Args:
            account_id: The platform's external account identifier.
            cursor: Pagination cursor from previous sync (None for full).

        Returns:
            SyncResult with counts, new cursor, and any error info.
        """
        ...


# =============================================================================
# Simulation Provider (for development and testing)
# =============================================================================


class SimulationSocialIntelligenceProvider:
    """Simulated social intelligence provider for development/testing.

    Returns realistic-looking fake data without making external API calls.
    Useful for local development and automated testing.
    """

    def __init__(self, platform: str = "instagram") -> None:
        self._platform = platform

    async def get_capabilities(self) -> ProviderCapabilities:
        """Return simulated capabilities (all enabled)."""
        return ProviderCapabilities(
            can_fetch_owned_metrics=True,
            can_fetch_owned_content=True,
            can_fetch_public_profiles=True,
            can_fetch_public_content=True,
            can_sync_incrementally=True,
            supported_platforms=[self._platform],
            supported_metric_types=[
                "views",
                "likes",
                "comments",
                "shares",
                "reach",
                "impressions",
                "followers",
                "engagement_rate",
            ],
        )

    async def get_connected_account(
        self, connection_id: UUID, credentials: dict
    ) -> AccountInfo:
        """Return simulated account info."""
        return AccountInfo(
            account_external_id=f"sim_{connection_id.hex[:8]}",
            account_name=f"simulated_{self._platform}_account",
            platform=self._platform,
            account_url=f"https://{self._platform}.com/simulated_account",
            follower_count=12500,
            is_verified=False,
            capabilities={
                "read_metrics": True,
                "read_content": True,
                "read_insights": True,
            },
        )

    async def get_owned_content(
        self, account_id: str, period: DateRange
    ) -> list[ContentItem]:
        """Return simulated content items."""
        import random

        content_types = ["image", "video", "carousel", "reel", "story"]
        items: list[ContentItem] = []
        for i in range(random.randint(3, 10)):
            items.append(
                ContentItem(
                    external_post_id=f"sim_post_{uuid4().hex[:8]}",
                    platform=self._platform,
                    content_type=random.choice(content_types),
                    caption=f"Simulated post #{i + 1}",
                    published_at=period.start,
                    url=f"https://{self._platform}.com/p/sim_{i}",
                    metadata={"simulated": True},
                )
            )
        return items

    async def get_owned_metrics(
        self, content_id: str
    ) -> list[MetricSnapshot]:
        """Return simulated metrics for a content item."""
        import random

        metric_types = ["views", "likes", "comments", "shares", "reach"]
        return [
            MetricSnapshot(
                metric_type=mt,
                metric_value=float(random.randint(10, 5000)),
                provenance=DataProvenance.FIRST_PARTY_CONNECTED,
                collection_method=CollectionMethod.API_SYNC,
                observation_timestamp=datetime.now(timezone.utc),
            )
            for mt in metric_types
        ]

    async def get_public_profile(
        self, identifier: str, platform: str
    ) -> PublicProfile | None:
        """Return simulated public profile."""
        import random

        return PublicProfile(
            identifier=identifier,
            platform=platform,
            display_name=f"Simulated {identifier}",
            follower_count=random.randint(1000, 1_000_000),
            following_count=random.randint(100, 5000),
            post_count=random.randint(50, 2000),
            bio="Simulated social profile for development.",
            is_verified=random.choice([True, False]),
            provenance=DataProvenance.PUBLIC_PLATFORM_DATA,
        )

    async def sync_metrics(
        self, account_id: str, cursor: str | None = None
    ) -> SyncResult:
        """Simulate a metrics sync operation."""
        import random

        return SyncResult(
            success=True,
            metrics_synced=random.randint(5, 50),
            content_synced=random.randint(1, 10),
            new_cursor=f"sim_cursor_{uuid4().hex[:8]}",
            partial=False,
            error=None,
            rate_limit_remaining=random.randint(50, 200),
            rate_limit_reset_at=None,
        )


# =============================================================================
# Provider Registry
# =============================================================================

SOCIAL_INTELLIGENCE_PROVIDERS: dict[str, type] = {
    "simulation": SimulationSocialIntelligenceProvider,
}


def get_social_intelligence_provider(
    provider_name: str = "simulation",
    platform: str = "instagram",
) -> SocialIntelligenceProvider:
    """Get a social intelligence provider instance by name.

    Args:
        provider_name: Registered provider name.
        platform: Target platform for the provider.

    Returns:
        An instance implementing SocialIntelligenceProvider.

    Raises:
        ValueError: If provider_name is not registered.
    """
    provider_cls = SOCIAL_INTELLIGENCE_PROVIDERS.get(provider_name)
    if provider_cls is None:
        available = list(SOCIAL_INTELLIGENCE_PROVIDERS.keys())
        raise ValueError(
            f"Unknown social intelligence provider: {provider_name!r}. "
            f"Available: {available}"
        )
    return provider_cls(platform=platform)
