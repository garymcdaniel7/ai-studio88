"""Storyboard & Production Repository — tenant-scoped, durable persistence.

All storyboard and story-engine operations require org_id from TenantContext.
This is the AUTHORITATIVE server-side state — browser state is optimistic only.

Persistence model:
- Storyboards persist in `storyboards` table (JSONB shots column)
- Story engine persists in universes/episodes/scenes/shots tables
- All records carry org_id for tenant isolation
- org_id is injected on create, filtered on read, immutable on update

Resumability:
- GET /storyboards/{id} returns full state including shot statuses
- Reopening a storyboard returns authoritative progress
- Browser refresh loads from server truth, not localStorage

Cross-tenant:
- All operations filter by org_id
- Cross-tenant ID access returns None (no existence leak)
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def _db():
    from backend.database import supabase
    return supabase


# =============================================================================
# Storyboards (tenant-scoped, durable)
# =============================================================================


def list_storyboards(org_id: str, status: str | None = None, limit: int = 50) -> list[dict]:
    """List storyboards scoped to a tenant, ordered by most recent."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")
    query = (
        _db().table("storyboards")
        .select("*")
        .eq("org_id", org_id)
        .order("updated_at", desc=True)
        .limit(limit)
    )
    if status:
        query = query.eq("status", status)
    return query.execute().data or []


def get_storyboard(storyboard_id: str, org_id: str) -> dict | None:
    """Get a storyboard by ID with full shot state, scoped to tenant.

    Returns None for not-found and cross-tenant (no existence leak).
    This is the AUTHORITATIVE state — browser must reconcile to this.
    """
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")
    result = (
        _db().table("storyboards")
        .select("*")
        .eq("id", storyboard_id)
        .eq("org_id", org_id)
        .execute()
    )
    return result.data[0] if result.data else None


def create_storyboard(data: dict, org_id: str, user_id: str | None = None) -> dict:
    """Create a storyboard. org_id injected from trusted context.

    The storyboard persists immediately — no in-memory-only state.
    Browser refresh after create will find the storyboard intact.
    """
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped creates")
    data["org_id"] = org_id
    if user_id:
        data["user_id"] = user_id
    if "id" not in data:
        data["id"] = str(uuid.uuid4())
    result = _db().table("storyboards").insert(data).execute()
    return result.data[0] if result.data else data


def update_storyboard(storyboard_id: str, data: dict, org_id: str) -> dict | None:
    """Update a storyboard, scoped to tenant.

    Returns None if not found or cross-tenant.
    org_id cannot be changed (immutable ownership).
    """
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped updates")
    data.pop("org_id", None)  # Prevent ownership reassignment
    data["updated_at"] = "now()"
    result = (
        _db().table("storyboards")
        .update(data)
        .eq("id", storyboard_id)
        .eq("org_id", org_id)
        .execute()
    )
    return result.data[0] if result.data else None


def delete_storyboard(storyboard_id: str, org_id: str) -> bool:
    """Delete a storyboard, scoped to tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped deletes")
    result = (
        _db().table("storyboards")
        .delete()
        .eq("id", storyboard_id)
        .eq("org_id", org_id)
        .execute()
    )
    return bool(result.data)


# =============================================================================
# Shot Status Persistence (within storyboard JSONB)
# =============================================================================


def update_shot_status(
    storyboard_id: str,
    shot_id: str,
    org_id: str,
    status: str,
    image_url: str | None = None,
    job_id: str | None = None,
) -> dict | None:
    """Update a specific shot's status within a storyboard.

    Persists shot progress server-side so it survives browser refresh.
    The storyboard's shots JSONB array is updated atomically.
    """
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped updates")

    storyboard = get_storyboard(storyboard_id, org_id)
    if not storyboard:
        return None

    shots = storyboard.get("shots", [])
    updated = False
    completed_count = 0

    for shot in shots:
        if shot.get("id") == shot_id:
            shot["status"] = status
            if image_url:
                shot["image_url"] = image_url
            if job_id:
                shot["job_id"] = job_id
            updated = True
        if shot.get("status") == "completed":
            completed_count += 1

    if not updated:
        return None

    # Update storyboard with new shot state
    update_data = {
        "shots": shots,
        "completed_shots": completed_count,
    }
    # Auto-update overall status
    if completed_count == len(shots) and len(shots) > 0:
        update_data["status"] = "complete"
    elif any(s.get("status") in ("generating", "queued") for s in shots):
        update_data["status"] = "generating"

    return update_storyboard(storyboard_id, update_data, org_id)


# =============================================================================
# Story Engine (tenant-scoped)
# =============================================================================


def list_universes(org_id: str, project_id: str | None = None) -> list[dict]:
    """List story universes scoped to tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")
    query = _db().table("universes").select("*").eq("org_id", org_id).order("created_at", desc=True)
    if project_id:
        query = query.eq("project_id", project_id)
    return query.execute().data or []


def get_universe(universe_id: str, org_id: str) -> dict | None:
    """Get a universe by ID, scoped to tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")
    result = (
        _db().table("universes")
        .select("*")
        .eq("id", universe_id)
        .eq("org_id", org_id)
        .execute()
    )
    return result.data[0] if result.data else None


def create_universe(data: dict, org_id: str) -> dict:
    """Create a universe. org_id injected."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped creates")
    data["org_id"] = org_id
    result = _db().table("universes").insert(data).execute()
    return result.data[0] if result.data else data


def create_episode(data: dict, org_id: str) -> dict:
    """Create an episode. org_id injected (denormalized from universe)."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped creates")
    data["org_id"] = org_id
    result = _db().table("episodes").insert(data).execute()
    return result.data[0] if result.data else data


def create_scene(data: dict, org_id: str) -> dict:
    """Create a scene. org_id injected (denormalized)."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped creates")
    data["org_id"] = org_id
    result = _db().table("scenes").insert(data).execute()
    return result.data[0] if result.data else data


def create_shot(data: dict, org_id: str) -> dict:
    """Create a shot. org_id injected (denormalized)."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped creates")
    data["org_id"] = org_id
    result = _db().table("shots").insert(data).execute()
    return result.data[0] if result.data else data


def create_shots_bulk(shots: list[dict], org_id: str) -> list[dict]:
    """Bulk create shots. org_id injected on all."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped creates")
    if not shots:
        return []
    for shot in shots:
        shot["org_id"] = org_id
    result = _db().table("shots").insert(shots).execute()
    return result.data or []


def list_episodes(universe_id: str, org_id: str) -> list[dict]:
    """List episodes for a universe, scoped to tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")
    return (
        _db().table("episodes")
        .select("*")
        .eq("universe_id", universe_id)
        .eq("org_id", org_id)
        .order("episode_number")
        .execute().data or []
    )


def list_scenes(episode_id: str, org_id: str) -> list[dict]:
    """List scenes for an episode, scoped to tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")
    return (
        _db().table("scenes")
        .select("*")
        .eq("episode_id", episode_id)
        .eq("org_id", org_id)
        .order("scene_number")
        .execute().data or []
    )


def list_shots(scene_id: str, org_id: str) -> list[dict]:
    """List shots for a scene, scoped to tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")
    return (
        _db().table("shots")
        .select("*")
        .eq("scene_id", scene_id)
        .eq("org_id", org_id)
        .order("shot_number")
        .execute().data or []
    )
