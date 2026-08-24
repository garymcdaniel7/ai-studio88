"""Image generation job handler.

Executes an ``image_generation`` job against a real ComfyUI/WAN-compatible
image engine, uploads the resulting PNG/JPEG bytes to Backblaze B2, and returns
a public URL. Replaces the SimulationHandler shim so worker jobs produce real
images when ComfyUI is reachable.
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from typing import Any, Callable

import httpx

from backend.handlers.base import BaseHandler
from backend.storage import generate_storage_key, upload_file

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "sdxl-turbo"
_DEFAULT_WIDTH = 1024
_DEFAULT_HEIGHT = 1024
_DEFAULT_STEPS = 1
_DEFAULT_CFG = 1.0

# ComfyUI checkpoint filename -> model key mapping (the model names the app uses)
_CHECKPOINT_BY_MODEL = {
    "sdxl-turbo": "sd_xl_turbo_1.0_fp16.safetensors",
    "sdxl": "sd_xl_base_1.0.safetensors",
    "flux-dev": "flux1-dev.safetensors",
}


class ImageGenerationHandler(BaseHandler):
    """Generate a real image via ComfyUI and upload to B2."""

    @property
    def name(self) -> str:
        return "image_generation"

    def execute(self, job: dict, report_progress: Callable[[int], None]) -> dict:
        job_input = job.get("input", {}) or {}
        prompt = job_input.get("prompt", "")
        if not prompt.strip():
            raise ValueError("Image generation requires a prompt")

        model = job_input.get("model", _DEFAULT_MODEL)
        width = int(job_input.get("width", _DEFAULT_WIDTH))
        height = int(job_input.get("height", _DEFAULT_HEIGHT))
        steps = int(job_input.get("steps", _DEFAULT_STEPS))
        cfg = float(job_input.get("cfg", _DEFAULT_CFG))
        seed = int(job_input.get("seed", -1)) or 0
        negative = job_input.get("negative_prompt", "")

        comfyui_url = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
        checkpoint = _CHECKPOINT_BY_MODEL.get(model)
        if not checkpoint:
            raise RuntimeError(
                f"No ComfyUI checkpoint mapped for model '{model}'. Available: "
                f"{', '.join(_CHECKPOINT_BY_MODEL)}. Deploy a model on the worker first."
            )

        report_progress(5)
        logger.info("Generating image: model=%s %sx%s prompt=%r", model, width, height, prompt[:80])

        # Build a minimal SDXL-Turbo-style ComfyUI workflow (text-to-image).
        # Uses CheckpointLoaderSimple + CLIPTextEncode + KSampler + VAEDecode +
        # SaveImage. Reference node names are the standard ComfyUI defaults.
        workflow = _build_workflow(prompt, negative, width, height, steps, cfg, seed, checkpoint)

        try:
            resp = httpx.post(
                f"{comfyui_url}/prompt",
                json={"prompt": workflow, "client_id": f"aistudio-{uuid.uuid4().hex[:8]}"},
                timeout=120,
            )
            resp.raise_for_status()
            prompt_id = resp.json().get("prompt_id")
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"ComfyUI unreachable at {comfyui_url}: {exc}. "
                "Ensure ComfyUI is running on the worker (COMFYUI_BASE_URL)."
            ) from exc

        report_progress(30)
        image_bytes, filename = _poll_for_image(comfyui_url, prompt_id, timeout_s=180)
        if not image_bytes:
            raise RuntimeError("ComfyUI did not produce an image within the timeout")

        storage_key = generate_storage_key(filename or "image.png", "image")
        image_url = upload_file(image_bytes, storage_key, "image/png")
        report_progress(100)

        return {
            "image_url": image_url,
            "model": model,
            "width": width,
            "height": height,
            "seed": seed,
            "provider": "comfyui",
            "storage_provider": "backblaze_b2",
        }


def _build_workflow(
    prompt: str,
    negative: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
    checkpoint: str,
) -> dict:
    """Build a ComfyUI text-to-image workflow graph (standard node IDs)."""
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative or "", "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "aistudio", "images": ["8", 0]},
        },
    }


def _poll_for_image(comfyui_url: str, prompt_id: str, timeout_s: int = 180) -> tuple[bytes | None, str | None]:
    """Poll ComfyUI history until the prompt produces an output image."""
    import time

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{comfyui_url}/history/{prompt_id}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                outputs = data.get(prompt_id, {}).get("outputs", {})
                for node_id, node_out in outputs.items():
                    images = node_out.get("images", [])
                    if images:
                        img = images[0]
                        return _fetch_image(comfyui_url, img["filename"]), img.get("filename")
        except Exception:
            pass
        time.sleep(2)
    return None, None


def _fetch_image(comfyui_url: str, filename: str) -> bytes | None:
    """Fetch a generated image from ComfyUI's /view endpoint."""
    try:
        resp = httpx.get(
            f"{comfyui_url}/view",
            params={"filename": filename, "subfolder": "", "type": "output"},
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None
