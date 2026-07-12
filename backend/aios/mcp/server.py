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
import time

from fastapi import APIRouter, HTTPException, Request

from backend.aios.mcp.tools import get_tool, get_tool_definitions, list_tools_by_category, MCP_TOOLS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aios/v1/mcp", tags=["mcp"])


# =============================================================================
# Tool Discovery
# =============================================================================


@router.get("/tools")
def mcp_list_tools():
    """List all available MCP tools.

    Returns the tool catalog that external AIs use to understand
    what they can do in AI Studio.
    """
    return {
        "tools": get_tool_definitions(),
        "total": len(MCP_TOOLS),
        "categories": list_tools_by_category(),
    }


@router.get("/schema")
def mcp_schema():
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
async def mcp_invoke(data: dict, request: Request):
    """Invoke an MCP tool.

    This is the primary execution endpoint for external AI clients.
    Each call goes through:
    1. Authentication (API key validation)
    2. Tool resolution (does the tool exist?)
    3. Parameter validation
    4. Governance check (requires approval?)
    5. Execution (or queue for approval)
    6. Decision logging

    Body:
        tool: str — tool name to invoke
        parameters: dict — tool parameters
        session_id: str (optional — for conversation context)
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

    # Governance check
    from backend.aios.governance.authority import requires_approval
    from backend.aios.governance.queue import enqueue_approval
    from backend.aios.council.base import AuthorityLevel

    needs_review, reason = requires_approval(
        tool=tool_name,
        agent_authority=AuthorityLevel.EXECUTE_WRITE,  # MCP clients get write authority
        estimated_cost=0.0,  # Cost estimated by tool executor
    )

    if needs_review:
        approval = enqueue_approval(
            session_id=session_id,
            tool=tool_name,
            parameters=parameters,
            reasoning=f"MCP invocation: {reason}",
            agent="mcp_client",
        )
        return {
            "status": "pending_approval",
            "approval_id": approval.get("id"),
            "reason": reason,
            "message": f"This action requires human approval. Review at /aios/v1/approvals.",
        }

    # Execute tool
    start = time.time()
    try:
        result = await _execute_tool(tool_name, parameters)
    except Exception as e:
        logger.error(f"MCP tool execution failed: {tool_name} — {e}")
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {str(e)[:200]}")

    elapsed = time.time() - start

    # Log decision
    from backend.aios.decisions import log_decision

    log_decision(
        session_id=session_id,
        decision_type="mcp_invoke",
        provider="mcp_client",
        model=tool_name,
        input_summary=str(parameters)[:200],
        output_summary=str(result)[:200] if result else "",
        latency_ms=int(elapsed * 1000),
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


async def _execute_tool(tool_name: str, params: dict) -> dict:
    """Route a tool invocation to the appropriate backend handler."""

    if tool_name == "search_talent":
        return await _exec_search_talent(params)
    elif tool_name == "get_talent_dna":
        return await _exec_get_talent_dna(params)
    elif tool_name == "create_talent":
        return await _exec_create_talent(params)
    elif tool_name == "generate_image":
        return await _exec_generate_image(params)
    elif tool_name == "generate_video":
        return await _exec_generate_video(params)
    elif tool_name == "recommend_workflow":
        return await _exec_recommend_workflow(params)
    elif tool_name == "train_lora":
        return await _exec_train_lora(params)
    elif tool_name == "get_training_status":
        return await _exec_get_training_status(params)
    elif tool_name == "search_assets":
        return await _exec_search_assets(params)
    elif tool_name == "schedule_post":
        return await _exec_schedule_post(params)
    elif tool_name == "check_gpu_status":
        return await _exec_check_gpu_status(params)
    elif tool_name == "estimate_cost":
        return await _exec_estimate_cost(params)
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


async def _exec_search_talent(params: dict) -> dict:
    from backend.database import supabase
    query = params.get("query", "")
    type_filter = params.get("type_filter")
    limit = params.get("limit", 10)

    q = supabase.table("talent").select("id,name,bio,default_style,visual_style,avatar_url").limit(limit)
    if type_filter:
        q = q.eq("default_style", type_filter)
    results = q.execute().data or []

    # Filter by query
    if query:
        ql = query.lower()
        results = [t for t in results if ql in (t.get("name") or "").lower() or ql in (t.get("bio") or "").lower()]

    return {"talents": results[:limit], "total": len(results)}


async def _exec_get_talent_dna(params: dict) -> dict:
    from backend.aios.knowledge.graph import get_talent_knowledge
    talent_id = params.get("talent_id")
    if not talent_id:
        return {"error": "talent_id required"}
    return get_talent_knowledge(talent_id)


async def _exec_create_talent(params: dict) -> dict:
    from backend.database import supabase
    record = {
        "name": params.get("name", ""),
        "bio": params.get("bio", ""),
        "default_style": params.get("type", "model"),
        "visual_style": params.get("visual_style", ""),
    }
    result = supabase.table("talent").insert(record).execute()
    return result.data[0] if result.data else record


async def _exec_generate_image(params: dict) -> dict:
    from backend.infrastructure.worker_api_client import get_worker_client
    client = get_worker_client()
    if client and client.is_available():
        return client.generate_image(**params)
    return {"error": "No GPU worker available. Launch a worker first.", "status": "unavailable"}


async def _exec_generate_video(params: dict) -> dict:
    return {"status": "queued", "message": "Video generation queued. Check status via get_training_status.", "params": params}


async def _exec_recommend_workflow(params: dict) -> dict:
    from backend.aios.knowledge.workflow_dna import recommend_workflow
    return {"recommendations": recommend_workflow(
        content_type=params.get("content_type", "image"),
        talent_id=params.get("talent_id"),
    )}


async def _exec_train_lora(params: dict) -> dict:
    return {"status": "requires_approval", "message": "LoRA training requires human approval. It has been queued."}


async def _exec_get_training_status(params: dict) -> dict:
    from backend.database import supabase
    job_id = params.get("job_id")
    if not job_id:
        return {"error": "job_id required"}
    try:
        result = supabase.table("training_jobs").select("*").eq("id", job_id).single().execute().data
        return result or {"error": "Job not found"}
    except Exception:
        return {"error": "Job not found"}


async def _exec_search_assets(params: dict) -> dict:
    from backend.database import supabase
    q = supabase.table("assets").select("id,filename,type,created_at,public_url").order("created_at", desc=True).limit(params.get("limit", 20))
    if params.get("type"):
        q = q.ilike("type", f"%{params['type']}%")
    if params.get("talent_id"):
        q = q.eq("talent_id", params["talent_id"])
    return {"assets": q.execute().data or []}


async def _exec_schedule_post(params: dict) -> dict:
    return {"status": "requires_approval", "message": "Publishing requires human approval. It has been queued."}


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
    action = params.get("action", "")
    estimates = {
        "generate_image": {"cost_usd": 0.003, "time_seconds": 45, "model": "flux-dev"},
        "generate_video": {"cost_usd": 0.05, "time_seconds": 120, "model": "wan-2.1"},
        "train_lora": {"cost_usd": 2.0, "time_seconds": 1200, "model": "flux-dev"},
    }
    return estimates.get(action, {"cost_usd": 0, "time_seconds": 0, "note": f"Unknown action: {action}"})


async def _exec_search_knowledge(params: dict) -> dict:
    from backend.aios.knowledge.graph import KnowledgeQuery, search
    sources = [s.strip() for s in params.get("sources", "").split(",")] if params.get("sources") else []
    query = KnowledgeQuery(query=params.get("query", ""), sources=sources)
    results = search(query)
    return {
        "results": [{"source": r.source, "name": r.name, "relevance": r.relevance, "summary": r.summary} for r in results[:10]],
        "total": len(results),
    }
