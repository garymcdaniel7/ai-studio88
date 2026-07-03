"""Studio Orchestrator — runs all departments and produces the Daily Briefing.

Builds StudioContext from all platform subsystems, runs each department,
assembles recommendations, and manages approval workflows.
"""
from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field
from typing import Any

from backend.autonomous_studio.department import Department, DepartmentOutput, Recommendation
from backend.autonomous_studio.departments import ALL_DEPARTMENTS


# =============================================================================
# Studio Context Builder
# =============================================================================

def build_studio_context() -> dict:
    """Build the full studio context from all platform subsystems.

    Reads from Creator OS, Execution Platform, Creative DNA, etc.
    """
    ctx: dict[str, Any] = {}

    # Creator OS state
    try:
        from backend.creator_os.router import _calendar, _campaigns, _analytics, _brands, _team, _notifications
        ctx["calendar_count"] = len(_calendar)
        ctx["scheduled_count"] = len([e for e in _calendar if e.get("status") == "scheduled"])
        ctx["unpublished_count"] = len([e for e in _calendar if e.get("status") == "draft"])
        ctx["campaigns"] = _campaigns
        ctx["campaigns_active"] = len([c for c in _campaigns if c.get("status") == "active"])
        ctx["analytics_count"] = len(_analytics)
        ctx["engagement_rate"] = sum(a.get("engagement_rate", 0) for a in _analytics) / max(len(_analytics), 1)
        ctx["total_revenue"] = sum(a.get("revenue_usd", 0) for a in _analytics)
        ctx["brands_count"] = len(_brands)
        ctx["team_count"] = len(_team)
        ctx["notifications_unread"] = len([n for n in _notifications if not n.get("read")])
    except Exception:
        pass

    # Execution Platform state
    try:
        from backend.execution.worker_manager import get_system_health
        health = get_system_health()
        ctx["workers_online"] = health.get("online", 0)
        ctx["workers_total"] = health.get("total_workers", 0)
        ctx["workers_busy"] = health.get("busy", 0)
        ctx["vram_free_gb"] = health.get("free_vram_gb", 0)
    except Exception:
        ctx["workers_online"] = 0

    # Intelligence: check if Creative DNA exists for any talent
    try:
        from backend.database import supabase
        dna = supabase.table("creative_dna").select("id").limit(1).execute()
        ctx["creative_dna"] = bool(dna.data)
    except Exception:
        ctx["creative_dna"] = False

    # Talent count
    try:
        from backend.database import supabase
        talent = supabase.table("talent").select("id").execute()
        ctx["talent_count"] = len(talent.data) if talent.data else 0
    except Exception:
        ctx["talent_count"] = 0

    # Recent feedback issues
    try:
        from backend.database import supabase
        fb = supabase.table("generation_feedback").select("problems").order("created_at", desc=True).limit(20).execute()
        all_problems = []
        for row in (fb.data or []):
            if row.get("problems"):
                all_problems.extend(row["problems"])
        ctx["feedback_issues"] = all_problems
        ctx["recent_low_ratings"] = False  # Simplified
    except Exception:
        ctx["feedback_issues"] = []

    # Studio Memory (recommendation tracking)
    ctx["recommendations_accepted"] = _memory.get("accepted", 0)
    ctx["recommendations_rejected"] = _memory.get("rejected", 0)

    return ctx


# =============================================================================
# Studio Memory (in-memory, future: DB-backed)
# =============================================================================

_memory: dict[str, Any] = {
    "accepted": 0,
    "rejected": 0,
    "history": [],  # List of {recommendation, outcome, timestamp}
}


def record_decision(recommendation_id: str, decision: str, notes: str = "") -> None:
    """Record a user decision on a recommendation."""
    if decision == "approved":
        _memory["accepted"] += 1
    elif decision == "rejected":
        _memory["rejected"] += 1
    _memory["history"].append({
        "id": recommendation_id,
        "decision": decision,
        "notes": notes,
        "timestamp": time.time(),
    })


def get_memory_stats() -> dict:
    """Get recommendation memory statistics."""
    total = _memory["accepted"] + _memory["rejected"]
    accuracy = (_memory["accepted"] / max(total, 1)) * 100
    return {
        "accepted": _memory["accepted"],
        "rejected": _memory["rejected"],
        "total_decisions": total,
        "accuracy_pct": round(accuracy, 1),
        "history_count": len(_memory["history"]),
    }


