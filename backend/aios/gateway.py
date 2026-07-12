"""AIOS Intelligence Gateway — the single entry point into AI Studio intelligence.

All intelligent operations route through here:
- Conversational chat (streaming support)
- Plan creation from natural language
- Tool invocation with governance
- Session management
- Decision traceability

Existing /api/v1/brain/* endpoints remain operational.
This gateway wraps them with enhanced context, logging, and provider routing.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException

from backend.aios.provider_router import route_request, RoutingContext
from backend.aios.sessions import (
    create_session,
    get_session,
    add_message,
    list_sessions,
)
from backend.aios.decisions import log_decision

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aios/v1", tags=["aios"])


# =============================================================================
# Chat — primary conversational interface
# =============================================================================


@router.post("/chat")
async def aios_chat(data: dict):
    """Talk to the AI Brain through the Intelligence Gateway.

    Enhanced over /brain/chat:
    - Dynamic provider routing (picks best LLM per request)
    - Session persistence (Supabase, survives restarts)
    - Decision logging (every response audited)
    - Memory retrieval (RAG context injection)
    - Fallback chain (Ollama → OpenAI → Anthropic)

    Body:
        message: str — user message
        session_id: str (optional — creates new if blank)
        mode: str (optional — creative, prompt_engineer, script_writer, etc.)
        talent_id: str (optional — inject Talent DNA context)
        project_id: str (optional — inject Project DNA context)
    """
    message = data.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="'message' required")

    mode = data.get("mode", "creative")
    session_id = data.get("session_id")
    talent_id = data.get("talent_id")
    project_id = data.get("project_id")

    # Get or create session
    if not session_id:
        session = create_session(mode=mode, talent_id=talent_id, project_id=project_id)
        session_id = session["id"]
    else:
        session = get_session(session_id)
        if not session:
            session = create_session(mode=mode, talent_id=talent_id, project_id=project_id)
            session_id = session["id"]

    # Record user message
    add_message(session_id, "user", message)

    # Build conversation context
    messages = _build_context(session_id, mode, talent_id)

    # Route to best provider
    start = time.time()
    routing_ctx = RoutingContext(
        mode=mode,
        message_length=len(message),
        session_message_count=len(messages),
        has_talent_context=talent_id is not None,
    )

    try:
        response_text, provider_used, model_used = route_request(messages, routing_ctx)
    except Exception as e:
        logger.error(f"AIOS chat failed: {e}")
        raise HTTPException(status_code=503, detail=f"All providers failed: {str(e)[:200]}")

    elapsed = time.time() - start

    # Record assistant message
    add_message(session_id, "assistant", response_text)

    # Log decision
    log_decision(
        session_id=session_id,
        decision_type="chat",
        provider=provider_used,
        model=model_used,
        input_summary=message[:200],
        output_summary=response_text[:200],
        latency_ms=int(elapsed * 1000),
        mode=mode,
    )

    return {
        "session_id": session_id,
        "response": response_text,
        "provider": provider_used,
        "model": model_used,
        "latency_ms": int(elapsed * 1000),
        "mode": mode,
    }


# =============================================================================
# Plan — create execution plan from intent
# =============================================================================


@router.post("/plan")
async def aios_plan(data: dict):
    """Create an execution plan from natural language intent.

    Uses LLM to decompose a request into actionable steps.

    Body:
        request: str — what the user wants to do
        talent_id: str (optional)
        project_id: str (optional)
    """
    request_text = data.get("request")
    if not request_text:
        raise HTTPException(status_code=400, detail="'request' required")

    # Use the Brain planner (enhanced with provider routing)
    from backend.brain.planner import create_plan

    plan = create_plan(request_text, context=data)

    return {
        "id": plan.id,
        "request": plan.request,
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "module": t.module,
                "action": t.action,
                "depends_on": t.depends_on,
                "estimated_seconds": t.estimated_seconds,
            }
            for t in plan.tasks
        ],
        "reasoning": plan.reasoning,
        "estimated_seconds": plan.estimated_total_seconds,
        "modules_involved": plan.modules_involved,
        "confidence": plan.confidence,
    }


# =============================================================================
# Health
# =============================================================================


@router.get("/health")
def aios_health():
    """Intelligence Gateway health — providers, sessions, decisions."""
    from backend.brain.llm_provider import get_brain_health

    brain_health = get_brain_health()

    return {
        "gateway": "operational",
        "brain": brain_health,
        "version": "1.0.0",
        "timestamp": time.time(),
    }


# =============================================================================
# Sessions
# =============================================================================


@router.get("/sessions")
def aios_list_sessions(limit: int = 20):
    """List recent AIOS sessions."""
    return list_sessions(limit=limit)


@router.get("/sessions/{session_id}")
def aios_get_session(session_id: str):
    """Get a specific session with messages."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# =============================================================================
