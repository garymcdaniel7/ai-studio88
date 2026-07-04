"""ComfyUI Video Provider — WAN 2.1 text-to-video via ComfyUI.

Submits video generation workflows to a ComfyUI instance, polls for
completion, and downloads the output video file.

Configuration (environment variables):
    COMFYUI_BASE_URL          — ComfyUI HTTP URL (default: http://localhost:8188)
    COMFYUI_API_TIMEOUT       — Max seconds to wait for video gen (default: 600)
    COMFYUI_WORKFLOWS_DIR     — Path to workflow templates (default: ./workflows/comfyui)
    COMFYUI_VIDEO_WORKFLOW    — Workflow template name (default: wan21_t2v_simple)
"""
from __future__ import annotations

import json
import os
import random
import time
import uuid
from pathlib import Path
from typing import Callable

import requests
from dotenv import load_dotenv

from backend.video.provider import VideoProvider, VideoRequest, VideoResult, VideoProgress

load_dotenv()

COMFYUI_BASE_URL = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
COMFYUI_TIMEOUT = int(os.getenv("COMFYUI_API_TIMEOUT", os.getenv("COMFYUI_TIMEOUT_SECONDS", "600")))
WORKFLOWS_DIR = Path(os.getenv("COMFYUI_WORKFLOWS_DIR", "./workflows/comfyui"))
DEFAULT_VIDEO_WORKFLOW = os.getenv("COMFYUI_VIDEO_WORKFLOW", "wan21_t2v_simple")

# WAN 2.1 default parameters
WAN_DEFAULTS = {
    "width": 832,
    "height": 480,
    "num_frames": 49,
    "steps": 20,
    "cfg": 6.0,
    "model": "wan2.1_t2v_14B_bf16.safetensors",
}


def _load_workflow(template_name: str) -> dict | None:
    """Load a ComfyUI workflow JSON template, stripping _meta."""
    path = WORKFLOWS_DIR / f"{template_name}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    data.pop("_meta", None)
    # Strip per-node _meta keys (ComfyUI doesn't use them)
    for node_id in list(data.keys()):
        if isinstance(data[node_id], dict):
            data[node_id].pop("_meta", None)
    return data


def _inject_params(workflow: dict, params: dict) -> dict:
    """Replace __PLACEHOLDER__ strings in workflow JSON with actual values."""
    workflow_str = json.dumps(workflow)
    for key, value in params.items():
        placeholder = f"__{key.upper()}__"
        # Handle both quoted and unquoted placeholders
        workflow_str = workflow_str.replace(f'"{placeholder}"', json.dumps(value))
        workflow_str = workflow_str.replace(placeholder, str(value))
    return json.loads(workflow_str)


def _parse_resolution(resolution: str) -> tuple[int, int]:
    """Parse 'WIDTHxHEIGHT' or 'HEIGHTxWIDTH' string.

    The video module uses 'WxH' format (e.g., '1080x1920').
    Returns (width, height).
    """
    parts = resolution.lower().split("x")
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    return WAN_DEFAULTS["width"], WAN_DEFAULTS["height"]


