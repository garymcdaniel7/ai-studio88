"""Job API endpoints — submission, claiming, heartbeat, completion, and listing.

Routes:
    POST   /jobs              → 202 Accepted (submit a new job)
    GET    /jobs              → 200 (list jobs with pagination)
    GET    /jobs/{job_id}     → 200 (get a single job)
    POST   /jobs/{job_id}/cancel    → 200 (cancel a job)
    POST   /jobs/claim        → 200 or 204 (claim next job — worker endpoint)
    POST   /jobs/{job_id}/heartbeat → 200 (extend lease — worker endpoint)
    POST   /jobs/{job_id}/complete  → 200 (mark completed — worker endpoint)
    POST   /jobs/{job_id}/fail      → 200 (mark failed — worker endpoint)

Requirements: R21.1, R21.3, R21.4, R21.5, R21.8, R64.1, R64.3
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.core.rbac import EditorDep, ViewerDep
from app.schemas.job import (
    JobCancel,
    JobCreate,
    JobListResponse,
    JobResponse,
)
from app.services.job_service import (
    DEFAULT_LEASE_DURATION_SECONDS,
    JobNotCancellableError,
    JobService,
    NoActiveLeaseError,
    StaleWorkerError,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


# =============================================================================
# Request/Response Schemas for Worker Endpoints
# =============================================================================


class JobClaimRequest(BaseModel):
    """Request schema for claiming the next queued job."""

    worker_identity: str = Field(
        ..., min_length=1, max_length=255,
        description="Identifier for the claiming worker",
    )
    lease_duration_seconds: int = Field(
        default=DEFAULT_LEASE_DURATION_SECONDS,
        ge=60,
        le=14400,
        description="Lease duration in seconds (60-14400)",
    )
    workload_class: str | None = Field(
        default=None,
        description="Optional workload class filter",
    )


class JobClaimResponse(BaseModel):
    """Response schema for a successful job claim."""

    job: JobResponse
    lease_token: UUID
    lease_expiration: datetime
    worker_identity: str

    model_config = {"from_attributes": True}


class HeartbeatRequest(BaseModel):
    """Request schema for heartbeat/lease extension."""

    lease_token: UUID = Field(..., description="Lease token from claim")
    progress_percent: int | None = Field(
        default=None, ge=0, le=100,
        description="Progress percentage (0-100)",
    )
    progress_message: str | None = Field(
        default=None, max_length=500,
        description="Human-readable progress message",
    )
    progress_metadata: dict | None = Field(
        default=None,
        description="Optional structured progress metadata (R21.13)",
    )


class HeartbeatResponse(BaseModel):
    """Response schema for heartbeat."""

    lease_expiration: datetime
    heartbeat_at: datetime


class CompleteRequest(BaseModel):
    """Request schema for marking a job completed."""

    lease_token: UUID = Field(..., description="Lease token from claim")
    cost_usd: float | None = Field(
        default=None, ge=0.0,
        description="Actual cost in USD",
    )
    output_asset_ids: list[UUID] = Field(
        default_factory=list,
        description="UUIDs of output assets",
    )


class FailRequest(BaseModel):
    """Request schema for marking a job failed."""

    lease_token: UUID = Field(..., description="Lease token from claim")
    error_message: str = Field(
        ..., min_length=1, max_length=2000,
        description="Human-readable error description",
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_job(
    body: JobCreate,
    tenant: EditorDep,
    db: DBSessionDep,
) -> JobResponse:
    """Submit a new job for async processing.

    Returns 202 Accepted with the job record. The job is queued for
    processing by a worker.

    Requires: EDITOR role (mutations require editor+).
    org_id is set from TenantContext, never from client.

    Requirements: R21.1, R64.1
    """
    service = JobService(db=db, org_id=tenant.org_id)
    job = await service.submit_job(
        create_schema=body,
        user_id=tenant.user_id,
    )
    return JobResponse.model_validate(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    tenant: ViewerDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
    job_type: str | None = Query(None),
    talent_id: UUID | None = Query(None),
) -> JobListResponse:
    """List jobs for the authenticated workspace with pagination.

    Requires: VIEWER role.
    """
    service = JobService(db=db, org_id=tenant.org_id)
    items, total = await service.list_jobs(
        limit=limit,
        offset=offset,
        status=status_filter,
        job_type=job_type,
        talent_id=talent_id,
    )
    return JobListResponse(
        items=[JobResponse.model_validate(j) for j in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    tenant: ViewerDep,
    db: DBSessionDep,
) -> JobResponse:
    """Get a single job by ID.

    Requires: VIEWER role.
    Returns 404 if not found or belongs to a different org.
    """
    service = JobService(db=db, org_id=tenant.org_id)
    job = await service.get_job(job_id)
    return JobResponse.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: UUID,
    body: JobCancel | None = None,
    tenant: EditorDep = None,
    db: DBSessionDep = None,
) -> JobResponse:
    """Cancel a running or queued job.

    Requires: EDITOR role.
    Returns 409 if job is already in a terminal state.
    """
    service = JobService(db=db, org_id=tenant.org_id)
    try:
        job = await service.cancel_job(job_id)
        return JobResponse.model_validate(job)
    except JobNotCancellableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
        ) from exc


@router.post("/claim", response_model=JobClaimResponse)
async def claim_job(
    body: JobClaimRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> JobClaimResponse | Response:
    """Claim the next queued job (worker endpoint).

    Atomically claims the highest-priority queued job and issues a
    lease_token. Returns 204 No Content if no jobs are available.

    Requires: EDITOR role (workers are authenticated org members).

    Requirements: R21.3, R64.2
    """
    service = JobService(db=db, org_id=tenant.org_id)
    result = await service.claim_job(
        worker_identity=body.worker_identity,
        lease_duration_seconds=body.lease_duration_seconds,
        workload_class=body.workload_class,
    )

    if result is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    job, lease = result
    return JobClaimResponse(
        job=JobResponse.model_validate(job),
        lease_token=lease.lease_token,
        lease_expiration=lease.lease_expiration,
        worker_identity=lease.worker_identity,
    )


@router.post("/{job_id}/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    job_id: UUID,
    body: HeartbeatRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> HeartbeatResponse:
    """Extend a job lease via heartbeat.

    Workers must call heartbeat at intervals <= lease_duration / 3
    to prevent lease expiration.

    Requires: EDITOR role (workers are authenticated).

    Requirements: R21.4, R21.5
    """
    service = JobService(db=db, org_id=tenant.org_id)
    try:
        lease = await service.heartbeat(
            job_id=job_id,
            lease_token=body.lease_token,
            progress_percent=body.progress_percent,
            progress_metadata=body.progress_metadata,
        )
        return HeartbeatResponse(
            lease_expiration=lease.lease_expiration,
            heartbeat_at=lease.heartbeat_at,
        )
    except StaleWorkerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
        ) from exc
    except NoActiveLeaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc


@router.post("/{job_id}/complete", response_model=JobResponse)
async def complete_job(
    job_id: UUID,
    body: CompleteRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> JobResponse:
    """Mark a job as completed and release the lease.

    The caller must present the correct lease_token.

    Requires: EDITOR role.

    Requirements: R21.8
    """
    service = JobService(db=db, org_id=tenant.org_id)
    try:
        job = await service.complete_job(
            job_id=job_id,
            lease_token=body.lease_token,
            output_asset_ids=body.output_asset_ids or None,
        )
        return JobResponse.model_validate(job)
    except StaleWorkerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
        ) from exc
    except NoActiveLeaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc


@router.post("/{job_id}/fail", response_model=JobResponse)
async def fail_job(
    job_id: UUID,
    body: FailRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> JobResponse:
    """Mark a job as failed and release the lease.

    The caller must present the correct lease_token.

    Requires: EDITOR role.
    """
    service = JobService(db=db, org_id=tenant.org_id)
    try:
        job = await service.fail_job(
            job_id=job_id,
            lease_token=body.lease_token,
            error_message=body.error_message,
        )
        return JobResponse.model_validate(job)
    except StaleWorkerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
        ) from exc
    except NoActiveLeaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc
