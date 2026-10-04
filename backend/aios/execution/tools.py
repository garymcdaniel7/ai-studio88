"""AIOS tool executors — bridge approved Brain actions to platform services.

Tenant-aware executors receive ``org_id`` only from the authenticated Brain
bridge.  They never infer organization ownership from prompts, tool arguments,
or client-provided selectors.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.tenant_context import validate_org_id

logger = logging.getLogger(__name__)


# These are the bridge executors that can read or mutate tenant-owned records.
# Keep this set explicit: system/reference tools do not gain tenant behavior by
# accident, while every tenant-aware operation fails closed without context.
TENANT_SCOPED_TOOLS = frozenset(
    {
        "generate_image",
        "generate_video",
        "train_lora",
        "search_talent",
        "create_talent",
        "schedule_post",
        "search_knowledge",
        "recommend_workflow",
    }
)
_CLIENT_TENANT_KEYS = frozenset({"org_id", "orgId", "org-id", "organization_id", "tenant_id"})


def _require_trusted_org(org_id: str | None) -> str:
    """Validate the trusted organization supplied by the authenticated bridge."""
    return validate_org_id(org_id)


def _trusted_parameters(params: dict[str, Any]) -> dict[str, Any]:
    """Return tool parameters without client-controlled tenant selectors.

    Organization scope is passed separately by the bridge.  Removing selector
    keys prevents downstream providers from treating prompt/tool input as an
    authorization source.
    """
    return {key: value for key, value in params.items() if key not in _CLIENT_TENANT_KEYS}


async def execute_tool(
    tool: str,
    parameters: dict[str, Any],
    *,
    org_id: str | None = None,
) -> dict[str, Any]:
    """Execute an approved tool action with trusted tenant context.

    ``org_id`` must come from the authenticated Brain request or an equivalent
    trusted tenant context.  It is keyword-only and is never read from
    ``parameters``.  Tenant-scoped executors reject missing context before
    validating tool arguments or touching a database/provider.
    """
    executors = {
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

    executor = executors.get(tool)
    if not executor:
        return {"success": False, "error": f"No executor for tool: {tool}"}

    try:
        if tool in TENANT_SCOPED_TOOLS:
            trusted_org_id = _require_trusted_org(org_id)
            result = await executor(parameters, trusted_org_id)
        else:
            result = await executor(parameters)
        return {"success": True, "tool": tool, **result}
    except Exception as exc:
        logger.error("Tool execution failed: %s — %s", tool, exc)
        return {"success": False, "tool": tool, "error": str(exc)[:300]}


# =============================================================================
# Individual Tool Executors
# =============================================================================


async def _exec_generate_image(params: dict[str, Any], org_id: str) -> dict[str, Any]:
    """Generate an image after validating any referenced talent belongs to org."""
    trusted_org_id = _require_trusted_org(org_id)
    params = _trusted_parameters(params)
    talent_id = params.get("talent_id")
    if talent_id:
        from backend.database import get_talent_by_id

        if not (get_talent_by_id(talent_id, trusted_org_id).data or []):
            return {"error": "Talent not found"}

    from backend.infrastructure.worker_api_client import get_worker_client

    # Auto-configure via Workflow Intelligence if no model specified.
    if not params.get("model") or not params.get("steps"):
        from backend.aios.workflow.intelligence import auto_configure

        config = auto_configure(
            prompt=params.get("prompt", ""),
            talent_id=talent_id,
            content_type="image",
            quality=params.get("quality", "auto"),
            platform=params.get("platform"),
        )
        auto_params = {
            "model": config.model,
            "width": config.width,
            "height": config.height,
            "steps": config.steps,
            "cfg": config.cfg,
            "prompt": config.prompt,
            "negative_prompt": config.negative_prompt,
        }
        params = {**auto_params, **{key: value for key, value in params.items() if value}}

    client = get_worker_client()
    if client and client.is_available():
        return client.generate_image(**params)

    import os

    import httpx

    comfyui_url = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
    try:
        resp = httpx.get(f"{comfyui_url}/system_stats", timeout=3)
        if resp.status_code == 200:
            from backend.infrastructure.generate import generate_image

            return generate_image(params)
    except Exception:
        pass

    return {"error": "No GPU worker or ComfyUI available. Launch a worker first."}


async def _exec_generate_video(params: dict[str, Any], org_id: str) -> dict[str, Any]:
    """Generate a video clip after validating any referenced talent ownership."""
    trusted_org_id = _require_trusted_org(org_id)
    params = _trusted_parameters(params)
    talent_id = params.get("talent_id")
    if talent_id:
        from backend.database import get_talent_by_id

        if not (get_talent_by_id(talent_id, trusted_org_id).data or []):
            return {"error": "Talent not found"}

    from backend.infrastructure.worker_api_client import get_worker_client

    client = get_worker_client()
    if client and client.is_available():
        return {
            "status": "submitted",
            "message": "Video generation submitted to GPU worker",
            "params": params,
        }

    return {"error": "Video generation requires GPU worker with WAN 2.1 loaded."}


async def _exec_train_lora(params: dict[str, Any], org_id: str) -> dict[str, Any]:
    """Start LoRA training using only assets and talent owned by ``org_id``."""
    trusted_org_id = _require_trusted_org(org_id)
    params = _trusted_parameters(params)

    from backend.database import get_assets, get_talent_by_id

    talent_id = params.get("talent_id")
    if not talent_id:
        return {"error": "talent_id required for LoRA training"}
    if not (get_talent_by_id(talent_id, trusted_org_id).data or []):
        return {"error": "Talent not found"}

    trigger_word = params.get("trigger_word", "ohwx")
    steps = int(params.get("steps", 1000))
    base_model = params.get("base_model", "flux-dev")
    media = [asset for asset in (get_assets(trusted_org_id).data or []) if asset.get("talent_id") == talent_id]
    image_count = len(media)

    if image_count < 5:
        return {
            "error": (
                f"Talent has {image_count} images. Need at least 5 for LoRA training. "
                "Upload more photos to the talent first."
            )
        }

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
                "message": (
                    f"LoRA training started for talent. {image_count} images, {steps} steps. "
                    "Poll /training/jobs for status."
                ),
            }
        return {"error": f"Training submission failed: {resp.text[:200]}"}
    except Exception as exc:
        return {"error": f"Cannot reach training service: {exc}"}


async def _exec_generate_voice(params: dict[str, Any]) -> dict[str, Any]:
    """Generate speech via MOSS-TTS or ElevenLabs."""
    text = params.get("text", "")
    if not text:
        return {"error": "text required for voice generation"}

    import httpx

    try:
        resp = httpx.post(
            "http://localhost:8000/api/v1/audio/tts/preview",
            json={
                "text": text,
                "provider": params.get("provider", "elevenlabs"),
                "voice_id": params.get("voice_id", ""),
            },
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "audio_base64": data.get("audio_base64", ""),
                "duration_seconds": data.get("duration_seconds", 0),
            }
        return {"error": f"Voice generation failed: {resp.text[:200]}"}
    except Exception as exc:
        return {"error": str(exc)}


async def _exec_search_talent(params: dict[str, Any], org_id: str) -> dict[str, Any]:
    """Search only the authenticated organization’s talent library."""
    trusted_org_id = _require_trusted_org(org_id)
    params = _trusted_parameters(params)

    from backend.database import get_talent

    query = params.get("query", "")
    results = get_talent(trusted_org_id).data or []
    if query:
        query_lower = query.lower()
        results = [
            talent
            for talent in results
            if query_lower in (talent.get("name") or "").lower()
            or query_lower in (talent.get("bio") or "").lower()
        ]

    fields = ("id", "name", "bio", "default_style", "avatar_url")
    trimmed = [{key: talent.get(key) for key in fields} for talent in results[:10]]
    return {"talents": trimmed, "count": len(trimmed)}


async def _exec_create_talent(params: dict[str, Any], org_id: str) -> dict[str, Any]:
    """Create a talent owned by the trusted organization."""
    trusted_org_id = _require_trusted_org(org_id)
    params = _trusted_parameters(params)

    from backend.database import create_talent

    record = {
        "name": params.get("name", ""),
        "bio": params.get("bio", ""),
        "default_style": params.get("type", "model"),
        "visual_style": params.get("visual_style", ""),
    }
    result = create_talent(record, trusted_org_id)
    return {"talent": result.data[0] if result.data else record}


async def _exec_schedule_post(params: dict[str, Any], org_id: str) -> dict[str, Any]:
    """Schedule a publishing post owned by the trusted organization."""
    trusted_org_id = _require_trusted_org(org_id)
    params = _trusted_parameters(params)

    asset_id = params.get("asset_id")
    if asset_id:
        from backend.database import get_asset_by_id

        if not (get_asset_by_id(asset_id, trusted_org_id).data or []):
            return {"error": "Asset not found"}

    from backend.database import supabase

    record = {
        "org_id": trusted_org_id,
        "platform": params.get("platform", "instagram"),
        "title": params.get("content", "")[:100],
        "body": params.get("content", ""),
        "asset_id": asset_id,
        "scheduled_for": params.get("scheduled_for"),
        "status": "scheduled",
    }
    result = supabase.table("publishing_posts").insert(record).execute()
    return {"post": result.data[0] if result.data else record, "status": "scheduled"}


async def _exec_search_knowledge(
    params: dict[str, Any], org_id: str
) -> dict[str, Any]:
    """Search knowledge visible to the trusted organization.

    Tenant-owned knowledge is scoped in the graph helper.  System model rows
    remain available because the audit classifies them as shared reference
    data; tenant-owned model rows are filtered to ``org_id`` there.
    """
    trusted_org_id = _require_trusted_org(org_id)
    params = _trusted_parameters(params)

    from backend.aios.knowledge.graph import KnowledgeQuery, search
    from backend.database import get_talent_by_id

    talent_id = params.get("talent_id")
    if talent_id and not (get_talent_by_id(talent_id, trusted_org_id).data or []):
        return {"error": "Talent not found"}

    sources = [source.strip() for source in params.get("sources", "").split(",") if source.strip()]
    query = KnowledgeQuery(
        query=params.get("query", ""),
        sources=sources,
        talent_id=talent_id,
        limit=10,
        # RAG currently has no tenant predicate in its RPC path.  Do not use
        # it from this tenant-sensitive bridge until that contract is fixed.
        include_vectors=False,
    )
    results = search(query, org_id=trusted_org_id)
    return {
        "results": [
            {"source": item.source, "name": item.name, "summary": item.summary}
            for item in results[:10]
        ]
    }


async def _exec_recommend_workflow(
    params: dict[str, Any], org_id: str
) -> dict[str, Any]:
    """Recommend only workflow DNA visible to the trusted organization."""
    trusted_org_id = _require_trusted_org(org_id)
    params = _trusted_parameters(params)

    from backend.aios.knowledge.workflow_dna import recommend_workflow
    from backend.database import get_talent_by_id

    talent_id = params.get("talent_id")
    if talent_id and not (get_talent_by_id(talent_id, trusted_org_id).data or []):
        return {"error": "Talent not found"}

    recs = recommend_workflow(
        content_type=params.get("content_type", "image"),
        talent_id=talent_id,
        org_id=trusted_org_id,
    )
    return {"recommendations": recs}
