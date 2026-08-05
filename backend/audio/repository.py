"""Audio/Voice Repository — tenant-scoped data access for voice and audio.

All operations require org_id from TenantContext. No bare-ID queries permitted.

Tables:
- voice_profiles: customer-owned voice identities (DIRECT org_id)
- voice_samples: audio samples for cloning (INHERITED via voice_profile_id, denormalized org_id)
- audio_clips: generated speech output (DIRECT org_id)

Public-vs-Private:
- Provider catalogs (ElevenLabs voices, MOSS voices) are retrieved LIVE from APIs.
- All data in these tables is PRIVATE customer content.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _db():
    from backend.database import supabase
    return supabase


# =============================================================================
# Voice Profiles (tenant-scoped)
# =============================================================================


def list_voice_profiles(org_id: str, talent_id: str | None = None) -> list[dict]:
    """List voice profiles scoped to a tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")
    query = _db().table("voice_profiles").select("*").eq("org_id", org_id).order("name")
    if talent_id:
        query = query.eq("talent_id", talent_id)
    return query.execute().data or []


def get_voice_profile(profile_id: str, org_id: str) -> dict | None:
    """Get a voice profile by ID, scoped to tenant.

    Returns None for both not-found and cross-tenant (no existence leak).
    """
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")
    result = (
        _db().table("voice_profiles")
        .select("*")
        .eq("id", profile_id)
        .eq("org_id", org_id)
        .execute()
    )
    return result.data[0] if result.data else None


def create_voice_profile(data: dict, org_id: str) -> dict:
    """Create a voice profile. org_id injected from trusted context."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped creates")
    data["org_id"] = org_id
    result = _db().table("voice_profiles").insert(data).execute()
    return result.data[0] if result.data else data


def update_voice_profile(profile_id: str, data: dict, org_id: str) -> dict | None:
    """Update a voice profile, scoped to tenant. Returns None if not found."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped updates")
    data.pop("org_id", None)  # Prevent ownership reassignment
    data["updated_at"] = "now()"
    result = (
        _db().table("voice_profiles")
        .update(data)
        .eq("id", profile_id)
        .eq("org_id", org_id)
        .execute()
    )
    return result.data[0] if result.data else None


def delete_voice_profile(profile_id: str, org_id: str) -> bool:
    """Delete a voice profile, scoped to tenant. Returns False if not found."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped deletes")
    result = (
        _db().table("voice_profiles")
        .delete()
        .eq("id", profile_id)
        .eq("org_id", org_id)
        .execute()
    )
    return bool(result.data)


# =============================================================================
# Voice Samples (tenant-scoped, inherited via voice_profile_id)
# =============================================================================


def list_voice_samples(profile_id: str, org_id: str) -> list[dict]:
    """List voice samples for a profile, scoped to tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")
    return (
        _db().table("voice_samples")
        .select("*")
        .eq("voice_profile_id", profile_id)
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .execute().data or []
    )


def create_voice_sample(data: dict, org_id: str) -> dict:
    """Create a voice sample. org_id injected."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped creates")
    data["org_id"] = org_id
    result = _db().table("voice_samples").insert(data).execute()
    return result.data[0] if result.data else data


# =============================================================================
# Audio Clips (tenant-scoped)
# =============================================================================


def list_audio_clips(org_id: str, voice_profile_id: str | None = None) -> list[dict]:
    """List audio clips scoped to a tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")
    query = (
        _db().table("audio_clips")
        .select("*")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
    )
    if voice_profile_id:
        query = query.eq("voice_profile_id", voice_profile_id)
    return query.execute().data or []


def get_audio_clip(clip_id: str, org_id: str) -> dict | None:
    """Get an audio clip by ID, scoped to tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")
    result = (
        _db().table("audio_clips")
        .select("*")
        .eq("id", clip_id)
        .eq("org_id", org_id)
        .execute()
    )
    return result.data[0] if result.data else None


def create_audio_clip(data: dict, org_id: str) -> dict:
    """Create an audio clip record. org_id injected."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped creates")
    data["org_id"] = org_id
    result = _db().table("audio_clips").insert(data).execute()
    return result.data[0] if result.data else data


def delete_audio_clip(clip_id: str, org_id: str) -> bool:
    """Delete an audio clip, scoped to tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped deletes")
    result = (
        _db().table("audio_clips")
        .delete()
        .eq("id", clip_id)
        .eq("org_id", org_id)
        .execute()
    )
    return bool(result.data)
