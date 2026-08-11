"""Unit tests for AssetService — asset metadata and lifecycle management.

Tests MIME validation, org_id enforcement (cross-tenant returns 404),
soft-delete behaviour, metadata storage on upload, and pagination.
All I/O is mocked — no DB, no storage.

Validates: Requirements R11.3, R11.5, R11.6, R11.7, R11.9, R11.10
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from backend.app.providers.storage import StorageProviderType, StorageResult, StorageUnavailableError
from backend.app.schemas.asset import ALLOWED_CONTENT_TYPES, AssetType
from backend.app.services.asset_service import (
    AssetMimeValidationError,
    AssetNotFoundError,
    AssetService,
    AssetStorageUnavailableError,
    validate_mime_type,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def org_id() -> UUID:
    """A sample org_id for tests."""
    return uuid4()


@pytest.fixture
def other_org_id() -> UUID:
    """A different org_id for cross-tenant tests."""
    return uuid4()


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Mock AssetRepository."""
    repo = AsyncMock()
    repo.insert = AsyncMock(return_value={})
    repo.get_by_id_and_org = AsyncMock(return_value=None)
    repo.list_assets = AsyncMock(return_value=([], 0))
    repo.soft_delete = AsyncMock(return_value=True)
    repo.insert_pending_deletion = AsyncMock(return_value={})
    repo.get_pending_deletions = AsyncMock(return_value=[])
    repo.mark_deletion_processed = AsyncMock()
    return repo


@pytest.fixture
def mock_storage() -> AsyncMock:
    """Mock StorageProvider."""
    storage = AsyncMock()
    storage.upload = AsyncMock(
        return_value=StorageResult(
            key="org123/images/test.png",
            size_bytes=1024,
            checksum_sha256="abc123",
            content_type="image/png",
            provider=StorageProviderType.B2,
        )
    )
    storage.delete = AsyncMock()
    storage.get_signed_url = AsyncMock(
        return_value="https://b2.example.com/signed/test.png?token=abc"
    )
    return storage


@pytest.fixture
def asset_service(mock_repository: AsyncMock, mock_storage: AsyncMock) -> AssetService:
    """AssetService with mocked dependencies."""
    return AssetService(
        repository=mock_repository,
        storage=mock_storage,
        storage_provider_type=StorageProviderType.B2,
    )


# =============================================================================
# Sample file data
# =============================================================================

# PNG magic bytes: \x89PNG\r\n\x1a\n + 4 more bytes for IHDR
VALID_PNG_DATA = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

# JPEG magic bytes: \xff\xd8\xff
VALID_JPEG_DATA = b"\xff\xd8\xff\xe0" + b"\x00" * 100

# WebP magic bytes: RIFF....WEBP
VALID_WEBP_DATA = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 100

# GIF magic bytes: GIF89a
VALID_GIF_DATA = b"GIF89a" + b"\x00" * 100

# MP4 magic bytes: ....ftyp
VALID_MP4_DATA = b"\x00\x00\x00\x1c" + b"ftyp" + b"isom" + b"\x00" * 100

# WAV magic bytes: RIFF....WAVE
VALID_WAV_DATA = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 100

# MP3 magic bytes: ID3
VALID_MP3_DATA = b"ID3" + b"\x00" * 100

# OGG magic bytes: OggS
VALID_OGG_DATA = b"OggS" + b"\x00" * 100

# Invalid: random bytes that don't match any known format
INVALID_DATA = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d"


# =============================================================================
# MIME Validation Tests (R11.9)
# =============================================================================


