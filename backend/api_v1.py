"""V1 API router — wraps existing Supabase functions under /api/v1/.

These endpoints mirror the root-level ones but under the versioned prefix.
They use the existing database.py Supabase client directly (no ORM, no auth).
As services are implemented, these will be replaced by the full scaffold endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.database import (
    get_projects,
    get_talent,
    create_talent,
    get_assets,
    get_asset_by_id,
    create_asset,
    delete_asset,
    get_jobs,
    get_job_by_id,
    create_job,
    update_job,
    delete_job,
)
from backend.storage import upload_file, delete_file, generate_storage_key, compute_checksum

router = APIRouter()


@router.get("/health", tags=["v1-ops"])
def v1_health():
    """V1 API liveness check."""
    return {"status": "ok", "api": "v1"}


@router.get("/projects", tags=["v1-projects"])
def v1_projects():
    """List all projects."""
    return get_projects().data


@router.get("/talent", tags=["v1-talent"])
def v1_talent():
    """List all AI talent."""
    return get_talent().data


@router.post("/talent", tags=["v1-talent"])
def v1_create_talent(talent_data: dict):
    """Create a new AI talent record."""
    try:
        result = create_talent(talent_data)
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# Assets
# =============================================================================

from fastapi import UploadFile, File, Form
from typing import Optional


@router.get("/assets", tags=["v1-assets"])
def v1_list_assets():
    """List all assets, ordered by most recent first."""
    return get_assets().data


@router.get("/assets/{asset_id}", tags=["v1-assets"])
def v1_get_asset(asset_id: str):
    """Get a single asset by ID."""
    try:
        result = get_asset_by_id(asset_id)
        return result.data
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Asset not found: {e}")


@router.post("/assets", tags=["v1-assets"], status_code=201)
async def v1_upload_asset(
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    talent_id: Optional[str] = Form(None),
    asset_type: str = Form("general"),
    tags: Optional[str] = Form(None),
):
    """Upload a file to Backblaze B2 and store metadata in Supabase.

    Accepts multipart/form-data with a file and optional metadata fields.
    Tags should be comma-separated (e.g. "portrait,headshot,flux").
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    original_filename = file.filename or "unnamed"
    storage_key = generate_storage_key(
        original_filename=original_filename,
        asset_type=asset_type,
        project_id=project_id,
    )
    checksum = compute_checksum(content)
    mime_type = file.content_type or "application/octet-stream"

    # Upload to B2
    try:
        public_url = upload_file(content, storage_key, mime_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {e}")

    # Parse tags
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()] or None

    # Store metadata in Supabase
    asset_record = {
        "project_id": project_id,
        "talent_id": talent_id,
        "type": asset_type,
        "filename": storage_key.split("/")[-1],
        "original_filename": original_filename,
        "mime_type": mime_type,
        "size_bytes": len(content),
        "storage_provider": "backblaze_b2",
        "storage_key": storage_key,
        "public_url": public_url,
        "checksum": checksum,
        "metadata": {"upload_source": "api_v1"},
        "tags": tag_list,
    }

    try:
        result = create_asset(asset_record)
        return result.data[0] if result.data else asset_record
    except Exception as e:
        # Clean up B2 on DB failure
        try:
            delete_file(storage_key)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to save asset metadata: {e}")


@router.delete("/assets/{asset_id}", tags=["v1-assets"])
def v1_delete_asset(asset_id: str):
    """Delete an asset from B2 storage and Supabase."""
    try:
        asset = get_asset_by_id(asset_id).data
    except Exception:
        raise HTTPException(status_code=404, detail="Asset not found")

    storage_key = asset.get("storage_key")
    if storage_key:
        try:
            delete_file(storage_key)
        except Exception:
            pass  # Best-effort B2 cleanup

    try:
        delete_asset(asset_id)
        return {"deleted": True, "asset": asset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete asset: {e}")


# =============================================================================
# Jobs
# =============================================================================

VALID_JOB_TYPES = [
    "image_generation",
    "video_generation",
    "lora_training",
    "image_upscale",
    "image_edit",
    "voice_generation",
    "workflow_execution",
    "asset_processing",
    "publishing",
]


@router.get("/jobs", tags=["v1-jobs"])
def v1_list_jobs(status: Optional[str] = None, type: Optional[str] = None):
    """List jobs, optionally filtered by status and/or type."""
    return get_jobs(status=status, job_type=type).data


@router.get("/jobs/{job_id}", tags=["v1-jobs"])
def v1_get_job(job_id: str):
    """Get a single job by ID."""
    try:
        return get_job_by_id(job_id).data
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Job not found: {e}")


@router.post("/jobs", tags=["v1-jobs"], status_code=201)
def v1_create_job(job_data: dict):
    """Create a new job and queue it for processing.

    Required fields:
        type: one of the valid job types

    Optional fields:
        project_id, talent_id, workflow_id, priority (1-10), input (json)
    """
    job_type = job_data.get("type")
    if not job_type:
        raise HTTPException(status_code=400, detail="'type' is required")
    if job_type not in VALID_JOB_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid job type '{job_type}'. Valid types: {VALID_JOB_TYPES}",
        )

    # Build job record with defaults
    record = {
        "type": job_type,
        "status": "queued",
        "priority": min(max(int(job_data.get("priority", 5)), 1), 10),
        "input": job_data.get("input", {}),
        "project_id": job_data.get("project_id"),
        "talent_id": job_data.get("talent_id"),
        "workflow_id": job_data.get("workflow_id"),
        "progress": 0,
        "attempts": 0,
        "max_attempts": int(job_data.get("max_attempts", 3)),
    }

    try:
        result = create_job(record)
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create job: {e}")


