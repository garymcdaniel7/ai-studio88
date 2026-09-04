"""Supabase database client — guarded initialization.

Creates the Supabase client lazily to avoid crashing at import time
when environment variables are not yet available (e.g., during testing
or when this module is imported by other modules that don't need DB).

The client is created on first access via get_supabase_client().
Direct module-level usage via the `supabase` variable is preserved
for backward compatibility but will raise a clear error if misconfigured.
"""

import os
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from backend.tenant_context import validate_org_id

if TYPE_CHECKING:
    from supabase import Client

load_dotenv()

_supabase_client: "Client | None" = None


class SupabaseNotConfiguredError(RuntimeError):
    """Raised when Supabase is accessed but not configured."""

    def __init__(self) -> None:
        super().__init__(
            "Supabase is not configured. "
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env"
        )


def get_supabase_client() -> "Client":
    """Get or create the Supabase client.

    Raises SupabaseNotConfiguredError if env vars are missing.
    """
    global _supabase_client

    if _supabase_client is not None:
        return _supabase_client

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    if not url or not key:
        raise SupabaseNotConfiguredError()

    # Reject obvious placeholders
    if url in ("https://your-project.supabase.co",) or key.startswith("your-"):
        raise SupabaseNotConfiguredError()

    from supabase import create_client

    _supabase_client = create_client(url, key)
    return _supabase_client


def is_supabase_configured() -> bool:
    """Check if Supabase can be initialized without raising."""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    return bool(url and key and not url.startswith("https://your-"))


# Backward-compatible module-level access (lazy)
class _LazySupabaseProxy:
    """Proxy that creates the client on first attribute access."""

    def __getattr__(self, name: str):
        client = get_supabase_client()
        return getattr(client, name)


supabase = _LazySupabaseProxy()  # type: ignore[assignment]


def get_projects(org_id: str):
    """Get projects scoped to a tenant.

    Args:
        org_id: Required tenant org_id. Must come from TenantContext.
    """
    validate_org_id(org_id)
    return supabase.table("projects").select("*").eq("org_id", org_id).execute()


def get_talent(org_id: str):
    """Get talent scoped to a tenant.

    Args:
        org_id: Required tenant org_id. Must come from TenantContext.
    """
    validate_org_id(org_id)
    return supabase.table("talent").select("*").eq("org_id", org_id).execute()


def get_talent_by_id(talent_id: str, org_id: str):
    """Get a single talent by ID, scoped to tenant.

    Returns None-data if not found or belongs to another tenant.
    """
    validate_org_id(org_id)
    return (
        supabase.table("talent")
        .select("*")
        .eq("id", talent_id)
        .eq("org_id", org_id)
        .execute()
    )


def create_talent(data: dict, org_id: str):
    """Create a talent record. org_id is injected automatically."""
    validate_org_id(org_id)
    data["org_id"] = org_id
    return supabase.table("talent").insert(data).execute()


# =============================================================================
# Assets
# =============================================================================


def get_assets(org_id: str):
    """Get all assets scoped to a tenant, ordered by most recent first.

    Args:
        org_id: Required tenant org_id.
    """
    validate_org_id(org_id)
    from backend.compliance.quarantine import filter_visible_assets

    result = (
        supabase.table("assets")
        .select("*")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .execute()
    )
    result.data = filter_visible_assets(result.data or [], org_id=org_id)
    return result


def get_asset_by_id(asset_id: str, org_id: str):
    """Get a single asset by ID, scoped to tenant.

    Returns same error for both not-found and cross-tenant (no existence leak).
    """
    validate_org_id(org_id)
    from backend.compliance.quarantine import filter_visible_assets

    result = (
        supabase.table("assets")
        .select("*")
        .eq("id", asset_id)
        .eq("org_id", org_id)
        .execute()
    )
    result.data = filter_visible_assets(result.data or [], org_id=org_id)
    return result


def create_asset(data: dict, org_id: str):
    """Insert a new asset record. org_id is injected."""
    validate_org_id(org_id)
    data["org_id"] = org_id
    return supabase.table("assets").insert(data).execute()


def delete_asset(asset_id: str, org_id: str):
    """Delete an asset by ID, scoped to tenant. No-op if not found in tenant."""
    validate_org_id(org_id)
    return (
        supabase.table("assets")
        .delete()
        .eq("id", asset_id)
        .eq("org_id", org_id)
        .execute()
    )