class TestMimeValidation:
    """Tests for validate_mime_type — magic byte inspection."""

    def test_valid_png(self) -> None:
        """PNG with correct magic bytes passes validation."""
        assert validate_mime_type(VALID_PNG_DATA, "image/png", "image") is True

    def test_valid_jpeg(self) -> None:
        """JPEG with correct magic bytes passes validation."""
        assert validate_mime_type(VALID_JPEG_DATA, "image/jpeg", "image") is True

    def test_valid_webp(self) -> None:
        """WebP with RIFF...WEBP magic bytes passes validation."""
        assert validate_mime_type(VALID_WEBP_DATA, "image/webp", "image") is True

    def test_valid_gif(self) -> None:
        """GIF89a magic bytes pass validation."""
        assert validate_mime_type(VALID_GIF_DATA, "image/gif", "image") is True

    def test_valid_mp4(self) -> None:
        """MP4 with ftyp at offset 4 passes validation."""
        assert validate_mime_type(VALID_MP4_DATA, "video/mp4", "video") is True

    def test_valid_wav(self) -> None:
        """WAV with RIFF...WAVE magic bytes passes validation."""
        assert validate_mime_type(VALID_WAV_DATA, "audio/wav", "audio") is True

    def test_valid_mp3(self) -> None:
        """MP3 with ID3 tag passes validation."""
        assert validate_mime_type(VALID_MP3_DATA, "audio/mpeg", "audio") is True

    def test_valid_ogg(self) -> None:
        """OGG with OggS magic bytes passes validation."""
        assert validate_mime_type(VALID_OGG_DATA, "audio/ogg", "audio") is True

    def test_valid_safetensors_accepts_any(self) -> None:
        """application/octet-stream (model) accepts any bytes — no magic check."""
        assert validate_mime_type(INVALID_DATA, "application/octet-stream", "model") is True

    def test_content_type_not_in_allowlist(self) -> None:
        """Disallowed content type raises AssetMimeValidationError."""
        with pytest.raises(AssetMimeValidationError, match="not allowed"):
            validate_mime_type(VALID_PNG_DATA, "text/html", "image")

    def test_unknown_asset_type(self) -> None:
        """Unknown asset_type raises AssetMimeValidationError."""
        with pytest.raises(AssetMimeValidationError, match="Unknown asset type"):
            validate_mime_type(VALID_PNG_DATA, "image/png", "unknown_type")

    def test_magic_bytes_mismatch_png_data_declared_jpeg(self) -> None:
        """PNG data declared as JPEG fails validation."""
        with pytest.raises(AssetMimeValidationError, match="do not match"):
            validate_mime_type(VALID_PNG_DATA, "image/jpeg", "image")

    def test_magic_bytes_mismatch_random_data_declared_png(self) -> None:
        """Random data declared as PNG fails validation."""
        with pytest.raises(AssetMimeValidationError, match="do not match"):
            validate_mime_type(INVALID_DATA, "image/png", "image")

    def test_webp_without_webp_marker_fails(self) -> None:
        """RIFF without WEBP at offset 8 fails for image/webp."""
        bad_webp = b"RIFF\x00\x00\x00\x00XXXX" + b"\x00" * 100
        with pytest.raises(AssetMimeValidationError, match="RIFF...WEBP"):
            validate_mime_type(bad_webp, "image/webp", "image")

    def test_wav_without_wave_marker_fails(self) -> None:
        """RIFF without WAVE at offset 8 fails for audio/wav."""
        bad_wav = b"RIFF\x00\x00\x00\x00XXXX" + b"\x00" * 100
        with pytest.raises(AssetMimeValidationError, match="RIFF...WAVE"):
            validate_mime_type(bad_wav, "audio/wav", "audio")

    def test_mp4_without_ftyp_fails(self) -> None:
        """Data without ftyp at offset 4 fails for video/mp4."""
        bad_mp4 = b"\x00\x00\x00\x1c" + b"xxxx" + b"\x00" * 100
        with pytest.raises(AssetMimeValidationError, match="ftyp"):
            validate_mime_type(bad_mp4, "video/mp4", "video")

    def test_file_too_small_for_validation(self) -> None:
        """Files smaller than 12 bytes fail validation."""
        with pytest.raises(AssetMimeValidationError, match="too small"):
            validate_mime_type(b"\x89PNG", "image/png", "image")


# =============================================================================
# Asset Creation Tests (R11.3, R11.6)
# =============================================================================


