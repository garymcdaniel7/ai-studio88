"""KLING AI API Client.

Provides text-to-video, image-to-video, and text-to-image generation
via KLING's async API (submit → poll pattern).

KLING API flow:
1. POST /v1/videos/generations (or /v1/images/generations)
2. Returns task_id immediately
3. Poll GET /v1/tasks/{task_id} until status = "completed"
4. Download result from output_url

Supports KLING 3.0, 3.0 Turbo, and 2.6 models.

API docs: https://docs.klingai.com (official) or third-party aggregators.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx

# KLING official API base (via EvoLink or direct Kuaishou)
KLING_API_BASE = "https://api.klingai.com"


class KlingClientError(Exception):
    """Raised when KLING API returns an error."""


class KlingClient:
    """Client for the KLING AI video/image generation API.

    Supports:
    - Text-to-video (t2v)
    - Image-to-video (i2v)
    - Text-to-image (t2i)
    - Task status polling
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("KLING_API_KEY", "")
        self.base_url = base_url or os.getenv("KLING_API_BASE", KLING_API_BASE)
        if not self.api_key:
            raise KlingClientError(
                "No KLING API key found. Set KLING_API_KEY in .env"
            )
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ─── Text to Video ────────────────────────────────────────────────────

    def generate_video_from_text(
        self,
        prompt: str,
        model: str = "kling-v3",
        duration: int = 5,
        resolution: str = "1080p",
        aspect_ratio: str = "16:9",
        negative_prompt: str = "",
        camera_motion: Optional[str] = None,
    ) -> dict:
        """Submit a text-to-video generation request.

        Args:
            prompt: Description of the video to generate
            model: Model version (kling-v3, kling-v3-turbo, kling-v2.6)
            duration: Video length in seconds (3-10)
            resolution: Output resolution (720p, 1080p)
            aspect_ratio: Aspect ratio (16:9, 9:16, 1:1)
            negative_prompt: What to avoid
            camera_motion: Camera movement type (optional)

        Returns:
            Dict with task_id for polling
        """
        payload: dict[str, Any] = {
            "prompt": prompt,
            "model": model,
            "duration": duration,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if camera_motion:
            payload["camera_motion"] = camera_motion

        return self._post("/v1/videos/generations", payload)

    # ─── Image to Video ───────────────────────────────────────────────────

    def generate_video_from_image(
        self,
        image_url: str,
        prompt: str = "",
        model: str = "kling-v3",
        duration: int = 5,
        resolution: str = "1080p",
    ) -> dict:
        """Submit an image-to-video generation request.

        Args:
            image_url: URL of the source image (must be publicly accessible)
            prompt: Optional motion/action description
            model: Model version
            duration: Video length in seconds
            resolution: Output resolution

        Returns:
            Dict with task_id for polling
        """
        payload: dict[str, Any] = {
            "image_url": image_url,
            "model": model,
            "duration": duration,
            "resolution": resolution,
        }
        if prompt:
            payload["prompt"] = prompt

        return self._post("/v1/videos/image-to-video", payload)

    # ─── Text to Image ────────────────────────────────────────────────────

    def generate_image(
        self,
        prompt: str,
        model: str = "kling-v3",
        resolution: str = "1024x1024",
        negative_prompt: str = "",
        num_images: int = 1,
    ) -> dict:
        """Submit a text-to-image generation request.

        Returns:
            Dict with task_id for polling
        """
        payload: dict[str, Any] = {
            "prompt": prompt,
            "model": model,
            "resolution": resolution,
            "n": num_images,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        return self._post("/v1/images/generations", payload)

    # ─── Task Polling ─────────────────────────────────────────────────────

    def get_task_status(self, task_id: str) -> dict:
        """Get the current status of a generation task.

        Returns:
            Dict with status, progress, output_url (when complete)
        """
        return self._get(f"/v1/tasks/{task_id}")

    def wait_for_task(
        self,
        task_id: str,
        timeout: int = 300,
        poll_interval: int = 5,
    ) -> dict:
        """Poll a task until completion or timeout.

        Args:
            task_id: The task to wait for
            timeout: Max seconds to wait
            poll_interval: Seconds between polls

        Returns:
            Final task data with output_url

        Raises:
            KlingClientError: If task fails or times out
        """
        start = time.time()
        while time.time() - start < timeout:
            result = self.get_task_status(task_id)
            status = result.get("status", result.get("state", ""))

            if status in ("completed", "succeed", "done"):
                return result
            if status in ("failed", "error"):
                raise KlingClientError(
                    f"Task {task_id} failed: {result.get('error', result.get('message', 'Unknown error'))}"
                )

            time.sleep(poll_interval)

        raise KlingClientError(f"Task {task_id} timed out after {timeout}s")

    # ─── Account / Health ─────────────────────────────────────────────────

    def get_account_info(self) -> dict:
        """Get account information and remaining credits."""
        return self._get("/v1/account")

    def health_check(self) -> dict:
        """Validate API key and check service availability."""
        try:
            info = self.get_account_info()
            return {
                "connected": True,
                "credits_remaining": info.get("credits", info.get("balance", 0)),
                "plan": info.get("plan", "unknown"),
            }
        except KlingClientError as e:
            return {"connected": False, "error": str(e)}

    # ─── Internal HTTP ────────────────────────────────────────────────────

    def _post(self, path: str, payload: dict) -> dict:
        """Send a POST request to the KLING API."""
        try:
            resp = httpx.post(
                f"{self.base_url}{path}",
                headers=self._headers,
                json=payload,
                timeout=30,
            )
        except httpx.HTTPError as e:
            raise KlingClientError(f"Network error: {e}")

        if resp.status_code not in (200, 201, 202):
            raise KlingClientError(
                f"KLING API error ({resp.status_code}): {resp.text}"
            )
        return resp.json()

    def _get(self, path: str) -> dict:
        """Send a GET request to the KLING API."""
        try:
            resp = httpx.get(
                f"{self.base_url}{path}",
                headers=self._headers,
                timeout=30,
            )
        except httpx.HTTPError as e:
            raise KlingClientError(f"Network error: {e}")

        if resp.status_code != 200:
            raise KlingClientError(
                f"KLING API error ({resp.status_code}): {resp.text}"
            )
        return resp.json()
