"""Pydantic schemas for Asset lifecycle management.

Validates: Requirements R11.3, R11.5, R11.6, R11.9, R11.10
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from backend.app.schemas.base import BaseSchema, PaginatedResponse, TimestampedSchema


# =============================================================================
# Constants
# =============================================================================


class AssetType(StrEnum):
    """Supported asset types."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    MODEL = "model"
    TRAINING = "training"


# MIME types allowed per asset type (R11.9)
ALLOWED_CONTENT_TYPES: dict[str, list[str]] = {
    "image": ["image/jpeg", "image/png", "image/webp", "image/gif"],
    "video": ["video/mp4"],
    "audio": ["audio/mpeg", "audio/wav", "audio/ogg"],
    "model": ["application/octet-stream"],  # .safetensors
    "training": ["image/jpeg", "image/png", "image/webp"],
}

# Magic bytes for MIME type validation (R11.9)
# Each entry maps a content_type to a list of valid magic byte prefixes.
MAGIC_BYTES: dict[str, list[bytes]] = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],  # Also check "WEBP" at offset 8
    "image/gif": [b"GIF87a", b"GIF89a"],
    "video/mp4": [b"\x00\x00\x00"],  # ftyp box — check "ftyp" at offset 4
    "audio/mpeg": [b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"ID3"],
    "audio/wav": [b"RIFF"],  # Also check "WAVE" at offset 8
    "audio/ogg": [b"OggS"],
    "application/octet-stream": [],  # .safetensors — no magic check (accept any)
}


# =============================================================================
# Request Schemas
# =============================================================================


class AssetCreate(BaseSchema):
    """Schema for creating a new asset record.

    Used internally by the AssetService — file uploads are handled via
    multipart form, not JSON body. This schema validates the metadata
    portion of the upload.
    """

    filename: str = Field(min_length=1, max_length=255, description="Original filename")
    content_type: str = Field(min_length=1, max_length=100, description="MIME type of the file")
    asset_type: AssetType = Field(description="Asset category")
    talent_id: UUID | None = Field(default=None, description="Associated talent ID")
    job_id: UUID | None = Field(default=None, description="Associated job ID")


# =============================================================================
# Response Schemas
# =============================================================================


class AssetResponse(TimestampedSchema):
    """Full asset metadata response."""

    id: UUID
    org_id: UUID
    storage_provider: str
    storage_key: str
    content_type: str
    file_size_bytes: int
    talent_id: UUID | None = None
    job_id: UUID | None = None
    filename: str
    asset_type: str
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    checksum_sha256: str | None = None


class AssetListResponse(PaginatedResponse):
    """Paginated list of assets."""

    items: list[AssetResponse]


class AssetDeleteResponse(BaseSchema):
    """Response for asset deletion."""

    id: UUID
    deleted: bool = True
    message: str = "Asset scheduled for deletion"


class AssetMediaAccessResponse(BaseSchema):
    """Response containing a media access descriptor (signed/CDN URL)."""

    access_type: str
    url: str
    expires_at: datetime | None = None
    mime_type: str
    thumbnail_url: str | None = None
    file_size_bytes: int | None = None


# =============================================================================
# Internal Schemas
# =============================================================================


class PendingDeletion(BaseSchema):
    """Record for a scheduled storage deletion.

    The asset has been soft-deleted in the DB. This record tracks
    the pending physical deletion from the storage provider.
    """

    id: UUID
    asset_id: UUID
    org_id: UUID
    storage_key: str
    storage_provider: str
    scheduled_at: datetime
    processed_at: datetime | None = None
    error: str | None = None
