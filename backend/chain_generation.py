"""Motion Director Chain Generation — P5 Graph Composer.

A Chain is an ordered sequence of Beat jobs that fire as a Motion Director
pipeline with carry-forward. The chain is atomic at the cost gate level:
either all beats get jobs or none do. Idempotent by chain-level key.

Chain Lifecycle:
    QUEUED         → All beats accepted, jobs being dispatched
    APPROVAL_WAIT  → Waiting on cost-gate human approval
    IN_PROGRESS    → At least one beat executing
    COMPLETED      → All beats completed
    FAILED         → One or more beats fatally failed (chain dead)
    CANCELLED      → User cancelled

Beat States (per job):
    QUEUED → EXECUTING → COMPLETED | FAILED | CANCELLED
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from backend.batch_generation import _resolve_worker_type, UnknownModelError

# =============================================================================
# Valid H3 Frame Grid (17k+5)
# =============================================================================

VALID_H3_FRAME_COUNTS: set[int] = {226, 243, 260, 277}


# =============================================================================
# Chain / Beat States
# =============================================================================


class ChainState(StrEnum):
    QUEUED = "queued"
    APPROVAL_WAIT = "approval_wait"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BeatState(StrEnum):
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# =============================================================================
# Exceptions
# =============================================================================


class ChainError(Exception):
    """Generic chain validation/operation error."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ChainNotFoundError(ChainError):
    def __init__(self, chain_id: str):
        super().__init__(f"Chain '{chain_id}' not found")


class InvalidBeatError(ChainError):
    """A beat failed semantic validation."""

    def __init__(self, beat_index: int, reason: str):
        self.beat_index = beat_index
        self.reason = reason
        super().__init__(f"Beat[{beat_index}]: {reason}")


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class BeatJob:
    """One beat in a chain — a single H3/GPU job with chain metadata."""

    job_id: str
    beat_index: int
    model_ref: str
    task_type: str
    prompt_sections: dict[str, str]
    ref_image_id: str | None
    frame_count: int
    frame_rate: int
    pipeline_config: dict[str, Any] = field(default_factory=dict)

    status: BeatState = BeatState.QUEUED
    prior_beat_id: str | None = None
    next_beat_id: str | None = None
    output_asset_id: str | None = None
    estimated_gpu_seconds: float = 0.0
    actual_gpu_seconds: float | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "beat_index": self.beat_index,
            "model_ref": self.model_ref,
            "task_type": self.task_type,
            "prompt_sections": self.prompt_sections,
            "ref_image_id": self.ref_image_id,
            "frame_count": self.frame_count,
            "frame_rate": self.frame_rate,
            "pipeline_config": self.pipeline_config,
            "status": self.status.value,
            "output_asset_id": self.output_asset_id,
            "estimated_gpu_seconds": self.estimated_gpu_seconds,
            "actual_gpu_seconds": self.actual_gpu_seconds,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Chain:
    """A chain of Beat jobs for Motion Director pipeline."""

    chain_id: str
    org_id: str
    user_id: str
    label: str
    pipeline: str
    idempotency_key: str

    status: ChainState = ChainState.QUEUED
    beats: list[BeatJob] = field(default_factory=list)
    approval_url: str | None = None

    total_estimated_gpu_seconds: float = 0.0
    total_estimated_cost_usd: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "org_id": self.org_id,
            "label": self.label,
            "pipeline": self.pipeline,
            "status": self.status.value,
            "total_estimated_gpu_seconds": self.total_estimated_gpu_seconds,
            "total_estimated_cost_usd": self.total_estimated_cost_usd,
            "approval_url": self.approval_url,
            "jobs": [b.to_dict() for b in self.beats],
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# =============================================================================
# In-Memory Store (production: replace with DB)
# =============================================================================

_chain_store: dict[str, Chain] = {}


def _idempotency_store() -> dict[str, str]:
    """Return a shared dict mapping idempotency_key → chain_id.

    Lives alongside _chain_store; production moves to DB unique constraint.
    """
    if not hasattr(_idempotency_store, "_store"):
        _idempotency_store._store = {}  # type: ignore[attr-defined]
    return _idempotency_store._store  # type: ignore[attr-defined]


