"""AI Studio — Application entry point.

Run with:
    uv run uvicorn backend.main:app --reload

This module serves as the bridge between the existing working endpoints
(Supabase-backed, flat-file approach) and the new layered app/ scaffold.

Configuration is validated at import time via the Settings class.
In production/staging, the process will refuse to start if critical
settings are missing, placeholder, or unsafe.

Endpoints:
    GET  /          → liveness (always 200)
    GET  /ready     → readiness with capability breakdown
    GET  /projects  → list projects
    GET  /talent    → list talent
    POST /talent    → create talent
    /api/v1/...     → layered architecture
"""

from __future__ import annotations

import logging as _logging
import os as _os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv as _load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Load .env BEFORE importing settings so env vars are available
_load_dotenv(override=True)

from backend.app.core.auth_policy import get_auth_policy  # noqa: E402
from backend.app.core.config import get_settings  # noqa: E402
from backend.app.core.readiness import router as readiness_router  # noqa: E402
from backend.auth import AuthUser, require_auth  # noqa: E402
from backend.database import create_talent, get_projects, get_talent  # noqa: E402
from backend.tenant_context import TenantValidationError, validate_org_id  # noqa: E402

# =============================================================================
# Validated Configuration
# =============================================================================
# This call validates the environment. In production/staging, the process
# will crash here with clear error messages if configuration is unsafe.
_settings = get_settings()
# Validate the same policy used by request middleware before accepting traffic.
get_auth_policy(_settings)
_logger = _logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start and stop process-owned background work without duplicate tasks."""
    from backend.infrastructure.thunder_watch import (
        start_thunder_watch_scheduler,
        stop_thunder_watch_scheduler,
    )

    try:
        await start_thunder_watch_scheduler(_settings)
        yield
    finally:
        try:
            await stop_thunder_watch_scheduler()
        except Exception as exc:
            # Shutdown must not mask the original application exit.
            _logger.warning("thunder_watch_scheduler_shutdown_failed: %s", type(exc).__name__)


# =============================================================================
# Application
# =============================================================================

app = FastAPI(
    title="AI Studio API",
    description="AI content production platform",
    version=_settings.app_version,
    docs_url="/docs" if not _settings.is_production else None,
    redoc_url="/redoc" if not _settings.is_production else None,
    lifespan=lifespan,
)

_allowed_origins = _settings.allowed_origins_list

# Write SSH key from env var if provided (for Railway/cloud deployments)
_ssh_key_content = _os.getenv("SSH_PRIVATE_KEY", "")
if _ssh_key_content and not _os.path.exists(_os.path.expanduser("~/.ssh/id_ed25519")):
    _ssh_dir = _os.path.expanduser("~/.ssh")
    _os.makedirs(_ssh_dir, mode=0o700, exist_ok=True)
    _key_path = _os.path.join(_ssh_dir, "id_ed25519")
    with open(_key_path, "w") as _f:
        _f.write(_ssh_key_content)
        if not _ssh_key_content.endswith("\n"):
            _f.write("\n")
    _os.chmod(_key_path, 0o600)

# Middleware is added in reverse of effective execution order. Starlette runs
# CORS first, then AuthMiddleware, then OrgIdInjectionGuard, followed by the
# request-context/request-id layers and finally the route handler.
from backend.app.core.middleware import (  # noqa: E402
    AuthMiddleware,
    OrgIdInjectionGuard,
    RequestIdMiddleware,
)
from backend.app.core.request_context import RequestContextMiddleware  # noqa: E402

app.add_middleware(RequestIdMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(OrgIdInjectionGuard)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With", "X-Request-ID"],
)

# Global exception handlers — ensures all errors follow standard format
from backend.app.core.error_handlers import register_error_handlers  # noqa: E402

register_error_handlers(app)

# Mount readiness/liveness probes (GET /health, GET /ready, GET /ready/capabilities)
app.include_router(readiness_router)

# Public Supabase Auth entry points (Google login, callback proxy, logout proxy)
from backend.auth_router import router as auth_router  # noqa: E402

app.include_router(auth_router)

# Chain Generation (Motion Director)
from backend.chain_generation_router import router as chain_router  # noqa: E402

app.include_router(chain_router)

# Start Ise background health monitor
try:
    from backend.aios.obaluaye.background import start_background_monitor
    start_background_monitor()
except Exception:
    pass  # Non-critical — Ise monitor is optional

# Start Ise UAT scheduler (runs Playwright tests every hour)
try:
    from backend.aios.obaluaye.uat_runner import start_uat_scheduler
    start_uat_scheduler(interval_seconds=3600)
except Exception:
    pass  # Non-critical — UAT scheduler is optional


# =============================================================================
# Existing working endpoints (Supabase direct)
# =============================================================================


@app.get("/", tags=["ops"])
def root():
    """Root liveness probe (alias for /health)."""
    return {"status": "ok"}


def _native_org_id(user: AuthUser) -> str:
    """Return a validated organization or the canonical membership error."""
    try:
        return validate_org_id(user.org_id)
    except TenantValidationError as exc:
        raise HTTPException(
            status_code=403,
            detail="Active workspace membership required",
            headers={"X-Error-Code": "WORKSPACE_MEMBERSHIP_REQUIRED"},
        ) from exc


@app.get("/projects", tags=["projects"])
def projects(user: AuthUser = Depends(require_auth)):
    """List projects belonging to the authenticated organization."""
    return get_projects(_native_org_id(user)).data


@app.get("/talent", tags=["talent"])
def talent(user: AuthUser = Depends(require_auth)):
    """List AI talent belonging to the authenticated organization."""
    return get_talent(_native_org_id(user)).data


@app.post("/talent", tags=["talent"])
def add_talent(talent_data: dict, user: AuthUser = Depends(require_auth)):
    """Create AI talent attributed to the authenticated organization."""
    try:
        result = create_talent(talent_data, _native_org_id(user))
        return result.data
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# =============================================================================
# Mount all domain routers via the centralized registry
# =============================================================================
# Previously ~250 lines of repeated try/except/include_router blocks. Now
# consolidated into a data-driven registry (backend/app/core/router_registry.py).
# Route set is identical: 494 router endpoints + the main.py-native endpoints
# defined below. Verified via OpenAPI path comparison.

from backend.app.core.router_registry import register_routers  # noqa: E402

register_routers(app)
