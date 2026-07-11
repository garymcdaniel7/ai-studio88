"""ElevenLabs Provider — Voice TTS + Video generation via ElevenLabs API."""

from backend.providers.elevenlabs.client import ElevenLabsClient, ElevenLabsClientError

__all__ = ["ElevenLabsClient", "ElevenLabsClientError"]
