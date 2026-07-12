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
import os
import random
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from fastapi import File as _File
from fastapi import Form as _Form
from fastapi import UploadFile as _UploadFile

load_dotenv(override=True)

router = APIRouter(prefix="/api/v1/generate", tags=["generate"])

COMFYUI_URL = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
WORKFLOWS_DIR = Path(os.getenv("COMFYUI_WORKFLOWS_DIR", "./workflows/comfyui"))

# Output directory for auto-saving generated images
_default_output_dir = os.path.expanduser(os.getenv("OUTPUT_DIR", "~/AI-Studio/outputs"))


def _get_output_dir() -> Path:
    """Get the current output directory, creating it if needed."""
    output_dir = Path(os.path.expanduser(os.getenv("OUTPUT_DIR", _default_output_dir)))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


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

    # Try Worker API first (for Vercel/cloud deployments)
    try:
        from backend.aios.orchestration.interceptor import intercept_resource_request
        intercept = intercept_resource_request(
            task_type="generate_image_flux" if "flux" in data.get("model", "") else "generate_image_sdxl",
            source="create_page",
            model=data.get("model", ""),
            talent_id=data.get("talent_ids", [None])[0] if data.get("talent_ids") else None,
        )
        # Log prediction for the user
        if intercept.get("prediction"):
            logger.info(f"Prediction: user may want to {intercept['prediction']} next")
    except Exception:
        pass

    try:
        from backend.infrastructure.worker_api_client import get_worker_client

        worker = get_worker_client()
        if worker and worker.is_available():
            result = worker.generate_image(**data)
            if result.get("success"):
                return result
    except Exception as e:
        logger.warning(f"Worker API dispatch failed, falling back to direct ComfyUI: {e}")

    model = data.get("model", "sdxl-turbo")

    negative_prompt = data.get("negative_prompt", "")
    width = int(
        data.get("width", 1024 if model in ("flux-dev", "flux2-dev", "flux2-klein") else 512)
    )
    height = int(
        data.get("height", 1024 if model in ("flux-dev", "flux2-dev", "flux2-klein") else 512)
    )
    steps = int(
        data.get("steps", 4 if model == "flux2-klein" else 20 if model != "sdxl-turbo" else 1)
    )
    cfg = float(
        data.get(
            "cfg", 1.0 if model in ("sdxl-turbo", "flux-dev", "flux2-dev", "flux2-klein") else 7.0
        )
    )
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
            detail=f"ComfyUI not reachable at {COMFYUI_URL}. Launch a GPU worker first.",
        )

    # Build workflow based on model
    workflow = _build_workflow(
        model, prompt, negative_prompt, width, height, steps, cfg, seed, guidance
    )

    # Inject LoRAs if any (chains LoraLoader nodes between model and sampler)
    loras = data.get("loras", [])
    # Also support legacy single-lora param
    if not loras and data.get("lora"):
        loras = [{"id": data["lora"], "strength": data.get("lora_strength", 0.7)}]

    if loras:
        workflow = _inject_loras(workflow, loras, model)

    # Inject ControlNet if provided
    controlnet_cfg = data.get("controlnet")
    if controlnet_cfg and controlnet_cfg.get("type") != "none":
        control_image = controlnet_cfg.get("image", "")
        if control_image:
            workflow = _inject_controlnet(workflow, controlnet_cfg, control_image)

    # Submit to ComfyUI
    start_time = time.time()
    try:
        resp = httpx.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
        if resp.status_code != 200:
            # Parse ComfyUI error for user-friendly message
            error_text = resp.text[:500]
            try:
                error_data = resp.json()
                node_errors = error_data.get("node_errors", {})
                if node_errors:
                    missing_files = []
                    for _nid, nerr in node_errors.items():
                        for e in nerr.get("errors", []):
                            if e.get("type") == "value_not_in_list":
                                details = e.get("details", "")
                                missing_files.append(details)
                    if missing_files:
                        raise HTTPException(
                            status_code=422,
                            detail=f"Model files not found on GPU worker. Missing: {'; '.join(missing_files[:3])}. "
                            f"Only 'sdxl-turbo' is currently loaded. Select a different model or upload the required files.",
                        )
            except HTTPException:
                raise
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f"ComfyUI rejected workflow: {error_text}")
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
                    for _nid, out in entry.get("outputs", {}).items():
                        for img in out.get("images", []):
                            # Download the image
                            img_resp = httpx.get(
                                f"{COMFYUI_URL}/view",
                                params={
                                    "filename": img["filename"],
                                    "type": img.get("type", "output"),
                                },
                                timeout=30,
                            )
                            if img_resp.status_code == 200:
                                elapsed = round(time.time() - start_time, 1)
                                image_bytes = img_resp.content
                                b64 = base64.b64encode(image_bytes).decode()

                                # Auto-save to local output directory
                                saved_path = None
                                try:
                                    output_dir = _get_output_dir()
                                    local_filename = f"{model}_{seed}_{img['filename']}"
                                    local_path = output_dir / local_filename
                                    local_path.write_bytes(image_bytes)
                                    saved_path = str(local_path)
                                except Exception:
                                    pass  # Don't fail generation if save fails

                                # Record job cost
                                try:
                                    from backend.infrastructure.cost_intelligence import (
                                        get_cost_tracker,
                                    )

                                    tracker = get_cost_tracker()
                                    # Estimate GPU cost: generation_time * hourly_rate / 3600
                                    hourly_rate = float(
                                        os.getenv("VAST_CURRENT_HOURLY_RATE", "0.076")
                                    )
                                    gpu_cost = round((elapsed / 3600) * hourly_rate, 6)
                                    tracker.record_job_cost(
                                        job_type="generation",
                                        model=model,
                                        provider="comfyui",
                                        duration_seconds=elapsed,
                                        estimated_cost=gpu_cost,
                                        input_summary=prompt[:100],
                                        output_summary=img["filename"],
                                    )
                                except Exception:
                                    pass

                                return {
                                    "success": True,
                                    "image_base64": b64,
                                    "filename": img["filename"],
                                    "saved_to": saved_path,
                                    "generation_time": elapsed,
                                    "estimated_cost": gpu_cost if "gpu_cost" in dir() else 0,
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
            raise HTTPException(
                status_code=503, detail="Lost connection to ComfyUI during generation"
            )

    raise HTTPException(status_code=504, detail="Generation timed out (5 minutes)")


@router.get("/output-dir")
def get_output_directory():
    """Get the current output directory where generated images are saved."""
    output_dir = _get_output_dir()
    # Count files in directory
    files = list(output_dir.glob("*.*")) if output_dir.exists() else []
    return {
        "path": str(output_dir),
        "exists": output_dir.exists(),
        "file_count": len(files),
        "total_size_mb": round(sum(f.stat().st_size for f in files) / (1024 * 1024), 1)
        if files
        else 0,
    }


@router.put("/output-dir")
def set_output_directory(data: dict):
    """Set the output directory for generated images.

    Persists to .env as OUTPUT_DIR.
    """
    new_path = data.get("path", "").strip()
    if not new_path:
        raise HTTPException(status_code=422, detail="'path' required")

    # Expand ~ and validate
    expanded = os.path.expanduser(new_path)
    try:
        Path(expanded).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot create directory: {e}")

    # Update .env
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        content = env_path.read_text()
        if "OUTPUT_DIR=" in content:
            import re

            content = re.sub(r"OUTPUT_DIR=.*", f"OUTPUT_DIR={new_path}", content)
        else:
            content += f"\nOUTPUT_DIR={new_path}\n"
        env_path.write_text(content)

    # Update runtime
    os.environ["OUTPUT_DIR"] = new_path

    return {
        "path": expanded,
        "message": f"Output directory set to {expanded}",
    }


@router.post("/open-folder")
def open_output_folder():
    """Open the output directory in the system file manager (Finder on macOS)."""
    import subprocess
    import sys

    output_dir = _get_output_dir()
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(output_dir)])
        elif sys.platform == "linux":
            subprocess.Popen(["xdg-open", str(output_dir)])
        else:
            subprocess.Popen(["explorer", str(output_dir)])
        return {"opened": True, "path": str(output_dir)}
    except Exception as e:
        return {"opened": False, "error": str(e)}


