"""External Deletion Tracking — Admin endpoints for Platform Operators.

Routes:
    GET  /admin/deletions          → 200 (list pending/failed deletions)
    POST /admin/deletions/{id}/retry → 200 (retry a failed deletion)

Access: Platform Operators (admin or above) — insufficient role receives 403.
All operations are logged.

Validates: Requirements R105.1, R105.2, R105.3
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.core.dependencies import DBSessionDep, PaginationDep, TenantContextDep
from app.core.logging import get_logger
from app.models.external_deletion import DeletionState
from app.schemas.external_deletion import (
    ExternalDeletionListResponse,
    ExternalDeletionResponse,
    ExternalDeletionRetryResponse,
)
from app.services.external_deletion_service import (
    DeletionNotFoundError,
    DeletionStateTransitionError,
    ExternalDeletionService,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/admin/deletions",
    tags=["admin-deletions"],
)


@router.get(
    "",
    response_model=ExternalDeletionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List external deletion records",
    description=(
        "Lists external deletion tracking records. Platform Operators see "
        "all failed deletions across tenants. Workspace admins see only "
        "their org's records."
    ),
)
async def list_deletions(
    db: DBSessionDep,
    tenant: TenantContextDep,
    pagination: PaginationDep,
    state: DeletionState | None = Query(
        default=None,
        description="Filter by deletion state",
    ),
) -> ExternalDeletionListResponse:
    """List external deletion tracking records.

    Requires admin role or above. Filters by org_id from TenantContext.

    Args:
        db: Database session.
        tenant: Resolved tenant context.
        pagination: Limit/offset pagination params.
        state: Optional filter by deletion state.

    Returns:
        Paginated list of deletion tracking records.
    """
    from app.core.dependencies import WorkspaceRole

    tenant.require_role(WorkspaceRole.ADMIN)

    service = ExternalDeletionService(db)
    items, total = await service.list_by_state(
        org_id=tenant.org_id,
        state=state,
        limit=pagination.limit,
        offset=pagination.offset,
    )

    return ExternalDeletionListResponse(
        items=[ExternalDeletionResponse.model_validate(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/{deletion_id}",
    response_model=ExternalDeletionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single external deletion record",
)
async def get_deletion(
    deletion_id: UUID,
    db: DBSessionDep,
    tenant: TenantContextDep,
) -> ExternalDeletionResponse:
    """Get a single deletion tracking record by ID.

    Returns 404 if not found (prevents cross-tenant information leakage).

    Args:
        deletion_id: The deletion tracking record UUID.
        db: Database session.
        tenant: Resolved tenant context.

    Returns:
        The deletion tracking record.
    """
    from app.core.dependencies import WorkspaceRole

    tenant.require_role(WorkspaceRole.ADMIN)

    service = ExternalDeletionService(db)
    record = await service.get(deletion_id, tenant.org_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deletion record not found",
        )

    return ExternalDeletionResponse.model_validate(record)


@router.post(
    "/{deletion_id}/retry",
    response_model=ExternalDeletionRetryResponse,
    status_code=status.HTTP_200_OK,
    summary="Retry a failed external deletion",
    description=(
        "Transitions a FAILED deletion back to REQUESTED state for retry. "
        "Platform Operators can trigger this after investigating the failure."
    ),
)
async def retry_deletion(
    deletion_id: UUID,
    db: DBSessionDep,
    tenant: TenantContextDep,
) -> ExternalDeletionRetryResponse:
    """Retry a failed external deletion.

    Only valid for records in EXTERNAL_DELETION_FAILED state.
    Transitions the record back to EXTERNAL_DELETION_REQUESTED.

    Args:
        deletion_id: The deletion tracking record UUID.
        db: Database session.
        tenant: Resolved tenant context.

    Returns:
        Updated record with retry confirmation message.

    Raises:
        404: Record not found in this org.
        409: Record is not in FAILED state (invalid transition).
    """
    from app.core.dependencies import WorkspaceRole

    tenant.require_role(WorkspaceRole.ADMIN)

    service = ExternalDeletionService(db)

    try:
        record = await service.retry_deletion(deletion_id, tenant.org_id)
    except DeletionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deletion record not found",
        )
    except DeletionStateTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot retry: {exc}",
        )

    logger.info(
        "external_deletion_retry_triggered",
        deletion_id=str(deletion_id),
        org_id=str(tenant.org_id),
        user_id=str(tenant.user_id),
        retry_count=record.retry_count,
    )

    return ExternalDeletionRetryResponse(
        id=record.id,
        deletion_state=DeletionState(record.deletion_state),
        retry_count=record.retry_count,
        message="Deletion retry initiated successfully",
    )