# =============================================================================
# Cost Estimation (server-side, client estimate ignored)
# =============================================================================


def _estimate_beat_cost(
    model_ref: str,
    steps: int | None,
    width: int,
    height: int,
    frame_count: int | None,
) -> float:
    """Server-computed GPU-seconds for one beat.

    Based on model class, resolution, and frame count (for video).
    Client-supplied estimated_gpu_seconds is NOT used.
    """
    normalized = model_ref.lower().replace("-", "_")

    # Base GPU-seconds per model class
    model_gpu_base: dict[str, float] = {
        "krea2": 8.0,
        "krea2_turbo": 4.0,
        "flux_dev": 12.0,
        "flux2_dev": 15.0,
        "flux2_klein": 6.0,
        "h3_video": 180.0,  # H3 per segment baseline
        "h3_turbo": 90.0,
        "wan": 300.0,
    }
    base = model_gpu_base.get(normalized, 12.0)

    # Scale by resolution (compared to 1024x1024 baseline = ~1MP)
    megapixels = (width * height) / 1_048_576
    resolution_factor = max(0.25, megapixels)

    # Scale by steps (image models only; video models use fixed steps)
    step_factor = 1.0
    if steps is not None and normalized not in ("h3_video", "h3_turbo", "wan"):
        step_factor = max(0.5, steps / 20.0)

    # Scale by frame count (video only)
    frame_factor = 1.0
    if frame_count is not None and normalized in ("h3_video", "h3_turbo", "wan"):
        frame_factor = frame_count / 243.0  # Baseline: 243 frames

    return round(base * resolution_factor * step_factor * frame_factor, 2)


def _estimate_cost_usd(gpu_seconds: float) -> float:
    """Convert GPU-seconds to USD at current provider rate.

    Approximate: Thunder Compute H3 pricing ~$0.000144/sec ($0.52/hr).
    """
    return round(gpu_seconds * 0.000144, 4)


# =============================================================================
# Validation
# =============================================================================


def _validate_beats(beats: list[dict[str, Any]]) -> list[InvalidBeatError]:
    """Run all beat validations and return a list of errors (empty = valid)."""
    errors: list[InvalidBeatError] = []

    if not beats:
        errors.append(InvalidBeatError(-1, "Chain must have at least one beat"))
        return errors

    # Contiguous beat_index from 0
    for i, beat in enumerate(beats):
        index = beat.get("beat_index", i)
        if index != i:
            errors.append(
                InvalidBeatError(i, f"Expected beat_index={i}, got {index}")
            )

    # Segment 0: ref_image_id required
    if beats[0].get("ref_image_id") is None:
        errors.append(
            InvalidBeatError(0, "Segment 0 must have a non-null ref_image_id")
        )

    # Segments 1+: ref_image_id must be null
    for beat in beats[1:]:
        idx = beat.get("beat_index", 0)
        if beat.get("ref_image_id") is not None:
            errors.append(
                InvalidBeatError(
                    idx,
                    "Segments 1..n must pass null for ref_image_id"
                    " (chain carries forward prior output)",
                )
            )

    # Frame count validation
    for beat in beats:
        idx = beat.get("beat_index", 0)
        fc = beat.get("frame_count")
        if fc is not None and fc not in VALID_H3_FRAME_COUNTS:
            errors.append(
                InvalidBeatError(
                    idx,
                    f"frame_count={fc} not in valid H3 grid: {sorted(VALID_H3_FRAME_COUNTS)}",
                )
            )

    # Validate model exists
    for beat in beats:
        idx = beat.get("beat_index", 0)
        model = beat.get("model_ref", "")
        try:
            _resolve_worker_type(model)
        except UnknownModelError:
            errors.append(
                InvalidBeatError(idx, f"Unknown model_ref '{model}'")
            )

    return errors


# =============================================================================
# Chain Operations
# =============================================================================


