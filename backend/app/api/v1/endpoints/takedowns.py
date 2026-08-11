"""Public Takedown Report and Appeal endpoints.

Routes:
    POST /api/v1/takedowns              → 201 (submit takedown report)
    POST /api/v1/takedowns/{case_id}/appeal → 200 (submit appeal)

These are PUBLIC-FACING endpoints. The report intake endpoint does NOT
require authentication — external reporters can submit complaints.
The appeal endpoint requires the case_id (acts as a token).

Validates: Requirements R40.1, R40.2, R40.7, A2-005
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import DBSessionDep
from app.core.logging import get_logger
from app.schemas.rights_case import (
    TakedownAppealRequest,
    TakedownReportRequest,
    TakedownReportResponse,
)
from app.services.rights_case_service import (
    CaseNotFoundError,
    InvalidCaseTransitionError,
    RightsCaseService,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/takedowns",
    tags=["takedowns"],
)


@router.post(
    "",
    response_model=TakedownReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_takedown_report(
    body: TakedownReportRequest,
    db: DBSessionDep,
) -> TakedownReportResponse:
    """Submit a takedown/rights complaint report.

    This is a PUBLIC endpoint — no authentication required.
    External reporters can submit complaints about content.

    Creates a case record with status 'received' and returns a case_id.
    CSAM reports are auto-escalated to critical priority with immediate
    action_required status.

    Requirements: R40.1, R40.2, A2-005
    """
    service = RightsCaseService(db=db)

    # Build reporter_contact from request
    reporter_contact = {
        "email": body.reporter_email,
    }
    if body.reporter_name:
        reporter_contact["name"] = body.reporter_name

    case = await service.create_case(
        case_type=body.complaint_type.value,
        reporter_contact=reporter_contact,
        content_url_or_id=body.content_url_or_id,
        description=body.description,
        evidence_urls=body.evidence_urls if body.evidence_urls else None,
    )

    logger.info(
        "takedown_report_submitted",
        case_id=str(case.id),
        complaint_type=body.complaint_type.value,
    )

    return TakedownReportResponse(
        case_id=case.id,
        status=case.status,
        message="Your report has been received and will be reviewed.",
    )


@router.post(
    "/{case_id}/appeal",
    response_model=TakedownReportResponse,
)
async def submit_takedown_appeal(
    case_id: UUID,
    body: TakedownAppealRequest,
    db: DBSessionDep,
) -> TakedownReportResponse:
    """Submit an appeal for a takedown action (R40.7).

    Users whose content was restricted or removed can submit an appeal
    which reopens the case for review.

    Requirements: R40.7
    """
    service = RightsCaseService(db=db)

    try:
        case = await service.submit_appeal(
            case_id=case_id,
            appellant_email=body.appellant_email,
            reason=body.reason,
            evidence_urls=body.evidence_urls if body.evidence_urls else None,
        )
    except CaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
            headers={"X-Error-Code": "CASE_NOT_FOUND"},
        )
    except InvalidCaseTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        ) from exc

    return TakedownReportResponse(
        case_id=case.id,
        status=case.status,
        message="Your appeal has been submitted and will be reviewed.",
    )
