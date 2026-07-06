"""SSE Progress — Server-Sent Events for real-time generation/training updates.

Provides a streaming endpoint that pushes progress updates to the frontend
without polling. Uses FastAPI's StreamingResponse with text/event-stream.

Frontend usage:
    const es = new EventSource('/api/v1/infrastructure/progress/stream?job_id=xxx');
    es.onmessage = (e) => { const data = JSON.parse(e.data); ... };
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import AsyncGenerator

import httpx


async def generate_progress_events(job_id: str) -> AsyncGenerator[str, None]:
    """Yield SSE events for a job's progress.

    Polls ComfyUI and job records every 2 seconds and yields updates.
    Closes when job completes, fails, or after 10 minutes.
    """
    comfyui_url = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
    start = time.time()
    timeout = 600  # 10 minutes max

    last_status = None

    while time.time() - start < timeout:
        progress_data = {
            "job_id": job_id,
            "status": "unknown",
            "progress": 0.0,
            "current_step": 0,
            "total_steps": 0,
            "elapsed_seconds": round(time.time() - start),
        }

        # Check ComfyUI queue
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{comfyui_url}/queue", timeout=3)
                if resp.status_code == 200:
                    queue = resp.json()
                    running = queue.get("queue_running", [])
                    pending = queue.get("queue_pending", [])

                    for item in running:
                        if len(item) > 1 and item[1].get("prompt_id") == job_id:
                            progress_data["status"] = "running"
                            break

                    for item in pending:
                        if len(item) > 1 and item[1].get("prompt_id") == job_id:
                            progress_data["status"] = "queued"
                            break

                # Check history for completion
                resp = await client.get(f"{comfyui_url}/history/{job_id}", timeout=3)
                if resp.status_code == 200:
                    history = resp.json()
                    if job_id in history:
                        outputs = history[job_id].get("outputs", {})
                        if outputs:
                            progress_data["status"] = "completed"
                            progress_data["progress"] = 1.0
        except Exception:
            pass

        # Check training jobs table
        if progress_data["status"] == "unknown":
            try:
                from backend.database import supabase
                result = supabase.table("training_jobs").select(
                    "status,current_step,config"
                ).eq("id", job_id).single().execute()
                if result.data:
                    progress_data["status"] = result.data.get("status", "unknown")
                    progress_data["current_step"] = result.data.get("current_step", 0)
                    config = result.data.get("config") or {}
                    progress_data["total_steps"] = config.get("steps", 0)
                    if progress_data["total_steps"] > 0:
                        progress_data["progress"] = (
                            progress_data["current_step"] / progress_data["total_steps"]
                        )
            except Exception:
                pass

        # Yield SSE event
        event_data = json.dumps(progress_data)
        yield f"data: {event_data}\n\n"

        # Check if done
        if progress_data["status"] in ("completed", "failed", "cancelled"):
            yield f"data: {json.dumps({'status': progress_data['status'], 'done': True})}\n\n"
            return

        # Only yield if status changed or on interval
        last_status = progress_data["status"]
        await asyncio.sleep(2)

    # Timeout
    yield f"data: {json.dumps({'status': 'timeout', 'done': True})}\n\n"
