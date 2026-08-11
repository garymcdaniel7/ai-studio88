"""Delegated Permissions endpoints.

Routes:
    GET    /api/v1/workspace/delegated-permissions  → 200 (list permissions)
    POST   /api/v1/workspace/delegated-permissions  → 201 (grant permission)
    DELETE /api/v1/workspace/delegated-permissions/{id}  → 204 (revoke permission)

Access: ADMIN or above for POST/DELETE, VIEWER or above for GET.
These endpoints are tenant-scoped — each workspace manages its own delegations.

Validates: Requirements R30.14, R98.3
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import DBSessionDep, PaginationDep
from app.core.rbac import AdminDep, ViewerDep
from app.schemas.delegated_permission import (
    DelegatedPermissionCreate,
    DelegatedPermissionListResponse,
    DelegatedPermissionResponse,
)
from app.services.delegated_permission_service import (
    DelegatedPermissionAlreadyRevokedError,
    DelegatedPermissionNotFoundError,
    DelegatedPermissionService,
)

router = APIRouter(prefix="/workspace", tags=["workspace"])


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/delegated-permissions",
    response_model=DelegatedPermissionListResponse,
)
async def list_delegated_permissions(
    tenant: ViewerDep,
    db: DBSessionDep,
    pagination: PaginationDep,
    include_revoked: bool = False,
) -> DelegatedPermissionListResponse:
    """List all delegated permissions for the workspace.

    Returns a paginated list of delegated permissions. By default, only
    active (non-revoked) permissions are returned. Use include_revoked=true
    to see all permissions including revoked ones.

    Requires: VIEWER role or above.

    Requirements: R30.14, R98.3
    """
    service = DelegatedPermissionService(db=db)
    items, total = await service.list_permissions(
        org_id=tenant.org_id,
        limit=pagination.limit,
        offset=pagination.offset,
        include_revoked=include_revoked,
    )

    return DelegatedPermissionListResponse(
        items=[
            DelegatedPermissionResponse(
                id=p.id,
                org_id=p.org_id,
                delegated_by=p.delegated_by,
                action_class=p.action_class,
                connection_scope=p.connection_scope,
                max_cost_usd=p.max_cost_usd,
                expires_at=p.expires_at,
                revoked_at=p.revoked_at,
                created_at=p.created_at,
                updated_at=p.updated_at,
                is_active=p.is_active,
            )
            for p in items
        ],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "/delegated-permissions",
    response_model=DelegatedPermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_delegated_permission(
    body: DelegatedPermissionCreate,
    tenant: AdminDep,
    db: DBSessionDep,
) -> DelegatedPermissionResponse:
    """Grant a new delegated permission to Hermes.

    Creates a delegation allowing Hermes to autonomously execute the
    specified action_class within the configured limits. Delegated
    permissions cannot exceed the delegator's own role permissions.

    Requires: ADMIN role or above.

    Requirements: R30.14, R98.3
    """
    service = DelegatedPermissionService(db=db)
    perm = await service.grant_permission(
        org_id=tenant.org_id,
        delegated_by=tenant.user_id,
        action_class=body.action_class,
        connection_scope=body.connection_scope,
        max_cost_usd=body.max_cost_usd,
        expires_at=body.expires_at,
    )

    return DelegatedPermissionResponse(
        id=perm.id,
        org_id=perm.org_id,
        delegated_by=perm.delegated_by,
        action_class=perm.action_class,
        connection_scope=perm.connection_scope,
        max_cost_usd=perm.max_cost_usd,
        expires_at=perm.expires_at,
        revoked_at=perm.revoked_at,
        created_at=perm.created_at,
        updated_at=perm.updated_at,
        is_active=perm.is_active,
    )


@router.delete(
    "/delegated-permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_delegated_permission(
    permission_id: UUID,
    tenant: AdminDep,
    db: DBSessionDep,
) -> None:
    """Revoke a delegated permission immediately.

    Once revoked, Hermes can no longer autonomously execute the
    delegated action class. Revocation takes effect immediately.

    Requires: ADMIN role or above.

    Requirements: R30.14, R98.3
    """
    service = DelegatedPermissionService(db=db)
    try:
        await service.revoke_permission(
            permission_id=permission_id,
            org_id=tenant.org_id,
            revoked_by=tenant.user_id,
        )
    except DelegatedPermissionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delegated permission not found",
            headers={"X-Error-Code": "NOT_FOUND"},
        )
    except DelegatedPermissionAlreadyRevokedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delegated permission already revoked",
            headers={"X-Error-Code": "ALREADY_REVOKED"},
        )
