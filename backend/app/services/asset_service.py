"""Asset Service — metadata and lifecycle management.

Handles asset creation with MIME validation, storage upload coordination,
soft-delete with scheduled storage cleanup, and tenant-isolated access.

Requirements covered: R11.3, R11.5, R11.6, R11.7, R11.9, R11.10
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

import structlog

from backend.app.providers.storage import (
    MediaAccessDescriptor,
    StorageProvider,
    StorageProviderType,
    StorageUnavailableError,
    generate_storage_key,
)
from backend.app.schemas.asset import (
    ALLOWED_CONTENT_TYPES,
    MAGIC_BYTES,
    AssetType,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Minimum bytes needed for magic byte validation
MIN_MAGIC_BYTES: int = 12

# Multipart upload threshold (R11.7)
MULTIPART_THRESHOLD_BYTES: int = 100 * 1024 * 1024  # 100 MB


# =============================================================================
# Exceptions
# =============================================================================


class AssetServiceError(Exception):
    """Base exception for AssetService operations."""

    def __init__(self, message: str, code: str = "ASSET_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class AssetNotFoundError(AssetServiceError):
    """Raised when an asset cannot be found for the given org_id (R11.10)."""

    def __init__(self, asset_id: UUID, org_id: UUID) -> None:
        super().__init__(
            message=f"Asset {asset_id} not found",
            code="ASSET_NOT_FOUND",
        )
        self.asset_id = asset_id
        self.org_id = org_id


class AssetMimeValidationError(AssetServiceError):
    """Raised when MIME type validation fails (R11.9)."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="INVALID_MIME_TYPE")


class AssetStorageUnavailableError(AssetServiceError):
    """Raised when the storage provider is unreachable."""

    def __init__(self, message: str = "Storage provider unavailable") -> None:
        super().__init__(message=message, code="STORAGE_UNAVAILABLE")


# =============================================================================
# Repository Protocol
# =============================================================================


class AssetRepository(Protocol):
    """Data access protocol for asset metadata in Supabase.

    The AssetService depends on this protocol so it can be mocked in tests
    and replaced with a real Supabase implementation in production.
    """

    async def insert(self, record: dict) -> dict:
        """Insert asset metadata record. Returns the inserted row."""
        ...

    async def get_by_id_and_org(self, asset_id: UUID, org_id: UUID) -> dict | None:
        """Fetch asset by id, filtered by org_id. Returns None if not found or wrong org."""
        ...

    async def list_assets(
        self,
        org_id: UUID,
        limit: int = 20,
        offset: int = 0,
        talent_id: UUID | None = None,
        job_id: UUID | None = None,
        asset_type: str | None = None,
    ) -> tuple[list[dict], int]:
        """List assets for org with filters. Returns (items, total_count)."""
        ...

    async def soft_delete(self, asset_id: UUID, org_id: UUID) -> bool:
        """Set deleted_at timestamp. Returns True if a row was updated."""
        ...

    async def insert_pending_deletion(self, record: dict) -> dict:
        """Insert a pending storage deletion record."""
        ...

    async def get_pending_deletions(self, limit: int = 50) -> list[dict]:
        """Fetch unprocessed pending deletions."""
        ...

    async def mark_deletion_processed(
        self, deletion_id: UUID, error: str | None = None
    ) -> None:
        """Mark a pending deletion as processed."""
        ...


# =============================================================================
# Asset Metadata Record
# =============================================================================


@dataclass
class AssetRecord:
    """In-memory representation of an asset metadata row."""

    id: UUID
    org_id: UUID
    storage_provider: str
    storage_key: str
    content_type: str
    file_size_bytes: int
    filename: str
    asset_type: str
    talent_id: UUID | None = None
    job_id: UUID | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    checksum_sha256: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None


# =============================================================================
# MIME Validation
# =============================================================================


