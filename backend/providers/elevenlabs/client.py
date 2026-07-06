"""ElevenLabs API Client — Voice TTS + Video Generation.

Provides:
- Text-to-speech (TTS) with voice cloning
- Video generation via Seedance 2.0 (text-to-video, image-to-video)
- Voice cloning from audio samples
- Lip-sync on existing video

API docs: https://elevenlabs.io/docs/api-reference
Video is async: POST to generate → poll for completion.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx

ELEVENLABS_API_BASE = "https://api.elevenlabs.io"


class ElevenLabsClientError(Exception):
    """Raised when ElevenLabs API returns an error."""


class ElevenLabsClient:
    """Client for ElevenLabs TTS and Video generation API.

    Supports:
    - Text-to-speech (multiple voices, voice cloning)
    - Text-to-video (Seedance 2.0)
    - Image-to-video (Seedance 2.0)
    - Lip-sync (overlay speech on video)
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY", "")
        if not self.api_key:
            raise ElevenLabsClientError(
                "No ElevenLabs API key found. Set ELEVENLABS_API_KEY in .env"
            )
        self._headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    # ─── Text-to-Speech ───────────────────────────────────────────────────

    def generate_speech(
        self,
        text: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",  # Rachel
        model_id: str = "eleven_turbo_v2_5",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ) -> bytes:
        """Generate speech audio from text.

        Args:
            text: Text to speak
            voice_id: ElevenLabs voice ID
            model_id: TTS model (eleven_turbo_v2_5, eleven_multilingual_v2)
            stability: Voice stability (0-1)
            similarity_boost: Voice similarity (0-1)

        Returns:
            Audio bytes (MP3)
        """
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
            },
        }

        try:
            resp = httpx.post(
                f"{ELEVENLABS_API_BASE}/v1/text-to-speech/{voice_id}",
                headers=self._headers,
                json=payload,
                timeout=30,
            )
        except httpx.HTTPError as e:
            raise ElevenLabsClientError(f"Network error: {e}")

        if resp.status_code != 200:
            raise ElevenLabsClientError(
                f"TTS failed ({resp.status_code}): {resp.text}"
            )
        return resp.content

    # ─── Video Generation (Seedance 2.0) ─────────────────────────────────

    def generate_video_from_text(
        self,
        prompt: str,
        model: str = "seedance-2.0",
        duration: int = 5,
        resolution: str = "1080p",
        aspect_ratio: str = "16:9",
        audio_enabled: bool = True,
    ) -> dict:
        """Submit a text-to-video generation request.

        Uses ElevenLabs' Seedance 2.0 model for video generation.

        Args:
            prompt: Description of the video
            model: Video model (seedance-2.0)
            duration: Video length in seconds (4-15)
            resolution: 480p, 720p, 1080p
            aspect_ratio: 16:9, 9:16, 1:1, 4:3, 3:4, 21:9
            audio_enabled: Whether to generate audio with the video

        Returns:
            Dict with generation_id for polling
        """
        payload: dict[str, Any] = {
            "prompt": prompt,
            "model": model,
            "settings": {
                "duration": duration,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "audio_enabled": audio_enabled,
            },
        }

        try:
            resp = httpx.post(
                f"{ELEVENLABS_API_BASE}/v1/video/generations",
                headers=self._headers,
                json=payload,
                timeout=30,
            )
        except httpx.HTTPError as e:
            raise ElevenLabsClientError(f"Network error: {e}")

        if resp.status_code not in (200, 201, 202):
            raise ElevenLabsClientError(
                f"Video generation failed ({resp.status_code}): {resp.text}"
            )
        return resp.json()

    def generate_video_from_image(
        self,
        image_url: str,
        prompt: str = "",
        model: str = "seedance-2.0",
        duration: int = 5,
        resolution: str = "1080p",
    ) -> dict:
        """Submit an image-to-video generation request.

        Args:
            image_url: URL of the start frame image
            prompt: Optional motion/action description
            model: Video model
            duration: Length in seconds

        Returns:
            Dict with generation_id for polling
        """
        payload: dict[str, Any] = {
            "model": model,
            "settings": {
                "duration": duration,
                "resolution": resolution,
            },
            "start_frame": {"url": image_url},
        }
        if prompt:
            payload["prompt"] = prompt

        try:
            resp = httpx.post(
                f"{ELEVENLABS_API_BASE}/v1/video/generations",
                headers=self._headers,
                json=payload,
                timeout=30,
            )
        except httpx.HTTPError as e:
            raise ElevenLabsClientError(f"Network error: {e}")

        if resp.status_code not in (200, 201, 202):
            raise ElevenLabsClientError(
                f"Video generation failed ({resp.status_code}): {resp.text}"
            )
        return resp.json()

    # ─── Video Task Polling ───────────────────────────────────────────────

    def get_video_status(self, generation_id: str) -> dict:
        """Get the status of a video generation task."""
        try:
            resp = httpx.get(
                f"{ELEVENLABS_API_BASE}/v1/video/generations/{generation_id}",
                headers=self._headers,
                timeout=30,
            )
        except httpx.HTTPError as e:
            raise ElevenLabsClientError(f"Network error: {e}")

        if resp.status_code != 200:
            raise ElevenLabsClientError(
                f"Status check failed ({resp.status_code}): {resp.text}"
            )
        return resp.json()

    def wait_for_video(
        self,
        generation_id: str,
        timeout: int = 300,
        poll_interval: int = 5,
    ) -> dict:
        """Poll a video generation until completion.

        Returns:
            Final result with download URL
        """
        start = time.time()
        while time.time() - start < timeout:
            result = self.get_video_status(generation_id)
            status = result.get("status", "")

            if status in ("completed", "done"):
                return result
            if status in ("failed", "error"):
                raise ElevenLabsClientError(
                    f"Video generation failed: {result.get('error', 'Unknown')}"
                )

            time.sleep(poll_interval)

        raise ElevenLabsClientError(
            f"Video generation timed out after {timeout}s"
        )

    # ─── Lip Sync ─────────────────────────────────────────────────────────

    def lip_sync(
        self,
        video_url: str,
        audio_url: str,
    ) -> dict:
        """Apply lip-sync to a video using audio.

        Args:
            video_url: URL of the source video
            audio_url: URL of the audio to sync

        Returns:
            Dict with generation_id for polling
        """
        payload = {
            "video_url": video_url,
            "audio_url": audio_url,
        }

        try:
            resp = httpx.post(
                f"{ELEVENLABS_API_BASE}/v1/video/lip-sync",
                headers=self._headers,
                json=payload,
                timeout=30,
            )
        except httpx.HTTPError as e:
            raise ElevenLabsClientError(f"Network error: {e}")

        if resp.status_code not in (200, 201, 202):
            raise ElevenLabsClientError(
                f"Lip sync failed ({resp.status_code}): {resp.text}"
            )
        return resp.json()

    # ─── Voice Management ─────────────────────────────────────────────────

    def list_voices(self) -> list[dict]:
        """List all available voices."""
        try:
            resp = httpx.get(
                f"{ELEVENLABS_API_BASE}/v1/voices",
                headers=self._headers,
                timeout=15,
            )
        except httpx.HTTPError as e:
            raise ElevenLabsClientError(f"Network error: {e}")

        if resp.status_code != 200:
            raise ElevenLabsClientError(f"List voices failed: {resp.text}")

        data = resp.json()
        return data.get("voices", [])

    # ─── Account / Health ─────────────────────────────────────────────────

    def get_subscription_info(self) -> dict:
        """Get subscription/usage info."""
        try:
            resp = httpx.get(
                f"{ELEVENLABS_API_BASE}/v1/user/subscription",
                headers=self._headers,
                timeout=15,
            )
        except httpx.HTTPError as e:
            raise ElevenLabsClientError(f"Network error: {e}")

        if resp.status_code != 200:
            raise ElevenLabsClientError(f"Subscription check failed: {resp.text}")
        return resp.json()

    def health_check(self) -> dict:
        """Validate API key and check service availability."""
        try:
            sub = self.get_subscription_info()
            return {
                "connected": True,
                "tier": sub.get("tier", "unknown"),
                "character_count": sub.get("character_count", 0),
                "character_limit": sub.get("character_limit", 0),
            }
        except ElevenLabsClientError as e:
            return {"connected": False, "error": str(e)}
