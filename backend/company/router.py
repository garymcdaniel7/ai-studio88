"""Production Company OS API Router.

Organizations, studios, brands, campaigns, teams, approvals, clients, licenses.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/company", tags=["company"])


def _db():
    from backend.database import supabase
    return supabase


TEAM_ROLES = ["owner", "admin", "creative_director", "editor", "producer",
              "prompt_engineer", "reviewer", "viewer"]

APPROVAL_STATUSES = ["pending", "approved", "rejected", "revision_requested"]


# =============================================================================
# Organizations
# =============================================================================

@router.get("/organizations")
def list_organizations():
    try: return _db().table("organizations").select("*").order("name").execute().data
    except Exception: return []

@router.post("/organizations", status_code=201)
def create_organization(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("organizations").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/organizations/{org_id}")
def get_organization(org_id: str):
    try: return _db().table("organizations").select("*").eq("id", org_id).single().execute().data
    except Exception: raise HTTPException(status_code=404, detail="Organization not found")


# =============================================================================
# Studios
# =============================================================================

@router.get("/studios")
def list_studios(organization_id: Optional[str] = None):
    query = _db().table("studios").select("*").order("name")
    if organization_id: query = query.eq("organization_id", organization_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/studios", status_code=201)
def create_studio(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("studios").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Brands
# =============================================================================

@router.get("/brands")
def list_brands(organization_id: Optional[str] = None, status: Optional[str] = None):
    query = _db().table("brands").select("*").order("name")
    if organization_id: query = query.eq("organization_id", organization_id)
    if status: query = query.eq("status", status)
    try: return query.execute().data
    except Exception: return []

@router.post("/brands", status_code=201)
def create_brand(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("brands").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/brands/{brand_id}")
def get_brand(brand_id: str):
    try: return _db().table("brands").select("*").eq("id", brand_id).single().execute().data
    except Exception: raise HTTPException(status_code=404, detail="Brand not found")

@router.put("/brands/{brand_id}")
def update_brand(brand_id: str, data: dict):
    data["updated_at"] = "now()"
    try:
        result = _db().table("brands").update(data).eq("id", brand_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/brands/{brand_id}")
def delete_brand(brand_id: str):
    try:
        _db().table("brands").delete().eq("id", brand_id).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Brand Campaigns
# =============================================================================

@router.get("/campaigns")
def list_brand_campaigns(brand_id: Optional[str] = None, status: Optional[str] = None):
    query = _db().table("brand_campaigns").select("*").order("created_at", desc=True)
    if brand_id: query = query.eq("brand_id", brand_id)
    if status: query = query.eq("status", status)
    try: return query.execute().data
    except Exception: return []

@router.post("/campaigns", status_code=201)
def create_brand_campaign(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("brand_campaigns").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/campaigns/{campaign_id}")
def get_brand_campaign(campaign_id: str):
    try: return _db().table("brand_campaigns").select("*").eq("id", campaign_id).single().execute().data
    except Exception: raise HTTPException(status_code=404, detail="Campaign not found")

@router.put("/campaigns/{campaign_id}")
def update_brand_campaign(campaign_id: str, data: dict):
    data["updated_at"] = "now()"
    try:
        result = _db().table("brand_campaigns").update(data).eq("id", campaign_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Team
# =============================================================================

@router.get("/team")
def list_team(organization_id: Optional[str] = None):
    query = _db().table("team_members").select("*").order("name")
    if organization_id: query = query.eq("organization_id", organization_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/team", status_code=201)
def add_team_member(data: dict):
    if not data.get("name") or not data.get("role"):
        raise HTTPException(status_code=400, detail="'name' and 'role' required")
    if data["role"] not in TEAM_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Valid: {TEAM_ROLES}")
    try:
        result = _db().table("team_members").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/team/roles")
def list_team_roles():
    return TEAM_ROLES

@router.put("/team/{member_id}")
def update_team_member(member_id: str, data: dict):
    data["updated_at"] = "now()"
    try:
        result = _db().table("team_members").update(data).eq("id", member_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/team/{member_id}")
def remove_team_member(member_id: str):
    try:
        _db().table("team_members").delete().eq("id", member_id).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Approvals
# =============================================================================

@router.get("/approvals")
def list_approvals(status: Optional[str] = None, brand_id: Optional[str] = None):
    query = _db().table("approval_requests").select("*").order("created_at", desc=True)
    if status: query = query.eq("status", status)
    if brand_id: query = query.eq("brand_id", brand_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/approvals", status_code=201)
def create_approval(data: dict):
    record = {
        "organization_id": data.get("organization_id"),
        "brand_id": data.get("brand_id"),
        "asset_id": data.get("asset_id"),
        "requested_by": data.get("requested_by", ""),
        "assigned_to": data.get("assigned_to", ""),
        "approval_type": data.get("approval_type", "creative"),
        "status": "pending",
        "notes": data.get("notes", ""),
    }
    try:
        result = _db().table("approval_requests").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/approvals/{approval_id}/decide")
def decide_approval(approval_id: str, data: dict):
    decision = data.get("decision")
    if decision not in APPROVAL_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid decision. Valid: {APPROVAL_STATUSES}")
    try:
        _db().table("approval_requests").update({
            "status": decision, "notes": data.get("notes", ""), "decided_at": "now()",
        }).eq("id", approval_id).execute()
        return {"decided": True, "status": decision}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Clients
# =============================================================================

@router.get("/clients")
def list_clients(organization_id: Optional[str] = None):
    query = _db().table("clients").select("*").order("name")
    if organization_id: query = query.eq("organization_id", organization_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/clients", status_code=201)
def create_client(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    try:
        result = _db().table("clients").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Licenses
# =============================================================================

@router.get("/licenses")
def list_licenses(asset_id: Optional[str] = None):
    query = _db().table("asset_licenses").select("*").order("created_at", desc=True)
    if asset_id: query = query.eq("asset_id", asset_id)
    try: return query.execute().data
    except Exception: return []

@router.post("/licenses", status_code=201)
def create_license(data: dict):
    if not data.get("asset_id"):
        raise HTTPException(status_code=400, detail="'asset_id' required")
    try:
        result = _db().table("asset_licenses").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
