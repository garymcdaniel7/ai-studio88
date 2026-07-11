"""Voice Studio — manages voice profiles and synthesis.

Provides a library of voice profiles (per character/talent) and
dispatches synthesis through the appropriate audio provider.
"""

from __future__ import annotations

from backend.production.models import VoiceProfile

# =============================================================================
# Voice Library (in-memory, DB-backed in future)
# =============================================================================

_voice_library: list[VoiceProfile] = [
    VoiceProfile(
        id="voice-melissa",
        name="Melissa Voice",
        provider="simulation",
        emotion="confident",
        accent="american",
        language="en",
        speed=1.0,
        pitch=1.0,
        style="narrative",
    ),
    VoiceProfile(
        id="voice-narrator",
        name="Narrator",
        provider="simulation",
        emotion="neutral",
        accent="british",
        language="en",
        speed=0.95,
        pitch=0.9,
        style="documentary",
    ),
]


def get_voice_library() -> list[dict]:
    """Get all voice profiles."""
    return [
        {
            "id": v.id,
            "name": v.name,
            "provider": v.provider,
            "emotion": v.emotion,
            "accent": v.accent,
            "language": v.language,
            "speed": v.speed,
            "pitch": v.pitch,
            "style": v.style,
        }
        for v in _voice_library
    ]


def get_voice(voice_id: str) -> dict | None:
    """Get a voice profile by ID."""
    for v in _voice_library:
        if v.id == voice_id:
            return {
                "id": v.id,
                "name": v.name,
                "provider": v.provider,
                "emotion": v.emotion,
                "style": v.style,
            }
    return None


def add_voice(data: dict) -> dict:
    """Add a new voice profile."""
    import uuid

    profile = VoiceProfile(
        id=data.get("id", f"voice-{uuid.uuid4().hex[:8]}"),
        name=data.get("name", "New Voice"),
        provider=data.get("provider", "simulation"),
        emotion=data.get("emotion", "neutral"),
        accent=data.get("accent", ""),
        language=data.get("language", "en"),
        speed=float(data.get("speed", 1.0)),
        pitch=float(data.get("pitch", 1.0)),
        style=data.get("style", "conversational"),
    )
    _voice_library.append(profile)
    return {"id": profile.id, "name": profile.name}
