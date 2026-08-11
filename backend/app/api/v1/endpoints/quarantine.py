"""Quarantine management endpoints for Platform Operators.

Provides read-only access to quarantined records and resolution workflow.
Only users with WORKSPACE_ADMIN trust domain or higher can access.

Requirements: R69.4, R69.5, R69.6
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.dependencies import TenantContext, TenantContextDep, WorkspaceRole
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/platform-admin/quarantine", tags=["platform-admin"])


# =============================================================================
# Schemas
# =============================================================================


class QuarantineEntryResponse(BaseModel):
    """Response schema for a quarantine log entry."""

    id: UUID
    source_table: str
    source_row_id: UUID
    classification: str
    quarantine_reason: str
    quarantine_date: datetime
    resolved_at: datetime | None = None
    resolution: str | None = None
    resolved_by: UUID | None = None
    resolution_evidence: str | None = None
    assigned_org_id: UUID | None = None


class QuarantineListResponse(BaseModel):
    """Paginated list of quarantine entries."""

    items: list[QuarantineEntryResponse]
    total: int
    limit: int
    offset: int


class QuarantineSummaryResponse(BaseModel):
    """Summary counts for quarantine dashboard."""

    total_quarantined: int
    pending_review: int
    eligible_for_purge: int
    resolved: int
    by_table: dict[str, int] = Field(default_factory=dict)


class ResolveQuarantineRequest(BaseModel):
    """Request to resolve a quarantined record."""

    resolution: str = Field(
        ...,
        description="Resolution type: 'assigned', 'system', or 'purged'",
        pattern="^(assigned|system|purged)$",
    )
    assigned_org_id: UUID | None = Field(
        None,
        description="Target org_id (required when resolution='assigned')",
    )
    evidence: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Justification for the resolution decision",
    )


class ResolveQuarantineResponse(BaseModel):
    """Response after resolving a quarantine entry."""

    id: UUID
    resolution: str
    resolved_at: datetime
    resolved_by: UUID
    assigned_org_id: UUID | None = None


# =============================================================================
# Dependencies
# =============================================================================


def require_admin(tenant: TenantContextDep) -> TenantContext:
    """Require at least admin role for quarantine operations."""
    tenant.require_role(WorkspaceRole.ADMIN)
    return tenant


AdminDep = Annotated[TenantContext, Depends(require_admin)]


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/summary", response_model=QuarantineSummaryResponse)
async def get_quarantine_summary(tenant: AdminDep) -> QuarantineSummaryResponse:
    """Get quarantine summary counts for the dashboard.

    Returns aggregate counts of quarantined records by status and table.
    Platform Operators use this to track remediation progress.
    """
    logger.info(
        "quarantine_summary_requested",
        user_id=str(tenant.user_id),
        org_id=str(tenant.org_id),
    )

    # TODO: Replace with real Supabase query when connected
    # For now return empty summary indicating clean state
    return QuarantineSummaryResponse(
        total_quarantined=0,
        pending_review=0,
        eligible_for_purge=0,
        resolved=0,
        by_table={},
    )


@router.get("/entries", response_model=QuarantineListResponse)
async def list_quarantine_entries(
    tenant: AdminDep,
    source_table: str | None = Query(None, description="Filter by source table"),
    classification: str | None = Query(None, description="Filter by classification"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> QuarantineListResponse:
    """List quarantine entries with optional filters.

    Supports filtering by source table and classification status.
    Results are ordered by quarantine_date descending (newest first).
    """
    logger.info(
        "quarantine_entries_listed",
        user_id=str(tenant.user_id),
        source_table=source_table,
        classification=classification,
    )

    # TODO: Replace with real Supabase query
    return QuarantineListResponse(
        items=[],
        total=0,
        limit=limit,
        offset=offset,
    )


@router.get("/entries/{entry_id}", response_model=QuarantineEntryResponse)
async def get_quarantine_entry(
    entry_id: UUID,
    tenant: AdminDep,
) -> QuarantineEntryResponse:
    """Get a single quarantine entry by ID.

    Returns full detail including resolution history if resolved.
    """
    logger.info(
        "quarantine_entry_requested",
        user_id=str(tenant.user_id),
        entry_id=str(entry_id),
    )

    # TODO: Replace with real Supabase query
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Quarantine entry not found",
    )


@router.post(
    "/entries/{entry_id}/resolve",
    response_model=ResolveQuarantineResponse,
    status_code=status.HTTP_200_OK,
)
async def resolve_quarantine_entry(
    entry_id: UUID,
    body: ResolveQuarantineRequest,
    tenant: AdminDep,
) -> ResolveQuarantineResponse:
    """Resolve a quarantined record.

    Resolution types:
    - 'assigned': Assign the row to a specific org (requires assigned_org_id)
    - 'system': Classify the row as system-owned (assigned to system org)
    - 'purged': Approve permanent deletion of the row

    Evidence is required for all resolutions (R69.6).
    """
    from app.services.org_id_backfill import (
        QUARANTINED_UUID,
        SYSTEM_ORG_ID,
        QuarantineResolution,
        OrgIdBackfillService,
    )

    # Validate resolution
    resolution = QuarantineResolution(body.resolution)
    service = OrgIdBackfillService(founder_org_id=tenant.org_id)
    errors = service.validate_resolution(
        resolution=resolution,
        assigned_org_id=body.assigned_org_id,
        evidence=body.evidence,
    )

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(errors),
        )

    logger.info(
        "quarantine_entry_resolved",
        entry_id=str(entry_id),
        resolution=body.resolution,
        resolved_by=str(tenant.user_id),
        assigned_org_id=str(body.assigned_org_id) if body.assigned_org_id else None,
    )

    # TODO: Execute actual resolution against Supabase
    # 1. Update _quarantine_log: set resolved_at, resolution, resolved_by, evidence
    # 2. If 'assigned': UPDATE source_table SET org_id = assigned_org_id WHERE id = source_row_id
    # 3. If 'system': UPDATE source_table SET org_id = SYSTEM_ORG WHERE id = source_row_id
    # 4. If 'purged': DELETE FROM source_table WHERE id = source_row_id

    return ResolveQuarantineResponse(
        id=entry_id,
        resolution=body.resolution,
        resolved_at=datetime.now(UTC),
        resolved_by=tenant.user_id,
        assigned_org_id=body.assigned_org_id,
    )
