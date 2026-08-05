"""Readiness and liveness probes.

GET /health  — Liveness: "Is the process alive?" (always 200 if accepting TCP)
GET /ready   — Readiness: "Can this instance serve traffic?" (checks capabilities)

The readiness endpoint reports capability status without exposing secrets.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.app.core.config import CapabilityStatus, get_settings

router = APIRouter(tags=["ops"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Liveness probe.

    Returns 200 if the process is alive and accepting connections.
    Does NOT check downstream dependencies — that's what /ready is for.
    """
    return {"status": "ok"}


@router.get("/ready")
def readiness_check() -> JSONResponse:
    """Readiness probe with capability breakdown.

    Returns:
        200: All critical capabilities are available.
        503: One or more critical capabilities are unavailable.

    Response body always includes capability details (no secrets).
    """
    settings = get_settings()
    summary = settings.get_readiness_summary()

    status_code = 200 if summary["ready"] else 503
    return JSONResponse(content=summary, status_code=status_code)


@router.get("/ready/capabilities")
def capabilities_detail() -> dict:
    """Detailed capability report.

    Lists each capability with its configuration status.
    Useful for debugging which services are available.
    """
    settings = get_settings()
    capabilities = settings.get_capability_status()

    return {
        "profile": settings.app_env,
        "capabilities": {
            cap.name: {
                "status": cap.status.value,
                "message": cap.message,
            }
            for cap in capabilities
        },
        "summary": {
            "total": len(capabilities),
            "ready": sum(1 for c in capabilities if c.status == CapabilityStatus.READY),
            "configured": sum(1 for c in capabilities if c.status == CapabilityStatus.CONFIGURED),
            "degraded": sum(1 for c in capabilities if c.status == CapabilityStatus.DEGRADED),
            "unavailable": sum(1 for c in capabilities if c.status == CapabilityStatus.UNAVAILABLE),
        },
    }
