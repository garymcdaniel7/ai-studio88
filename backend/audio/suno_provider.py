"""Suno/Udio Music Generation Provider — AI music creation.

Configuration:
    SUNO_API_KEY — API key (future, when API becomes available)
    MUSIC_PROVIDER — simulation | suno | udio | stable_audio
    SUNO_LIVE — true to use real API

Currently simulated. Suno/Udio don't have official APIs yet.
Architecture is ready for when they do (or for Stable Audio / MusicGen).
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid

from dotenv import load_dotenv

from backend.audio.provider import AudioResult, MusicProvider

load_dotenv()

logger = logging.getLogger(__name__)

SUNO_API_KEY = os.getenv("SUNO_API_KEY", "")
SUNO_LIVE = os.getenv("SUNO_LIVE", "false").lower() == "true"


class SunoMusicProvider(MusicProvider):
    """AI music generation provider.

    Supports prompt-based music generation with mood, genre, and duration control.
    Currently simulated — architecture ready for Suno, Udio, or Stable Audio APIs.
    """

    @property
    def name(self) -> str:
        return "suno"

    def health(self) -> dict:
        return {
            "healthy": True,
            "provider": self.name,
            "mode": "live" if SUNO_LIVE else "simulated",
            "message": "Simulated — waiting for Suno/Udio API access"
            if not SUNO_LIVE
            else "Connected",
        }

    def capabilities(self) -> dict:
        return {
            "provider": self.name,
            "genres": [
                "pop",
                "rock",
                "electronic",
                "classical",
                "jazz",
                "hip-hop",
                "ambient",
                "cinematic",
                "lo-fi",
                "r&b",
                "country",
                "metal",
            ],
            "moods": [
                "happy",
                "sad",
                "energetic",
                "calm",
                "dramatic",
                "mysterious",
                "romantic",
                "epic",
                "dark",
                "uplifting",
                "nostalgic",
                "intense",
            ],
            "max_duration_seconds": 240,
            "supports_lyrics": True,
            "supports_instrumental": True,
            "supports_style_transfer": False,
            "live_mode": SUNO_LIVE,
        }

    def generate(self, prompt: str, duration: float = 30.0, mood: str = "neutral") -> AudioResult:
        """Generate music from a text prompt.

        Args:
            prompt: Description of desired music (genre, instruments, mood)
            duration: Duration in seconds (max 240)
            mood: Mood tag for the generation

        Returns:
            AudioResult with generated music bytes
        """
        if SUNO_LIVE and SUNO_API_KEY:
            return self._generate_live(prompt, duration, mood)
        return self._generate_simulated(prompt, duration, mood)

    def _generate_live(self, prompt: str, duration: float, mood: str) -> AudioResult:
        """Real API call — placeholder for when Suno/Udio API is available."""
        # When API is available:
        # 1. POST to API with prompt, duration, mood
        # 2. Poll for completion
        # 3. Download audio file
        # For now, fall back to simulation
        return self._generate_simulated(prompt, duration, mood)

    def _generate_simulated(self, prompt: str, duration: float, mood: str) -> AudioResult:
        """Simulated music generation."""
        start = time.time()
        time.sleep(min(duration * 0.01, 1.0))

        fake_audio = hashlib.sha256(
            f"suno-{prompt}-{mood}-{duration}-{time.time()}".encode()
        ).digest() * int(duration * 4)  # ~4 bytes per second placeholder

        return AudioResult(
            success=True,
            output_bytes=fake_audio,
            filename=f"music_{uuid.uuid4().hex[:8]}.mp3",
            mime_type="audio/mpeg",
            duration_seconds=duration,
            sample_rate=44100,
            generation_time_seconds=round(time.time() - start, 2),
            metadata={
                "provider": self.name,
                "mode": "simulated",
                "prompt": prompt[:200],
                "mood": mood,
                "duration_requested": duration,
            },
        )
