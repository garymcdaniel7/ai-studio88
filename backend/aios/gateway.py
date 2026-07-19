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
    images = data.get("images")  # Base64 images for vision analysis
    routing_ctx = RoutingContext(
        mode=mode,
        message_length=len(message),
        session_message_count=len(messages),
        has_talent_context=talent_id is not None,
    )

    # ─── INTENT DETECTION: Does the user want to GENERATE something? ─────
    # If yes, actually generate it instead of just describing it.
    generation_result = None
    gen_keywords = ["generate", "create an image", "make an image", "create a photo",
                    "generate a photo", "draw", "make a picture", "create a picture",
                    "generate an image", "show me", "visualize", "render"]
    msg_lower = message.lower()
    wants_generation = any(kw in msg_lower for kw in gen_keywords)

    if wants_generation:
        try:
            import httpx
            # Extract the visual concept from the message as the prompt
            gen_prompt = message  # Use the full message as the generation prompt
            gen_resp = httpx.post(
                "http://localhost:8000/api/v1/generate/image",
                json={"prompt": gen_prompt, "model": "sdxl-turbo", "width": 512, "height": 512},
                timeout=120,
            )
            if gen_resp.status_code == 200:
                gen_data = gen_resp.json()
                if gen_data.get("success") and gen_data.get("image_base64"):
                    generation_result = {
                        "image_base64": gen_data["image_base64"],
                        "filename": gen_data.get("filename"),
                        "generation_time": gen_data.get("generation_time"),
                        "model": gen_data.get("model"),
                        "prompt": gen_prompt,
                    }
        except Exception as e:
            logger.warning(f"Auto-generation failed: {e}")
    # ─────────────────────────────────────────────────────────────────────

    try:
        # If images are attached, use direct chat() with vision model support
        if images:
            from backend.brain.llm_provider import chat as brain_chat
            response_text = brain_chat(messages, mode=mode, images=images)
            provider_used = "ollama"
            model_used = "llava:7b"
        else:
            response_text, provider_used, model_used = route_request(messages, routing_ctx)
    except Exception as e:
        logger.error(f"AIOS chat failed: {e}")
        raise HTTPException(status_code=503, detail=f"All providers failed: {str(e)[:200]}")

    elapsed = time.time() - start

    # Check if the message implies an action (run council for action detection)
    proposed_actions = []
    governance_result = {}
    try:
        from backend.aios.council.base import AIOSContext
        from backend.aios.council.orchestrator import run_council
        import asyncio

        ctx = AIOSContext(
            user_message=message,
            mode=mode,
            session_id=session_id,
            talent_id=talent_id,
            project_id=project_id,
        )

        # Run council (non-blocking check for action intent)
        council_result = asyncio.get_event_loop().run_until_complete(run_council(ctx))
        proposed_actions = council_result.get("proposed_actions", [])
        governance_result = council_result.get("governance", {})
    except Exception:
        pass  # Council failure shouldn't block chat response

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

    # If generation happened, prepend a note to the response
    if generation_result:
        response_text = f"Here's your image! Generated in {generation_result.get('generation_time', '?')}s using {generation_result.get('model', 'SDXL Turbo')}.\n\n{response_text}"

    return {
        "session_id": session_id,
        "response": response_text,
        "provider": provider_used,
        "model": model_used,
        "latency_ms": int(elapsed * 1000),
        "mode": mode,
        "actions": proposed_actions,
        "governance": governance_result,
        "generation": generation_result,
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
async def aios_approve(approval_id: str):
    """Approve a pending action — it will be executed immediately."""
    from backend.aios.governance.queue import approve_action
    from backend.aios.decisions import log_decision
    from backend.aios.execution.tools import execute_tool

    result = approve_action(approval_id)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found")

    # Execute the approved action
    tool = result.get("tool", "")
    parameters = result.get("parameters", {})
    execution_result = {}

    if tool and parameters:
        execution_result = await execute_tool(tool, parameters)

    log_decision(
        session_id=result.get("session_id", ""),
        decision_type="approval_executed",
        provider="human",
        model=tool,
        input_summary=f"Approved + Executed: {tool}",
        output_summary=str(execution_result)[:200],
    )

    return {"status": "approved_and_executed", "approval": result, "execution": execution_result}


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
# Hermes Agent — Nous Research self-improving agent
# =============================================================================


@router.post("/hermes/chat")
async def aios_hermes_chat(data: dict):
    """Chat with Hermes — the primary Brain interface (Option C).

    Hermes handles: conversation, memory, learning, skill creation.
    AI Studio tools available: generate, train, search, diagnose, etc.

    Body:
        message: str — what to say
        mode: str (optional) — brain mode (creative, prompt_engineer, etc.)
        model: str (optional) — override LLM model
        skip_memory: bool (default false) — disable memory for this call
        images: list[str] (optional) — base64 images for vision
    """
    from backend.aios.hermes.agent import hermes_chat, AIOS_HERMES_PROMPT
    from backend.brain.llm_provider import get_system_prompt

    message = data.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="'message' required")

    # Build mode-aware system prompt
    mode = data.get("mode", "creative")
    mode_prompt = get_system_prompt(mode)
    full_prompt = AIOS_HERMES_PROMPT + f"\n\nCURRENT MODE: {mode}\n{mode_prompt}"

    # For images, prepend context
    images = data.get("images")
    if images:
        message = f"[User attached an image for analysis]\n\n{message}"

    response = hermes_chat(
        message=message,
        model=data.get("model"),
        skip_memory=data.get("skip_memory", False),
    )

    return {
        "response": response,
        "agent": "hermes",
        "mode": mode,
        "memory_enabled": not data.get("skip_memory", False),
        "provider": "hermes",
    }


