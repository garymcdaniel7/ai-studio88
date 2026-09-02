"""Storyboard Production Orchestration — Story 110.

One durable production job manages all shots in a storyboard. Individual
shots are child jobs with their own lifecycle, retry, and cancel controls.
Progress survives browser refresh/navigation.

Model:
    ProductionJob (parent)
        ├── ShotJob[0] (child)
        ├── ShotJob[1] (child)
        └── ShotJob[N] (child)

Parent lifecycle:
    queued → running → completed | partial | failed | cancelled

Child lifecycle:
    queued → running → completed | failed | cancelled
    failed → queued (retry)

Rules:
    - Parent completes only when ALL children are terminal
    - Retry targets a single shot (doesn't affect completed siblings)
    - Cancel of parent cancels all non-terminal children
    - Cancel of child doesn't affect siblings
    - Ordering is immutable once production starts
    - Costs aggregate from children to parent
    - Duplicate submission returns existing production (idempotent)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class ProductionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"       # All shots completed
    PARTIAL = "partial"           # Some completed, some failed/cancelled
    FAILED = "failed"             # All shots failed
    CANCELLED = "cancelled"


class ShotJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class ShotJob:
    """A child job for a single storyboard shot."""
    shot_job_id: str = field(default_factory=lambda: f"shot-j-{uuid.uuid4().hex[:10]}")
    production_id: str = ""
    shot_index: int = 0
    prompt: str = ""
    context_package_id: str = ""

    # Status
    status: ShotJobStatus = ShotJobStatus.QUEUED
    attempts: int = 0
    max_attempts: int = 3

    # Output
    output_asset_id: str | None = None

    # Cost
    cost_usd: float = 0.0

    # Timing
    started_at: float | None = None
    completed_at: float | None = None

    # Error
    error: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (ShotJobStatus.COMPLETED, ShotJobStatus.FAILED, ShotJobStatus.CANCELLED)

    @property
    def is_retryable(self) -> bool:
        return self.status == ShotJobStatus.FAILED and self.attempts < self.max_attempts


@dataclass
class ProductionJob:
    """Parent production job for a storyboard."""
    production_id: str = field(default_factory=lambda: f"prod-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    user_id: str = ""
    storyboard_id: str = ""
    context_package_id: str = ""

    # Status
    status: ProductionStatus = ProductionStatus.QUEUED

    # Child shots (ordered)
    shots: list[ShotJob] = field(default_factory=list)

    # Cost (aggregated)
    total_cost_usd: float = 0.0

    # Timing
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None

    # Idempotency
    idempotency_key: str | None = None

    @property
    def shot_count(self) -> int:
        return len(self.shots)

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.shots if s.status == ShotJobStatus.COMPLETED)

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.shots if s.status == ShotJobStatus.FAILED)

    @property
    def progress_pct(self) -> int:
        if not self.shots:
            return 0
        terminal = sum(1 for s in self.shots if s.is_terminal)
        return int((terminal / len(self.shots)) * 100)

    @property
    def all_terminal(self) -> bool:
        return all(s.is_terminal for s in self.shots)


# =============================================================================
# Store
# =============================================================================

_productions: dict[str, ProductionJob] = {}


# =============================================================================
# Production API
# =============================================================================


def create_production(
    org_id: str,
    user_id: str,
    storyboard_id: str,
    context_package_id: str,
    shots: list[dict[str, Any]],
    idempotency_key: str | None = None,
) -> ProductionJob:
    """Create a storyboard production job with child-shot jobs.

    Idempotent: same idempotency_key returns existing production.
    """
    if not org_id or not user_id or not storyboard_id:
        raise ValueError("org_id, user_id, and storyboard_id are required")
    if not shots:
        raise ValueError("At least one shot is required")
    if not context_package_id:
        raise ValueError("context_package_id is required")

    # Idempotency
    if idempotency_key:
        existing = _find_by_idempotency(org_id, idempotency_key)
        if existing:
            return existing

    prod = ProductionJob(
        org_id=org_id,
        user_id=user_id,
        storyboard_id=storyboard_id,
        context_package_id=context_package_id,
        idempotency_key=idempotency_key,
    )

    for i, shot_data in enumerate(shots):
        shot_job = ShotJob(
            production_id=prod.production_id,
            shot_index=i,
            prompt=shot_data.get("prompt", ""),
            context_package_id=shot_data.get("context_package_id", context_package_id),
        )
        prod.shots.append(shot_job)

    _productions[prod.production_id] = prod

    logger.info(
        f"PRODUCTION_CREATED: id={prod.production_id} storyboard={storyboard_id} "
        f"shots={prod.shot_count}"
    )
    return prod


# =============================================================================
# Shot Lifecycle
# =============================================================================


def start_shot(production_id: str, shot_index: int, org_id: str) -> ShotJob:
    """Mark a shot as running."""
    prod = _get_production(production_id, org_id)
    shot = _get_shot(prod, shot_index)

    if shot.status == ShotJobStatus.CANCELLED:
        return shot  # Can't start cancelled

    shot.status = ShotJobStatus.RUNNING
    shot.started_at = time.time()
    shot.attempts += 1

    # Update parent status
    if prod.status == ProductionStatus.QUEUED:
        prod.status = ProductionStatus.RUNNING
        prod.started_at = time.time()

    return shot


def complete_shot(
    production_id: str,
    shot_index: int,
    org_id: str,
    output_asset_id: str,
    cost_usd: float = 0.0,
) -> ShotJob:
    """Mark a shot as completed with output asset."""
    prod = _get_production(production_id, org_id)
    shot = _get_shot(prod, shot_index)

    if shot.status == ShotJobStatus.CANCELLED:
        return shot  # Discard output for cancelled shots

    shot.status = ShotJobStatus.COMPLETED
    shot.output_asset_id = output_asset_id
    shot.cost_usd = cost_usd
    shot.completed_at = time.time()

    # Recalculate parent
    _recalculate_production_status(prod)
    return shot


def fail_shot(production_id: str, shot_index: int, org_id: str, error: str) -> ShotJob:
    """Mark a shot as failed."""
    prod = _get_production(production_id, org_id)
    shot = _get_shot(prod, shot_index)

    if shot.status == ShotJobStatus.CANCELLED:
        return shot

    shot.status = ShotJobStatus.FAILED
    shot.error = error[:500]
    shot.completed_at = time.time()

    _recalculate_production_status(prod)
    return shot


def retry_shot(production_id: str, shot_index: int, org_id: str) -> ShotJob:
    """Retry a failed shot — requeue without affecting completed siblings."""
    prod = _get_production(production_id, org_id)
    shot = _get_shot(prod, shot_index)

    if not shot.is_retryable:
        raise ShotNotRetryable(
            f"Shot {shot_index} not retryable (status={shot.status.value}, attempts={shot.attempts})"
        )

    shot.status = ShotJobStatus.QUEUED
    shot.error = None
    shot.started_at = None
    shot.completed_at = None

    # Parent back to running if it was partial/failed
    if prod.status in (ProductionStatus.PARTIAL, ProductionStatus.FAILED):
        prod.status = ProductionStatus.RUNNING

    logger.info(f"SHOT_RETRIED: prod={production_id} shot={shot_index} attempt={shot.attempts + 1}")
    return shot


# =============================================================================
# Cancel
# =============================================================================


def cancel_shot_job(production_id: str, shot_index: int, org_id: str) -> ShotJob:
    """Cancel a single shot (doesn't affect siblings)."""
    prod = _get_production(production_id, org_id)
    shot = _get_shot(prod, shot_index)

    if shot.is_terminal:
        return shot  # Idempotent for already-terminal

    shot.status = ShotJobStatus.CANCELLED
    shot.completed_at = time.time()

    _recalculate_production_status(prod)
    return shot


def cancel_production(production_id: str, org_id: str) -> ProductionJob:
    """Cancel entire production — cancels all non-terminal children."""
    prod = _get_production(production_id, org_id)

    if prod.status == ProductionStatus.CANCELLED:
        return prod  # Idempotent

    for shot in prod.shots:
        if not shot.is_terminal:
            shot.status = ShotJobStatus.CANCELLED
            shot.completed_at = time.time()

    prod.status = ProductionStatus.CANCELLED
    prod.completed_at = time.time()

    logger.info(f"PRODUCTION_CANCELLED: id={production_id}")
    return prod


# =============================================================================
# Progress & Recovery (reconnect)
# =============================================================================


def get_production_progress(production_id: str, org_id: str) -> dict[str, Any] | None:
    """Get full production progress — the reconnect/recovery endpoint.

    Returns complete server truth for UI reconciliation.
    """
    prod = _productions.get(production_id)
    if not prod or prod.org_id != org_id:
        return None

    return {
        "production_id": prod.production_id,
        "storyboard_id": prod.storyboard_id,
        "status": prod.status.value,
        "progress_pct": prod.progress_pct,
        "completed_count": prod.completed_count,
        "failed_count": prod.failed_count,
        "shot_count": prod.shot_count,
        "total_cost_usd": prod.total_cost_usd,
        "shots": [
            {
                "shot_index": s.shot_index,
                "status": s.status.value,
                "prompt": s.prompt,
                "output_asset_id": s.output_asset_id,
                "cost_usd": s.cost_usd,
                "attempts": s.attempts,
                "error": s.error,
                "is_retryable": s.is_retryable,
            }
            for s in prod.shots
        ],
    }


def list_productions(org_id: str, storyboard_id: str | None = None) -> list[dict[str, Any]]:
    """List productions for an org, optionally filtered by storyboard."""
    results = []
    for prod in _productions.values():
        if prod.org_id != org_id:
            continue
        if storyboard_id and prod.storyboard_id != storyboard_id:
            continue
        results.append({
            "production_id": prod.production_id,
            "storyboard_id": prod.storyboard_id,
            "status": prod.status.value,
            "progress_pct": prod.progress_pct,
            "shot_count": prod.shot_count,
            "total_cost_usd": prod.total_cost_usd,
            "created_at": prod.created_at,
        })
    return results


# =============================================================================
# Internal
# =============================================================================


def _recalculate_production_status(prod: ProductionJob) -> None:
    """Recalculate parent production status from children."""
    if not prod.all_terminal:
        return  # Still in progress

    completed = prod.completed_count
    total = prod.shot_count

    # Aggregate cost
    prod.total_cost_usd = round(sum(s.cost_usd for s in prod.shots), 4)

    if completed == total:
        prod.status = ProductionStatus.COMPLETED
    elif completed > 0:
        prod.status = ProductionStatus.PARTIAL
    else:
        prod.status = ProductionStatus.FAILED

    prod.completed_at = time.time()


def _get_production(production_id: str, org_id: str) -> ProductionJob:
    prod = _productions.get(production_id)
    if not prod or prod.org_id != org_id:
        raise ProductionNotFound(f"Production {production_id} not found")
    return prod


def _get_shot(prod: ProductionJob, shot_index: int) -> ShotJob:
    if shot_index < 0 or shot_index >= len(prod.shots):
        raise ShotNotFound(f"Shot {shot_index} out of range (0-{len(prod.shots)-1})")
    return prod.shots[shot_index]


def _find_by_idempotency(org_id: str, key: str) -> ProductionJob | None:
    for prod in _productions.values():
        if prod.org_id == org_id and prod.idempotency_key == key:
            return prod
    return None


# =============================================================================
# Exceptions
# =============================================================================


class ProductionError(Exception):
    """Base production error."""


class ProductionNotFound(ProductionError):
    """Production not found or cross-tenant."""


class ShotNotFound(ProductionError):
    """Shot index out of range."""


class ShotNotRetryable(ProductionError):
    """Shot cannot be retried."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _productions.clear()
