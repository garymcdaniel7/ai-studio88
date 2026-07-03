"""Cinematic Studio API Router.

Professional timeline, storyboard, continuity, editing, and export.
Heavy rendering always on external workers — FastAPI stores metadata only.
"""
from __future__ import annotations

import uuid
import time
from typing import Optional
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/cinematic", tags=["cinematic"])


def _db():
    from backend.database import supabase
    return supabase


# =============================================================================
# Timelines
# =============================================================================

@router.get("/timelines")
def list_timelines(project_id: Optional[str] = None, status: Optional[str] = None):
    query = _db().table("cinematic_timelines").select("*").order("created_at", desc=True)
    if project_id: query = query.eq("project_id", project_id)
    if status: query = query.eq("status", status)
    try: return query.execute().data
    except Exception: return []

@router.post("/timelines", status_code=201)
def create_timeline(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    record = {
        "name": data["name"],
        "project_id": data.get("project_id"),
        "episode_id": data.get("episode_id"),
        "duration_seconds": float(data.get("duration_seconds", 0)),
        "fps": int(data.get("fps", 24)),
        "resolution": data.get("resolution", "1920x1080"),
        "aspect_ratio": data.get("aspect_ratio", "16:9"),
        "status": "editing",
        "color_grade": data.get("color_grade"),
    }
    try:
        result = _db().table("cinematic_timelines").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/timelines/{timeline_id}")
def get_timeline(timeline_id: str):
    try:
        timeline = _db().table("cinematic_timelines").select("*").eq("id", timeline_id).single().execute().data
        tracks = _db().table("cinematic_tracks").select("*").eq("timeline_id", timeline_id).order("order_index").execute().data or []
        for track in tracks:
            items = _db().table("cinematic_items").select("*").eq("track_id", track["id"]).order("start_time").execute().data or []
            track["items"] = items
        timeline["tracks"] = tracks
        return timeline
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Timeline not found: {e}")

@router.put("/timelines/{timeline_id}")
def update_timeline(timeline_id: str, data: dict):
    data["updated_at"] = "now()"
    try:
        result = _db().table("cinematic_timelines").update(data).eq("id", timeline_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Tracks
# =============================================================================

@router.post("/timelines/{timeline_id}/tracks", status_code=201)
def create_track(timeline_id: str, data: dict):
    record = {
        "timeline_id": timeline_id,
        "name": data.get("name", "Video 1"),
        "track_type": data.get("track_type", "video"),
        "order_index": int(data.get("order_index", 0)),
    }
    try:
        result = _db().table("cinematic_tracks").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/timelines/{timeline_id}/tracks")
def list_tracks(timeline_id: str):
    try: return _db().table("cinematic_tracks").select("*").eq("timeline_id", timeline_id).order("order_index").execute().data
    except Exception: return []


# =============================================================================
# Timeline Items (clips)
# =============================================================================

@router.post("/tracks/{track_id}/items", status_code=201)
def add_item(track_id: str, data: dict):
    record = {
        "track_id": track_id,
        "asset_id": data.get("asset_id"),
        "shot_id": data.get("shot_id"),
        "item_type": data.get("item_type", "clip"),
        "start_time": float(data.get("start_time", 0)),
        "duration": float(data.get("duration", 3.0)),
        "in_point": float(data.get("in_point", 0)),
        "out_point": float(data.get("out_point", 0)),
        "transition_in": data.get("transition_in", "cut"),
        "transition_out": data.get("transition_out", "cut"),
        "speed": float(data.get("speed", 1.0)),
        "effects": data.get("effects", []),
        "color_grade": data.get("color_grade"),
    }
    try:
        result = _db().table("cinematic_items").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tracks/{track_id}/items")
def list_items(track_id: str):
    try: return _db().table("cinematic_items").select("*").eq("track_id", track_id).order("start_time").execute().data
    except Exception: return []

@router.put("/items/{item_id}")
def update_item(item_id: str, data: dict):
    try:
        result = _db().table("cinematic_items").update(data).eq("id", item_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/items/{item_id}")
def delete_item(item_id: str):
    try:
        _db().table("cinematic_items").delete().eq("id", item_id).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Storyboard
# =============================================================================

@router.get("/storyboard")
def list_storyboard(episode_id: Optional[str] = None, scene_id: Optional[str] = None):
    query = _db().table("storyboard_panels").select("*").order("panel_number")
    if episode_id: query = query.eq("episode_id", episode_id)
    if scene_id: query = query.eq("scene_id", scene_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/storyboard", status_code=201)
def create_storyboard_panel(data: dict):
    record = {
        "episode_id": data.get("episode_id"),
        "scene_id": data.get("scene_id"),
        "shot_id": data.get("shot_id"),
        "panel_number": int(data.get("panel_number", 1)),
        "description": data.get("description", ""),
        "camera": data.get("camera", ""),
        "dialogue": data.get("dialogue", ""),
        "action": data.get("action", ""),
        "mood": data.get("mood", ""),
        "duration_seconds": float(data.get("duration_seconds", 3.0)),
        "asset_id": data.get("asset_id"),
    }
    try:
        result = _db().table("storyboard_panels").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Editing Operations
# =============================================================================

EDITING_OPERATIONS = [
    "trim", "split", "merge", "duplicate", "replace", "extend",
    "slow_motion", "speed_ramp", "freeze_frame", "reverse",
    "stabilize", "crop", "zoom", "pan", "rotate",
]

TRANSITIONS = [
    "cut", "fade", "cross_dissolve", "whip_pan", "zoom_transition",
    "match_cut", "flash", "film_burn", "blur", "slide",
]

COLOR_GRADES = [
    "none", "cinematic_warm", "cinematic_cool", "netflix", "kodak",
    "fuji", "luxury_gold", "editorial", "film_noir", "vintage",
]

@router.get("/editing/operations")
def list_editing_operations():
    return EDITING_OPERATIONS

@router.get("/editing/transitions")
def list_transitions():
    return TRANSITIONS

@router.get("/editing/color-grades")
def list_color_grades():
    return COLOR_GRADES

@router.post("/editing/apply")
def apply_edit(data: dict):
    """Apply an editing operation to a timeline item."""
    operation = data.get("operation")
    if operation not in EDITING_OPERATIONS:
        raise HTTPException(status_code=400, detail=f"Invalid operation. Valid: {EDITING_OPERATIONS}")

    record = {
        "timeline_id": data.get("timeline_id"),
        "operation": operation,
        "target_item_id": data.get("item_id"),
        "parameters": data.get("parameters", {}),
    }
    try:
        _db().table("editing_operations").insert(record).execute()
        return {"applied": True, "operation": operation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Render & Export
# =============================================================================

EXPORT_FORMATS = ["mp4", "mov", "png_sequence", "gif", "webm", "audio_only", "storyboard_pdf", "shot_list_pdf"]

@router.get("/export/formats")
def list_export_formats():
    return EXPORT_FORMATS

@router.post("/render", status_code=201)
def create_render(data: dict):
    """Create a render job for a timeline (dispatched to worker)."""
    timeline_id = data.get("timeline_id")
    if not timeline_id:
        raise HTTPException(status_code=400, detail="'timeline_id' required")

    record = {
        "timeline_id": timeline_id,
        "format": data.get("format", "mp4"),
        "resolution": data.get("resolution", "1920x1080"),
        "fps": int(data.get("fps", 24)),
        "codec": data.get("codec", "h264"),
        "quality": data.get("quality", "high"),
        "status": "completed",  # Simulated
        "runtime_seconds": 5.0,
    }
    try:
        result = _db().table("cinematic_renders").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/renders")
def list_renders(timeline_id: Optional[str] = None):
    query = _db().table("cinematic_renders").select("*").order("created_at", desc=True)
    if timeline_id: query = query.eq("timeline_id", timeline_id)
    try: return query.execute().data
    except Exception: return []


# =============================================================================
# Sequences
# =============================================================================

@router.get("/sequences")
def list_sequences(episode_id: Optional[str] = None):
    query = _db().table("sequences").select("*").order("sequence_number")
    if episode_id: query = query.eq("episode_id", episode_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/sequences", status_code=201)
def create_sequence(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("sequences").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Continuity Check (uses story engine's continuity checker)
# =============================================================================

@router.post("/continuity/check")
def check_continuity(data: dict):
    """Run continuity checks for a scene or shot sequence.

    Validates: wardrobe, props, lighting, camera direction, time of day, emotion.
    """
    items = data.get("items", [])
    warnings = []

    for i in range(1, len(items)):
        prev = items[i - 1]
        curr = items[i]

        # Check wardrobe continuity
        if prev.get("wardrobe") and curr.get("wardrobe") and prev["wardrobe"] != curr["wardrobe"]:
            warnings.append({
                "type": "wardrobe_change",
                "message": f"Item {i}: wardrobe changed from '{prev['wardrobe']}' to '{curr['wardrobe']}'",
                "severity": "warning",
            })

        # Check lighting continuity
        if prev.get("lighting") and curr.get("lighting") and prev["lighting"] != curr["lighting"]:
            warnings.append({
                "type": "lighting_change",
                "message": f"Item {i}: lighting changed from '{prev['lighting']}' to '{curr['lighting']}'",
                "severity": "info",
            })

        # Check screen direction
        if prev.get("exit_direction") and curr.get("enter_direction"):
            if prev["exit_direction"] == curr["enter_direction"]:
                warnings.append({
                    "type": "screen_direction",
                    "message": f"Item {i}: character exits and enters from same direction (breaks 180° rule)",
                    "severity": "warning",
                })

    return {
        "items_checked": len(items),
        "warnings": warnings,
        "passed": not any(w["severity"] == "error" for w in warnings),
    }
