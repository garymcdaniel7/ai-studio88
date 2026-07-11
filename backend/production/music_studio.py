"""Music Studio — manages music library and track assignment."""

from __future__ import annotations

from backend.production.models import MusicTrack

# =============================================================================
# Music Library (in-memory, DB-backed in future)
# =============================================================================

_music_library: list[MusicTrack] = [
    MusicTrack(
        id="music-luxury-ambient",
        title="Luxury Ambient",
        mood="elegant",
        genre="ambient",
        tempo_bpm=80,
        energy="low",
        duration_seconds=120.0,
    ),
    MusicTrack(
        id="music-upbeat-pop",
        title="Upbeat Pop",
        mood="energetic",
        genre="pop",
        tempo_bpm=128,
        energy="high",
        duration_seconds=90.0,
    ),
    MusicTrack(
        id="music-cinematic-epic",
        title="Cinematic Epic",
        mood="dramatic",
        genre="cinematic",
        tempo_bpm=100,
        energy="high",
        duration_seconds=180.0,
    ),
    MusicTrack(
        id="music-chill-lofi",
        title="Chill Lo-Fi",
        mood="relaxed",
        genre="lo-fi",
        tempo_bpm=85,
        energy="low",
        duration_seconds=150.0,
    ),
    MusicTrack(
        id="music-fashion-beat",
        title="Fashion Beat",
        mood="stylish",
        genre="electronic",
        tempo_bpm=110,
        energy="medium",
        duration_seconds=60.0,
    ),
]


def get_music_library() -> list[dict]:
    """Get all music tracks."""
    return [
        {
            "id": m.id,
            "title": m.title,
            "mood": m.mood,
            "genre": m.genre,
            "tempo_bpm": m.tempo_bpm,
            "energy": m.energy,
            "duration_seconds": m.duration_seconds,
        }
        for m in _music_library
    ]


def get_music_by_mood(mood: str) -> list[dict]:
    """Find tracks matching a mood."""
    matches = [m for m in _music_library if mood.lower() in m.mood.lower()]
    return [{"id": m.id, "title": m.title, "mood": m.mood, "genre": m.genre} for m in matches]


def recommend_music(content_type: str, mood: str = "") -> dict | None:
    """Recommend a music track based on content type and mood."""
    mood_map = {
        "reel": "energetic",
        "tiktok": "energetic",
        "portrait": "elegant",
        "fashion_campaign": "stylish",
        "commercial": "dramatic",
        "short_film": "dramatic",
        "talking_head": "relaxed",
    }
    target_mood = mood or mood_map.get(content_type, "relaxed")
    matches = get_music_by_mood(target_mood)
    return matches[0] if matches else None