@router.delete("/jobs/{job_id}", tags=["v1-jobs"])
def v1_delete_job(job_id: str):
    """Delete a job. Only queued or terminal jobs can be deleted."""
    try:
        job = get_job_by_id(job_id).data
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") == "running":
        raise HTTPException(status_code=409, detail="Cannot delete a running job. Cancel it first.")

    try:
        delete_job(job_id)
        return {"deleted": True, "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {e}")


@router.post("/jobs/{job_id}/cancel", tags=["v1-jobs"])
def v1_cancel_job(job_id: str):
    """Cancel a queued or running job."""
    try:
        job = get_job_by_id(job_id).data
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    current_status = job.get("status")
    if current_status in ("completed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Job is already {current_status}")
    if current_status == "failed":
        raise HTTPException(status_code=409, detail="Cannot cancel a failed job")

    try:
        update_job(job_id, {"status": "cancelled"})
        return {"cancelled": True, "job_id": job_id, "previous_status": current_status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {e}")


@router.post("/jobs/{job_id}/retry", tags=["v1-jobs"])
def v1_retry_job(job_id: str):
    """Retry a failed or cancelled job by resetting it to queued."""
    try:
        job = get_job_by_id(job_id).data
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    current_status = job.get("status")
    if current_status not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Can only retry failed or cancelled jobs. Current status: {current_status}",
        )

    attempts = job.get("attempts", 0)
    max_attempts = job.get("max_attempts", 3)
    if attempts >= max_attempts:
        raise HTTPException(
            status_code=409,
            detail=f"Max attempts ({max_attempts}) reached. Increase max_attempts to retry.",
        )

    try:
        update_job(job_id, {
            "status": "queued",
            "error": None,
            "progress": 0,
            "started_at": None,
            "completed_at": None,
        })
        return {"retried": True, "job_id": job_id, "attempt": attempts + 1}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retry job: {e}")


# =============================================================================
# Workflows
# =============================================================================

from backend.database import (
    get_workflows,
    get_workflow_by_id,
    create_workflow,
    update_workflow,
    delete_workflow,
    get_workflow_run,
)
from backend.workflow_engine import execute_workflow


VALID_WORKFLOW_STATUSES = ["draft", "active", "archived"]
VALID_TRIGGER_TYPES = ["manual", "schedule", "event", "api"]


@router.get("/workflows", tags=["v1-workflows"])
def v1_list_workflows(status: Optional[str] = None):
    """List all workflows, optionally filtered by status."""
    return get_workflows(status=status).data


@router.get("/workflows/{workflow_id}", tags=["v1-workflows"])
def v1_get_workflow(workflow_id: str):
    """Get a single workflow by ID with full step definitions."""
    try:
        return get_workflow_by_id(workflow_id).data
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {e}")


@router.post("/workflows", tags=["v1-workflows"], status_code=201)
def v1_create_workflow(data: dict):
    """Create a new workflow.

    Required fields:
        name: Human-readable workflow name
        steps: Array of step definitions

    Each step:
        {
            "name": "Step Name",
            "handler": "image_generation",  (must be a registered job type)
            "config": {},                   (input params for the handler)
            "depends_on": []               (indices of prerequisite steps)
        }
    """
    name = data.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="'name' is required")

    steps = data.get("steps", [])
    if not steps:
        raise HTTPException(status_code=400, detail="'steps' array is required and must not be empty")

    # Validate steps
    for i, step in enumerate(steps):
        if "handler" not in step:
            raise HTTPException(status_code=400, detail=f"Step {i} missing 'handler' field")
        deps = step.get("depends_on", [])
        for dep in deps:
            if dep < 0 or dep >= len(steps) or dep == i:
                raise HTTPException(status_code=400, detail=f"Step {i} has invalid depends_on: {dep}")

    record = {
        "name": name,
        "description": data.get("description", ""),
        "project_id": data.get("project_id"),
        "version": int(data.get("version", 1)),
        "status": data.get("status", "active"),
        "trigger_type": data.get("trigger_type", "manual"),
        "steps": steps,
        "definition": data.get("definition", {}),
    }

    try:
        result = create_workflow(record)
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {e}")


