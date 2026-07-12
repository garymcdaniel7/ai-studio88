"""Worker HTTP API — runs on the GPU worker for Vercel to dispatch jobs.

This is the bridge between the stateless Vercel backend and the GPU worker.
It exposes endpoints for:
- Health check
- Image/video generation (via ComfyUI)
- LoRA training
- Voice generation (via MOSS-TTS/Ollama)
- FFmpeg video transforms
- Model management (load/unload)

Runs on port 7860 (configurable via WORKER_API_PORT env var).

Start: python -m worker.api
Or: uvicorn worker.api:app --host 0.0.0.0 --port 7860
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker-api")

app = FastAPI(
    title="AI Studio Worker API",
    description="GPU Worker endpoint for AI Studio platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Worker is behind firewall/SSH tunnel
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKER_API_PORT = int(os.getenv("WORKER_API_PORT", "7860"))
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")


# =============================================================================
# Health
# =============================================================================


@app.get("/")
def root():
    return {"service": "ai-studio-worker", "status": "running", "port": WORKER_API_PORT}


@app.get("/health")
def health():
    """Full health check: GPU, ComfyUI, Ollama, ffmpeg, disk."""
    import httpx

    checks = {}

    # GPU
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,temperature.gpu,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            checks["gpu"] = {
                "available": True,
                "name": parts[0] if len(parts) > 0 else "Unknown",
                "vram_total_mb": int(parts[1]) if len(parts) > 1 else 0,
                "vram_free_mb": int(parts[2]) if len(parts) > 2 else 0,
                "temperature_c": int(parts[3]) if len(parts) > 3 else 0,
                "utilization_pct": int(parts[4]) if len(parts) > 4 else 0,
            }
        else:
            checks["gpu"] = {"available": False, "error": "nvidia-smi failed"}
    except Exception as e:
        checks["gpu"] = {"available": False, "error": str(e)[:100]}

    # ComfyUI
    try:
        resp = httpx.get(f"{COMFYUI_URL}/system_stats", timeout=3)
        checks["comfyui"] = {"available": resp.status_code == 200, "url": COMFYUI_URL}
    except Exception:
        checks["comfyui"] = {"available": False, "url": COMFYUI_URL}

    # Ollama
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = [m.get("name") for m in resp.json().get("models", [])]
            checks["ollama"] = {"available": True, "models": models[:5]}
        else:
            checks["ollama"] = {"available": False}
    except Exception:
        checks["ollama"] = {"available": False}

    # FFmpeg
    checks["ffmpeg"] = {"available": shutil.which("ffmpeg") is not None}

    # Disk
    try:
        usage = shutil.disk_usage("/workspace")
        checks["disk"] = {
            "total_gb": round(usage.total / (1024**3), 1),
            "free_gb": round(usage.free / (1024**3), 1),
            "used_pct": round((usage.used / usage.total) * 100, 1),
        }
    except Exception:
        checks["disk"] = {"total_gb": 0, "free_gb": 0}

    return {
        "status": "healthy",
        "worker_id": os.getenv("WORKER_ID", "unknown"),
        "checks": checks,
        "timestamp": time.time(),
    }


# =============================================================================
# Image Generation (via ComfyUI)
# =============================================================================


@app.post("/generate/image")
async def generate_image(data: dict):
    """Generate an image via ComfyUI.

    Body:
        prompt: str
        negative_prompt: str (optional)
        model: str (checkpoint name)
        width: int (default 1024)
        height: int (default 1024)
        steps: int (default 20)
        cfg: float (default 7.0)
        seed: int (optional, -1 for random)
        lora: str (optional, LoRA filename)
        lora_strength: float (optional, default 0.7)
    """
    import httpx

    prompt = data.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="'prompt' required")

    # Build ComfyUI workflow
    workflow = _build_image_workflow(data)

    # Submit to ComfyUI
    try:
        resp = httpx.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=10,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"ComfyUI rejected workflow: {resp.text[:200]}")

        prompt_id = resp.json().get("prompt_id")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="ComfyUI not running on this worker")

    # Poll for completion
    import asyncio
    max_wait = 300  # 5 minutes
    start = time.time()

    while time.time() - start < max_wait:
        await asyncio.sleep(2)
        try:
            history_resp = httpx.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=5)
            if history_resp.status_code == 200:
                history = history_resp.json()
                if prompt_id in history:
                    outputs = history[prompt_id].get("outputs", {})
                    # Find the output image
                    for node_id, node_output in outputs.items():
                        images = node_output.get("images", [])
                        if images:
                            img = images[0]
                            filename = img.get("filename")
                            subfolder = img.get("subfolder", "")
                            # Download the image from ComfyUI
                            img_resp = httpx.get(
                                f"{COMFYUI_URL}/view",
                                params={"filename": filename, "subfolder": subfolder, "type": "output"},
                                timeout=30,
                            )
                            if img_resp.status_code == 200:
                                import base64
                                image_b64 = base64.b64encode(img_resp.content).decode()
                                return {
                                    "success": True,
                                    "image_base64": image_b64,
                                    "filename": filename,
                                    "generation_time": round(time.time() - start, 2),
                                    "prompt": prompt,
                                    "model": data.get("model", "default"),
                                }
        except Exception:
            pass

    raise HTTPException(status_code=504, detail="Generation timed out (5 min)")


# =============================================================================
# FFmpeg Video Transform
# =============================================================================


@app.post("/ffmpeg/transform")
async def ffmpeg_transform(data: dict):
    """Apply ffmpeg transforms to a video.

    Body:
        source_url: str — URL of the source video to download
        trim_start: str (optional)
        trim_end: str (optional)
        speed: float (default 1.0)
        resolution: str (optional, e.g. "1080p", "720x480")
        color_grade: str (optional)
        text_overlay: str (optional)
    """
    import httpx

    source_url = data.get("source_url")
    if not source_url:
        raise HTTPException(status_code=400, detail="'source_url' required")

    if not shutil.which("ffmpeg"):
        raise HTTPException(status_code=503, detail="FFmpeg not installed on this worker")

    # Download source
    try:
        resp = httpx.get(source_url, timeout=60, follow_redirects=True)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Cannot download source video")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Download failed: {str(e)[:100]}")

    src_path = f"/tmp/src_{uuid.uuid4().hex[:8]}.mp4"
    out_path = f"/tmp/out_{uuid.uuid4().hex[:8]}.mp4"

    with open(src_path, "wb") as f:
        f.write(resp.content)

    # Build ffmpeg command
    cmd = ["ffmpeg", "-y", "-i", src_path]

    if data.get("trim_start"):
        cmd += ["-ss", str(data["trim_start"])]
    if data.get("trim_end"):
        cmd += ["-to", str(data["trim_end"])]

    speed = float(data.get("speed", 1.0))
    if speed != 1.0:
        cmd += ["-filter:v", f"setpts={1/speed}*PTS"]

    res = data.get("resolution")
    if res and res != "original":
        if "p" in str(res):
            cmd += ["-vf", f"scale=-2:{res.replace('p', '')}"]

    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "23", out_path]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return {"success": False, "error": result.stderr[:300]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "FFmpeg timed out"}

    # Read output and return as base64
    import base64
    with open(out_path, "rb") as f:
        content = f.read()

    # Cleanup
    os.unlink(src_path)
    os.unlink(out_path)

    return {
        "success": True,
        "video_base64": base64.b64encode(content).decode(),
        "size_bytes": len(content),
        "filename": f"transformed_{uuid.uuid4().hex[:8]}.mp4",
    }


# =============================================================================
# Ollama Chat (proxy)
# =============================================================================


@app.post("/ollama/chat")
async def ollama_chat(data: dict):
    """Proxy chat to local Ollama."""
    import httpx

    try:
        resp = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json=data,
            timeout=120,
        )
        if resp.status_code == 200:
            return resp.json()
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:200])
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Ollama not running on this worker")


@app.get("/ollama/models")
def ollama_models():
    """List Ollama models on this worker."""
    import httpx

    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {"models": []}


# =============================================================================
# TTS (MOSS)
# =============================================================================


@app.post("/tts/generate")
async def tts_generate(data: dict):
    """Generate speech via MOSS-TTS on this worker.

    Body:
        text: str
        voice_sample_url: str (optional, for cloning)
        language: str (default: en)
        speed: float (default: 1.0)
    """
    import httpx

    moss_url = os.getenv("MOSS_TTS_URL", "http://127.0.0.1:18083")

    text = data.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="'text' required")

    payload = {
        "text": text,
        "language": data.get("language", "en"),
        "speed": float(data.get("speed", 1.0)),
    }
    if data.get("voice_sample_url"):
        payload["prompt_audio_path"] = data["voice_sample_url"]

    try:
        resp = httpx.post(f"{moss_url}/generate", json=payload, timeout=120)
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            if "audio" in content_type:
                import base64
                return {
                    "success": True,
                    "audio_base64": base64.b64encode(resp.content).decode(),
                    "mime_type": "audio/wav",
                }
            else:
                return resp.json()
        raise HTTPException(status_code=resp.status_code, detail=f"MOSS-TTS error: {resp.text[:200]}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="MOSS-TTS not running on this worker (port 18083)")


# =============================================================================
# Model Management
# =============================================================================


@app.get("/models/loaded")
def list_loaded_models():
    """List models currently on this worker's disk."""
    model_dirs = [
        "/workspace/ComfyUI/models/checkpoints",
        "/workspace/ComfyUI/models/loras",
        "/workspace/ComfyUI/models/vae",
        "/workspace/ComfyUI/models/controlnet",
    ]
    models = {}
    for dir_path in model_dirs:
        category = Path(dir_path).name
        models[category] = []
        if os.path.isdir(dir_path):
            for f in os.listdir(dir_path):
                if f.endswith((".safetensors", ".ckpt", ".pt", ".gguf")):
                    full_path = os.path.join(dir_path, f)
                    size_mb = os.path.getsize(full_path) / (1024 * 1024)
                    models[category].append({"name": f, "size_mb": round(size_mb, 1)})
    return {"models": models}


