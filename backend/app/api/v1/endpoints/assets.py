"""Asset management endpoints (images, videos, audio)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.schemas.asset import AssetResponse

if TYPE_CHECKING:
    from uuid import UUID

    from app.core.dependencies import CurrentUserIDDep, DBSessionDep, PaginationDep

router = APIRouter()


@router.get("", response_model=list[AssetResponse])
async def list_assets(
    db: DBSessionDep, user_id: CurrentUserIDDep, pagination: PaginationDep
) -> Any:
    return []


@router.post("/upload", status_code=status.HTTP_201_CREATED, response_model=AssetResponse)
async def upload_asset(
    file: UploadFile,
    db: DBSessionDep,
    user_id: CurrentUserIDDep,
) -> Any:
    """Upload a file to Backblaze B2 storage.

    Accepts: jpg, png, webp (images), mp4 (video), safetensors (models).
    Max size: 500MB.
    """
    # TODO: implement AssetService.upload()
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not yet implemented")


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: UUID, db: DBSessionDep, user_id: CurrentUserIDDep) -> Any:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(asset_id: UUID, db: DBSessionDep, user_id: CurrentUserIDDep) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
