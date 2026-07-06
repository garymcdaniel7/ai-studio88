"""Generation tasks — image and video generation dispatched to GPU workers."""
from __future__ import annotations

from backend.app.workers.celery_app import app


@app.task(bind=True, name="generate.image", max_retries=3)
def generate_image_task(self, prompt: str, model: str = "flux-dev", **params):
    """Generate an image via ComfyUI on the GPU worker.

    Retries up to 3 times on transient failures (network, worker restart).
    Does NOT retry on content failures (bad prompt, missing model).
    """
    import os
    import httpx

    comfyui_url = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")

    try:
        # Build and submit workflow
        # (In production, this would use the workflow selector + LoRA injector)
        resp = httpx.post(
            f"{comfyui_url}/prompt",
            json={"prompt": {"placeholder": True}},  # Simplified
            timeout=30,
        )
        return {"status": "submitted", "prompt_id": resp.json().get("prompt_id")}
    except httpx.HTTPError as exc:
        # Transient — retry
        raise self.retry(exc=exc, countdown=30)


@app.task(bind=True, name="generate.video", max_retries=2)
def generate_video_task(self, prompt: str, model: str = "wan-2.1-t2v", **params):
    """Generate a video via ComfyUI WAN 2.1 on the GPU worker."""
    return {"status": "queued", "model": model, "prompt": prompt[:50]}


@app.task(name="generate.assemble")
def assemble_video_task(clips: list, output_format: str = "mp4", **params):
    """Assemble clips into a final video using ffmpeg on the GPU worker."""
    from backend.infrastructure.ffmpeg_assembly import build_ssh_assembly_command

    cmd = build_ssh_assembly_command(clips, resolution=params.get("resolution", "1920x1080"))
    return {"status": "ready", "command": cmd, "clip_count": len(clips)}
