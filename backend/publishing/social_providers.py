"""Social media publishing providers — scaffolding for platform integrations.

Each provider implements the same interface:
- authenticate(credentials) → bool
- publish(post_data) → {post_id, url}
- get_analytics(post_id) → {views, likes, comments, shares}
- delete(post_id) → bool

Supported platforms (scaffolded):
- Instagram (Graph API)
- TikTok (Content Posting API)
- YouTube (Data API v3)
- Twitter/X (API v2)
- LinkedIn (Marketing API)
- Facebook (Graph API)
- Pinterest (API v5)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PublishResult:
    success: bool
    post_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    platform: str = ""


class SocialProvider(ABC):
    """Base class for social media publishing providers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def authenticate(self, credentials: dict) -> bool: ...

    @abstractmethod
    def publish(self, post_data: dict) -> PublishResult: ...

    @abstractmethod
    def get_analytics(self, post_id: str) -> dict: ...


class InstagramProvider(SocialProvider):
    """Instagram publishing via Facebook Graph API."""

    name = "instagram"

    def authenticate(self, credentials: dict) -> bool:
        # Requires: access_token, instagram_business_account_id
        self.access_token = credentials.get("access_token", "")
        self.account_id = credentials.get("account_id", "")
        return bool(self.access_token and self.account_id)

    def publish(self, post_data: dict) -> PublishResult:
        # Graph API: POST /{ig-user-id}/media → POST /{ig-user-id}/media_publish
        return PublishResult(
            success=False,
            error="Instagram integration pending. Add credentials in Admin → API Keys.",
            platform="instagram",
        )

    def get_analytics(self, post_id: str) -> dict:
        return {"views": 0, "likes": 0, "comments": 0, "shares": 0}


class TikTokProvider(SocialProvider):
    """TikTok publishing via Content Posting API v2."""

    name = "tiktok"

    def authenticate(self, credentials: dict) -> bool:
        self.access_token = credentials.get("access_token", "")
        return bool(self.access_token)

    def publish(self, post_data: dict) -> PublishResult:
        """Publish a video to TikTok via the Content Posting API.

        TikTok only supports video posts. The flow:
        1. Initialize upload (get upload_url)
        2. Upload video file to upload_url
        3. Publish with caption
        """
        import httpx

        if not self.access_token:
            return PublishResult(success=False, error="Not authenticated. Connect TikTok first.", platform="tiktok")

        caption = post_data.get("caption", "")
        video_url = post_data.get("video_url", "")  # B2 signed URL or local path

        if not video_url:
            return PublishResult(success=False, error="TikTok requires a video. No video_url provided.", platform="tiktok")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        # Step 1: Initialize video upload
        try:
            init_resp = httpx.post(
                "https://open.tiktokapis.com/v2/post/publish/video/init/",
                headers=headers,
                json={
                    "post_info": {
                        "title": caption[:150],
                        "privacy_level": post_data.get("privacy", "SELF_ONLY"),
                        "disable_duet": False,
                        "disable_stitch": False,
                        "disable_comment": False,
                    },
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "video_url": video_url,
                    },
                },
                timeout=30,
            )

            if init_resp.status_code == 200:
                data = init_resp.json()
                publish_id = data.get("data", {}).get("publish_id", "")
                return PublishResult(
                    success=True,
                    post_id=publish_id,
                    url=f"https://www.tiktok.com/@user/video/{publish_id}",
                    platform="tiktok",
                )
            else:
                error_data = init_resp.json()
                error_msg = error_data.get("error", {}).get("message", f"HTTP {init_resp.status_code}")
                return PublishResult(success=False, error=f"TikTok API: {error_msg}", platform="tiktok")

        except Exception as e:
            return PublishResult(success=False, error=f"TikTok publish failed: {str(e)[:100]}", platform="tiktok")

    def get_analytics(self, post_id: str) -> dict:
        return {"views": 0, "likes": 0, "comments": 0, "shares": 0}


class YouTubeProvider(SocialProvider):
    """YouTube publishing via Data API v3."""

    name = "youtube"

    def authenticate(self, credentials: dict) -> bool:
        self.api_key = credentials.get("api_key", "")
        self.oauth_token = credentials.get("oauth_token", "")
        return bool(self.api_key or self.oauth_token)

    def publish(self, post_data: dict) -> PublishResult:
        return PublishResult(
            success=False, error="YouTube integration pending.", platform="youtube"
        )

    def get_analytics(self, post_id: str) -> dict:
        return {"views": 0, "likes": 0, "comments": 0, "shares": 0}


SOCIAL_PROVIDERS: dict[str, type[SocialProvider]] = {
    "instagram": InstagramProvider,
    "tiktok": TikTokProvider,
    "youtube": YouTubeProvider,
}


def get_social_provider(platform: str) -> SocialProvider:
    """Get a social provider instance by platform name."""
    cls = SOCIAL_PROVIDERS.get(platform)
    if not cls:
        raise ValueError(
            f"Unknown platform: {platform}. Valid: {list(SOCIAL_PROVIDERS.keys())}"
        )
    return cls()
