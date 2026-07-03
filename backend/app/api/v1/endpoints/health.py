"""Health check endpoints for the v1 API prefix."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("", summary="API v1 health")
async def v1_health() -> dict[str, str]:
    """Returns OK if the v1 API is reachable."""
    return {"status": "ok", "api": "v1"}