def validate_mime_type(
    data: bytes,
    declared_content_type: str,
    asset_type: str,
) -> bool:
    """Validate MIME type against allowlist and magic bytes (R11.9).

    Checks:
    1. The declared content_type is in the allowlist for the given asset_type.
    2. The file's magic bytes match the declared content_type.

    Args:
        data: File content bytes (at least first 12 bytes needed).
        declared_content_type: The MIME type declared by the client.
        asset_type: The asset category (image, video, audio, model).

    Returns:
        True if validation passes.

    Raises:
        AssetMimeValidationError: If the content type is not allowed or
            magic bytes don't match.
    """
    # Check allowlist
    allowed = ALLOWED_CONTENT_TYPES.get(asset_type, [])
    if not allowed:
        raise AssetMimeValidationError(
            f"Unknown asset type: {asset_type}"
        )

    if declared_content_type not in allowed:
        raise AssetMimeValidationError(
            f"Content type '{declared_content_type}' is not allowed for "
            f"asset type '{asset_type}'. Allowed: {allowed}"
        )

    # Check magic bytes
    magic_signatures = MAGIC_BYTES.get(declared_content_type, [])
    if not magic_signatures:
        # No magic byte check for this type (e.g., application/octet-stream)
        return True

    if len(data) < MIN_MAGIC_BYTES:
        raise AssetMimeValidationError(
            f"File too small ({len(data)} bytes) for MIME validation"
        )

    # Special handling for RIFF-based formats (WebP, WAV)
    if declared_content_type == "image/webp":
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return True
        raise AssetMimeValidationError(
            "File magic bytes do not match image/webp (expected RIFF...WEBP)"
        )

    if declared_content_type == "audio/wav":
        if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
            return True
        raise AssetMimeValidationError(
            "File magic bytes do not match audio/wav (expected RIFF...WAVE)"
        )

    # Special handling for MP4 (ftyp box)
    if declared_content_type == "video/mp4":
        if data[4:8] == b"ftyp":
            return True
        raise AssetMimeValidationError(
            "File magic bytes do not match video/mp4 (expected ftyp at offset 4)"
        )

    # Standard prefix check
    for signature in magic_signatures:
        if data[: len(signature)] == signature:
            return True

    raise AssetMimeValidationError(
        f"File magic bytes do not match declared content type '{declared_content_type}'"
    )


# =============================================================================
# Asset Service
# =============================================================================


