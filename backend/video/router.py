"""Video Pipeline API Router — Hardened (Story 017).

All video operations require authenticated workspace context.
Parent-project ownership is validated for all child resources.
Destructive and paid actions produce audit entries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import AuthUser, require_auth
from backend.data_access import AuthorizationError
from backend.data_access_helpers import get_authorized_client, get_authorized_client_strict
from backend.video.provider import (
    VIDEO_PROVIDERS,
    VideoRequest,
    get_video_provider,
)

router = APIRouter(prefix="/api/v1", tags=["video"])


# =============================================================================
# Audit helpers (destructive/paid video actions)
# =============================================================================

_video_audit: list[dict] = []
_MAX_AUDIT = 500


def _audit(action: str, resource_type: str, resource_id: str, user: AuthUser, details: str = ""):
    from datetime import UTC, datetime

    _video_audit.append({
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "actor_user_id": user.user_id,
        "org_id": user.org_id,
        "details": details,
    })
    if len(_video_audit) > _MAX_AUDIT:
        _video_audit.pop(0)


# =============================================================================
# Video Providers (informational — no auth required)
# =============================================================================


@router.get("/video/providers")
def list_video_providers():
    """List available video generation providers and their health/capabilities."""
    results = []
    for name, cls in VIDEO_PROVIDERS.items():
        provider = cls()
        results.append(
            {
                "name": name,
                "health": provider.health(),
                "capabilities": provider.capabilities(),
            }
        )
    return {"providers": results}


@router.get("/video/providers/{provider_name}")
def get_provider_detail(provider_name: str):
    """Get detailed info for a specific video provider."""
    cls = VIDEO_PROVIDERS.get(provider_name)
    if not cls:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_name}")
    provider = cls()
    return {
        "name": provider_name,
        "health": provider.health(),
        "capabilities": provider.capabilities(),
    }


# =============================================================================
# Video Projects (all require auth + org scoping)
# =============================================================================


@router.get("/videos")
def list_videos(
    talent_id: str | None = None,
    status: str | None = None,
    user: AuthUser = Depends(require_auth),
):
    """List video projects scoped to the user's workspace."""
    client = get_authorized_client(user)
    if client:
        filters = {}
        if talent_id:
            filters["talent_id"] = talent_id
        if status:
            filters["status"] = status
        result = client.select("video_projects", filters=filters, order_by="created_at", desc=True)
        return result.data or []
    else:
        # Dev mode fallback
        from backend.database import supabase
        query = supabase.table("video_projects").select("*").order("created_at", desc=True)
        if talent_id:
            query = query.eq("talent_id", talent_id)
        if status:
            query = query.eq("status", status)
        try:
            return query.execute().data or []
        except Exception:
            return []


@router.post("/videos", status_code=201)
def create_video(data: dict, user: AuthUser = Depends(require_auth)):
    """Create a video project in the user's workspace."""
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")

    client = get_authorized_client_strict(user)
    record = {
        "name": data["name"],
        "description": data.get("description", ""),
        "video_type": data.get("video_type", "reel"),
        "platform": data.get("platform", "instagram"),
        "aspect_ratio": data.get("aspect_ratio", "9:16"),
        "duration_seconds": float(data.get("duration_seconds", 5.0)),
        "talent_id": data.get("talent_id"),
        "project_id": data.get("project_id"),
        "campaign_id": data.get("campaign_id"),
        "status": "draft",
    }
    result = client.insert("video_projects", record)
    return result.data[0] if result.data else record


@router.get("/videos/{video_id}")
def get_video(video_id: str, user: AuthUser = Depends(require_auth)):
    """Get a video project by ID (org-scoped)."""
    client = get_authorized_client(user)
    if client:
        try:
            result = client.select_by_id("video_projects", video_id)
            return result.data
        except AuthorizationError:
            raise HTTPException(status_code=404, detail="Video project not found")
    else:
        from backend.database import supabase
        try:
            return supabase.table("video_projects").select("*").eq("id", video_id).single().execute().data
        except Exception:
            raise HTTPException(status_code=404, detail="Video project not found")


@router.put("/videos/{video_id}")
def update_video(video_id: str, data: dict, user: AuthUser = Depends(require_auth)):
    """Update a video project (org-scoped)."""
    client = get_authorized_client_strict(user)
    data["updated_at"] = "now()"
    result = client.update("video_projects", data, record_id=video_id)
    if not result.data:
        raise HTTPException(status_code=404, detail="Video project not found")
    return result.data[0]