# Decisions (audit trail)
# =============================================================================


@router.get("/decisions")
def aios_list_decisions(session_id: str | None = None, limit: int = 50):
    """List recent AI decisions for audit."""
    from backend.aios.decisions import list_decisions

    return list_decisions(session_id=session_id, limit=limit)


# =============================================================================
# Council — Agent orchestration endpoint
# =============================================================================


@router.post("/council")
async def aios_council(data: dict):
    """Run the Agent Council on a request.

    This is the multi-agent orchestration endpoint.
    Èṣù routes, Òrúnmìlà plans, results assembled.

    Body:
        message: str — what the user wants
        talent_id: str (optional)
        project_id: str (optional)
        mode: str (optional)

    Returns:
        decisions: list of agent decisions with reasoning
        proposed_actions: actions that need approval or can be auto-executed
        routing: how Èṣù routed the request
        summary: unified plain-language summary
    """
    from backend.aios.council.base import AIOSContext
    from backend.aios.council.orchestrator import run_council

    message = data.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="'message' required")

    # Build context
    context = AIOSContext(
        user_message=message,
        mode=data.get("mode", "creative"),
        talent_id=data.get("talent_id"),
        project_id=data.get("project_id"),
    )

    # Load talent DNA if provided
    if context.talent_id:
        try:
            from backend.database import supabase

            talent = supabase.table("talent").select("name,visual_style,best_for,persona").eq("id", context.talent_id).single().execute().data
            if talent:
                context.talent_name = talent.get("name", "")
                context.talent_dna = talent
        except Exception:
            pass

    # Check GPU worker status
    try:
        from backend.infrastructure.worker_orchestrator import get_orchestrator

        o = get_orchestrator()
        context.gpu_worker_active = o.session is not None and o.session.instance_id is not None
    except Exception:
        pass

    # Run the council
    result = await run_council(context)

    return result


@router.get("/council/agents")
def aios_list_agents():
    """List all registered council agents and their capabilities."""
    from backend.aios.council.orchestrator import get_all_agents

    agents = get_all_agents()
    return [
        {
            "name": a.name,
            "display_name": a.display_name,
            "domain": a.domain,
            "authority": a.authority.value,
            "capabilities": [
                {"name": c.name, "description": c.description, "authority_required": c.authority_required.value}
                for c in a.capabilities()
            ],
        }
        for a in agents
    ]


# =============================================================================
# Approvals — governance queue
# =============================================================================


@router.get("/approvals")
def aios_list_approvals(session_id: str | None = None):
    """List pending actions awaiting human approval."""
    from backend.aios.governance.queue import get_pending_approvals

    return get_pending_approvals(session_id=session_id)


@router.get("/approvals/count")
def aios_approval_count():
    """Get count of pending approvals (for UI badge)."""
    from backend.aios.governance.queue import count_pending

    return {"pending": count_pending()}


@router.post("/approvals/{approval_id}/approve")
def aios_approve(approval_id: str):
    """Approve a pending action — it will be executed."""
    from backend.aios.governance.queue import approve_action
    from backend.aios.decisions import log_decision

    result = approve_action(approval_id)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found")

    log_decision(
        session_id=result.get("session_id", ""),
        decision_type="approval",
        provider="human",
        model="human",
        input_summary=f"Approved: {result.get('tool', '')}",
        output_summary="Action approved by user",
    )

    return {"status": "approved", "approval": result}


@router.post("/approvals/{approval_id}/reject")
def aios_reject(approval_id: str, data: dict = None):
    """Reject a pending action — it will be discarded."""
    from backend.aios.governance.queue import reject_action
    from backend.aios.decisions import log_decision

    reason = (data or {}).get("reason", "")
    result = reject_action(approval_id, reason=reason)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found")

    log_decision(
        session_id=result.get("session_id", ""),
        decision_type="rejection",
        provider="human",
        model="human",
        input_summary=f"Rejected: {result.get('tool', '')}",
        output_summary=f"Reason: {reason}" if reason else "Rejected without reason",
    )

    return {"status": "rejected", "approval": result}


# =============================================================================
# Governance Policies
# =============================================================================


@router.get("/governance/policies")
def aios_get_policies():
    """Get current governance policies."""
    from backend.aios.governance.policies import get_policies

    return get_policies()


