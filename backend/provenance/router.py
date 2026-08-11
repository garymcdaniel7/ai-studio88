"""Asset Provenance API Router (FU-132-A).

Exposes the asset_provenance, asset_lineage, and provenance_amendments
schema (migration 039) via tenant-scoped CRUD endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import AuthUser, require_auth

router = APIRouter(prefix="/api/v1/provenance", tags=["provenance"])


def _db():
    from backend.database import supabase
    return supabase


# =============================================================================
# Asset Provenance
# =============================================================================


@router.get("/assets/{asset_id}")
def get_asset_provenance(asset_id: str, user: AuthUser = Depends(require_auth)):
    """Get full provenance record for an asset (tenant-scoped)."""
    try:
        result = (
            _db().table("asset_provenance")
            .select("*")
            .eq("asset_id", asset_id)
            .eq("org_id", user.org_id)
            .single()
            .execute()
        )
        return result.data
    except Exception:
        raise HTTPException(status_code=404, detail="Provenance not found")


@router.get("/")
def list_provenance(
    user: AuthUser = Depends(require_auth),
    state: str | None = None,
    talent_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List provenance records for the workspace."""
    query = (
        _db().table("asset_provenance")
        .select("*", count="exact")
        .eq("org_id", user.org_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if state:
        query = query.eq("provenance_state", state)
    if talent_id:
        query = query.eq("talent_id", talent_id)
    try:
        result = query.execute()
        return {"items": result.data or [], "total": result.count or 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", status_code=201)
def create_provenance(data: dict, user: AuthUser = Depends(require_auth)):
    """Register provenance for a generated asset."""
    if not data.get("asset_id"):
        raise HTTPException(status_code=422, detail="'asset_id' required")
    data["org_id"] = user.org_id
    data["user_id"] = user.user_id
    data.setdefault("provenance_state", "pending")
    try:
        result = _db().table("asset_provenance").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/assets/{asset_id}")
def update_provenance(asset_id: str, data: dict, user: AuthUser = Depends(require_auth)):
    """Update provenance record (e.g. mark as verified)."""
    data.pop("org_id", None)
    data.pop("asset_id", None)
    try:
        result = (
            _db().table("asset_provenance")
            .update(data)
            .eq("asset_id", asset_id)
            .eq("org_id", user.org_id)
            .execute()
        )
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Lineage Links
# =============================================================================


@router.get("/assets/{asset_id}/lineage")
def get_asset_lineage(asset_id: str, user: AuthUser = Depends(require_auth)):
    """Get parent-child lineage for an asset."""
    try:
        parents = (
            _db().table("asset_lineage")
            .select("*")
            .eq("child_asset_id", asset_id)
            .eq("org_id", user.org_id)
            .execute()
        )
        children = (
            _db().table("asset_lineage")
            .select("*")
            .eq("parent_asset_id", asset_id)
            .eq("org_id", user.org_id)
            .execute()
        )
        return {
            "asset_id": asset_id,
            "parents": parents.data or [],
            "children": children.data or [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lineage", status_code=201)
def create_lineage_link(data: dict, user: AuthUser = Depends(require_auth)):
    """Link a child asset to a parent (derived_from, remix_of, etc)."""
    if not data.get("child_asset_id") or not data.get("parent_asset_id"):
        raise HTTPException(status_code=422, detail="child_asset_id and parent_asset_id required")
    data["org_id"] = user.org_id
    data.setdefault("relationship", "derived_from")
    try:
        result = _db().table("asset_lineage").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Amendments (audited corrections)
# =============================================================================


@router.get("/assets/{asset_id}/amendments")
def list_amendments(asset_id: str, user: AuthUser = Depends(require_auth)):
    """Get provenance amendment history for an asset."""
    try:
        result = (
            _db().table("provenance_amendments")
            .select("*")
            .eq("asset_id", asset_id)
            .eq("org_id", user.org_id)
            .order("amended_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assets/{asset_id}/amendments", status_code=201)
def create_amendment(asset_id: str, data: dict, user: AuthUser = Depends(require_auth)):
    """Record an audited correction to provenance."""
    if not data.get("field_name") or not data.get("reason"):
        raise HTTPException(status_code=422, detail="field_name and reason required")
    data["asset_id"] = asset_id
    data["org_id"] = user.org_id
    data["amended_by"] = user.user_id
    try:
        result = _db().table("provenance_amendments").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
