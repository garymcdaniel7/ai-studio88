"""Campaign management endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, status

from app.schemas.campaign import CampaignCreate, CampaignResponse

if TYPE_CHECKING:
    from uuid import UUID

    from app.core.dependencies import CurrentUserIDDep, DBSessionDep, PaginationDep

router = APIRouter()


@router.get("", response_model=list[CampaignResponse])
async def list_campaigns(
    db: DBSessionDep, user_id: CurrentUserIDDep, pagination: PaginationDep
) -> Any:
    return []


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CampaignResponse)
async def create_campaign(
    payload: CampaignCreate, db: DBSessionDep, user_id: CurrentUserIDDep
) -> Any:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not yet implemented")


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: UUID, db: DBSessionDep, user_id: CurrentUserIDDep) -> Any:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
