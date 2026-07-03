import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_projects():
    return supabase.table("projects").select("*").execute()

def get_talent():
    return supabase.table("talent").select("*").execute()

def create_talent(data):
    return supabase.table("talent").insert(data).execute()


# =============================================================================
# Assets
# =============================================================================

def get_assets():
    """Get all assets, ordered by most recent first."""
    return supabase.table("assets").select("*").order("created_at", desc=True).execute()


def get_asset_by_id(asset_id: str):
    """Get a single asset by ID."""
    return supabase.table("assets").select("*").eq("id", asset_id).single().execute()


def create_asset(data: dict):
    """Insert a new asset record."""
    return supabase.table("assets").insert(data).execute()


def delete_asset(asset_id: str):
    """Delete an asset record by ID. Returns the deleted row."""
    return supabase.table("assets").delete().eq("id", asset_id).execute()


# =============================================================================
# Jobs
# =============================================================================

def get_jobs(status: str | None = None, job_type: str | None = None, limit: int = 50):
    """Get jobs, optionally filtered by status and/or type."""
    query = supabase.table("jobs").select("*").order("created_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    if job_type:
        query = query.eq("type", job_type)
    return query.execute()


def get_job_by_id(job_id: str):
    """Get a single job by ID."""
    return supabase.table("jobs").select("*").eq("id", job_id).single().execute()


def create_job(data: dict):
    """Insert a new job record."""
    return supabase.table("jobs").insert(data).execute()


def update_job(job_id: str, data: dict):
    """Update a job record. Sets updated_at automatically."""
    data["updated_at"] = "now()"
    return supabase.table("jobs").update(data).eq("id", job_id).execute()


def delete_job(job_id: str):
    """Delete a job record by ID."""
    return supabase.table("jobs").delete().eq("id", job_id).execute()


def claim_next_job(worker_name: str, worker_id: str) -> dict | None:
    """Atomically claim the next queued job (highest priority, oldest first).

    Uses update with filter to act as a lightweight lock.
    Returns the claimed job or None if no jobs are available.
    """
    # Find the next queued job
    result = (
        supabase.table("jobs")
        .select("*")
        .eq("status", "queued")
        .order("priority", desc=True)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    job = result.data[0]
    job_id = job["id"]

    # Attempt to claim it (only if still queued — basic optimistic lock)
    claim_result = (
        supabase.table("jobs")
        .update({
            "status": "running",
            "worker_name": worker_name,
            "worker_id": worker_id,
            "started_at": "now()",
            "updated_at": "now()",
            "attempts": job.get("attempts", 0) + 1,
        })
        .eq("id", job_id)
        .eq("status", "queued")  # Only claim if still queued
        .execute()
    )

    if claim_result.data:
        return claim_result.data[0]
    return None


def complete_job(job_id: str, output: dict):
    """Mark a job as completed with output data."""
    return (
        supabase.table("jobs")
        .update({
            "status": "completed",
            "output": output,
            "progress": 100,
            "completed_at": "now()",
            "updated_at": "now()",
        })
        .eq("id", job_id)
        .execute()
    )


def fail_job(job_id: str, error: str):
    """Mark a job as failed with an error message."""
    return (
        supabase.table("jobs")
        .update({
            "status": "failed",
            "error": error,
            "updated_at": "now()",
        })
        .eq("id", job_id)
        .execute()
    )
