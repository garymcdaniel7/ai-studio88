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