@router.get("/outputs")
def list_outputs(limit: int = 20, offset: int = 0):
    """List recently generated images in the output directory."""
    output_dir = _get_output_dir()
    if not output_dir.exists():
        return {"items": [], "total": 0}

    files = sorted(output_dir.glob("*.*"), key=lambda f: f.stat().st_mtime, reverse=True)
    total = len(files)
    page = files[offset : offset + limit]

    items = []
    for f in page:
        stat = f.stat()
        items.append(
            {
                "filename": f.name,
                "path": str(f),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)),
            }
        )

    return {"items": items, "total": total, "output_dir": str(output_dir)}


def _build_workflow(
    model: str,
    prompt: str,
    negative: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
    guidance: float,
) -> dict:
    """Build ComfyUI workflow JSON for the given model."""

    if model == "flux2-dev":
        # Flux 2 Dev — 32B param model, uses UNETLoader + Mistral text encoder + flux2-vae
        return {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name": "flux2_dev_fp8mixed.safetensors",
                    "weight_dtype": "fp8_e4m3fn",
                },
            },
            "2": {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": "mistral_3_small_flux2_bf16.safetensors",
                    "clip_name2": "mistral_3_small_flux2_bf16.safetensors",
                    "type": "flux",
                },
            },
            "3": {
                "class_type": "CLIPTextEncodeFlux",
                "inputs": {
                    "clip": ["2", 0],
                    "clip_l": prompt[:200],
                    "t5xxl": prompt,
                    "guidance": guidance,
                },
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["3", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                    "seed": seed,
                    "steps": steps,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                },
            },
            "6": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["6", 0]}},
            "8": {
                "class_type": "SaveImage",
                "inputs": {"images": ["7", 0], "filename_prefix": "studio_flux2dev"},
            },
        }
    elif model == "flux2-klein":
        # Flux 2 Klein — 4B param, uses Qwen 3 4B text encoder + Flux2-specific nodes
        return {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "flux-2-klein-4b.safetensors", "weight_dtype": "default"},
            },
            "2": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "flux2"},
            },
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
            "4": {
                "class_type": "EmptyFlux2LatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "5": {
                "class_type": "BasicGuider",
                "inputs": {"model": ["1", 0], "conditioning": ["3", 0]},
            },
            "6": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
            "7": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "8": {
                "class_type": "Flux2Scheduler",
                "inputs": {"steps": steps, "width": width, "height": height},
            },
            "9": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise": ["6", 0],
                    "guider": ["5", 0],
                    "sampler": ["7", 0],
                    "sigmas": ["8", 0],
                    "latent_image": ["4", 0],
                },
            },
            "10": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
            "11": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["10", 0]}},
            "12": {
                "class_type": "SaveImage",
                "inputs": {"images": ["11", 0], "filename_prefix": "studio_flux2klein"},
            },
        }
    elif model == "flux-dev":
        # Flux 1 Dev (legacy)
        return {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "default"},
            },
            "2": {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": "clip_l.safetensors",
                    "clip_name2": "t5xxl_fp16.safetensors",
                    "type": "flux",
                },
            },
            "3": {
                "class_type": "CLIPTextEncodeFlux",
                "inputs": {
                    "clip": ["2", 0],
                    "clip_l": prompt[:77],
                    "t5xxl": prompt,
                    "guidance": guidance,
                },
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["3", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                    "seed": seed,
                    "steps": steps,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                },
            },
            "6": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["6", 0]}},
            "8": {
                "class_type": "SaveImage",
                "inputs": {"images": ["7", 0], "filename_prefix": "studio_flux"},
            },
        }
    elif model == "sdxl-turbo":
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "sd_xl_turbo_1.0_fp16.safetensors"},
            },
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative or "ugly, blurry", "clip": ["1", 1]},
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                },
            },
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {
                "class_type": "SaveImage",
                "inputs": {"images": ["6", 0], "filename_prefix": "studio_sdxl"},
            },
        }
    else:  # sd15
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
            },
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative or "ugly, blurry", "clip": ["1", 1]},
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "euler_ancestral",
                    "scheduler": "normal",
                    "denoise": 1.0,
                },
            },
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {
                "class_type": "SaveImage",
                "inputs": {"images": ["6", 0], "filename_prefix": "studio_gen"},
            },
        }


