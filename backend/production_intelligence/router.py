"""Production Intelligence API Router.

Executive Producer, Director, Editor, Model/GPU Advisors, Quality Scoring,
Self-Healing, and Learning System endpoints.
"""
from __future__ import annotations

import uuid
import time
from typing import Optional
from fastapi import APIRouter, HTTPException

from backend.production_intelligence.agents import (
    run_all_agents, QualityScorer, PRODUCTION_AGENTS,
)

router = APIRouter(prefix="/api/v1/intelligence", tags=["production-intelligence"])


# =============================================================================
# In-memory stores (future: Supabase-backed)
# =============================================================================

_quality_scores: list[dict] = []
_learning_events: list[dict] = []
_production_insights: list[dict] = []


def _build_context() -> dict:
    """Build context from platform state for agents to reason over."""
    ctx = {}
    try:
        from backend.execution.worker_manager import get_system_health
        health = get_system_health()
        ctx["workers_online"] = health.get("online", 0)
        ctx["vram_free_gb"] = health.get("free_vram_gb", 0)
    except Exception:
        ctx["workers_online"] = 0
        ctx["vram_free_gb"] = 0

    try:
        from backend.database import supabase
        jobs = supabase.table("jobs").select("id").eq("status", "failed").execute()
        ctx["failed_jobs"] = len(jobs.data) if jobs.data else 0
        pending = supabase.table("jobs").select("id").eq("status", "queued").execute()
        ctx["pending_jobs"] = len(pending.data) if pending.data else 0
    except Exception:
        ctx["failed_jobs"] = 0
        ctx["pending_jobs"] = 0

    ctx["average_quality"] = sum(s.get("overall", 0.8) for s in _quality_scores[-10:]) / max(len(_quality_scores[-10:]), 1) if _quality_scores else 0.8

    return ctx


# =============================================================================
# Insights (all agents)
# =============================================================================

@router.get("/production-insights")
def get_production_insights():
    """Run all production intelligence agents and get insights."""
    ctx = _build_context()
    insights = run_all_agents(ctx)
    return [
        {
            "agent": i.agent,
            "title": i.title,
            "description": i.description,
            "reasoning": i.reasoning,
            "confidence": i.confidence,
            "priority": i.priority,
            "action": i.action,
            "estimated_impact": i.estimated_impact,
        }
        for i in insights
    ]


@router.get("/production-insights/agents")
def list_production_agents():
    """List all production intelligence agents."""
    return [
        {"name": a().name if hasattr(a, 'name') else a.__name__,
         "class": a.__name__}
        for a in PRODUCTION_AGENTS
    ]


# =============================================================================
# Quality Scoring
# =============================================================================

@router.post("/quality-score")
def score_quality(data: dict):
    """Score a generated asset on multiple quality dimensions.

    Body: {"asset_id": "...", "metadata": {...}}
    Returns: quality scores + overall rating
    """
    scorer = QualityScorer()
    scores = scorer.score(data.get("metadata", {}))
    scores["asset_id"] = data.get("asset_id")
    scores["scored_at"] = time.time()
    _quality_scores.append(scores)
    return scores


@router.get("/quality-scores")
def list_quality_scores(limit: int = 20):
    """Get recent quality scores."""
    return _quality_scores[-limit:]


@router.get("/quality-scores/summary")
def quality_summary():
    """Get aggregate quality summary."""
    if not _quality_scores:
        return {"count": 0, "average_overall": 0.0, "message": "No scores yet"}

    recent = _quality_scores[-20:]
    return {
        "count": len(_quality_scores),
        "recent_count": len(recent),
        "average_overall": sum(s.get("overall", 0) for s in recent) / len(recent),
        "average_identity": sum(s.get("identity_consistency", 0) for s in recent) / len(recent),
        "average_composition": sum(s.get("composition", 0) for s in recent) / len(recent),
        "average_hands": sum(s.get("hands", 0) for s in recent) / len(recent),
    }


# =============================================================================
# Learning Events
# =============================================================================

@router.post("/learning/event")
def record_learning_event(data: dict):
    """Record a learning event (what worked, what didn't)."""
    event = {
        "id": uuid.uuid4().hex[:12],
        "type": data.get("type", "observation"),
        "description": data.get("description", ""),
        "outcome": data.get("outcome", ""),
        "impact": data.get("impact", "neutral"),
        "recorded_at": time.time(),
        "metadata": data.get("metadata", {}),
    }
    _learning_events.append(event)
    return event


@router.get("/learning/events")
def list_learning_events(limit: int = 20):
    """Get recent learning events."""
    return _learning_events[-limit:]


@router.get("/learning/summary")
def learning_summary():
    """Summary of what the system has learned."""
    positive = [e for e in _learning_events if e.get("impact") == "positive"]
    negative = [e for e in _learning_events if e.get("impact") == "negative"]
    return {
        "total_events": len(_learning_events),
        "positive_outcomes": len(positive),
        "negative_outcomes": len(negative),
        "neutral": len(_learning_events) - len(positive) - len(negative),
        "learning_rate": len(positive) / max(len(_learning_events), 1),
    }


# =============================================================================
# Production Reports
# =============================================================================

@router.get("/reports/production")
def production_report():
    """Auto-generated production summary report."""
    ctx = _build_context()
    return {
        "report_type": "production_summary",
        "generated_at": time.time(),
        "workers_online": ctx.get("workers_online", 0),
        "pending_jobs": ctx.get("pending_jobs", 0),
        "failed_jobs": ctx.get("failed_jobs", 0),
        "average_quality": ctx.get("average_quality", 0),
        "quality_scores_count": len(_quality_scores),
        "learning_events_count": len(_learning_events),
        "insights_count": len(run_all_agents(ctx)),
    }


@router.get("/reports/recommendations")
def recommendations_report():
    """Top recommendations from all agents."""
    ctx = _build_context()
    insights = run_all_agents(ctx)
    high_priority = [i for i in insights if i.priority in ("critical", "high")]
    return {
        "total_recommendations": len(insights),
        "high_priority": len(high_priority),
        "top_5": [
            {"agent": i.agent, "title": i.title, "priority": i.priority, "action": i.action}
            for i in insights[:5]
        ],
    }