# =============================================================================
# Jobs
# =============================================================================


def get_jobs(
    org_id: str,
    status: str | None = None,
    job_type: str | None = None,
    limit: int = 50,
):
    """Get jobs scoped to a tenant, optionally filtered by status/type."""
    validate_org_id(org_id)
    query = (
        supabase.table("jobs")
        .select("*")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        query = query.eq("status", status)
    if job_type:
        query = query.eq("type", job_type)
    return query.execute()


def get_job_by_id(job_id: str, org_id: str):
    """Get a single job by ID, scoped to tenant."""
    validate_org_id(org_id)
    return (
        supabase.table("jobs")
        .select("*")
        .eq("id", job_id)
        .eq("org_id", org_id)
        .execute()
    )


def create_job(data: dict, org_id: str):
    """Insert a new job record. org_id injected."""
    validate_org_id(org_id)
    data["org_id"] = org_id
    return supabase.table("jobs").insert(data).execute()


def update_job(job_id: str, data: dict, org_id: str):
    """Update a job record, scoped to tenant."""
    validate_org_id(org_id)
    data.pop("org_id", None)  # org_id is immutable
    data["updated_at"] = "now()"
    return (
        supabase.table("jobs")
        .update(data)
        .eq("id", job_id)
        .eq("org_id", org_id)
        .execute()
    )


def delete_job(job_id: str, org_id: str):
    """Delete a job record, scoped to tenant."""
    validate_org_id(org_id)
    return (
        supabase.table("jobs")
        .delete()
        .eq("id", job_id)
        .eq("org_id", org_id)
        .execute()
    )


def claim_next_job(worker_name: str, worker_id: str, org_id: str) -> dict | None:
    """Atomically claim the next queued job, scoped to tenant.

    Uses update with filter to act as a lightweight lock.
    Returns the claimed job or None if no jobs are available.
    """
    validate_org_id(org_id)
    # Find the next queued job for this tenant
    result = (
        supabase.table("jobs")
        .select("*")
        .eq("status", "queued")
        .eq("org_id", org_id)
        .order("priority", desc=True)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    job = result.data[0]
    job_id = job["id"]

    # Attempt to claim (only if still queued — optimistic lock)
    claim_result = (
        supabase.table("jobs")
        .update(
            {
                "status": "running",
                "worker_name": worker_name,
                "worker_id": worker_id,
                "started_at": "now()",
                "updated_at": "now()",
                "attempts": job.get("attempts", 0) + 1,
            }
        )
        .eq("id", job_id)
        .eq("status", "queued")
        .eq("org_id", org_id)
        .execute()
    )

    if claim_result.data:
        return claim_result.data[0]
    return None


def complete_job(job_id: str, output: dict, org_id: str):
    """Mark a job as completed, scoped to tenant."""
    validate_org_id(org_id)
    return (
        supabase.table("jobs")
        .update(
            {
                "status": "completed",
                "output": output,
                "progress": 100,
                "completed_at": "now()",
                "updated_at": "now()",
            }
        )
        .eq("id", job_id)
        .eq("org_id", org_id)
        .execute()
    )


def fail_job(job_id: str, error: str, org_id: str):
    """Mark a job as failed, scoped to tenant."""
    validate_org_id(org_id)
    return (
        supabase.table("jobs")
        .update(
            {
                "status": "failed",
                "error": error,
                "updated_at": "now()",
            }
        )
        .eq("id", job_id)
        .eq("org_id", org_id)
        .execute()
    )


# =============================================================================
# Workflows
# =============================================================================


def get_workflows(org_id: str, status: str | None = None):
    """Get all workflows scoped to tenant, optionally filtered by status."""
    validate_org_id(org_id)
    query = (
        supabase.table("workflows")
        .select("*")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
    )
    if status:
        query = query.eq("status", status)
    return query.execute()


def get_workflow_by_id(workflow_id: str, org_id: str):
    """Get a single workflow by ID, scoped to tenant."""
    validate_org_id(org_id)
    return (
        supabase.table("workflows")
        .select("*")
        .eq("id", workflow_id)
        .eq("org_id", org_id)
        .execute()
    )


def create_workflow(data: dict, org_id: str):
    """Insert a new workflow. org_id injected."""
    validate_org_id(org_id)
    data["org_id"] = org_id
    return supabase.table("workflows").insert(data).execute()


def update_workflow(workflow_id: str, data: dict, org_id: str):
    """Update a workflow record, scoped to tenant."""
    validate_org_id(org_id)
    data.pop("org_id", None)
    data["updated_at"] = "now()"
    return (
        supabase.table("workflows")
        .update(data)
        .eq("id", workflow_id)
        .eq("org_id", org_id)
        .execute()
    )


def delete_workflow(workflow_id: str, org_id: str):
    """Delete a workflow, scoped to tenant."""
    validate_org_id(org_id)
    return (
        supabase.table("workflows")
        .delete()
        .eq("id", workflow_id)
        .eq("org_id", org_id)
        .execute()
    )


# =============================================================================
# Workflow Runs
# =============================================================================


def create_workflow_run(data: dict):
    """Create a workflow run record."""
    return supabase.table("workflow_runs").insert(data).execute()


def get_workflow_run(run_id: str):
    """Get a workflow run by ID."""
    return supabase.table("workflow_runs").select("*").eq("id", run_id).single().execute()


def update_workflow_run(run_id: str, data: dict):
    """Update a workflow run."""
    data["updated_at"] = "now()"
    return supabase.table("workflow_runs").update(data).eq("id", run_id).execute()


# =============================================================================
# Creative DNA (tenant-scoped via org_id, inherited from talent)
# =============================================================================


def get_creative_dna_list(org_id: str):
    """Get all creative DNA records for a tenant."""
    validate_org_id(org_id)
    return supabase.table("creative_dna").select("*").eq("org_id", org_id).order("created_at", desc=True).execute()


def get_creative_dna_by_talent(talent_id: str, org_id: str):
    """Get creative DNA for a specific talent, scoped to tenant."""
    validate_org_id(org_id)
    return supabase.table("creative_dna").select("*").eq("talent_id", talent_id).eq("org_id", org_id).execute()


def create_creative_dna(data: dict, org_id: str):
    """Create a creative DNA record. org_id injected."""
    validate_org_id(org_id)
    data["org_id"] = org_id
    return supabase.table("creative_dna").insert(data).execute()


def update_creative_dna(dna_id: str, data: dict, org_id: str):
    """Update a creative DNA record, scoped to tenant."""
    validate_org_id(org_id)
    data.pop("org_id", None)
    data["updated_at"] = "now()"
    return supabase.table("creative_dna").update(data).eq("id", dna_id).eq("org_id", org_id).execute()


# =============================================================================
# Generation Feedback (tenant-scoped via org_id)
# =============================================================================


def get_feedback(org_id: str, talent_id: str | None = None, limit: int = 50):
    """Get feedback scoped to a tenant, optionally filtered by talent."""
    validate_org_id(org_id)
    query = (
        supabase.table("generation_feedback")
        .select("*")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if talent_id:
        query = query.eq("talent_id", talent_id)
    return query.execute()


def create_feedback(data: dict, org_id: str):
    """Store generation feedback. org_id injected."""
    validate_org_id(org_id)
    data["org_id"] = org_id
    return supabase.table("generation_feedback").insert(data).execute()


def get_recent_problems(talent_id: str, org_id: str, limit: int = 20) -> list[str]:
    """Get the most common recent problems for a talent, scoped to tenant."""
    validate_org_id(org_id)
    result = (
        supabase.table("generation_feedback")
        .select("problems")
        .eq("talent_id", talent_id)
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    all_problems = []
    for row in result.data:
        problems = row.get("problems")
        if problems:
            all_problems.extend(problems)
    return all_problems


def get_average_rating(talent_id: str, org_id: str) -> float | None:
    """Get average rating for a talent's recent outputs, scoped to tenant."""
    validate_org_id(org_id)
    result = (
        supabase.table("generation_feedback")
        .select("rating")
        .eq("talent_id", talent_id)
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    ratings = [r["rating"] for r in result.data if r.get("rating")]
    if ratings:
        return sum(ratings) / len(ratings)
    return None


# =============================================================================
# Continuity Notes (tenant-scoped, direct org_id)
# =============================================================================


def get_continuity_notes(org_id: str, talent_id: str | None = None, project_id: str | None = None):
    """Get continuity notes scoped to tenant, filtered by talent/project."""
    validate_org_id(org_id)
    query = (
        supabase.table("continuity_notes")
        .select("*")
        .eq("org_id", org_id)
        .eq("active", True)
        .order("priority", desc=True)
    )
    if talent_id:
        query = query.eq("talent_id", talent_id)
    if project_id:
        query = query.eq("project_id", project_id)
    return query.execute()


def create_continuity_note(data: dict, org_id: str):
    """Create a continuity note. org_id injected."""
    validate_org_id(org_id)
    data["org_id"] = org_id
    return supabase.table("continuity_notes").insert(data).execute()


def update_continuity_note(note_id: str, data: dict, org_id: str):
    """Update a continuity note, scoped to tenant."""
    validate_org_id(org_id)
    data.pop("org_id", None)
    data["updated_at"] = "now()"
    return supabase.table("continuity_notes").update(data).eq("id", note_id).eq("org_id", org_id).execute()


def delete_continuity_note(note_id: str, org_id: str):
    """Delete a continuity note, scoped to tenant."""
    validate_org_id(org_id)
    return supabase.table("continuity_notes").delete().eq("id", note_id).eq("org_id", org_id).execute()


# =============================================================================
# Creative Rules (tenant-scoped, direct org_id)
# =============================================================================


def get_creative_rules(org_id: str, talent_id: str | None = None, rule_type: str | None = None):
    """Get active creative rules scoped to tenant."""
    validate_org_id(org_id)
    query = (
        supabase.table("creative_rules")
        .select("*")
        .eq("org_id", org_id)
        .eq("active", True)
        .order("created_at", desc=True)
    )
    if talent_id:
        query = query.eq("talent_id", talent_id)
    if rule_type:
        query = query.eq("rule_type", rule_type)
    return query.execute()


def create_creative_rule(data: dict, org_id: str):
    """Create a creative rule. org_id injected."""
    validate_org_id(org_id)
    data["org_id"] = org_id
    return supabase.table("creative_rules").insert(data).execute()


def delete_creative_rule(rule_id: str, org_id: str):
    """Delete a creative rule, scoped to tenant."""
    validate_org_id(org_id)
    return supabase.table("creative_rules").delete().eq("id", rule_id).eq("org_id", org_id).execute()


# =============================================================================
# Style Preferences (tenant-scoped via org_id)
# =============================================================================


def get_style_preferences(org_id: str, talent_id: str | None = None):
    """Get style preferences scoped to tenant."""
    validate_org_id(org_id)
    query = supabase.table("style_preferences").select("*").eq("org_id", org_id).order("confidence", desc=True)
    if talent_id:
        query = query.eq("talent_id", talent_id)
    return query.execute()


def upsert_style_preference(data: dict, org_id: str):
    """Create or update a style preference. org_id injected."""
    validate_org_id(org_id)
    data["org_id"] = org_id
    return (
        supabase.table("style_preferences")
        .upsert(data, on_conflict="talent_id,category,preference_key")
        .execute()
    )


# =============================================================================
# Prompt History (tenant-scoped via org_id)
# =============================================================================


def record_prompt_history(data: dict, org_id: str):
    """Record a prompt+outcome for learning. org_id injected."""
    validate_org_id(org_id)
    data["org_id"] = org_id
    return supabase.table("prompt_history").insert(data).execute()


def get_prompt_history(org_id: str, talent_id: str | None = None, limit: int = 20):
    """Get prompt history scoped to tenant."""
    validate_org_id(org_id)
    query = supabase.table("prompt_history").select("*").eq("org_id", org_id).order("created_at", desc=True).limit(limit)
    if talent_id:
        query = query.eq("talent_id", talent_id)
    return query.execute()


# =============================================================================
# Story Engine
# =============================================================================


def get_universes(project_id: str | None = None):
    query = supabase.table("universes").select("*").order("created_at", desc=True)
    if project_id:
        query = query.eq("project_id", project_id)
    return query.execute()


def get_universe(universe_id: str):
    return supabase.table("universes").select("*").eq("id", universe_id).single().execute()


def create_universe(data: dict):
    return supabase.table("universes").insert(data).execute()


def update_universe(universe_id: str, data: dict):
    data["updated_at"] = "now()"
    return supabase.table("universes").update(data).eq("id", universe_id).execute()


def delete_universe(universe_id: str):
    return supabase.table("universes").delete().eq("id", universe_id).execute()


# Characters
def get_characters(universe_id: str):
    return (
        supabase.table("characters")
        .select("*")
        .eq("universe_id", universe_id)
        .order("name")
        .execute()
    )


def get_character(char_id: str):
    return supabase.table("characters").select("*").eq("id", char_id).single().execute()


def create_character(data: dict):
    return supabase.table("characters").insert(data).execute()


def update_character(char_id: str, data: dict):
    data["updated_at"] = "now()"
    return supabase.table("characters").update(data).eq("id", char_id).execute()


# Episodes
def get_episodes(universe_id: str):
    return (
        supabase.table("episodes")
        .select("*")
        .eq("universe_id", universe_id)
        .order("episode_number")
        .execute()
    )


def get_episode(episode_id: str):
    return supabase.table("episodes").select("*").eq("id", episode_id).single().execute()


def create_episode(data: dict):
    return supabase.table("episodes").insert(data).execute()


def update_episode(episode_id: str, data: dict):
    data["updated_at"] = "now()"
    return supabase.table("episodes").update(data).eq("id", episode_id).execute()


# Scenes
def get_scenes(episode_id: str):
    return (
        supabase.table("scenes")
        .select("*")
        .eq("episode_id", episode_id)
        .order("scene_number")
        .execute()
    )


def create_scene(data: dict):
    return supabase.table("scenes").insert(data).execute()


def update_scene(scene_id: str, data: dict):
    data["updated_at"] = "now()"
    return supabase.table("scenes").update(data).eq("id", scene_id).execute()


# Shots
def get_shots(scene_id: str):
    return (
        supabase.table("shots").select("*").eq("scene_id", scene_id).order("shot_number").execute()
    )


def create_shot(data: dict):
    return supabase.table("shots").insert(data).execute()


def create_shots_bulk(shots: list[dict]):
    return supabase.table("shots").insert(shots).execute()


def update_shot(shot_id: str, data: dict):
    data["updated_at"] = "now()"
    return supabase.table("shots").update(data).eq("id", shot_id).execute()


# Story Memory
def get_story_memory(universe_id: str, character_id: str | None = None):
    query = (
        supabase.table("story_memory")
        .select("*")
        .eq("universe_id", universe_id)
        .eq("active", True)
        .order("created_at", desc=True)
    )
    if character_id:
        query = query.eq("character_id", character_id)
    return query.execute()


def create_story_memory(data: dict):
    return supabase.table("story_memory").insert(data).execute()


# =============================================================================
# Models
# =============================================================================


def get_models(
    org_id: str,
    model_type: str | None = None,
    family: str | None = None,
    status: str | None = None,
):
    """Get models scoped to tenant."""
    validate_org_id(org_id)
    query = supabase.table("models").select("*").eq("org_id", org_id).order("name")
    if model_type:
        query = query.eq("type", model_type)
    if family:
        query = query.eq("family", family)
    if status:
        query = query.eq("status", status)
    return query.execute()


def get_model_by_id(model_id: str, org_id: str):
    """Get a single model by ID, scoped to tenant."""
    validate_org_id(org_id)
    return (
        supabase.table("models")
        .select("*")
        .eq("id", model_id)
        .eq("org_id", org_id)
        .execute()
    )


def get_lora_catalog(
    base_model: str | None = None,
    lane: str | None = None,
):
    """List the global external LoRA catalog (Civitai/Ko-Fi purchases).

    Unlike the tenant-scoped `models` table, lora_catalog is a shared index
    of purchased/external LoRAs available on the GPU workers.
    """
    query = supabase.table("lora_catalog").select("*").order("name")
    if base_model:
        query = query.eq("base_model", base_model)
    if lane:
        query = query.eq("lane", lane)
    return query.execute()


def create_model_record(data: dict, org_id: str):
    """Create a model record. org_id injected."""
    validate_org_id(org_id)
    data["org_id"] = org_id
    return supabase.table("models").insert(data).execute()


def update_model_record(model_id: str, data: dict, org_id: str):
    """Update a model record, scoped to tenant."""
    validate_org_id(org_id)
    data.pop("org_id", None)
    data["updated_at"] = "now()"
    return (
        supabase.table("models")
        .update(data)
        .eq("id", model_id)
        .eq("org_id", org_id)
        .execute()
    )


def delete_model_record(model_id: str, org_id: str):
    """Delete a model record, scoped to tenant."""
    validate_org_id(org_id)
    return (
        supabase.table("models")
        .delete()
        .eq("id", model_id)
        .eq("org_id", org_id)
        .execute()
    )


# =============================================================================
# Workflow Templates
# =============================================================================


def get_workflow_templates(category: str | None = None, provider: str | None = None):
    query = supabase.table("workflow_templates").select("*").order("name")
    if category:
        query = query.eq("category", category)
    if provider:
        query = query.eq("provider", provider)
    return query.execute()


def get_workflow_template_by_id(template_id: str):
    return supabase.table("workflow_templates").select("*").eq("id", template_id).single().execute()


def create_workflow_template(data: dict):
    return supabase.table("workflow_templates").insert(data).execute()


def update_workflow_template(template_id: str, data: dict):
    data["updated_at"] = "now()"
    return supabase.table("workflow_templates").update(data).eq("id", template_id).execute()


def delete_workflow_template(template_id: str):
    return supabase.table("workflow_templates").delete().eq("id", template_id).execute()


# =============================================================================
# Workers (persistent, tenant-scoped)
# =============================================================================


def get_workers_db(org_id: str, status: str | None = None, provider: str | None = None):
    """Get workers scoped to a tenant.

    Args:
        org_id: Required tenant org_id from TenantContext.
        status: Optional filter by worker status.
        provider: Optional filter by provider type.
    """
    validate_org_id(org_id)
    query = supabase.table("workers").select("*").eq("org_id", org_id).order("name")
    if status:
        query = query.eq("status", status)
    if provider:
        query = query.eq("provider", provider)
    return query.execute()


def get_worker_db(worker_id: str, org_id: str):
    """Get a single worker by ID, scoped to tenant.

    Returns same error for not-found and cross-tenant (no existence leak).
    """
    validate_org_id(org_id)
    return (
        supabase.table("workers")
        .select("*")
        .eq("id", worker_id)
        .eq("org_id", org_id)
        .execute()
    )


def create_worker_db(data: dict, org_id: str):
    """Register a new worker. org_id injected from trusted context."""
    validate_org_id(org_id)
    data["org_id"] = org_id
    return supabase.table("workers").insert(data).execute()


def update_worker_db(worker_id: str, data: dict, org_id: str):
    """Update a worker record, scoped to tenant.

    org_id cannot be changed (immutable ownership).
    """
    validate_org_id(org_id)
    data.pop("org_id", None)  # Prevent ownership reassignment
    data["updated_at"] = "now()"
    return (
        supabase.table("workers")
        .update(data)
        .eq("id", worker_id)
        .eq("org_id", org_id)
        .execute()
    )


def delete_worker_db(worker_id: str, org_id: str):
    """Delete a worker, scoped to tenant."""
    validate_org_id(org_id)
    return (
        supabase.table("workers")
        .delete()
        .eq("id", worker_id)
        .eq("org_id", org_id)
        .execute()
    )


def heartbeat_worker_db(worker_id: str, data: dict, org_id: str):
    """Update worker heartbeat and status, scoped to tenant.

    This is the narrow service-update path used by worker processes
    and the backend orchestrator to report health.
    """
    validate_org_id(org_id)
    update = {
        "last_heartbeat_at": "now()",
        "status": data.get("status", "online"),
        "updated_at": "now()",
    }
    if "available_vram_gb" in data:
        update["available_vram_gb"] = data["available_vram_gb"]
    if "current_job_id" in data:
        update["current_job_id"] = data["current_job_id"]
    return (
        supabase.table("workers")
        .update(update)
        .eq("id", worker_id)
        .eq("org_id", org_id)
        .execute()
    )


def get_available_workers_db(org_id: str):
    """Get workers that are online and not busy, scoped to tenant."""
    validate_org_id(org_id)
    return (
        supabase.table("workers")
        .select("*")
        .eq("org_id", org_id)
        .in_("status", ["online"])
        .order("available_vram_gb", desc=True)
        .execute()
    )