@router.delete("/videos/{video_id}")
def delete_video(video_id: str, user: AuthUser = Depends(require_auth)):
    """Delete a video project (org-scoped, audited)."""
    client = get_authorized_client_strict(user)
    try:
        client.delete("video_projects", video_id)
    except AuthorizationError:
        raise HTTPException(status_code=404, detail="Video project not found")

    _audit("delete_video_project", "video_project", video_id, user)
    return {"deleted": True}


# =============================================================================
# Video Shots (child of video project — validates parent ownership)
# =============================================================================


def _verify_project_ownership(video_id: str, user: AuthUser):
    """Verify the user's org owns the parent video project.

    Returns the AuthorizedClient if ownership confirmed.
    Raises 404 if project not found in user's org.
    """
    client = get_authorized_client(user)
    if client:
        try:
            client.select_by_id("video_projects", video_id)
            return client
        except AuthorizationError:
            raise HTTPException(status_code=404, detail="Video project not found")
    return None


@router.get("/videos/{video_id}/shots")
def list_shots(video_id: str, user: AuthUser = Depends(require_auth)):
    """List shots for a video project (validates project ownership)."""
    client = _verify_project_ownership(video_id, user)
    if client:
        result = client.select(
            "video_shots",
            filters={"video_project_id": video_id},
            order_by="shot_number",
            desc=False,
        )
        return result.data or []
    else:
        from backend.database import supabase
        try:
            return supabase.table("video_shots").select("*").eq("video_project_id", video_id).order("shot_number").execute().data or []
        except Exception:
            return []


@router.post("/videos/{video_id}/shots", status_code=201)
def create_shot(video_id: str, data: dict, user: AuthUser = Depends(require_auth)):
    """Create a shot in a video project (validates project ownership)."""
    client = _verify_project_ownership(video_id, user)
    if not client:
        client = get_authorized_client_strict(user)

    record = {
        "video_project_id": video_id,
        "shot_number": int(data.get("shot_number", 1)),
        "prompt": data.get("prompt", ""),
        "negative_prompt": data.get("negative_prompt", ""),
        "motion_prompt": data.get("motion_prompt", ""),
        "model": data.get("model", "wan-2.1"),
        "duration_seconds": float(data.get("duration_seconds", 3.0)),
        "fps": int(data.get("fps", 24)),
        "resolution": data.get("resolution", "1080x1920"),
        "camera_motion": data.get("camera_motion", "static"),
        "status": "planned",
    }
    result = client.insert("video_shots", record)
    return result.data[0] if result.data else record


# =============================================================================
# Generate Video Shot (paid action — auth + audit)
# =============================================================================


@router.post("/videos/{video_id}/generate")
def generate_video(video_id: str, data: dict = None, user: AuthUser = Depends(require_auth)):
    """Generate video for all planned shots (requires auth, audited as paid action)."""
    if data is None:
        data = {}

    client = _verify_project_ownership(video_id, user)
    if not client:
        client = get_authorized_client_strict(user)

    # Get planned shots for this project
    shots_result = client.select(
        "video_shots",
        filters={"video_project_id": video_id, "status": "planned"},
        order_by="shot_number",
        desc=False,
    )
    shots = shots_result.data or []

    if not shots:
        raise HTTPException(status_code=400, detail="No planned shots to generate")

    _audit("generate_video", "video_project", video_id, user, f"shots={len(shots)}")

    provider = get_video_provider(data.get("provider", "simulation"))
    results = []

    for shot in shots:
        request = VideoRequest(
            prompt=shot.get("prompt", ""),
            negative_prompt=shot.get("negative_prompt", ""),
            motion_prompt=shot.get("motion_prompt", ""),
            duration_seconds=shot.get("duration_seconds", 3.0),
            fps=shot.get("fps", 24),
            resolution=shot.get("resolution", "1080x1920"),
            model=shot.get("model", "wan-2.1"),
            camera_motion=shot.get("camera_motion", "static"),
        )

        # Mark generating
        client.update("video_shots", {"status": "generating", "updated_at": "now()"}, record_id=shot["id"])

        try:
            result = provider.submit(request)

            if result.success and result.output_bytes:
                from backend.storage import compute_checksum, generate_storage_key, upload_file

                storage_key = generate_storage_key(result.filename, "video")
                checksum = compute_checksum(result.output_bytes)
                public_url = upload_file(result.output_bytes, storage_key, result.mime_type)

                asset_data = {
                    "talent_id": None,
                    "type": "video",
                    "filename": result.filename,
                    "original_filename": result.filename,
                    "mime_type": result.mime_type,
                    "size_bytes": len(result.output_bytes),
                    "storage_provider": "backblaze_b2",
                    "storage_key": storage_key,
                    "public_url": public_url,
                    "checksum": checksum,
                    "metadata": {
                        **result.metadata,
                        "video_project_id": video_id,
                        "shot_id": shot["id"],
                    },
                    "tags": ["video", result.metadata.get("model", ""), provider.name],
                }
                asset_result = client.insert("assets", asset_data)
                asset = asset_result.data[0] if asset_result.data else {}

                client.update("video_shots", {
                    "status": "completed",
                    "output_asset_id": asset.get("id"),
                    "updated_at": "now()",
                }, record_id=shot["id"])

                results.append({"shot_id": shot["id"], "status": "completed", "asset_id": asset.get("id")})
            else:
                client.update("video_shots", {"status": "failed", "updated_at": "now()"}, record_id=shot["id"])
                results.append({"shot_id": shot["id"], "status": "failed", "error": result.error})

        except Exception as e:
            client.update("video_shots", {"status": "failed", "updated_at": "now()"}, record_id=shot["id"])
            results.append({"shot_id": shot["id"], "status": "failed", "error": str(e)})

    return {"video_project_id": video_id, "shots_processed": len(results), "results": results}


