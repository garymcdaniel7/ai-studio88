"""Authenticated MCP adapters for WRITE story and storyboard operations."""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.aios.mcp.phase2_common import (
    MCPExecutionContext,
    MCPToolError,
    parse_uuid,
    reject_org_selectors,
    require_role,
    safe_record,
)
from backend.story_engine.repository import StoryRepository
from backend.story_engine.schemas import (
    EpisodeCreate,
    SceneCreate,
    ShotCreate,
    ShotWriteUpdate,
)
from backend.story_engine.service import StoryService

_ALLOWED_REFERENCE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _validated(model: Any, params: dict[str, Any], excluded: set[str]) -> Any:
    """Validate a strict story payload and map Pydantic errors to MCP errors."""
    payload = {key: value for key, value in params.items() if key not in excluded}
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise MCPToolError("Story input failed validation", "INVALID_INPUT", 422) from exc


def _service() -> StoryService:
    """Build the existing story service without duplicating repository queries."""
    return StoryService(StoryRepository())


async def _call(operation: Any) -> Any:
    """Run the existing synchronous story service off the event loop."""
    return await asyncio.to_thread(operation)


async def create_episode(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Create an episode under an authenticated tenant's universe."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    universe_id = parse_uuid(params.get("universe_id"), "universe_id")
    data = _validated(EpisodeCreate, params, {"universe_id", "idempotency_key"})
    result = await _call(lambda: _service().create_episode(universe_id, data, context.org_id))
    return {"status": "created", "episode": safe_record(result), "org_id": context.org_id}


async def create_scene(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Create a scene under an authenticated tenant's episode."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    episode_id = parse_uuid(params.get("episode_id"), "episode_id")
    data = _validated(SceneCreate, params, {"episode_id", "idempotency_key"})
    result = await _call(lambda: _service().create_scene(episode_id, data, context.org_id))
    return {"status": "created", "scene": safe_record(result), "org_id": context.org_id}


async def create_shot(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Create a shot under an authenticated tenant's scene."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    scene_id = parse_uuid(params.get("scene_id"), "scene_id")
    data = _validated(ShotCreate, params, {"scene_id", "idempotency_key"})
    result = await _call(lambda: _service().create_shot(scene_id, data, context.org_id))
    return {"status": "created", "shot": safe_record(result), "org_id": context.org_id}


async def update_shot_prompt(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Persist WRITE prompt/context fields using the story service's ownership checks."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    shot_id = parse_uuid(params.get("shot_id"), "shot_id")
    data = _validated(ShotWriteUpdate, params, {"shot_id", "idempotency_key"})
    result = await _call(lambda: _service().update_shot_write(shot_id, data, context.org_id))
    return {"status": "updated", "shot": safe_record(result), "org_id": context.org_id}


async def list_episodes(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """List episodes for one authenticated tenant's universe."""
    reject_org_selectors(params)
    universe_id = parse_uuid(params.get("universe_id"), "universe_id")
    limit = min(max(int(params.get("limit", 20)), 1), 100)
    offset = max(int(params.get("offset", 0)), 0)
    items, total = await _call(lambda: _service().list_episodes(universe_id, context.org_id, limit, offset))
    return {"items": [safe_record(item) for item in items], "total": total, "limit": limit, "offset": offset}


async def get_storyboard(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Read an episode storyboard through tenant-scoped story service methods."""
    reject_org_selectors(params)
    service = _service()
    episode_id = params.get("episode_id")
    if episode_id is not None:
        episode_id = parse_uuid(episode_id, "episode_id")
        episode = await _call(lambda: service.get_episode(episode_id, context.org_id))
        scenes, _ = await _call(lambda: service.list_scenes(episode_id, context.org_id, 100, 0))
        scene_rows = []
        for scene in scenes:
            scene_id = parse_uuid(scene["id"], "scene_id")
            shots, _ = await _call(lambda: service.list_shots(scene_id, context.org_id, 100, 0))
            scene_rows.append({**safe_record(scene), "shots": [safe_record(shot) for shot in shots]})
        return {"episode": safe_record(episode), "scenes": scene_rows, "org_id": context.org_id}

    universe_id = parse_uuid(params.get("universe_id"), "universe_id")
    episodes, _ = await _call(lambda: service.list_episodes(universe_id, context.org_id, 100, 0))
    return {
        "episodes": [safe_record(episode) for episode in episodes],
        "org_id": context.org_id,
    }


async def upload_shot_reference(params: dict[str, Any], context: MCPExecutionContext) -> dict[str, Any]:
    """Return a short-lived signed B2 upload URL for a tenant-owned shot reference."""
    reject_org_selectors(params)
    require_role(context, "owner", "admin", "editor")
    shot_id = parse_uuid(params.get("shot_id"), "shot_id")
    content_type = str(params.get("content_type", ""))
    if content_type not in _ALLOWED_REFERENCE_TYPES:
        raise MCPToolError("Unsupported reference MIME type", "INVALID_CONTENT_TYPE", 422)
    filename = str(params.get("filename", "reference"))
    filename = _FILENAME_RE.sub("_", Path(filename).name)[:160]
    if not filename:
        raise MCPToolError("filename is required", "INVALID_INPUT", 422)
    # Prove ownership through the existing story service before touching B2.
    await _call(lambda: _service().repository.get_shot(shot_id, context.org_id))

    try:
        from backend import storage

        talent_id = parse_uuid(params["talent_id"], "talent_id") if params.get("talent_id") else "story"
        key = f"/{context.org_id}/images/{talent_id}/{shot_id}/{uuid.uuid4().hex}_{filename}"
        client = storage._get_client()  # noqa: SLF001 - storage owns provider configuration
        upload_url = client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": storage.B2_BUCKET_NAME,
                "Key": key.lstrip("/"),
                "ContentType": content_type,
                "Metadata": {
                    "org_id": context.org_id,
                    "job_id": shot_id,
                    "content_type": content_type,
                },
            },
            ExpiresIn=900,
            HttpMethod="PUT",
        )
    except MCPToolError:
        raise
    except Exception as exc:
        raise MCPToolError("Reference upload service unavailable", "STORAGE_UNAVAILABLE", 503) from exc

    return {
        "status": "upload_url_ready",
        "shot_id": shot_id,
        "storage_key": key,
        "upload_url": upload_url,
        "expires_in_seconds": 900,
        "content_type": content_type,
        "validation": {"max_size_bytes": 100 * 1024 * 1024, "allowed_content_types": sorted(_ALLOWED_REFERENCE_TYPES)},
        "org_id": context.org_id,
    }
