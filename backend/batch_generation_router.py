"""Batch Generation API Router — Story 109.

Exposes durable batch generation as HTTP endpoints. One request creates
a batch + N child variation jobs that persist independently of the browser.

Endpoints:
    POST   /api/v1/generate/batch           — Submit a batch
    GET    /api/v1/generate/batch/{id}       — Get batch status + variations
    GET    /api/v1/generate/batches          — List user's batches
    POST   /api/v1/generate/batch/{id}/cancel — Cancel batch
    POST   /api/v1/generate/batch/{id}/retry  — Retry failed variations
    POST   /api/v1/generate/batch/{id}/retry/{job_id} — Retry single variation
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import AuthUser, require_auth
from backend.batch_generation import (
    BatchError,
    BatchState,
    cancel_batch,
    cancel_variation,
    complete_variation,
    fail_variation,
    get_batch,
    retry_failed,
    retry_single,
    start_variation,
    submit_batch,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/generate", tags=["batch-generation"])


# =============================================================================
# Request / Response Models
# =============================================================================


class BatchSubmitRequest(BaseModel):
    """Request to create a generation batch."""

    prompt: str = Field(..., min_length=1, description="Generation prompt")
    negative_prompt: str = Field(default="", description="Negative prompt")
    model: str = Field(default="flux-dev", description="Model to use")
    variation_count: int = Field(default=4, ge=1, le=50, description="Number of variations")
    width: int = Field(default=1024, ge=256, le=4096)
    height: int = Field(default=1024, ge=256, le=4096)
    steps: int = Field(default=20, ge=1, le=150)
    cfg_scale: float = Field(default=7.0, ge=0.0, le=30.0)
    seeds: list[int] | None = Field(default=None, description="Per-variation seeds")
    idempotency_key: str = Field(default="", description="Deduplication key")


class BatchCancelVariationRequest(BaseModel):
    """Request to cancel a specific variation."""

    job_id: str = Field(..., description="Variation job_id to cancel")


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/batch", status_code=201)
def submit_generation_batch(
    request: BatchSubmitRequest,
    user: AuthUser = Depends(require_auth),
):
    """Submit a durable batch of variation generation jobs.

    Creates one batch record with N child variation jobs atomically.
    Idempotent: same idempotency_key returns existing batch.
    Browser closure does not stop accepted work.

    Returns the batch with all variation details.
    """
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Workspace membership required")

    # Estimate cost per variation (DECISION-REQUIRED: actual cost model)
    cost_per_variation = _estimate_variation_cost(request.model, request.steps)

    try:
        batch = submit_batch(
            org_id=user.org_id,
            user_id=user.user_id,
            variation_count=request.variation_count,
            model=request.model,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            steps=request.steps,
            cfg_scale=request.cfg_scale,
            seeds=request.seeds,
            cost_per_variation_usd=cost_per_variation,
            idempotency_key=request.idempotency_key,
        )
    except BatchError as e:
        raise HTTPException(status_code=422, detail=e.message)

    logger.info(
        "batch_submitted",
        extra={
            "batch_id": batch.batch_id,
            "org_id": user.org_id,
            "user_id": user.user_id,
            "variation_count": request.variation_count,
            "model": request.model,
        },
    )

    return batch.to_dict()


@router.get("/batch/{batch_id}")
def get_batch_status(
    batch_id: str,
    user: AuthUser = Depends(require_auth),
):
    """Get batch status with all variation details.

    Returns full batch record including per-variation state, cost, and output.
    Tenant-scoped: only returns batches belonging to the caller's workspace.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Tenant isolation
    if user.org_id and batch.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Batch not found")

    return batch.to_dict()


