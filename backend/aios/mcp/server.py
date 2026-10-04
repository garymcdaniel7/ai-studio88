"""MCP Server — HTTP transport for MCP tool invocations.

Exposes AI Studio tools via an authenticated HTTP API that
MCP-compatible clients (Claude, ChatGPT, Cursor) can call.

All invocations go through the same governance pipeline as internal requests.
The external AI never has direct DB or infrastructure access.

Endpoints:
- GET /aios/v1/mcp/tools — list available tools (tool discovery)
- POST /aios/v1/mcp/invoke — invoke a tool (with governance)
- GET /aios/v1/mcp/schema — full MCP schema for client configuration

Authentication: API key in X-API-Key header or Bearer token.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from backend.aios.mcp.auth import (
    MCPAuthError,
    MCPClientIdentity,
    MCPRateLimitError,
    authenticate_mcp_request,
)
from backend.aios.mcp.tools import get_tool, get_tool_definitions, list_tools_by_category, MCP_TOOLS
from backend.aios.mcp.model_registry import get_spec, validate_model_for_dispatch, list_models_by_lane
from backend.aios.mcp.ollama_guard import guard_h3_dispatch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aios/v1/mcp", tags=["mcp"])


# =============================================================================
# Authentication Dependency
# =============================================================================


def require_mcp_client(
    authorization: Annotated[str | None, Header()] = None,
) -> MCPClientIdentity:
    """Authenticate the MCP client and resolve its identity.

    Every MCP endpoint depends on this. The resolved identity — including
    org_id — is the ONLY source of tenant scope. Request bodies never
    supply org_id, and nothing executes without a valid credential.
    """
    try:
        return authenticate_mcp_request(authorization)
    except MCPRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except MCPAuthError as exc:
        raise HTTPException(
            status_code=401,
            detail=exc.safe_message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


MCPClientDep = Annotated[MCPClientIdentity, Depends(require_mcp_client)]


# =============================================================================
# Cost Estimation — shared by the governance gate and the estimate_cost tool
# =============================================================================

# Per-invocation cost/time estimates. The governance budget gate reads these,
# so a missing entry must NOT fall through to zero — an unknown cost is
# treated as expensive enough to require review.
_TOOL_COST_ESTIMATES: dict[str, tuple[float, float]] = {
    # tool name: (cost_usd, time_seconds)
    "generate_image": (0.005, 45.0),
    "generate_video": (0.05, 120.0),
    "train_lora": (2.0, 1200.0),
    "schedule_post": (0.0, 1.0),
}

# Returned when a tool has no estimate. Chosen to exceed the default
# auto-approval limit so unpriced actions fail closed into review.
_UNKNOWN_COST_USD = 999.0

# Tools that only read and cost nothing to run.
_FREE_READ_TOOLS = frozenset({
    "search_talent",
    "get_talent_dna",
    "search_assets",
    "search_knowledge",
    "recommend_workflow",
    "check_gpu_status",
    "estimate_cost",
    "list_models",
    "get_training_status",
    "get_story_context",
})


def estimate_tool_cost(tool_name: str, params: dict | None = None) -> tuple[float, float]:
    """Estimate (cost_usd, time_seconds) for a tool invocation.

    Never returns 0.0 for an unrecognized tool — the governance budget gate
    depends on this value, and a zero silently disables it.
    """
    params = params or {}

    if tool_name in _FREE_READ_TOOLS:
        return 0.0, 1.0

    if tool_name in _TOOL_COST_ESTIMATES:
        cost, seconds = _TOOL_COST_ESTIMATES[tool_name]
        # Scale training cost by requested steps against the 1000-step baseline.
        if tool_name == "train_lora":
            steps = int(params.get("steps", 1000) or 1000)
            factor = max(steps, 1) / 1000
            return round(cost * factor, 4), seconds * factor
        # Scale video cost by requested duration against the 5s baseline.
        if tool_name == "generate_video":
            duration = int(params.get("duration_seconds", params.get("duration", 5)) or 5)
            factor = max(duration, 1) / 5
            return round(cost * factor, 4), seconds * factor
        return cost, seconds

    return _UNKNOWN_COST_USD, 0.0


# =============================================================================
# Tool Discovery
# =============================================================================


@router.get("/tools")
def mcp_list_tools(client: MCPClientDep):
    """List all available MCP tools.

    Returns the tool catalog that external AIs use to understand
    what they can do in AI Studio. Requires a valid credential — the
    catalog describes platform capabilities and is not public.
    """
    return {
        "tools": get_tool_definitions(),
        "total": len(MCP_TOOLS),
        "categories": list_tools_by_category(),
        "org_id": client.org_id,
    }


@router.get("/schema")
def mcp_schema(client: MCPClientDep):
    """Full MCP server schema — for client configuration.

    Compatible with the MCP protocol specification.
    """
    return {
        "name": "ai-studio",
        "version": "1.0.0",
        "description": "AI Studio — Creative Intelligence Platform. Generate images, train models, manage talent, publish content.",
        "tools": get_tool_definitions(),
        "authentication": {
            "type": "api_key",
            "header": "X-API-Key",
            "description": "API key from AI Studio Admin → API Keys",
        },
    }


# =============================================================================
# Tool Invocation
# =============================================================================


@router.post("/invoke")
async def mcp_invoke(data: dict, client: MCPClientDep):
    """Invoke an MCP tool.

    This is the primary execution endpoint for external AI clients.
    Each call goes through:
    1. Authentication (credential validation + rate limit) — via MCPClientDep
    2. Tool resolution (does the tool exist?)
    3. Capability check (is this client allowed to call it?)
    4. Cost estimation
    5. Governance check (requires approval?)
    6. Execution (or queue for approval)
    7. Decision logging — scoped to the client's org

    Body:
        tool: str — tool name to invoke
        parameters: dict — tool parameters
        session_id: str (optional — for conversation context)

    org_id is NEVER read from the body; it comes from the credential.
    """
    tool_name = data.get("tool")
    parameters = data.get("parameters", {})
    session_id = data.get("session_id", "mcp-session")

    if not tool_name:
        raise HTTPException(status_code=400, detail="'tool' required")

    # Resolve tool
    tool = get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Unknown tool: '{tool_name}'. Use GET /aios/v1/mcp/tools to list available tools.")

    # Capability check — deny by default when the credential doesn't grant it
    if not client.has_capability(tool_name):
        logger.warning(
            "MCP capability denied: cred=%s tool=%s",
            client.credential_id[:12],
            tool_name,
        )
        raise HTTPException(
            status_code=403,
            detail=f"This credential is not permitted to call '{tool_name}'.",
        )

    # Governance check — with a real cost estimate, not a placeholder zero
    from backend.aios.governance.authority import requires_approval
    from backend.aios.governance.queue import enqueue_approval
    from backend.aios.council.base import AuthorityLevel

    estimated_cost, estimated_seconds = estimate_tool_cost(tool_name, parameters)

    needs_review, reason = requires_approval(
        tool=tool_name,
        agent_authority=AuthorityLevel.EXECUTE_WRITE,  # MCP clients get write authority
        estimated_cost=estimated_cost,
    )

    if needs_review:
        try:
            approval = enqueue_approval(
                session_id=session_id,
                tool=tool_name,
                parameters=parameters,
                reasoning=f"MCP invocation: {reason}",
                estimated_cost_usd=estimated_cost,
                estimated_time_seconds=estimated_seconds,
                agent="mcp_client",
                org_id=client.org_id,
                strict=True,
            )
        except Exception as exc:
            # The approval row did not persist. Returning a pending status
            # here would hand the caller an approval_id that no human can
            # ever see, so fail loudly instead.
            logger.error(
                "MCP approval enqueue failed: tool=%s org=%s — %s",
                tool_name,
                client.org_id[:8],
                exc,
            )
            raise HTTPException(
                status_code=503,
                detail="This action requires approval, but the approval could not be recorded. Nothing was executed.",
            ) from exc

        return {
            "status": "pending_approval",
            "approval_id": approval.get("id"),
            "reason": reason,
            "estimated_cost_usd": estimated_cost,
            "message": "This action requires human approval. Review at /aios/v1/approvals.",
        }

    # Execute tool
    start = time.time()
    try:
        result = await _execute_tool(tool_name, parameters, client.org_id)
    except Exception as e:
        logger.error(f"MCP tool execution failed: {tool_name} — {e}")
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {str(e)[:200]}")

    elapsed = time.time() - start

    # Log decision — org-scoped audit trail. A logging failure must not
    # discard an execution that already produced side effects, so this is
    # guarded and reported rather than raised.
    from backend.aios.decisions import log_decision

    try:
        log_decision(
            org_id=client.org_id,
            session_id=session_id,
            decision_type="mcp_invoke",
            provider="mcp_client",
            model=tool_name,
            input_summary=str(parameters)[:200],
            output_summary=str(result)[:200] if result else "",
            latency_ms=int(elapsed * 1000),
            cost_usd=estimated_cost,
        )
    except Exception as exc:
        logger.error(
            "MCP decision logging failed after execution: tool=%s org=%s — %s",
            tool_name,
            client.org_id[:8],
            exc,
        )

    return {
        "status": "completed",
        "tool": tool_name,
        "result": result,
        "latency_ms": int(elapsed * 1000),
    }


# =============================================================================
# Tool Execution Router
# =============================================================================


async def _execute_tool(tool_name: str, params: dict, org_id: str) -> dict:
    """Route a tool invocation to the appropriate backend handler.

    Args:
        org_id: Tenant scope resolved from the client credential. Every
            tenant-scoped executor receives it explicitly — no executor
            derives tenancy from params.
    """
    if not org_id:
        raise ValueError("org_id is required for MCP tool execution")

    if tool_name == "search_talent":
        return await _exec_search_talent(params, org_id)
    elif tool_name == "get_talent_dna":
        return await _exec_get_talent_dna(params, org_id)
    elif tool_name == "create_talent":
        return await _exec_create_talent(params, org_id)
    elif tool_name == "generate_image":
        return await _exec_generate_image(params)
    elif tool_name == "generate_video":
        return await _exec_generate_video(params, org_id)
    elif tool_name == "recommend_workflow":
        return await _exec_recommend_workflow(params)
    elif tool_name == "train_lora":
        return await _exec_train_lora(params)
    elif tool_name == "get_training_status":
        return await _exec_get_training_status(params, org_id)
    elif tool_name == "search_assets":
        return await _exec_search_assets(params, org_id)
    elif tool_name == "schedule_post":
        return await _exec_schedule_post(params)
    elif tool_name == "check_gpu_status":
        return await _exec_check_gpu_status(params)
    elif tool_name == "estimate_cost":
        return await _exec_estimate_cost(params)
    elif tool_name == "list_models":
        return await _exec_list_models(params)
    elif tool_name == "search_knowledge":
        return await _exec_search_knowledge(params)
    elif tool_name == "continue_story":
        return {"status": "not_implemented", "message": "Story continuation coming soon"}
    elif tool_name == "get_story_context":
        return {"status": "not_implemented", "message": "Story context coming soon"}
    else:
        return {"error": f"Tool '{tool_name}' has no executor"}


# =============================================================================
# Tool Executors
# =============================================================================


async def _exec_search_talent(params: dict, org_id: str) -> dict:
    """Search talent within the caller's org.

    Uses the org-scoped database helper rather than a raw table query so
    tenant filtering cannot be omitted.
    """
    from backend.database import get_talent

    query = params.get("query", "")
    type_filter = params.get("type_filter")
    limit = int(params.get("limit", 10) or 10)

    results = get_talent(org_id).data or []

    if type_filter:
        results = [t for t in results if t.get("default_style") == type_filter]

    if query:
        ql = query.lower()
        results = [
            t for t in results
            if ql in (t.get("name") or "").lower() or ql in (t.get("bio") or "").lower()
        ]

    fields = ("id", "name", "bio", "default_style", "visual_style", "avatar_url")
    trimmed = [{k: t.get(k) for k in fields} for t in results[:limit]]
    return {"talents": trimmed, "total": len(results)}


async def _exec_get_talent_dna(params: dict, org_id: str) -> dict:
    """Get Creative DNA for a talent, after confirming it belongs to the org."""
    from backend.aios.knowledge.graph import get_talent_knowledge
    from backend.database import get_talent_by_id

    talent_id = params.get("talent_id")
    if not talent_id:
        return {"error": "talent_id required"}

    # Ownership check — same response for not-found and cross-tenant so the
    # caller cannot probe for the existence of another org's talent.
    owned = get_talent_by_id(talent_id, org_id).data or []
    if not owned:
        return {"error": "Talent not found"}

    return get_talent_knowledge(talent_id)


async def _exec_create_talent(params: dict, org_id: str) -> dict:
    """Create a talent record owned by the caller's org."""
    from backend.database import create_talent

    record = {
        "name": params.get("name", ""),
        "bio": params.get("bio", ""),
        "default_style": params.get("type", "model"),
        "visual_style": params.get("visual_style", ""),
    }
    result = create_talent(record, org_id)
    return result.data[0] if result.data else record


