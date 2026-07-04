"""AI Brain API Router — the primary conversational interface.

One endpoint to rule them all: POST /brain/chat
The Brain understands, plans, delegates, and responds.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException

from backend.brain.registry import list_modules, find_modules_for_intent, MODULES
from backend.brain.planner import create_plan, ExecutionPlan
from backend.brain.memory import (
    create_session, get_session, add_message, get_conversation_history,
    get_production_memory, update_production_memory, list_sessions,
)

router = APIRouter(prefix="/api/v1/brain", tags=["brain"])


# =============================================================================
# Chat — the primary interface
# =============================================================================

@router.post("/chat")
def brain_chat(data: dict):
    """Talk to the AI Brain.

    The primary interface to AI Studio. Send natural language and receive
    a production plan with reasoning.

    Body: {"message": "Create Melissa in Dubai", "session_id": "optional"}
    """
    message = data.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="'message' required")

    session_id = data.get("session_id")
    if not session_id:
        session = create_session()
        session_id = session.id

    # Record user message
    add_message(session_id, "user", message)

    # Build context from conversation history
    history = get_conversation_history(session_id, limit=10)
    memory = get_production_memory()
    context = {
        "history": history,
        "memory": memory,
        "talent_preference": data.get("talent_id"),
        "project_preference": data.get("project_id"),
    }

    # Create execution plan
    plan = create_plan(message, context)

    # Generate brain response
    response = _build_response(plan, message)

    # Record brain response
    add_message(session_id, "brain", response["summary"], plan_id=plan.id)

    return {
        "session_id": session_id,
        "response": response["summary"],
        "plan": {
            "id": plan.id,
            "tasks": [
                {"id": t.id, "name": t.name, "module": t.module, "action": t.action,
                 "depends_on": t.depends_on, "estimated_seconds": t.estimated_seconds}
                for t in plan.tasks
            ],
            "reasoning": plan.reasoning,
            "estimated_seconds": plan.estimated_total_seconds,
            "estimated_cost": plan.estimated_cost,
            "confidence": plan.confidence,
            "modules_involved": plan.modules_involved,
        },
        "recommendations": _build_recommendations(plan),
    }


def _build_response(plan: ExecutionPlan, request: str) -> dict:
    """Build a natural language response from the plan."""
    task_names = [t.name for t in plan.tasks]
    modules = plan.modules_involved

    summary = (
        f"I'll handle this with {len(plan.tasks)} steps across {len(modules)} modules "
        f"({', '.join(modules)}). "
        f"Estimated time: ~{plan.estimated_total_seconds}s. "
        f"Plan: {' → '.join(task_names[:5])}."
    )

    return {"summary": summary}


def _build_recommendations(plan: ExecutionPlan) -> list[dict]:
    """Build contextual recommendations based on the plan."""
    recs = []

    if "Generation Engine" in plan.modules_involved:
        recs.append({
            "type": "model",
            "title": "Recommended: FLUX.1-dev",
            "reason": "Best photorealism for editorial content",
        })

    if "Video Studio" in plan.modules_involved:
        recs.append({
            "type": "video",
            "title": "Use 9:16 vertical for social",
            "reason": "Instagram/TikTok optimized format",
        })

    if "Publishing Engine" in plan.modules_involved:
        recs.append({
            "type": "publishing",
            "title": "Best time: Tuesday 7-9pm",
            "reason": "Historical engagement peak",
        })

    return recs


# =============================================================================
# Plan
# =============================================================================

@router.post("/plan")
def brain_plan(data: dict):
    """Create a production plan without chatting.

    Body: {"request": "Create a luxury travel reel"}
    """
    request = data.get("request")
    if not request:
        raise HTTPException(status_code=400, detail="'request' required")

    plan = create_plan(request)
    return {
        "id": plan.id,
        "request": plan.request,
        "tasks": [
            {"id": t.id, "name": t.name, "module": t.module, "action": t.action,
             "status": t.status, "estimated_seconds": t.estimated_seconds}
            for t in plan.tasks
        ],
        "reasoning": plan.reasoning,
        "estimated_total_seconds": plan.estimated_total_seconds,
        "estimated_cost": plan.estimated_cost,
        "confidence": plan.confidence,
        "modules_involved": plan.modules_involved,
    }


# =============================================================================
# Sessions
# =============================================================================

@router.get("/sessions")
def brain_sessions():
    """List all brain sessions."""
    return list_sessions()


@router.get("/sessions/{session_id}")
def brain_session_detail(session_id: str):
    """Get a session with conversation history."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": session.id,
        "messages": get_conversation_history(session_id),
        "created_at": session.created_at,
    }


# =============================================================================
# Context & Memory
# =============================================================================

@router.get("/context")
def brain_context():
    """Get the Brain's current context (what it knows about)."""
    return {
        "modules": list_modules(),
        "memory": get_production_memory(),
        "active_sessions": len(list_sessions()),
    }


@router.get("/memory")
def brain_memory():
    """Get production memory (learned preferences)."""
    return get_production_memory()


@router.put("/memory")
def update_memory(data: dict):
    """Update production memory."""
    for key, value in data.items():
        update_production_memory(key, value)
    return {"updated": True, "memory": get_production_memory()}


# =============================================================================
# Modules
# =============================================================================

@router.get("/modules")
def brain_modules():
    """List all modules registered with the Brain."""
    return list_modules()


# =============================================================================
# Reasoning
# =============================================================================

@router.get("/reasoning/{plan_id}")
def get_reasoning(plan_id: str):
    """Get reasoning for a specific plan (why these steps were chosen)."""
    # In a real implementation, reasoning would be stored per-plan
    return {
        "plan_id": plan_id,
        "reasoning": "Plan created based on intent analysis, module capabilities, and production memory.",
        "factors": [
            "User request keywords",
            "Available modules and their capabilities",
            "Production memory preferences",
            "Conversation history context",
        ],
    }


# =============================================================================
# LLM Chat (Ollama / OpenAI / Anthropic)
# =============================================================================

@router.get("/health")
def brain_health():
    """Check the AI Brain's LLM provider status."""
    from backend.brain.llm_provider import get_brain_health
    return get_brain_health()


@router.post("/llm/chat")
def brain_llm_chat(data: dict):
    """Chat directly with the LLM provider (Ollama/OpenAI/Anthropic).

    Body: {"messages": [{"role": "user", "content": "..."}], "mode": "creative"}
    Optional: "model" to override default, "mode" for specialized personality
    Modes: creative, prompt_engineer, story_assistant, production_advisor, research, image_analyzer
    """
    from backend.brain.llm_provider import chat, LLMProviderError

    messages = data.get("messages", [])
    if not messages:
        msg = data.get("message", "")
        if not msg:
            raise HTTPException(status_code=400, detail="'messages' or 'message' required")
        messages = [{"role": "user", "content": msg}]

    model = data.get("model")
    mode = data.get("mode", "creative")

    try:
        response = chat(messages, model=model, mode=mode)
        return {"response": response, "model": model or "default", "mode": mode}
    except LLMProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
