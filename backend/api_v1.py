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
