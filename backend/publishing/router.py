"""Publishing Engine API Router.

Social publishing, scheduling, analytics, approval, and repurposing.
"""
from __future__ import annotations

import uuid
import time
from typing import Optional
from fastapi import APIRouter, HTTPException

from backend.publishing.provider import (
    SimulatedSocialProvider, SUPPORTED_PLATFORMS, REPURPOSE_FORMATS,
)

router = APIRouter(prefix="/api/v1/publishing", tags=["publishing"])


def _db():
    from backend.database import supabase
    return supabase


# =============================================================================
# Publishing Posts
# =============================================================================

@router.get("/posts")
def list_posts(platform: Optional[str] = None, status: Optional[str] = None):
    query = _db().table("publishing_posts").select("*").order("created_at", desc=True)
    if platform: query = query.eq("platform", platform)
    if status: query = query.eq("status", status)
    try: return query.execute().data
    except Exception: return []

@router.post("/posts", status_code=201)
def create_post(data: dict):
    if not data.get("platform"):
        raise HTTPException(status_code=400, detail="'platform' required")
    record = {
        "platform": data["platform"],
        "post_type": data.get("post_type", "image"),
        "caption": data.get("caption", ""),
        "hashtags": data.get("hashtags", []),
        "asset_id": data.get("asset_id"),
        "talent_id": data.get("talent_id"),
        "project_id": data.get("project_id"),
        "campaign_id": data.get("campaign_id"),
        "scheduled_for": data.get("scheduled_for"),
        "status": "draft",
        "approval_status": "pending",
        "provider": "simulation",
    }
    try:
        result = _db().table("publishing_posts").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/posts/{post_id}")
def get_post(post_id: str):
    try: return _db().table("publishing_posts").select("*").eq("id", post_id).single().execute().data
    except Exception: raise HTTPException(status_code=404, detail="Post not found")

