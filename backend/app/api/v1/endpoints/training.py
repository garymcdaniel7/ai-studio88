"""Training Pipeline API endpoints — job submission, estimation, and lifecycle.

Routes:
    POST   /training/jobs           → 202 Accepted (submit training job)
    GET    /training/jobs           → 200 (list training jobs)
    GET    /training/jobs/{job_id}  → 200 (get a training job)
    POST   /training/jobs/{job_id}/cancel → 200 (cancel training job)
    GET    /training/estimate       → 200 (cost estimation)
    POST   /training/jobs/{job_id}/complete → 200 (worker: mark complete)
    POST   /training/jobs/{job_id}/fail    → 200 (worker: mark failed)

Requirements: R35.1, R35.2, R35.3, R35.4, R35.5, R35.6, R35.7, R35.8, R35.10, R35.11
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from app.core.dependencies import DBSessionDep, PaginationDep, TenantContextDep
from app.core.rbac import EditorDep, ViewerDep
from app.schemas.training import (
    TrainingBaseModel,
    TrainingCancelResponse,
    TrainingEstimateResponse,
    TrainingJobCreate,
    TrainingJobListResponse,
    TrainingJobResponse,
)
from app.services.training_pipeline_service import TrainingPipelineService

router = APIRouter(prefix="/training", tags=["training"])


# =============================================================================
# Worker Request Schemas
# =============================================================================


class TrainingCompleteRequest(BaseModel):
    """Request from worker when training completes successfully."""

    model_name: str = Field(
        ..., min_length=1, max_length=200,
        description="Human-readable model name",
    )
    storage_key: str = Field(
        ..., min_length=1, max_length=500,
        description="B2 storage key for the LoRA file",
    )
    checksum_sha256: str = Field(
        ..., min_length=64, max_length=64,
        description="SHA-256 hex digest of the model file",
    )
    file_size_bytes: int = Field(
        ..., ge=1,
        description="Size of the LoRA file in bytes",
    )
    cost_usd: float | None = Field(
        default=None, ge=0,
        description="Actual GPU cost incurred",
    )


class TrainingFailRequest(BaseModel):
    """Request from worker when training fails."""

    error_message: str = Field(
        ..., min_length=1, max_length=2000,
        description="Human-readable failure description",
    )
    timed_out: bool = Field(
        default=False,
        description="Whether the failure was due to 4-hour timeout",
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TrainingJobResponse,
    summary="Submit a LoRA training job",
)
async def submit_training_job(
    data: TrainingJobCreate,
    db: DBSessionDep,
    tenant: EditorDep,
) -> TrainingJobResponse:
    """Submit a new LoRA training job.

    Requires talent_id (owned by requesting org) and a manifest_id
    referencing 10-200 training images. Returns 202 Accepted with the
    queued job record.

    Validates: R35.1, R35.10
    """
    service = TrainingPipelineService(db=db, tenant=tenant)
    job = await service.submit_training_job(data)
    await db.commit()
    return _job_to_response(job)


@router.get(
    "/estimate",
    response_model=TrainingEstimateResponse,
    summary="Estimate training cost",
)
async def estimate_training_cost(
    db: DBSessionDep,
    tenant: ViewerDep,
    base_model: TrainingBaseModel = Query(
        default=TrainingBaseModel.FLUX_DEV,
        description="Base model for training",
    ),
    steps: int = Query(default=1000, ge=100, le=5000),
    resolution: int = Query(default=1024, ge=256, le=2048),
    image_count: int = Query(default=20, ge=10, le=200),
) -> TrainingEstimateResponse:
    """Estimate training cost before submission.

    Returns estimated time and cost based on model type, resolution,
    steps, and current GPU provider rates. No GPU is provisioned.

    Validates: R35.2
    """
    service = TrainingPipelineService(db=db, tenant=tenant)
    return await service.estimate_cost(
        base_model=base_model.value,
        steps=steps,
        resolution=resolution,
        image_count=image_count,
    )


@router.get(
    "/jobs",
    response_model=TrainingJobListResponse,
    summary="List training jobs",
)
async def list_training_jobs(
    db: DBSessionDep,
    tenant: ViewerDep,
    pagination: PaginationDep,
    talent_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> TrainingJobListResponse:
    """List training jobs for the authenticated workspace.

    Supports filtering by talent_id and status, with pagination.
    """
    service = TrainingPipelineService(db=db, tenant=tenant)
    items, total = await service.list_training_jobs(
        limit=pagination.limit,
        offset=pagination.offset,
        talent_id=talent_id,
        job_status=status_filter,
    )
    return TrainingJobListResponse(
        items=[_job_to_response(j) for j in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=TrainingJobResponse,
    summary="Get a training job",
)
async def get_training_job(
    job_id: UUID,
    db: DBSessionDep,
    tenant: ViewerDep,
) -> TrainingJobResponse:
    """Get a training job by ID (org-scoped)."""
    service = TrainingPipelineService(db=db, tenant=tenant)
    job = await service.get_training_job(job_id)
    return _job_to_response(job)


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=TrainingCancelResponse,
    summary="Cancel a training job",
)
async def cancel_training_job(
    job_id: UUID,
    db: DBSessionDep,
    tenant: EditorDep,
) -> TrainingCancelResponse:
    """Cancel a queued or running training job.

    Returns 409 if the job is already completed, failed, or cancelled.

    Validates: R35.5, R35.6
    """
    service = TrainingPipelineService(db=db, tenant=tenant)
    job = await service.cancel_training_job(job_id)
    await db.commit()
    return TrainingCancelResponse(
        id=job.id,
        status=job.status,
        cancelled_at=job.completed_at or datetime.now(UTC),
    )


@router.post(
    "/jobs/{job_id}/complete",
    response_model=TrainingJobResponse,
    summary="Mark training job as completed (worker endpoint)",
)
async def complete_training_job(
    job_id: UUID,
    data: TrainingCompleteRequest,
    db: DBSessionDep,
    tenant: EditorDep,
) -> TrainingJobResponse:
    """Worker endpoint: mark a training job as completed.

    Creates the model record with provenance, links to talent via
    talent_loras association, and updates job status to completed.

    Validates: R35.4, R35.11
    """
    service = TrainingPipelineService(db=db, tenant=tenant)
    job = await service.complete_training_job(
        job_id=job_id,
        model_name=data.model_name,
        storage_key=data.storage_key,
        checksum_sha256=data.checksum_sha256,
        file_size_bytes=data.file_size_bytes,
        cost_usd=data.cost_usd,
    )
    await db.commit()
    return _job_to_response(job)


@router.post(
    "/jobs/{job_id}/fail",
    response_model=TrainingJobResponse,
    summary="Mark training job as failed (worker endpoint)",
)
async def fail_training_job(
    job_id: UUID,
    data: TrainingFailRequest,
    db: DBSessionDep,
    tenant: EditorDep,
) -> TrainingJobResponse:
    """Worker endpoint: mark a training job as failed or timed out.

    The worker calls this when training fails or the 4-hour timeout
    is exceeded. Instance termination must happen in the worker's
    finally block regardless (R35.8).

    Validates: R35.7, R35.8
    """
    service = TrainingPipelineService(db=db, tenant=tenant)
    job = await service.fail_training_job(
        job_id=job_id,
        error_message=data.error_message,
        timed_out=data.timed_out,
    )
    await db.commit()
    return _job_to_response(job)


# =============================================================================
# Response Helper
# =============================================================================


def _job_to_response(job: object) -> TrainingJobResponse:
    """Convert a Job ORM instance to a TrainingJobResponse schema."""
    params = job.parameters or {}
    cancelled_at = None
    if job.status == "cancelled" and job.completed_at:
        cancelled_at = job.completed_at

    return TrainingJobResponse(
        id=job.id,
        org_id=job.org_id,
        talent_id=job.talent_id,
        manifest_id=UUID(params["manifest_id"]) if params.get("manifest_id") else job.id,
        status=job.status,
        base_model=params.get("base_model", "flux-dev"),
        trigger_word=params.get("trigger_word", "ohwx"),
        steps=params.get("steps", 1000),
        rank=params.get("rank", 16),
        learning_rate=params.get("learning_rate", 1e-4),
        resolution=params.get("resolution", 1024),
        progress_percent=job.progress_percent,
        progress_message=None,
        error_message=job.error_message,
        cost_usd=None,
        model_id=UUID(params["model_id"]) if params.get("model_id") else None,
        started_at=job.started_at,
        completed_at=job.completed_at,
        cancelled_at=cancelled_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
