"""V1 API router — wraps existing Supabase functions under /api/v1/.

These endpoints mirror the root-level ones but under the versioned prefix.
They use the existing database.py Supabase client directly (no ORM, no auth).
As services are implemented, these will be replaced by the full scaffold endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.database import get_projects, get_talent, create_talent

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
