"""Shared tenant-scoped cost gate for synchronous generation dispatch.

The polling worker and the legacy synchronous ``GenerationEngine`` path both
use this boundary. A caller must provide trusted organization and job context;
the gate reserves the estimated cost before invoking the provider and releases
an active reservation unless the complete operation finalizes successfully.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from backend import cost_ledger

# These are conservative local estimates until provider pricing is persisted in
# the database. Both direct and queued generation use this same estimator when
# a caller does not already have a persisted estimate.
_MODEL_BASE_COST_USD = {
    "sd15": 0.02,
    "sdxl": 0.04,
    "sdxl-turbo": 0.02,
    "flux-dev": 0.05,
    "flux2-dev": 0.06,
    "wan-2.1": 0.15,
    "wan-2.1-t2v": 0.15,
    "thunder-h3": 0.20,
}
_TYPE_MULTIPLIER = {
    "image_generation": 1.0,
    "video_generation": 3.0,
    "image_upscale": 1.0,
    "image_edit": 1.25,
    "workflow_execution": 1.0,
}


def estimate_generation_cost(model: str, steps: int, generation_type: str) -> float:
    """Return a positive server-side estimate for a generation request.

    The estimate is intentionally deterministic so it can be persisted on the
    job before execution and independently recomputed by a trusted caller. A
    client may choose a model and step count, but cannot choose the resulting
    organization budget or bypass this calculation.
    """
    try:
        normalized_steps = int(steps)
    except (TypeError, ValueError) as exc:
        raise ValueError("steps must be a positive integer") from exc
    if normalized_steps <= 0:
        raise ValueError("steps must be a positive integer")

    base = _MODEL_BASE_COST_USD.get(model, 0.05)
    multiplier = _TYPE_MULTIPLIER.get(generation_type, 1.0)
    estimate = base * max(normalized_steps, 1) / 20 * multiplier
    return round(max(estimate, 0.001), 4)


def execute_with_cost_gate[T](
    *,
    org_id: str,
    job_id: str,
    operation: str,
    provider: str,
    estimated_cost_usd: float,
    execute: Callable[[], T],
    actual_cost: Callable[[T, float], float] | None = None,
) -> T:
    """Run one operation through reservation, execution, and settlement.

    Reservation is atomic and occurs before ``execute`` is called. If execution
    or finalization fails, the active reservation is released in ``finally``.
    A successful finalization changes the reservation status to ``finalized``;
    finalized reservations are never released a second time.
    """
    if not org_id:
        raise ValueError("org_id is required before provider execution")
    if not job_id:
        raise ValueError("job_id is required before provider execution")
    if not operation:
        raise ValueError("operation is required before provider execution")
    if not math.isfinite(estimated_cost_usd) or estimated_cost_usd <= 0:
        raise ValueError("estimated_cost_usd must be a finite positive number")

    reservation = cost_ledger.reserve_cost(
        org_id,
        estimated_cost_usd,
        operation=operation,
        job_id=job_id,
        provider=provider,
    )
    try:
        result = execute()
        resolved_cost = (
            actual_cost(result, estimated_cost_usd)
            if actual_cost is not None
            else estimated_cost_usd
        )
        if not math.isfinite(resolved_cost) or resolved_cost < 0:
            raise ValueError("actual cost must be a finite non-negative number")
        cost_ledger.finalize_cost(reservation.reservation_id, resolved_cost)
        return result
    finally:
        if reservation.status == "active":
            cost_ledger.release_reservation(
                reservation.reservation_id,
                reason="generation_failure_or_cancellation",
            )