@router.post("/hermes/task")
async def aios_hermes_task(data: dict):
    """Run a complex multi-step task through Hermes.

    Hermes will use its tools (web search, file ops, etc.) to complete the task.
    More powerful than /chat — supports multi-turn tool calling.

    Body:
        message: str — the task description
        system_prompt: str (optional) — custom instructions
        model: str (optional)
        toolsets: list[str] (optional) — which tools to enable
    """
    from backend.aios.hermes.agent import hermes_task

    message = data.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="'message' required")

    result = hermes_task(
        message=message,
        system_prompt=data.get("system_prompt"),
        model=data.get("model"),
        enabled_toolsets=data.get("toolsets"),
    )

    return result


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
    """Check if the current GPU worker should be released."""
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


@router.post("/session/autoscale")
def aios_autoscale(data: dict):
    """Evaluate if the GPU fleet needs to scale up/down.

    Body:
        pending_tasks: list — tasks waiting [{type: "generate_image_flux"}, ...]
        budget_remaining: float (optional, default 20.0)
    """
    from backend.aios.orchestration.autoscaler import ScaleDecision, WorkerState, evaluate_scaling, get_fleet_summary

    # Build current worker state from orchestrator
    workers: list[WorkerState] = []
    try:
        from backend.infrastructure.worker_api_client import get_worker_client
        client = get_worker_client()
        if client and client.is_available():
            health = client.health()
            gpu = health.get("checks", {}).get("gpu", {})
            workers.append(WorkerState(
                id="primary",
                gpu_name=gpu.get("name", "Unknown"),
                vram_total_gb=gpu.get("vram_total_mb", 24000) / 1024,
                vram_used_gb=(gpu.get("vram_total_mb", 24000) - gpu.get("vram_free_mb", 20000)) / 1024,
                status="active",
            ))
    except Exception:
        pass

    pending = data.get("pending_tasks", [])
    budget = float(data.get("budget_remaining", 20.0))

    decisions = evaluate_scaling(workers, pending, budget)
    summary = get_fleet_summary(workers)

    return {
        "fleet": summary,
        "decisions": [
            {
                "action": d.action,
                "reason": d.reason,
                "target_gpu": d.target_gpu,
                "target_provider": d.target_provider,
                "estimated_cost_hr": d.estimated_cost_hr,
                "priority": d.priority,
                "requires_approval": d.requires_approval,
            }
            for d in decisions
        ],
    }


