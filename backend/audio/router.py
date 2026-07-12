"""Voice, Audio, and Lip Sync API Router."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, HTTPException

from backend.audio.provider import (
    LIP_SYNC_PROVIDERS,
    MUSIC_PROVIDERS,
    SFX_PROVIDERS,
    VOICE_PROVIDERS,
    LipSyncRequest,
    TTSRequest,
    get_lip_sync_provider,
    get_voice_provider,
)

router = APIRouter(prefix="/api/v1", tags=["audio"])


def _db():
    from backend.database import supabase

    return supabase


# =============================================================================
# Voice Profiles
# =============================================================================


@router.get("/voice-profiles")
def list_voice_profiles(talent_id: str | None = None):
    query = _db().table("voice_profiles").select("*").order("name")
    if talent_id:
        query = query.eq("talent_id", talent_id)
    try:
        return query.execute().data
    except Exception:
        return []


@router.post("/voice-profiles", status_code=201)
def create_voice_profile(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    record = {
        "name": data["name"],
        "talent_id": data.get("talent_id"),
        "character_id": data.get("character_id"),
        "provider": data.get("provider", "simulation"),
        "provider_voice_id": data.get("provider_voice_id", ""),
        "voice_type": data.get("voice_type", "character"),
        "language": data.get("language", "en"),
        "accent": data.get("accent", ""),
        "gender": data.get("gender", ""),
        "tone": data.get("tone", ""),
        "speaking_style": data.get("speaking_style", "narrative"),
        "speed": float(data.get("speed", 1.0)),
        "pitch": float(data.get("pitch", 1.0)),
        "stability": float(data.get("stability", 0.7)),
        "similarity": float(data.get("similarity", 0.8)),
        "status": "active",
        "metadata": data.get("metadata", {}),
    }
    try:
        result = _db().table("voice_profiles").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/voice-profiles/{profile_id}")
def get_voice_profile(profile_id: str):
    try:
        return (
            _db().table("voice_profiles").select("*").eq("id", profile_id).single().execute().data
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Voice profile not found")


@router.put("/voice-profiles/{profile_id}")
def update_voice_profile(profile_id: str, data: dict):
    data["updated_at"] = "now()"
    try:
        result = _db().table("voice_profiles").update(data).eq("id", profile_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/voice-profiles/{profile_id}")
def delete_voice_profile(profile_id: str):
    try:
        _db().table("voice_profiles").delete().eq("id", profile_id).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── ElevenLabs Voices (from provider API) ─────────────────────────────────────


@router.get("/voices/elevenlabs")
def list_elevenlabs_voices():
    """List all voices available from ElevenLabs API.

    Used by the Voices tab on the Talent page to browse and assign voices.
    Returns the full voice catalog from ElevenLabs including custom cloned voices.
    """
    try:
        from backend.audio.elevenlabs_provider import ElevenLabsVoiceProvider

        provider = ElevenLabsVoiceProvider()
        voices = provider.list_voices()
        return {
            "voices": voices,
            "count": len(voices),
            "provider": "elevenlabs",
        }
    except Exception as e:
        return {"voices": [], "count": 0, "provider": "elevenlabs", "error": str(e)}


# ── MOSS-TTS Voice Generation ────────────────────────────────────────────────


@router.get("/voices/moss")
def list_moss_voices():
    """List available MOSS-TTS voices (saved voice identities)."""
    try:
        voices = _db().table("voice_profiles").select("*").eq("provider", "moss-tts").execute().data or []
        # Also get MOSS-VoiceGenerator created voices
        generated = _db().table("voice_profiles").select("*").eq("provider", "moss-voicegenerator").execute().data or []
        return {
            "voices": voices + generated,
            "count": len(voices) + len(generated),
            "provider": "moss-tts",
        }
    except Exception as e:
        return {"voices": [], "count": 0, "provider": "moss-tts", "error": str(e)}


@router.get("/voices/moss/health")
def moss_tts_health():
    """Check MOSS-TTS worker health."""
    from backend.audio.moss_provider import MossTTSProvider

    provider = MossTTSProvider()
    return provider.health()


@router.post("/voices/moss/generate-speech")
def moss_generate_speech(data: dict):
    """Generate speech using MOSS-TTS (with optional voice cloning).

    Returns audio as base64 for preview playback.
    If save=true is passed, also uploads to B2.

    Body:
        text: str — text to synthesize
        voice_sample_url: str — URL/path to voice sample for cloning (optional)
        language: str — language code (default: en)
        speed: float — speech speed (default: 1.0)
        talent_id: str — talent to use saved voice from (optional)
        save: bool — if true, save to B2 (default: false for preview)
    """
    import base64

    from backend.audio.moss_provider import MossTTSProvider

    text = data.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="'text' required")

    voice_sample = data.get("voice_sample_url")
    talent_id = data.get("talent_id")

    # If talent_id provided, look up their saved voice sample
    if talent_id and not voice_sample:
        try:
            profiles = (
                _db()
                .table("voice_profiles")
                .select("*")
                .eq("talent_id", talent_id)
                .in_("provider", ["moss-tts", "moss-voicegenerator"])
                .execute()
                .data or []
            )
            if profiles:
                meta = profiles[0].get("metadata", {}) or {}
                voice_sample = meta.get("sample_url") or meta.get("b2_url")
        except Exception:
            pass

    provider = MossTTSProvider()
    result = provider.generate_speech(
        text=text,
        voice_sample_path=voice_sample,
        language=data.get("language", "en"),
        speed=float(data.get("speed", 1.0)),
    )

    if result.success:
        # Always return base64 for preview playback
        audio_b64 = base64.b64encode(result.audio_bytes).decode("utf-8") if result.audio_bytes else ""

        # Save to B2 only if requested
        b2_url = None
        should_save = data.get("save", False)
        if result.audio_bytes and should_save:
            try:
                from backend.storage import upload_file

                storage_key = f"voices/generated/{result.filename}"
                b2_url = upload_file(result.audio_bytes, storage_key, "audio/wav")
            except Exception:
                pass

        return {
            "success": True,
            "audio_base64": audio_b64,
            "mime_type": "audio/wav",
            "filename": result.filename,
            "duration_seconds": result.duration_seconds,
            "b2_url": b2_url,
            "saved": should_save and b2_url is not None,
            "provider": "moss-tts",
            "metadata": result.metadata,
        }
    else:
        raise HTTPException(status_code=500, detail=result.error or "MOSS-TTS generation failed")


@router.post("/voices/moss/create-voice")
def moss_create_voice(data: dict):
    """Create a new voice identity using MOSS-VoiceGenerator.

    Generates a unique voice from a text description and saves it to B2 + DB.

    Body:
        description: str — voice description (e.g. "Warm female voice, 30s, confident")
        name: str — name for this voice (optional, auto-generated if blank)
        sample_text: str — text to generate as demo (default provided)
        talent_id: str — talent to associate this voice with (optional)
    """
    from backend.audio.moss_provider import MossTTSProvider

    description = data.get("description")
    if not description:
        raise HTTPException(status_code=400, detail="'description' required")

    provider = MossTTSProvider()
    voice = provider.create_voice(
        description=description,
        name=data.get("name", ""),
        sample_text=data.get("sample_text", "Hello, this is a sample of my generated voice."),
    )

    # Save sample audio to B2
    b2_url = None
    if voice.sample_audio_bytes:
        try:
            from backend.storage import upload_file

            storage_key = f"voices/identities/{voice.sample_filename}"
            b2_url = upload_file(voice.sample_audio_bytes, storage_key, "audio/wav")
        except Exception:
            pass

    # Save voice profile to DB
    talent_id = data.get("talent_id")
    profile_record = {
        "name": voice.name,
        "talent_id": talent_id,
        "provider": "moss-voicegenerator",
        "provider_voice_id": voice.id,
        "voice_type": "generated",
        "language": "en",
        "gender": "",
        "accent": "",
        "tone": data.get("description", "")[:100],
        "status": "active",
        "metadata": {
            "description": description,
            "sample_url": b2_url,
            "b2_url": b2_url,
            "sample_filename": voice.sample_filename,
            **(voice.metadata or {}),
        },
    }

    try:
        result = _db().table("voice_profiles").insert(profile_record).execute()
        saved = result.data[0] if result.data else profile_record
    except Exception:
        saved = profile_record

    return {
        "success": True,
        "voice_id": voice.id,
        "name": voice.name,
        "description": description,
        "sample_url": b2_url,
        "profile": saved,
        "provider": "moss-voicegenerator",
    }


# ── Voice Samples ─────────────────────────────────────────────────────────────


@router.get("/voice-profiles/{profile_id}/samples")
def list_voice_samples(profile_id: str):
    try:
        return (
            _db()
            .table("voice_samples")
            .select("*")
            .eq("voice_profile_id", profile_id)
            .execute()
            .data
        )
    except Exception:
        return []


@router.post("/voice-profiles/{profile_id}/samples", status_code=201)
def add_voice_sample(profile_id: str, data: dict):
    record = {
        "voice_profile_id": profile_id,
        "asset_id": data.get("asset_id"),
        "transcript": data.get("transcript", ""),
        "duration_seconds": float(data.get("duration_seconds", 0)),
        "quality_score": float(data.get("quality_score", 1.0)),
        "approved": data.get("approved", False),
    }
    try:
        result = _db().table("voice_samples").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# TTS / Dialogue / Narration
# =============================================================================


@router.post("/audio/tts/preview")
def preview_tts(data: dict):
    """Generate TTS audio and return as base64 for browser playback.

    Does NOT save to B2 or create an asset. Use POST /audio/tts to save.

    Required: text
    Optional: voice_profile_id, language, speed, emotion, style, provider, voice_id
    Returns: { audio_base64, mime_type, duration_seconds, provider }
    """
    import base64

    text = data.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="'text' required")

    provider = get_voice_provider(data.get("provider"))
    request = TTSRequest(
        text=text,
        voice_profile_id=data.get("voice_profile_id", ""),
        language=data.get("language", "en"),
        speed=float(data.get("speed", 1.0)),
        pitch=float(data.get("pitch", 1.0)),
        emotion=data.get("emotion", "neutral"),
        style=data.get("style", "narrative"),
        extra={
            "voice_id": data.get("voice_id", ""),
            "model_id": data.get("model_id", ""),
            "stability": data.get("stability", 0.7),
            "similarity": data.get("similarity", 0.8),
        },
    )

    result = provider.generate_speech(request)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "TTS preview failed")

    audio_b64 = base64.b64encode(result.output_bytes).decode("utf-8")

    return {
        "audio_base64": audio_b64,
        "mime_type": result.mime_type,
        "duration_seconds": result.duration_seconds,
        "filename": result.filename,
        "provider": provider.name,
    }


@router.post("/audio/tts", status_code=201)
def generate_tts(data: dict):
    """Generate text-to-speech audio and save to B2.

    Required: text
    Optional: voice_profile_id, language, speed, emotion, style, provider
    """
    text = data.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="'text' required")

    provider = get_voice_provider(data.get("provider"))
    request = TTSRequest(
        text=text,
        voice_profile_id=data.get("voice_profile_id", ""),
        language=data.get("language", "en"),
        speed=float(data.get("speed", 1.0)),
        pitch=float(data.get("pitch", 1.0)),
        emotion=data.get("emotion", "neutral"),
        style=data.get("style", "narrative"),
        extra={
            "voice_id": data.get("voice_id", ""),
            "model_id": data.get("model_id", ""),
            "stability": data.get("stability", 0.7),
            "similarity": data.get("similarity", 0.8),
        },
    )

    result = provider.generate_speech(request)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "TTS failed")

    # Upload to B2 and register as asset
    from backend.database import create_asset
    from backend.storage import compute_checksum, generate_storage_key, upload_file

    storage_key = generate_storage_key(result.filename, "audio")
    checksum = compute_checksum(result.output_bytes)
    public_url = upload_file(result.output_bytes, storage_key, result.mime_type)

    asset_result = create_asset(
        {
            "type": "audio",
            "filename": result.filename,
            "original_filename": result.filename,
            "mime_type": result.mime_type,
            "size_bytes": len(result.output_bytes),
            "storage_provider": "backblaze_b2",
            "storage_key": storage_key,
            "public_url": public_url,
            "checksum": checksum,
            "metadata": {**result.metadata, "duration_seconds": result.duration_seconds},
            "tags": ["audio", "tts", provider.name],
        }
    )
    asset = asset_result.data[0] if asset_result.data else {}

    # Create audio clip record
    with contextlib.suppress(Exception):
        _db().table("audio_clips").insert(
            {
                "voice_profile_id": data.get("voice_profile_id"),
                "asset_id": asset.get("id"),
                "text": text,
                "clip_type": "tts",
                "duration_seconds": result.duration_seconds,
                "provider": provider.name,
                "status": "completed",
            }
        ).execute()

    # Record job cost
    try:
        from backend.infrastructure.cost_intelligence import get_cost_tracker

        tracker = get_cost_tracker()
        # ElevenLabs charges ~$0.30 per 1000 characters
        char_count = len(text)
        api_cost = round((char_count / 1000) * 0.30, 6) if provider.name == "elevenlabs" else 0
        tracker.record_job_cost(
            job_type="voice",
            model="eleven_multilingual_v2",
            provider=provider.name,
            duration_seconds=result.duration_seconds,
            api_cost=api_cost,
            input_summary=text[:100],
            output_summary=asset.get("id", ""),
        )
    except Exception:
        pass

    return {
        "status": "completed",
        "asset_id": asset.get("id"),
        "public_url": asset.get("public_url"),
        "duration_seconds": result.duration_seconds,
        "provider": provider.name,
    }


@router.post("/audio/dialogue", status_code=201)
def generate_dialogue(data: dict):
    """Generate character dialogue. Same as TTS but typed as dialogue."""
    data.setdefault("style", "conversational")
    data.setdefault("emotion", data.get("direction", "neutral"))
    return generate_tts(data)


@router.post("/audio/narration", status_code=201)
def generate_narration(data: dict):
    """Generate narration voice. Same as TTS but styled as narration."""
    data.setdefault("style", "narrative")
    data.setdefault("speed", 0.95)
    return generate_tts(data)


@router.get("/audio/clips")
def list_audio_clips(voice_profile_id: str | None = None):
    query = _db().table("audio_clips").select("*").order("created_at", desc=True)
    if voice_profile_id:
        query = query.eq("voice_profile_id", voice_profile_id)
    try:
        return query.execute().data
    except Exception:
        return []


@router.get("/audio/clips/{clip_id}")
def get_audio_clip(clip_id: str):
    try:
        return _db().table("audio_clips").select("*").eq("id", clip_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Clip not found")


# =============================================================================
# Lip Sync
# =============================================================================


@router.post("/lip-sync", status_code=201)
def create_lip_sync_job(data: dict):
    """Create a lip sync job: combine video + audio into synced output.

    Required: video_asset_id, audio_asset_id
    """
    video_id = data.get("video_asset_id")
    audio_id = data.get("audio_asset_id")
    if not video_id or not audio_id:
        raise HTTPException(
            status_code=400, detail="'video_asset_id' and 'audio_asset_id' required"
        )

    provider = get_lip_sync_provider(data.get("provider", "simulation"))
    request = LipSyncRequest(
        video_asset_id=video_id,
        audio_asset_id=audio_id,
        model=data.get("model", "wav2lip"),
    )

    result = provider.sync(request)

    if result.success and result.output_bytes:
        from backend.database import create_asset
        from backend.storage import compute_checksum, generate_storage_key, upload_file

        storage_key = generate_storage_key(result.filename, "video")
        checksum = compute_checksum(result.output_bytes)
        public_url = upload_file(result.output_bytes, storage_key, result.mime_type)

        asset_result = create_asset(
            {
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
                    "lip_sync": True,
                    "video_source": video_id,
                    "audio_source": audio_id,
                },
                "tags": ["video", "lip_sync", provider.name],
            }
        )
        asset = asset_result.data[0] if asset_result.data else {}

        # Record lip sync job
        with contextlib.suppress(Exception):
            _db().table("lip_sync_jobs").insert(
                {
                    "video_asset_id": video_id,
                    "audio_asset_id": audio_id,
                    "output_asset_id": asset.get("id"),
                    "provider": provider.name,
                    "status": "completed",
                }
            ).execute()

        return {"status": "completed", "asset_id": asset.get("id"), "provider": provider.name}

    raise HTTPException(status_code=500, detail=result.error or "Lip sync failed")


@router.get("/lip-sync/jobs")
def list_lip_sync_jobs():
    try:
        return (
            _db().table("lip_sync_jobs").select("*").order("created_at", desc=True).execute().data
        )
    except Exception:
        return []


@router.get("/lip-sync/jobs/{job_id}")
def get_lip_sync_job(job_id: str):
    try:
        return _db().table("lip_sync_jobs").select("*").eq("id", job_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Lip sync job not found")


# =============================================================================
# Music + SFX
# =============================================================================


@router.get("/music")
def list_music(mood: str | None = None):
    query = _db().table("music_tracks_db").select("*").order("name")
    if mood:
        query = query.eq("mood", mood)
    try:
        return query.execute().data
    except Exception:
        return []


@router.post("/music", status_code=201)
def create_music(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("music_tracks_db").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sfx")
def list_sfx(category: str | None = None):
    query = _db().table("sound_effects").select("*").order("name")
    if category:
        query = query.eq("category", category)
    try:
        return query.execute().data
    except Exception:
        return []


@router.post("/sfx", status_code=201)
def create_sfx(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("sound_effects").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Provider Health
# =============================================================================


@router.get("/audio/providers/health")
def audio_providers_health():
    """Health status of all audio-related providers."""
    results = []
    for name, cls in VOICE_PROVIDERS.items():
        p = cls()
        results.append({"type": "voice", "provider": name, **p.health()})
    for name, cls in LIP_SYNC_PROVIDERS.items():
        p = cls()
        results.append({"type": "lip_sync", "provider": name, **p.health()})
    for name, cls in MUSIC_PROVIDERS.items():
        p = cls()
        results.append({"type": "music", "provider": name, **p.health()})
    for name, cls in SFX_PROVIDERS.items():
        p = cls()
        results.append({"type": "sfx", "provider": name, **p.health()})
    return results
