"""AI Studio tools for Hermes — our AIOS becomes Hermes's toolkit.

These are custom tool functions that Hermes can call during conversations.
Each tool maps to an AI Studio capability. Hermes decides WHEN to call them
based on the user's request.

Hermes handles: conversation, memory, learning, skill creation
These tools handle: generation, training, fleet, governance, knowledge
"""

from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

API_BASE = "http://localhost:8000"


# =============================================================================
# Tool definitions (Hermes tool format)
# =============================================================================

AISTUDIO_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Generate an AI image using ComfyUI on the GPU worker. Supports Flux Dev (high quality portraits), SDXL Turbo (fast drafts), SD 1.5 (anime). Returns base64 image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Image generation prompt (be descriptive)"},
                    "model": {"type": "string", "enum": ["flux-dev", "sdxl-turbo", "sd15"], "description": "Model to use"},
                    "width": {"type": "integer", "description": "Width in pixels", "default": 1024},
                    "height": {"type": "integer", "description": "Height in pixels", "default": 1024},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "train_lora",
            "description": "Start LoRA training for a talent. Uses their uploaded photos. Costs ~$2, takes 15-30 min. Requires talent_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "talent_id": {"type": "string", "description": "UUID of the talent to train"},
                    "trigger_word": {"type": "string", "description": "LoRA trigger word (e.g., 'ohwx')", "default": "ohwx"},
                    "steps": {"type": "integer", "description": "Training steps (500-5000)", "default": 1000},
                },
                "required": ["talent_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_talent",
            "description": "Search the talent library by name, style, or type. Returns matching talent profiles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (name, style, keywords)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_talent_knowledge",
            "description": "Get full knowledge about a talent: profile, Creative DNA, LoRAs, voices, relationships, recent generations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "talent_id": {"type": "string", "description": "Talent UUID"},
                },
                "required": ["talent_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_platform_health",
            "description": "Check health of all AI Studio services: ComfyUI, Ollama, Supabase, B2, ElevenLabs, Worker API. Returns status per service.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "auto_configure_generation",
            "description": "Get the optimal generation configuration for a request. Picks best model, LoRAs, steps, resolution based on Workflow DNA and talent preferences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "What to generate"},
                    "talent_id": {"type": "string", "description": "Talent context (optional)"},
                    "quality": {"type": "string", "enum": ["draft", "standard", "high", "auto"], "default": "auto"},
                    "platform": {"type": "string", "enum": ["instagram", "tiktok", "youtube"], "description": "Target platform (optional)"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_graph",
            "description": "Search across ALL platform knowledge: talents, models, Creative DNA, Object DNA, stories, workflows, generation history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fleet_status",
            "description": "Get GPU fleet status: active workers, VRAM usage, models loaded, hourly cost, budget remaining.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_worker_status",
            "description": "Get detailed GPU worker status including lifecycle state, GPU name, hourly rate, session cost, models loaded, and progress message. Admin-only.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_generation_pipeline",
            "description": "Check if the generation pipeline is functional: ComfyUI reachable, models loaded, preflight check. Returns ready state per model. Admin-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "string", "description": "Model to check (sdxl-turbo, flux2-dev, flux2-klein, flux-dev, sd15)", "default": "sdxl-turbo"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "launch_gpu_worker",
            "description": "Launch a GPU worker on RunPod or Vast.ai. ALWAYS confirm cost with admin first. Returns session_id and begins boot sequence. Admin-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "enum": ["runpod", "vast"], "description": "GPU provider (default: runpod)"},
                    "max_price": {"type": "number", "description": "Max hourly price in USD (default: 1.50)"},
                    "min_vram_gb": {"type": "number", "description": "Min VRAM in GB (default: 12)"},
                    "gpu_filter": {"type": "string", "description": "GPU name filter (e.g. 'RTX 4090')"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_gpu_worker",
            "description": "Stop and destroy the active GPU worker. Records final cost. Requires explicit admin confirmation. Admin-only.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cost_summary",
            "description": "Get cost summary: today's spend, current session cost, per-job breakdown, budget status. Admin-only.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose_service",
            "description": "Diagnose a failing service using AI analysis. Returns root cause, fix command, and whether auto-fix is available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name (comfyui, ollama, worker_api, supabase, elevenlabs)"},
                    "error": {"type": "string", "description": "Error message observed"},
                },
                "required": ["service", "error"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_voice",
            "description": "Generate speech from text. Uses ElevenLabs or MOSS-TTS. Returns audio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to speak"},
                    "voice_id": {"type": "string", "description": "Voice ID (optional, uses default)"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_post",
            "description": "Schedule a social media post. Requires approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "enum": ["instagram", "tiktok", "youtube", "twitter"]},
                    "content": {"type": "string", "description": "Post text/caption"},
                    "scheduled_for": {"type": "string", "description": "ISO datetime to publish"},
                },
                "required": ["platform", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_uat_tests",
            "description": "Run Playwright E2E tests on the frontend. Can run all tests or filter by page name. Returns pass/fail counts and details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "description": "Optional filter (e.g. 'fleet', 'brain', 'create')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_uat_results",
            "description": "Get the latest UAT test results without running new tests. Shows pass/fail per test.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# =============================================================================
# Tool Executors — called by Hermes when it invokes a tool
# =============================================================================


def execute_tool(name: str, arguments: dict) -> str:
    """Execute an AI Studio tool and return the result as a string.

    This is the bridge Hermes calls. Each tool makes an HTTP call
    to our own backend endpoints.
    """
    executors = {
        "generate_image": _exec_generate_image,
        "train_lora": _exec_train_lora,
        "search_talent": _exec_search_talent,
        "get_talent_knowledge": _exec_get_talent_knowledge,
        "check_platform_health": _exec_check_health,
        "auto_configure_generation": _exec_auto_configure,
        "search_knowledge_graph": _exec_search_knowledge,
        "get_fleet_status": _exec_fleet_status,
        "get_worker_status": _exec_get_worker_status,
        "check_generation_pipeline": _exec_check_generation_pipeline,
        "launch_gpu_worker": _exec_launch_gpu_worker,
        "stop_gpu_worker": _exec_stop_gpu_worker,
        "get_cost_summary": _exec_get_cost_summary,
        "diagnose_service": _exec_diagnose,
        "generate_voice": _exec_generate_voice,
        "schedule_post": _exec_schedule_post,
        "run_uat_tests": _exec_run_uat_tests,
        "get_uat_results": _exec_get_uat_results,
    }

    executor = executors.get(name)
    if not executor:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        result = executor(arguments)
        return json.dumps(result, default=str)
    except Exception as e:
        error_detail = {
            "error": str(e)[:300],
            "tool": name,
            "arguments": arguments,
            "debug_hint": f"Check if the backend service for '{name}' is running. Try: GET http://localhost:8000/aios/v1/health/full",
        }
        logger.error(f"Hermes tool '{name}' failed: {e}")
        return json.dumps(error_detail)


def _exec_generate_image(args: dict) -> dict:
    resp = httpx.post(f"{API_BASE}/api/v1/generate/image", json=args, timeout=300)
    if resp.status_code == 200:
        data = resp.json()
        # Don't return full base64 to Hermes (too large for context)
        return {"success": True, "model": data.get("model"), "generation_time": data.get("generation_time"), "filename": data.get("filename"), "message": "Image generated successfully"}
    return {"error": resp.text[:200]}


def _exec_train_lora(args: dict) -> dict:
    resp = httpx.post(f"{API_BASE}/api/v1/training/start", data={
        "talent_id": args.get("talent_id", ""),
        "trigger_word": args.get("trigger_word", "ohwx"),
        "steps": str(args.get("steps", 1000)),
        "use_talent_media": "true",
        "base_model": "flux-dev",
        "provider": "simpletuner",
    }, timeout=30)
    if resp.status_code == 201:
        return resp.json()
    return {"error": resp.text[:200]}


def _exec_search_talent(args: dict) -> dict:
    resp = httpx.get(f"{API_BASE}/aios/v1/knowledge/search", params={"q": args.get("query", ""), "sources": "talent"}, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        return {"results": [{"name": r["name"], "id": r["entity_id"], "summary": r.get("summary", "")} for r in data.get("results", [])[:5]]}
    return {"results": []}


def _exec_get_talent_knowledge(args: dict) -> dict:
    resp = httpx.get(f"{API_BASE}/aios/v1/knowledge/talent/{args.get('talent_id', '')}", timeout=10)
    if resp.status_code == 200:
        return resp.json()
    return {"error": "Talent not found"}


def _exec_check_health(args: dict) -> dict:
    resp = httpx.get(f"{API_BASE}/aios/v1/health/full", timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        # Summarize for Hermes (don't overwhelm context)
        summary = {"overall": data.get("overall")}
        for name, svc in data.get("services", {}).items():
            summary[name] = svc.get("status", "unknown")
        return summary
    return {"error": "Health check failed"}


def _exec_auto_configure(args: dict) -> dict:
    resp = httpx.post(f"{API_BASE}/aios/v1/workflow/configure", json=args, timeout=10)
    if resp.status_code == 200:
        return resp.json()
    return {"error": resp.text[:200]}


def _exec_search_knowledge(args: dict) -> dict:
    resp = httpx.get(f"{API_BASE}/aios/v1/knowledge/search", params={"q": args.get("query", "")}, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        return {"results": [{"source": r["source"], "name": r["name"], "summary": r.get("summary", "")} for r in data.get("results", [])[:8]]}
    return {"results": []}


def _exec_fleet_status(args: dict) -> dict:
    resp = httpx.post(f"{API_BASE}/aios/v1/session/autoscale", json={"pending_tasks": []}, timeout=10)
    if resp.status_code == 200:
        return resp.json().get("fleet", {})
    return {"error": "Fleet status unavailable"}


def _exec_diagnose(args: dict) -> dict:
    resp = httpx.post(f"{API_BASE}/aios/v1/health/diagnose", json=args, timeout=30)
    if resp.status_code == 200:
        return resp.json()
    return {"error": resp.text[:200]}


def _exec_generate_voice(args: dict) -> dict:
    resp = httpx.post(f"{API_BASE}/api/v1/audio/tts/preview", json=args, timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        return {"success": True, "duration_seconds": data.get("duration_seconds"), "message": "Voice generated"}
    return {"error": resp.text[:200]}


def _exec_schedule_post(args: dict) -> dict:
    return {"status": "requires_approval", "message": "Post scheduling requires human approval. Queued for review."}


def _exec_run_uat_tests(args: dict) -> dict:
    """Run Playwright UAT tests via the Ise runner."""
    try:
        from backend.aios.obaluaye.uat_runner import run_tests_now

        test_filter = args.get("filter")
        result = run_tests_now(test_filter=test_filter, trigger="hermes")
        return {
            "status": "completed",
            "total": result.get("total", 0),
            "passed": result.get("passed", 0),
            "failed": result.get("failed", 0),
            "failures": [
                r for r in result.get("results", []) if r.get("status") == "failed"
            ][:10],  # Limit to 10 failures for context
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _exec_get_uat_results(args: dict) -> dict:
    """Get the latest UAT test results."""
    try:
        from backend.aios.obaluaye.uat_runner import get_latest_run, get_test_runs

        latest = get_latest_run()
        if not latest:
            return {"status": "no_runs", "message": "No UAT runs yet. Use run_uat_tests to trigger one."}
        return {
            "status": "ok",
            "total_runs": len(get_test_runs()),
            "latest": {
                "run_id": latest.get("run_id"),
                "total": latest.get("total", 0),
                "passed": latest.get("passed", 0),
                "failed": latest.get("failed", 0),
                "trigger": latest.get("trigger"),
                "completed_at": latest.get("completed_at"),
            },
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# =============================================================================
# GPU Infrastructure Tool Executors (Admin-Only)
# =============================================================================


def _exec_get_worker_status(args: dict) -> dict:
    """Get detailed GPU worker status from the orchestrator."""
    resp = httpx.get(f"{API_BASE}/api/v1/infrastructure/worker/status", timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        # Enrich with cost estimate
        if data.get("active") and data.get("hourly_rate"):
            data["cost_alert"] = (
                "IDLE WARNING: Worker running without recent generation"
                if data.get("jobs_completed", 0) == 0
                and data.get("status") == "ready"
                else None
            )
        return data
    return {"error": f"Worker status check failed: {resp.status_code}"}


def _exec_check_generation_pipeline(args: dict) -> dict:
    """Check generation pipeline: ComfyUI reachability + model availability."""
    model = args.get("model", "sdxl-turbo")
    result = {}

    # Check preflight
    try:
        preflight = httpx.get(
            f"{API_BASE}/api/v1/generate/preflight",
            params={"model": model},
            timeout=10,
        )
        if preflight.status_code == 200:
            result["preflight"] = preflight.json()
        else:
            result["preflight"] = {"ready": False, "error": preflight.text[:200]}
    except Exception as e:
        result["preflight"] = {"ready": False, "error": str(e)[:200]}

    # Check available models
    try:
        models_resp = httpx.get(
            f"{API_BASE}/api/v1/generate/available-models", timeout=10
        )
        if models_resp.status_code == 200:
            models_data = models_resp.json()
            result["models"] = models_data.get("models", [])
            result["ready_models"] = [
                m["id"] for m in result["models"] if m.get("ready")
            ]
        else:
            result["models"] = []
            result["ready_models"] = []
    except Exception as e:
        result["models"] = []
        result["error"] = str(e)[:200]

    result["pipeline_ready"] = bool(result.get("ready_models"))
    return result


def _exec_launch_gpu_worker(args: dict) -> dict:
    """Launch a GPU worker. Returns immediately with session_id."""
    payload = {
        "provider": args.get("provider", "runpod"),
        "max_price": args.get("max_price", 1.50),
        "min_vram_gb": args.get("min_vram_gb", 12),
    }
    if args.get("gpu_filter"):
        payload["gpu_filter"] = args["gpu_filter"]

    resp = httpx.post(
        f"{API_BASE}/api/v1/infrastructure/worker/launch",
        json=payload,
        timeout=30,
    )
    if resp.status_code == 200:
        return resp.json()
    return {"error": f"Launch failed: {resp.text[:200]}"}


def _exec_stop_gpu_worker(args: dict) -> dict:
    """Stop the active GPU worker and destroy the instance."""
    resp = httpx.post(
        f"{API_BASE}/api/v1/infrastructure/worker/stop", timeout=30
    )
    if resp.status_code == 200:
        return resp.json()
    return {"error": f"Stop failed: {resp.text[:200]}"}


def _exec_get_cost_summary(args: dict) -> dict:
    """Get cost summary from the cost intelligence tracker."""
    try:
        resp = httpx.get(
            f"{API_BASE}/api/v1/infrastructure/cost/summary", timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    # Fallback: get worker status for session cost
    try:
        worker_resp = httpx.get(
            f"{API_BASE}/api/v1/infrastructure/worker/status", timeout=10
        )
        if worker_resp.status_code == 200:
            data = worker_resp.json()
            return {
                "current_session_cost": data.get("total_cost", 0),
                "hourly_rate": data.get("hourly_rate", 0),
                "gpu_name": data.get("gpu_name", "unknown"),
                "status": data.get("status", "no_session"),
                "note": "Full cost history endpoint not available — showing current session only",
            }
    except Exception as e:
        return {"error": f"Cost summary unavailable: {e}"}

    return {"error": "Cost intelligence service unavailable"}
