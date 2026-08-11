"""Workspace data export API endpoints.

Routes:
    POST /workspace/export         → 202 Accepted (initiate async export)
    GET  /workspace/export/{id}    → 200 (get export status + download URL)

Export requires owner or admin role. Data is tenant-scoped to the
authenticated workspace.

Validates: Requirements R104.1, R104.2, R104.3
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import TenantContextDep
from app.core.rbac import AdminDep
from app.schemas.workspace_export import (
    WorkspaceExportRequest,
    WorkspaceExportResponse,
)
from app.services.workspace_export_service import (
    ExportNotFoundError,
    WorkspaceExportService,
)

router = APIRouter(prefix="/workspace/export", tags=["workspace-export"])


@router.post(
    "",
    response_model=WorkspaceExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Initiate workspace data export",
    description=(
        "Starts an asynchronous export of workspace data. "
        "Returns 202 Accepted with the export job record. "
        "Poll GET /workspace/export/{id} for status and download URL. "
        "Requires owner or admin role."
    ),
)
async def initiate_export(
    tenant: AdminDep,
    body: WorkspaceExportRequest | None = None,
) -> WorkspaceExportResponse:
    """Initiate an async workspace data export.

    Creates an export job that asynchronously collects and packages
    workspace data into a downloadable JSON file.

    Requires: ADMIN role (owner or admin).
    org_id resolved from TenantContext, never from client.

    Requirements: R104.1, R104.2, R104.3
    """
    request_body = body or WorkspaceExportRequest()

    service = WorkspaceExportService(org_id=tenant.org_id)
    export = await service.initiate_export(
        user_id=tenant.user_id,
        categories=request_body.categories,
    )
    return export


@router.get(
    "/{export_id}",
    response_model=WorkspaceExportResponse,
    summary="Get export job status",
    description=(
        "Returns the current status of an export job. "
        "When status is 'completed', the download_url field "
        "contains a signed URL to download the export file."
    ),
)
async def get_export_status(
    export_id: UUID,
    tenant: TenantContextDep,
) -> WorkspaceExportResponse:
    """Get the status of a workspace export job.

    Returns the export record including status and download URL
    (when completed). Requires any authenticated workspace member.

    Returns 404 if not found or belongs to different org.
    """
    service = WorkspaceExportService(org_id=tenant.org_id)
    try:
        export = await service.get_export(export_id)
        return export
    except ExportNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export job not found",
        )