class AssetService:
    """Asset metadata and lifecycle management service.

    Coordinates between the storage provider (binary data) and the asset
    repository (Supabase metadata). Enforces MIME validation, org isolation,
    soft-delete, and scheduled storage cleanup.

    Requirements covered: R11.3, R11.5, R11.6, R11.7, R11.9, R11.10
    """

    def __init__(
        self,
        repository: AssetRepository,
        storage: StorageProvider,
        storage_provider_type: str = StorageProviderType.B2,
    ) -> None:
        """Initialize the AssetService.

        Args:
            repository: Data access layer for asset metadata.
            storage: Storage provider for binary file operations.
            storage_provider_type: Identifier for which storage backend is active.
        """
        self._repo = repository
        self._storage = storage
        self._storage_provider_type = storage_provider_type

    async def create_asset(
        self,
        org_id: UUID,
        data: bytes,
        content_type: str,
        filename: str,
        asset_type: str = "image",
        talent_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> AssetRecord:
        """Create a new asset: validate MIME, upload to storage, store metadata.

        Validates: R11.3 (metadata in Supabase), R11.6 (object metadata on upload),
        R11.7 (multipart for > 100 MB), R11.9 (MIME magic byte validation).

        Args:
            org_id: Organization that owns this asset.
            data: Raw file bytes.
            content_type: Declared MIME type.
            filename: Original filename.
            asset_type: Asset category (image, video, audio, model, training).
            talent_id: Optional associated talent.
            job_id: Optional associated job.

        Returns:
            AssetRecord with metadata for the created asset.

        Raises:
            AssetMimeValidationError: If MIME validation fails (R11.9).
            AssetStorageUnavailableError: If storage provider is unreachable.
        """
        # 1. Validate MIME type via magic bytes (R11.9)
        validate_mime_type(data, content_type, asset_type)

        # 2. Generate structured storage key (R11.12)
        storage_key = generate_storage_key(
            org_id=str(org_id),
            asset_type=asset_type + "s",  # pluralized: images, videos, etc.
            talent_id=str(talent_id) if talent_id else None,
            job_id=str(job_id) if job_id else None,
            filename=filename,
        )

        # 3. Build object metadata (R11.6)
        object_metadata: dict[str, str] = {
            "org_id": str(org_id),
            "content_type": content_type,
        }
        if job_id:
            object_metadata["job_id"] = str(job_id)

        # 4. Upload to storage (uses multipart for > 100 MB per R11.7)
        try:
            storage_result = await self._storage.upload(
                key=storage_key,
                data=data,
                metadata=object_metadata,
                content_type=content_type,
            )
        except StorageUnavailableError as exc:
            logger.error(
                "asset_upload_storage_unavailable",
                org_id=str(org_id),
                filename=filename,
                error=exc.message,
            )
            raise AssetStorageUnavailableError(
                f"Storage provider unavailable: {exc.message}"
            ) from exc

        # 5. Record metadata in Supabase (R11.3)
        asset_id = uuid4()
        now = datetime.now(UTC)

        record = {
            "id": str(asset_id),
            "org_id": str(org_id),
            "storage_provider": self._storage_provider_type,
            "storage_key": storage_key,
            "content_type": content_type,
            "file_size_bytes": storage_result.size_bytes,
            "filename": filename,
            "asset_type": asset_type,
            "talent_id": str(talent_id) if talent_id else None,
            "job_id": str(job_id) if job_id else None,
            "checksum_sha256": storage_result.checksum_sha256,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        await self._repo.insert(record)

        logger.info(
            "asset_created",
            asset_id=str(asset_id),
            org_id=str(org_id),
            storage_key=storage_key,
            content_type=content_type,
            file_size_bytes=storage_result.size_bytes,
            asset_type=asset_type,
        )

        return AssetRecord(
            id=asset_id,
            org_id=org_id,
            storage_provider=self._storage_provider_type,
            storage_key=storage_key,
            content_type=content_type,
            file_size_bytes=storage_result.size_bytes,
            filename=filename,
            asset_type=asset_type,
            talent_id=talent_id,
            job_id=job_id,
            checksum_sha256=storage_result.checksum_sha256,
            created_at=now,
            updated_at=now,
        )

    async def get_asset(self, asset_id: UUID, org_id: UUID) -> AssetRecord:
        """Get asset metadata, enforcing org_id isolation (R11.10).

        Returns 404 (not 403) if the asset belongs to a different org or
        does not exist — to prevent information leakage.

        Args:
            asset_id: The asset to retrieve.
            org_id: The requesting organization (from JWT, never client-supplied).

        Returns:
            AssetRecord with full metadata.

        Raises:
            AssetNotFoundError: If asset not found for this org (R11.10).
        """
        row = await self._repo.get_by_id_and_org(asset_id, org_id)
        if row is None:
            raise AssetNotFoundError(asset_id=asset_id, org_id=org_id)

        return self._row_to_record(row)

    async def list_assets(
        self,
        org_id: UUID,
        limit: int = 20,
        offset: int = 0,
        talent_id: UUID | None = None,
        job_id: UUID | None = None,
        asset_type: str | None = None,
    ) -> tuple[list[AssetRecord], int]:
        """List assets for an organization with optional filters.

        Always scoped to org_id (tenant isolation).

        Args:
            org_id: The organization to list assets for.
            limit: Maximum items to return (1-100, default 20).
            offset: Pagination offset (default 0).
            talent_id: Optional filter by talent.
            job_id: Optional filter by job.
            asset_type: Optional filter by asset type.

        Returns:
            Tuple of (asset records, total count).
        """
        items, total = await self._repo.list_assets(
            org_id=org_id,
            limit=limit,
            offset=offset,
            talent_id=talent_id,
            job_id=job_id,
            asset_type=asset_type,
        )

        records = [self._row_to_record(row) for row in items]
        return records, total

    async def delete_asset(self, asset_id: UUID, org_id: UUID) -> bool:
        """Soft-delete an asset and schedule storage deletion (R11.5).

        1. Sets deleted_at in the database (soft-delete).
        2. Schedules async storage object deletion.
        The actual storage deletion happens later via process_pending_deletions().

        Args:
            asset_id: The asset to delete.
            org_id: The requesting organization (enforces isolation).

        Returns:
            True if the asset was soft-deleted.

        Raises:
            AssetNotFoundError: If asset not found for this org.
        """
        # First verify the asset exists and belongs to this org
        asset = await self.get_asset(asset_id, org_id)

        # Soft-delete in DB
        deleted = await self._repo.soft_delete(asset_id, org_id)
        if not deleted:
            raise AssetNotFoundError(asset_id=asset_id, org_id=org_id)

        # Schedule async storage deletion
        await self.schedule_storage_deletion(
            asset_id=asset_id,
            org_id=org_id,
            storage_key=asset.storage_key,
            storage_provider=asset.storage_provider,
        )

        logger.info(
            "asset_soft_deleted",
            asset_id=str(asset_id),
            org_id=str(org_id),
            storage_key=asset.storage_key,
        )

        return True

    async def get_media_access(
        self, asset_id: UUID, org_id: UUID
    ) -> MediaAccessDescriptor:
        """Get a media access descriptor (signed/CDN URL) for an asset.

        Never returns raw storage URLs — always signed or CDN (R11.4).

        Args:
            asset_id: The asset to get access for.
            org_id: The requesting organization.

        Returns:
            MediaAccessDescriptor with URL and metadata.

        Raises:
            AssetNotFoundError: If asset not found for this org.
        """
        asset = await self.get_asset(asset_id, org_id)

        # Use the storage provider to get a signed URL or CDN URL
        signed_url = await self._storage.get_signed_url(asset.storage_key)

        return MediaAccessDescriptor(
            access_type="signed_url",
            url=signed_url,
            expires_at=None,  # Provider determines expiry
            mime_type=asset.content_type,
            file_size_bytes=asset.file_size_bytes,
        )

    async def schedule_storage_deletion(
        self,
        asset_id: UUID,
        org_id: UUID,
        storage_key: str,
        storage_provider: str,
    ) -> None:
        """Create a pending deletion record for async storage cleanup (R11.5).

        The actual physical deletion is processed by process_pending_deletions().

        Args:
            asset_id: The asset that was soft-deleted.
            org_id: The organization that owns the asset.
            storage_key: The storage path to eventually delete.
            storage_provider: Which storage backend holds the file.
        """
        deletion_record = {
            "id": str(uuid4()),
            "asset_id": str(asset_id),
            "org_id": str(org_id),
            "storage_key": storage_key,
            "storage_provider": storage_provider,
            "scheduled_at": datetime.now(UTC).isoformat(),
        }

        await self._repo.insert_pending_deletion(deletion_record)

        logger.info(
            "storage_deletion_scheduled",
            asset_id=str(asset_id),
            org_id=str(org_id),
            storage_key=storage_key,
        )

    async def process_pending_deletions(self, limit: int = 50) -> int:
        """Process scheduled storage deletions (background task).

        Fetches pending deletion records and attempts to delete the
        corresponding objects from storage. Records success or failure.

        Args:
            limit: Maximum deletions to process in one batch.

        Returns:
            Number of deletions successfully processed.
        """
        pending = await self._repo.get_pending_deletions(limit=limit)
        processed = 0

        for record in pending:
            deletion_id = UUID(record["id"])
            storage_key = record["storage_key"]

            try:
                await self._storage.delete(storage_key)
                await self._repo.mark_deletion_processed(deletion_id)
                processed += 1

                logger.info(
                    "storage_deletion_processed",
                    deletion_id=str(deletion_id),
                    storage_key=storage_key,
                )
            except Exception as exc:
                await self._repo.mark_deletion_processed(
                    deletion_id, error=str(exc)
                )
                logger.warning(
                    "storage_deletion_failed",
                    deletion_id=str(deletion_id),
                    storage_key=storage_key,
                    error=str(exc),
                )

        return processed

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _row_to_record(self, row: dict) -> AssetRecord:
        """Convert a raw database row dict to an AssetRecord dataclass."""
        return AssetRecord(
            id=UUID(row["id"]) if isinstance(row["id"], str) else row["id"],
            org_id=UUID(row["org_id"]) if isinstance(row["org_id"], str) else row["org_id"],
            storage_provider=row["storage_provider"],
            storage_key=row["storage_key"],
            content_type=row["content_type"],
            file_size_bytes=row["file_size_bytes"],
            filename=row["filename"],
            asset_type=row["asset_type"],
            talent_id=(
                UUID(row["talent_id"])
                if row.get("talent_id") and isinstance(row["talent_id"], str)
                else row.get("talent_id")
            ),
            job_id=(
                UUID(row["job_id"])
                if row.get("job_id") and isinstance(row["job_id"], str)
                else row.get("job_id")
            ),
            width=row.get("width"),
            height=row.get("height"),
            duration_seconds=row.get("duration_seconds"),
            checksum_sha256=row.get("checksum_sha256"),
            created_at=(
                datetime.fromisoformat(row["created_at"])
                if isinstance(row["created_at"], str)
                else row["created_at"]
            ),
            updated_at=(
                datetime.fromisoformat(row["updated_at"])
                if isinstance(row["updated_at"], str)
                else row["updated_at"]
            ),
            deleted_at=(
                datetime.fromisoformat(row["deleted_at"])
                if row.get("deleted_at") and isinstance(row["deleted_at"], str)
                else row.get("deleted_at")
            ),
        )
