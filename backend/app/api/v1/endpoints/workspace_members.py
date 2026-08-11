"""Workspace Members endpoints — member departure and content ownership.

Routes:
    POST /api/v1/workspace/members/{user_id}/depart → 200 (process departure)
    GET  /api/v1/workspace/members/{user_id}/content-inventory → 200
    GET  /api/v1/workspace/members/{user_id}/deletion-eligibility → 200

Access: ADMIN or above for departure; VIEWER or above for inventory/eligibility.

Validates: Requirements R96.1, R96.2, R96.3, R96.4
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import DBSessionDep
from app.core.rbac import AdminDep, ViewerDep
from app.schemas.workspace_content_ownership import (
    AccountDeletionEligibility,
    ContentInventoryResponse,
    DepartureResponse,
)
from app.services.workspace_content_ownership_service import (
    DepartureError,
    WorkspaceContentOwnershipService,
)

router = APIRouter(prefix="/workspace/members", tags=["workspace"])


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/{user_id}/depart",
    response_model=DepartureResponse,
    status_code=status.HTTP_200_OK,
)
async def process_member_departure(
    user_id: UUID,
    tenant: AdminDep,
    db: DBSessionDep,
) -> DepartureResponse:
    """Process a member's departure from the workspace.

    Handles the full departure protocol:
    1. Workspace content remains (org_id is the owner)
    2. Personal connections are revoked
    3. Workspace connections stay functional
    4. Unfinished jobs are paused for admin review

    Requires: ADMIN role or above.

    Args:
        user_id: UUID of the departing member.

    Returns:
        DepartureResponse with full summary of actions taken.

    Raises:
        HTTPException 404: If user is not a member of this workspace.
        HTTPException 400: If departure processing fails.

    Requirements: R96.1, R96.2
    """
    # Build connection permission service for delegation
    from app.repositories.connection_repository import ConnectionRepository
    from app.services.connection_permission_service import ConnectionPermissionService

    conn_repo = ConnectionRepository(db=db, org_id=tenant.org_id)
    conn_service = ConnectionPermissionService(repo=conn_repo)

    service = WorkspaceContentOwnershipService(
        db=db,
        org_id=tenant.org_id,
        connection_permission_service=conn_service,
    )

    try:
        summary = await service.process_member_departure(
            departing_user_id=user_id,
        )
    except DepartureError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        ) from exc

    return DepartureResponse(
        summary=summary,
        message=(
            f"Member departure processed. "
            f"{summary.workspace_content_preserved} content items preserved, "
            f"{summary.personal_connections_revoked} connections revoked, "
            f"{summary.jobs_paused} jobs paused."
        ),
    )


@router.get(
    "/{user_id}/content-inventory",
    response_model=ContentInventoryResponse,
)
async def get_member_content_inventory(
    user_id: UUID,
    tenant: ViewerDep,
    db: DBSessionDep,
) -> ContentInventoryResponse:
    """Get content inventory for a workspace member.

    Shows workspace-owned content created by the specified user.
    All content belongs to the workspace regardless of who created it.

    Requires: VIEWER role or above.

    Args:
        user_id: UUID of the member to query.

    Returns:
        ContentInventoryResponse with per-type counts.

    Requirements: R96.1
    """
    service = WorkspaceContentOwnershipService(db=db, org_id=tenant.org_id)
    return await service.get_content_inventory(user_id=user_id)


@router.get(
    "/{user_id}/deletion-eligibility",
    response_model=AccountDeletionEligibility,
)
async def check_deletion_eligibility(
    user_id: UUID,
    tenant: ViewerDep,
    db: DBSessionDep,
) -> AccountDeletionEligibility:
    """Check if a user is eligible to delete their account.

    Account deletion is blocked if the user is the sole owner of the
    workspace. Ownership must be transferred to another admin/owner first.

    Requires: VIEWER role or above.

    Args:
        user_id: UUID of the user to check.

    Returns:
        AccountDeletionEligibility with eligibility status and reason.

    Requirements: R96.3
    """
    service = WorkspaceContentOwnershipService(db=db, org_id=tenant.org_id)
    return await service.validate_account_deletion_eligible(user_id=user_id)