@app.post("/models/download")
async def download_model(data: dict):
    """Download a model from B2 to this worker.

    Body:
        url: str — B2 download URL
        destination: str — where to save (e.g. /workspace/ComfyUI/models/checkpoints/model.safetensors)
    """
    import httpx

    url = data.get("url")
    destination = data.get("destination")
    if not url or not destination:
        raise HTTPException(status_code=400, detail="'url' and 'destination' required")

    # Ensure directory exists
    os.makedirs(os.path.dirname(destination), exist_ok=True)

    try:
        with httpx.stream("GET", url, timeout=600, follow_redirects=True) as resp:
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Download failed: HTTP {resp.status_code}")
            with open(destination, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download error: {str(e)[:200]}")

    size_mb = os.path.getsize(destination) / (1024 * 1024)
    return {"success": True, "path": destination, "size_mb": round(size_mb, 1)}


# =============================================================================
# Helpers
# =============================================================================


def _build_image_workflow(data: dict) -> dict:
    """Build a ComfyUI workflow JSON from generation parameters."""
    # Load the appropriate template
    model = data.get("model", "flux-dev")
    prompt = data.get("prompt", "")
    negative = data.get("negative_prompt", "")
    width = data.get("width", 1024)
    height = data.get("height", 1024)
    steps = data.get("steps", 20)
    cfg = data.get("cfg", 7.0)
    seed = data.get("seed", -1)
    if seed == -1:
        import random
        seed = random.randint(0, 2**32 - 1)

    # Basic SDXL/Flux workflow (simplified — production would load from templates)
    workflow = {
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
            "inputs": {"ckpt_name": _resolve_checkpoint(model)},
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
            "inputs": {"text": negative or "low quality, blurry", "clip": ["4", 1]},
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

    return workflow


def _resolve_checkpoint(model_name: str) -> str:
    """Resolve a model name to a ComfyUI checkpoint filename."""
    mapping = {
        "flux-dev": "flux1-dev-fp8.safetensors",
        "sdxl": "sd_xl_base_1.0.safetensors",
        "sdxl-turbo": "sd_xl_turbo_1.0_fp16.safetensors",
        "sd15": "v1-5-pruned-emaonly.safetensors",
    }
    return mapping.get(model_name, model_name)


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Worker API on port {WORKER_API_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=WORKER_API_PORT)