def _inject_loras(workflow: dict, loras: list[dict], model: str) -> dict:
    """Inject LoraLoader nodes into the workflow.

    For checkpoint-based models (SDXL, SD1.5): chains LoraLoader after checkpoint.
    For UNET-based models (Flux): chains LoraLoader after UNETLoader.

    Each LoRA node takes model+clip from previous, passes to next.
    Final model+clip connects to the sampler/text encoder.
    """
    if not loras:
        return workflow

    # Resolve LoRA filenames from IDs
    lora_files = []
    for lora_cfg in loras:
        lora_id = lora_cfg.get("id", "")
        strength = float(lora_cfg.get("strength", 0.7))

        # Look up filename from model registry
        try:
            from backend.database import get_model_by_id

            model_data = get_model_by_id(lora_id).data
            filename = model_data.get("storage_path", "").split("/")[-1] if model_data else ""
            if not filename:
                filename = f"{lora_id}.safetensors"
        except Exception:
            filename = f"{lora_id}.safetensors"

        lora_files.append({"filename": filename, "strength": strength})

    if not lora_files:
        return workflow

    # Find the model source node (node "1" is always the model loader)
    # And the first node that uses the model output
    # For SDXL/SD15: node 1 outputs [model, clip, vae] at indices [0, 1, 2]
    # For Flux/WAN: node 1 outputs [model] at index [0], clip is separate node "2"

    is_checkpoint = any(n.get("class_type") == "CheckpointLoaderSimple" for n in workflow.values())

    # Generate LoRA node IDs starting from 100 to avoid conflicts
    new_nodes = {}
    prev_model_source = ["1", 0]
    prev_clip_source = ["1", 1] if is_checkpoint else ["2", 0]

    for i, lora in enumerate(lora_files):
        node_id = str(100 + i)
        new_nodes[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": prev_model_source,
                "clip": prev_clip_source,
                "lora_name": lora["filename"],
                "strength_model": lora["strength"],
                "strength_clip": lora["strength"],
            },
        }
        prev_model_source = [node_id, 0]
        prev_clip_source = [node_id, 1]

    # Rewire: find nodes that reference the original model/clip sources and update them
    last_lora_id = str(100 + len(lora_files) - 1)

    for nid, node in workflow.items():
        inputs = node.get("inputs", {})
        for key, val in inputs.items():
            if isinstance(val, list) and len(val) == 2:
                # Rewire model connections from node "1" output 0
                if val == ["1", 0] and nid != "100" and is_checkpoint:
                    inputs[key] = [last_lora_id, 0]
                elif val == ["1", 0] and nid != "100" and not is_checkpoint:
                    # For UNET models, only the KSampler/Guider uses model
                    if key == "model":
                        inputs[key] = [last_lora_id, 0]
                # Rewire clip connections from node "1" output 1 or node "2" output 0
                if (
                    is_checkpoint
                    and val == ["1", 1]
                    and nid != "100"
                    or not is_checkpoint
                    and val == ["2", 0]
                    and key == "clip"
                    and nid != "100"
                ):
                    inputs[key] = [last_lora_id, 1]

    # Add LoRA nodes to workflow
    workflow.update(new_nodes)
    return workflow


