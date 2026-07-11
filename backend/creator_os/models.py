"""Creator OS data models.

Campaigns, calendar, publishing, analytics, brands, teams, and notifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# =============================================================================
# Content Calendar
# =============================================================================


class ContentStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Platform(StrEnum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    YOUTUBE_SHORTS = "youtube_shorts"
    FACEBOOK = "facebook"
    THREADS = "threads"
    PINTEREST = "pinterest"
    LINKEDIN = "linkedin"
    X = "x"
    BLOG = "blog"
    EMAIL = "email"
    PODCAST = "podcast"


@dataclass
class CalendarEntry:
    """A piece of content on the publishing calendar."""

    id: str = ""
    project_id: str | None = None
    talent_id: str | None = None
    campaign_id: str | None = None
    asset_id: str | None = None
    title: str = ""
    platform: str = "instagram"
    content_type: str = "image"
    status: str = "draft"
    scheduled_at: str | None = None  # ISO datetime
    published_at: str | None = None
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# =============================================================================
# Campaigns
# =============================================================================


@dataclass
class Campaign:
    """A multi-platform campaign with objectives and content plan."""

    id: str = ""
    project_id: str | None = None
    name: str = ""
    objective: str = ""
    platforms: list[str] = field(default_factory=list)
    budget_usd: float = 0.0
    target_audience: str = ""
    start_date: str | None = None
    end_date: str | None = None
    status: str = "planning"  # planning, active, paused, completed
    content_count: int = 0
    metadata: dict = field(default_factory=dict)


# =============================================================================
# Analytics
# =============================================================================


@dataclass
class AnalyticsSnapshot:
    """Analytics data point for a content piece or campaign."""

    id: str = ""
    asset_id: str | None = None
    campaign_id: str | None = None
    platform: str = ""
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    watch_time_seconds: int = 0
    completion_rate: float = 0.0
    ctr: float = 0.0
    reach: int = 0
    followers_gained: int = 0
    revenue_usd: float = 0.0
    engagement_rate: float = 0.0
    recorded_at: str = ""


# =============================================================================
# Brands
# =============================================================================


@dataclass
class Brand:
    """A brand entity with guidelines and assets."""

    id: str = ""
    name: str = ""
    description: str = ""
    industry: str = ""
    primary_color: str = ""
    secondary_color: str = ""
    logo_asset_id: str | None = None
    voice: str = ""
    guidelines: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


# =============================================================================
# Teams
# =============================================================================


class TeamRole(StrEnum):
    OWNER = "owner"
    CREATIVE_DIRECTOR = "creative_director"
    PRODUCER = "producer"
    EDITOR = "editor"
    DESIGNER = "designer"
    ANIMATOR = "animator"
    CLIENT = "client"
    REVIEWER = "reviewer"
    PUBLISHER = "publisher"
    VIEWER = "viewer"


@dataclass
class TeamMember:
    """A member of the production team."""

    id: str = ""
    name: str = ""
    email: str = ""
    role: str = "viewer"
    permissions: list[str] = field(default_factory=list)
    active: bool = True


# =============================================================================
# Notifications
# =============================================================================


class NotificationType(StrEnum):
    JOB_COMPLETED = "job_completed"
    WORKER_OFFLINE = "worker_offline"
    GENERATION_FAILED = "generation_failed"
    PUBLISHING_COMPLETED = "publishing_completed"
    CAMPAIGN_STARTED = "campaign_started"
    CAMPAIGN_FINISHED = "campaign_finished"
    TRENDING_OPPORTUNITY = "trending_opportunity"
    CREATIVE_RECOMMENDATION = "creative_recommendation"
    APPROVAL_REQUESTED = "approval_requested"


@dataclass
class Notification:
    """A notification for the creator."""

    id: str = ""
    type: str = ""
    title: str = ""
    message: str = ""
    read: bool = False
    action_url: str | None = None
    metadata: dict = field(default_factory=dict)
    created_at: str = ""


# =============================================================================
# Content Repurposing
# =============================================================================

REPURPOSE_FORMATS = [
    "instagram_reel",
    "tiktok",
    "youtube_short",
    "trailer",
    "story",
    "carousel",
    "thumbnail",
    "wallpaper",
    "newsletter",
    "behind_the_scenes",
    "podcast_clip",
    "gif",
    "teaser",
    "quote_graphic",
]