async def _exec_generate_image(params: dict) -> dict:
    """Generate an image via ComfyUI, with model validation and pre-flight checks.

    Validates:
    - Model name resolves to a known spec
    - Corresponding workflow template exists on disk
    - Ollama isn't squatting VRAM for VRAM-critical image models
    """
    model = params.get("model", "flux-dev")
    workflow = params.get("workflow", "auto")

    # Step 1: Model validation — known spec + correct lane + workflow exists
    from pathlib import Path

    workflows_dir = Path(
        os.getenv("COMFYUI_WORKFLOWS_DIR", "./workflows/comfyui")
    )
    validation = validate_model_for_dispatch(model, "image", workflows_dir)
    if not validation.get("valid"):
        return {
            "status": "invalid_model",
            "error": validation.get("error", "Model validation failed"),
            "suggestions": validation.get("suggestions", list_models_by_lane("image")),
        }

    spec = validation["spec"]

    # Step 2: Ollama pre-flight for VRAM-critical image models
    guard = guard_h3_dispatch(model)
    if not guard.get("can_dispatch"):
        return {
            "status": "vram_conflict",
            "error": guard.get("reason", "VRAM conflict detected"),
            "ollama_status": guard.get("ollama_status", {}),
            "resolution": "Kill Ollama with `pkill -9 -f ollama` and retry.",
        }

    # Step 3: Resolve workflow template
    if workflow and workflow != "auto":
        spec_workflow = workflow
    else:
        spec_workflow = spec.workflow_template

    # Step 4: Dispatch to worker
    from backend.infrastructure.worker_api_client import get_worker_client

    client = get_worker_client()
    if client and client.is_available():
        # Pass resolved workflow to the worker
        dispatch_params = dict(params)
        dispatch_params["workflow"] = spec_workflow
        return client.generate_image(**dispatch_params)

    return {
        "status": "unavailable",
        "error": "No GPU worker available. Launch a worker first.",
        "model_validated": model,
        "workflow_resolved": spec_workflow,
    }