def _inject_controlnet(workflow: dict, controlnet_cfg: dict, control_image: str) -> dict:
    """Inject ControlNet nodes into the workflow.

    Adds:
    - LoadImage node for the control reference
    - Preprocessor node (Canny/OpenPose depending on type)
    - ControlNetLoader for the model
    - ControlNetApplyAdvanced to apply guidance

    Args:
        workflow: existing workflow dict
        controlnet_cfg: {"type": "openpose"|"canny"|"depth", "strength": 0.7, "model": "filename"}
        control_image: filename of uploaded image in ComfyUI input folder
    """
    control_type = controlnet_cfg.get("type", "canny")
    strength = float(controlnet_cfg.get("strength", 0.7))

    # Map control type to model filename
    MODEL_MAP = {
        "openpose": "control_v11p_sd15_openpose.safetensors",
        "canny": "control_v11p_sd15_canny.safetensors",
        "depth": "control_v11f1p_sd15_depth.safetensors",
    }
    model_file = controlnet_cfg.get("model") or MODEL_MAP.get(control_type, "")

    # Add nodes (IDs 200+)
    # Node 200: Load reference image
    workflow["200"] = {
        "class_type": "LoadImage",
        "inputs": {"image": control_image},
    }

    # Node 201: Preprocessor (Canny for now — others need custom nodes)
    if control_type == "canny":
        workflow["201"] = {
            "class_type": "Canny",
            "inputs": {
                "image": ["200", 0],
                "low_threshold": 100,
                "high_threshold": 200,
            },
        }
    elif control_type == "openpose":
        # Use SDPoseKeypointExtractor if available
        workflow["201"] = {
            "class_type": "SDPoseKeypointExtractor",
            "inputs": {
                "model": ["1", 0],  # needs model reference
                "vae": ["1", 2]
                if "CheckpointLoaderSimple" in str(workflow.get("1", {}).get("class_type", ""))
                else ["6", 0],
                "image": ["200", 0],
                "batch_size": 1,
            },
        }
    else:
        # Depth or other — pass image directly
        workflow["201"] = {
            "class_type": "LoadImage",
            "inputs": {"image": control_image},
        }

    # Node 202: Load ControlNet model
    workflow["202"] = {
        "class_type": "ControlNetLoader",
        "inputs": {"control_net_name": model_file},
    }

    # Node 203: Apply ControlNet — modifies positive/negative conditioning
    # Find the positive conditioning node (usually connects to sampler's "positive" input)
    sampler_node = None
    for nid, node in workflow.items():
        if node.get("class_type") in ("KSampler", "SamplerCustomAdvanced"):
            sampler_node = nid
            break

    if sampler_node:
        sampler_inputs = workflow[sampler_node]["inputs"]
        original_positive = sampler_inputs.get("positive", ["3", 0])
        original_negative = sampler_inputs.get("negative", ["4", 0])

        workflow["203"] = {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": original_positive,
                "negative": original_negative,
                "control_net": ["202", 0],
                "image": ["201", 0] if control_type == "canny" else ["200", 0],
                "strength": strength,
                "start_percent": 0.0,
                "end_percent": 1.0,
            },
        }

        # Rewire sampler to use ControlNet-modified conditioning
        sampler_inputs["positive"] = ["203", 0]
        sampler_inputs["negative"] = ["203", 1]

    return workflow