@router.get("/session/insights")
def aios_usage_insights():
    """Get learned usage patterns and predictions.

    Shows what the system has learned about your usage:
    - Task frequency breakdown
    - Peak hours
    - Burst mode detection
    - Predicted next action
    """
    from backend.aios.orchestration.interceptor import get_tracker

    tracker = get_tracker()
    return tracker.get_insights()


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


@router.post("/models/ensure-loaded")
async def aios_ensure_model_loaded(data: dict):
    """Ensure a model is downloaded and ready on the GPU worker.

    If not present: downloads from B2 → loads to worker.
    If already there: returns immediately.

    Body:
        model: str — model name (flux-dev, sdxl-turbo, etc.)
    """
    from backend.aios.orchestration.model_lifecycle import ensure_model_loaded

    model = data.get("model", "")
    if not model:
        raise HTTPException(status_code=400, detail="'model' required")

    result = await ensure_model_loaded(model)
    return result


@router.post("/models/unload")
async def aios_unload_model(data: dict):
    """Unload a model from GPU worker (frees VRAM, keeps in B2).

    Body:
        model: str — model name to unload
    """
    from backend.aios.orchestration.model_lifecycle import unload_model

    model = data.get("model", "")
    if not model:
        raise HTTPException(status_code=400, detail="'model' required")

    return await unload_model(model)


@router.post("/models/archive")
async def aios_archive_model(data: dict):
    """Archive a model — marks inactive, stays in B2 for future restore.

    Body:
        model_id: str — UUID of model to archive
    """
    from backend.aios.orchestration.model_lifecycle import archive_model

    model_id = data.get("model_id", "")
    if not model_id:
        raise HTTPException(status_code=400, detail="'model_id' required")

    return await archive_model(model_id)


@router.post("/models/restore")
async def aios_restore_model(data: dict):
    """Restore an archived model — sets to B2-only (downloads when needed).

    Body:
        model_id: str — UUID of model to restore
    """
    from backend.aios.orchestration.model_lifecycle import restore_model

    model_id = data.get("model_id", "")
    if not model_id:
        raise HTTPException(status_code=400, detail="'model_id' required")

    return await restore_model(model_id)