# =============================================================================
# Run All Departments
# =============================================================================

def run_all_departments(context: dict | None = None) -> list[DepartmentOutput]:
    """Run every department against the current studio context."""
    ctx = context or build_studio_context()
    outputs = []
    for dept_class in ALL_DEPARTMENTS:
        dept = dept_class()
        try:
            output = dept.analyze(ctx)
            outputs.append(output)
        except Exception as e:
            outputs.append(DepartmentOutput(
                department=dept.name,
                recommendations=[],
                summary=f"Error: {e}",
                health="critical",
            ))
    return outputs


def get_all_recommendations(context: dict | None = None) -> list[Recommendation]:
    """Get all recommendations from all departments, sorted by priority."""
    outputs = run_all_departments(context)
    all_recs = []
    for output in outputs:
        all_recs.extend(output.recommendations)

    # Sort: critical > high > medium > low
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_recs.sort(key=lambda r: (priority_order.get(r.priority, 3), -r.confidence))
    return all_recs


# =============================================================================
# Daily Briefing
# =============================================================================

def generate_daily_briefing() -> dict:
    """Generate the Daily Briefing for the creator.

    Aggregates status from all subsystems into one unified view.
    """
    ctx = build_studio_context()
    outputs = run_all_departments(ctx)
    recommendations = get_all_recommendations(ctx)

    # Department health summary
    dept_health = {}
    for output in outputs:
        dept_health[output.department] = output.health

    # Count recommendations by priority
    priority_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for rec in recommendations:
        priority_counts[rec.priority] = priority_counts.get(rec.priority, 0) + 1

    return {
        "briefing_id": uuid.uuid4().hex[:12],
        "timestamp": time.time(),

        # Status
        "production_status": {
            "workers_online": ctx.get("workers_online", 0),
            "workers_busy": ctx.get("workers_busy", 0),
            "vram_free_gb": ctx.get("vram_free_gb", 0),
        },
        "publishing_status": {
            "scheduled": ctx.get("scheduled_count", 0),
            "drafts": ctx.get("unpublished_count", 0),
        },
        "campaign_health": {
            "active": ctx.get("campaigns_active", 0),
            "total": len(ctx.get("campaigns", [])),
        },
        "analytics_summary": {
            "total_entries": ctx.get("analytics_count", 0),
            "avg_engagement": ctx.get("engagement_rate", 0),
            "total_revenue": ctx.get("total_revenue", 0),
        },

        # Recommendations
        "recommendations_count": len(recommendations),
        "priority_breakdown": priority_counts,
        "top_recommendations": [
            {
                "department": r.department,
                "title": r.title,
                "description": r.description,
                "reasoning": r.reasoning,
                "confidence": r.confidence,
                "priority": r.priority,
                "action": r.action,
            }
            for r in recommendations[:10]
        ],

        # Department health
        "department_health": dept_health,

        # Memory
        "learning": get_memory_stats(),

        # Alerts
        "alerts": [r.title for r in recommendations if r.priority == "critical"],
    }


# =============================================================================
# Multi-Agent Discussion
# =============================================================================

def department_discussion(topic: str, context: dict | None = None) -> list[dict]:
    """Simulate a multi-agent discussion on a topic.

    Each department provides its perspective in sequence, building on
    previous contributions. Returns the discussion log.
    """
    ctx = context or build_studio_context()
    ctx["discussion_topic"] = topic
    discussion = []

    for dept_class in ALL_DEPARTMENTS:
        dept = dept_class()
        try:
            output = dept.analyze(ctx)
            if output.recommendations:
                for rec in output.recommendations[:1]:  # One contribution per dept
                    discussion.append({
                        "department": dept.name,
                        "role": dept.role,
                        "contribution": rec.title,
                        "detail": rec.description,
                        "confidence": rec.confidence,
                    })
            elif output.summary:
                discussion.append({
                    "department": dept.name,
                    "role": dept.role,
                    "contribution": output.summary,
                    "detail": "",
                    "confidence": 0.5,
                })
        except Exception:
            pass

    return discussion
