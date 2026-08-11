"""Image Generation API endpoints.

POST /api/v1/generate/image — Submit an image generation request.
Returns HTTP 202 Accepted with job_id within 2 seconds.

Requirements: R12.1, R12.2, R12.3
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.schemas.generation import ImageGenerateRequest, ImageGenerateResponse
from app.services.generation_service import GenerationService

router = APIRouter(prefix="/generate", tags=["generation"])


@router.post(
    "/image",
    response_model=ImageGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit image generation",
    description=(
        "Submit an image generation request. Creates a job with status 'queued' "
        "and returns HTTP 202 within 2 seconds. The job is dispatched asynchronously "
        "to a compute provider meeting the model's VRAM and cost requirements."
    ),
)
async def generate_image(
    request: ImageGenerateRequest,
    db: DBSessionDep,
    tenant: TenantContextDep,
) -> ImageGenerateResponse:
    """Submit an image generation request.

    Creates a job record with status "queued" and returns 202 Accepted
    with the job_id. Generation is performed asynchronously by the worker
    layer via the job leasing system.

    - Prompt: 1-2000 characters, whitespace-only rejected
    - Dimensions: 256-2048px per side, multiples of 64
    - Model: one of flux_dev, sdxl_turbo, sd15
    - talent_id: must belong to authenticated org if provided

    Validates: R12.1, R12.2, R12.3, R12.6, R12.7, R12.8, R12.9, R12.10
    """
    service = GenerationService(db=db, tenant=tenant)
    job = await service.submit_image_generation(request)

    return ImageGenerateResponse(
        job_id=job.id,
        status=job.status,
        estimated_duration_seconds=None,
        estimated_cost_usd=None,
    )
