"""Workspace Fallback Preferences endpoints.

Routes:
    GET  /api/v1/workspace/fallback  → 200 (current fallback config)
    PUT  /api/v1/workspace/fallback  → 200 (update fallback config)

Access: ADMIN or above for PUT, VIEWER or above for GET.
These endpoints are tenant-scoped — each workspace manages its own config.

Validates: Requirements R26.3, R26.4, R26.9, R102.1, R102.2, R102.3
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.core.rbac import AdminDep, ViewerDep
from app.schemas.workspace_fallback import (
    WorkspaceFallbackConfigResponse,
    WorkspaceFallbackConfigUpdate,
)
from app.services.workspace_fallback_service import (
    FallbackMode,
    WorkspaceFallbackService,
)

router = APIRouter(prefix="/workspace", tags=["workspace"])


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/fallback", response_model=WorkspaceFallbackConfigResponse)
async def get_workspace_fallback(
    tenant: ViewerDep,
    db: DBSessionDep,
) -> WorkspaceFallbackConfigResponse:
    """Get the current workspace fallback preferences.

    Returns the fallback mode (AUTO/ASK/STRICT) and the list of
    denied providers for this workspace. Returns defaults (AUTO, [])
    if no configuration has been set.

    Requires: VIEWER role or above.

    Requirements: R26.3, R102.1
    """
    service = WorkspaceFallbackService(db=db)
    config = await service.get_config(org_id=tenant.org_id)

    return WorkspaceFallbackConfigResponse(
        org_id=config.org_id,
        fallback_mode=config.fallback_mode.value,
        denied_providers=config.denied_providers,
    )


@router.put("/fallback", response_model=WorkspaceFallbackConfigResponse)
async def update_workspace_fallback(
    body: WorkspaceFallbackConfigUpdate,
    tenant: AdminDep,
    db: DBSessionDep,
) -> WorkspaceFallbackConfigResponse:
    """Update workspace fallback preferences.

    Sets the fallback mode and denied provider list for this workspace.
    Only ADMIN or above can modify these settings since they affect
    all users within the workspace.

    Fallback modes:
    - AUTO: Automatically route to next available provider in chain.
    - ASK: Pause and return alternatives for user confirmation.
    - STRICT: Fail the request — never route to a different provider.

    Privacy policy (denied_providers):
    - Providers in this list will never be used, regardless of fallback mode.
    - If AUTO mode would only have denied providers available, it is
      treated as STRICT (privacy override per R26.9).

    Requires: ADMIN role or above.

    Requirements: R26.3, R26.4, R26.9, R102.2, R102.3
    """
    service = WorkspaceFallbackService(db=db)
    config = await service.set_config(
        org_id=tenant.org_id,
        fallback_mode=FallbackMode(body.fallback_mode),
        denied_providers=body.denied_providers,
        updated_by=tenant.user_id,
    )

    return WorkspaceFallbackConfigResponse(
        org_id=config.org_id,
        fallback_mode=config.fallback_mode.value,
        denied_providers=config.denied_providers,
    )