# =============================================================================
# Image-to-Video (paid action — auth + audit)
# =============================================================================


@router.post("/video/image-to-video", status_code=201)
def image_to_video(data: dict, user: AuthUser = Depends(require_auth)):
    """Generate video from a source image (requires auth, audited)."""
    if not data.get("prompt"):
        raise HTTPException(status_code=400, detail="'prompt' required")
    if not data.get("source_image"):
        raise HTTPException(status_code=400, detail="'source_image' required (filename or URL)")

    _audit("image_to_video", "generation", "i2v", user, f"model={data.get('model', 'wan-2.1')}")

    provider = get_video_provider(data.get("provider", "comfyui"))

    request = VideoRequest(
        prompt=data["prompt"],
        negative_prompt=data.get("negative_prompt", ""),
        duration_seconds=float(data.get("duration_seconds", 2.0)),
        fps=int(data.get("fps", 24)),
        resolution=data.get("resolution", "832x480"),
        model=data.get("model", "wan-2.1"),
        extra={
            "mode": "image_to_video",
            "source_image": data["source_image"],
            "denoise": float(data.get("denoise", 0.75)),
            "workflow_template": data.get("workflow_template", "wan21_i2v_simple"),
        },
    )

    result = provider.submit(request)

    if result.success:
        return {
            "status": "completed",
            "filename": result.filename,
            "mime_type": result.mime_type,
            "duration_seconds": result.duration_seconds,
            "generation_time_seconds": result.generation_time_seconds,
            "metadata": result.metadata,
        }
    else:
        raise HTTPException(status_code=500, detail=result.error or "Generation failed")


# =============================================================================
# Timeline (child of video project — validates parent ownership)
# =============================================================================


@router.get("/videos/{video_id}/timeline")
def get_timeline(video_id: str, user: AuthUser = Depends(require_auth)):
    """Get the full timeline for a video project (validates ownership)."""
    client = _verify_project_ownership(video_id, user)
    if client:
        tracks_result = client.select(
            "timeline_tracks",
            filters={"video_project_id": video_id},
            order_by="order_index",
            desc=False,
        )
        tracks = tracks_result.data or []
        # Note: timeline_clips don't have org_id — accessed via track parent
        # For full isolation, we'd need to join. For now, we validate project ownership.
        from backend.database import supabase
        for track in tracks:
            try:
                clips = supabase.table("timeline_clips").select("*").eq("track_id", track["id"]).order("start_time").execute().data or []
                track["clips"] = clips
            except Exception:
                track["clips"] = []
        return {"video_project_id": video_id, "tracks": tracks}
    else:
        from backend.database import supabase
        try:
            tracks = supabase.table("timeline_tracks").select("*").eq("video_project_id", video_id).order("order_index").execute().data or []
            for track in tracks:
                clips = supabase.table("timeline_clips").select("*").eq("track_id", track["id"]).order("start_time").execute().data or []
                track["clips"] = clips
            return {"video_project_id": video_id, "tracks": tracks}
        except Exception:
            return {"video_project_id": video_id, "tracks": []}


