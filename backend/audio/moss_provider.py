"""MOSS-TTS Provider — Voice cloning + voice generation via MOSS-TTS family.

Supports:
- MOSS-TTS-Nano (100M): Lightweight CPU-capable TTS with voice cloning from 6s audio
- MOSS-VoiceGenerator (1.7B): Creates new voice identities from text descriptions
- MOSS-TTS (8B): Full flagship TTS with zero-shot cloning (GPU required)

Architecture:
- MOSS-TTS-Nano runs on the GPU worker via HTTP API (port 18083)
- Voice samples and generated voices are stored in B2
- The provider communicates with the worker via SSH tunnel or direct URL

Usage:
    provider = MossTTSProvider()
    # Generate speech with a cloned voice
    result = provider.generate_speech(text="Hello world", voice_sample_url="...")
    # Create a new voice identity from description
    voice = provider.create_voice(description="A warm female voice, mid-30s, confident")
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration
MOSS_TTS_BASE_URL = os.getenv("MOSS_TTS_BASE_URL", "http://localhost:18083")
MOSS_TTS_ENABLED = os.getenv("MOSS_TTS_ENABLED", "false").lower() == "true"


@dataclass
class MossVoiceResult:
    """Result from MOSS voice generation."""

    success: bool
    audio_bytes: bytes | None = None
    filename: str = ""
    duration_seconds: float = 0.0
    sample_rate: int = 48000
    error: str | None = None
    metadata: dict | None = None


@dataclass
class MossVoiceIdentity:
    """A generated voice identity."""

    id: str
    name: str
    description: str
    sample_audio_bytes: bytes | None = None
    sample_filename: str = ""
    provider: str = "moss-voicegenerator"
    metadata: dict | None = None


class MossTTSProvider:
    """Provider for MOSS-TTS family models.

    Operates in two modes:
    - Live: connects to MOSS-TTS-Nano running on GPU worker (port 18083)
    - Simulation: returns placeholder data when worker is unavailable
    """

    def __init__(self) -> None:
        self.base_url = MOSS_TTS_BASE_URL
        self.enabled = MOSS_TTS_ENABLED
        self.name = "moss-tts"

    def health(self) -> dict:
        """Check if MOSS-TTS service is reachable."""
        if not self.enabled:
            return {"status": "disabled", "provider": self.name}
        try:
            resp = httpx.get(f"{self.base_url}/health", timeout=5)
            if resp.status_code == 200:
                return {"status": "healthy", "provider": self.name, "url": self.base_url}
        except Exception as e:
            return {"status": "unreachable", "provider": self.name, "error": str(e)}
        return {"status": "unhealthy", "provider": self.name}

    def generate_speech(
        self,
        text: str,
        voice_sample_path: str | None = None,
        language: str = "en",
        speed: float = 1.0,
    ) -> MossVoiceResult:
        """Generate speech from text, optionally cloning a voice from a sample.

        Args:
            text: Text to synthesize
            voice_sample_path: Path/URL to a 6+ second audio sample for voice cloning
            language: Language code (en, zh, etc.)
            speed: Speech speed multiplier

        Returns:
            MossVoiceResult with audio bytes or error
        """
        if not self.enabled:
            return self._simulate_speech(text)

        start = time.time()
        try:
            payload = {
                "text": text,
                "language": language,
                "speed": speed,
            }
            if voice_sample_path:
                payload["prompt_audio_path"] = voice_sample_path

            resp = httpx.post(
                f"{self.base_url}/generate",
                json=payload,
                timeout=120.0,
            )
            if resp.status_code == 200:
                # Response may be audio bytes directly or JSON with download URL
                content_type = resp.headers.get("content-type", "")
                if "audio" in content_type:
                    audio_bytes = resp.content
                else:
                    data = resp.json()
                    audio_url = data.get("audio_url", "")
                    if audio_url:
                        audio_resp = httpx.get(audio_url, timeout=30)
                        audio_bytes = audio_resp.content
                    else:
                        return MossVoiceResult(success=False, error="No audio in response")

                filename = f"moss_tts_{uuid.uuid4().hex[:8]}.wav"
                duration = len(audio_bytes) / (48000 * 2)  # Approximate for 48kHz 16-bit mono

                return MossVoiceResult(
                    success=True,
                    audio_bytes=audio_bytes,
                    filename=filename,
                    duration_seconds=round(duration, 2),
                    metadata={
                        "provider": self.name,
                        "mode": "live",
                        "text_length": len(text),
                        "language": language,
                        "generation_time": round(time.time() - start, 2),
                        "voice_cloned": voice_sample_path is not None,
                    },
                )
            else:
                return MossVoiceResult(
                    success=False,
                    error=f"MOSS-TTS returned {resp.status_code}: {resp.text[:200]}",
                )
        except Exception as e:
            logger.warning(f"MOSS-TTS generation failed: {e}")
            return MossVoiceResult(success=False, error=str(e))

    def create_voice(
        self,
        description: str,
        name: str = "",
        sample_text: str = "Hello, this is a sample of my voice.",
    ) -> MossVoiceIdentity:
        """Create a new voice identity from a text description.

        Uses MOSS-VoiceGenerator to design a voice from free-form text.

        Args:
            description: Voice description (e.g. "A warm female voice, mid-30s, confident")
            name: Name for this voice identity
            sample_text: Text to generate as a sample clip

        Returns:
            MossVoiceIdentity with the generated voice sample
        """
        voice_id = uuid.uuid4().hex[:12]
        voice_name = name or f"Voice_{voice_id[:6]}"

        if not self.enabled:
            return self._simulate_voice_creation(description, voice_name, voice_id)

        try:
            payload = {
                "description": description,
                "text": sample_text,
            }
            resp = httpx.post(
                f"{self.base_url}/create-voice",
                json=payload,
                timeout=180.0,
            )
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "")
                if "audio" in content_type:
                    audio_bytes = resp.content
                else:
                    data = resp.json()
                    audio_url = data.get("audio_url", "")
                    if audio_url:
                        audio_resp = httpx.get(audio_url, timeout=30)
                        audio_bytes = audio_resp.content
                    else:
                        audio_bytes = None

                return MossVoiceIdentity(
                    id=voice_id,
                    name=voice_name,
                    description=description,
                    sample_audio_bytes=audio_bytes,
                    sample_filename=f"moss_voice_{voice_id}.wav",
                    metadata={
                        "provider": "moss-voicegenerator",
                        "description": description,
                        "sample_text": sample_text,
                    },
                )
            else:
                logger.warning(f"MOSS-VoiceGenerator returned {resp.status_code}")
                return self._simulate_voice_creation(description, voice_name, voice_id)
        except Exception as e:
            logger.warning(f"MOSS-VoiceGenerator failed: {e}")
            return self._simulate_voice_creation(description, voice_name, voice_id)

    def list_available_voices(self) -> list[dict]:
        """List voices available on the MOSS-TTS worker."""
        if not self.enabled:
            return [{"id": "simulation", "name": "Simulated MOSS Voice", "provider": "moss-tts"}]
        try:
            resp = httpx.get(f"{self.base_url}/voices", timeout=10)
            if resp.status_code == 200:
                return resp.json().get("voices", [])
        except Exception:
            pass
        return []

    # ─── Simulation fallbacks ─────────────────────────────────────────────

    def _simulate_speech(self, text: str) -> MossVoiceResult:
        """Return simulated audio for development/testing — produces a valid short WAV."""
        import struct

        time.sleep(min(len(text) * 0.003, 0.5))

        # Generate a valid WAV file (silent, 1 second at 24kHz 16-bit mono)
        sample_rate = 24000
        duration = min(max(len(text) * 0.06, 1.0), 5.0)
        num_samples = int(sample_rate * duration)
        # WAV header + silent samples
        wav_data = b"RIFF"
        data_size = num_samples * 2  # 16-bit = 2 bytes per sample
        file_size = 36 + data_size
        wav_data += struct.pack("<I", file_size)
        wav_data += b"WAVEfmt "
        wav_data += struct.pack("<I", 16)  # chunk size
        wav_data += struct.pack("<H", 1)   # PCM
        wav_data += struct.pack("<H", 1)   # mono
        wav_data += struct.pack("<I", sample_rate)
        wav_data += struct.pack("<I", sample_rate * 2)  # byte rate
        wav_data += struct.pack("<H", 2)   # block align
        wav_data += struct.pack("<H", 16)  # bits per sample
        wav_data += b"data"
        wav_data += struct.pack("<I", data_size)
        wav_data += b"\x00" * data_size  # Silent audio

        return MossVoiceResult(
            success=True,
            audio_bytes=wav_data,
            filename=f"moss_sim_{uuid.uuid4().hex[:8]}.wav",
            duration_seconds=round(duration, 2),
            metadata={
                "provider": self.name,
                "mode": "simulated",
                "text_length": len(text),
                "note": "MOSS-TTS not enabled. Set MOSS_TTS_ENABLED=true and ensure worker is running.",
            },
        )

    def _simulate_voice_creation(
        self, description: str, name: str, voice_id: str
    ) -> MossVoiceIdentity:
        """Return simulated voice identity with a valid WAV sample."""
        import struct

        # Generate a valid 1-second silent WAV
        sample_rate = 24000
        num_samples = sample_rate  # 1 second
        data_size = num_samples * 2
        wav_data = b"RIFF"
        wav_data += struct.pack("<I", 36 + data_size)
        wav_data += b"WAVEfmt "
        wav_data += struct.pack("<I", 16)
        wav_data += struct.pack("<H", 1)   # PCM
        wav_data += struct.pack("<H", 1)   # mono
        wav_data += struct.pack("<I", sample_rate)
        wav_data += struct.pack("<I", sample_rate * 2)
        wav_data += struct.pack("<H", 2)
        wav_data += struct.pack("<H", 16)
        wav_data += b"data"
        wav_data += struct.pack("<I", data_size)
        wav_data += b"\x00" * data_size

        return MossVoiceIdentity(
            id=voice_id,
            name=name,
            description=description,
            sample_audio_bytes=wav_data,
            sample_filename=f"moss_voice_{voice_id}_sim.wav",
            metadata={
                "provider": "moss-voicegenerator",
                "mode": "simulated",
                "description": description,
                "note": "Simulated. Enable MOSS-TTS worker for real voice generation.",
            },
        )
