"""Publishing Approval Binding API endpoints.

Provides approval binding for publishing packages:
    - POST /api/v1/publishing/approve           — create approval binding
    - GET  /api/v1/publishing/approvals/{id}    — get approval status
    - POST /api/v1/publishing/approvals/{id}/verify — verify still valid

An approval binds to the exact state of: asset checksum, caption, destination,
schedule, targeting, consent state, disclosure settings, and policy state.
Any change to a bound element invalidates the approval.

Requirements: R79.1, R79.2, R79.3, R79.4, R79.5, R79.6
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.core.rbac import EditorDep
from app.schemas.publishing_approval import (
    PublishingApprovalCreateRequest,
    PublishingApprovalResponse,
    PublishingApprovalVerifyRequest,
    PublishingApprovalVerifyResponse,
)
from app.services.publishing_approval_service import PublishingApprovalService

router = APIRouter(prefix="/publishing", tags=["publishing-approval"])


# =============================================================================
# Helper to build response from ORM model
# =============================================================================


def _to_response(record: object) -> PublishingApprovalResponse:
    """Convert a PublishingApprovedPackage ORM instance to a response schema."""
    return PublishingApprovalResponse(
        id=record.id,
        org_id=record.org_id,
        asset_id=record.asset_id,
        asset_checksum=record.asset_checksum,
        caption=record.caption,
        destination=record.destination,
        schedule=record.schedule,
        targeting=record.targeting,
        consent_state=record.consent_state,
        disclosure_settings=record.disclosure_settings,
        policy_state=record.policy_state,
        talent_id=record.talent_id,
        project_id=record.project_id,
        package_hash=record.package_hash,
        approved_by=record.approved_by,
        approved_at=record.approved_at,
        invalidated_at=record.invalidated_at,
        invalidation_reason=record.invalidation_reason,
        is_valid=record.is_valid,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/approve",
    response_model=PublishingApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create publishing approval binding",
    description=(
        "Creates an immutable approval record binding the exact state of all "
        "publishing package elements. Supersedes any previous valid approval "
        "for the same asset."
    ),
)
async def create_publishing_approval(
    request: PublishingApprovalCreateRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> PublishingApprovalResponse:
    """Create a publishing approval binding.

    Binds the exact current state of: asset checksum, caption, destination,
    schedule, targeting, consent state, disclosure settings, and policy state.

    Requires EDITOR role or higher.

    Requirements: R79.1, R79.2
    """
    service = PublishingApprovalService(db=db, tenant=tenant)

    record = await service.create_approval(
        asset_id=request.asset_id,
        asset_checksum=request.asset_checksum,
        caption=request.caption,
        destination=request.destination.model_dump(),
        schedule=request.schedule.model_dump(),
        targeting=request.targeting.model_dump(),
        consent_state=[cs.model_dump() for cs in request.consent_state],
        disclosure_settings=request.disclosure_settings.model_dump(),
        policy_state=request.policy_state.model_dump(),
        talent_id=request.talent_id,
        project_id=request.project_id,
    )

    await db.commit()
    return _to_response(record)


@router.get(
    "/approvals/{approval_id}",
    response_model=PublishingApprovalResponse,
    summary="Get publishing approval status",
    description="Retrieve the current status of a publishing approval binding.",
)
async def get_publishing_approval(
    approval_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> PublishingApprovalResponse:
    """Get a publishing approval record by ID.

    Returns the full approval state including whether it is still valid.

    Requirements: R79.4
    """
    service = PublishingApprovalService(db=db, tenant=tenant)
    record = await service.get_approval(approval_id)
    return _to_response(record)


@router.post(
    "/approvals/{approval_id}/verify",
    response_model=PublishingApprovalVerifyResponse,
    summary="Verify publishing approval against current state",
    description=(
        "Compares the current state of all bound elements against the "
        "approved state. If any element has changed, the approval is "
        "invalidated and the mismatched fields are reported."
    ),
)
async def verify_publishing_approval(
    approval_id: UUID,
    request: PublishingApprovalVerifyRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> PublishingApprovalVerifyResponse:
    """Verify an approval is still valid at publish time.

    Provides current state of all bound elements for comparison against
    the approved snapshot. If any element differs, the approval is
    automatically invalidated.

    Requirements: R79.3, R79.5, R79.6
    """
    service = PublishingApprovalService(db=db, tenant=tenant)

    result = await service.verify_approval(
        approval_id=approval_id,
        current_asset_checksum=request.asset_checksum,
        current_caption=request.caption,
        current_destination=request.destination.model_dump(),
        current_schedule=request.schedule.model_dump(),
        current_targeting=request.targeting.model_dump(),
        current_consent_state=[cs.model_dump() for cs in request.consent_state],
        current_disclosure_settings=request.disclosure_settings.model_dump(),
        current_policy_state=request.policy_state.model_dump(),
    )

    await db.commit()

    return PublishingApprovalVerifyResponse(
        approval_id=result["approval_id"],
        is_valid=result["is_valid"],
        mismatched_fields=result["mismatched_fields"],
        invalidation_reason=result["invalidation_reason"],
        approved_at=result["approved_at"],
        message=result["message"],
    )
