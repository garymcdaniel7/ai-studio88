"""Creator OS API Router — business layer endpoints.

Campaigns, calendar, publishing, analytics, brands, teams,
search, notifications, content repurposing, and AI operations.
"""
from __future__ import annotations

import uuid
import time
from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.creator_os.models import (
    Platform, ContentStatus, TeamRole, NotificationType,
    REPURPOSE_FORMATS,
)

router = APIRouter(prefix="/api/v1", tags=["creator-os"])


# =============================================================================
# In-memory stores (future: Supabase tables)
# =============================================================================

_calendar: list[dict] = []
_campaigns: list[dict] = []
_analytics: list[dict] = []
_brands: list[dict] = []
_team: list[dict] = [
    {"id": "owner-1", "name": "Gary McDaniel", "email": "gary@aistudio.ai", "role": "owner", "active": True},
]
_notifications: list[dict] = []


# =============================================================================
# Content Calendar
# =============================================================================

@router.get("/calendar", tags=["creator-os-calendar"])
def list_calendar(platform: Optional[str] = None, status: Optional[str] = None):
    """List calendar entries, filterable by platform and status."""
    entries = _calendar
    if platform:
        entries = [e for e in entries if e.get("platform") == platform]
    if status:
        entries = [e for e in entries if e.get("status") == status]
    return entries


@router.post("/calendar", tags=["creator-os-calendar"], status_code=201)
def create_calendar_entry(data: dict):
    """Schedule content on the calendar."""
    if not data.get("title"):
        raise HTTPException(status_code=400, detail="'title' required")
    entry = {
        "id": uuid.uuid4().hex[:12],
        "title": data["title"],
        "platform": data.get("platform", "instagram"),
        "content_type": data.get("content_type", "image"),
        "status": data.get("status", "draft"),
        "scheduled_at": data.get("scheduled_at"),
        "campaign_id": data.get("campaign_id"),
        "asset_id": data.get("asset_id"),
        "talent_id": data.get("talent_id"),
        "caption": data.get("caption", ""),
        "hashtags": data.get("hashtags", []),
    }
    _calendar.append(entry)
    return entry


@router.put("/calendar/{entry_id}", tags=["creator-os-calendar"])
def update_calendar_entry(entry_id: str, data: dict):
    """Update a calendar entry (reschedule, change status, etc.)."""
    for entry in _calendar:
        if entry["id"] == entry_id:
            entry.update({k: v for k, v in data.items() if k != "id"})
            return entry
    raise HTTPException(status_code=404, detail="Calendar entry not found")


@router.delete("/calendar/{entry_id}", tags=["creator-os-calendar"])
def delete_calendar_entry(entry_id: str):
    """Remove a calendar entry."""
    global _calendar
    _calendar = [e for e in _calendar if e["id"] != entry_id]
    return {"deleted": True}


# =============================================================================
# Campaigns
# =============================================================================

@router.get("/campaigns", tags=["creator-os-campaigns"])
def list_campaigns(status: Optional[str] = None):
    """List all campaigns."""
    camps = _campaigns
    if status:
        camps = [c for c in camps if c.get("status") == status]
    return camps


@router.post("/campaigns", tags=["creator-os-campaigns"], status_code=201)
def create_campaign(data: dict):
    """Create a new campaign."""
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    campaign = {
        "id": uuid.uuid4().hex[:12],
        "name": data["name"],
        "objective": data.get("objective", ""),
        "platforms": data.get("platforms", ["instagram"]),
        "budget_usd": float(data.get("budget_usd", 0)),
        "target_audience": data.get("target_audience", ""),
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "status": "planning",
        "content_count": 0,
    }
    _campaigns.append(campaign)
    return campaign


@router.get("/campaigns/{campaign_id}", tags=["creator-os-campaigns"])
def get_campaign(campaign_id: str):
    """Get campaign details."""
    for c in _campaigns:
        if c["id"] == campaign_id:
            return c
    raise HTTPException(status_code=404, detail="Campaign not found")


@router.put("/campaigns/{campaign_id}", tags=["creator-os-campaigns"])
def update_campaign(campaign_id: str, data: dict):
    """Update campaign."""
    for c in _campaigns:
        if c["id"] == campaign_id:
            c.update({k: v for k, v in data.items() if k != "id"})
            return c
    raise HTTPException(status_code=404, detail="Campaign not found")


# =============================================================================
# Analytics
# =============================================================================

