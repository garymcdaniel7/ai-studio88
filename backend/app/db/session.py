"""Database session management.

Uses SQLAlchemy async engine with PostgreSQL via asyncpg.
Connection pooling is managed here — never create engine outside this module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the async database engine (created once on first call)."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        settings = get_settings()
        # Convert postgres:// DSN to postgresql+asyncpg://
        db_url = (
            str(settings.database_url)
            .replace("postgresql://", "postgresql+asyncpg://", 1)
            .replace("postgres://", "postgresql+asyncpg://", 1)
        )
        _engine = create_async_engine(
            db_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,  # Test connections before use
            echo=settings.is_development,  # Log SQL in dev
        )
        logger.info("database_engine_created", pool_size=settings.database_pool_size)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory (created once on first call)."""
    global _session_factory  # noqa: PLW0603
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session.

    Usage:
        @router.get("/endpoint")
        async def handler(db: DBSessionDep):
            result = await db.execute(select(Model))
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_engine() -> None:
    """Dispose of the database engine. Call on application shutdown."""
    global _engine  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        logger.info("database_engine_closed")
        _engine = None