@router.get("/available-models")
def get_available_generation_models():
    """Check which models are actually loaded on the GPU worker.

    Queries ComfyUI's object_info to see what checkpoints/unets/clips exist.
    """
    try:
        resp = httpx.get(f"{COMFYUI_URL}/object_info/CheckpointLoaderSimple", timeout=5)
        checkpoints = []
        if resp.status_code == 200:
            data = resp.json()
            ckpt_input = (
                data.get("CheckpointLoaderSimple", {})
                .get("input", {})
                .get("required", {})
                .get("ckpt_name", [[]])[0]
            )
            checkpoints = ckpt_input if isinstance(ckpt_input, list) else []
    except Exception:
        checkpoints = []

    try:
        resp = httpx.get(f"{COMFYUI_URL}/object_info/UNETLoader", timeout=5)
        unets = []
        if resp.status_code == 200:
            data = resp.json()
            unet_input = (
                data.get("UNETLoader", {})
                .get("input", {})
                .get("required", {})
                .get("unet_name", [[]])[0]
            )
            unets = unet_input if isinstance(unet_input, list) else []
    except Exception:
        unets = []

    # Map to our model names
    models = []
    for ckpt in checkpoints:
        if "turbo" in ckpt.lower():
            models.append({"id": "sdxl-turbo", "name": "SDXL Turbo", "file": ckpt, "ready": True})
        elif "sdxl" in ckpt.lower() or "xl" in ckpt.lower():
            models.append({"id": "sdxl", "name": "SDXL", "file": ckpt, "ready": True})
        elif "v1-5" in ckpt.lower() or "sd15" in ckpt.lower():
            models.append({"id": "sd15", "name": "SD 1.5", "file": ckpt, "ready": True})

    for unet in unets:
        if "flux2" in unet.lower() and "klein" in unet.lower() or "flux-2-klein" in unet.lower():
            models.append(
                {"id": "flux2-klein", "name": "Flux 2 Klein", "file": unet, "ready": True}
            )
        elif "flux2" in unet.lower() or "flux-2" in unet.lower():
            models.append({"id": "flux2-dev", "name": "Flux 2 Dev", "file": unet, "ready": True})
        elif "flux" in unet.lower():
            models.append({"id": "flux-dev", "name": "Flux Dev", "file": unet, "ready": True})

    # Always list all supported models, mark unavailable ones
    ALL_MODELS = [
        {"id": "sdxl-turbo", "name": "SDXL Turbo", "vram": "8GB", "badge": "Fast"},
        {"id": "flux2-dev", "name": "Flux 2 Dev", "vram": "24GB+", "badge": "New"},
        {"id": "flux2-klein", "name": "Flux 2 Klein", "vram": "12GB", "badge": "Fast"},
        {"id": "flux-dev", "name": "Flux Dev (v1)", "vram": "32GB", "badge": ""},
        {"id": "sd15", "name": "SD 1.5", "vram": "6GB", "badge": ""},
        {"id": "wan2.2-5b", "name": "WAN 2.2 (Video)", "vram": "24GB", "badge": "Video"},
    ]
    ready_ids = {m["id"] for m in models}

    # Check if WAN model is loaded
    try:
        resp2 = httpx.get(f"{COMFYUI_URL}/object_info/UNETLoader", timeout=5)
        if resp2.status_code == 200:
            unet_list = (
                resp2.json()
                .get("UNETLoader", {})
                .get("input", {})
                .get("required", {})
                .get("unet_name", [[]])[0]
            )
            if any(
                "wan2.2" in u.lower() for u in (unet_list if isinstance(unet_list, list) else [])
            ):
                ready_ids.add("wan2.2-5b")
    except Exception:
        pass

    result = []
    for m in ALL_MODELS:
        result.append({**m, "ready": m["id"] in ready_ids})

    return {"models": result, "checkpoints": checkpoints, "unets": unets}


