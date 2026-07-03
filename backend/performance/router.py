"""Performance Engine API Router.

Voice training, song studio, performance memory, series continuity,
and performance DNA. All heavy compute on external workers.
"""
from __future__ import annotations

import uuid
import hashlib
import time
from typing import Optional
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1", tags=["performance"])


def _db():
    from backend.database import supabase
    return supabase


# =============================================================================
# Voice Training
# =============================================================================

@router.get("/voice-training/datasets")
def list_voice_datasets(talent_id: Optional[str] = None):
    query = _db().table("voice_datasets").select("*").order("created_at", desc=True)
    if talent_id: query = query.eq("talent_id", talent_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/voice-training/datasets", status_code=201)
def create_voice_dataset(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    record = {
        "name": data["name"],
        "talent_id": data.get("talent_id"),
        "character_id": data.get("character_id"),
        "description": data.get("description", ""),
        "status": "draft",
        "consent_confirmed": data.get("consent_confirmed", False),
        "usage_rights": data.get("usage_rights", ""),
        "source": data.get("source", ""),
    }
    try:
        result = _db().table("voice_datasets").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/voice-training/jobs", status_code=201)
def start_voice_training(data: dict):
    """Start a simulated voice training job."""
    dataset_id = data.get("voice_dataset_id")
    if not dataset_id:
        raise HTTPException(status_code=400, detail="'voice_dataset_id' required")

    record = {
        "voice_dataset_id": dataset_id,
        "voice_profile_id": data.get("voice_profile_id"),
        "provider": "simulation",
        "status": "completed",  # Simulated instant completion
        "config": data.get("config", {}),
    }
    try:
        result = _db().table("voice_training_jobs").insert(record).execute()
        job = result.data[0] if result.data else record

        # Create a voice version
        version_record = {
            "voice_profile_id": data.get("voice_profile_id"),
            "talent_id": data.get("talent_id"),
            "character_id": data.get("character_id"),
            "training_job_id": job.get("id"),
            "version": 1,
            "name": f"Voice v1 (simulated)",
            "provider": "simulation",
            "status": "active",
            "quality_score": 0.85,
        }
        _db().table("voice_versions").insert(version_record).execute()

        return {"status": "completed", "training_job_id": job.get("id"), "message": "Simulated voice training complete"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/voice-training/jobs")
def list_voice_training_jobs():
    try: return _db().table("voice_training_jobs").select("*").order("created_at", desc=True).execute().data
    except Exception: return []

@router.get("/voice-versions")
def list_voice_versions(talent_id: Optional[str] = None):
    query = _db().table("voice_versions").select("*").order("created_at", desc=True)
    if talent_id: query = query.eq("talent_id", talent_id)
    try: return query.execute().data
    except Exception: return []


# =============================================================================
# Voice DNA
# =============================================================================

@router.get("/voice-dna")
def list_voice_dna(talent_id: Optional[str] = None):
    query = _db().table("voice_dna").select("*")
    if talent_id: query = query.eq("talent_id", talent_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/voice-dna", status_code=201)
def create_voice_dna(data: dict):
    try:
        result = _db().table("voice_dna").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/voice-dna/{dna_id}")
def update_voice_dna(dna_id: str, data: dict):
    data["updated_at"] = "now()"
    try:
        result = _db().table("voice_dna").update(data).eq("id", dna_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Song Studio
# =============================================================================

@router.get("/songs")
def list_songs(story_id: Optional[str] = None, episode_id: Optional[str] = None):
    query = _db().table("songs").select("*").order("created_at", desc=True)
    if story_id: query = query.eq("story_id", story_id)
    if episode_id: query = query.eq("episode_id", episode_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/songs", status_code=201)
def create_song(data: dict):
    if not data.get("title"):
        raise HTTPException(status_code=400, detail="'title' required")
    record = {
        "title": data["title"],
        "project_id": data.get("project_id"),
        "story_id": data.get("story_id"),
        "episode_id": data.get("episode_id"),
        "scene_id": data.get("scene_id"),
        "character_id": data.get("character_id"),
        "genre": data.get("genre", ""),
        "mood": data.get("mood", ""),
        "tempo": int(data.get("tempo", 120)),
        "musical_key": data.get("musical_key", ""),
        "lyrics": data.get("lyrics", ""),
        "vocal_style": data.get("vocal_style", ""),
        "instrumental_style": data.get("instrumental_style", ""),
        "duration_seconds": float(data.get("duration_seconds", 0)),
        "provider": data.get("provider", "simulation"),
        "status": "draft",
    }
    try:
        result = _db().table("songs").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/songs/{song_id}")
def get_song(song_id: str):
    try: return _db().table("songs").select("*").eq("id", song_id).single().execute().data
    except Exception: raise HTTPException(status_code=404, detail="Song not found")

@router.put("/songs/{song_id}")
def update_song(song_id: str, data: dict):
    data["updated_at"] = "now()"
    try:
        result = _db().table("songs").update(data).eq("id", song_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/songs/{song_id}/generate")
def generate_song(song_id: str, data: dict = {}):
    """Generate a simulated song output and register as asset."""
    try:
        song = _db().table("songs").select("*").eq("id", song_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Song not found")

    # Simulated generation
    fake_audio = hashlib.sha256(f"song-{song['title']}-{time.time()}".encode()).digest() * 32
    filename = f"song_{uuid.uuid4().hex[:8]}.mp3"

    from backend.storage import upload_file, compute_checksum, generate_storage_key
    from backend.database import create_asset

    storage_key = generate_storage_key(filename, "audio")
    checksum = compute_checksum(fake_audio)
    public_url = upload_file(fake_audio, storage_key, "audio/mp3")

    asset_result = create_asset({
        "type": "audio",
        "filename": filename,
        "original_filename": filename,
        "mime_type": "audio/mp3",
        "size_bytes": len(fake_audio),
        "storage_provider": "backblaze_b2",
        "storage_key": storage_key,
        "public_url": public_url,
        "checksum": checksum,
        "metadata": {"song_id": song_id, "title": song["title"], "genre": song.get("genre")},
        "tags": ["audio", "song", "generated"],
    })
    asset = asset_result.data[0] if asset_result.data else {}

    _db().table("songs").update({
        "output_asset_id": asset.get("id"), "status": "completed", "updated_at": "now()",
    }).eq("id", song_id).execute()

    return {"status": "completed", "song_id": song_id, "asset_id": asset.get("id")}


# =============================================================================
# Performance Memory
# =============================================================================

@router.get("/performance-memory")
def list_performance_memory(character_id: Optional[str] = None, episode_id: Optional[str] = None):
    query = _db().table("performance_memory").select("*").order("created_at", desc=True).limit(50)
    if character_id: query = query.eq("character_id", character_id)
    if episode_id: query = query.eq("episode_id", episode_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/performance-memory", status_code=201)
def record_performance(data: dict):
    """Record how a character was performing at a specific moment.

    This is the continuity of performance — the character remembers their state.
    """
    try:
        result = _db().table("performance_memory").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/performance-memory/latest/{character_id}")
def get_latest_performance(character_id: str):
    """Get the most recent performance state for a character.

    Used to maintain continuity into the next shot/scene.
    """
    try:
        result = _db().table("performance_memory").select("*").eq("character_id", character_id).order("created_at", desc=True).limit(1).execute()
        return result.data[0] if result.data else {}
    except Exception:
        return {}


# =============================================================================
# Performance DNA
# =============================================================================

@router.get("/performance-dna")
def list_performance_dna(talent_id: Optional[str] = None):
    query = _db().table("performance_dna").select("*")
    if talent_id: query = query.eq("talent_id", talent_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/performance-dna", status_code=201)
def create_performance_dna(data: dict):
    try:
        result = _db().table("performance_dna").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/performance-dna/{dna_id}")
def update_performance_dna(dna_id: str, data: dict):
    data["updated_at"] = "now()"
    try:
        result = _db().table("performance_dna").update(data).eq("id", dna_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Series
# =============================================================================

@router.get("/series")
def list_series(universe_id: Optional[str] = None):
    query = _db().table("series").select("*").order("created_at", desc=True)
    if universe_id: query = query.eq("universe_id", universe_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/series", status_code=201)
def create_series(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("series").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/series/{series_id}")
def get_series(series_id: str):
    try: return _db().table("series").select("*").eq("id", series_id).single().execute().data
    except Exception: raise HTTPException(status_code=404, detail="Series not found")


# =============================================================================
# Soundtrack Cues
# =============================================================================

@router.get("/soundtrack-cues")
def list_soundtrack_cues(episode_id: Optional[str] = None, scene_id: Optional[str] = None):
    query = _db().table("soundtrack_cues").select("*").order("start_time")
    if episode_id: query = query.eq("episode_id", episode_id)
    if scene_id: query = query.eq("scene_id", scene_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/soundtrack-cues", status_code=201)
def create_soundtrack_cue(data: dict):
    try:
        result = _db().table("soundtrack_cues").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
