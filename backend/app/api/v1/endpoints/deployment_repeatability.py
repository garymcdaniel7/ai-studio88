"""Deployment Repeatability API endpoints.

Provides endpoints for querying deployment stability classification,
viewing verification history, and triggering new verification runs.

Routes:
    GET   /release/repeatability       → 200 (current classification + history)
    POST  /release/repeatability/run   → 201 (trigger a new verification run)

Access: Authenticated users (platform operators in practice).

Validates: Requirements R109.1, R109.2, R109.3, R109.4, R109.5, R82.7, R82.8
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import CurrentUserIDDep
from app.schemas.deployment_repeatability import (
    DeploymentRepeatabilityResponse,
    DeploymentVerificationRunResponse,
)
from app.services.deployment_repeatability_service import (
    DeploymentRepeatabilityService,
    VerificationRunError,
)

router = APIRouter(prefix="/release", tags=["release"])


@router.get(
    "/repeatability",
    response_model=DeploymentRepeatabilityResponse,
    summary="Get deployment repeatability classification",
    description=(
        "Returns the current deployment stability classification, success rate, "
        "and recent verification history. Classification is 'repeatable_and_stable' "
        "only when 3+ consecutive successful verifications have been recorded."
    ),
)
async def get_repeatability_status(
    current_user_id: CurrentUserIDDep,
) -> DeploymentRepeatabilityResponse:
    """Get deployment repeatability status and classification.

    Returns:
        DeploymentRepeatabilityResponse with classification, metrics,
        and recent history.

    Per R109.2: deployment architecture is classified as
    "demonstrated but unstable" until repeatability is independently proven.
    """
    service = DeploymentRepeatabilityService()
    return service.get_repeatability_status()


@router.post(
    "/repeatability/run",
    response_model=DeploymentVerificationRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run deployment verification",
    description=(
        "Triggers a full deployment verification run. Checks frontend build, "
        "backend lint/compilation, and suppressed build checks. Records the "
        "result and updates the stability classification."
    ),
)
async def run_deployment_verification(
    current_user_id: CurrentUserIDDep,
) -> DeploymentVerificationRunResponse:
    """Execute a deployment verification run.

    Runs all verification checks and records the result. Updates the
    repeatability classification based on the new result.

    Returns:
        DeploymentVerificationRunResponse with the new record and
        updated classification.

    Raises:
        500: If verification infrastructure fails.
    """
    service = DeploymentRepeatabilityService()

    try:
        result = await service.run_verification()
    except VerificationRunError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.message,
        )

    return result
