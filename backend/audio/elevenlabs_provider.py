"""ElevenLabs Voice Provider — real text-to-speech via ElevenLabs API.

Configuration:
    ELEVENLABS_API_KEY — API key from elevenlabs.io/settings
    ELEVENLABS_DEFAULT_VOICE — Default voice ID (optional)
    ELEVENLABS_MODEL — Model ID (default: eleven_multilingual_v2)

Set VOICE_PROVIDER=elevenlabs in .env to use as default.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid

import httpx
from dotenv import load_dotenv

from backend.audio.provider import AudioResult, TTSRequest, VoiceProvider

load_dotenv(override=True)

logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
ELEVENLABS_DEFAULT_VOICE = os.getenv("ELEVENLABS_DEFAULT_VOICE", "21m00Tcm4TlvDq8ikWAM")  # Rachel
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_LIVE = os.getenv("ELEVENLABS_LIVE", "false").lower() == "true"


class ElevenLabsVoiceProvider(VoiceProvider):
    """ElevenLabs text-to-speech provider.

    Supports both live (real API calls) and simulated modes.
    Set ELEVENLABS_LIVE=true and provide ELEVENLABS_API_KEY for real speech.
    """

    @property
    def name(self) -> str:
        return "elevenlabs"

    def health(self) -> dict:
        if not ELEVENLABS_LIVE:
            return {
                "healthy": True,
                "provider": self.name,
                "mode": "simulated",
                "message": "Set ELEVENLABS_LIVE=true for real TTS",
            }

        if not ELEVENLABS_API_KEY:
            return {
                "healthy": False,
                "provider": self.name,
                "error": "ELEVENLABS_API_KEY not set",
            }

        try:
            resp = httpx.get(
                f"{ELEVENLABS_BASE_URL}/user",
                headers={"xi-api-key": ELEVENLABS_API_KEY},
                timeout=10,
            )
            if resp.status_code == 200:
                user = resp.json()
                return {
                    "healthy": True,
                    "provider": self.name,
                    "mode": "live",
                    "subscription": user.get("subscription", {}).get("tier", "unknown"),
                    "character_count": user.get("subscription", {}).get("character_count", 0),
                    "character_limit": user.get("subscription", {}).get("character_limit", 0),
                }
            return {"healthy": False, "provider": self.name, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"healthy": False, "provider": self.name, "error": str(e)}

    def capabilities(self) -> dict:
        return {
            "provider": self.name,
            "languages": ["en", "es", "fr", "de", "it", "pt", "pl", "hi", "ar", "ja", "ko", "zh"],
            "voices": 100,
            "max_chars": 5000,
            "styles": ["narrative", "conversational", "dramatic", "whisper", "excited"],
            "models": ["eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_monolingual_v1"],
            "features": ["voice_cloning", "voice_design", "emotion_control", "stability_control"],
            "live_mode": ELEVENLABS_LIVE,
        }

    def generate_speech(self, request: TTSRequest) -> AudioResult:
        """Generate speech from text.

        In live mode: calls ElevenLabs API.
        In simulated mode: returns a placeholder.
        """
        if ELEVENLABS_LIVE and ELEVENLABS_API_KEY:
            return self._generate_live(request)
        return self._generate_simulated(request)

    def _generate_live(self, request: TTSRequest) -> AudioResult:
        """Real ElevenLabs API call."""
        start = time.time()

        voice_id = request.extra.get("voice_id") or ELEVENLABS_DEFAULT_VOICE
        model_id = request.extra.get("model_id") or ELEVENLABS_MODEL

        # Build voice settings
        voice_settings = {
            "stability": request.extra.get("stability", 0.7),
            "similarity_boost": request.extra.get("similarity", 0.8),
            "style": request.extra.get("style_intensity", 0.5),
            "use_speaker_boost": True,
        }

        payload = {
            "text": request.text,
            "model_id": model_id,
            "voice_settings": voice_settings,
        }

        try:
            resp = httpx.post(
                f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json=payload,
                timeout=30,
            )

            if resp.status_code != 200:
                return AudioResult(
                    success=False,
                    error=f"ElevenLabs API error ({resp.status_code}): {resp.text[:200]}",
                    generation_time_seconds=round(time.time() - start, 2),
                    metadata={"provider": self.name, "mode": "live"},
                )

            audio_bytes = resp.content
            duration = len(request.text) * 0.06  # Estimate ~60ms per char

            return AudioResult(
                success=True,
                output_bytes=audio_bytes,
                filename=f"tts_11labs_{uuid.uuid4().hex[:8]}.mp3",
                mime_type="audio/mpeg",
                duration_seconds=round(duration, 2),
                sample_rate=44100,
                generation_time_seconds=round(time.time() - start, 2),
                metadata={
                    "provider": self.name,
                    "mode": "live",
                    "voice_id": voice_id,
                    "model_id": model_id,
                    "text_length": len(request.text),
                    "language": request.language,
                },
            )

        except httpx.TimeoutException:
            return AudioResult(
                success=False,
                error="ElevenLabs API timeout",
                generation_time_seconds=round(time.time() - start, 2),
            )
        except Exception as e:
            return AudioResult(
                success=False,
                error=f"ElevenLabs error: {e}",
                generation_time_seconds=round(time.time() - start, 2),
            )

    def _generate_simulated(self, request: TTSRequest) -> AudioResult:
        """Simulated ElevenLabs response."""
        start = time.time()
        time.sleep(min(len(request.text) * 0.005, 1.0))
        duration = len(request.text) * 0.06
        fake_audio = hashlib.sha256(f"11labs-{request.text}-{time.time()}".encode()).digest() * 32

        return AudioResult(
            success=True,
            output_bytes=fake_audio,
            filename=f"tts_11labs_{uuid.uuid4().hex[:8]}.mp3",
            mime_type="audio/mpeg",
            duration_seconds=round(duration, 2),
            sample_rate=44100,
            generation_time_seconds=round(time.time() - start, 2),
            metadata={
                "provider": self.name,
                "mode": "simulated",
                "text_length": len(request.text),
                "voice_id": ELEVENLABS_DEFAULT_VOICE,
                "language": request.language,
            },
        )

    def cancel(self, job_id: str) -> bool:
        return True

    # ─── ElevenLabs-specific helpers ──────────────────────────────────────

    def list_voices(self) -> list[dict]:
        """List available voices from ElevenLabs API."""
        if not ELEVENLABS_API_KEY:
            return [{"voice_id": "simulation", "name": "Simulated Voice"}]

        try:
            resp = httpx.get(
                f"{ELEVENLABS_BASE_URL}/voices",
                headers={"xi-api-key": ELEVENLABS_API_KEY},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("voices", [])
        except Exception as e:
            logger.warning(f"Failed to list ElevenLabs voices: {e}")
        return []
