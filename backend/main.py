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
# Mount v1 scaffold (new layered endpoints)
# =============================================================================
# These endpoints require auth and are progressively implemented.
# Import is guarded so the app still starts even if scaffold deps are incomplete.

try:
    from backend.api_v1 import router as v1_router

    app.include_router(v1_router, prefix="/api/v1")
except ImportError as exc:
    import warnings

    warnings.warn(f"v1 router not loaded: {exc}", stacklevel=1)
    _reg_failure("api_v1 router", str(exc))

try:
    from backend.creator_os.router import router as creator_os_router

    app.include_router(creator_os_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Creator OS router not loaded: {exc}", stacklevel=1)
    _reg_failure("creator_os router", str(exc))

try:
    from backend.autonomous_studio.router import router as studio_router

    app.include_router(studio_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Autonomous Studio router not loaded: {exc}", stacklevel=1)
    _reg_failure("autonomous_studio router", str(exc))

try:
    from backend.training.router import router as training_router

    app.include_router(training_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Training router not loaded: {exc}", stacklevel=1)
    _reg_failure("training router", str(exc))

try:
    from backend.video.router import router as video_router

    app.include_router(video_router)

    # Initialize the canonical video provider registry (Story 143)
    try:
        from backend.video.registry import setup_video_providers
        setup_video_providers()
    except Exception as _vr_exc:
        import warnings
        warnings.warn(f"Video provider registry init failed: {_vr_exc}", stacklevel=1)

except ImportError as exc:
    import warnings

    warnings.warn(f"Video router not loaded: {exc}", stacklevel=1)
    _reg_failure("video router", str(exc))

try:
    from backend.audio.router import router as audio_router

    app.include_router(audio_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Audio router not loaded: {exc}", stacklevel=1)
    _reg_failure("audio router", str(exc))

try:
    from backend.performance.router import router as performance_router

    app.include_router(performance_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Performance router not loaded: {exc}", stacklevel=1)

try:
    from backend.publishing.oauth import router as oauth_router
    from backend.publishing.router import router as publishing_router

    app.include_router(publishing_router)
    app.include_router(oauth_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Publishing router not loaded: {exc}", stacklevel=1)

try:
    from backend.brain.router import router as brain_router

    app.include_router(brain_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Brain router not loaded: {exc}", stacklevel=1)

try:
    from backend.production_intelligence.router import router as pi_router

    app.include_router(pi_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Production Intelligence router not loaded: {exc}", stacklevel=1)

try:
    from backend.asset_intelligence.router import router as ai_router

    app.include_router(ai_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Asset Intelligence router not loaded: {exc}", stacklevel=1)

try:
    from backend.cinematic.router import router as cinematic_router

    app.include_router(cinematic_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Cinematic router not loaded: {exc}", stacklevel=1)

try:
    from backend.company.router import router as company_router

    app.include_router(company_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Company router not loaded: {exc}", stacklevel=1)

try:
    from backend.object_intelligence.router import router as object_intelligence_router

    app.include_router(object_intelligence_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Object Intelligence router not loaded: {exc}", stacklevel=1)

try:
    from backend.infrastructure.router import router as infrastructure_router

    app.include_router(infrastructure_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Infrastructure router not loaded: {exc}", stacklevel=1)
    _reg_failure("infrastructure router", str(exc))

try:
    from backend.infrastructure.generate import router as generate_router

    app.include_router(generate_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Generate router not loaded: {exc}", stacklevel=1)
    _reg_failure("generate router", str(exc))

try:
    from backend.aios.gateway import router as aios_router
    from backend.aios.mcp.server import router as mcp_router

    app.include_router(aios_router)
    app.include_router(mcp_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"AIOS Gateway router not loaded: {exc}", stacklevel=1)

try:
    from backend.aios.approval_router import router as approval_router

    app.include_router(approval_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"AIOS Approval router not loaded: {exc}", stacklevel=1)

try:
    from backend.batch_generation_router import router as batch_gen_router

    app.include_router(batch_gen_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Batch generation router not loaded: {exc}", stacklevel=1)

try:
    from backend.provenance.router import router as provenance_router

    app.include_router(provenance_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Provenance router not loaded: {exc}", stacklevel=1)

try:
    from backend.lifecycle.router import router as lifecycle_router

    app.include_router(lifecycle_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Lifecycle router not loaded: {exc}", stacklevel=1)

try:
    from backend.notifications.notification_router import router as notifications_router

    app.include_router(notifications_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Notifications router not loaded: {exc}", stacklevel=1)
    _reg_failure("notifications router", str(exc))

try:
    from backend.social_analytics.router import router as social_analytics_router

    app.include_router(social_analytics_router)
except ImportError as exc:
    import warnings

    warnings.warn(f"Social Analytics router not loaded: {exc}", stacklevel=1)
    _reg_failure("social_analytics router", str(exc))
