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

import os as _os

from dotenv import load_dotenv as _load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Load .env BEFORE importing settings so env vars are available
_load_dotenv(override=True)

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.core.readiness import router as readiness_router  # noqa: E402
from backend.database import create_talent, get_projects, get_talent  # noqa: E402

# =============================================================================
# Validated Configuration
# =============================================================================
# This call validates the environment. In production/staging, the process
# will crash here with clear error messages if configuration is unsafe.
_settings = get_settings()

# =============================================================================
# Application
# =============================================================================

app = FastAPI(
    title="AI Studio API",
    description="AI content production platform",
    version=_settings.app_version,
    docs_url="/docs" if not _settings.is_production else None,
    redoc_url="/redoc" if not _settings.is_production else None,
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With", "X-Request-ID"],
)

# Request context middleware — binds request_id, org_id, user_id to structlog
from backend.app.core.request_context import RequestContextMiddleware  # noqa: E402

app.add_middleware(RequestContextMiddleware)

# Request ID middleware — generates UUID v4 and adds X-Request-ID to all responses
from backend.app.core.middleware import RequestIdMiddleware  # noqa: E402

app.add_middleware(RequestIdMiddleware)

# Global exception handlers — ensures all errors follow standard format
from backend.app.core.error_handlers import register_error_handlers  # noqa: E402

register_error_handlers(app)

# Mount readiness/liveness probes (GET /health, GET /ready, GET /ready/capabilities)
app.include_router(readiness_router)

# Public Supabase Auth entry points (Google login, callback proxy, logout proxy)
from backend.auth_router import router as auth_router  # noqa: E402

app.include_router(auth_router)

# Import startup failure registry for router load tracking (Story 117)
from backend.app.core.capability_readiness import register_startup_failure as _reg_failure

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


@app.get("/projects", tags=["projects"])
def projects():
    """List all projects from Supabase."""
    return get_projects().data


@app.get("/talent", tags=["talent"])
def talent():
    """List all AI talent from Supabase."""
    return get_talent().data


@app.post("/talent", tags=["talent"])
def add_talent(talent_data: dict):
    """Create a new AI talent record in Supabase."""
    try:
        result = create_talent(talent_data)
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Mount all domain routers via the centralized registry
# =============================================================================
# Previously ~250 lines of repeated try/except/include_router blocks. Now
# consolidated into a data-driven registry (backend/app/core/router_registry.py).
# Route set is identical: 494 router endpoints + the main.py-native endpoints
# defined below. Verified via OpenAPI path comparison.

from backend.app.core.router_registry import register_routers  # noqa: E402

register_routers(app)
