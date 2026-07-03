"""FastAPI dependency injection providers.

All shared dependencies live here. Use Depends() in route handlers.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.security import decode_supabase_jwt, extract_user_id
from app.db.session import get_db_session

logger = get_logger(__name__)


# =============================================================================
# Settings
# =============================================================================

SettingsDep = Annotated[Settings, Depends(get_settings)]


# =============================================================================
# Database
# =============================================================================

DBSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


# =============================================================================
# Authentication
# =============================================================================

async def get_current_user_id(
    authorization: Annotated[str | None, Header()] = None,
    settings: SettingsDep = None,  # type: ignore[assignment]
) -> str:
    """Extract and validate the authenticated user ID from the Bearer token.

    Raises:
        401: If token is missing or invalid
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not authorization:
        raise credentials_exception

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise credentials_exception

    token = parts[1]
    try:
        payload = decode_supabase_jwt(token)
        user_id = extract_user_id(payload)
        return user_id
    except (JWTError, ValueError) as exc:
        logger.warning("auth_failed", reason=str(exc))
        raise credentials_exception from exc


CurrentUserIDDep = Annotated[str, Depends(get_current_user_id)]


async def get_current_org_id(
    user_id: CurrentUserIDDep,
    db: DBSessionDep,
) -> UUID:
    """Resolve the organisation ID for the authenticated user.

    For multi-tenant systems, each user belongs to exactly one organisation
    (or can switch between orgs — extend this as needed).

    Raises:
        403: If user has no organisation
    """
    # TODO: query org_members table to get user's org_id
    # For now, return a placeholder that will fail gracefully
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Organisation context not available",
    )


CurrentOrgIDDep = Annotated[UUID, Depends(get_current_org_id)]


# =============================================================================
# Pagination
# =============================================================================

class PaginationParams:
    """Standard pagination query parameters."""

    def __init__(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> None:
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="limit must be between 1 and 100",
            )
        if offset < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="offset must be >= 0",
            )
        self.limit = limit
        self.offset = offset


PaginationDep = Annotated[PaginationParams, Depends(PaginationParams)]
