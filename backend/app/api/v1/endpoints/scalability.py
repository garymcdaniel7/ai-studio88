"""Scalability Architecture Verification API endpoints.

Provides an endpoint for querying the scalability verification status
of the platform architecture.

Routes:
    GET /scalability/status → 200 (current verification status)

Access: Authenticated users.

Validates: Requirements R91.1, R91.3, R91.4, R76.8, R76.10
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import CurrentUserIDDep
from app.schemas.scalability import ScalabilityStatusResponse
from app.services.scalability_verification_service import (
    ScalabilityVerificationService,
)

router = APIRouter(prefix="/scalability", tags=["scalability"])


@router.get(
    "/status",
    response_model=ScalabilityStatusResponse,
    summary="Get scalability architecture verification status",
    description=(
        "Returns the current verification status of all scalability architecture "
        "properties: user-GPU independence, job transport replaceability, backend "
        "statelessness, and scaling documentation. Also includes component scaling "
        "strategy (horizontal vs vertical) per system component."
    ),
)
async def get_scalability_status(
    current_user_id: CurrentUserIDDep,
) -> ScalabilityStatusResponse:
    """Get scalability architecture verification status.

    Verifies:
    - User growth independent of GPU scaling (R91.1, R76.8)
    - Job transport replaceable without API contract change (R91.3, R76.10)
    - Backend stateless behind load balancer (R7.5)
    - Horizontal vs vertical scaling documented per component (R91.4)

    Returns:
        ScalabilityStatusResponse with all properties and component scaling info.
    """
    service = ScalabilityVerificationService()
    return service.get_scalability_status()