async def _exec_generate_video(params: dict, org_id: str) -> dict:
    """Enqueue a real video_generation job for the GPU worker.

    Includes model validation and Ollama VRAM pre-flight checks before
    enqueueing. Previously accepted any model string without validation
    and could produce silent simulation fallback on the worker side.

    The worker (backend.worker) polls the Supabase jobs table scoped to the
    org and dispatches 'video_generation' to VideoGenerationHandler, which
    runs the real ComfyUI/WAN provider and uploads the result to B2.

    The job is created under the caller's org_id, resolved from the
    credential — never a hardcoded tenant.
    """
    from pathlib import Path

    from backend.database import create_job

    if not params.get("prompt"):
        return {"error": "prompt is required", "status": "invalid_request"}

    model = params.get("model", "wan-2.2-t2v")
    workflow = params.get("workflow", "auto")

    # Step 1: Model validation — known spec + correct lane + workflow exists
    workflows_dir = Path(
        os.getenv("COMFYUI_WORKFLOWS_DIR", "./workflows/comfyui")
    )
    validation = validate_model_for_dispatch(model, "video", workflows_dir)
    if not validation.get("valid"):
        return {
            "status": "invalid_model",
            "error": validation.get("error", "Model validation failed"),
            "suggestions": validation.get("suggestions", list_models_by_lane("video")),
        }

    spec = validation["spec"]

    # Step 2: Ollama pre-flight — video models are VRAM-critical
    guard = guard_h3_dispatch(model)
    if not guard.get("can_dispatch"):
        return {
            "status": "vram_conflict",
            "error": guard.get("reason", "VRAM conflict detected"),
            "ollama_status": guard.get("ollama_status", {}),
            "resolution": "Kill Ollama with `pkill -9 -f ollama` and retry.",
        }

    # Step 3: Resolve workflow template for the job
    if workflow and workflow != "auto":
        spec_workflow = workflow
    else:
        spec_workflow = spec.workflow_template

    duration = params.get("duration_seconds", params.get("duration", 5))
    job_input = {
        "prompt": params.get("prompt", ""),
        "negative_prompt": params.get("negative_prompt", ""),
        "motion_prompt": params.get("motion_prompt", ""),
        "model": model,
        "workflow_template": spec_workflow,
        "duration_seconds": int(duration),
        "fps": int(params.get("fps", 24)),
        "width": int(params.get("width", 832)),
        "height": int(params.get("height", 480)),
        "camera_motion": params.get("camera_motion", "static"),
        "seed": int(params.get("seed", -1)),
        "talent_id": params.get("talent_id"),
    }

    job = {
        "type": "video_generation",
        "status": "queued",
        "priority": 5,
        "input": job_input,
        "attempts": 0,
        "max_attempts": 3,
        "progress": 0,
    }

    try:
        created = create_job(job, org_id)
        job_id = created.data[0]["id"] if created.data else None
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to enqueue video_generation job: %s", exc)
        return {"error": f"Failed to enqueue video job: {exc}", "status": "failed"}

    return {
        "status": "queued",
        "job_id": job_id,
        "model": model,
        "workflow_template": spec_workflow,
        "duration_seconds": job_input["duration_seconds"],
        "message": (
            f"Video generation job queued for the GPU worker using {spec_workflow} template. "
            f"Poll get_training_status with the job_id."
        ),
    }