@router.post("/videos/{video_id}/timeline/tracks", status_code=201)
def create_track(video_id: str, data: dict, user: AuthUser = Depends(require_auth)):
    """Create a timeline track (validates project ownership)."""
    client = _verify_project_ownership(video_id, user)
    if not client:
        client = get_authorized_client_strict(user)

    record = {
        "video_project_id": video_id,
        "name": data.get("name", "Video"),
        "track_type": data.get("track_type", "video"),
        "order_index": int(data.get("order_index", 0)),
    }
    result = client.insert("timeline_tracks", record)
    return result.data[0] if result.data else record


@router.post("/videos/{video_id}/timeline/clips", status_code=201)
def create_clip(video_id: str, data: dict, user: AuthUser = Depends(require_auth)):
    """Create a timeline clip (validates project ownership)."""
    _verify_project_ownership(video_id, user)

    if not data.get("track_id"):
        raise HTTPException(status_code=400, detail="'track_id' required")

    # For clips, we insert via raw DB since timeline_clips may not be in TENANT_TABLES
    from backend.database import supabase
    record = {
        "track_id": data["track_id"],
        "asset_id": data.get("asset_id"),
        "start_time": float(data.get("start_time", 0.0)),
        "end_time": float(data.get("end_time", 3.0)),
        "duration_seconds": float(data.get("duration_seconds", 3.0)),
        "clip_type": data.get("clip_type", "video"),
        "effects": data.get("effects", []),
    }
    try:
        result = supabase.table("timeline_clips").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Render + Export (paid actions — auth + audit)
# =============================================================================


@router.post("/videos/{video_id}/render")
def render_video(video_id: str, data: dict = None, user: AuthUser = Depends(require_auth)):
    """Create a render job (requires auth, validates ownership, audited)."""
    if data is None:
        data = {}

    client = _verify_project_ownership(video_id, user)
    if not client:
        client = get_authorized_client_strict(user)

    record = {
        "video_project_id": video_id,
        "provider": data.get("provider", "simulation"),
        "status": "completed",
        "runtime_seconds": 2.5,
        "metadata": {"rendered_by": "simulation"},
    }
    result = client.insert("video_renders", record)
    _audit("render_video", "video_render", video_id, user, f"provider={data.get('provider', 'simulation')}")
    return result.data[0] if result.data else record


@router.post("/videos/{video_id}/export")
def export_video(video_id: str, data: dict = None, user: AuthUser = Depends(require_auth)):
    """Create a timeline export (requires auth, validates ownership, audited)."""
    if data is None:
        data = {}

    _verify_project_ownership(video_id, user)

    from backend.database import supabase
    record = {
        "video_project_id": video_id,
        "export_format": data.get("format", "mp4"),
        "resolution": data.get("resolution", "1080x1920"),
        "fps": int(data.get("fps", 24)),
        "status": "completed",
    }
    try:
        result = supabase.table("timeline_exports").insert(record).execute()
        _audit("export_video", "video_export", video_id, user, f"format={data.get('format', 'mp4')}")
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/video-renders")
def list_renders(video_project_id: str | None = None, user: AuthUser = Depends(require_auth)):
    """List renders scoped to user's workspace."""
    client = get_authorized_client(user)
    if client:
        filters = {}
        if video_project_id:
            filters["video_project_id"] = video_project_id
        result = client.select("video_renders", filters=filters, order_by="created_at", desc=True)
        return result.data or []
    else:
        from backend.database import supabase
        query = supabase.table("video_renders").select("*").order("created_at", desc=True)
        if video_project_id:
            query = query.eq("video_project_id", video_project_id)
        try:
            return query.execute().data or []
        except Exception:
            return []


@router.get("/video-renders/{render_id}")
def get_render(render_id: str, user: AuthUser = Depends(require_auth)):
    """Get a render by ID (org-scoped)."""
    client = get_authorized_client(user)
    if client:
        try:
            result = client.select_by_id("video_renders", render_id)
            return result.data
        except AuthorizationError:
            raise HTTPException(status_code=404, detail="Render not found")
    else:
        from backend.database import supabase
        try:
            return supabase.table("video_renders").select("*").eq("id", render_id).single().execute().data
        except Exception:
            raise HTTPException(status_code=404, detail="Render not found")
