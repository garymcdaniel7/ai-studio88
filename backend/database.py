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
        .execute()
    )


def fail_job(job_id: str, error: str):
    """Mark a job as failed with an error message."""
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
        .execute()
    )


# =============================================================================
# Workflows
# =============================================================================


def get_workflows(status: str | None = None):
    """Get all workflows, optionally filtered by status."""
    query = supabase.table("workflows").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    return query.execute()


def get_workflow_by_id(workflow_id: str):
    """Get a single workflow by ID."""
    return supabase.table("workflows").select("*").eq("id", workflow_id).single().execute()


def create_workflow(data: dict):
    """Insert a new workflow."""
    return supabase.table("workflows").insert(data).execute()


def update_workflow(workflow_id: str, data: dict):
    """Update a workflow record."""
    data["updated_at"] = "now()"
    return supabase.table("workflows").update(data).eq("id", workflow_id).execute()


def delete_workflow(workflow_id: str):
    """Delete a workflow by ID."""
    return supabase.table("workflows").delete().eq("id", workflow_id).execute()


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
# Creative DNA
# =============================================================================


def get_creative_dna_list():
    """Get all creative DNA records."""
    return supabase.table("creative_dna").select("*").order("created_at", desc=True).execute()


def get_creative_dna_by_talent(talent_id: str):
    """Get creative DNA for a specific talent."""
    return supabase.table("creative_dna").select("*").eq("talent_id", talent_id).single().execute()


def create_creative_dna(data: dict):
    """Create a creative DNA record."""
    return supabase.table("creative_dna").insert(data).execute()


def update_creative_dna(dna_id: str, data: dict):
    """Update a creative DNA record."""
    data["updated_at"] = "now()"
    return supabase.table("creative_dna").update(data).eq("id", dna_id).execute()


# =============================================================================
# Generation Feedback
# =============================================================================


