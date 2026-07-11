"""AI Studio — FastAPI application entry point.

Application lifecycle:
  startup  → configure logging, connect DB, init services
  request  → auth middleware → router → service → DB/storage
  shutdown → close DB engine, flush queues
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import close_engine, get_engine

settings = get_settings()
configure_logging()
logger = get_logger(__name__)


# =============================================================================
# Lifespan (startup / shutdown)
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Application startup and shutdown lifecycle."""
    logger.info(
        "application_starting",
        name=settings.app_name,
        version=settings.app_version,
        env=settings.app_env,
    )

    # Warm up database connection pool
    get_engine()
    logger.info("database_pool_ready")

    yield

    # Graceful shutdown
    logger.info("application_shutting_down")
    await close_engine()
    logger.info("application_stopped")


# =============================================================================
# Application factory
# =============================================================================


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="AI Studio API",
        description="Commercial AI content production platform",
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    _register_routers(app)

    # ── Exception handlers ────────────────────────────────────────────────────
    _register_exception_handlers(app)

    return app


def _register_routers(app: FastAPI) -> None:
    """Register all API routers."""
    from app.api.v1 import router as v1_router

    app.include_router(v1_router, prefix=settings.api_prefix)


def _register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers."""

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "code": "INTERNAL_ERROR"},
        )


# =============================================================================
# Application instance
# =============================================================================

app = create_app()


# =============================================================================
# Health / readiness endpoints (outside versioned prefix)
# =============================================================================


@app.get("/health", tags=["ops"])
async def health_check() -> dict[str, Any]:
    """Basic liveness probe. Returns 200 if the process is running."""
    return {
        "status": "ok",
        "version": settings.app_version,
        "env": settings.app_env,
    }


@app.get("/ready", tags=["ops"])
async def readiness_check() -> dict[str, Any]:
    """Readiness probe. Checks database connectivity."""
    from sqlalchemy import text

    try:
        from app.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        logger.warning("readiness_db_check_failed", error=str(exc))
        db_status = "error"

    is_ready = db_status == "ok"
    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if is_ready else "not_ready",
            "checks": {"database": db_status},
        },
    )