async def _exec_recommend_workflow(params: dict) -> dict:
    from backend.aios.knowledge.workflow_dna import recommend_workflow
    return {"recommendations": recommend_workflow(
        content_type=params.get("content_type", "image"),
        talent_id=params.get("talent_id"),
    )}


async def _exec_train_lora(params: dict) -> dict:
    """LoRA training is gated upstream and has no MCP executor yet.

    Reaching this function means the governance gate let the call through
    without one, which should not happen. It previously claimed the job had
    been queued; nothing was ever enqueued here, so report honestly.
    """
    logger.error("train_lora executor reached without a training pipeline — nothing was queued")
    return {
        "status": "not_implemented",
        "message": "LoRA training is not yet wired to the MCP surface. No job was queued.",
    }


async def _exec_get_training_status(params: dict, org_id: str) -> dict:
    """Get job status, scoped to the caller's org.

    Returns the same "not found" response for a missing job and for a job
    owned by another tenant, so job IDs cannot be probed across orgs.
    """
    from backend.database import supabase

    job_id = params.get("job_id")
    if not job_id:
        return {"error": "job_id required"}

    # Poll the main jobs table first (covers image/video generation),
    # then fall back to training_jobs for LoRA training. Both filtered by org.
    for table in ("jobs", "training_jobs"):
        try:
            rows = (
                supabase.table(table)
                .select("*")
                .eq("id", job_id)
                .eq("org_id", org_id)
                .limit(1)
                .execute()
                .data
            )
            if rows:
                return rows[0]
        except Exception:
            continue

    return {"error": "Job not found"}


