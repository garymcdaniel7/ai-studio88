"""Deletion Lifecycle API Router (FU-132-A).

Exposes lifecycle state management for entities: trash, restore, hold,
permanent delete. Uses the schema from migration 038.

Entities supported: ai_talent, content_jobs, lora_models, workflows,
brain_conversations, projects, campaigns.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import AuthUser, require_auth

router = APIRouter(prefix="/api/v1/lifecycle", tags=["lifecycle"])

SUPPORTED_ENTITIES = [
    "ai_talent",
    "content_jobs",
    "lora_models",
    "workflows",
    "brain_conversations",
    "projects",
    "campaigns",
]


def _db():
    from backend.database import supabase
    return supabase


def _validate_entity_type(entity_type: str) -> None:
    if entity_type not in SUPPORTED_ENTITIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported entity type. Valid: {SUPPORTED_ENTITIES}",
        )


# =============================================================================
# Trash (soft delete)
# =============================================================================


@router.post("/{entity_type}/{entity_id}/trash")
def trash_entity(
    entity_type: str,
    entity_id: str,
    data: dict | None = None,
    user: AuthUser = Depends(require_auth),
):
    """Move an entity to trash (soft delete).

    Records the transition in lifecycle_transitions for audit.
    """
    _validate_entity_type(entity_type)
    reason = (data or {}).get("reason", "")

    try:
        # Update entity lifecycle_state
        _db().table(entity_type).update({
            "lifecycle_state": "trashed",
            "trashed_at": "now()",
            "trashed_by": user.user_id,
            "trash_reason": reason,
        }).eq("id", entity_id).eq("org_id", user.org_id).execute()

        # Record transition
        _db().table("lifecycle_transitions").insert({
            "entity_type": entity_type,
            "entity_id": entity_id,
            "org_id": user.org_id,
            "prior_state": "active",
            "new_state": "trashed",
            "action": "trash",
            "actor_id": user.user_id,
            "actor_role": "owner",
            "reason": reason,
        }).execute()

        return {"status": "trashed", "entity_type": entity_type, "entity_id": entity_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Restore
# =============================================================================


@router.post("/{entity_type}/{entity_id}/restore")
def restore_entity(
    entity_type: str,
    entity_id: str,
    user: AuthUser = Depends(require_auth),
):
    """Restore a trashed entity back to active."""
    _validate_entity_type(entity_type)

    try:
        _db().table(entity_type).update({
            "lifecycle_state": "active",
            "trashed_at": None,
            "trashed_by": None,
            "trash_reason": None,
        }).eq("id", entity_id).eq("org_id", user.org_id).execute()

        _db().table("lifecycle_transitions").insert({
            "entity_type": entity_type,
            "entity_id": entity_id,
            "org_id": user.org_id,
            "prior_state": "trashed",
            "new_state": "active",
            "action": "restore",
            "actor_id": user.user_id,
            "actor_role": "owner",
        }).execute()

        return {"status": "restored", "entity_type": entity_type, "entity_id": entity_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Holds
# =============================================================================


@router.post("/{entity_type}/{entity_id}/hold")
def place_hold(
    entity_type: str,
    entity_id: str,
    data: dict,
    user: AuthUser = Depends(require_auth),
):
    """Place a hold on an entity (prevents permanent deletion)."""
    _validate_entity_type(entity_type)
    if not data.get("hold_type") or not data.get("reason"):
        raise HTTPException(status_code=422, detail="hold_type and reason required")

    try:
        _db().table("entity_holds").insert({
            "entity_type": entity_type,
            "entity_id": entity_id,
            "org_id": user.org_id,
            "hold_type": data["hold_type"],
            "placed_by": user.user_id,
            "reason": data["reason"],
            "expires_at": data.get("expires_at"),
        }).execute()

        return {"status": "hold_placed", "entity_type": entity_type, "entity_id": entity_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{entity_type}/{entity_id}/holds")
def get_holds(
    entity_type: str,
    entity_id: str,
    user: AuthUser = Depends(require_auth),
):
    """Get active holds on an entity."""
    _validate_entity_type(entity_type)
    try:
        result = (
            _db().table("entity_holds")
            .select("*")
            .eq("entity_type", entity_type)
            .eq("entity_id", entity_id)
            .eq("org_id", user.org_id)
            .is_("released_at", "null")
            .execute()
        )
        return result.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Transition History
# =============================================================================


@router.get("/{entity_type}/{entity_id}/history")
def get_lifecycle_history(
    entity_type: str,
    entity_id: str,
    user: AuthUser = Depends(require_auth),
):
    """Get full lifecycle transition history for an entity."""
    _validate_entity_type(entity_type)
    try:
        result = (
            _db().table("lifecycle_transitions")
            .select("*")
            .eq("entity_type", entity_type)
            .eq("entity_id", entity_id)
            .eq("org_id", user.org_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Trash Bin (list trashed entities)
# =============================================================================


@router.get("/trash")
def list_trash(
    entity_type: str | None = None,
    user: AuthUser = Depends(require_auth),
):
    """List all trashed entities in the workspace (trash bin view)."""
    results = []
    types_to_check = [entity_type] if entity_type else SUPPORTED_ENTITIES

    for etype in types_to_check:
        if etype not in SUPPORTED_ENTITIES:
            continue
        try:
            data = (
                _db().table(etype)
                .select("id, lifecycle_state, trashed_at, trashed_by, trash_reason")
                .eq("org_id", user.org_id)
                .eq("lifecycle_state", "trashed")
                .order("trashed_at", desc=True)
                .limit(50)
                .execute()
            )
            for item in data.data or []:
                item["entity_type"] = etype
                results.append(item)
        except Exception:
            continue

    results.sort(key=lambda x: x.get("trashed_at", ""), reverse=True)
    return {"items": results[:100], "total": len(results)}
