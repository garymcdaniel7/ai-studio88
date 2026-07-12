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
    Esu routes, Orunmila plans, results assembled.

    Body:
        message: str — what the user wants
        talent_id: str (optional)
        project_id: str (optional)
        mode: str (optional)

    Returns:
        decisions: list of agent decisions with reasoning
        proposed_actions: actions that need approval or can be auto-executed
        routing: how Esu routed the request
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
# Session Orchestration — multi-worker management
# =============================================================================


@router.post("/session/plan")
def aios_plan_session(data: dict):
    """Plan a work session — determines what GPU resources are needed.

    Call this before heavy work to get cost estimates and resource requirements.

    Body:
        session_type: str — image, video, training, mixed, chat_only, auto
        tasks: list[str] — planned tasks (generate_image, train_lora, etc.)
        talent_id: str (optional) — checks what LoRAs need loading
    """
    from backend.aios.orchestration.session_planner import plan_session

    plan = plan_session(
        session_type=data.get("session_type", "auto"),
        tasks=data.get("tasks"),
        talent_id=data.get("talent_id"),
    )

    return {
        "session_type": plan.session_type.value,
        "models_needed": plan.models_needed,
        "min_vram_gb": plan.min_vram_gb,
        "preferred_provider": plan.preferred_provider,
        "estimated_duration_minutes": plan.estimated_duration_minutes,
        "estimated_cost_usd": round(plan.estimated_cost_usd, 4),
        "auto_release_idle_minutes": plan.auto_release_idle_minutes,
        "reasoning": plan.reasoning,
    }


@router.post("/session/should-release")
def aios_should_release(data: dict):
    """Check if the current GPU worker should be released.

    Body:
        idle_minutes: float — how long the worker has been idle
        session_type: str — current session type
        pending_jobs: int — jobs still in queue
    """
    from backend.aios.orchestration.session_planner import SessionPlan, SessionType, should_release_worker

    plan = SessionPlan(
        session_type=SessionType(data.get("session_type", "image")),
        auto_release_idle_minutes=int(data.get("auto_release_minutes", 10)),
    )

    release, reason = should_release_worker(
        idle_minutes=float(data.get("idle_minutes", 0)),
        session_plan=plan,
        pending_jobs=int(data.get("pending_jobs", 0)),
    )

    return {"should_release": release, "reason": reason}


@router.post("/session/model-swap")
def aios_model_swap(data: dict):
    """Recommend whether to load, swap, or skip a model change.

    Body:
        current_models: list[str] — models currently in VRAM
        needed_model: str — model needed for next task
        vram_total_gb: float — total VRAM on worker
        vram_used_gb: float — VRAM currently in use
    """
    from backend.aios.orchestration.session_planner import recommend_model_swap

    result = recommend_model_swap(
        current_models=data.get("current_models", []),
        needed_model=data.get("needed_model", ""),
        vram_total_gb=float(data.get("vram_total_gb", 24)),
        vram_used_gb=float(data.get("vram_used_gb", 0)),
    )

    return result


# =============================================================================
# Workflow Intelligence — auto-configuration
# =============================================================================


@router.post("/workflow/configure")
def aios_auto_configure(data: dict):
    """Auto-configure optimal generation parameters.

    Given a prompt and context, returns the best model, LoRAs, steps,
    CFG, resolution, and negative prompt — ready to submit.

    Body:
        prompt: str — what to generate
        talent_id: str (optional) — inject DNA + LoRAs
        content_type: str — image or video (default: image)
        quality: str — draft, standard, high, auto (default: auto)
        platform: str (optional) — instagram, tiktok, youtube (affects resolution)
        budget_max_usd: float (optional) — max spend allowed
    """
    from backend.aios.workflow.intelligence import auto_configure

    prompt = data.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="'prompt' required")

    config = auto_configure(
        prompt=prompt,
        talent_id=data.get("talent_id"),
        content_type=data.get("content_type", "image"),
        quality=data.get("quality", "auto"),
        platform=data.get("platform"),
        budget_max_usd=data.get("budget_max_usd"),
    )

    return {
        "model": config.model,
        "prompt": config.prompt,
        "negative_prompt": config.negative_prompt,
        "width": config.width,
        "height": config.height,
        "steps": config.steps,
        "cfg": config.cfg,
        "sampler": config.sampler,
        "scheduler": config.scheduler,
        "seed": config.seed,
        "loras": config.loras,
        "estimated_cost_usd": config.estimated_cost_usd,
        "estimated_time_seconds": config.estimated_time_seconds,
        "quality_tier": config.quality_tier,
        "reasoning": config.reasoning,
    }