@router.get("/analytics", tags=["creator-os-analytics"])
def list_analytics(platform: Optional[str] = None, campaign_id: Optional[str] = None):
    """Get analytics data."""
    data = _analytics
    if platform:
        data = [a for a in data if a.get("platform") == platform]
    if campaign_id:
        data = [a for a in data if a.get("campaign_id") == campaign_id]
    return data


@router.post("/analytics", tags=["creator-os-analytics"], status_code=201)
def record_analytics(data: dict):
    """Record an analytics snapshot."""
    snapshot = {
        "id": uuid.uuid4().hex[:12],
        "asset_id": data.get("asset_id"),
        "campaign_id": data.get("campaign_id"),
        "platform": data.get("platform", "instagram"),
        "views": int(data.get("views", 0)),
        "likes": int(data.get("likes", 0)),
        "comments": int(data.get("comments", 0)),
        "shares": int(data.get("shares", 0)),
        "engagement_rate": float(data.get("engagement_rate", 0)),
        "reach": int(data.get("reach", 0)),
        "revenue_usd": float(data.get("revenue_usd", 0)),
        "recorded_at": data.get("recorded_at", ""),
    }
    _analytics.append(snapshot)
    return snapshot


@router.get("/analytics/summary", tags=["creator-os-analytics"])
def analytics_summary():
    """Get aggregate analytics summary."""
    total_views = sum(a.get("views", 0) for a in _analytics)
    total_likes = sum(a.get("likes", 0) for a in _analytics)
    total_revenue = sum(a.get("revenue_usd", 0) for a in _analytics)
    return {
        "total_entries": len(_analytics),
        "total_views": total_views,
        "total_likes": total_likes,
        "total_revenue_usd": total_revenue,
        "avg_engagement": sum(a.get("engagement_rate", 0) for a in _analytics) / max(len(_analytics), 1),
    }


# =============================================================================
# Brands
# =============================================================================

@router.get("/brands", tags=["creator-os-brands"])
def list_brands():
    return _brands


