"""Independent Verification API endpoints.

Routes:
    POST   /verification/run                     → 202 Accepted (run automated verification)
    GET    /verification/status                   → 200 (coverage summary)
    POST   /verification/evidence                 → 201 Created (record manual evidence)
    GET    /verification/evidence/{requirement_id} → 200 (evidence for requirement)

Access: Admin or Owner only — verification is a platform operations concern.

Requirements: R82.1, R82.2, R82.3, R82.4, R82.5, R82.6
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import DBSessionDep, PaginationDep, TenantContextDep
from app.core.rbac import AdminDep
from app.schemas.verification import (
    RunAutomatedVerificationRequest,
    VerificationEvidenceCreateRequest,
    VerificationEvidenceListResponse,
    VerificationEvidenceResponse,
    VerificationRunResponse,
    VerificationStatusResponse,
)
from app.services.verification_service import (
    EvidenceNotFoundError,
    IndependentVerificationService,
    VerificationError,
    VerificationMethod,
)

router = APIRouter(prefix="/verification", tags=["verification"])


@router.post(
    "/run",
    response_model=VerificationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run automated verification",
    description=(
        "Execute automated test suites and record verification evidence "
        "per requirement. Returns 202 with run summary. "
        "Automated tests alone are insufficient for PRODUCTION classification — "
        "independent verification is also required (R82.3)."
    ),
)
async def run_automated_verification(
    request: RunAutomatedVerificationRequest,
    db: DBSessionDep,
    tenant: AdminDep,
) -> VerificationRunResponse:
    """Trigger automated verification suite.

    Requires: Admin or Owner role (platform operations).
    """
    service = IndependentVerificationService(db)

    try:
        result = await service.run_automated_verification(
            feature_name=request.feature_name,
            verifier_identity=f"automated_test_suite (triggered by {tenant.email or tenant.user_id})",
        )
    except VerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
        ) from exc

    await db.commit()
    return VerificationRunResponse(**result)


@router.get(
    "/status",
    response_model=VerificationStatusResponse,
    summary="Get verification coverage status",
    description=(
        "Return verification coverage summary across all tracked requirements. "
        "Shows which requirements have automated tests, independent verification, "
        "and which meet the independence requirement for PRODUCTION classification."
    ),
)
async def get_verification_status(
    db: DBSessionDep,
    tenant: AdminDep,
    feature_name: str | None = None,
) -> VerificationStatusResponse:
    """Get verification coverage across all requirements.

    Requires: Admin or Owner role.
    """
    service = IndependentVerificationService(db)

    try:
        result = await service.get_verification_status(feature_name=feature_name)
    except VerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.message,
        ) from exc

    return VerificationStatusResponse(**result)


@router.post(
    "/evidence",
    response_model=VerificationEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record verification evidence",
    description=(
        "Record a manual verification evidence entry (human review, "
        "Hermes inspection, or adversarial test). This provides the "
        "independent verification required alongside automated tests "
        "for PRODUCTION classification (R82.1, R82.3, R82.6)."
    ),
)
async def record_verification_evidence(
    request: VerificationEvidenceCreateRequest,
    db: DBSessionDep,
    tenant: AdminDep,
) -> VerificationEvidenceResponse:
    """Record manual verification evidence.

    Requires: Admin or Owner role.
    """
    service = IndependentVerificationService(db)

    try:
        result = await service.record_evidence(
            requirement_id=request.requirement_id,
            feature_name=request.feature_name,
            method=request.method,
            evidence_location=request.evidence_location,
            evidence_type=request.evidence_type,
            passed=request.passed,
            verifier_identity=request.verifier_identity,
            notes=request.notes,
        )
    except VerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
        ) from exc

    await db.commit()
    return VerificationEvidenceResponse(**result)


@router.get(
    "/evidence/{requirement_id}",
    response_model=VerificationEvidenceListResponse,
    summary="Get evidence for a requirement",
    description=(
        "Retrieve all verification evidence records for a specific requirement. "
        "Returns paginated list ordered by verification date (newest first)."
    ),
)
async def get_evidence_for_requirement(
    requirement_id: str,
    db: DBSessionDep,
    tenant: AdminDep,
    pagination: PaginationDep,
) -> VerificationEvidenceListResponse:
    """Get all verification evidence for a requirement.

    Requires: Admin or Owner role.
    """
    service = IndependentVerificationService(db)

    try:
        result = await service.get_evidence_for_requirement(
            requirement_id=requirement_id,
            limit=pagination.limit,
            offset=pagination.offset,
        )
    except VerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.message,
        ) from exc

    return VerificationEvidenceListResponse(**result)
