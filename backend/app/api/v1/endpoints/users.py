"""User profile endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, status

from app.core.logging import get_logger
from app.schemas.user import UserResponse

if TYPE_CHECKING:
    from app.core.dependencies import CurrentUserIDDep, DBSessionDep

logger = get_logger(__name__)
router = APIRouter()


@router.get("/me", summary="Get current user", response_model=UserResponse)
async def get_me(
    db: DBSessionDep,
    user_id: CurrentUserIDDep,
) -> Any:
    """Get the profile for the authenticated user."""
    # TODO: implement UserService.get()
    logger.info("get_me_called", user_id=user_id)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
