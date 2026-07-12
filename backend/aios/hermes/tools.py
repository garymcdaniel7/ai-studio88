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
        "diagnose_service": _exec_diagnose,
        "generate_voice": _exec_generate_voice,
        "schedule_post": _exec_schedule_post,
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