@router.get("/batches")
def list_batches(
    limit: int = 20,
    offset: int = 0,
    state: str | None = None,
    user: AuthUser = Depends(require_auth),
):
    """List the caller's batches (most recent first).

    Supports filtering by state and pagination.
    """
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Workspace membership required")

    from backend.batch_generation import _batch_store

    # Filter by org
    batches = [
        b for b in _batch_store.values()
        if b.org_id == user.org_id
    ]

    # Filter by state
    if state:
        batches = [b for b in batches if b.state.value == state]

    # Sort by created_at descending
    batches.sort(key=lambda b: b.created_at, reverse=True)

    # Paginate
    total = len(batches)
    page = batches[offset:offset + limit]

    return {
        "items": [b.to_dict() for b in page],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/batch/{batch_id}/cancel")
def cancel_generation_batch(
    batch_id: str,
    user: AuthUser = Depends(require_auth),
):
    """Cancel a batch.

    Marks all QUEUED children as CANCELLED.
    EXECUTING children are allowed to finish (cannot interrupt GPU work).
    Already-completed children are preserved.
    Idempotent: cancelling an already-cancelled batch is a no-op.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if user.org_id and batch.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Batch not found")

    result = cancel_batch(batch_id)
    if not result:
        raise HTTPException(status_code=404, detail="Batch not found")

    logger.info(
        "batch_cancelled",
        extra={"batch_id": batch_id, "org_id": user.org_id},
    )

    return result.to_dict()


@router.post("/batch/{batch_id}/cancel-variation")
def cancel_single_variation(
    batch_id: str,
    request: BatchCancelVariationRequest,
    user: AuthUser = Depends(require_auth),
):
    """Cancel a single variation within a batch (only if QUEUED)."""
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if user.org_id and batch.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Batch not found")

    result = cancel_variation(batch_id, request.job_id)
    if not result:
        raise HTTPException(
            status_code=409,
            detail="Variation cannot be cancelled (not in QUEUED state)",
        )

    return result.to_dict()


@router.post("/batch/{batch_id}/retry")
def retry_batch_failures(
    batch_id: str,
    user: AuthUser = Depends(require_auth),
):
    """Retry all FAILED/CANCELLED variations in a batch.

    Creates new child jobs for each retryable variation.
    Completed variations are preserved untouched.
    Retry lineage is tracked (parent_job_id, attempt counter).
    """
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if user.org_id and batch.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Batch not found")

    retried = retry_failed(batch_id)
    if not retried:
        raise HTTPException(
            status_code=409,
            detail="No retryable variations found (all completed or still active)",
        )

    logger.info(
        "batch_retry",
        extra={
            "batch_id": batch_id,
            "retried_count": len(retried),
            "org_id": user.org_id,
        },
    )

    return {
        "batch_id": batch_id,
        "retried_count": len(retried),
        "retried_jobs": [v.to_dict() for v in retried],
        "batch": batch.to_dict(),
    }


@router.post("/batch/{batch_id}/retry/{job_id}")
def retry_single_variation(
    batch_id: str,
    job_id: str,
    user: AuthUser = Depends(require_auth),
):
    """Retry a single failed/cancelled variation."""
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if user.org_id and batch.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Batch not found")

    result = retry_single(batch_id, job_id)
    if not result:
        raise HTTPException(
            status_code=409,
            detail="Variation cannot be retried (not in FAILED/CANCELLED state)",
        )

    return {
        "batch_id": batch_id,
        "retried_job": result.to_dict(),
        "batch": batch.to_dict(),
    }


# =============================================================================
# Cost Estimation Helper
# =============================================================================


def _estimate_variation_cost(model: str, steps: int) -> float:
    """Estimate cost per variation based on model and steps.

    DECISION-REQUIRED: These are placeholder estimates.
    In production, this should come from the cost model / provider pricing.
    """
    # Base costs per model (USD per generation at default steps)
    model_costs = {
        "flux-dev": 0.05,
        "flux2-dev": 0.06,
        "flux2-klein": 0.02,
        "sdxl-turbo": 0.01,
        "sd15": 0.02,
    }
    base = model_costs.get(model, 0.05)

    # Scale by steps (more steps = more GPU time)
    step_factor = steps / 20.0
    return round(base * step_factor, 4)
