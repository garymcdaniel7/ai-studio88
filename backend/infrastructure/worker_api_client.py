"""Worker API Client — dispatches operations to the GPU worker's HTTP API.

The Worker API runs on the GPU instance (port 7860) and handles:
- Image generation (ComfyUI)
- FFmpeg video transforms
- Ollama LLM chat
- MOSS TTS voice generation
- Model management

This client resolves the worker URL from:
1. WORKER_API_URL env var (explicit override)
2. Active worker session (ssh_host:7860)
3. Returns None if no worker available

Usage:
    client = get_worker_client()
    if client:
        result = client.generate_image(prompt="...", model="flux-dev")
    else:
        # No worker available — return 503 or use fallback
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

WORKER_API_URL = os.getenv("WORKER_API_URL", "")
WORKER_API_PORT = int(os.getenv("WORKER_API_PORT", "7860"))
WORKER_API_TIMEOUT = int(os.getenv("WORKER_API_TIMEOUT", "300"))


class WorkerAPIClient:
    """Client for the GPU Worker HTTP API."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=WORKER_API_TIMEOUT)

    def health(self) -> dict:
        """Check worker health."""
        try:
            resp = self._client.get("/health")
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            return {"status": "unreachable", "error": str(e)[:100]}
        return {"status": "unhealthy"}

    def is_available(self) -> bool:
        """Quick check if worker is reachable."""
        try:
            resp = self._client.get("/", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def generate_image(self, **kwargs: Any) -> dict:
        """Generate an image via ComfyUI on the worker.

        Args: prompt, negative_prompt, model, width, height, steps, cfg, seed, lora, lora_strength
        Returns: {success, image_base64, filename, generation_time, ...}
        """
        resp = self._client.post("/generate/image", json=kwargs, timeout=WORKER_API_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        raise WorkerAPIError(f"Generation failed: HTTP {resp.status_code} — {resp.text[:200]}")

    def ffmpeg_transform(self, **kwargs: Any) -> dict:
        """Apply ffmpeg video transforms on the worker.

        Args: source_url, trim_start, trim_end, speed, resolution, color_grade, text_overlay
        Returns: {success, video_base64, size_bytes, filename}
        """
        resp = self._client.post("/ffmpeg/transform", json=kwargs, timeout=WORKER_API_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        raise WorkerAPIError(f"FFmpeg transform failed: HTTP {resp.status_code} — {resp.text[:200]}")

    def ollama_chat(self, messages: list[dict], model: str = "llama3.1:8b", **kwargs: Any) -> dict:
        """Chat via Ollama on the worker.

        Returns: raw Ollama response
        """
        payload = {"model": model, "messages": messages, "stream": False, **kwargs}
        resp = self._client.post("/ollama/chat", json=payload, timeout=120)
        if resp.status_code == 200:
            return resp.json()
        raise WorkerAPIError(f"Ollama chat failed: HTTP {resp.status_code} — {resp.text[:200]}")

    def tts_generate(self, text: str, **kwargs: Any) -> dict:
        """Generate speech via MOSS-TTS on the worker.

        Returns: {success, audio_base64, mime_type}
        """
        payload = {"text": text, **kwargs}
        resp = self._client.post("/tts/generate", json=payload, timeout=120)
        if resp.status_code == 200:
            return resp.json()
        raise WorkerAPIError(f"TTS failed: HTTP {resp.status_code} — {resp.text[:200]}")

    def list_models(self) -> dict:
        """List models loaded on the worker."""
        resp = self._client.get("/models/loaded", timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return {"models": {}}

    def download_model(self, url: str, destination: str) -> dict:
        """Download a model from B2 to the worker.

        Returns: {success, path, size_mb}
        """
        resp = self._client.post("/models/download", json={"url": url, "destination": destination}, timeout=600)
        if resp.status_code == 200:
            return resp.json()
        raise WorkerAPIError(f"Model download failed: HTTP {resp.status_code} — {resp.text[:200]}")


class WorkerAPIError(Exception):
    """Raised when Worker API call fails."""
    pass


# =============================================================================
# Factory — resolves worker URL from env or active session
# =============================================================================

_cached_client: WorkerAPIClient | None = None
_cached_url: str = ""


def get_worker_client() -> WorkerAPIClient | None:
    """Get a WorkerAPIClient connected to the active GPU worker.

    Resolves URL from:
    1. WORKER_API_URL env var (explicit override for Vercel)
    2. Active worker session (worker_orchestrator)
    3. Returns None if no worker available
    """
    global _cached_client, _cached_url

    # Try explicit env var first
    url = WORKER_API_URL
    if not url:
        # Try to resolve from active worker session
        try:
            from backend.infrastructure.worker_orchestrator import get_orchestrator

            orchestrator = get_orchestrator()
            if orchestrator.session and orchestrator.session.ssh_host:
                url = f"http://{orchestrator.session.ssh_host}:{WORKER_API_PORT}"
        except Exception:
            pass

    if not url:
        return None

    # Cache the client if URL hasn't changed
    if url != _cached_url or _cached_client is None:
        _cached_client = WorkerAPIClient(url)
        _cached_url = url

    return _cached_client


def get_worker_url() -> str | None:
    """Get the resolved Worker API URL (for display/debugging)."""
    if WORKER_API_URL:
        return WORKER_API_URL
    try:
        from backend.infrastructure.worker_orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        if orchestrator.session and orchestrator.session.ssh_host:
            return f"http://{orchestrator.session.ssh_host}:{WORKER_API_PORT}"
    except Exception:
        pass
    return None
