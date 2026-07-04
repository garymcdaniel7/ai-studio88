"""Direct generation endpoint — submits workflow to ComfyUI and returns result.

This is the endpoint the frontend Create page calls. It:
1. Builds the correct workflow for the selected model
2. Submits to ComfyUI (via COMFYUI_BASE_URL)
3. Polls for completion
4. Returns the image data (base64) or download URL

Requires ComfyUI to be running (either local or via SSH tunnel from Vast worker).
"""
from __future__ import annotations

import base64
import json
import os
import random
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/v1/generate", tags=["generate"])

COMFYUI_URL = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
WORKFLOWS_DIR = Path(os.getenv("COMFYUI_WORKFLOWS_DIR", "./workflows/comfyui"))


@router.post("/image")
def generate_image(data: dict):
    """Generate an image via ComfyUI.

    Body:
        prompt: str — what to generate
        negative_prompt: str — what to avoid (optional)
        model: str — "flux-dev" | "sdxl-turbo" | "sd15"
        width: int — output width (default from model)
        height: int — output height (default from model)
        steps: int — sampling steps (default from model)
        cfg: float — CFG scale (default from model)
        seed: int — seed (-1 for random)
        guidance: float — Flux guidance (default 3.5)

    Returns:
        image_base64: base64 encoded PNG
        filename: output filename
        generation_time: seconds
    """
    prompt = data.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="'prompt' required")

    model = data.get("model", "sdxl-turbo")
    negative_prompt = data.get("negative_prompt", "")
    width = int(data.get("width", 1024 if model == "flux-dev" else 512))
    height = int(data.get("height", 1024 if model == "flux-dev" else 512))
    steps = int(data.get("steps", 20 if model != "sdxl-turbo" else 1))
    cfg = float(data.get("cfg", 1.0 if model in ("sdxl-turbo", "flux-dev") else 7.0))
    seed = int(data.get("seed", -1))
    guidance = float(data.get("guidance", 3.5))

    if seed < 0:
        seed = random.randint(1, 999999999)

    # Check ComfyUI is reachable
    try:
        health = httpx.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        if health.status_code != 200:
            raise HTTPException(status_code=503, detail="ComfyUI not responding")
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"ComfyUI not reachable at {COMFYUI_URL}. Launch a GPU worker first."
        )

    # Build workflow based on model
    workflow = _build_workflow(model, prompt, negative_prompt, width, height, steps, cfg, seed, guidance)

    # Submit to ComfyUI
    start_time = time.time()
    try:
        resp = httpx.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail=f"ComfyUI rejected workflow: {resp.text[:200]}")
        prompt_id = resp.json().get("prompt_id")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="ComfyUI connection lost during submit")

    # Poll for result (max 5 minutes)
    max_wait = 300
    while time.time() - start_time < max_wait:
        time.sleep(2)
        try:
            hist = httpx.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10).json()
            if prompt_id in hist:
                entry = hist[prompt_id]
                status = entry.get("status", {})

                if status.get("completed"):
                    # Find output image
                    for nid, out in entry.get("outputs", {}).items():
                        for img in out.get("images", []):
                            # Download the image
                            img_resp = httpx.get(
                                f"{COMFYUI_URL}/view",
                                params={"filename": img["filename"], "type": img.get("type", "output")},
                                timeout=30,
                            )
                            if img_resp.status_code == 200:
                                elapsed = round(time.time() - start_time, 1)
                                return {
                                    "success": True,
                                    "image_base64": base64.b64encode(img_resp.content).decode(),
                                    "filename": img["filename"],
                                    "generation_time": elapsed,
                                    "model": model,
                                    "prompt": prompt,
                                    "seed": seed,
                                    "width": width,
                                    "height": height,
                                }

                elif status.get("status_str") == "error":
                    msgs = status.get("messages", [])
                    err_msg = "Unknown generation error"
                    for m in msgs:
                        if m[0] == "execution_error":
                            err_msg = m[1].get("exception_message", "")[:300]
                    raise HTTPException(status_code=500, detail=f"Generation failed: {err_msg}")
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Lost connection to ComfyUI during generation")

    raise HTTPException(status_code=504, detail="Generation timed out (5 minutes)")


def _build_workflow(
    model: str, prompt: str, negative: str,
    width: int, height: int, steps: int, cfg: float, seed: int, guidance: float
) -> dict:
    """Build ComfyUI workflow JSON for the given model."""

    if model == "flux-dev":
        return {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "default"}},
            "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl_fp16.safetensors", "type": "flux"}},
            "3": {"class_type": "CLIPTextEncodeFlux", "inputs": {"clip": ["2", 0], "clip_l": prompt[:77], "t5xxl": prompt, "guidance": guidance}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["3", 0], "negative": ["3", 0], "latent_image": ["4", 0], "seed": seed, "steps": steps, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
            "6": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["6", 0]}},
            "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "studio_flux"}},
        }
    elif model == "sdxl-turbo":
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_turbo_1.0_fp16.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative or "ugly, blurry", "clip": ["1", 1]}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0], "seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "studio_sdxl"}},
        }
    else:  # sd15
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative or "ugly, blurry", "clip": ["1", 1]}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0], "seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 1.0}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "studio_gen"}},
        }