class ComfyUIVideoProvider(VideoProvider):
    """Video generation via ComfyUI with WAN 2.1 workflows.

    Connects to a running ComfyUI instance (typically over SSH tunnel),
    submits a WAN 2.1 text-to-video workflow, and polls for the result.
    Falls back to simulation if ComfyUI is unreachable.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
        workflow_name: str | None = None,
    ):
        self._base_url = (base_url or COMFYUI_BASE_URL).rstrip("/")
        self._timeout = timeout or COMFYUI_TIMEOUT
        self._workflow_name = workflow_name or DEFAULT_VIDEO_WORKFLOW

    @property
    def name(self) -> str:
        return "comfyui"

    def health(self) -> dict:
        """Check ComfyUI connectivity and GPU status."""
        try:
            resp = requests.get(f"{self._base_url}/system_stats", timeout=5)
            if resp.ok:
                stats = resp.json()
                devices = stats.get("devices", [{}])
                gpu = devices[0] if devices else {}
                return {
                    "healthy": True,
                    "provider": self.name,
                    "gpu_name": gpu.get("name", "Unknown"),
                    "vram_total_gb": round(gpu.get("vram_total", 0) / (1024**3), 1),
                    "vram_free_gb": round(gpu.get("vram_free", 0) / (1024**3), 1),
                    "queue_remaining": stats.get("exec_info", {}).get("queue_remaining", 0),
                    "base_url": self._base_url,
                }
            return {
                "healthy": False,
                "provider": self.name,
                "error": f"HTTP {resp.status_code}",
                "base_url": self._base_url,
            }
        except requests.ConnectionError:
            return {
                "healthy": False,
                "provider": self.name,
                "error": f"ComfyUI not reachable at {self._base_url}",
                "base_url": self._base_url,
            }
        except Exception as e:
            return {
                "healthy": False,
                "provider": self.name,
                "error": str(e),
                "base_url": self._base_url,
            }

    def capabilities(self) -> dict:
        return {
            "provider": self.name,
            "modes": ["text_to_video", "image_to_video"],
            "models": ["wan-2.1"],
            "max_duration": 10,
            "max_fps": 24,
            "max_resolution": "1280x720",
            "default_resolution": f"{WAN_DEFAULTS['width']}x{WAN_DEFAULTS['height']}",
            "default_frames": WAN_DEFAULTS["num_frames"],
            "notes": "WAN 2.1 14B requires 80GB+ VRAM. Typical gen time: 3-10 min per 2s clip.",
        }

    def supports_model(self, model: str) -> bool:
        """Check if this provider supports the given model."""
        supported = {"wan-2.1", "wan2.1", "wan-2.1-t2v"}
        return model.lower().replace(" ", "-") in supported

    def submit(
        self,
        request: VideoRequest,
        on_progress: Callable[[VideoProgress], None] | None = None,
    ) -> VideoResult:
        """Generate video via ComfyUI.

        Falls back to simulation if ComfyUI is not reachable.
        """
        # Check connectivity first
        health = self.health()
        if not health.get("healthy"):
            return self._fallback_simulation(request, health.get("error", "ComfyUI unavailable"))

        # Parse resolution
        width, height = _parse_resolution(request.resolution)

        # Calculate frames from duration
        num_frames = int(request.duration_seconds * request.fps)
        # WAN 2.1 works best with specific frame counts (multiples of 4 + 1)
        num_frames = max(17, min(num_frames, 81))

        # Determine seed
        seed = request.seed if request.seed > 0 else random.randint(1, 999999999)

        # Load and parameterize workflow
        workflow_name = request.extra.get("workflow_template", self._workflow_name)
        workflow = _load_workflow(workflow_name)
        if not workflow:
            return VideoResult(
                success=False,
                error=f"Workflow template '{workflow_name}' not found in {WORKFLOWS_DIR}",
            )

        params = {
            "POSITIVE_PROMPT": request.prompt,
            "NEGATIVE_PROMPT": request.negative_prompt or "",
            "WIDTH": width,
            "HEIGHT": height,
            "NUM_FRAMES": num_frames,
            "STEPS": request.extra.get("steps", WAN_DEFAULTS["steps"]),
            "CFG": request.extra.get("cfg", WAN_DEFAULTS["cfg"]),
            "SEED": seed,
            "MODEL": request.extra.get("model_filename", WAN_DEFAULTS["model"]),
        }
        workflow = _inject_params(workflow, params)

        # Submit to ComfyUI
        client_id = uuid.uuid4().hex
        try:
            resp = requests.post(
                f"{self._base_url}/prompt",
                json={"prompt": workflow, "client_id": client_id},
                timeout=10,
            )
            resp.raise_for_status()
            prompt_id = resp.json().get("prompt_id")
        except requests.ConnectionError as e:
            return self._fallback_simulation(request, f"Connection failed: {e}")
        except Exception as e:
            return VideoResult(success=False, error=f"Failed to submit workflow: {e}")

        # Poll for completion
        start_time = time.time()
        while (time.time() - start_time) < self._timeout:
            time.sleep(2)  # Video gen is slow; no need to poll fast

            try:
                hist_resp = requests.get(
                    f"{self._base_url}/history/{prompt_id}", timeout=5
                )
                if hist_resp.ok:
                    history_data = hist_resp.json()
                    if prompt_id in history_data:
                        outputs = history_data[prompt_id].get("outputs", {})
                        return self._extract_video_output(
                            outputs, request, time.time() - start_time, params
                        )
            except Exception:
                pass

            # Report progress
            if on_progress:
                elapsed = time.time() - start_time
                estimated_total = params["STEPS"] * 3  # rough: ~3s per step for video
                pct = min(int((elapsed / max(estimated_total, 1)) * 100), 95)
                on_progress(VideoProgress(
                    percent=pct,
                    frame=int(pct * num_frames / 100),
                    total_frames=num_frames,
                    message=f"ComfyUI generating video... ({elapsed:.0f}s elapsed)",
                ))

        return VideoResult(
            success=False,
            error=f"Timeout after {self._timeout}s waiting for video generation (prompt_id={prompt_id})",
            metadata={"prompt_id": prompt_id, "provider": self.name},
        )

    def cancel(self, job_id: str) -> bool:
        """Cancel current generation via ComfyUI /interrupt."""
        try:
            resp = requests.post(f"{self._base_url}/interrupt", timeout=5)
            return resp.ok
        except Exception:
            return False

    def _extract_video_output(
        self,
        outputs: dict,
        request: VideoRequest,
        elapsed: float,
        params: dict,
    ) -> VideoResult:
        """Extract video/image output from ComfyUI history."""
        # Look for video outputs (VHS_VideoCombine) or animated images (SaveAnimatedWEBP)
        for node_id, node_output in outputs.items():
            # Check for video files (from VHS_VideoCombine)
            gifs = node_output.get("gifs", [])
            if gifs:
                file_info = gifs[0]
                return self._download_output(file_info, request, elapsed, params, "video/mp4")

            # Check for images (from SaveAnimatedWEBP or SaveImage)
            images = node_output.get("images", [])
            if images:
                file_info = images[0]
                mime = "image/webp" if file_info.get("filename", "").endswith(".webp") else "image/png"
                return self._download_output(file_info, request, elapsed, params, mime)

        return VideoResult(
            success=False,
            error="No output files found in ComfyUI history",
            generation_time_seconds=round(elapsed, 2),
            metadata={"provider": self.name},
        )

    def _download_output(
        self,
        file_info: dict,
        request: VideoRequest,
        elapsed: float,
        params: dict,
        mime_type: str,
    ) -> VideoResult:
        """Download an output file from ComfyUI."""
        filename = file_info.get("filename", "output.mp4")
        subfolder = file_info.get("subfolder", "")
        file_type = file_info.get("type", "output")

        dl_params = {"filename": filename, "type": file_type}
        if subfolder:
            dl_params["subfolder"] = subfolder

        try:
            dl_resp = requests.get(
                f"{self._base_url}/view", params=dl_params, timeout=60
            )
            dl_resp.raise_for_status()
            file_bytes = dl_resp.content
        except Exception as e:
            return VideoResult(
                success=False,
                error=f"Failed to download output: {e}",
                generation_time_seconds=round(elapsed, 2),
            )

        return VideoResult(
            success=True,
            output_bytes=file_bytes,
            filename=filename,
            mime_type=mime_type,
            duration_seconds=request.duration_seconds,
            fps=request.fps,
            resolution=request.resolution,
            generation_time_seconds=round(elapsed, 2),
            metadata={
                "provider": self.name,
                "model": request.model,
                "prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "width": params["WIDTH"],
                "height": params["HEIGHT"],
                "num_frames": params["NUM_FRAMES"],
                "steps": params["STEPS"],
                "cfg": params["CFG"],
                "seed": params["SEED"],
                "workflow_template": self._workflow_name,
            },
        )

    def _fallback_simulation(self, request: VideoRequest, reason: str) -> VideoResult:
        """Fall back to simulated output when ComfyUI is unavailable."""
        from backend.video.provider import SimulatedVideoProvider

        sim = SimulatedVideoProvider()
        result = sim.submit(request)
        result.metadata["fallback_reason"] = reason
        result.metadata["original_provider"] = self.name
        result.metadata["provider"] = f"{self.name} (simulated fallback)"
        return result
