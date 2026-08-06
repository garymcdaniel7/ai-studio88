"""Readiness and liveness probes — Story 117.

GET /health  — Liveness: "Is the process alive?" (always 200 if accepting TCP)
GET /ready   — Readiness: "Can this instance serve traffic?" (checks required capabilities)
GET /ready/capabilities — Detailed capability breakdown with evidence

Liveness is always 200 if the process responds.
Readiness checks all required capabilities with bounded timeouts.
Missing routers, failed configs, unreachable databases → ready=false.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["ops"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Liveness probe.

    Returns 200 if the process is alive and accepting connections.
    Does NOT check downstream dependencies — that's what /ready is for.
    This endpoint MUST remain fast and dependency-free.
    """
    return {"status": "ok"}


@router.get("/ready")
def readiness_check() -> JSONResponse:
    """Readiness probe with capability-aware checks.

    Performs live connectivity verification on all required capabilities
    with bounded timeouts. Returns:
        200: All required capabilities are READY (or acceptably DEGRADED).
        503: One or more required capabilities are unavailable.

    Response body always includes capability details (no secrets).
    Checks are cached for 30s to prevent thundering herd on rapid polling.
    """
    from backend.app.core.capability_readiness import compute_readiness, run_all_checks

    results = run_all_checks()
    summary = compute_readiness(results)

    status_code = 200 if summary["ready"] else 503
    return JSONResponse(content=summary, status_code=status_code)


@router.get("/ready/capabilities")
def capabilities_detail() -> JSONResponse:
    """Detailed capability report with evidence.

    Lists each capability with its live-verified state, latency,
    evidence, and required/optional classification.
    Useful for debugging which services are available and why.
    """
    from backend.app.core.capability_readiness import compute_readiness, run_all_checks

    results = run_all_checks()
    summary = compute_readiness(results)

    status_code = 200 if summary["ready"] else 503
    return JSONResponse(content=summary, status_code=status_code)