def get_feedback(talent_id: str | None = None, limit: int = 50):
    """Get feedback, optionally filtered by talent."""
    query = (
        supabase.table("generation_feedback")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if talent_id:
        query = query.eq("talent_id", talent_id)
    return query.execute()


def create_feedback(data: dict):
    """Store generation feedback."""
    return supabase.table("generation_feedback").insert(data).execute()


def get_recent_problems(talent_id: str, limit: int = 20) -> list[str]:
    """Get the most common recent problems for a talent.

    Returns a flat list of problem tags from recent feedback.
    """
    result = (
        supabase.table("generation_feedback")
        .select("problems")
        .eq("talent_id", talent_id)
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


def get_average_rating(talent_id: str) -> float | None:
    """Get average rating for a talent's recent outputs."""
    result = (
        supabase.table("generation_feedback")
        .select("rating")
        .eq("talent_id", talent_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    ratings = [r["rating"] for r in result.data if r.get("rating")]
    if ratings:
        return sum(ratings) / len(ratings)
    return None


# =============================================================================
# Continuity Notes
# =============================================================================


def get_continuity_notes(talent_id: str | None = None, project_id: str | None = None):
    """Get continuity notes filtered by talent and/or project."""
    query = (
        supabase.table("continuity_notes")
        .select("*")
        .eq("active", True)
        .order("priority", desc=True)
    )
    if talent_id:
        query = query.eq("talent_id", talent_id)
    if project_id:
        query = query.eq("project_id", project_id)
    return query.execute()


def create_continuity_note(data: dict):
    """Create a continuity note."""
    return supabase.table("continuity_notes").insert(data).execute()


def update_continuity_note(note_id: str, data: dict):
    """Update a continuity note."""
    data["updated_at"] = "now()"
    return supabase.table("continuity_notes").update(data).eq("id", note_id).execute()


def delete_continuity_note(note_id: str):
    """Delete a continuity note."""
    return supabase.table("continuity_notes").delete().eq("id", note_id).execute()


# =============================================================================
# Creative Rules
# =============================================================================


def get_creative_rules(talent_id: str | None = None, rule_type: str | None = None):
    """Get active creative rules filtered by talent and/or type."""
    query = (
        supabase.table("creative_rules")
        .select("*")
        .eq("active", True)
        .order("created_at", desc=True)
    )
    if talent_id:
        query = query.eq("talent_id", talent_id)
    if rule_type:
        query = query.eq("rule_type", rule_type)
    return query.execute()


def create_creative_rule(data: dict):
    """Create a creative rule."""
    return supabase.table("creative_rules").insert(data).execute()


def delete_creative_rule(rule_id: str):
    """Delete a creative rule."""
    return supabase.table("creative_rules").delete().eq("id", rule_id).execute()


# =============================================================================
# Style Preferences (API layer)
# =============================================================================


def get_style_preferences(talent_id: str | None = None):
    """Get style preferences, optionally filtered by talent."""
    query = supabase.table("style_preferences").select("*").order("confidence", desc=True)
    if talent_id:
        query = query.eq("talent_id", talent_id)
    return query.execute()


def upsert_style_preference(data: dict):
    """Create or update a style preference."""
    return (
        supabase.table("style_preferences")
        .upsert(data, on_conflict="talent_id,category,preference_key")
        .execute()
    )


# =============================================================================
# Prompt History (auto-capture)
# =============================================================================


def record_prompt_history(data: dict):
    """Record a prompt+outcome for learning."""
    return supabase.table("prompt_history").insert(data).execute()


def get_prompt_history(talent_id: str | None = None, limit: int = 20):
    """Get prompt history, optionally filtered by talent."""
    query = supabase.table("prompt_history").select("*").order("created_at", desc=True).limit(limit)
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


def get_models(model_type: str | None = None, family: str | None = None, status: str | None = None):
    query = supabase.table("models").select("*").order("name")
    if model_type:
        query = query.eq("type", model_type)
    if family:
        query = query.eq("family", family)
    if status:
        query = query.eq("status", status)
    return query.execute()


def get_model_by_id(model_id: str):
    return supabase.table("models").select("*").eq("id", model_id).single().execute()


def create_model_record(data: dict):
    return supabase.table("models").insert(data).execute()


def update_model_record(model_id: str, data: dict):
    data["updated_at"] = "now()"
    return supabase.table("models").update(data).eq("id", model_id).execute()


def delete_model_record(model_id: str):
    return supabase.table("models").delete().eq("id", model_id).execute()


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
# Workers (persistent)
# =============================================================================


def get_workers_db(status: str | None = None, provider: str | None = None):
    query = supabase.table("workers").select("*").order("name")
    if status:
        query = query.eq("status", status)
    if provider:
        query = query.eq("provider", provider)
    return query.execute()


def get_worker_db(worker_id: str):
    return supabase.table("workers").select("*").eq("id", worker_id).single().execute()


def create_worker_db(data: dict):
    return supabase.table("workers").insert(data).execute()


def update_worker_db(worker_id: str, data: dict):
    data["updated_at"] = "now()"
    return supabase.table("workers").update(data).eq("id", worker_id).execute()


def delete_worker_db(worker_id: str):
    return supabase.table("workers").delete().eq("id", worker_id).execute()


def heartbeat_worker_db(worker_id: str, data: dict):
    """Update worker heartbeat and status."""
    update = {
        "last_heartbeat_at": "now()",
        "status": data.get("status", "online"),
        "updated_at": "now()",
    }
    if "available_vram_gb" in data:
        update["available_vram_gb"] = data["available_vram_gb"]
    if "current_job_id" in data:
        update["current_job_id"] = data["current_job_id"]
    return supabase.table("workers").update(update).eq("id", worker_id).execute()


def get_available_workers_db():
    """Get workers that are online and not busy."""
    return (
        supabase.table("workers")
        .select("*")
        .in_("status", ["online"])
        .order("available_vram_gb", desc=True)
        .execute()
    )