@router.put("/governance/policies")
def aios_update_policies(data: dict):
    """Update governance policies.

    Body: any combination of:
        auto_approve_generation: bool
        auto_approve_training: bool
        auto_approve_gpu_launch: bool
        require_publish_approval: bool
        require_delete_approval: bool
        max_auto_spend_usd: float
        budget_daily_usd: float
        budget_monthly_usd: float
    """
    from backend.aios.governance.policies import get_policies, save_policies

    current = get_policies()
    updated = {**current, **data}
    save_policies(updated)
    return {"status": "updated", "policies": updated}


# =============================================================================
# Knowledge Graph
# =============================================================================


@router.get("/knowledge/search")
def aios_knowledge_search(q: str, sources: str | None = None, talent_id: str | None = None, limit: int = 20):
    """Search across all knowledge systems.

    Query params:
        q: search query (natural language or keywords)
        sources: comma-separated filter (talent,creative_dna,object_dna,model,generation,workflow_dna,story)
        talent_id: scope to a specific talent
        limit: max results (default 20)
    """
    from backend.aios.knowledge.graph import KnowledgeQuery, search

    source_list = [s.strip() for s in sources.split(",")] if sources else []

    query = KnowledgeQuery(
        query=q,
        sources=source_list,
        talent_id=talent_id,
        limit=limit,
    )

    results = search(query)
    return {
        "query": q,
        "results": [
            {
                "source": r.source,
                "entity_id": r.entity_id,
                "name": r.name,
                "relevance": r.relevance,
                "summary": r.summary,
                "data": r.data,
            }
            for r in results
        ],
        "total": len(results),
    }


@router.get("/knowledge/talent/{talent_id}")
def aios_talent_knowledge(talent_id: str):
    """Get all knowledge about a specific talent.

    Returns: profile, creative DNA, relationships, LoRAs, voices, recent generations.
    """
    from backend.aios.knowledge.graph import get_talent_knowledge

    return get_talent_knowledge(talent_id)


@router.get("/knowledge/workflow-dna")
def aios_workflow_recommendations(content_type: str = "image", talent_id: str | None = None, limit: int = 3):
    """Get recommended workflow configs based on past success."""
    from backend.aios.knowledge.workflow_dna import recommend_workflow

    return recommend_workflow(content_type=content_type, talent_id=talent_id, limit=limit)


@router.post("/knowledge/workflow-dna/capture")
def aios_capture_workflow(data: dict):
    """Capture a successful generation config as Workflow DNA.

    Body:
        config: dict — the full generation config (model, steps, cfg, prompt, etc.)
        rating: int — user rating (1-5, only 4+ gets captured)
        talent_id: str (optional)
        content_type: str (default: image)
    """
    from backend.aios.knowledge.workflow_dna import capture_workflow

    config = data.get("config", {})
    rating = int(data.get("rating", 0))
    talent_id = data.get("talent_id")
    content_type = data.get("content_type", "image")

    if rating < 4:
        return {"captured": False, "reason": "Only configs rated 4+ are captured as Workflow DNA"}

    result = capture_workflow(config, rating, talent_id, content_type)
    return {"captured": bool(result), "recipe": result}


@router.get("/knowledge/workflow-dna/stats")
def aios_workflow_stats():
    """Get Workflow DNA aggregate statistics."""
    from backend.aios.knowledge.workflow_dna import get_workflow_stats

    return get_workflow_stats()


# =============================================================================
# Helpers
# =============================================================================


def _build_context(session_id: str, mode: str, talent_id: str | None) -> list[dict]:
    """Build the full message context for LLM call.

    Uses the enhanced memory retrieval pipeline to inject:
    - System prompt + mode personality
    - Talent DNA + relationships
    - Workflow DNA recommendations
    - RAG (relevant past conversations)
    - Project context
    - Session history
    """
    from backend.brain.llm_provider import get_system_prompt

    messages = []

    # System prompt based on mode
    system = get_system_prompt(mode)

    # Enhanced context injection via knowledge memory pipeline
    try:
        from backend.aios.knowledge.memory import retrieve_context

        session = get_session(session_id)
        last_user_msg = ""
        if session and session.get("messages"):
            user_msgs = [m for m in session["messages"] if m.get("role") == "user"]
            if user_msgs:
                last_user_msg = user_msgs[-1].get("content", "")

        extra_context = retrieve_context(
            query=last_user_msg,
            talent_id=talent_id,
            session_id=session_id,
            mode=mode,
        )
        if extra_context:
            system += f"\n\n{extra_context}"
    except Exception:
        pass

    messages.append({"role": "system", "content": system})

    # Session message history (last 20 messages)
    session = get_session(session_id)
    if session and session.get("messages"):
        for msg in session["messages"][-20:]:
            role = msg.get("role", "user")
            if role == "brain":
                role = "assistant"
            messages.append({"role": role, "content": msg.get("content", "")})

    return messages