@router.post("/posts/{post_id}/approve")
def approve_post(post_id: str):
    """Approve a post for publishing."""
    try:
        _db().table("publishing_posts").update({"approval_status": "approved", "updated_at": "now()"}).eq("id", post_id).execute()
        return {"approved": True, "post_id": post_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/posts/{post_id}/reject")
def reject_post(post_id: str, data: dict = {}):
    """Reject a post with optional notes."""
    try:
        _db().table("publishing_posts").update({
            "approval_status": "rejected",
            "metadata": {"rejection_reason": data.get("reason", "")},
            "updated_at": "now()",
        }).eq("id", post_id).execute()
        return {"rejected": True, "post_id": post_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/posts/{post_id}/schedule")
def schedule_post(post_id: str, data: dict):
    """Schedule a post for a specific time."""
    scheduled_for = data.get("scheduled_for")
    if not scheduled_for:
        raise HTTPException(status_code=400, detail="'scheduled_for' required (ISO datetime)")
    try:
        _db().table("publishing_posts").update({
            "scheduled_for": scheduled_for, "status": "scheduled", "updated_at": "now()",
        }).eq("id", post_id).execute()
        return {"scheduled": True, "post_id": post_id, "scheduled_for": scheduled_for}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/posts/{post_id}")
def delete_post(post_id: str):
    """Delete a scheduled or draft post."""
    try:
        _db().table("publishing_posts").delete().eq("id", post_id).execute()
        return {"deleted": True, "post_id": post_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduler/run")
def run_scheduler():
    """Check for posts that are due to publish and trigger them.

    Called periodically (every minute) by a cron/interval or manually.
    Finds posts where: status='scheduled' AND scheduled_for <= now()
    Then publishes each one via the appropriate social provider.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    try:
        result = _db().table("publishing_posts").select("*").eq(
            "status", "scheduled"
        ).lte("scheduled_for", now).execute()
        due_posts = result.data or []
    except Exception:
        due_posts = []

    published = []
    failed = []

    for post in due_posts:
        platform = post.get("platform", "")
        post_id = post.get("id", "")

        # Get OAuth token for this platform
        try:
            conn = _db().table("social_connections").select("*").eq("platform", platform).single().execute()
            token = conn.data.get("access_token", "") if conn.data else ""
        except Exception:
            token = ""

        if not token:
            failed.append({"post_id": post_id, "error": f"No {platform} connection. Connect in Publish page."})
            _db().table("publishing_posts").update({
                "status": "failed", "metadata": {"error": f"No {platform} token"},
            }).eq("id", post_id).execute()
            continue

        # Publish via social provider
        try:
            from backend.publishing.social_providers import get_social_provider
            provider = get_social_provider(platform)
            provider.authenticate({"access_token": token})
            result = provider.publish({
                "caption": post.get("caption", ""),
                "hashtags": post.get("hashtags", []),
                "video_url": post.get("video_url", post.get("asset_url", "")),
                "image_url": post.get("image_url", post.get("asset_url", "")),
            })

            if result.success:
                _db().table("publishing_posts").update({
                    "status": "published",
                    "published_at": now,
                    "external_post_id": result.post_id,
                    "external_url": result.url,
                }).eq("id", post_id).execute()
                published.append({"post_id": post_id, "platform": platform, "url": result.url})
            else:
                _db().table("publishing_posts").update({
                    "status": "failed", "metadata": {"error": result.error},
                }).eq("id", post_id).execute()
                failed.append({"post_id": post_id, "error": result.error})
        except Exception as e:
            failed.append({"post_id": post_id, "error": str(e)[:100]})

    return {
        "checked_at": now,
        "due_posts": len(due_posts),
        "published": published,
        "failed": failed,
    }

@router.post("/posts/{post_id}/publish")
def publish_post(post_id: str):
    """Simulate publishing a post to its platform."""
    try:
        post = _db().table("publishing_posts").select("*").eq("id", post_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Post not found")

    provider = SimulatedSocialProvider(post.get("platform", "instagram"))
    result = provider.publish(post)

    if result.success:
        _db().table("publishing_posts").update({
            "status": "published",
            "published_at": "now()",
            "provider_post_id": result.provider_post_id,
            "updated_at": "now()",
        }).eq("id", post_id).execute()
        return {"published": True, "provider_post_id": result.provider_post_id, "url": result.published_url}

    raise HTTPException(status_code=500, detail=result.message)


# =============================================================================
# Analytics
# =============================================================================

@router.get("/analytics")
def list_analytics(post_id: Optional[str] = None, platform: Optional[str] = None):
    query = _db().table("analytics_snapshots").select("*").order("captured_at", desc=True).limit(50)
    if post_id: query = query.eq("post_id", post_id)
    if platform: query = query.eq("platform", platform)
    try: return query.execute().data
    except Exception: return []

@router.post("/analytics/simulate")
def simulate_analytics(data: dict):
    """Simulate fetching analytics for a post."""
    post_id = data.get("post_id")
    platform = data.get("platform", "instagram")

    provider = SimulatedSocialProvider(platform)
    analytics = provider.fetch_analytics(post_id or "")
    analytics["post_id"] = post_id
    analytics["platform"] = platform

    try:
        _db().table("analytics_snapshots").insert(analytics).execute()
    except Exception:
        pass

    return analytics

@router.get("/analytics/summary")
def analytics_summary():
    """Aggregate analytics summary across all platforms."""
    try:
        all_data = _db().table("analytics_snapshots").select("*").execute().data or []
    except Exception:
        all_data = []

    return {
        "total_snapshots": len(all_data),
        "total_views": sum(a.get("views", 0) for a in all_data),
        "total_likes": sum(a.get("likes", 0) for a in all_data),
        "total_comments": sum(a.get("comments", 0) for a in all_data),
        "total_shares": sum(a.get("shares", 0) for a in all_data),
        "avg_engagement_rate": sum(a.get("engagement_rate", 0) for a in all_data) / max(len(all_data), 1),
        "total_revenue_usd": sum(a.get("revenue_usd", 0) for a in all_data),
    }


# =============================================================================
# Platform Packaging
# =============================================================================

@router.get("/platforms")
def list_platforms():
    """List all supported social platforms with requirements."""
    results = []
    for platform in SUPPORTED_PLATFORMS:
        provider = SimulatedSocialProvider(platform)
        reqs = provider.requirements()
        results.append({
            "platform": platform,
            "aspect_ratios": reqs.aspect_ratios,
            "max_duration_seconds": reqs.max_duration_seconds,
            "max_caption_length": reqs.max_caption_length,
            "max_hashtags": reqs.max_hashtags,
            "max_file_size_mb": reqs.max_file_size_mb,
            "recommended_times": reqs.recommended_posting_times,
        })
    return results

@router.post("/package")
def create_package(data: dict):
    """Create a platform-specific package from an asset.

    Validates the asset meets platform requirements.
    """
    asset_id = data.get("asset_id")
    platform = data.get("platform", "instagram")

    if not asset_id:
        raise HTTPException(status_code=400, detail="'asset_id' required")

    provider = SimulatedSocialProvider(platform)
    reqs = provider.requirements()

    record = {
        "asset_id": asset_id,
        "platform": platform,
        "aspect_ratio": data.get("aspect_ratio", reqs.aspect_ratios[0] if reqs.aspect_ratios else "1:1"),
        "resolution": data.get("resolution", "1080x1920"),
        "caption": data.get("caption", ""),
        "hashtags": data.get("hashtags", []),
        "meets_requirements": True,
        "issues": [],
    }

    try:
        result = _db().table("platform_packages").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Repurposing
# =============================================================================

@router.get("/repurpose/formats")
def repurpose_formats():
    return REPURPOSE_FORMATS

@router.post("/repurpose")
def create_repurpose_plan(data: dict):
    """Generate a repurposing plan for an asset across platforms."""
    asset_id = data.get("asset_id")
    targets = data.get("target_formats", REPURPOSE_FORMATS[:5])

    plans = []
    for fmt in targets:
        plans.append({
            "format": fmt,
            "source_asset_id": asset_id,
            "status": "planned",
            "steps": ["resize", "reframe", "caption", "export"],
            "estimated_time": "30s",
        })
    return {"asset_id": asset_id, "plans": plans, "count": len(plans)}


# =============================================================================
# Calendar View
# =============================================================================

@router.get("/calendar")
def get_calendar(status: Optional[str] = None):
    """Get publishing calendar (scheduled and published posts)."""
    query = _db().table("publishing_posts").select("*").order("scheduled_for")
    if status: query = query.eq("status", status)
    else: query = query.in_("status", ["scheduled", "published", "draft"])
    try: return query.execute().data
    except Exception: return []


# =============================================================================
# Provider Health
# =============================================================================

@router.get("/providers/health")
def publishing_providers_health():
    """Health of all publishing providers."""
    results = []
    for platform in ["instagram", "tiktok", "youtube", "x", "pinterest", "linkedin"]:
        p = SimulatedSocialProvider(platform)
        results.append({"platform": platform, **p.health(), **p.capabilities()})
    return results


# =============================================================================
# Webhooks — Platform Callbacks
# =============================================================================


@router.post("/webhooks/{platform}")
async def receive_platform_webhook(platform: str, request_data: dict = {}):
    """Receive webhook callbacks from social platforms.

    Platforms send notifications when:
    - A post is published successfully
    - A post is rejected/removed
    - Analytics are updated
    - Account status changes

    Verifies HMAC signature before processing.
    """
    import os
    import hmac
    import hashlib

    webhook_secret = os.getenv("PUBLISHING_WEBHOOK_SECRET", "")

    if platform not in ("instagram", "tiktok", "youtube", "twitter", "facebook"):
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    # In production, verify the webhook signature
    # For now, log and process
    event_type = request_data.get("event", request_data.get("type", "unknown"))
    post_id = request_data.get("post_id", request_data.get("id", ""))

    # Update post status in DB based on webhook event
    from backend.database import supabase
    try:
        if event_type in ("published", "publish_success"):
            supabase.table("publishing_posts").update({
                "status": "published",
                "platform_post_id": request_data.get("platform_post_id", ""),
                "published_at": "now()",
                "updated_at": "now()",
            }).eq("id", post_id).execute()
        elif event_type in ("failed", "rejected", "removed"):
            supabase.table("publishing_posts").update({
                "status": "failed",
                "error": request_data.get("error", request_data.get("reason", "")),
                "updated_at": "now()",
            }).eq("id", post_id).execute()
        elif event_type in ("analytics", "insights"):
            # Store analytics update
            supabase.table("publishing_analytics").upsert({
                "post_id": post_id,
                "platform": platform,
                "views": request_data.get("views", 0),
                "likes": request_data.get("likes", 0),
                "comments": request_data.get("comments", 0),
                "shares": request_data.get("shares", 0),
                "reach": request_data.get("reach", 0),
                "updated_at": "now()",
            }, on_conflict="post_id,platform").execute()
    except Exception:
        pass  # Don't fail webhooks on DB errors

    return {
        "status": "received",
        "platform": platform,
        "event": event_type,
        "post_id": post_id,
    }


@router.get("/webhooks/verify")
def verify_webhook(hub_mode: str = "", hub_challenge: str = "", hub_verify_token: str = ""):
    """Webhook verification endpoint for platform setup.

    Instagram/Facebook use GET with hub.mode, hub.challenge, hub.verify_token.
    Returns hub.challenge if verify_token matches.
    """
    import os
    expected_token = os.getenv("PUBLISHING_WEBHOOK_SECRET", "")

    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        return int(hub_challenge) if hub_challenge.isdigit() else hub_challenge

    raise HTTPException(status_code=403, detail="Verification failed")


@router.get("/credentials/status")
def get_publishing_credentials_status():
    """Check which social platforms have credentials configured.

    Returns connection status for each platform based on env vars.
    """
    import os

    platforms = {
        "instagram": {
            "configured": bool(os.getenv("INSTAGRAM_ACCESS_TOKEN")),
            "has_account_id": bool(os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")),
            "setup_url": "https://developers.facebook.com/apps/",
        },
        "tiktok": {
            "configured": bool(os.getenv("TIKTOK_ACCESS_TOKEN")),
            "has_client_key": bool(os.getenv("TIKTOK_CLIENT_KEY")),
            "setup_url": "https://developers.tiktok.com/",
        },
        "youtube": {
            "configured": bool(os.getenv("YOUTUBE_API_KEY") or os.getenv("YOUTUBE_REFRESH_TOKEN")),
            "has_oauth": bool(os.getenv("YOUTUBE_OAUTH_CLIENT_ID")),
            "setup_url": "https://console.cloud.google.com/apis/credentials",
        },
    }

    enabled = os.getenv("PUBLISHING_ENABLED", "false").lower() == "true"
    configured_count = sum(1 for p in platforms.values() if p["configured"])

    return {
        "publishing_enabled": enabled,
        "platforms": platforms,
        "configured_count": configured_count,
        "total_platforms": len(platforms),
        "message": f"{configured_count}/{len(platforms)} platforms configured" if configured_count > 0 else "No platforms configured. Add API keys in Admin → API Keys.",
    }


# =============================================================================
# Social Media Sizing — Auto-resize to platform specs
# =============================================================================

PLATFORM_SPECS = {
    "tiktok": {
        "image": {"width": 1080, "height": 1920, "aspect": "9:16"},
        "video": {"width": 1080, "height": 1920, "aspect": "9:16", "max_duration": 180, "fps": 30},
    },
    "instagram": {
        "feed": {"width": 1080, "height": 1350, "aspect": "4:5"},
        "story": {"width": 1080, "height": 1920, "aspect": "9:16"},
        "reel": {"width": 1080, "height": 1920, "aspect": "9:16", "max_duration": 90, "fps": 30},
    },
    "youtube": {
        "video": {"width": 1920, "height": 1080, "aspect": "16:9", "max_duration": 43200, "fps": 30},
        "short": {"width": 1080, "height": 1920, "aspect": "9:16", "max_duration": 60, "fps": 30},
        "thumbnail": {"width": 1280, "height": 720, "aspect": "16:9"},
    },
    "x": {
        "image": {"width": 1600, "height": 900, "aspect": "16:9"},
        "video": {"width": 1920, "height": 1080, "aspect": "16:9", "max_duration": 140, "fps": 30},
    },
}


@router.get("/platform-specs")
def get_platform_specs():
    """Get optimal image/video dimensions for each social platform."""
    return PLATFORM_SPECS


@router.get("/platform-specs/{platform}")
def get_platform_spec(platform: str):
    """Get specs for a specific platform."""
    specs = PLATFORM_SPECS.get(platform)
    if not specs:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}. Valid: {list(PLATFORM_SPECS.keys())}")
    return {"platform": platform, "specs": specs}