# =============================================================================
# Video Generation — WAN 2.2
# =============================================================================


@router.post("/video")
def generate_video(data: dict):
    """Generate a video via ComfyUI using WAN 2.2.

    Body:
        prompt: str — what to generate
        width: int — default 832
        height: int — default 480
        length: int — number of frames (default 49 = ~2s at 24fps)
        steps: int — sampling steps (default 20)
        seed: int — seed (-1 for random)
        model: str — "wan2.2-5b" (default)

    Returns:
        success: bool
        video_url: str (from ComfyUI output)
        generation_time: float
        frames: int
    """
    prompt_text = data.get("prompt")
    if not prompt_text:
        raise HTTPException(status_code=400, detail="'prompt' required")

    width = int(data.get("width", 832))
    height = int(data.get("height", 480))
    length = int(data.get("length", 49))
    steps = int(data.get("steps", 20))
    seed = int(data.get("seed", -1))

    # Support duration_seconds as alternative to raw frame count
    duration = float(data.get("duration_seconds", 0))
    if duration > 0:
        fps = 24
        length = int(duration * fps)
        # Cap at 97 frames (~4s) for single-clip generation on 24GB VRAM
        if length > 97:
            length = 97

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
            detail=f"ComfyUI not reachable at {COMFYUI_URL}. Launch a GPU worker first.",
        )

    # Build WAN 2.2 workflow
    workflow = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "wan2.2_ti2v_5B_fp16.safetensors",
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt_text,
                "clip": ["2", 0],
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "",
                "clip": ["2", 0],
            },
        },
        "5": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": "wan2.2_vae.safetensors",
            },
        },
        "6": {
            "class_type": "Wan22ImageToVideoLatent",
            "inputs": {
                "vae": ["5", 0],
                "width": width,
                "height": height,
                "length": length,
                "batch_size": 1,
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["6", 0],
                "seed": seed,
                "steps": steps,
                "cfg": 5.0,
                "sampler_name": "uni_pc_bh2",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["7", 0],
                "vae": ["5", 0],
            },
        },
        "9": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": "studio_video",
                "fps": 24,
                "lossless": False,
                "quality": 85,
                "method": "default",
            },
        },
    }

    # Inject LoRAs for talent identity consistency in video generation
    video_loras = data.get("loras", [])
    if not video_loras and data.get("lora"):
        video_loras = [{"id": data["lora"], "strength": data.get("lora_strength", 0.7)}]
    if video_loras:
        workflow = _inject_loras(workflow, video_loras, "wan2.2")

    # Submit video workflow to ComfyUI
    start_time = time.time()
    try:
        resp = httpx.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
        if resp.status_code != 200:
            # Parse error
            try:
                error_data = resp.json()
                node_errors = error_data.get("node_errors", {})
                if node_errors:
                    missing = []
                    for _nid, nerr in node_errors.items():
                        for e in nerr.get("errors", []):
                            if e.get("type") == "value_not_in_list":
                                missing.append(e.get("details", ""))
                    if missing:
                        raise HTTPException(
                            status_code=422,
                            detail=f"WAN 2.2 model files not found. Missing: {'; '.join(missing[:3])}",
                        )
            except HTTPException:
                raise
            except Exception:
                pass
            raise HTTPException(
                status_code=500, detail=f"ComfyUI rejected workflow: {resp.text[:200]}"
            )
        prompt_id = resp.json().get("prompt_id")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="ComfyUI connection lost")

    # Poll for result (video takes longer — up to 30 minutes)
    max_wait = 1800
    while time.time() - start_time < max_wait:
        time.sleep(5)
        try:
            hist = httpx.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10).json()
            if prompt_id in hist:
                entry = hist[prompt_id]
                status = entry.get("status", {})

                if status.get("completed"):
                    elapsed = round(time.time() - start_time, 1)

                    # Find output video/animated file
                    for _nid, out in entry.get("outputs", {}).items():
                        # Check for gifs/webp/videos
                        for key in ("gifs", "images", "videos"):
                            for item in out.get(key, []):
                                filename = item.get("filename", "")
                                subfolder = item.get("subfolder", "")
                                # Record cost
                                try:
                                    from backend.infrastructure.cost_intelligence import (
                                        get_cost_tracker,
                                    )

                                    tracker = get_cost_tracker()
                                    hourly_rate = float(
                                        os.getenv("VAST_CURRENT_HOURLY_RATE", "0.076")
                                    )
                                    gpu_cost = round((elapsed / 3600) * hourly_rate, 6)
                                    tracker.record_job_cost(
                                        job_type="video",
                                        model="wan2.2-5b",
                                        provider="comfyui",
                                        duration_seconds=elapsed,
                                        estimated_cost=gpu_cost,
                                        input_summary=prompt_text[:100],
                                        output_summary=filename,
                                    )
                                except Exception:
                                    pass

                                return {
                                    "success": True,
                                    "filename": filename,
                                    "generation_time": elapsed,
                                    "model": "wan2.2-5b",
                                    "prompt": prompt_text,
                                    "frames": length,
                                    "width": width,
                                    "height": height,
                                    "seed": seed,
                                    "estimated_cost": gpu_cost if "gpu_cost" in dir() else 0,
                                    "download_url": f"{COMFYUI_URL}/view?filename={filename}&type=output&subfolder={subfolder}",
                                }

                elif status.get("status_str") == "error":
                    msgs = status.get("messages", [])
                    err_msg = "Video generation failed"
                    for m in msgs:
                        if m[0] == "execution_error":
                            err_msg = m[1].get("exception_message", "")[:300]
                    raise HTTPException(status_code=500, detail=err_msg)
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503, detail="Lost connection to ComfyUI during generation"
            )

    raise HTTPException(status_code=504, detail="Video generation timed out (30 minutes)")


