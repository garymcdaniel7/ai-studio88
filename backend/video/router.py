"""Video Pipeline API Router.

Manages video projects, shots, renders, timelines, and exports.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException

from backend.video.provider import (
    get_video_provider, get_editing_provider, VideoRequest,
    VIDEO_PROVIDERS,
)

router = APIRouter(prefix="/api/v1", tags=["video"])


def _db():
    from backend.database import supabase
    return supabase


# =============================================================================
# Video Providers
# =============================================================================

@router.get("/video/providers")
def list_video_providers():
    """List available video generation providers and their health/capabilities."""
    results = []
    for name, cls in VIDEO_PROVIDERS.items():
        provider = cls()
        results.append({
            "name": name,
            "health": provider.health(),
            "capabilities": provider.capabilities(),
        })
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
# Video Projects
# =============================================================================

@router.get("/videos")
def list_videos(talent_id: Optional[str] = None, status: Optional[str] = None):
    query = _db().table("video_projects").select("*").order("created_at", desc=True)
    if talent_id: query = query.eq("talent_id", talent_id)
    if status: query = query.eq("status", status)
    try: return query.execute().data
    except Exception: return []

@router.post("/videos", status_code=201)
def create_video(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
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
    try:
        result = _db().table("video_projects").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/videos/{video_id}")
def get_video(video_id: str):
    try: return _db().table("video_projects").select("*").eq("id", video_id).single().execute().data
    except Exception: raise HTTPException(status_code=404, detail="Video project not found")

@router.put("/videos/{video_id}")
def update_video(video_id: str, data: dict):
    data["updated_at"] = "now()"
    try:
        result = _db().table("video_projects").update(data).eq("id", video_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/videos/{video_id}")
def delete_video(video_id: str):
    try:
        _db().table("video_projects").delete().eq("id", video_id).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Video Shots
# =============================================================================

@router.get("/videos/{video_id}/shots")
def list_shots(video_id: str):
    try: return _db().table("video_shots").select("*").eq("video_project_id", video_id).order("shot_number").execute().data
    except Exception: return []

@router.post("/videos/{video_id}/shots", status_code=201)
def create_shot(video_id: str, data: dict):
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
    try:
        result = _db().table("video_shots").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Generate Video Shot
# =============================================================================

@router.post("/videos/{video_id}/generate")
def generate_video(video_id: str, data: dict = {}):
    """Generate video for all planned shots in a project.

    Uses the VideoProvider to generate each shot, uploads to B2, registers assets.
    """
    try:
        shots = _db().table("video_shots").select("*").eq("video_project_id", video_id).eq("status", "planned").order("shot_number").execute().data or []
    except Exception:
        raise HTTPException(status_code=404, detail="Video project not found")

    if not shots:
        raise HTTPException(status_code=400, detail="No planned shots to generate")

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

        # Mark running
        _db().table("video_shots").update({"status": "generating", "updated_at": "now()"}).eq("id", shot["id"]).execute()

        try:
            result = provider.submit(request)

            if result.success and result.output_bytes:
                # Upload to B2
                from backend.storage import upload_file, compute_checksum, generate_storage_key
                from backend.database import create_asset

                storage_key = generate_storage_key(result.filename, "video")
                checksum = compute_checksum(result.output_bytes)
                public_url = upload_file(result.output_bytes, storage_key, result.mime_type)

                asset_result = create_asset({
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
                    "metadata": {**result.metadata, "video_project_id": video_id, "shot_id": shot["id"]},
                    "tags": ["video", result.metadata.get("model", ""), provider.name],
                })
                asset = asset_result.data[0] if asset_result.data else {}

                _db().table("video_shots").update({
                    "status": "completed", "output_asset_id": asset.get("id"), "updated_at": "now()",
                }).eq("id", shot["id"]).execute()

                results.append({"shot_id": shot["id"], "status": "completed", "asset_id": asset.get("id")})
            else:
                _db().table("video_shots").update({"status": "failed", "updated_at": "now()"}).eq("id", shot["id"]).execute()
                results.append({"shot_id": shot["id"], "status": "failed", "error": result.error})

        except Exception as e:
            _db().table("video_shots").update({"status": "failed", "updated_at": "now()"}).eq("id", shot["id"]).execute()
            results.append({"shot_id": shot["id"], "status": "failed", "error": str(e)})

    return {"video_project_id": video_id, "shots_processed": len(results), "results": results}


# =============================================================================
# Timeline
# =============================================================================

@router.get("/videos/{video_id}/timeline")
def get_timeline(video_id: str):
    """Get the full timeline for a video project."""
    try:
        tracks = _db().table("timeline_tracks").select("*").eq("video_project_id", video_id).order("order_index").execute().data or []
        for track in tracks:
            clips = _db().table("timeline_clips").select("*").eq("track_id", track["id"]).order("start_time").execute().data or []
            track["clips"] = clips
        return {"video_project_id": video_id, "tracks": tracks}
    except Exception:
        return {"video_project_id": video_id, "tracks": []}

@router.post("/videos/{video_id}/timeline/tracks", status_code=201)
def create_track(video_id: str, data: dict):
    record = {
        "video_project_id": video_id,
        "name": data.get("name", "Video"),
        "track_type": data.get("track_type", "video"),
        "order_index": int(data.get("order_index", 0)),
    }
    try:
        result = _db().table("timeline_tracks").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/videos/{video_id}/timeline/clips", status_code=201)
def create_clip(video_id: str, data: dict):
    if not data.get("track_id"):
        raise HTTPException(status_code=400, detail="'track_id' required")
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
        result = _db().table("timeline_clips").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Render + Export
# =============================================================================

@router.post("/videos/{video_id}/render")
def render_video(video_id: str, data: dict = {}):
    """Create a render job for the video project (simulated)."""
    record = {
        "video_project_id": video_id,
        "provider": data.get("provider", "simulation"),
        "status": "completed",  # Simulated instant completion
        "runtime_seconds": 2.5,
        "metadata": {"rendered_by": "simulation"},
    }
    try:
        result = _db().table("video_renders").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/videos/{video_id}/export")
def export_video(video_id: str, data: dict = {}):
    """Create a timeline export (simulated)."""
    record = {
        "video_project_id": video_id,
        "export_format": data.get("format", "mp4"),
        "resolution": data.get("resolution", "1080x1920"),
        "fps": int(data.get("fps", 24)),
        "status": "completed",
    }
    try:
        result = _db().table("timeline_exports").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/video-renders")
def list_renders(video_project_id: Optional[str] = None):
    query = _db().table("video_renders").select("*").order("created_at", desc=True)
    if video_project_id: query = query.eq("video_project_id", video_project_id)
    try: return query.execute().data
    except Exception: return []

@router.get("/video-renders/{render_id}")
def get_render(render_id: str):
    try: return _db().table("video_renders").select("*").eq("id", render_id).single().execute().data
    except Exception: raise HTTPException(status_code=404, detail="Render not found")
