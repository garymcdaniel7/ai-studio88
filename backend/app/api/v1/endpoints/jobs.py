"""GPU Job management endpoints.

Jobs represent generation or training tasks dispatched to GPU workers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, status

from app.schemas.job import JobCreate, JobResponse

if TYPE_CHECKING:
    from uuid import UUID

    from app.core.dependencies import CurrentUserIDDep, DBSessionDep, PaginationDep

router = APIRouter()


@router.get("", response_model=list[JobResponse])
async def list_jobs(db: DBSessionDep, user_id: CurrentUserIDDep, pagination: PaginationDep) -> Any:
    """List GPU jobs for the current organisation."""
    return []


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=JobResponse)
async def submit_job(
    payload: JobCreate,
    db: DBSessionDep,
    user_id: CurrentUserIDDep,
) -> Any:
    """Submit a generation or training job to the GPU queue.

    Returns 202 Accepted — the job is queued asynchronously.
    Poll /jobs/{job_id} or subscribe to Supabase Realtime for status updates.
    """
    # TODO: implement JobService.submit()
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not yet implemented")


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID, db: DBSessionDep, user_id: CurrentUserIDDep) -> Any:
    """Get current status and results for a GPU job."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: UUID, db: DBSessionDep, user_id: CurrentUserIDDep) -> Any:
    """Request cancellation of a queued or running job."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
