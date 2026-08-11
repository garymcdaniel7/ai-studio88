"""Durable Batch Generation — Story 109.

One server-side batch manages multiple variation jobs. Browser closure does
not stop accepted work. Cancellation, partial success, and retry are all
handled durably.

Batch Lifecycle:
    SUBMITTED   → Batch accepted, child jobs being created
    IN_PROGRESS → At least one child executing
    COMPLETED   → All children completed/cancelled/failed (batch done)
    CANCELLED   → User cancelled entire batch

Child Job States (per variation):
    QUEUED → EXECUTING → COMPLETED | FAILED | CANCELLED

Key Behaviors:
    - One submission creates batch + N child jobs atomically
    - Idempotent: same idempotency_key returns existing batch
    - Cancel: marks all QUEUED children as CANCELLED, active ones finish
    - Retry: targets only FAILED/CANCELLED children, preserves completed
    - Cost: tracked per child and aggregated on batch
    - Assets: each completed child has one authoritative asset
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Batch States
# =============================================================================


class BatchState(StrEnum):
    SUBMITTED = "submitted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ChildState(StrEnum):
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (ChildState.COMPLETED, ChildState.FAILED, ChildState.CANCELLED)

    @property
    def is_retryable(self) -> bool:
        return self in (ChildState.FAILED, ChildState.CANCELLED)


# =============================================================================
# Child Variation Job
# =============================================================================


@dataclass
class VariationJob:
    """A single variation within a batch."""

    job_id: str = field(default_factory=lambda: f"var-{uuid.uuid4().hex[:10]}")
    batch_id: str = ""
    variation_index: int = 0
    state: ChildState = ChildState.QUEUED

    # Per-variation settings (seed differs, others may be shared)
    seed: int = -1
    extra_settings: dict = field(default_factory=dict)

    # Output
    asset_id: str | None = None
    error_message: str | None = None

    # Cost
    cost_estimated_usd: float = 0.0
    cost_actual_usd: float | None = None

    # Retry
    attempt: int = 1
    parent_job_id: str | None = None  # Previous attempt's job_id

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "batch_id": self.batch_id,
            "variation_index": self.variation_index,
            "state": self.state.value,
            "seed": self.seed,
            "asset_id": self.asset_id,
            "error_message": self.error_message,
            "cost_estimated_usd": self.cost_estimated_usd,
            "cost_actual_usd": self.cost_actual_usd,
            "attempt": self.attempt,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


# =============================================================================
# Batch Record
# =============================================================================


@dataclass
class GenerationBatch:
    """A durable batch of variation generation jobs."""

    # Identity
    batch_id: str = field(default_factory=lambda: f"batch-{uuid.uuid4().hex[:10]}")
    idempotency_key: str = ""
    org_id: str = ""
    user_id: str = ""

    # Shared specification
    spec_hash: str = ""             # From canonical generation spec
    context_package_id: str = ""
    model: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg_scale: float = 7.0

    # Children
    variations: list[VariationJob] = field(default_factory=list)
    requested_count: int = 0

    # State
    state: BatchState = BatchState.SUBMITTED

    # Cost aggregate
    total_estimated_usd: float = 0.0
    total_actual_usd: float = 0.0

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None

    # Computed properties
    @property
    def completed_count(self) -> int:
        return sum(1 for v in self.variations if v.state == ChildState.COMPLETED)

    @property
    def failed_count(self) -> int:
        return sum(1 for v in self.variations if v.state == ChildState.FAILED)

    @property
    def cancelled_count(self) -> int:
        return sum(1 for v in self.variations if v.state == ChildState.CANCELLED)

    @property
    def active_count(self) -> int:
        return sum(1 for v in self.variations if not v.state.is_terminal)

    @property
    def progress_pct(self) -> float:
        if not self.variations:
            return 0.0
        terminal = sum(1 for v in self.variations if v.state.is_terminal)
        return round((terminal / len(self.variations)) * 100, 1)

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "org_id": self.org_id,
            "state": self.state.value,
            "requested_count": self.requested_count,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "cancelled_count": self.cancelled_count,
            "active_count": self.active_count,
            "progress_pct": self.progress_pct,
            "total_estimated_usd": self.total_estimated_usd,
            "total_actual_usd": self.total_actual_usd,
            "model": self.model,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "variations": [v.to_dict() for v in self.variations],
        }


# =============================================================================
# Batch Store
# =============================================================================

_batch_store: dict[str, GenerationBatch] = {}
_idempotency_index: dict[str, str] = {}  # key → batch_id


def clear_store() -> None:
    _batch_store.clear()
    _idempotency_index.clear()


def get_batch(batch_id: str) -> GenerationBatch | None:
    return _batch_store.get(batch_id)


# =============================================================================
# Batch Submission (idempotent)
# =============================================================================


class BatchError(Exception):
    def __init__(self, message: str, code: str = "BATCH_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


def submit_batch(
    *,
    org_id: str,
    user_id: str,
    variation_count: int,
    model: str = "flux-dev",
    prompt: str = "",
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    steps: int = 20,
    cfg_scale: float = 7.0,
    seeds: list[int] | None = None,
    cost_per_variation_usd: float = 0.0,
    spec_hash: str = "",
    context_package_id: str = "",
    idempotency_key: str = "",
) -> GenerationBatch:
    """Submit a batch of variation generation jobs.

    Idempotent: same idempotency_key returns existing batch.
    Creates batch + N child VariationJobs atomically.
    """
    if not org_id or not user_id:
        raise BatchError("org_id and user_id required", code="AUTH_REQUIRED")

    if variation_count < 1 or variation_count > 50:
        raise BatchError(
            f"variation_count must be 1-50, got {variation_count}",
            code="INVALID_COUNT",
        )

    # Idempotency check
    if idempotency_key and idempotency_key in _idempotency_index:
        existing_id = _idempotency_index[idempotency_key]
        existing = _batch_store.get(existing_id)
        if existing:
            return existing

    # Create batch
    batch = GenerationBatch(
        idempotency_key=idempotency_key,
        org_id=org_id,
        user_id=user_id,
        model=model,
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        steps=steps,
        cfg_scale=cfg_scale,
        spec_hash=spec_hash,
        context_package_id=context_package_id,
        requested_count=variation_count,
        total_estimated_usd=cost_per_variation_usd * variation_count,
    )

    # Create child jobs
    for i in range(variation_count):
        seed = seeds[i] if seeds and i < len(seeds) else -1
        child = VariationJob(
            batch_id=batch.batch_id,
            variation_index=i,
            seed=seed,
            cost_estimated_usd=cost_per_variation_usd,
        )
        batch.variations.append(child)

    # Persist
    _batch_store[batch.batch_id] = batch
    if idempotency_key:
        _idempotency_index[idempotency_key] = batch.batch_id

    return batch


# =============================================================================
# Child State Transitions
# =============================================================================


def start_variation(batch_id: str, job_id: str) -> VariationJob | None:
    """Mark a variation as EXECUTING."""
    batch = _batch_store.get(batch_id)
    if not batch:
        return None

    for v in batch.variations:
        if v.job_id == job_id and v.state == ChildState.QUEUED:
            v.state = ChildState.EXECUTING
            v.started_at = datetime.now(UTC).isoformat()
            _update_batch_state(batch)
            return v
    return None


def complete_variation(
    batch_id: str,
    job_id: str,
    *,
    asset_id: str,
    cost_actual_usd: float = 0.0,
) -> VariationJob | None:
    """Mark a variation as COMPLETED with its output asset."""
    batch = _batch_store.get(batch_id)
    if not batch:
        return None

    for v in batch.variations:
        if v.job_id == job_id and v.state == ChildState.EXECUTING:
            v.state = ChildState.COMPLETED
            v.asset_id = asset_id
            v.cost_actual_usd = cost_actual_usd
            v.completed_at = datetime.now(UTC).isoformat()
            batch.total_actual_usd += cost_actual_usd
            _update_batch_state(batch)
            return v
    return None


def fail_variation(batch_id: str, job_id: str, *, error: str) -> VariationJob | None:
    """Mark a variation as FAILED."""
    batch = _batch_store.get(batch_id)
    if not batch:
        return None

    for v in batch.variations:
        if v.job_id == job_id and not v.state.is_terminal:
            v.state = ChildState.FAILED
            v.error_message = error
            v.completed_at = datetime.now(UTC).isoformat()
            _update_batch_state(batch)
            return v
    return None


# =============================================================================
# Cancellation
# =============================================================================


def cancel_batch(batch_id: str) -> GenerationBatch | None:
    """Cancel an entire batch.

    Marks all QUEUED children as CANCELLED.
    EXECUTING children are allowed to finish (cannot interrupt GPU work).
    Already-completed children are preserved.
    """
    batch = _batch_store.get(batch_id)
    if not batch:
        return None

    if batch.state == BatchState.CANCELLED:
        return batch  # Idempotent

    for v in batch.variations:
        if v.state == ChildState.QUEUED:
            v.state = ChildState.CANCELLED
            v.completed_at = datetime.now(UTC).isoformat()

    batch.state = BatchState.CANCELLED
    batch.completed_at = datetime.now(UTC).isoformat()
    return batch


def cancel_variation(batch_id: str, job_id: str) -> VariationJob | None:
    """Cancel a single variation (only if QUEUED)."""
    batch = _batch_store.get(batch_id)
    if not batch:
        return None

    for v in batch.variations:
        if v.job_id == job_id and v.state == ChildState.QUEUED:
            v.state = ChildState.CANCELLED
            v.completed_at = datetime.now(UTC).isoformat()
            _update_batch_state(batch)
            return v
    return None


# =============================================================================
# Retry
# =============================================================================


def retry_failed(batch_id: str) -> list[VariationJob]:
    """Retry all FAILED/CANCELLED variations in a batch.

    Creates new child jobs for each retryable variation.
    Completed variations are preserved untouched.
    """
    batch = _batch_store.get(batch_id)
    if not batch:
        return []

    new_jobs: list[VariationJob] = []
    for v in batch.variations:
        if v.state.is_retryable:
            new_child = VariationJob(
                batch_id=batch.batch_id,
                variation_index=v.variation_index,
                seed=v.seed,
                extra_settings=v.extra_settings,
                cost_estimated_usd=v.cost_estimated_usd,
                attempt=v.attempt + 1,
                parent_job_id=v.job_id,
            )
            # Replace in list
            idx = batch.variations.index(v)
            batch.variations[idx] = new_child
            new_jobs.append(new_child)

    if new_jobs:
        batch.state = BatchState.SUBMITTED
        batch.completed_at = None

    return new_jobs


def retry_single(batch_id: str, job_id: str) -> VariationJob | None:
    """Retry a single failed/cancelled variation."""
    batch = _batch_store.get(batch_id)
    if not batch:
        return None

    for i, v in enumerate(batch.variations):
        if v.job_id == job_id and v.state.is_retryable:
            new_child = VariationJob(
                batch_id=batch.batch_id,
                variation_index=v.variation_index,
                seed=v.seed,
                extra_settings=v.extra_settings,
                cost_estimated_usd=v.cost_estimated_usd,
                attempt=v.attempt + 1,
                parent_job_id=v.job_id,
            )
            batch.variations[i] = new_child
            if batch.state in (BatchState.COMPLETED, BatchState.CANCELLED):
                batch.state = BatchState.SUBMITTED
                batch.completed_at = None
            return new_child
    return None


# =============================================================================
# Internal Helpers
# =============================================================================


def _update_batch_state(batch: GenerationBatch) -> None:
    """Update batch state based on child states."""
    if batch.state == BatchState.CANCELLED:
        return  # Don't override explicit cancel

    all_terminal = all(v.state.is_terminal for v in batch.variations)
    any_executing = any(v.state == ChildState.EXECUTING for v in batch.variations)

    if all_terminal:
        batch.state = BatchState.COMPLETED
        batch.completed_at = datetime.now(UTC).isoformat()
    elif any_executing:
        batch.state = BatchState.IN_PROGRESS
