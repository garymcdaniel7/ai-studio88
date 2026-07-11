"""Social Media Provider Interface.

All social platforms implement this. AI Studio dispatches
publishing through it without knowing platform-specific details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PlatformRequirements:
    """Media requirements for a platform."""

    platform: str
    aspect_ratios: list[str] = field(default_factory=list)
    max_duration_seconds: float = 60.0
    max_caption_length: int = 2200
    max_hashtags: int = 30
    max_file_size_mb: int = 100
    supported_formats: list[str] = field(default_factory=list)
    recommended_posting_times: list[str] = field(default_factory=list)


@dataclass
class PublishResult:
    success: bool = False
    provider_post_id: str = ""
    published_url: str = ""
    message: str = ""
    metadata: dict = field(default_factory=dict)


class SocialProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def health(self) -> dict: ...

    @abstractmethod
    def capabilities(self) -> dict: ...

    @abstractmethod
    def requirements(self) -> PlatformRequirements: ...

    @abstractmethod
    def publish(self, post: dict) -> PublishResult: ...

    @abstractmethod
    def fetch_analytics(self, post_id: str) -> dict: ...

    @abstractmethod
    def validate_media(self, asset: dict) -> tuple[bool, list[str]]: ...


class SimulatedSocialProvider(SocialProvider):
    """Simulates social publishing for all platforms."""

    def __init__(self, platform: str = "instagram") -> None:
        self._platform = platform

    @property
    def name(self) -> str:
        return f"simulation_{self._platform}"

    def health(self):
        return {"healthy": True, "provider": self.name}

    def capabilities(self):
        return {
            "platform": self._platform,
            "can_publish": True,
            "can_schedule": True,
            "can_analytics": True,
        }

    def requirements(self):
        reqs = {
            "instagram": PlatformRequirements(
                "instagram",
                ["1:1", "4:5", "9:16"],
                90,
                2200,
                30,
                100,
                ["jpg", "mp4"],
                ["Tue-Thu 10am-1pm"],
            ),
            "tiktok": PlatformRequirements(
                "tiktok", ["9:16"], 180, 2200, 30, 287, ["mp4"], ["Tue-Thu 7-9pm"]
            ),
            "youtube": PlatformRequirements(
                "youtube", ["16:9"], 43200, 5000, 15, 256000, ["mp4", "mov"], ["Fri-Sat 2-4pm"]
            ),
            "youtube_shorts": PlatformRequirements(
                "youtube_shorts", ["9:16"], 60, 100, 3, 100, ["mp4"], ["Mon-Fri evenings"]
            ),
            "pinterest": PlatformRequirements(
                "pinterest", ["2:3", "1:1"], 60, 500, 20, 32, ["jpg", "png", "mp4"], ["Sat 8-11pm"]
            ),
            "linkedin": PlatformRequirements(
                "linkedin", ["1:1", "16:9"], 600, 3000, 5, 200, ["jpg", "mp4"], ["Tue-Thu 9am-12pm"]
            ),
            "x": PlatformRequirements(
                "x", ["16:9", "1:1"], 140, 280, 5, 512, ["jpg", "mp4", "gif"], ["Mon-Fri 12-3pm"]
            ),
        }
        return reqs.get(self._platform, PlatformRequirements(self._platform))

    def publish(self, post: dict) -> PublishResult:
        import uuid

        return PublishResult(
            success=True,
            provider_post_id=f"sim_{uuid.uuid4().hex[:12]}",
            published_url=f"https://{self._platform}.com/p/simulated",
            message=f"Simulated publish to {self._platform}",
        )

    def fetch_analytics(self, post_id: str) -> dict:
        import random

        return {
            "views": random.randint(100, 10000),
            "likes": random.randint(10, 500),
            "comments": random.randint(1, 50),
            "shares": random.randint(0, 30),
            "engagement_rate": round(random.uniform(2.0, 8.0), 2),
            "reach": random.randint(200, 15000),
        }

    def validate_media(self, asset: dict) -> tuple[bool, list[str]]:
        issues = []
        reqs = self.requirements()
        size_mb = (asset.get("size_bytes", 0) or 0) / (1024 * 1024)
        if size_mb > reqs.max_file_size_mb:
            issues.append(f"File too large: {size_mb:.1f}MB (max {reqs.max_file_size_mb}MB)")
        return len(issues) == 0, issues


# Provider registry
SOCIAL_PROVIDERS: dict[str, type[SocialProvider]] = {
    "simulation": SimulatedSocialProvider,
    # Future: "instagram", "tiktok", "youtube", "x", "facebook", "pinterest", "linkedin"
}

SUPPORTED_PLATFORMS = [
    "instagram",
    "tiktok",
    "youtube",
    "youtube_shorts",
    "facebook",
    "threads",
    "pinterest",
    "linkedin",
    "x",
    "website",
    "blog",
    "email",
    "podcast",
]

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
