"""AI Studio — Application entry point.

Run with:
    uv run uvicorn backend.main:app --reload

This module serves as the bridge between the existing working endpoints
(Supabase-backed, flat-file approach) and the new layered app/ scaffold.

Existing endpoints preserved at root level:
    GET  /          → health check
    GET  /projects  → list projects
    GET  /talent    → list talent
    POST /talent    → create talent

New scaffold endpoints mounted at:
    /api/v1/...     → layered architecture (auth-required, in progress)
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.database import get_projects, get_talent, create_talent

# =============================================================================
# Application
# =============================================================================

app = FastAPI(
    title="AI Studio API",
    description="AI content production platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Existing working endpoints (Supabase direct)
# =============================================================================

@app.get("/", tags=["ops"])
def health_check():
    """Liveness probe."""
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

try:
    from backend.creator_os.router import router as creator_os_router

    app.include_router(creator_os_router)
except ImportError as exc:
    import warnings
    warnings.warn(f"Creator OS router not loaded: {exc}", stacklevel=1)

try:
    from backend.autonomous_studio.router import router as studio_router

    app.include_router(studio_router)
except ImportError as exc:
    import warnings
    warnings.warn(f"Autonomous Studio router not loaded: {exc}", stacklevel=1)

try:
    from backend.training.router import router as training_router

    app.include_router(training_router)
except ImportError as exc:
    import warnings
    warnings.warn(f"Training router not loaded: {exc}", stacklevel=1)

try:
    from backend.video.router import router as video_router

    app.include_router(video_router)
except ImportError as exc:
    import warnings
    warnings.warn(f"Video router not loaded: {exc}", stacklevel=1)

try:
    from backend.audio.router import router as audio_router

    app.include_router(audio_router)
except ImportError as exc:
    import warnings
    warnings.warn(f"Audio router not loaded: {exc}", stacklevel=1)

try:
    from backend.performance.router import router as performance_router

    app.include_router(performance_router)
except ImportError as exc:
    import warnings
    warnings.warn(f"Performance router not loaded: {exc}", stacklevel=1)

try:
    from backend.publishing.router import router as publishing_router

    app.include_router(publishing_router)
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

try:
    from backend.infrastructure.generate import router as generate_router

    app.include_router(generate_router)
except ImportError as exc:
    import warnings
    warnings.warn(f"Generate router not loaded: {exc}", stacklevel=1)
