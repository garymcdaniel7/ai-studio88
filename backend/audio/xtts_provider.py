"""XTTS Voice Provider — Local voice cloning via Coqui XTTS-v2.

Free, open-source alternative to ElevenLabs. Runs on GPU worker.
Supports voice cloning from a 10-second audio sample.

Architecture:
- XTTS-v2 runs on the GPU worker (same instance as ComfyUI)
- Accessed via HTTP API on port 8199
- Voice samples stored in B2, downloaded to worker on demand

Setup on GPU worker:
  pip install TTS
  tts --model_name tts_models/multilingual/multi-dataset/xtts_v2 --list_speaker_idxs
  tts-server --model_name tts_models/multilingual/multi-dataset/xtts_v2 --port 8199
"""

from __future__ import annotations

import logging
import os
import time
import uuid

import httpx

from backend.audio.provider import AudioResult, TTSRequest, VoiceProvider

logger = logging.getLogger(__name__)

XTTS_BASE_URL = os.getenv("XTTS_BASE_URL", "http://localhost:8199")
XTTS_LIVE = os.getenv("XTTS_LIVE", "false").lower() == "true"


class XTTSProvider(VoiceProvider):
    """Local XTTS-v2 voice cloning provider.

    Free, unlimited, supports voice cloning from short audio samples.
    Requires GPU worker with XTTS installed.
    """

    @property
    def name(self) -> str:
        return "xtts"

    def health(self) -> dict:
        if not XTTS_LIVE:
            return {
                "healthy": True,
                "provider": self.name,
                "mode": "disabled",
                "message": "Set XTTS_LIVE=true and start XTTS on GPU worker",
            }
        try:
            resp = httpx.get(f"{XTTS_BASE_URL}/docs", timeout=5)
            return {
                "healthy": resp.status_code == 200,
                "provider": self.name,
                "mode": "live",
                "url": XTTS_BASE_URL,
            }
        except Exception as e:
            return {"healthy": False, "provider": self.name, "error": str(e)[:100]}

    def capabilities(self) -> dict:
        return {
            "provider": self.name,
            "languages": [
                "en",
                "es",
                "fr",
                "de",
                "it",
                "pt",
                "pl",
                "tr",
                "ru",
                "nl",
                "cs",
                "ar",
                "zh",
                "ja",
                "ko",
                "hi",
            ],
            "voices": "unlimited (clone any voice)",
            "max_chars": 10000,
            "features": ["voice_cloning", "multilingual", "emotion_control"],
            "cost": "free (runs locally on GPU)",
            "live_mode": XTTS_LIVE,
        }

    def generate_speech(self, request: TTSRequest) -> AudioResult:
        """Generate speech using XTTS-v2.

        If a voice sample is provided, clones that voice.
        Otherwise uses a default speaker.
        """
        if not XTTS_LIVE:
            return self._simulate(request)
        return self._generate_live(request)

    def _generate_live(self, request: TTSRequest) -> AudioResult:
        """Real XTTS generation via the TTS server API."""
        start = time.time()

        speaker_wav = request.extra.get("speaker_wav", "")
        language = request.language or "en"

        try:
            if speaker_wav:
                # Voice cloning mode
                resp = httpx.post(
                    f"{XTTS_BASE_URL}/tts_to_audio",
                    json={
                        "text": request.text,
                        "speaker_wav": speaker_wav,
                        "language": language,
                    },
                    timeout=60,
                )
            else:
                # Default speaker mode
                resp = httpx.post(
                    f"{XTTS_BASE_URL}/tts_to_audio",
                    json={
                        "text": request.text,
                        "language": language,
                    },
                    timeout=60,
                )

            if resp.status_code == 200:
                audio_bytes = resp.content
                filename = f"xtts_{uuid.uuid4().hex[:8]}.wav"
                elapsed = time.time() - start

                return AudioResult(
                    success=True,
                    output_bytes=audio_bytes,
                    filename=filename,
                    mime_type="audio/wav",
                    duration_seconds=round(len(audio_bytes) / (22050 * 2), 2),  # rough estimate
                    metadata={
                        "provider": "xtts",
                        "language": language,
                        "cloned": bool(speaker_wav),
                        "generation_time": round(elapsed, 2),
                    },
                )
            else:
                return AudioResult(
                    success=False,
                    error=f"XTTS server error: {resp.status_code} {resp.text[:100]}",
                )
        except httpx.ConnectError:
            return AudioResult(
                success=False,
                error=f"XTTS not reachable at {XTTS_BASE_URL}. Start it on the GPU worker.",
            )
        except Exception as e:
            return AudioResult(success=False, error=f"XTTS error: {str(e)[:100]}")

    def _simulate(self, request: TTSRequest) -> AudioResult:
        """Simulated XTTS output."""
        import hashlib

        fake_audio = hashlib.sha256(f"xtts-{request.text}-{time.time()}".encode()).digest() * 100
        filename = f"xtts_sim_{uuid.uuid4().hex[:8]}.wav"
        return AudioResult(
            success=True,
            output_bytes=fake_audio,
            filename=filename,
            mime_type="audio/wav",
            duration_seconds=round(len(request.text) / 15, 2),
            metadata={"provider": "xtts", "simulated": True},
        )


def clone_voice(audio_sample_path: str, name: str = "cloned") -> dict:
    """Clone a voice from an audio sample.

    Args:
        audio_sample_path: Path to a 10+ second audio file
        name: Name for the cloned voice

    Returns:
        Voice profile dict with speaker_wav path
    """
    # In production: upload sample to GPU worker, store reference
    return {
        "name": name,
        "speaker_wav": audio_sample_path,
        "provider": "xtts",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