@router.get("/models/placements")
def aios_model_placements():
    """Get current model placement state — REAL data from GPU worker + registry.

    Combines:
    - Worker API /models/loaded (what's actually on the GPU disk)
    - Worker API /health (GPU VRAM usage)
    - Supabase models table (what's registered)

    Shows everything on the GPU: models, software, disk usage.
    """
    from backend.aios.orchestration.model_lifecycle import get_model_placements

    placements = get_model_placements()

    # Also get REAL worker data if available
    worker_data = {"models": {}, "disk": {}, "software": []}
    try:
        from backend.infrastructure.worker_api_client import get_worker_client
        client = get_worker_client()
        if client and client.is_available():
            # Get actual models on worker disk
            loaded = client.list_models()
            worker_data["models"] = loaded.get("models", {})

            # Get health for disk/GPU info
            health = client.health()
            checks = health.get("checks", {})
            worker_data["disk"] = checks.get("disk", {})
            worker_data["gpu"] = checks.get("gpu", {})

            # Software installed on worker
            worker_data["software"] = []
            if checks.get("comfyui", {}).get("available"):
                worker_data["software"].append({"name": "ComfyUI", "status": "running", "type": "software"})
            if checks.get("ollama", {}).get("available"):
                models = checks.get("ollama", {}).get("models", [])
                worker_data["software"].append({"name": f"Ollama ({len(models)} models)", "status": "running", "type": "llm"})
            if checks.get("ffmpeg", {}).get("available"):
                worker_data["software"].append({"name": "FFmpeg", "status": "installed", "type": "software"})
    except Exception:
        pass

    # Build the full picture: registered models + what's actually on worker
    worker_models_flat = []
    for category, models in worker_data.get("models", {}).items():
        for m in models:
            worker_models_flat.append({
                "name": m.get("name", ""),
                "size_mb": m.get("size_mb", 0),
                "category": category,
                "source": "worker_disk",
            })

    return {
        "models": [
            {
                "id": p.model_id,
                "name": p.name,
                "state": p.state.value,
                "size_mb": p.size_mb,
                "vram_mb": p.vram_mb,
                "type": p.model_type,
                "b2_path": p.b2_path,
                "worker_path": p.worker_path,
            }
            for p in placements
        ],
        "worker_models": worker_models_flat,
        "worker_software": worker_data.get("software", []),
        "worker_disk": worker_data.get("disk", {}),
        "worker_gpu": worker_data.get("gpu", {}),
        "summary": {
            "total_registered": len(placements),
            "loaded": len([p for p in placements if p.state.value == "loaded"]),
            "b2_only": len([p for p in placements if p.state.value == "b2_only"]),
            "archived": len([p for p in placements if p.state.value == "archived"]),
            "on_worker_disk": len(worker_models_flat),
            "worker_disk_used_gb": worker_data.get("disk", {}).get("total_gb", 0) - worker_data.get("disk", {}).get("free_gb", 0),
            "worker_disk_total_gb": worker_data.get("disk", {}).get("total_gb", 0),
            "gpu_vram_total_mb": worker_data.get("gpu", {}).get("vram_total_mb", 0),
            "gpu_vram_free_mb": worker_data.get("gpu", {}).get("vram_free_mb", 0),
        },
    }


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
    """Get current active alerts (includes service health + UAT failures)."""
    from backend.aios.obaluaye.monitor import get_monitor

    monitor = get_monitor()
    report = monitor.get_last_report()
    if not report:
        report = monitor.check_all()

    alerts = list(report.alerts)

    # Include UAT test failures as alerts
    try:
        from backend.aios.obaluaye.uat_runner import get_uat_alerts
        alerts.extend(get_uat_alerts())
    except Exception:
        pass

    return {"alerts": alerts, "count": len(alerts)}


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


# =============================================================================
# Ise UAT — Automated testing endpoints
# =============================================================================


@router.get("/ise/uat/results")
async def get_uat_results():
    """Get all stored UAT test run results."""
    from backend.aios.obaluaye.uat_runner import get_test_runs

    runs = get_test_runs()
    return {
        "total_runs": len(runs),
        "runs": runs,
    }


@router.get("/ise/uat/latest")
async def get_uat_latest():
    """Get the most recent UAT test run."""
    from backend.aios.obaluaye.uat_runner import get_latest_run

    latest = get_latest_run()
    if not latest:
        return {"message": "No test runs yet. Trigger one via POST /aios/v1/ise/uat/run"}
    return latest


@router.post("/ise/uat/run")
async def trigger_uat_run(data: dict | None = None):
    """Manually trigger a UAT test run.

    Body (optional):
        {"filter": "fleet"}  — only run tests matching this filter
    """
    from backend.aios.obaluaye.uat_runner import run_tests_now

    test_filter = None
    if data and data.get("filter"):
        test_filter = data["filter"]

    result = run_tests_now(test_filter=test_filter, trigger="manual")
    return result


@router.get("/ise/uat/alerts")
async def get_uat_alerts():
    """Get failed tests from the latest run as alerts."""
    from backend.aios.obaluaye.uat_runner import get_uat_alerts

    alerts = get_uat_alerts()
    return {"alerts": alerts, "count": len(alerts)}
