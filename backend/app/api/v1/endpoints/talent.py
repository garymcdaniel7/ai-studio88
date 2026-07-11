"""AI Talent management endpoints.

AI Talent represents an AI-generated influencer persona. Each talent is
associated with an organisation and can have multiple LoRA models,
campaigns, and generated assets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, status

from app.core.logging import get_logger
from app.schemas.talent import TalentCreate, TalentResponse, TalentUpdate

if TYPE_CHECKING:
    from uuid import UUID

    from app.core.dependencies import CurrentUserIDDep, DBSessionDep, PaginationDep

logger = get_logger(__name__)
router = APIRouter()


@router.get("", summary="List AI talent", response_model=list[TalentResponse])
async def list_talent(
    db: DBSessionDep,
    user_id: CurrentUserIDDep,
    pagination: PaginationDep,
) -> Any:
    """List all AI talent for the current organisation.

    Returns a paginated list of talent records.
    """
    # TODO: implement TalentService.list()
    logger.info("list_talent_called", user_id=user_id)
    return []


@router.post(
    "",
    summary="Create AI talent",
    status_code=status.HTTP_201_CREATED,
    response_model=TalentResponse,
)
async def create_talent(
    payload: TalentCreate,
    db: DBSessionDep,
    user_id: CurrentUserIDDep,
) -> Any:
    """Create a new AI talent persona.

    The talent is scoped to the user's organisation.
    """
    # TODO: implement TalentService.create()
    logger.info("create_talent_called", user_id=user_id, name=payload.name)
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not yet implemented")


@router.get("/{talent_id}", summary="Get AI talent", response_model=TalentResponse)
async def get_talent(
    talent_id: UUID,
    db: DBSessionDep,
    user_id: CurrentUserIDDep,
) -> Any:
    """Get a single AI talent record by ID."""
    # TODO: implement TalentService.get()
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Talent not found")


@router.patch("/{talent_id}", summary="Update AI talent", response_model=TalentResponse)
async def update_talent(
    talent_id: UUID,
    payload: TalentUpdate,
    db: DBSessionDep,
    user_id: CurrentUserIDDep,
) -> Any:
    """Update an AI talent record."""
    # TODO: implement TalentService.update()
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Talent not found")


@router.delete("/{talent_id}", summary="Delete AI talent", status_code=status.HTTP_204_NO_CONTENT)
async def delete_talent(
    talent_id: UUID,
    db: DBSessionDep,
    user_id: CurrentUserIDDep,
) -> None:
    """Soft-delete an AI talent record."""
    # TODO: implement TalentService.delete()
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Talent not found")