def submit_chain(
    org_id: str,
    user_id: str,
    label: str,
    pipeline: str,
    beats_data: list[dict[str, Any]],
    idempotency_key: str,
) -> Chain:
    """Create a new chain with validated beats.

    Idempotent: same idempotency_key returns existing chain.
    Validates all beats atomically before creating any jobs.
    """
    # Check idempotency
    store = _idempotency_store()
    if idempotency_key:
        existing_id = store.get(idempotency_key)
        if existing_id:
            chain = _chain_store.get(existing_id)
            if chain:
                return chain

    # Validate all beats
    errors = _validate_beats(beats_data)
    if errors:
        raise ChainError(
            "Beat validation failed: " + "; ".join(e.message for e in errors)
        )

    chain_id = f"chain-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)

    total_gpu_seconds = 0.0

    # Create BeatJob records
    jobs: list[BeatJob] = []
    for i, data in enumerate(beats_data):
        gpu_sec = _estimate_beat_cost(
            model_ref=data.get("model_ref", ""),
            steps=data.get("steps"),
            width=data.get("width", 768),
            height=data.get("height", 1152),
            frame_count=data.get("frame_count"),
        )
        total_gpu_seconds += gpu_sec

        job = BeatJob(
            job_id=f"job-{uuid.uuid4().hex[:12]}",
            beat_index=i,
            model_ref=data.get("model_ref", ""),
            task_type=data.get("task_type", "i2v"),
            prompt_sections=data.get("prompt_sections", {}),
            ref_image_id=data.get("ref_image_id"),
            frame_count=data.get("frame_count", 243),
            frame_rate=data.get("frame_rate", 24),
            pipeline_config=data.get("pipeline_config", {}),
            estimated_gpu_seconds=gpu_sec,
            prior_beat_id=jobs[-1].job_id if jobs else None,
            next_beat_id=None,
            created_at=now,
        )
        jobs.append(job)

    # Set forward links
    for i in range(len(jobs) - 1):
        jobs[i].next_beat_id = jobs[i + 1].job_id

    total_cost_usd = _estimate_cost_usd(total_gpu_seconds)

    # ── Cost gate ($50 hard cap) ──────────────────────────────────────────────
    # Temporary guard until full budget system lands.
    COST_THRESHOLD_USD: float = 50.0
    status: ChainState = ChainState.QUEUED
    approval_url: str | None = None
    if total_cost_usd > COST_THRESHOLD_USD:
        status = ChainState.APPROVAL_WAIT
        approval_url = f"/api/v1/approvals/chain/{chain_id}"

    chain = Chain(
        chain_id=chain_id,
        org_id=org_id,
        user_id=user_id,
        label=label,
        pipeline=pipeline,
        idempotency_key=idempotency_key,
        status=status,
        beats=jobs,
        total_estimated_gpu_seconds=total_gpu_seconds,
        total_estimated_cost_usd=total_cost_usd,
        approval_url=approval_url,
        created_at=now,
    )

    # Store
    _chain_store[chain_id] = chain
    if idempotency_key:
        store[idempotency_key] = chain_id

    return chain


def get_chain(chain_id: str) -> Chain | None:
    """Retrieve a chain by ID."""
    return _chain_store.get(chain_id)


def get_chains_by_org(
    org_id: str,
    limit: int = 20,
    offset: int = 0,
    state: str | None = None,
) -> tuple[list[Chain], int]:
    """List chains for an org, sorted by created_at descending."""
    chains = [
        c for c in _chain_store.values()
        if c.org_id == org_id
    ]
    if state:
        chains = [c for c in chains if c.status.value == state]
    chains.sort(key=lambda c: c.created_at, reverse=True)
    total = len(chains)
    return chains[offset:offset + limit], total


def cancel_chain(chain_id: str) -> Chain | None:
    """Cancel a chain and all its QUEUED/EXECUTING beats."""
    chain = _chain_store.get(chain_id)
    if not chain:
        return None
    if chain.status in (ChainState.COMPLETED, ChainState.CANCELLED, ChainState.FAILED):
        return chain  # Idempotent — already terminal
    for beat in chain.beats:
        if beat.status in (BeatState.QUEUED, BeatState.EXECUTING):
            beat.status = BeatState.CANCELLED
    chain.status = ChainState.CANCELLED
    return chain