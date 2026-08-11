"""Release Gate API endpoints — production gate check execution and approval.

Routes:
    POST   /release/gate/run         → 201 Created (run gate checks)
    GET    /release/gate/{gate_id}   → 200 (get gate status)
    POST   /release/gate/{gate_id}/approve → 200 (approve passing gate)
    POST   /release/gate/{gate_id}/verify-emergency → 200 (verify emergency gate)

Access: Admin or Owner only — these are deployment operations.

Requirements: R83.1, R83.2, R83.6, R83.7, R83.8, R83.9
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.core.rbac import AdminDep
from app.schemas.production_gate import (
    GateType,
    ProductionGateApproveRequest,
    ProductionGateResponse,
    ProductionGateRunRequest,
    ProductionGateStatusResponse,
)
from app.services.production_gate_service import (
    GateNotApprovableError,
    GateNotFoundError,
    ProductionGateError,
    ProductionGateService,
    ReleaseIdentityNotFoundError,
)

router = APIRouter(prefix="/release/gate", tags=["release-gate"])


@router.post(
    "/run",
    response_model=ProductionGateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run production gate checks",
    description=(
        "Execute all required gate checks for a release identity. "
        "For full gates, all 14 checks are evaluated. "
        "For emergency gates, a reduced subset is used with a 24h follow-up deadline."
    ),
)
async def run_gate_checks(
    request: ProductionGateRunRequest,
    db: DBSessionDep,
    tenant: AdminDep,
) -> ProductionGateResponse:
    """Run production gate checks for a release identity.

    Requires: Admin or Owner role (deployment operations).
    """
    service = ProductionGateService(db)

    try:
        result = await service.run_gate_checks(
            release_identity_id=request.release_identity_id,
            gate_type=request.gate_type,
            check_overrides=request.check_overrides,
        )
    except ReleaseIdentityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc
    except ProductionGateError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
        ) from exc

    await db.commit()
    return ProductionGateResponse(**result)


@router.get(
    "/{gate_id}",
    response_model=ProductionGateStatusResponse,
    summary="Get gate status",
    description="Retrieve the current status and check results for a production gate.",
)
async def get_gate_status(
    gate_id: UUID,
    db: DBSessionDep,
    tenant: AdminDep,
) -> ProductionGateStatusResponse:
    """Get the current status of a production gate evaluation.

    Requires: Admin or Owner role.
    """
    service = ProductionGateService(db)

    try:
        result = await service.get_gate_status(gate_id)
    except GateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc

    return ProductionGateStatusResponse(**result)


@router.post(
    "/{gate_id}/approve",
    response_model=ProductionGateResponse,
    summary="Approve production gate",
    description=(
        "Approve a production gate that has all required checks passing. "
        "Records: Release_Identity, evidence links, timestamp, and approving actor."
    ),
)
async def approve_gate(
    gate_id: UUID,
    request: ProductionGateApproveRequest,
    db: DBSessionDep,
    tenant: AdminDep,
) -> ProductionGateResponse:
    """Approve a production gate passage.

    Only gates where all_passed=True can be approved.
    Records the approving actor and evidence links for audit trail.

    Requires: Admin or Owner role.
    """
    service = ProductionGateService(db)

    try:
        result = await service.record_passage(
            gate_id=gate_id,
            approving_actor=tenant.user_id,
            evidence_links=request.evidence_links,
        )
    except GateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc
    except GateNotApprovableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
        ) from exc

    await db.commit()
    return ProductionGateResponse(**result)


@router.post(
    "/{gate_id}/verify-emergency",
    response_model=ProductionGateResponse,
    summary="Verify emergency gate (full checks)",
    description=(
        "Complete full verification for an emergency gate within the 24h deadline. "
        "Re-runs all gate checks and marks the gate as fully verified if all pass."
    ),
)
async def verify_emergency_gate(
    gate_id: UUID,
    db: DBSessionDep,
    tenant: AdminDep,
) -> ProductionGateResponse:
    """Complete full verification of an emergency gate.

    Emergency gates (hotfixes) allow a reduced gate for immediate deployment,
    but require full verification within 24 hours (R83.7).

    Requires: Admin or Owner role.
    """
    service = ProductionGateService(db)

    try:
        result = await service.verify_emergency_gate(gate_id)
    except GateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc
    except ProductionGateError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
        ) from exc

    await db.commit()
    return ProductionGateResponse(**result)