# =============================================================================
# Obaluaye — Reliability & Diagnostics
# =============================================================================


@router.get("/health/full")
def aios_full_health():
    """Full platform health report from Obaluaye.

    Checks all services, applies circuit breaker logic,
    generates alerts for DOWN services.
    """
    from backend.aios.obaluaye.monitor import get_monitor

    monitor = get_monitor()
    report = monitor.check_all()

    return {
        "overall": report.overall_status.value,
        "services": {
            name: {
                "status": svc.status.value,
                "response_time_ms": svc.response_time_ms,
                "consecutive_failures": svc.consecutive_failures,
                "error": svc.error,
                "last_success": svc.last_success,
            }
            for name, svc in report.services.items()
        },
        "alerts": report.alerts,
        "metrics": report.metrics,
        "timestamp": report.timestamp,
    }


@router.get("/health/alerts")
def aios_alerts():
    """Get current active alerts."""
    from backend.aios.obaluaye.monitor import get_monitor

    monitor = get_monitor()
    report = monitor.get_last_report()
    if not report:
        report = monitor.check_all()
    return {"alerts": report.alerts, "count": len(report.alerts)}


@router.post("/health/check-stuck-jobs")
def aios_check_stuck_jobs():
    """Check for stuck jobs and attempt recovery."""
    from backend.aios.obaluaye.recovery import get_recovery_engine

    engine = get_recovery_engine()
    actions = engine.check_stuck_jobs()
    budget_alerts = engine.check_budget_alerts()
    return {
        "stuck_job_actions": [{"service": a.service, "action": a.action, "reason": a.reason} for a in actions],
        "budget_alerts": [{"service": a.service, "action": a.action, "reason": a.reason} for a in budget_alerts],
    }


@router.get("/health/recovery-log")
def aios_recovery_log(limit: int = 20):
    """Get recent recovery actions taken by Obaluaye."""
    from backend.aios.obaluaye.recovery import get_recovery_engine

    engine = get_recovery_engine()
    return {"actions": engine.get_recent_actions(limit=limit)}


@router.post("/health/diagnose")
async def aios_diagnose(data: dict):
    """Diagnose a service failure using LLM + rules.

    Body:
        service: str — which service failed (comfyui, ollama, worker_api, etc.)
        error: str — the error message
    """
    from backend.aios.obaluaye.diagnostics import diagnose_failure

    service = data.get("service", "")
    error = data.get("error", "")
    if not service:
        raise HTTPException(status_code=400, detail="'service' required")

    result = await diagnose_failure(service, error, context=data)
    return result


@router.post("/health/auto-fix")
async def aios_auto_fix(data: dict):
    """Attempt to automatically fix a service issue.

    Body:
        fix_action: str — the action to execute (start_comfyui, start_worker_api, etc.)
        service: str — which service this is for
    """
    from backend.aios.obaluaye.diagnostics import attempt_auto_fix

    fix_action = data.get("fix_action")
    service = data.get("service", "")
    if not fix_action:
        raise HTTPException(status_code=400, detail="'fix_action' required")

    result = await attempt_auto_fix(fix_action, service)

    # Log the fix attempt
    from backend.aios.decisions import log_decision
    log_decision(
        session_id="ise-auto-fix",
        decision_type="auto_fix",
        provider="ise",
        model=fix_action,
        input_summary=f"Auto-fix: {service} — {fix_action}",
        output_summary=result.get("message", "")[:200],
    )

    return result


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
