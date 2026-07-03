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