class TestAssetCreation:
    """Tests for AssetService.create_asset."""

    @pytest.mark.asyncio
    async def test_create_asset_happy_path(
        self, asset_service: AssetService, mock_repository: AsyncMock, org_id: UUID
    ) -> None:
        """Successful asset creation stores metadata and uploads to storage."""
        result = await asset_service.create_asset(
            org_id=org_id,
            data=VALID_PNG_DATA,
            content_type="image/png",
            filename="photo.png",
            asset_type="image",
        )

        assert result.org_id == org_id
        assert result.content_type == "image/png"
        assert result.filename == "photo.png"
        assert result.asset_type == "image"
        assert result.file_size_bytes == 1024  # from mock
        assert result.checksum_sha256 == "abc123"  # from mock
        assert result.storage_provider == StorageProviderType.B2

        # Verify metadata was inserted in repository
        mock_repository.insert.assert_called_once()
        inserted = mock_repository.insert.call_args[0][0]
        assert inserted["org_id"] == str(org_id)
        assert inserted["content_type"] == "image/png"
        assert inserted["asset_type"] == "image"

    @pytest.mark.asyncio
    async def test_create_asset_stores_object_metadata(
        self, asset_service: AssetService, mock_storage: AsyncMock, org_id: UUID
    ) -> None:
        """Upload passes org_id, content_type as object metadata (R11.6)."""
        job_id = uuid4()

        await asset_service.create_asset(
            org_id=org_id,
            data=VALID_PNG_DATA,
            content_type="image/png",
            filename="photo.png",
            asset_type="image",
            job_id=job_id,
        )

        # Verify storage.upload was called with metadata
        mock_storage.upload.assert_called_once()
        call_kwargs = mock_storage.upload.call_args[1]
        metadata = call_kwargs["metadata"]
        assert metadata["org_id"] == str(org_id)
        assert metadata["content_type"] == "image/png"
        assert metadata["job_id"] == str(job_id)

    @pytest.mark.asyncio
    async def test_create_asset_mime_validation_rejects_invalid(
        self, asset_service: AssetService, org_id: UUID
    ) -> None:
        """Invalid magic bytes cause AssetMimeValidationError."""
        with pytest.raises(AssetMimeValidationError):
            await asset_service.create_asset(
                org_id=org_id,
                data=INVALID_DATA,
                content_type="image/png",
                filename="fake.png",
                asset_type="image",
            )

    @pytest.mark.asyncio
    async def test_create_asset_storage_unavailable_raises(
        self, asset_service: AssetService, mock_storage: AsyncMock, org_id: UUID
    ) -> None:
        """Storage unavailable raises AssetStorageUnavailableError."""
        mock_storage.upload.side_effect = StorageUnavailableError(
            "Connection refused", key="test"
        )

        with pytest.raises(AssetStorageUnavailableError):
            await asset_service.create_asset(
                org_id=org_id,
                data=VALID_PNG_DATA,
                content_type="image/png",
                filename="photo.png",
                asset_type="image",
            )

    @pytest.mark.asyncio
    async def test_create_asset_with_talent_and_job(
        self, asset_service: AssetService, mock_repository: AsyncMock, org_id: UUID
    ) -> None:
        """Asset creation includes talent_id and job_id in metadata."""
        talent_id = uuid4()
        job_id = uuid4()

        result = await asset_service.create_asset(
            org_id=org_id,
            data=VALID_PNG_DATA,
            content_type="image/png",
            filename="photo.png",
            asset_type="image",
            talent_id=talent_id,
            job_id=job_id,
        )

        assert result.talent_id == talent_id
        assert result.job_id == job_id

        # Verify stored in DB
        inserted = mock_repository.insert.call_args[0][0]
        assert inserted["talent_id"] == str(talent_id)
        assert inserted["job_id"] == str(job_id)


# =============================================================================
# Org Isolation Tests (R11.10)
# =============================================================================


class TestOrgIsolation:
    """Tests that org_id enforcement returns 404 for wrong org."""

    @pytest.mark.asyncio
    async def test_get_asset_wrong_org_returns_not_found(
        self, asset_service: AssetService, mock_repository: AsyncMock, org_id: UUID
    ) -> None:
        """Requesting asset with wrong org_id raises AssetNotFoundError (R11.10)."""
        asset_id = uuid4()
        # Repository returns None (asset not found for this org)
        mock_repository.get_by_id_and_org.return_value = None

        with pytest.raises(AssetNotFoundError) as exc_info:
            await asset_service.get_asset(asset_id, org_id)

        assert exc_info.value.asset_id == asset_id
        assert exc_info.value.org_id == org_id
        assert exc_info.value.code == "ASSET_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_asset_correct_org_returns_record(
        self, asset_service: AssetService, mock_repository: AsyncMock, org_id: UUID
    ) -> None:
        """Requesting asset with correct org_id returns the record."""
        asset_id = uuid4()
        now = datetime.now(UTC).isoformat()
        mock_repository.get_by_id_and_org.return_value = {
            "id": str(asset_id),
            "org_id": str(org_id),
            "storage_provider": "b2",
            "storage_key": "org/images/test.png",
            "content_type": "image/png",
            "file_size_bytes": 2048,
            "filename": "test.png",
            "asset_type": "image",
            "talent_id": None,
            "job_id": None,
            "checksum_sha256": "def456",
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }

        result = await asset_service.get_asset(asset_id, org_id)

        assert result.id == asset_id
        assert result.org_id == org_id
        assert result.content_type == "image/png"

    @pytest.mark.asyncio
    async def test_delete_asset_wrong_org_returns_not_found(
        self, asset_service: AssetService, mock_repository: AsyncMock, org_id: UUID
    ) -> None:
        """Deleting asset with wrong org_id raises AssetNotFoundError."""
        asset_id = uuid4()
        mock_repository.get_by_id_and_org.return_value = None

        with pytest.raises(AssetNotFoundError):
            await asset_service.delete_asset(asset_id, org_id)

    @pytest.mark.asyncio
    async def test_list_assets_scoped_to_org(
        self, asset_service: AssetService, mock_repository: AsyncMock, org_id: UUID
    ) -> None:
        """list_assets calls repository with the correct org_id."""
        mock_repository.list_assets.return_value = ([], 0)

        await asset_service.list_assets(org_id=org_id, limit=10, offset=0)

        mock_repository.list_assets.assert_called_once_with(
            org_id=org_id,
            limit=10,
            offset=0,
            talent_id=None,
            job_id=None,
            asset_type=None,
        )


