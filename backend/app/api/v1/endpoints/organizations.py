"""Organisation management endpoints."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import CurrentUserIDDep, DBSessionDep, PaginationDep
from app.core.logging import get_logger
from app.schemas.organization import OrganizationCreate, OrganizationResponse

logger = get_logger(__name__)
router = APIRouter()


@router.get("/me", summary="Get current organisation", response_model=OrganizationResponse)
async def get_my_organization(
    db: DBSessionDep,
    user_id: CurrentUserIDDep,
) -> Any:
    """Get the organisation for the authenticated user."""
    # TODO: implement OrganizationService.get_by_user()
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")


@router.post("", summary="Create organisation", status_code=status.HTTP_201_CREATED, response_model=OrganizationResponse)
async def create_organization(
    payload: OrganizationCreate,
    db: DBSessionDep,
    user_id: CurrentUserIDDep,
) -> Any:
    """Create a new organisation. The authenticated user becomes the owner."""
    # TODO: implement OrganizationService.create()
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not yet implemented")
