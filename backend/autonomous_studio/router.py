"""Autonomous Studio API Router."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException

from backend.autonomous_studio.orchestrator import (
    generate_daily_briefing,
    get_all_recommendations,
    department_discussion,
    run_all_departments,
    record_decision,
    get_memory_stats,
    build_studio_context,
)
from backend.autonomous_studio.departments import ALL_DEPARTMENTS

router = APIRouter(prefix="/api/v1/studio", tags=["autonomous-studio"])


@router.get("/briefing")
def daily_briefing():
    """Daily Briefing — complete studio status with AI recommendations.

    Returns production status, publishing status, campaign health,
    analytics summary, top recommendations, department health, and alerts.
    """
    return generate_daily_briefing()


@router.get("/recommendations")
def studio_recommendations():
    """Get all current AI recommendations from all departments."""
    recs = get_all_recommendations()
    return [
        {
            "department": r.department,
            "title": r.title,
            "description": r.description,
            "reasoning": r.reasoning,
            "confidence": r.confidence,
            "priority": r.priority,
            "action": r.action,
            "expected_benefit": r.expected_benefit,
            "potential_risks": r.potential_risks,
            "status": r.status,
        }
        for r in recs
    ]


@router.post("/recommendations/{rec_index}/decide")
def decide_recommendation(rec_index: int, data: dict):
    """Approve, reject, or modify a recommendation.

    Body: {"decision": "approved|rejected|modified", "notes": "optional"}
    """
    decision = data.get("decision")
    if decision not in ("approved", "rejected", "modified"):
        raise HTTPException(status_code=400, detail="decision must be approved/rejected/modified")
    record_decision(str(rec_index), decision, data.get("notes", ""))
    return {"recorded": True, "decision": decision}


@router.get("/departments")
def list_departments():
    """List all AI departments with their roles."""
    return [
        {"name": d().name, "role": d().role}
        for d in ALL_DEPARTMENTS
    ]


@router.get("/departments/{dept_name}/analyze")
def department_analyze(dept_name: str):
    """Run a specific department's analysis."""
    ctx = build_studio_context()
    for dept_class in ALL_DEPARTMENTS:
        dept = dept_class()
        if dept.name.lower().replace(" ", "_") == dept_name.lower().replace(" ", "_"):
            output = dept.analyze(ctx)
            return {
                "department": output.department,
                "health": output.health,
                "summary": output.summary,
                "recommendations": [
                    {"title": r.title, "description": r.description, "confidence": r.confidence, "priority": r.priority}
                    for r in output.recommendations
                ],
            }
    raise HTTPException(status_code=404, detail=f"Department '{dept_name}' not found")


@router.post("/discuss")
def discuss_topic(data: dict):
    """Multi-agent discussion on a topic.

    All departments contribute their perspective sequentially.
    Body: {"topic": "luxury travel campaign for Melissa"}
    """
    topic = data.get("topic")
    if not topic:
        raise HTTPException(status_code=400, detail="'topic' required")
    discussion = department_discussion(topic)
    return {"topic": topic, "contributions": discussion, "departments_involved": len(discussion)}


@router.get("/memory")
def studio_memory():
    """Get studio learning memory — recommendation tracking stats."""
    return get_memory_stats()


@router.get("/health")
def studio_health():
    """Overall autonomous studio health."""
    ctx = build_studio_context()
    outputs = run_all_departments(ctx)
    critical = sum(1 for o in outputs if o.health == "critical")
    warning = sum(1 for o in outputs if o.health == "warning")
    return {
        "status": "critical" if critical > 0 else "warning" if warning > 0 else "healthy",
        "departments_total": len(ALL_DEPARTMENTS),
        "departments_healthy": len(outputs) - critical - warning,
        "departments_warning": warning,
        "departments_critical": critical,
        "workers_online": ctx.get("workers_online", 0),
        "recommendations_pending": len(get_all_recommendations(ctx)),
    }