# =============================================================================
# Soft-Delete Tests (R11.5)
# =============================================================================


class TestSoftDelete:
    """Tests for soft-delete and scheduled storage cleanup."""

    @pytest.mark.asyncio
    async def test_delete_sets_deleted_at_and_schedules_deletion(
        self, asset_service: AssetService, mock_repository: AsyncMock, org_id: UUID
    ) -> None:
        """delete_asset soft-deletes in DB and schedules storage cleanup."""
        asset_id = uuid4()
        now = datetime.now(UTC).isoformat()

        # Mock the asset existing for this org
        mock_repository.get_by_id_and_org.return_value = {
            "id": str(asset_id),
            "org_id": str(org_id),
            "storage_provider": "b2",
            "storage_key": "org/images/photo.png",
            "content_type": "image/png",
            "file_size_bytes": 1024,
            "filename": "photo.png",
            "asset_type": "image",
            "talent_id": None,
            "job_id": None,
            "checksum_sha256": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        mock_repository.soft_delete.return_value = True

        result = await asset_service.delete_asset(asset_id, org_id)

        assert result is True

        # Verify soft_delete was called
        mock_repository.soft_delete.assert_called_once_with(asset_id, org_id)

        # Verify pending deletion was scheduled
        mock_repository.insert_pending_deletion.assert_called_once()
        deletion = mock_repository.insert_pending_deletion.call_args[0][0]
        assert deletion["asset_id"] == str(asset_id)
        assert deletion["org_id"] == str(org_id)
        assert deletion["storage_key"] == "org/images/photo.png"
        assert deletion["storage_provider"] == "b2"

    @pytest.mark.asyncio
    async def test_delete_does_not_immediately_remove_from_storage(
        self, asset_service: AssetService, mock_storage: AsyncMock, mock_repository: AsyncMock, org_id: UUID
    ) -> None:
        """Soft-delete does NOT call storage.delete — only schedules it."""
        asset_id = uuid4()
        now = datetime.now(UTC).isoformat()

        mock_repository.get_by_id_and_org.return_value = {
            "id": str(asset_id),
            "org_id": str(org_id),
            "storage_provider": "b2",
            "storage_key": "org/images/photo.png",
            "content_type": "image/png",
            "file_size_bytes": 1024,
            "filename": "photo.png",
            "asset_type": "image",
            "talent_id": None,
            "job_id": None,
            "checksum_sha256": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        mock_repository.soft_delete.return_value = True

        await asset_service.delete_asset(asset_id, org_id)

        # Storage.delete should NOT have been called during soft-delete
        mock_storage.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_pending_deletions_removes_from_storage(
        self, asset_service: AssetService, mock_repository: AsyncMock, mock_storage: AsyncMock
    ) -> None:
        """process_pending_deletions calls storage.delete for each pending record."""
        deletion_id = uuid4()
        mock_repository.get_pending_deletions.return_value = [
            {
                "id": str(deletion_id),
                "asset_id": str(uuid4()),
                "org_id": str(uuid4()),
                "storage_key": "org/images/old.png",
                "storage_provider": "b2",
                "scheduled_at": datetime.now(UTC).isoformat(),
            }
        ]

        processed = await asset_service.process_pending_deletions()

        assert processed == 1
        mock_storage.delete.assert_called_once_with("org/images/old.png")
        mock_repository.mark_deletion_processed.assert_called_once_with(deletion_id)

    @pytest.mark.asyncio
    async def test_process_pending_deletions_handles_errors(
        self, asset_service: AssetService, mock_repository: AsyncMock, mock_storage: AsyncMock
    ) -> None:
        """Failed storage deletion records the error but continues."""
        deletion_id = uuid4()
        mock_repository.get_pending_deletions.return_value = [
            {
                "id": str(deletion_id),
                "asset_id": str(uuid4()),
                "org_id": str(uuid4()),
                "storage_key": "org/images/broken.png",
                "storage_provider": "b2",
                "scheduled_at": datetime.now(UTC).isoformat(),
            }
        ]
        mock_storage.delete.side_effect = Exception("Connection timeout")

        processed = await asset_service.process_pending_deletions()

        assert processed == 0
        mock_repository.mark_deletion_processed.assert_called_once_with(
            deletion_id, error="Connection timeout"
        )


# =============================================================================
# Pagination Tests
# =============================================================================


class TestPagination:
    """Tests for paginated asset listing."""

    @pytest.mark.asyncio
    async def test_list_assets_returns_items_and_total(
        self, asset_service: AssetService, mock_repository: AsyncMock, org_id: UUID
    ) -> None:
        """list_assets returns records and total count."""
        now = datetime.now(UTC).isoformat()
        asset_id = uuid4()
        mock_repository.list_assets.return_value = (
            [
                {
                    "id": str(asset_id),
                    "org_id": str(org_id),
                    "storage_provider": "b2",
                    "storage_key": "org/images/test.png",
                    "content_type": "image/png",
                    "file_size_bytes": 2048,
                    "filename": "test.png",
                    "asset_type": "image",
                    "talent_id": None,
                    "job_id": None,
                    "checksum_sha256": None,
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                }
            ],
            42,
        )

        records, total = await asset_service.list_assets(
            org_id=org_id, limit=20, offset=0
        )

        assert len(records) == 1
        assert total == 42
        assert records[0].id == asset_id

    @pytest.mark.asyncio
    async def test_list_assets_with_filters(
        self, asset_service: AssetService, mock_repository: AsyncMock, org_id: UUID
    ) -> None:
        """list_assets passes filter params to repository."""
        talent_id = uuid4()
        job_id = uuid4()
        mock_repository.list_assets.return_value = ([], 0)

        await asset_service.list_assets(
            org_id=org_id,
            limit=10,
            offset=5,
            talent_id=talent_id,
            job_id=job_id,
            asset_type="video",
        )

        mock_repository.list_assets.assert_called_once_with(
            org_id=org_id,
            limit=10,
            offset=5,
            talent_id=talent_id,
            job_id=job_id,
            asset_type="video",
        )


# =============================================================================
# Media Access Tests
# =============================================================================


class TestMediaAccess:
    """Tests for get_media_access — signed URL generation."""

    @pytest.mark.asyncio
    async def test_get_media_access_returns_signed_url(
        self, asset_service: AssetService, mock_repository: AsyncMock, mock_storage: AsyncMock, org_id: UUID
    ) -> None:
        """get_media_access returns a signed URL (never raw)."""
        asset_id = uuid4()
        now = datetime.now(UTC).isoformat()
        mock_repository.get_by_id_and_org.return_value = {
            "id": str(asset_id),
            "org_id": str(org_id),
            "storage_provider": "b2",
            "storage_key": "org/images/photo.png",
            "content_type": "image/png",
            "file_size_bytes": 1024,
            "filename": "photo.png",
            "asset_type": "image",
            "talent_id": None,
            "job_id": None,
            "checksum_sha256": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }

        descriptor = await asset_service.get_media_access(asset_id, org_id)

        assert descriptor.url == "https://b2.example.com/signed/test.png?token=abc"
        assert descriptor.mime_type == "image/png"
        assert descriptor.access_type == "signed_url"
        mock_storage.get_signed_url.assert_called_once_with("org/images/photo.png")

    @pytest.mark.asyncio
    async def test_get_media_access_wrong_org_raises(
        self, asset_service: AssetService, mock_repository: AsyncMock, org_id: UUID
    ) -> None:
        """get_media_access for wrong org raises AssetNotFoundError."""
        mock_repository.get_by_id_and_org.return_value = None

        with pytest.raises(AssetNotFoundError):
            await asset_service.get_media_access(uuid4(), org_id)
