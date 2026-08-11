"""Cost API endpoints — summary, reservations, entries, reconciliation.

Routes:
    GET    /costs/summary                    → 200 (cost summary with breakdowns)
    GET    /costs/reservations               → 200 (list reservations, paginated)
    GET    /costs/entries                    → 200 (list cost entries, paginated)
    POST   /costs/reservations               → 201 (create new reservation)
    POST   /costs/reservations/{id}/finalize → 200 (finalize with actual cost)
    POST   /costs/reservations/{id}/release  → 200 (release a reservation)

Requirements: R14.5, R14.6, R14.10, R14.11, R66.3, R66.4, R66.5
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.dependencies import DBSessionDep
from app.core.rbac import EditorDep, ViewerDep
from app.schemas.cost import (
    CostEntryListResponse,
    CostEntryResponse,
    CostReservationCreate,
    CostReservationFinalize,
    CostReservationListResponse,
    CostReservationResponse,
    CostSummaryResponse,
)
from app.services.cost_service import (
    BudgetExceededError,
    CostService,
    LedgerUnavailableError,
)

router = APIRouter(prefix="/costs", tags=["costs"])


# =============================================================================
# Request Schemas
# =============================================================================


class ReleaseRequest(BaseModel):
    """Request schema for releasing a reservation."""

    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Reason for releasing the reservation",
    )


class FinalizeRequest(BaseModel):
    """Request schema for finalizing a reservation with actual cost."""

    actual_amount_usd: Decimal = Field(
        ...,
        ge=Decimal("0"),
        le=Decimal("99999.9999"),
        description="Actual cost incurred (USD)",
    )
    provider_receipt: str | None = Field(
        default=None,
        max_length=500,
        description="Optional provider receipt/reference",
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/summary", response_model=CostSummaryResponse)
async def get_cost_summary(
    tenant: ViewerDep,
    db: DBSessionDep,
) -> CostSummaryResponse:
    """Get cost summary for the authenticated workspace.

    Returns today_spend, month_spend, budgets, and breakdowns
    by provider and classification.

    Requires: VIEWER role.

    Requirements: R14.5
    """
    service = CostService(db=db, org_id=tenant.org_id)
    try:
        summary = await service.get_cost_summary()
        return CostSummaryResponse(
            today_spend_usd=summary["today_spend_usd"],
            month_spend_usd=summary["month_spend_usd"],
            active_reservations_usd=summary["active_reservations_usd"],
            breakdown_by_classification=summary["breakdown_by_classification"],
            breakdown_by_provider=summary["breakdown_by_provider"],
        )
    except LedgerUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        ) from exc


@router.get("/reservations", response_model=CostReservationListResponse)
async def list_reservations(
    tenant: ViewerDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
) -> CostReservationListResponse:
    """List cost reservations for the authenticated workspace.

    Requires: VIEWER role.
    """
    service = CostService(db=db, org_id=tenant.org_id)
    items, total = await service.list_reservations(
        limit=limit,
        offset=offset,
        status_filter=status_filter,
    )
    return CostReservationListResponse(
        items=[CostReservationResponse.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/entries", response_model=CostEntryListResponse)
async def list_entries(
    tenant: ViewerDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    entry_type: str | None = Query(None),
) -> CostEntryListResponse:
    """List cost entries for the authenticated workspace.

    Requires: VIEWER role.
    """
    service = CostService(db=db, org_id=tenant.org_id)
    items, total = await service.list_entries(
        limit=limit,
        offset=offset,
        entry_type_filter=entry_type,
    )
    return CostEntryListResponse(
        items=[CostEntryResponse.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/reservations",
    response_model=CostReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    body: CostReservationCreate,
    tenant: EditorDep,
    db: DBSessionDep,
) -> CostReservationResponse:
    """Create a new cost reservation (atomic budget check + hold).

    Returns 201 on success.
    Returns 402 if budget would be exceeded.
    Returns 503 if the cost ledger is unavailable (fail-safe).

    Requires: EDITOR role.

    Requirements: R14.9, R66.1, R66.2
    """
    service = CostService(db=db, org_id=tenant.org_id)
    try:
        reservation = await service.reserve_cost(
            operation=body.operation,
            estimated_amount_usd=body.reserved_amount_usd,
            job_id=body.job_id,
            provider=body.provider,
            cost_classification=body.cost_classification.value,
            expires_at=body.expires_at,
        )
        return CostReservationResponse.model_validate(reservation)
    except BudgetExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        ) from exc
    except LedgerUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
            headers={"X-Error-Code": "VALIDATION_ERROR"},
        ) from exc


@router.post(
    "/reservations/{reservation_id}/finalize",
    response_model=CostReservationResponse,
)
async def finalize_reservation(
    reservation_id: UUID,
    body: FinalizeRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> CostReservationResponse:
    """Finalize a reservation with the actual cost incurred.

    Releases the reservation hold, records the actual cost, and logs
    a warning if variance exceeds 20%.

    Requires: EDITOR role.

    Requirements: R14.10, R66.3
    """
    service = CostService(db=db, org_id=tenant.org_id)
    try:
        reservation = await service.finalize_cost(
            reservation_id=reservation_id,
            actual_amount_usd=body.actual_amount_usd,
            provider_receipt=body.provider_receipt,
        )
        return CostReservationResponse.model_validate(reservation)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
            headers={"X-Error-Code": "NOT_FOUND"},
        ) from exc
    except LedgerUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        ) from exc


@router.post(
    "/reservations/{reservation_id}/release",
    response_model=CostReservationResponse,
)
async def release_reservation(
    reservation_id: UUID,
    body: ReleaseRequest | None = None,
    tenant: EditorDep = None,
    db: DBSessionDep = None,
) -> CostReservationResponse:
    """Release an active reservation without recording actual cost.

    Used when a job is cancelled or never provisioned.

    Requires: EDITOR role.

    Requirements: R66.3
    """
    service = CostService(db=db, org_id=tenant.org_id)
    reason = body.reason if body else None
    try:
        reservation = await service.release_reservation(
            reservation_id=reservation_id,
            reason=reason,
        )
        return CostReservationResponse.model_validate(reservation)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
            headers={"X-Error-Code": "NOT_FOUND"},
        ) from exc
    except LedgerUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        ) from exc
