"""Platform Admin — Compute Availability endpoints.

Routes:
    GET    /platform-admin/compute/state    → 200 (current state + grants)
    PUT    /platform-admin/compute/state    → 200 (change DISABLED/SELECTIVE/ENABLED)
    POST   /platform-admin/compute/grants   → 201 (create selective grant)
    DELETE /platform-admin/compute/grants/{id} → 204 (revoke selective grant)
    GET    /platform-admin/compute/grants   → 200 (list active grants)

Access: Platform Operators with Founder Authority only.
These endpoints are NOT tenant-scoped — they manage platform-level config.

Validates: Requirements R86.1, R86.2, R86.3, R86.5, R13.16
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import DBSessionDep
from app.core.rbac import OwnerDep
from app.schemas.compute_availability import (
    ComputeStateResponse,
    ComputeStateUpdate,
    ComputeStateWithGrantsResponse,
    SelectiveGrantCreate,
    SelectiveGrantListResponse,
    SelectiveGrantResponse,
)
from app.services.compute_availability_service import (
    ComputeAvailabilityService,
    ComputeAvailabilityState,
    GrantType,
)

router = APIRouter(prefix="/platform-admin/compute", tags=["platform-admin"])


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/state", response_model=ComputeStateWithGrantsResponse)
async def get_compute_state(
    tenant: OwnerDep,
    db: DBSessionDep,
) -> ComputeStateWithGrantsResponse:
    """Get the current compute availability state and active grants.

    Returns the current state, who changed it, when, and the list
    of active selective grants (if in SELECTIVE mode).

    Requires: OWNER role (Founder Authority).

    Requirements: R86.1
    """
    service = ComputeAvailabilityService(db=db)
    details = await service.get_state_details()

    grants = [
        SelectiveGrantResponse(
            id=g.id,
            grant_type=g.grant_type,
            grant_target=g.grant_target,
            expires_at=g.expires_at,
            granted_by=g.granted_by,
            revoked_at=g.revoked_at,
            revoked_by=g.revoked_by,
            created_at=g.created_at,
        )
        for g in details["grants"]
    ]

    return ComputeStateWithGrantsResponse(
        state=details["state"].value if details["state"] else "disabled",
        changed_by=details["changed_by"] or UUID("00000000-0000-0000-0000-000000000000"),
        changed_at=details["changed_at"] or details.get("changed_at"),
        reason=details["reason"],
        selective_grants=grants,
    )


@router.put("/state", response_model=ComputeStateResponse)
async def update_compute_state(
    body: ComputeStateUpdate,
    tenant: OwnerDep,
    db: DBSessionDep,
) -> ComputeStateResponse:
    """Change the compute availability state.

    This is a Founder-level action that controls whether platform-managed
    compute is available to any workspace. State changes propagate within
    60 seconds without code deployment or service restart.

    States:
    - DISABLED: All compute requests rejected with 403
    - SELECTIVE: Only granted workspaces/plans/cohorts can access
    - ENABLED: All eligible workspaces can access

    Requires: OWNER role (Founder Authority).

    Requirements: R86.1, R86.5, R13.16
    """
    service = ComputeAvailabilityService(db=db)
    new_state = ComputeAvailabilityState(body.state.value)

    config = await service.set_state_async(
        new_state=new_state,
        changed_by=tenant.user_id,
        reason=body.reason,
    )

    return ComputeStateResponse(
        state=config.state,
        changed_by=config.changed_by,
        changed_at=config.changed_at,
        reason=config.reason,
    )


@router.get("/grants", response_model=SelectiveGrantListResponse)
async def list_selective_grants(
    tenant: OwnerDep,
    db: DBSessionDep,
) -> SelectiveGrantListResponse:
    """List all active selective compute grants.

    Returns grants that are not revoked and not expired.
    Used when in SELECTIVE mode to see which workspaces/plans/etc.
    have access to platform-managed compute.

    Requires: OWNER role (Founder Authority).

    Requirements: R86.3
    """
    service = ComputeAvailabilityService(db=db)
    grants = await service.list_active_grants()

    items = [
        SelectiveGrantResponse(
            id=g.id,
            grant_type=g.grant_type,
            grant_target=g.grant_target,
            expires_at=g.expires_at,
            granted_by=g.granted_by,
            revoked_at=g.revoked_at,
            revoked_by=g.revoked_by,
            created_at=g.created_at,
        )
        for g in grants
    ]

    return SelectiveGrantListResponse(
        items=items,
        total=len(items),
        limit=100,
        offset=0,
    )


@router.post(
    "/grants",
    response_model=SelectiveGrantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_selective_grant(
    body: SelectiveGrantCreate,
    tenant: OwnerDep,
    db: DBSessionDep,
) -> SelectiveGrantResponse:
    """Create a selective compute access grant.

    Grants access to platform-managed compute for a specific workspace,
    plan, cohort, workload class, provider, or promotion.

    Only effective when compute state is SELECTIVE.
    When state is ENABLED, grants are informational (all have access).
    When state is DISABLED, grants are ignored (none have access).

    Requires: OWNER role (Founder Authority).

    Requirements: R86.3
    """
    service = ComputeAvailabilityService(db=db)
    grant_type = GrantType(body.grant_type.value)

    grant = await service.create_selective_grant(
        grant_type=grant_type,
        grant_target=body.grant_target,
        granted_by=tenant.user_id,
        expires_at=body.expires_at,
    )

    return SelectiveGrantResponse(
        id=grant.id,
        grant_type=grant.grant_type,
        grant_target=grant.grant_target,
        expires_at=grant.expires_at,
        granted_by=grant.granted_by,
        revoked_at=grant.revoked_at,
        revoked_by=grant.revoked_by,
        created_at=grant.created_at,
    )


@router.delete(
    "/grants/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_selective_grant(
    grant_id: UUID,
    tenant: OwnerDep,
    db: DBSessionDep,
) -> None:
    """Revoke a selective compute access grant.

    Soft-revokes the grant by setting revoked_at and revoked_by.
    The revocation propagates within 60 seconds (cache TTL).

    Requires: OWNER role (Founder Authority).

    Requirements: R86.3
    """
    service = ComputeAvailabilityService(db=db)
    grant = await service.revoke_selective_grant(
        grant_id=grant_id,
        revoked_by=tenant.user_id,
    )

    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grant not found or already revoked",
            headers={"X-Error-Code": "NOT_FOUND"},
        )