@router.post("/brands", tags=["creator-os-brands"], status_code=201)
def create_brand(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    brand = {"id": uuid.uuid4().hex[:12], **data}
    _brands.append(brand)
    return brand


# =============================================================================
# Team
# =============================================================================

@router.get("/team", tags=["creator-os-team"])
def list_team():
    """List team members."""
    return _team


@router.post("/team", tags=["creator-os-team"], status_code=201)
def add_team_member(data: dict):
    """Add a team member."""
    if not data.get("name") or not data.get("role"):
        raise HTTPException(status_code=400, detail="'name' and 'role' required")
    member = {"id": uuid.uuid4().hex[:12], "active": True, **data}
    _team.append(member)
    return member


@router.get("/team/roles", tags=["creator-os-team"])
def list_roles():
    """List available team roles."""
    return [r.value for r in TeamRole]


# =============================================================================
# Notifications
# =============================================================================

@router.get("/notifications", tags=["creator-os-notifications"])
def list_notifications(unread_only: bool = False):
    """List notifications."""
    notes = _notifications
    if unread_only:
        notes = [n for n in notes if not n.get("read")]
    return notes[-20:]  # Last 20


@router.post("/notifications", tags=["creator-os-notifications"], status_code=201)
def create_notification(data: dict):
    """Create a notification."""
    note = {
        "id": uuid.uuid4().hex[:12],
        "type": data.get("type", "creative_recommendation"),
        "title": data.get("title", ""),
        "message": data.get("message", ""),
        "read": False,
        "created_at": str(time.time()),
    }
    _notifications.append(note)
    return note


@router.get("/notifications/types", tags=["creator-os-notifications"])
def notification_types():
    return [n.value for n in NotificationType]


# =============================================================================
# Content Repurposing
# =============================================================================

@router.get("/repurpose/formats", tags=["creator-os-repurpose"])
def repurpose_formats():
    """List all repurposing formats."""
    return REPURPOSE_FORMATS


@router.post("/repurpose", tags=["creator-os-repurpose"])
def repurpose_content(data: dict):
    """Generate a repurposing plan for an asset.

    Input: asset_id, target_formats[]
    Returns: list of production plans (one per format).
    """
    asset_id = data.get("asset_id")
    targets = data.get("target_formats", REPURPOSE_FORMATS[:5])

    plans = []
    for fmt in targets:
        plans.append({
            "format": fmt,
            "source_asset_id": asset_id,
            "status": "planned",
            "steps": ["resize", "reframe", "caption", "export"],
        })
    return {"asset_id": asset_id, "plans": plans, "count": len(plans)}


# =============================================================================
# Platforms
# =============================================================================

@router.get("/platforms", tags=["creator-os-platforms"])
def list_platforms():
    """List all supported social platforms."""
    return [p.value for p in Platform]


# =============================================================================
# Search (unified)
# =============================================================================

@router.get("/search", tags=["creator-os-search"])
def unified_search(q: str = ""):
    """Search across all platform entities.

    Searches: campaigns, calendar, brands, team, notifications.
    Future: also searches Supabase tables (assets, talent, projects, etc.)
    """
    if not q:
        return {"results": [], "query": ""}

    q_lower = q.lower()
    results = []

    for c in _campaigns:
        if q_lower in c.get("name", "").lower() or q_lower in c.get("objective", "").lower():
            results.append({"type": "campaign", "id": c["id"], "title": c["name"]})

    for e in _calendar:
        if q_lower in e.get("title", "").lower():
            results.append({"type": "calendar", "id": e["id"], "title": e["title"]})

    for b in _brands:
        if q_lower in b.get("name", "").lower():
            results.append({"type": "brand", "id": b["id"], "title": b["name"]})

    return {"query": q, "results": results, "count": len(results)}


# =============================================================================
# AI Operations Assistant
# =============================================================================

@router.get("/ops/recommendations", tags=["creator-os-ops"])
def ops_recommendations():
    """AI Operations Assistant — proactive recommendations.

    Analyzes platform state and suggests actions.
    """
    recs = []

    # Check publishing gaps
    if not _calendar:
        recs.append({
            "type": "publishing_gap",
            "title": "No content scheduled",
            "message": "You haven't scheduled any content. Consider planning your next week.",
            "action": "Create calendar entries",
            "priority": "high",
        })

    # Check campaign status
    active = [c for c in _campaigns if c.get("status") == "active"]
    if not active:
        recs.append({
            "type": "no_campaigns",
            "title": "No active campaigns",
            "message": "Create a campaign to organize your content strategy.",
            "action": "Create a campaign",
            "priority": "medium",
        })

    # Worker utilization (check existing execution system)
    try:
        from backend.execution.worker_manager import get_system_health
        health = get_system_health()
        idle = health.get("online", 0)
        if idle > 0 and not any(a for a in _analytics):
            recs.append({
                "type": "idle_workers",
                "title": f"{idle} worker(s) idle",
                "message": "Workers are available. Consider launching a production.",
                "action": "Start generation",
                "priority": "low",
            })
    except Exception:
        pass

    # Performance insights
    if _analytics:
        avg_engagement = sum(a.get("engagement_rate", 0) for a in _analytics) / len(_analytics)
        if avg_engagement < 3.0:
            recs.append({
                "type": "low_engagement",
                "title": "Engagement below target",
                "message": f"Average engagement: {avg_engagement:.1f}%. Consider adjusting content strategy.",
                "action": "Review Creative DNA",
                "priority": "medium",
            })

    if not recs:
        recs.append({
            "type": "all_good",
            "title": "System running well",
            "message": "No urgent recommendations. Keep creating!",
            "priority": "low",
        })

    return recs


# =============================================================================
# Creator Hub Summary
# =============================================================================

@router.get("/hub/summary", tags=["creator-os-hub"])
def creator_hub_summary():
    """Creator Hub — unified dashboard data.

    Returns all key metrics for the main creator dashboard.
    """
    try:
        from backend.execution.worker_manager import get_system_health
        worker_health = get_system_health()
    except Exception:
        worker_health = {"total_workers": 0, "online": 0}

    return {
        "calendar_entries": len(_calendar),
        "scheduled": len([e for e in _calendar if e.get("status") == "scheduled"]),
        "campaigns_active": len([c for c in _campaigns if c.get("status") == "active"]),
        "campaigns_total": len(_campaigns),
        "brands": len(_brands),
        "team_members": len(_team),
        "notifications_unread": len([n for n in _notifications if not n.get("read")]),
        "analytics_entries": len(_analytics),
        "total_revenue_usd": sum(a.get("revenue_usd", 0) for a in _analytics),
        "workers_online": worker_health.get("online", 0),
        "workers_total": worker_health.get("total_workers", 0),
    }
