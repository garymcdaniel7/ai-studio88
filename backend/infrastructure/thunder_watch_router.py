"""Admin-scoped Thunder Compute watcher endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.core.config import get_settings
from backend.infrastructure.authorization import TenantContext, require_infra_admin
from backend.infrastructure.thunder_watch import ThunderWatcher, ThunderWatchError

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])


class ThunderWatchResponse(BaseModel):
    """Safe watcher result containing only provider instance identifiers."""

    terminated: list[str] = Field(default_factory=list)
    warned: list[str] = Field(default_factory=list)


@router.post(
    "/thunder-watch",
    response_model=ThunderWatchResponse,
    status_code=status.HTTP_200_OK,
)
async def thunder_watch(_ctx: TenantContext = Depends(require_infra_admin)) -> ThunderWatchResponse:
    """Protect GPU spend by terminating idle Thunder instances.

    Access is admin-scoped through the authenticated workspace membership. The
    watcher checks all durable tenant job activity before global provider cleanup,
    but returns no tenant or job details to the caller.
    """
    try:
        result = await ThunderWatcher(get_settings()).run()
    except ThunderWatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Thunder watcher temporarily unavailable",
        ) from exc
    return ThunderWatchResponse(**result)
