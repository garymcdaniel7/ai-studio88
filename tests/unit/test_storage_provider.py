"""Unit tests for backend.app.providers.storage module.

Tests the StorageProvider Protocol, implementations, utility functions,
and factory. All external I/O is mocked.

Run with: pytest tests/unit/test_storage_provider.py -v
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from backend.app.providers.storage import (
    DEFAULT_SIGNED_URL_EXPIRY_SECONDS,
    MULTIPART_THRESHOLD_BYTES,
    AccessType,
    B2StorageProvider,
    R2Provider,
    S3CompatibleProvider,
    StorageConfig,
    StorageError,
    StorageNotFoundError,
    StorageProviderType,
    StorageResult,
    StorageUnavailableError,
    StorageUploadError,
    compute_checksum,
    create_default_storage_provider,
    create_storage_provider,
    generate_storage_key,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def storage_config() -> StorageConfig:
    """A test StorageConfig with no CDN."""
    return StorageConfig(
        endpoint_url="https://s3.us-east-005.backblazeb2.com",
        access_key_id="test_key_id",
        secret_access_key="test_secret",
        bucket_name="test-bucket",
        region="us-east-005",
        cdn_url=None,
    )


@pytest.fixture
def cdn_config() -> StorageConfig:
    """A test StorageConfig with CDN enabled."""
    return StorageConfig(
        endpoint_url="https://s3.us-east-005.backblazeb2.com",
        access_key_id="test_key_id",
        secret_access_key="test_secret",
        bucket_name="test-bucket",
        region="us-east-005",
        cdn_url="https://cdn.example.com",
    )


@pytest.fixture
def b2_provider(storage_config: StorageConfig) -> B2StorageProvider:
    """A B2StorageProvider instance."""
    return B2StorageProvider(storage_config)


@pytest.fixture
def b2_cdn_provider(cdn_config: StorageConfig) -> B2StorageProvider:
    """A B2StorageProvider with CDN configured."""
    return B2StorageProvider(cdn_config)


# =============================================================================
# Tests: generate_storage_key
# =============================================================================


@pytest.mark.unit
class TestGenerateStorageKey:
    """Tests for the generate_storage_key utility function."""

    def test_full_key_structure(self) -> None:
        """Key with all parts follows /{org_id}/{asset_type}/{talent_id}/{job_id}/{filename}."""
        key = generate_storage_key(
            org_id="org_abc123",
            asset_type="images",
            talent_id="talent_xyz",
            job_id="job_456",
            filename="output.webp",
        )
        parts = key.split("/")
        assert len(parts) == 5
        assert parts[0] == "org_abc123"
        assert parts[1] == "images"
        assert parts[2] == "talent_xyz"
        assert parts[3] == "job_456"
        assert "output.webp" in parts[4]

    def test_minimal_key_without_optional_parts(self) -> None:
        """Key with only org_id and asset_type generates auto filename."""
        key = generate_storage_key(org_id="org_abc", asset_type="models")
        parts = key.split("/")
        assert len(parts) == 3
        assert parts[0] == "org_abc"
        assert parts[1] == "models"
        assert parts[2].endswith(".bin")

    def test_filename_sanitization(self) -> None:
        """Spaces and slashes in filename are replaced with underscores."""
        key = generate_storage_key(
            org_id="org1",
            asset_type="images",
            filename="my file/with spaces.png",
        )
        filename_part = key.split("/")[-1]
        assert " " not in filename_part
        # Only forward slashes are path separators; within filename they are sanitized
        assert filename_part.endswith("my_file_with_spaces.png")

    def test_unique_prefix_prevents_collisions(self) -> None:
        """Same inputs produce different keys due to UUID prefix."""
        key1 = generate_storage_key(org_id="org1", asset_type="images", filename="test.png")
        key2 = generate_storage_key(org_id="org1", asset_type="images", filename="test.png")
        assert key1 != key2

    def test_key_without_talent_id(self) -> None:
        """Key without talent_id omits that path segment."""
        key = generate_storage_key(
            org_id="org1",
            asset_type="images",
            job_id="job123",
            filename="out.png",
        )
        parts = key.split("/")
        assert parts[0] == "org1"
        assert parts[1] == "images"
        assert parts[2] == "job123"
        assert "out.png" in parts[3]


# =============================================================================
# Tests: compute_checksum
# =============================================================================


@pytest.mark.unit
class TestComputeChecksum:
    """Tests for the compute_checksum utility."""

    def test_returns_sha256_hex(self) -> None:
        """Checksum is a 64-character hex SHA-256 digest."""
        result = compute_checksum(b"hello world")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self) -> None:
        """Same input always produces same checksum."""
        data = b"test data"
        assert compute_checksum(data) == compute_checksum(data)

    def test_different_inputs_different_checksums(self) -> None:
        """Different inputs produce different checksums."""
        assert compute_checksum(b"a") != compute_checksum(b"b")


# =============================================================================
# Tests: StorageProviderType enum
# =============================================================================


@pytest.mark.unit
class TestStorageProviderType:
    """Tests for the StorageProviderType enum."""

    def test_values(self) -> None:
        """Enum has expected values."""
        assert StorageProviderType.B2.value == "b2"
        assert StorageProviderType.S3.value == "s3"
        assert StorageProviderType.R2.value == "r2"

    def test_is_str_enum(self) -> None:
        """Enum values can be used directly as strings."""
        assert f"provider={StorageProviderType.B2}" == "provider=b2"


# =============================================================================
# Tests: Provider Instantiation
# =============================================================================


@pytest.mark.unit
class TestProviderInstantiation:
    """Tests for creating storage provider instances."""

    def test_b2_provider_creates(self, storage_config: StorageConfig) -> None:
        """B2StorageProvider instantiates without error."""
        provider = B2StorageProvider(storage_config)
        assert provider._provider_type == StorageProviderType.B2

    def test_s3_provider_creates(self, storage_config: StorageConfig) -> None:
        """S3CompatibleProvider instantiates without error."""
        provider = S3CompatibleProvider(storage_config)
        assert provider._provider_type == StorageProviderType.S3

    def test_r2_provider_creates(self, storage_config: StorageConfig) -> None:
        """R2Provider instantiates without error."""
        provider = R2Provider(storage_config)
        assert provider._provider_type == StorageProviderType.R2


# =============================================================================
# Tests: Factory Function
# =============================================================================


@pytest.mark.unit
class TestCreateStorageProvider:
    """Tests for the create_storage_provider factory."""

    def test_creates_b2(self, storage_config: StorageConfig) -> None:
        """Factory creates B2StorageProvider for B2 type."""
        provider = create_storage_provider(StorageProviderType.B2, storage_config)
        assert isinstance(provider, B2StorageProvider)

    def test_creates_s3(self, storage_config: StorageConfig) -> None:
        """Factory creates S3CompatibleProvider for S3 type."""
        provider = create_storage_provider(StorageProviderType.S3, storage_config)
        assert isinstance(provider, S3CompatibleProvider)

    def test_creates_r2(self, storage_config: StorageConfig) -> None:
        """Factory creates R2Provider for R2 type."""
        provider = create_storage_provider(StorageProviderType.R2, storage_config)
        assert isinstance(provider, R2Provider)

    def test_raises_for_invalid_type(self, storage_config: StorageConfig) -> None:
        """Factory raises ValueError for unsupported type."""
        with pytest.raises(ValueError, match="Unsupported storage provider"):
            create_storage_provider("invalid", storage_config)


# =============================================================================
# Tests: create_default_storage_provider
# =============================================================================


@pytest.mark.unit
class TestCreateDefaultStorageProvider:
    """Tests for the create_default_storage_provider factory."""

    def test_raises_when_env_vars_missing(self) -> None:
        """Raises ValueError when required env vars are absent."""
        with patch.dict("os.environ", {}, clear=True), pytest.raises(
            ValueError, match="Missing required B2 environment variables"
        ):
            create_default_storage_provider()

    def test_creates_from_env_vars(self) -> None:
        """Creates B2StorageProvider when all env vars are set."""
        env = {
            "B2_ENDPOINT_URL": "https://s3.example.com",
            "B2_KEY_ID": "key123",
            "B2_APPLICATION_KEY": "secret456",
            "B2_BUCKET_NAME": "my-bucket",
            "B2_REGION": "eu-central-001",
            "B2_CDN_URL": "https://cdn.example.com",
        }
        with patch.dict("os.environ", env, clear=True):
            provider = create_default_storage_provider()
            assert isinstance(provider, B2StorageProvider)
            assert provider._config.bucket_name == "my-bucket"
            assert provider._config.cdn_url == "https://cdn.example.com"
            assert provider._config.region == "eu-central-001"


# =============================================================================
# Tests: Upload (mocked)
# =============================================================================


@pytest.mark.unit
class TestUpload:
    """Tests for the upload method with mocked S3 client."""

    @pytest.mark.asyncio
    async def test_upload_small_file(self, b2_provider: B2StorageProvider) -> None:
        """Small file upload uses put_object."""
        b2_provider._client = MagicMock()
        data = b"hello world"

        result = await b2_provider.upload(
            key="org1/images/file.png",
            data=data,
            metadata={"org_id": "org1", "job_id": "job1"},
            content_type="image/png",
        )

        assert isinstance(result, StorageResult)
        assert result.key == "org1/images/file.png"
        assert result.size_bytes == len(data)
        assert result.content_type == "image/png"
        assert result.provider == StorageProviderType.B2
        assert len(result.checksum_sha256) == 64

        b2_provider._client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="org1/images/file.png",
            Body=data,
            ContentType="image/png",
            Metadata={"org_id": "org1", "job_id": "job1"},
        )

    @pytest.mark.asyncio
    async def test_upload_large_file_uses_multipart(
        self, b2_provider: B2StorageProvider
    ) -> None:
        """Files > 100 MB trigger multipart upload."""
        b2_provider._client = MagicMock()
        b2_provider._client.create_multipart_upload.return_value = {
            "UploadId": "mpu-123"
        }
        b2_provider._client.upload_part.return_value = {"ETag": '"etag1"'}

        # Create data just over threshold
        data = b"x" * (MULTIPART_THRESHOLD_BYTES + 1)

        result = await b2_provider.upload(
            key="org1/models/large.safetensors",
            data=data,
            content_type="application/octet-stream",
        )

        assert result.size_bytes == len(data)
        b2_provider._client.create_multipart_upload.assert_called_once()
        b2_provider._client.complete_multipart_upload.assert_called_once()
        assert b2_provider._client.upload_part.call_count >= 2

    @pytest.mark.asyncio
    async def test_upload_unavailable_raises(self, b2_provider: B2StorageProvider) -> None:
        """ServiceUnavailable error raises StorageUnavailableError."""
        from botocore.exceptions import ClientError

        b2_provider._client = MagicMock()
        b2_provider._client.put_object.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "Down"}},
            "PutObject",
        )

        with pytest.raises(StorageUnavailableError):
            await b2_provider.upload(
                key="org1/images/fail.png",
                data=b"data",
            )

    @pytest.mark.asyncio
    async def test_upload_client_error_raises_upload_error(
        self, b2_provider: B2StorageProvider
    ) -> None:
        """Non-transient ClientError raises StorageUploadError."""
        from botocore.exceptions import ClientError

        b2_provider._client = MagicMock()
        b2_provider._client.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Forbidden"}},
            "PutObject",
        )

        with pytest.raises(StorageUploadError):
            await b2_provider.upload(key="org1/images/fail.png", data=b"data")


# =============================================================================
# Tests: Download (mocked)
# =============================================================================


@pytest.mark.unit
class TestDownload:
    """Tests for the download method with mocked S3 client."""

    @pytest.mark.asyncio
    async def test_download_success(self, b2_provider: B2StorageProvider) -> None:
        """Successful download returns file bytes."""
        b2_provider._client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"file content"
        b2_provider._client.get_object.return_value = {"Body": mock_body}

        result = await b2_provider.download("org1/images/file.png")
        assert result == b"file content"

    @pytest.mark.asyncio
    async def test_download_not_found_raises(self, b2_provider: B2StorageProvider) -> None:
        """NoSuchKey raises StorageNotFoundError."""
        from botocore.exceptions import ClientError

        b2_provider._client = MagicMock()
        b2_provider._client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
            "GetObject",
        )

        with pytest.raises(StorageNotFoundError):
            await b2_provider.download("org1/images/missing.png")


# =============================================================================
# Tests: Delete (mocked)
# =============================================================================


@pytest.mark.unit
class TestDelete:
    """Tests for the delete method with mocked S3 client."""

    @pytest.mark.asyncio
    async def test_delete_success(self, b2_provider: B2StorageProvider) -> None:
        """Successful delete calls head_object then delete_object."""
        b2_provider._client = MagicMock()

        await b2_provider.delete("org1/images/file.png")

        b2_provider._client.head_object.assert_called_once()
        b2_provider._client.delete_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self, b2_provider: B2StorageProvider) -> None:
        """Deleting non-existent object raises StorageNotFoundError."""
        from botocore.exceptions import ClientError

        b2_provider._client = MagicMock()
        b2_provider._client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not found"}},
            "HeadObject",
        )

        with pytest.raises(StorageNotFoundError):
            await b2_provider.delete("org1/images/missing.png")


# =============================================================================
# Tests: get_signed_url (mocked)
# =============================================================================


@pytest.mark.unit
class TestGetSignedUrl:
    """Tests for the get_signed_url method."""

    @pytest.mark.asyncio
    async def test_signed_url_without_cdn(self, b2_provider: B2StorageProvider) -> None:
        """Without CDN, returns a presigned URL."""
        b2_provider._client = MagicMock()
        b2_provider._client.generate_presigned_url.return_value = (
            "https://s3.example.com/test-bucket/org1/file.png?X-Amz-Signature=abc"
        )

        url = await b2_provider.get_signed_url("org1/file.png", expiry=7200)
        assert "X-Amz-Signature" in url
        b2_provider._client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "org1/file.png"},
            ExpiresIn=7200,
        )

    @pytest.mark.asyncio
    async def test_signed_url_with_cdn(self, b2_cdn_provider: B2StorageProvider) -> None:
        """With CDN configured, returns CDN URL instead of signed URL."""
        url = await b2_cdn_provider.get_signed_url("org1/file.png")
        assert url == "https://cdn.example.com/org1/file.png"


# =============================================================================
# Tests: exists (mocked)
# =============================================================================


@pytest.mark.unit
class TestExists:
    """Tests for the exists method."""

    @pytest.mark.asyncio
    async def test_exists_true(self, b2_provider: B2StorageProvider) -> None:
        """Returns True when head_object succeeds."""
        b2_provider._client = MagicMock()
        result = await b2_provider.exists("org1/file.png")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self, b2_provider: B2StorageProvider) -> None:
        """Returns False when head_object raises ClientError."""
        from botocore.exceptions import ClientError

        b2_provider._client = MagicMock()
        b2_provider._client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not found"}},
            "HeadObject",
        )

        result = await b2_provider.exists("org1/missing.png")
        assert result is False


# =============================================================================
# Tests: list_objects (mocked)
# =============================================================================


@pytest.mark.unit
class TestListObjects:
    """Tests for the list_objects method."""

    @pytest.mark.asyncio
    async def test_list_objects_returns_items(self, b2_provider: B2StorageProvider) -> None:
        """Correctly parses paginated list response."""
        b2_provider._client = MagicMock()
        paginator = MagicMock()
        b2_provider._client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {
                        "Key": "org1/images/file1.png",
                        "Size": 1024,
                        "LastModified": datetime(2024, 1, 1, tzinfo=UTC),
                        "ETag": '"abc123"',
                    },
                    {
                        "Key": "org1/images/file2.png",
                        "Size": 2048,
                        "LastModified": datetime(2024, 1, 2, tzinfo=UTC),
                        "ETag": '"def456"',
                    },
                ]
            }
        ]

        result = await b2_provider.list_objects("org1/images/")
        assert len(result) == 2
        assert result[0].key == "org1/images/file1.png"
        assert result[0].size_bytes == 1024
        assert result[1].key == "org1/images/file2.png"

    @pytest.mark.asyncio
    async def test_list_objects_empty(self, b2_provider: B2StorageProvider) -> None:
        """Returns empty list when no objects match prefix."""
        b2_provider._client = MagicMock()
        paginator = MagicMock()
        b2_provider._client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{"Contents": []}]

        result = await b2_provider.list_objects("org1/nonexistent/")
        assert result == []


# =============================================================================
# Tests: MediaAccessDescriptor
# =============================================================================


@pytest.mark.unit
class TestMediaAccessDescriptor:
    """Tests for the get_media_descriptor helper."""

    def test_cdn_descriptor(self, b2_cdn_provider: B2StorageProvider) -> None:
        """CDN config produces CDN URL with no expiration."""
        desc = b2_cdn_provider.get_media_descriptor(
            key="org1/images/photo.webp",
            mime_type="image/webp",
            file_size_bytes=4096,
        )
        assert desc.access_type == AccessType.CDN_URL
        assert desc.url == "https://cdn.example.com/org1/images/photo.webp"
        assert desc.expires_at is None
        assert desc.mime_type == "image/webp"
        assert desc.provider == "b2"
        assert desc.file_size_bytes == 4096

    def test_signed_url_descriptor(self, b2_provider: B2StorageProvider) -> None:
        """No CDN produces signed URL with expiration."""
        b2_provider._client = MagicMock()
        b2_provider._client.generate_presigned_url.return_value = "https://signed.url/file"

        desc = b2_provider.get_media_descriptor(
            key="org1/images/photo.webp",
            mime_type="image/webp",
        )
        assert desc.access_type == AccessType.SIGNED_URL
        assert desc.url == "https://signed.url/file"
        assert desc.expires_at is not None
        assert desc.provider == "b2"

    def test_thumbnail_url_with_cdn(self, b2_cdn_provider: B2StorageProvider) -> None:
        """Thumbnail URL uses CDN when available."""
        desc = b2_cdn_provider.get_media_descriptor(
            key="org1/images/photo.webp",
            mime_type="image/webp",
            thumbnail_key="org1/images/photo_thumb.webp",
        )
        assert desc.thumbnail_url == "https://cdn.example.com/org1/images/photo_thumb.webp"


# =============================================================================
# Tests: Exception Hierarchy
# =============================================================================


@pytest.mark.unit
class TestExceptions:
    """Tests for the exception classes."""

    def test_storage_error_base(self) -> None:
        """StorageError stores message and key."""
        err = StorageError("something failed", key="org1/file.png")
        assert err.message == "something failed"
        assert err.key == "org1/file.png"
        assert str(err) == "something failed"

    def test_upload_error_inherits(self) -> None:
        """StorageUploadError is a StorageError."""
        err = StorageUploadError("upload failed")
        assert isinstance(err, StorageError)

    def test_not_found_error_inherits(self) -> None:
        """StorageNotFoundError is a StorageError."""
        err = StorageNotFoundError("not found", key="missing")
        assert isinstance(err, StorageError)
        assert err.key == "missing"

    def test_unavailable_error_inherits(self) -> None:
        """StorageUnavailableError is a StorageError."""
        err = StorageUnavailableError("unreachable")
        assert isinstance(err, StorageError)


# =============================================================================
# Tests: Constants
# =============================================================================


@pytest.mark.unit
class TestConstants:
    """Tests for module constants."""

    def test_multipart_threshold(self) -> None:
        """Multipart threshold is 100 MB."""
        assert MULTIPART_THRESHOLD_BYTES == 100 * 1024 * 1024

    def test_default_expiry(self) -> None:
        """Default signed URL expiry is 3600 seconds."""
        assert DEFAULT_SIGNED_URL_EXPIRY_SECONDS == 3600
