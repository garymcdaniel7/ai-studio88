"""Chain Generation API Router — P5 Graph Composer.

Endpoints:
    POST   /api/v1/generate/chain        — Submit a Motion Director chain
    GET    /api/v1/generate/chain/{id}    — Get chain status + per-beat jobs
    GET    /api/v1/generate/chains        — List user's chains
    POST   /api/v1/generate/chain/{id}/cancel — Cancel chain
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import AuthUser, require_auth
from backend.chain_generation import (
    ChainError,
    ChainNotFoundError,
    cancel_chain,
    get_chain,
    get_chains_by_org,
    submit_chain,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/generate", tags=["chain-generation"])


# =============================================================================
# Health / diagnostic endpoint (public)
# =============================================================================


@router.get("/chain-health", include_in_schema=True)
def chain_health():
    """Public probe to verify the chain_generation router loaded."""
    return {"status": "chain_generation_router loaded", "routes": 4}


# =============================================================================
# Request / Response Models
# =============================================================================


class BeatSubmitRequest(BaseModel):
    """One beat in a chain submission."""

    beat_index: int = Field(..., description="Position in sequence (0-indexed)")
    model_ref: str = Field(..., min_length=1, description="Model/checkpoint reference ID")
    task_type: str = Field(default="i2v", pattern=r"^(t2v|i2v|fl2v|r2v)$")
    prompt_sections: dict[str, str] = Field(default_factory=dict)
    ref_image_id: str | None = Field(
        default=None,
        description="Reference image ID (non-null for beat 0 only; null for beats 1..n)",
    )
    frame_count: int = Field(default=243, ge=1, description="Frame count (must be in valid H3 grid: 226, 243, 260, 277)")
    frame_rate: int = Field(default=24, ge=1, le=120)
    width: int = Field(default=768, ge=256, le=4096)
    height: int = Field(default=1152, ge=256, le=4096)
    steps: int | None = Field(default=None, ge=1, le=150, description="Inference steps (None = model default)")
    pipeline_config: dict[str, Any] = Field(default_factory=dict)


class ChainSubmitRequest(BaseModel):
    """Request to submit a Motion Director chain."""

    label: str = Field(..., min_length=1, max_length=256, description="Human-readable chain name")
    pipeline: str = Field(default="motion-director-h3", description="Pipeline routing hint")
    beats: list[BeatSubmitRequest] = Field(
        ..., min_length=1, max_length=100,
        description="Ordered beat array (validated as a Motion Director chain)",
    )
    idempotency_key: str = Field(default="", description="Deduplication key (chain-level)")


class ChainResponse(BaseModel):
    """Response for chain submission and status queries."""

    chain_id: str
    status: str
    label: str
    pipeline: str
    total_estimated_gpu_seconds: float
    total_estimated_cost_usd: float
    approval_url: str | None
    jobs: list[dict[str, Any]]
    created_at: str
    completed_at: str | None = None


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/chain", status_code=201)
def submit_generation_chain(
    request: ChainSubmitRequest,
    user: AuthUser = Depends(require_auth),
):
    """Submit a Motion Director chain of beat jobs.

    Accepts an ordered array of Beat objects, validates every beat against
    H3 / Motion Director constraints, then creates jobs with chain metadata
    (prior_beat_id, next_beat_id) atomically.

    Cost gate at chain level: if total estimated cost exceeds the user's
    remaining budget or requires approval, the chain returns with
    status="approval_wait" and an approval_url — no jobs are dispatched
    until the gate opens.

    Idempotent: same idempotency_key returns existing chain (200, not 201).
    """
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Workspace membership required")

    # Convert Pydantic models to dicts for domain layer
    beats_data = [b.model_dump() for b in request.beats]

    try:
        chain = submit_chain(
            org_id=user.org_id,
            user_id=user.user_id,
            label=request.label,
            pipeline=request.pipeline,
            beats_data=beats_data,
            idempotency_key=request.idempotency_key,
        )
    except ChainError as e:
        raise HTTPException(status_code=422, detail=e.message)

    logger.info(
        "chain_submitted",
        extra={
            "chain_id": chain.chain_id,
            "org_id": user.org_id,
            "user_id": user.user_id,
            "beat_count": len(chain.beats),
            "total_cost": chain.total_estimated_cost_usd,
            "idempotent": bool(request.idempotency_key),
        },
    )

    return chain.to_dict()


@router.get("/chain/{chain_id}")
def get_chain_status(
    chain_id: str,
    user: AuthUser = Depends(require_auth),
):
    """Get chain status with per-beat job details.

    Tenant-scoped: only returns chains belonging to the caller's workspace.
    """
    chain = get_chain(chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")

    if user.org_id and chain.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Chain not found")

    return chain.to_dict()


@router.get("/chains")
def list_chains(
    limit: int = 20,
    offset: int = 0,
    state: str | None = None,
    user: AuthUser = Depends(require_auth),
):
    """List the caller's chains (most recent first).

    Supports filtering by state and pagination.
    """
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Workspace membership required")

    chains, total = get_chains_by_org(
        org_id=user.org_id,
        limit=limit,
        offset=offset,
        state=state,
    )

    return {
        "items": [c.to_dict() for c in chains],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/chain/{chain_id}/cancel")
def cancel_generation_chain(
    chain_id: str,
    user: AuthUser = Depends(require_auth),
):
    """Cancel a chain.

    Marks all QUEUED/EXECUTING beats as CANCELLED.
    Idempotent: cancelling an already-terminal chain is a no-op.
    """
    chain = get_chain(chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")

    if user.org_id and chain.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Chain not found")

    result = cancel_chain(chain_id)
    if not result:
        raise HTTPException(status_code=404, detail="Chain not found")

    logger.info(
        "chain_cancelled",
        extra={"chain_id": chain_id, "org_id": user.org_id},
    )

    return result.to_dict()