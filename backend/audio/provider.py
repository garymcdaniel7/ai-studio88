"""Voice, Music, SFX, and Lip Sync Provider Interfaces.

All audio backends implement these. AI Studio dispatches through them
without knowing provider-specific details.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# =============================================================================
# Data models
# =============================================================================


@dataclass
class TTSRequest:
    text: str = ""
    voice_profile_id: str = ""
    language: str = "en"
    speed: float = 1.0
    pitch: float = 1.0
    emotion: str = "neutral"
    style: str = "narrative"
    extra: dict = field(default_factory=dict)


@dataclass
class AudioResult:
    success: bool = False
    output_bytes: bytes | None = None
    filename: str = ""
    mime_type: str = "audio/mp3"
    duration_seconds: float = 0.0
    sample_rate: int = 44100
    generation_time_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class LipSyncRequest:
    video_bytes: bytes | None = None
    audio_bytes: bytes | None = None
    video_asset_id: str = ""
    audio_asset_id: str = ""
    model: str = "wav2lip"
    extra: dict = field(default_factory=dict)


@dataclass
class LipSyncResult:
    success: bool = False
    output_bytes: bytes | None = None
    filename: str = ""
    mime_type: str = "video/mp4"
    duration_seconds: float = 0.0
    generation_time_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)
    error: str | None = None


# =============================================================================
# Provider Interfaces
# =============================================================================


class VoiceProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    def health(self) -> dict: ...
    @abstractmethod
    def capabilities(self) -> dict: ...
    @abstractmethod
    def generate_speech(self, request: TTSRequest) -> AudioResult: ...
    @abstractmethod
    def cancel(self, job_id: str) -> bool: ...


class MusicProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    def health(self) -> dict: ...
    @abstractmethod
    def generate(self, prompt: str, duration: float, mood: str) -> AudioResult: ...


class SFXProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    def health(self) -> dict: ...
    @abstractmethod
    def generate(self, description: str, duration: float) -> AudioResult: ...


class LipSyncProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    def health(self) -> dict: ...
    @abstractmethod
    def sync(self, request: LipSyncRequest) -> LipSyncResult: ...
    @abstractmethod
    def cancel(self, job_id: str) -> bool: ...


# =============================================================================
# Simulated Providers
# =============================================================================


class SimulatedVoiceProvider(VoiceProvider):
    @property
    def name(self) -> str:
        return "simulation"

    def health(self):
        return {"healthy": True, "provider": self.name}

    def capabilities(self):
        return {
            "languages": ["en", "es", "fr", "de", "ja"],
            "voices": 50,
            "max_chars": 5000,
            "styles": ["narrative", "conversational", "dramatic"],
        }

    def generate_speech(self, request: TTSRequest) -> AudioResult:
        start = time.time()
        # Simulate ~0.1s per 10 chars
        time.sleep(min(len(request.text) * 0.01, 2.0))
        duration = len(request.text) * 0.06  # ~60ms per character
        fake_audio = hashlib.sha256(f"tts-{request.text}-{time.time()}".encode()).digest() * 16
        return AudioResult(
            success=True,
            output_bytes=fake_audio,
            filename=f"tts_{uuid.uuid4().hex[:8]}.mp3",
            mime_type="audio/mp3",
            duration_seconds=round(duration, 2),
            sample_rate=44100,
            generation_time_seconds=round(time.time() - start, 2),
            metadata={
                "provider": self.name,
                "text": request.text[:100],
                "language": request.language,
                "emotion": request.emotion,
            },
        )

    def cancel(self, job_id) -> bool:
        return True


class SimulatedMusicProvider(MusicProvider):
    @property
    def name(self) -> str:
        return "simulation"

    def health(self):
        return {"healthy": True, "provider": self.name}

    def generate(self, prompt, duration, mood):
        fake = hashlib.sha256(f"music-{prompt}-{mood}".encode()).digest() * 32
        return AudioResult(
            success=True,
            output_bytes=fake,
            filename=f"music_{uuid.uuid4().hex[:8]}.mp3",
            duration_seconds=duration,
            generation_time_seconds=0.5,
            metadata={"provider": self.name, "prompt": prompt, "mood": mood},
        )


class SimulatedSFXProvider(SFXProvider):
    @property
    def name(self) -> str:
        return "simulation"

    def health(self):
        return {"healthy": True, "provider": self.name}

    def generate(self, description, duration):
        fake = hashlib.sha256(f"sfx-{description}".encode()).digest() * 8
        return AudioResult(
            success=True,
            output_bytes=fake,
            filename=f"sfx_{uuid.uuid4().hex[:8]}.wav",
            mime_type="audio/wav",
            duration_seconds=duration,
            generation_time_seconds=0.3,
            metadata={"provider": self.name, "description": description},
        )


class SimulatedLipSyncProvider(LipSyncProvider):
    @property
    def name(self) -> str:
        return "simulation"

    def health(self):
        return {"healthy": True, "provider": self.name}

    def sync(self, request: LipSyncRequest) -> LipSyncResult:
        fake = hashlib.sha256(f"lipsync-{time.time()}".encode()).digest() * 64
        return LipSyncResult(
            success=True,
            output_bytes=fake,
            filename=f"lipsync_{uuid.uuid4().hex[:8]}.mp4",
            duration_seconds=5.0,
            generation_time_seconds=1.0,
            metadata={"provider": self.name, "model": request.model},
        )

    def cancel(self, job_id) -> bool:
        return True


# =============================================================================
# Provider Registries
# =============================================================================

VOICE_PROVIDERS: dict[str, type[VoiceProvider]] = {
    "simulation": SimulatedVoiceProvider,
    # Future: "xtts", "openvoice", "fish_speech", "rvc"
}


def _register_elevenlabs() -> None:
    """Register ElevenLabs provider."""
    from backend.audio.elevenlabs_provider import ElevenLabsVoiceProvider

    VOICE_PROVIDERS["elevenlabs"] = ElevenLabsVoiceProvider


_register_elevenlabs()


def _register_xtts() -> None:
    """Register XTTS local voice cloning provider."""
    from backend.audio.xtts_provider import XTTSProvider

    VOICE_PROVIDERS["xtts"] = XTTSProvider


_register_xtts()

MUSIC_PROVIDERS: dict[str, type[MusicProvider]] = {
    "simulation": SimulatedMusicProvider,
    # Future: "udio", "stable_audio"
}


def _register_suno() -> None:
    from backend.audio.suno_provider import SunoMusicProvider

    MUSIC_PROVIDERS["suno"] = SunoMusicProvider


_register_suno()

SFX_PROVIDERS: dict[str, type[SFXProvider]] = {
    "simulation": SimulatedSFXProvider,
    # Future: "elevenlabs_sfx", "stable_audio"
}

LIP_SYNC_PROVIDERS: dict[str, type[LipSyncProvider]] = {
    "simulation": SimulatedLipSyncProvider,
    # Future: "wav2lip", "sadtalker", "musetalk", "synclabs"
}


def get_voice_provider(name: str | None = None) -> VoiceProvider:
    import os

    provider_name = name or os.getenv("VOICE_PROVIDER", "simulation")
    cls = VOICE_PROVIDERS.get(provider_name)
    if not cls:
        raise ValueError(
            f"Unknown voice provider: {provider_name}. Available: {list(VOICE_PROVIDERS.keys())}"
        )
    return cls()


def get_lip_sync_provider(name: str = "simulation") -> LipSyncProvider:
    cls = LIP_SYNC_PROVIDERS.get(name)
    if not cls:
        raise ValueError(f"Unknown lip sync provider: {name}")
    return cls()