async def _exec_search_assets(params: dict, org_id: str) -> dict:
    """Search assets within the caller's org.

    Uses the org-scoped helper, which also applies compliance quarantine
    filtering that a raw table query would bypass.
    """
    from backend.database import get_assets

    limit = int(params.get("limit", 20) or 20)
    results = get_assets(org_id).data or []

    if params.get("type"):
        wanted = str(params["type"]).lower()
        results = [a for a in results if wanted in (a.get("type") or "").lower()]
    if params.get("talent_id"):
        results = [a for a in results if a.get("talent_id") == params["talent_id"]]

    fields = ("id", "filename", "type", "created_at", "public_url")
    trimmed = [{k: a.get(k) for k in fields} for a in results[:limit]]
    return {"assets": trimmed, "total": len(results)}


async def _exec_schedule_post(params: dict) -> dict:
    """Publishing is gated upstream and has no MCP executor yet.

    Previously claimed the post had been queued while enqueueing nothing.
    """
    logger.error("schedule_post executor reached without a publishing call — nothing was queued")
    return {
        "status": "not_implemented",
        "message": "Publishing is not yet wired to the MCP surface. No post was scheduled.",
    }


async def _exec_check_gpu_status(params: dict) -> dict:
    try:
        from backend.infrastructure.worker_orchestrator import get_orchestrator
        o = get_orchestrator()
        if o.session and o.session.instance_id:
            return {
                "active": True,
                "gpu": o.session.gpu_name,
                "worker": o.session.worker_name,
                "status": o.session.status,
            }
        return {"active": False, "message": "No GPU worker running"}
    except Exception:
        return {"active": False}


