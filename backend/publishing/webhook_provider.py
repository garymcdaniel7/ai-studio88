"""Webhook Publishing Provider — push to external tools via HTTP webhooks.

Supports publishing to:
- Buffer
- Hootsuite
- Later
- Custom endpoints (Zapier, Make, n8n)
- Direct platform APIs (Instagram Graph, TikTok, YouTube)

Configuration:
    PUBLISHING_WEBHOOK_URL — Default webhook endpoint
    PUBLISHING_WEBHOOK_SECRET — HMAC secret for webhook signing
    PUBLISHING_LIVE — true to send real webhooks

Each platform can have its own webhook URL configured via the API.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid

import httpx
from dotenv import load_dotenv

from backend.publishing.provider import PlatformRequirements, PublishResult, SocialProvider

load_dotenv()

logger = logging.getLogger(__name__)

WEBHOOK_URL = os.getenv("PUBLISHING_WEBHOOK_URL", "")
WEBHOOK_SECRET = os.getenv("PUBLISHING_WEBHOOK_SECRET", "")
PUBLISHING_LIVE = os.getenv("PUBLISHING_LIVE", "false").lower() == "true"


class WebhookPublishingProvider(SocialProvider):
    """Publishes content via webhooks to external services.

    Sends a signed JSON payload to configured webhook URLs.
    Compatible with Buffer, Hootsuite, Zapier, Make, n8n, or custom handlers.
    """

    def __init__(self, platform: str = "webhook", webhook_url: str = "") -> None:
        self._platform = platform
        self._webhook_url = webhook_url or WEBHOOK_URL

    @property
    def name(self) -> str:
        return f"webhook_{self._platform}"

    def health(self) -> dict:
        return {
            "healthy": bool(self._webhook_url) or not PUBLISHING_LIVE,
            "provider": self.name,
            "mode": "live" if PUBLISHING_LIVE else "simulated",
            "webhook_configured": bool(self._webhook_url),
        }

    def capabilities(self) -> dict:
        return {
            "provider": self.name,
            "platforms": ["instagram", "tiktok", "youtube", "twitter", "linkedin", "pinterest"],
            "features": ["scheduling", "captions", "hashtags", "media_upload"],
            "webhook_url": self._webhook_url[:20] + "..." if self._webhook_url else None,
            "live_mode": PUBLISHING_LIVE,
        }

    def requirements(self) -> PlatformRequirements:
        return PlatformRequirements(
            platform=self._platform,
            aspect_ratios=["1:1", "9:16", "16:9", "4:5"],
            max_duration_seconds=600,
            max_caption_length=5000,
            max_hashtags=30,
            max_file_size_mb=500,
            supported_formats=["image/png", "image/jpeg", "video/mp4", "video/webm"],
        )

    def publish(self, post: dict) -> PublishResult:
        """Publish by sending a webhook to the configured endpoint.

        Post dict should contain:
        - platform, caption, hashtags, media_url, scheduled_for, etc.
        """
        if PUBLISHING_LIVE and self._webhook_url:
            return self._publish_live(post)
        return self._publish_simulated(post)

    def _publish_live(self, post: dict) -> PublishResult:
        """Send real webhook."""
        payload = {
            "event": "publish",
            "timestamp": time.time(),
            "platform": post.get("platform", self._platform),
            "caption": post.get("caption", ""),
            "hashtags": post.get("hashtags", []),
            "media_url": post.get("media_url") or post.get("public_url"),
            "scheduled_for": post.get("scheduled_for"),
            "metadata": {
                "talent_id": post.get("talent_id"),
                "campaign_id": post.get("campaign_id"),
                "asset_id": post.get("asset_id"),
            },
        }

        # Sign the payload
        body = json.dumps(payload, sort_keys=True)
        signature = ""
        if WEBHOOK_SECRET:
            signature = hmac.new(WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-AI-Studio-Signature": signature,
            "X-AI-Studio-Event": "publish",
        }

        try:
            resp = httpx.post(self._webhook_url, content=body, headers=headers, timeout=15)
            if resp.status_code in (200, 201, 202):
                return PublishResult(
                    success=True,
                    provider_post_id=str(uuid.uuid4()),
                    message=f"Webhook delivered to {self._webhook_url[:30]}",
                    metadata={"webhook_status": resp.status_code, "provider": self.name},
                )
            return PublishResult(
                success=False,
                message=f"Webhook returned {resp.status_code}: {resp.text[:100]}",
            )
        except Exception as e:
            return PublishResult(success=False, message=f"Webhook failed: {e}")

    def _publish_simulated(self, post: dict) -> PublishResult:
        """Simulated webhook publishing."""
        return PublishResult(
            success=True,
            provider_post_id=f"sim_{uuid.uuid4().hex[:12]}",
            published_url=f"https://{self._platform}.com/p/simulated",
            message=f"[simulated] Would publish to {self._platform} via webhook",
            metadata={
                "provider": self.name,
                "mode": "simulated",
                "platform": post.get("platform", self._platform),
                "caption_length": len(post.get("caption", "")),
            },
        )

    def fetch_analytics(self, post_id: str) -> dict:
        """Fetch analytics — simulated for now."""
        return {
            "post_id": post_id,
            "views": 0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "engagement_rate": 0.0,
            "provider": self.name,
            "note": "Analytics via webhook not yet implemented",
        }

    def validate_media(self, asset: dict) -> tuple[bool, list[str]]:
        """Validate media against platform requirements."""
        issues = []
        reqs = self.requirements()

        size_bytes = asset.get("size_bytes", 0)
        if size_bytes > reqs.max_file_size_mb * 1024 * 1024:
            issues.append(f"File too large: {size_bytes / 1e6:.1f}MB > {reqs.max_file_size_mb}MB")

        mime = asset.get("mime_type", "")
        if mime and mime not in reqs.supported_formats:
            issues.append(f"Unsupported format: {mime}")

        return (len(issues) == 0, issues)