@router.put("/workflows/{workflow_id}", tags=["v1-workflows"])
def v1_update_workflow(workflow_id: str, data: dict):
    """Update a workflow's definition, steps, or metadata."""
    try:
        get_workflow_by_id(workflow_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Workflow not found")

    allowed_fields = {"name", "description", "version", "status", "trigger_type", "steps", "definition"}
    update_data = {k: v for k, v in data.items() if k in allowed_fields}

    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    try:
        result = update_workflow(workflow_id, update_data)
        return result.data[0] if result.data else update_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update workflow: {e}")


@router.delete("/workflows/{workflow_id}", tags=["v1-workflows"])
def v1_delete_workflow(workflow_id: str):
    """Delete a workflow."""
    try:
        get_workflow_by_id(workflow_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Workflow not found")

    try:
        delete_workflow(workflow_id)
        return {"deleted": True, "workflow_id": workflow_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete workflow: {e}")


@router.post("/workflows/{workflow_id}/run", tags=["v1-workflows"])
def v1_run_workflow(workflow_id: str, data: dict = {}):
    """Execute a workflow, spawning child jobs for each step.

    Steps are executed in dependency order. Each step creates a job
    using the configured handler. Outputs from earlier steps are
    available to dependent steps.

    Returns the workflow run record with status and outputs.
    """
    try:
        get_workflow_by_id(workflow_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Workflow not found")

    try:
        result = execute_workflow(workflow_id, run_input=data.get("input"))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {e}")


# =============================================================================
# Creative DNA
# =============================================================================

from backend.database import (
    get_creative_dna_list,
    get_creative_dna_by_talent,
    create_creative_dna,
    update_creative_dna,
    get_feedback,
    create_feedback,
)


@router.get("/creative-dna", tags=["v1-creative-dna"])
def v1_list_creative_dna():
    """List all creative DNA records."""
    return get_creative_dna_list().data


@router.get("/creative-dna/{talent_id}", tags=["v1-creative-dna"])
def v1_get_creative_dna(talent_id: str):
    """Get creative DNA for a specific talent."""
    try:
        return get_creative_dna_by_talent(talent_id).data
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Creative DNA not found: {e}")


@router.post("/creative-dna", tags=["v1-creative-dna"], status_code=201)
def v1_create_creative_dna(data: dict):
    """Create a creative DNA record for a talent.

    Required: talent_id
    Optional: preferred_styles, avoided_styles, color_palette,
              camera_preferences, wardrobe_preferences, setting_preferences,
              prompt_rules, negative_prompt_rules, lora_preferences,
              model_preferences, notes
    """
    if not data.get("talent_id"):
        raise HTTPException(status_code=400, detail="'talent_id' is required")
    try:
        result = create_creative_dna(data)
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create creative DNA: {e}")


@router.put("/creative-dna/{dna_id}", tags=["v1-creative-dna"])
def v1_update_creative_dna(dna_id: str, data: dict):
    """Update a creative DNA record."""
    try:
        result = update_creative_dna(dna_id, data)
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update creative DNA: {e}")


# =============================================================================
# Feedback
# =============================================================================

VALID_PROBLEMS = [
    "face_drift",
    "bad_hands",
    "bad_lighting",
    "poor_motion",
    "identity_mismatch",
    "wrong_outfit",
    "poor_composition",
    "too_artificial",
    "prompt_mismatch",
]


@router.get("/feedback", tags=["v1-feedback"])
def v1_list_feedback(talent_id: Optional[str] = None):
    """List generation feedback, optionally filtered by talent."""
    return get_feedback(talent_id=talent_id).data


@router.post("/feedback", tags=["v1-feedback"], status_code=201)
def v1_submit_feedback(data: dict):
    """Submit feedback on a generation output.

    Required: rating (1-5)
    Optional: job_id, asset_id, talent_id, project_id, problems[], notes, context{}
    """
    rating = data.get("rating")
    if not rating or not (1 <= int(rating) <= 5):
        raise HTTPException(status_code=400, detail="'rating' must be 1-5")

    problems = data.get("problems", [])
    for p in problems:
        if p not in VALID_PROBLEMS:
            raise HTTPException(status_code=400, detail=f"Invalid problem tag: '{p}'. Valid: {VALID_PROBLEMS}")

    record = {
        "rating": int(rating),
        "problems": problems if problems else None,
        "notes": data.get("notes"),
        "job_id": data.get("job_id"),
        "asset_id": data.get("asset_id"),
        "talent_id": data.get("talent_id"),
        "project_id": data.get("project_id"),
        "context": data.get("context", {}),
    }

    try:
        result = create_feedback(record)
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save feedback: {e}")


# =============================================================================
# Generation Engine
# =============================================================================

from backend.engine.generation_engine import (
    GenerationEngine,
    get_gpu_status,
    get_model_registry,
    get_model,
    PROVIDERS,
    get_default_provider_name,
)
from backend.engine.models import GenerationRequest, GenerationType


@router.get("/generation/health", tags=["v1-generation"])
def v1_generation_health():
    """Check generation provider health and GPU status."""
    engine = GenerationEngine()
    health = engine.health()
    gpu = get_gpu_status()
    return {
        "provider": engine.provider_name,
        "healthy": health.healthy,
        "message": health.message,
        "gpu": {
            "name": gpu.name,
            "vram_total_gb": gpu.vram_total_gb,
            "vram_free_gb": gpu.vram_free_gb,
            "utilization_pct": gpu.utilization_pct,
            "temperature_c": gpu.temperature_c,
            "status": gpu.status,
            "current_job": gpu.current_job,
            "queue_size": gpu.queue_size,
        },
    }


@router.get("/generation/providers", tags=["v1-generation"])
def v1_list_providers():
    """List available generation providers."""
    result = []
    for name, cls in PROVIDERS.items():
        p = cls()
        caps = p.capabilities()
        result.append({
            "name": name,
            "is_default": name == get_default_provider_name(),
            "supports_image": caps.supports_image,
            "supports_video": caps.supports_video,
            "supports_upscale": caps.supports_upscale,
            "supports_training": caps.supports_training,
            "max_resolution": caps.max_resolution,
            "supported_models": caps.supported_models,
        })
    return result


@router.get("/generation/models", tags=["v1-generation"])
def v1_list_models():
    """List all registered models (checkpoints, LoRAs, etc.)."""
    return [
        {
            "id": m.id,
            "name": m.name,
            "type": m.type,
            "version": m.version,
            "provider": m.provider,
            "capabilities": m.capabilities,
            "required_vram_gb": m.required_vram_gb,
            "status": m.status,
        }
        for m in get_model_registry()
    ]


@router.post("/generation/run", tags=["v1-generation"], status_code=201)
def v1_run_generation(data: dict):
    """Execute a generation request through the Generation Engine.

    This is the primary endpoint for triggering content generation.
    Creates the content, uploads to B2, and registers as an asset.

    Required fields:
        prompt: The generation prompt

    Optional fields:
        type: image_generation (default), video_generation, image_upscale
        negative_prompt, width, height, steps, cfg_scale, seed, model,
        lora, lora_strength, talent_id, project_id, provider
    """
    prompt = data.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="'prompt' is required")

    # Build request
    gen_type = data.get("type", "image_generation")
    try:
        request = GenerationRequest(
            type=GenerationType(gen_type),
            prompt=prompt,
            negative_prompt=data.get("negative_prompt", ""),
            width=int(data.get("width", 1024)),
            height=int(data.get("height", 1024)),
            steps=int(data.get("steps", 20)),
            cfg_scale=float(data.get("cfg_scale", 7.0)),
            seed=int(data.get("seed", -1)),
            model=data.get("model", "flux-dev"),
            lora=data.get("lora"),
            lora_strength=float(data.get("lora_strength", 0.7)),
            talent_id=data.get("talent_id"),
            project_id=data.get("project_id"),
            creative_session_id=data.get("creative_session_id"),
            extra=data.get("extra", {}),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid generation type: {e}")

    # Select provider
    provider_name = data.get("provider", get_default_provider_name())
    try:
        engine = GenerationEngine(provider_name=provider_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Also create a job record for tracking
    job_data = create_job({
        "type": gen_type,
        "status": "running",
        "priority": int(data.get("priority", 7)),
        "input": {
            "prompt": prompt,
            "negative_prompt": request.negative_prompt,
            "width": request.width,
            "height": request.height,
            "steps": request.steps,
            "model": request.model,
            "provider": provider_name,
        },
        "project_id": request.project_id,
        "talent_id": request.talent_id,
        "workflow_id": data.get("workflow_id"),
        "worker_name": f"engine-{provider_name}",
        "worker_id": f"engine-{provider_name}",
        "started_at": "now()",
    })
    job = job_data.data[0] if job_data.data else {}
    job_id = job.get("id", "")

    # Execute
    try:
        def on_progress(p):
            try:
                update_job(job_id, {"progress": p.percent})
            except Exception:
                pass

        asset = engine.generate_and_register(request, on_progress=on_progress)

        # Mark job completed
        from backend.database import complete_job
        complete_job(job_id, {
            "asset_id": asset.get("id"),
            "public_url": asset.get("public_url"),
            "generation_time": asset.get("metadata", {}).get("generation_time_seconds"),
        })

        # Auto-capture prompt history for learning
        try:
            record_prompt_history({
                "talent_id": request.talent_id,
                "job_id": job_id,
                "model": request.model,
                "positive_prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "prompt_metadata": {
                    "steps": request.steps,
                    "cfg_scale": request.cfg_scale,
                    "width": request.width,
                    "height": request.height,
                    "lora": request.lora,
                    "lora_strength": request.lora_strength,
                    "provider": provider_name,
                    "seed": asset.get("metadata", {}).get("seed_used"),
                },
            })
        except Exception:
            pass  # Non-critical — don't fail generation for history capture

        return {
            "status": "completed",
            "job_id": job_id,
            "asset": asset,
            "provider": provider_name,
        }

    except Exception as e:
        # Mark job failed
        from backend.database import fail_job
        fail_job(job_id, str(e))
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")


# =============================================================================
# Generation History + Lifecycle
# =============================================================================


@router.get("/generation/history", tags=["v1-generation"])
def v1_generation_history(talent_id: Optional[str] = None, limit: int = 20):
    """List past generation outputs with full metadata.

    Returns assets that were created by the Generation Engine,
    ordered by most recent first. Includes all generation parameters.
    """
    from backend.database import supabase

    query = (
        supabase.table("assets")
        .select("*")
        .contains("tags", ["image_generation"])
        .order("created_at", desc=True)
        .limit(limit)
    )
    if talent_id:
        query = query.eq("talent_id", talent_id)

    result = query.execute()

    # Also include video generations
    query2 = (
        supabase.table("assets")
        .select("*")
        .contains("tags", ["video_generation"])
        .order("created_at", desc=True)
        .limit(limit)
    )
    if talent_id:
        query2 = query2.eq("talent_id", talent_id)

    result2 = query2.execute()

    # Merge and sort
    all_items = (result.data or []) + (result2.data or [])
    all_items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return all_items[:limit]


@router.post("/generation/{job_id}/cancel", tags=["v1-generation"])
def v1_cancel_generation(job_id: str):
    """Cancel a running generation job.

    Attempts to cancel via the provider, then marks the job as cancelled.
    """
    try:
        job = get_job_by_id(job_id).data
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") not in ("queued", "running"):
        raise HTTPException(status_code=409, detail=f"Cannot cancel job in status: {job['status']}")

    # Attempt provider cancellation
    engine = GenerationEngine()
    engine._provider.cancel(job_id)

    # Mark cancelled in DB
    update_job(job_id, {"status": "cancelled"})
    return {"cancelled": True, "job_id": job_id}


@router.post("/generation/{job_id}/retry", tags=["v1-generation"])
def v1_retry_generation(job_id: str):
    """Retry a failed generation by re-running with the same parameters.

    Creates a new generation job using the original input parameters.
    """
    try:
        job = get_job_by_id(job_id).data
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") not in ("failed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Can only retry failed/cancelled jobs")

    # Re-submit using original input
    original_input = job.get("input", {})
    if not original_input.get("prompt"):
        raise HTTPException(status_code=400, detail="Original job has no prompt to retry")

    # Create a new generation using the same parameters
    gen_data = {
        "prompt": original_input.get("prompt", ""),
        "negative_prompt": original_input.get("negative_prompt", ""),
        "width": original_input.get("width", 1024),
        "height": original_input.get("height", 1024),
        "steps": original_input.get("steps", 20),
        "model": original_input.get("model", "flux-dev"),
        "talent_id": job.get("talent_id"),
        "project_id": job.get("project_id"),
        "provider": original_input.get("provider", get_default_provider_name()),
    }

    return v1_run_generation(gen_data)


@router.get("/generation/{job_id}/status", tags=["v1-generation"])
def v1_generation_status(job_id: str):
    """Get live status and progress for a generation job.

    Used by the dashboard to poll for progress updates.
    """
    try:
        job = get_job_by_id(job_id).data
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "type": job.get("type"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "error": job.get("error"),
        "worker_name": job.get("worker_name"),
        "output": job.get("output", {}),
    }


# =============================================================================
# Intelligence Engine (Phase B)
# =============================================================================

from backend.intelligence_engine.orchestrator import build_creative_plan


@router.post("/intelligence/plan", tags=["v1-intelligence"])
def v1_build_plan(data: dict):
    """Run the full AI Intelligence Engine and produce a creative plan.

    The system thinks before generating: 10 specialized agents analyze context,
    Creative DNA, feedback history, and available resources to produce an
    optimized plan with full reasoning.

    Required: user_idea
    Optional: talent_id, project_id, platform, content_type, campaign, target_audience
    """
    user_idea = data.get("user_idea")
    if not user_idea:
        raise HTTPException(status_code=400, detail="'user_idea' is required")

    plan = build_creative_plan(
        user_idea=user_idea,
        talent_id=data.get("talent_id"),
        project_id=data.get("project_id"),
        platform=data.get("platform", "instagram"),
        content_type=data.get("content_type", "image"),
        campaign=data.get("campaign", ""),
        target_audience=data.get("target_audience", ""),
    )

    return {
        "session_id": plan.session_id,
        "prompt": plan.prompt,
        "negative_prompt": plan.negative_prompt,
        "model": plan.model,
        "settings": plan.settings,
        "workflow_steps": plan.workflow_steps,
        "gpu_routing": plan.gpu_routing,
        "publishing": plan.publishing,
        "estimated_time": plan.estimated_time,
        "estimated_cost": plan.estimated_cost,
        "confidence": plan.confidence,
        "agents": [
            {
                "agent": o.agent,
                "recommendations": o.recommendations,
                "reasoning": o.reasoning,
                "confidence": o.confidence,
            }
            for o in plan.agent_outputs
        ],
    }


# =============================================================================
# Execution Platform (Phase C)
# =============================================================================

from backend.execution.worker_manager import (
    register_worker, heartbeat, list_workers, get_worker,
    unregister_worker, mark_worker_idle, detect_offline_workers, get_system_health,
)
from backend.execution.provider_registry import list_providers as list_exec_providers, get_provider
from backend.execution.job_router import job_router, RoutingDecision
from backend.execution.provider_interface import ExecutionRequest


@router.get("/execution/health", tags=["v1-execution"])
def v1_execution_health():
    """Overall execution platform health."""
    health = get_system_health()
    offline = detect_offline_workers()
    return {
        **health,
        "newly_offline": [w.name for w in offline],
    }


@router.get("/execution/workers", tags=["v1-execution"])
def v1_list_workers(status: Optional[str] = None):
    """List all registered workers with GPU info."""
    workers = list_workers(status=status)
    return [
        {
            "id": w.id,
            "name": w.name,
            "provider": w.provider,
            "status": w.status,
            "url": w.url,
            "gpu": {
                "model": w.gpu.model,
                "vram_total_gb": w.gpu.vram_total_gb,
                "vram_free_gb": w.gpu.vram_free_gb,
                "cuda_version": w.gpu.cuda_version,
                "temperature_c": w.gpu.temperature_c,
                "utilization_pct": w.gpu.utilization_pct,
                "supported_models": w.gpu.supported_models,
            },
            "current_job": w.current_job,
            "queue_size": w.queue_size,
            "is_alive": w.is_alive,
            "tags": w.tags,
        }
        for w in workers
    ]


@router.post("/execution/workers/register", tags=["v1-execution"], status_code=201)
def v1_register_worker(data: dict):
    """Register a new worker with the platform."""
    name = data.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="'name' is required")

    worker = register_worker(
        name=name,
        provider=data.get("provider", "local"),
        url=data.get("url", ""),
        gpu=data.get("gpu"),
        tags=data.get("tags", []),
    )
    return {"worker_id": worker.id, "name": worker.name, "status": worker.status}


@router.post("/execution/workers/{worker_id}/heartbeat", tags=["v1-execution"])
def v1_worker_heartbeat(worker_id: str, data: dict = {}):
    """Worker heartbeat — keeps worker alive in the registry."""
    worker = heartbeat(worker_id, gpu_status=data.get("gpu"))
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return {"status": worker.status, "acknowledged": True}


@router.delete("/execution/workers/{worker_id}", tags=["v1-execution"])
def v1_unregister_worker(worker_id: str):
    """Remove a worker from the registry."""
    if unregister_worker(worker_id):
        return {"unregistered": True, "worker_id": worker_id}
    raise HTTPException(status_code=404, detail="Worker not found")


@router.get("/execution/providers", tags=["v1-execution"])
def v1_list_execution_providers():
    """List all registered execution providers with health status."""
    return list_exec_providers()


@router.post("/execution/route", tags=["v1-execution"])
def v1_route_job(data: dict):
    """Route a job to the best available worker.

    Returns the routing decision (which worker, why).
    Does NOT execute the job — just determines where it should go.
    """
    request = ExecutionRequest(
        job_id=data.get("job_id", ""),
        type=data.get("type", "image"),
        provider=data.get("provider", ""),
        model=data.get("model", ""),
        parameters=data.get("parameters", {}),
        priority=int(data.get("priority", 5)),
    )

    decision = job_router.route(request)
    if not decision:
        raise HTTPException(status_code=503, detail="No suitable worker available")

    return {
        "worker_id": decision.worker_id,
        "worker_name": decision.worker_name,
        "provider": decision.provider,
        "reason": decision.reason,
        "estimated_wait_seconds": decision.estimated_wait_seconds,
    }


# =============================================================================
# Creative DNA Engine — Phase D additions
# =============================================================================

from backend.database import (
    get_continuity_notes, create_continuity_note, update_continuity_note, delete_continuity_note,
    get_creative_rules, create_creative_rule, delete_creative_rule,
    get_style_preferences, upsert_style_preference,
    record_prompt_history, get_prompt_history,
)


# ── Dedicated talent-scoped endpoints ─────────────────────────────────────────

@router.get("/creative-dna/talent/{talent_id}", tags=["v1-creative-dna"])
def v1_get_dna_by_talent(talent_id: str):
    """Get Creative DNA for a specific talent (dedicated route)."""
    try:
        return get_creative_dna_by_talent(talent_id).data
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Creative DNA not found for talent: {e}")


@router.get("/feedback/talent/{talent_id}", tags=["v1-feedback"])
def v1_feedback_by_talent(talent_id: str, limit: int = 20):
    """Get all feedback for a specific talent."""
    return get_feedback(talent_id=talent_id, limit=limit).data


# ── Continuity Notes ──────────────────────────────────────────────────────────

CONTINUITY_CATEGORIES = [
    "identity", "wardrobe", "hair", "makeup", "props",
    "locations", "relationships", "story", "general",
]


@router.get("/continuity", tags=["v1-continuity"])
def v1_list_continuity(talent_id: Optional[str] = None, project_id: Optional[str] = None):
    """List continuity notes for a talent or project."""
    return get_continuity_notes(talent_id=talent_id, project_id=project_id).data


@router.post("/continuity", tags=["v1-continuity"], status_code=201)
def v1_create_continuity(data: dict):
    """Create a continuity note.

    Required: title, content
    Optional: talent_id, project_id, category, priority
    """
    if not data.get("title") or not data.get("content"):
        raise HTTPException(status_code=400, detail="'title' and 'content' required")
    category = data.get("category", "general")
    if category not in CONTINUITY_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Valid: {CONTINUITY_CATEGORIES}")
    try:
        result = create_continuity_note(data)
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/continuity/{note_id}", tags=["v1-continuity"])
def v1_update_continuity(note_id: str, data: dict):
    """Update a continuity note."""
    try:
        result = update_continuity_note(note_id, data)
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/continuity/{note_id}", tags=["v1-continuity"])
def v1_delete_continuity(note_id: str):
    """Delete a continuity note."""
    try:
        delete_continuity_note(note_id)
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Creative Rules ────────────────────────────────────────────────────────────

@router.get("/rules", tags=["v1-rules"])
def v1_list_rules(talent_id: Optional[str] = None, rule_type: Optional[str] = None):
    """List creative rules (include/avoid). Filtered by talent and/or type."""
    return get_creative_rules(talent_id=talent_id, rule_type=rule_type).data


@router.post("/rules", tags=["v1-rules"], status_code=201)
def v1_create_rule(data: dict):
    """Create a creative rule.

    Required: rule, rule_type (include/avoid)
    Optional: talent_id, project_id, category, reason, confidence, source
    """
    if not data.get("rule"):
        raise HTTPException(status_code=400, detail="'rule' is required")
    if data.get("rule_type") not in ("include", "avoid"):
        raise HTTPException(status_code=400, detail="'rule_type' must be 'include' or 'avoid'")
    try:
        result = create_creative_rule(data)
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rules/{rule_id}", tags=["v1-rules"])
def v1_delete_rule(rule_id: str):
    """Delete a creative rule."""
    try:
        delete_creative_rule(rule_id)
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Style Preferences ─────────────────────────────────────────────────────────

@router.get("/preferences", tags=["v1-preferences"])
def v1_list_preferences(talent_id: Optional[str] = None):
    """List learned style preferences."""
    return get_style_preferences(talent_id=talent_id).data


@router.post("/preferences", tags=["v1-preferences"], status_code=201)
def v1_save_preference(data: dict):
    """Save or update a style preference (upserts by talent+category+key)."""
    required = ["talent_id", "category", "preference_key", "preference_value"]
    for field in required:
        if not data.get(field):
            raise HTTPException(status_code=400, detail=f"'{field}' is required")
    try:
        result = upsert_style_preference(data)
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Prompt History ────────────────────────────────────────────────────────────

@router.get("/prompt-history", tags=["v1-prompt-history"])
def v1_get_prompt_history(talent_id: Optional[str] = None, limit: int = 20):
    """Get prompt history for learning analysis."""
    return get_prompt_history(talent_id=talent_id, limit=limit).data


# =============================================================================
# Story Engine (Phase E)
# =============================================================================

from backend.database import (
    get_universes, get_universe, create_universe, update_universe, delete_universe,
    get_characters, get_character, create_character, update_character,
    get_episodes, get_episode, create_episode, update_episode,
    get_scenes, create_scene, update_scene,
    get_shots, create_shot, create_shots_bulk, update_shot,
    get_story_memory, create_story_memory,
)
from backend.story_engine.scene_builder import plan_shots, estimate_scene_duration
from backend.story_engine.continuity_checker import check_continuity


# ── Universes ─────────────────────────────────────────────────────────────────

@router.get("/universes", tags=["v1-story"])
def v1_list_universes(project_id: Optional[str] = None):
    return get_universes(project_id=project_id).data

@router.get("/universes/{universe_id}", tags=["v1-story"])
def v1_get_universe(universe_id: str):
    try:
        return get_universe(universe_id).data
    except Exception:
        raise HTTPException(status_code=404, detail="Universe not found")

@router.post("/universes", tags=["v1-story"], status_code=201)
def v1_create_universe(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    result = create_universe(data)
    return result.data[0] if result.data else data

@router.put("/universes/{universe_id}", tags=["v1-story"])
def v1_update_universe(universe_id: str, data: dict):
    result = update_universe(universe_id, data)
    return result.data[0] if result.data else data

@router.delete("/universes/{universe_id}", tags=["v1-story"])
def v1_delete_universe(universe_id: str):
    delete_universe(universe_id)
    return {"deleted": True}


# ── Characters ────────────────────────────────────────────────────────────────

@router.get("/universes/{universe_id}/characters", tags=["v1-story"])
def v1_list_characters(universe_id: str):
    return get_characters(universe_id).data

@router.post("/characters", tags=["v1-story"], status_code=201)
def v1_create_character(data: dict):
    if not data.get("name") or not data.get("universe_id"):
        raise HTTPException(status_code=400, detail="'name' and 'universe_id' required")
    result = create_character(data)
    return result.data[0] if result.data else data

@router.get("/characters/{char_id}", tags=["v1-story"])
def v1_get_character(char_id: str):
    try:
        return get_character(char_id).data
    except Exception:
        raise HTTPException(status_code=404, detail="Character not found")

@router.put("/characters/{char_id}", tags=["v1-story"])
def v1_update_character(char_id: str, data: dict):
    result = update_character(char_id, data)
    return result.data[0] if result.data else data


# ── Episodes ──────────────────────────────────────────────────────────────────

@router.get("/universes/{universe_id}/episodes", tags=["v1-story"])
def v1_list_episodes(universe_id: str):
    return get_episodes(universe_id).data

@router.post("/episodes", tags=["v1-story"], status_code=201)
def v1_create_episode(data: dict):
    if not data.get("title") or not data.get("universe_id"):
        raise HTTPException(status_code=400, detail="'title' and 'universe_id' required")
    result = create_episode(data)
    return result.data[0] if result.data else data

@router.get("/episodes/{episode_id}", tags=["v1-story"])
def v1_get_episode(episode_id: str):
    try:
        return get_episode(episode_id).data
    except Exception:
        raise HTTPException(status_code=404, detail="Episode not found")

@router.put("/episodes/{episode_id}", tags=["v1-story"])
def v1_update_episode(episode_id: str, data: dict):
    result = update_episode(episode_id, data)
    return result.data[0] if result.data else data


# ── Scenes ────────────────────────────────────────────────────────────────────

@router.get("/episodes/{episode_id}/scenes", tags=["v1-story"])
def v1_list_scenes(episode_id: str):
    return get_scenes(episode_id).data

@router.post("/scenes", tags=["v1-story"], status_code=201)
def v1_create_scene(data: dict):
    if not data.get("episode_id"):
        raise HTTPException(status_code=400, detail="'episode_id' required")
    result = create_scene(data)
    return result.data[0] if result.data else data

@router.put("/scenes/{scene_id}", tags=["v1-story"])
def v1_update_scene(scene_id: str, data: dict):
    result = update_scene(scene_id, data)
    return result.data[0] if result.data else data


# ── Shots ─────────────────────────────────────────────────────────────────────

@router.get("/scenes/{scene_id}/shots", tags=["v1-story"])
def v1_list_shots(scene_id: str):
    return get_shots(scene_id).data

@router.post("/scenes/{scene_id}/plan-shots", tags=["v1-story"], status_code=201)
def v1_plan_shots(scene_id: str):
    """Auto-plan shots for a scene using the Scene Builder.

    Reads the scene, generates a shot plan based on characters/mood/purpose,
    and saves the shots to the database.
    """
    try:
        from backend.database import supabase
        scene = supabase.table("scenes").select("*").eq("id", scene_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Scene not found")

    shots = plan_shots(scene)

    # Add scene_id to each shot
    for shot in shots:
        shot["scene_id"] = scene_id

    result = create_shots_bulk(shots)
    duration = estimate_scene_duration(shots)

    return {
        "scene_id": scene_id,
        "shots_created": len(shots),
        "estimated_duration_seconds": duration,
        "shots": result.data if result.data else shots,
    }

@router.post("/shots/{shot_id}/generate", tags=["v1-story"])
def v1_generate_shot(shot_id: str):
    """Generate content for a specific shot via the Generation Engine."""
    try:
        from backend.database import supabase
        shot = supabase.table("shots").select("*").eq("id", shot_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Shot not found")

    # Build generation request from shot description
    gen_data = {
        "prompt": shot.get("description", ""),
        "type": "video_generation" if shot.get("duration_seconds", 0) > 2 else "image_generation",
        "steps": 3,  # Fast for simulation
    }
    gen_data.update(shot.get("generation_params", {}))

    # Use the generation engine
    result = v1_run_generation(gen_data)

    # Link asset to shot
    if result.get("status") == "completed":
        asset = result.get("asset", {})
        update_shot(shot_id, {
            "status": "completed",
            "asset_id": asset.get("id"),
            "job_id": result.get("job_id"),
        })

    return {"shot_id": shot_id, "generation_result": result}


# ── Continuity Check ──────────────────────────────────────────────────────────

@router.post("/scenes/{scene_id}/check-continuity", tags=["v1-story"])
def v1_check_continuity(scene_id: str):
    """Run continuity checks on a scene's shots.

    Returns warnings about potential continuity issues.
    """
    try:
        from backend.database import supabase
        scene = supabase.table("scenes").select("*").eq("id", scene_id).single().execute().data
        shots_result = get_shots(scene_id)
        shots = shots_result.data or []
    except Exception:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Get story memory if we can find the universe
    memory = []
    try:
        episode = get_episode(scene.get("episode_id", "")).data
        universe_id = episode.get("universe_id")
        if universe_id:
            memory = get_story_memory(universe_id).data or []
    except Exception:
        pass

    warnings = check_continuity(shots, scene, story_memory=memory)

    return {
        "scene_id": scene_id,
        "shots_checked": len(shots),
        "warnings": [
            {"severity": w.severity, "category": w.category, "message": w.message,
             "shot_number": w.shot_number, "suggestion": w.suggestion}
            for w in warnings
        ],
        "passed": not any(w.severity == "error" for w in warnings),
    }


# ── Story Memory ──────────────────────────────────────────────────────────────

@router.get("/universes/{universe_id}/memory", tags=["v1-story"])
def v1_list_memory(universe_id: str, character_id: Optional[str] = None):
    return get_story_memory(universe_id, character_id=character_id).data

@router.post("/memory", tags=["v1-story"], status_code=201)
def v1_create_memory(data: dict):
    """Record a story event in universe memory.

    Required: universe_id, event
    Optional: character_id, episode_id, scene_id, category
    Categories: event, relationship, possession, location, injury, death
    """
    if not data.get("universe_id") or not data.get("event"):
        raise HTTPException(status_code=400, detail="'universe_id' and 'event' required")
    result = create_story_memory(data)
    return result.data[0] if result.data else data


# =============================================================================
# Production Studio (Phase F)
# =============================================================================

from backend.production.pipeline_engine import (
    build_production_graph, estimate_production_time, get_pipeline_template,
    build_timeline_from_shots, PIPELINE_TEMPLATES,
)
from backend.production.voice_studio import get_voice_library, get_voice, add_voice
from backend.production.music_studio import get_music_library, get_music_by_mood, recommend_music
from backend.production.models import ProductionType, PipelineType, CameraMove, ShotSize, EditOp


@router.get("/production/types", tags=["v1-production"])
def v1_production_types():
    """List all supported production types."""
    return [t.value for t in ProductionType]


@router.get("/production/pipelines", tags=["v1-production"])
def v1_pipeline_types():
    """List all media pipeline types."""
    return [p.value for p in PipelineType]


@router.get("/production/templates", tags=["v1-production"])
def v1_pipeline_templates():
    """List available pipeline templates with step counts."""
    return {
        name: {"steps": len(steps), "nodes": [s["name"] for s in steps]}
        for name, steps in PIPELINE_TEMPLATES.items()
    }


@router.post("/production/plan", tags=["v1-production"], status_code=201)
def v1_plan_production(data: dict):
    """Build a production graph for a given production type.

    Required: type (e.g. 'reel', 'tiktok', 'commercial')
    Optional: parameters (prompt, model, etc.)

    Returns the production graph with estimated time and cost.
    """
    prod_type = data.get("type")
    if not prod_type:
        raise HTTPException(status_code=400, detail="'type' required")

    graph = build_production_graph(prod_type, parameters=data.get("parameters", {}))
    estimates = estimate_production_time(graph)

    return {
        "production_type": prod_type,
        "graph": graph,
        **estimates,
    }


@router.post("/production/timeline", tags=["v1-production"])
def v1_build_timeline(data: dict):
    """Build a timeline from a list of shots.

    Input: shots[] (each with id, duration_seconds, transition, asset_id)
    Returns: timeline structure with tracks.
    """
    shots = data.get("shots", [])
    if not shots:
        raise HTTPException(status_code=400, detail="'shots' array required")
    fps = int(data.get("fps", 24))
    timeline = build_timeline_from_shots(shots, fps=fps)
    return timeline


# ── Camera System ─────────────────────────────────────────────────────────────

@router.get("/production/camera/moves", tags=["v1-production"])
def v1_camera_moves():
    """List all supported camera movements."""
    return [m.value for m in CameraMove]


@router.get("/production/camera/sizes", tags=["v1-production"])
def v1_shot_sizes():
    """List all supported shot sizes."""
    return [s.value for s in ShotSize]


@router.get("/production/editing/operations", tags=["v1-production"])
def v1_edit_operations():
    """List all supported editing operations."""
    return [e.value for e in EditOp]


# ── Voice Studio ──────────────────────────────────────────────────────────────

@router.get("/production/voices", tags=["v1-production"])
def v1_list_voices():
    """List all voice profiles in the library."""
    return get_voice_library()


@router.post("/production/voices", tags=["v1-production"], status_code=201)
def v1_add_voice(data: dict):
    """Add a new voice profile to the library."""
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    return add_voice(data)


# ── Music Studio ──────────────────────────────────────────────────────────────

@router.get("/production/music", tags=["v1-production"])
def v1_list_music():
    """List all music tracks in the library."""
    return get_music_library()


@router.get("/production/music/recommend", tags=["v1-production"])
def v1_recommend_music(content_type: str = "reel", mood: str = ""):
    """Get a music recommendation for a content type."""
    rec = recommend_music(content_type, mood)
    if not rec:
        return {"recommendation": None, "message": "No matching tracks found"}
    return {"recommendation": rec}