@router.post("/video-from-image")
async def generate_video_from_image(
    file: _UploadFile = _File(...),
    motion_prompt: str = _Form("gentle camera movement, cinematic"),
):
    """Generate video from a starting image + motion description.

    Uses WAN 2.2 TI2V hybrid model (text+image to video).
    """

    if not file.filename:
        raise HTTPException(status_code=400, detail="No image file provided")

    # Read image
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # Check ComfyUI
    try:
        health = httpx.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        if health.status_code != 200:
            raise HTTPException(status_code=503, detail="ComfyUI not responding")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="ComfyUI not reachable")

    # Upload image to ComfyUI's input folder
    try:
        upload_resp = httpx.post(
            f"{COMFYUI_URL}/upload/image",
            files={"image": (file.filename, image_bytes, "image/png")},
            timeout=30,
        )
        if upload_resp.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to upload image to ComfyUI")
        uploaded = upload_resp.json()
        input_filename = uploaded.get("name", file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {e}")

    seed = random.randint(1, 999999999)
    width = 832
    height = 480
    length = 49  # ~2s at 24fps
    steps = 20

    # Build WAN 2.2 I2V workflow
    workflow = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "wan2.2_ti2v_5B_fp16.safetensors",
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": motion_prompt,
                "clip": ["2", 0],
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "",
                "clip": ["2", 0],
            },
        },
        "5": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": "wan2.2_vae.safetensors",
            },
        },
        "6": {
            "class_type": "LoadImage",
            "inputs": {
                "image": input_filename,
            },
        },
        "7": {
            "class_type": "Wan22ImageToVideoLatent",
            "inputs": {
                "vae": ["5", 0],
                "width": width,
                "height": height,
                "length": length,
                "batch_size": 1,
                "image": ["6", 0],
            },
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["7", 0],
                "seed": seed,
                "steps": steps,
                "cfg": 5.0,
                "sampler_name": "uni_pc_bh2",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "9": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["8", 0],
                "vae": ["5", 0],
            },
        },
        "10": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["9", 0],
                "filename_prefix": "studio_i2v",
                "fps": 24,
                "lossless": False,
                "quality": 85,
                "method": "default",
            },
        },
    }

    # Submit to ComfyUI
    start_time = time.time()
    try:
        resp = httpx.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=500, detail=f"ComfyUI rejected I2V workflow: {resp.text[:200]}"
            )
        prompt_id = resp.json().get("prompt_id")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="ComfyUI connection lost")

    # Poll for result (up to 30 min)
    max_wait = 1800
    while time.time() - start_time < max_wait:
        time.sleep(5)
        try:
            hist = httpx.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10).json()
            if prompt_id in hist:
                entry = hist[prompt_id]
                status = entry.get("status", {})

                if status.get("completed"):
                    elapsed = round(time.time() - start_time, 1)
                    for _nid, out in entry.get("outputs", {}).items():
                        for key in ("gifs", "images", "videos"):
                            for item in out.get(key, []):
                                return {
                                    "success": True,
                                    "filename": item.get("filename", ""),
                                    "generation_time": elapsed,
                                    "model": "wan2.2-5b-i2v",
                                    "prompt": motion_prompt,
                                    "frames": length,
                                    "width": width,
                                    "height": height,
                                    "seed": seed,
                                    "source_image": input_filename,
                                }

                elif status.get("status_str") == "error":
                    msgs = status.get("messages", [])
                    err_msg = "I2V generation failed"
                    for m in msgs:
                        if m[0] == "execution_error":
                            err_msg = m[1].get("exception_message", "")[:300]
                    raise HTTPException(status_code=500, detail=err_msg)
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Lost connection during generation")

    raise HTTPException(status_code=504, detail="Video generation timed out (30 minutes)")
