"""Workspace Autonomy Profile endpoints.

Routes:
    GET  /api/v1/workspace/autonomy  → 200 (current autonomy profile)
    PUT  /api/v1/workspace/autonomy  → 200 (update autonomy profile)

Access: ADMIN or above for PUT, VIEWER or above for GET.
These endpoints are tenant-scoped — each workspace manages its own profile.

Validates: Requirements R98.1, R98.2, R30.12, R30.13
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import DBSessionDep
from app.core.rbac import AdminDep, ViewerDep
from app.schemas.workspace_autonomy import (
    AutonomyProfileResponse,
    AutonomyProfileUpdate,
    MandatoryControlsResponse,
)
from app.services.autonomy_profile_service import (
    AutonomyLevel,
    AutonomyProfileService,
)

router = APIRouter(prefix="/workspace", tags=["workspace"])


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/autonomy", response_model=AutonomyProfileResponse)
async def get_workspace_autonomy(
    tenant: ViewerDep,
    db: DBSessionDep,
) -> AutonomyProfileResponse:
    """Get the current workspace autonomy profile.

    Returns the autonomy level and mandatory controls for this workspace.
    Returns defaults (ADVISORY) if no profile has been configured.

    Requires: VIEWER role or above.

    Requirements: R98.1
    """
    service = AutonomyProfileService(db=db)
    profile = await service.get_profile(org_id=tenant.org_id)

    return AutonomyProfileResponse(
        org_id=profile.org_id,
        autonomy_level=profile.autonomy_level.value,
        mandatory_controls=MandatoryControlsResponse(**profile.mandatory_controls),
    )


@router.put("/autonomy", response_model=AutonomyProfileResponse)
async def update_workspace_autonomy(
    body: AutonomyProfileUpdate,
    tenant: AdminDep,
    db: DBSessionDep,
) -> AutonomyProfileResponse:
    """Update workspace autonomy profile.

    Sets the autonomy level for this workspace. Only ADMIN or above
    can modify this setting since it affects agent behavior for all
    users within the workspace.

    Autonomy levels:
    - ADVISORY: Brain/Hermes recommends only, never auto-executes mutations.
    - ASSISTED: Low-risk actions auto-execute (reads, knowledge retrieval).
      High-risk actions still require user confirmation.
    - AUTONOMOUS_WITHIN_LIMITS: Delegated actions execute within configured
      limits without per-action confirmation.

    Mandatory safety/security/consent/budget/destructive controls are ALWAYS
    enforced regardless of the chosen autonomy level.

    Requires: ADMIN role or above.

    Requirements: R98.1, R98.2, R30.12, R30.13
    """
    service = AutonomyProfileService(db=db)
    profile = await service.set_profile(
        org_id=tenant.org_id,
        autonomy_level=AutonomyLevel(body.autonomy_level.value),
        updated_by=tenant.user_id,
    )

    return AutonomyProfileResponse(
        org_id=profile.org_id,
        autonomy_level=profile.autonomy_level.value,
        mandatory_controls=MandatoryControlsResponse(**profile.mandatory_controls),
    )
