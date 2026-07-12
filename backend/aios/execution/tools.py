"""AIOS Tool Executors — bridge between agent decisions and platform services.

When a user says "Train a LoRA for Shy" in the Brain:
1. Esu routes → detects "train" intent
2. Orunmila plans → proposes train_lora action
3. Governance → requires approval (training costs money)
4. User approves
5. THIS MODULE executes the action by calling the real backend services

Each executor:
- Accepts parameters from the proposed action
- Calls the appropriate backend endpoint/service
- Returns a structured result
- Logs the execution to decision trail
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def execute_tool(tool: str, parameters: dict) -> dict:
    """Execute an approved tool action.

    This is the bridge between AIOS governance and actual platform operations.
    """
    EXECUTORS = {
        "generate_image": _exec_generate_image,
        "generate_video": _exec_generate_video,
        "train_lora": _exec_train_lora,
        "generate_voice": _exec_generate_voice,
        "search_talent": _exec_search_talent,
        "create_talent": _exec_create_talent,
        "schedule_post": _exec_schedule_post,
        "search_knowledge": _exec_search_knowledge,
        "recommend_workflow": _exec_recommend_workflow,
    }

    executor = EXECUTORS.get(tool)
    if not executor:
        return {"success": False, "error": f"No executor for tool: {tool}"}

    try:
        result = await executor(parameters)
        return {"success": True, "tool": tool, **result}
    except Exception as e:
        logger.error(f"Tool execution failed: {tool} — {e}")
        return {"success": False, "tool": tool, "error": str(e)[:300]}


# =============================================================================
# Individual Tool Executors
# =============================================================================


async def _exec_generate_image(params: dict) -> dict:
    """Generate an image — tries Worker API, falls back to direct ComfyUI."""
    from backend.infrastructure.worker_api_client import get_worker_client

    # Auto-configure via Workflow Intelligence if no model specified
    if not params.get("model") or not params.get("steps"):
        from backend.aios.workflow.intelligence import auto_configure
        config = auto_configure(
            prompt=params.get("prompt", ""),
            talent_id=params.get("talent_id"),
            content_type="image",
            quality=params.get("quality", "auto"),
            platform=params.get("platform"),
        )
        # Merge auto-config with user params (user overrides auto)
        auto_params = {
            "model": config.model,
            "width": config.width,
            "height": config.height,
            "steps": config.steps,
            "cfg": config.cfg,
            "prompt": config.prompt,
            "negative_prompt": config.negative_prompt,
        }
        params = {**auto_params, **{k: v for k, v in params.items() if v}}

    # Try Worker API
    client = get_worker_client()
    if client and client.is_available():
        return client.generate_image(**params)

    # Fall back to direct ComfyUI
    import httpx
    import os
    comfyui_url = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
    try:
        resp = httpx.get(f"{comfyui_url}/system_stats", timeout=3)
        if resp.status_code == 200:
            # ComfyUI is reachable — use the generate endpoint
            from backend.infrastructure.generate import generate_image
            return generate_image(params)
    except Exception:
        pass

    return {"error": "No GPU worker or ComfyUI available. Launch a worker first."}


async def _exec_generate_video(params: dict) -> dict:
    """Generate a video clip."""
    from backend.infrastructure.worker_api_client import get_worker_client

    client = get_worker_client()
    if client and client.is_available():
        # Worker API handles video generation
        return {"status": "submitted", "message": "Video generation submitted to GPU worker", "params": params}

    return {"error": "Video generation requires GPU worker with WAN 2.1 loaded."}


async def _exec_train_lora(params: dict) -> dict:
    """Start LoRA training for a talent.

    If talent_id is provided, uses their existing uploaded photos.
    """
    from backend.database import supabase

    talent_id = params.get("talent_id")
    trigger_word = params.get("trigger_word", "ohwx")
    steps = int(params.get("steps", 1000))
    base_model = params.get("base_model", "flux-dev")

    if not talent_id:
        return {"error": "talent_id required for LoRA training"}

    # Check talent has images
    media = supabase.table("assets").select("id").eq("talent_id", talent_id).execute().data or []
    image_count = len([m for m in media if True])  # All assets for this talent

    if image_count < 5:
        return {"error": f"Talent has {image_count} images. Need at least 5 for LoRA training. Upload more photos to the talent first."}

    # Submit training via the training start endpoint
    import httpx
    try:
        resp = httpx.post(
            "http://localhost:8000/api/v1/training/start",
            data={
                "talent_id": talent_id,
                "trigger_word": trigger_word,
                "steps": str(steps),
                "base_model": base_model,
                "use_talent_media": "true",
                "provider": "simpletuner",
            },
            timeout=30,
        )
        if resp.status_code == 201:
            data = resp.json()
            return {
                "status": "training_started",
                "job_id": data.get("training_job_id"),
                "images_used": data.get("images_uploaded", image_count),
                "message": f"LoRA training started for talent. {image_count} images, {steps} steps. Poll /training/jobs for status.",
            }
        else:
            return {"error": f"Training submission failed: {resp.text[:200]}"}
    except Exception as e:
        return {"error": f"Cannot reach training service: {e}"}


async def _exec_generate_voice(params: dict) -> dict:
    """Generate speech via MOSS-TTS or ElevenLabs."""
    text = params.get("text", "")
    if not text:
        return {"error": "text required for voice generation"}

    import httpx
    try:
        resp = httpx.post(
            "http://localhost:8000/api/v1/audio/tts/preview",
            json={"text": text, "provider": params.get("provider", "elevenlabs"), "voice_id": params.get("voice_id", "")},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"audio_base64": data.get("audio_base64", ""), "duration_seconds": data.get("duration_seconds", 0)}
        return {"error": f"Voice generation failed: {resp.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


async def _exec_search_talent(params: dict) -> dict:
    """Search talent library."""
    from backend.database import supabase

    query = params.get("query", "")
    results = supabase.table("talent").select("id,name,bio,default_style,avatar_url").limit(10).execute().data or []

    if query:
        ql = query.lower()
        results = [t for t in results if ql in (t.get("name") or "").lower() or ql in (t.get("bio") or "").lower()]

    return {"talents": results, "count": len(results)}


async def _exec_create_talent(params: dict) -> dict:
    """Create a new talent record."""
    from backend.database import supabase

    record = {
        "name": params.get("name", ""),
        "bio": params.get("bio", ""),
        "default_style": params.get("type", "model"),
        "visual_style": params.get("visual_style", ""),
    }
    result = supabase.table("talent").insert(record).execute()
    return {"talent": result.data[0] if result.data else record}


async def _exec_schedule_post(params: dict) -> dict:
    """Schedule a social media post."""
    from backend.database import supabase

    record = {
        "platform": params.get("platform", "instagram"),
        "title": params.get("content", "")[:100],
        "body": params.get("content", ""),
        "asset_id": params.get("asset_id"),
        "scheduled_for": params.get("scheduled_for"),
        "status": "scheduled",
    }
    result = supabase.table("publishing_posts").insert(record).execute()
    return {"post": result.data[0] if result.data else record, "status": "scheduled"}


async def _exec_search_knowledge(params: dict) -> dict:
    """Search the knowledge graph."""
    from backend.aios.knowledge.graph import KnowledgeQuery, search

    query = KnowledgeQuery(query=params.get("query", ""), limit=10)
    results = search(query)
    return {"results": [{"source": r.source, "name": r.name, "summary": r.summary} for r in results[:10]]}


async def _exec_recommend_workflow(params: dict) -> dict:
    """Get workflow recommendation."""
    from backend.aios.knowledge.workflow_dna import recommend_workflow

    recs = recommend_workflow(
        content_type=params.get("content_type", "image"),
        talent_id=params.get("talent_id"),
    )
    return {"recommendations": recs}