async def _exec_estimate_cost(params: dict) -> dict:
    """Estimate cost for an action.

    Reads the same table the governance budget gate uses, so a quote shown
    to a caller can never disagree with the gate that will judge it.
    """
    action = params.get("action", "")
    if not action:
        return {"error": "action required"}

    known = action in _FREE_READ_TOOLS or action in _TOOL_COST_ESTIMATES
    cost, seconds = estimate_tool_cost(action, params)

    if not known:
        return {
            "action": action,
            "estimated": False,
            "note": f"No cost model for '{action}'. Treated as requiring approval.",
        }

    return {
        "action": action,
        "estimated": True,
        "cost_usd": cost,
        "time_seconds": seconds,
    }


async def _exec_list_models(params: dict) -> dict:
    """List available models for generation.

    Returns model names, workflow templates, lane, and notes so MCP
    clients can discover valid values before calling generate_image
    or generate_video.
    """
    lane = params.get("lane", "all")

    if lane == "image":
        models = list_models_by_lane("image")
    elif lane == "video":
        models = list_models_by_lane("video")
    else:
        models = list_models_by_lane("image") + list_models_by_lane("video")

    return {
        "models": models,
        "total": len(models),
        "lane": lane,
        "note": "Use these model names in generate_image or generate_video.",
    }


async def _exec_search_knowledge(params: dict) -> dict:
    from backend.aios.knowledge.graph import KnowledgeQuery, search
    sources = [s.strip() for s in params.get("sources", "").split(",")] if params.get("sources") else []
    query = KnowledgeQuery(query=params.get("query", ""), sources=sources)
    results = search(query)
    return {
        "results": [{"source": r.source, "name": r.name, "relevance": r.relevance, "summary": r.summary} for r in results[:10]],
        "total": len(results),
    }
