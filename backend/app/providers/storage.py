"""Provider-agnostic storage interface.

Defines the StorageProvider Protocol and supporting dataclasses.
Implementations: B2StorageProvider (default), S3CompatibleProvider, R2Provider.
This module MUST NOT import from any provider-specific packages at the Protocol level.

Key structure: /{org_id}/{asset_type}/{talent_id}/{job_id}/{filename}

Validates: Requirements R11.1, R11.2, R11.4, R11.7, R11.12
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

import boto3
import structlog
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Files larger than this threshold use multipart upload (R11.7)
MULTIPART_THRESHOLD_BYTES: int = 100 * 1024 * 1024  # 100 MB

# Default signed URL expiration in seconds (R11.4)
DEFAULT_SIGNED_URL_EXPIRY_SECONDS: int = 3600

# Multipart upload chunk size
MULTIPART_CHUNK_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB


# =============================================================================
# Enums
# =============================================================================


class StorageProviderType(StrEnum):
    """Supported storage provider types."""

    B2 = "b2"
    S3 = "s3"
    R2 = "r2"


class AccessType(StrEnum):
    """Type of URL access returned to clients."""

    SIGNED_URL = "signed_url"
    CDN_URL = "cdn_url"
    LOCAL_PATH = "local_path"
    STREAMING = "streaming"


# =============================================================================
# Dataclasses (generic — no provider-specific fields)
# =============================================================================


@dataclass(frozen=True)
class StorageResult:
    """Result of a successful upload operation."""

    key: str
    size_bytes: int
    checksum_sha256: str
    content_type: str
    provider: StorageProviderType
    uploaded_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ObjectInfo:
    """Metadata about a stored object."""

    key: str
    size_bytes: int
    content_type: str
    last_modified: datetime
    checksum: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaAccessDescriptor:
    """Provider-neutral media access reference.

    Frontend consumes this canonical descriptor regardless of where
    the media lives. Never exposes raw storage URLs.
    """

    access_type: AccessType
    url: str
    expires_at: datetime | None
    mime_type: str
    thumbnail_url: str | None = None
    provider: str = ""
    file_size_bytes: int | None = None


@dataclass(frozen=True)
class StorageConfig:
    """Configuration for a storage provider connection."""

    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str
    region: str = "us-east-005"
    cdn_url: str | None = None


# =============================================================================
# Exceptions
# =============================================================================


class StorageError(Exception):
    """Base exception for storage provider operations."""

    def __init__(self, message: str, key: str | None = None) -> None:
        self.message = message
        self.key = key
        super().__init__(message)


class StorageUploadError(StorageError):
    """Raised when an upload fails."""


class StorageDownloadError(StorageError):
    """Raised when a download fails."""


class StorageDeleteError(StorageError):
    """Raised when a delete fails."""


class StorageNotFoundError(StorageError):
    """Raised when a requested object does not exist."""


class StorageUnavailableError(StorageError):
    """Raised when the storage provider is unreachable (maps to HTTP 503)."""


# =============================================================================
# Protocol
# =============================================================================


class StorageProvider(Protocol):
    """Provider-agnostic storage interface.

    All storage providers implement this protocol.

    This protocol uses ONLY generic identifiers:
    - key (str) — structured storage path
    - metadata (dict) — provider-stored object metadata
    - Return types are generic dataclasses defined above

    Never returns raw URLs — always signed or CDN (R11.4).

    Validates: Requirements R11.1, R11.2, R11.4, R11.7, R11.12
    """

    async def upload(
        self,
        key: str,
        data: bytes,
        metadata: dict[str, str] | None = None,
        content_type: str = "application/octet-stream",
    ) -> StorageResult:
        """Upload data to storage.

        Uses multipart upload for files > 100 MB (R11.7).

        Args:
            key: Storage path (/{org_id}/{asset_type}/{talent_id}/{job_id}/{filename}).
            data: Raw file bytes.
            metadata: Object metadata (org_id, job_id, content_type stored per R11.6).
            content_type: MIME type of the file.

        Returns:
            StorageResult with upload confirmation.

        Raises:
            StorageUploadError: If the upload fails.
            StorageUnavailableError: If the provider is unreachable.
        """
        ...

    async def download(self, key: str) -> bytes:
        """Download data from storage.

        Args:
            key: Storage path to download.

        Returns:
            Raw file bytes.

        Raises:
            StorageNotFoundError: If the object does not exist.
            StorageDownloadError: If the download fails.
        """
        ...

    async def delete(self, key: str) -> None:
        """Delete an object from storage.

        Args:
            key: Storage path to delete.

        Raises:
            StorageNotFoundError: If the object does not exist.
            StorageDeleteError: If the deletion fails.
        """
        ...

    async def get_signed_url(
        self,
        key: str,
        expiry: int = DEFAULT_SIGNED_URL_EXPIRY_SECONDS,
    ) -> str:
        """Generate a time-limited signed URL for private file access (R11.4).

        Never returns raw storage URLs.

        Args:
            key: Storage path.
            expiry: URL lifetime in seconds (default 3600).

        Returns:
            Signed URL string.

        Raises:
            StorageNotFoundError: If the object does not exist.
        """
        ...

    async def list_objects(self, prefix: str) -> list[ObjectInfo]:
        """List objects under a prefix.

        Args:
            prefix: Key prefix to filter by.

        Returns:
            List of ObjectInfo for matching objects.
        """
        ...

    async def exists(self, key: str) -> bool:
        """Check if an object exists in storage.

        Args:
            key: Storage path to check.

        Returns:
            True if the object exists, False otherwise.
        """
        ...


# =============================================================================
# Utility Functions
# =============================================================================


def generate_storage_key(
    org_id: str,
    asset_type: str,
    talent_id: str | None = None,
    job_id: str | None = None,
    filename: str | None = None,
) -> str:
    """Generate a structured storage key per R11.12.

    Pattern: /{org_id}/{asset_type}/{talent_id}/{job_id}/{filename}

    Args:
        org_id: Organization UUID string.
        asset_type: Asset category (images, videos, models, training, audio).
        talent_id: Optional talent UUID string.
        job_id: Optional job UUID string.
        filename: Optional original filename (sanitized).

    Returns:
        Structured storage key.
    """
    if not filename:
        filename = f"{uuid.uuid4().hex[:12]}.bin"
    else:
        # Sanitize filename
        filename = filename.replace(" ", "_").replace("/", "_").replace("\\", "_")
        # Prepend unique prefix to avoid collisions
        filename = f"{uuid.uuid4().hex[:8]}_{filename}"

    parts = [org_id, asset_type]
    if talent_id:
        parts.append(talent_id)
    if job_id:
        parts.append(job_id)
    parts.append(filename)

    return "/".join(parts)


def compute_checksum(data: bytes) -> str:
    """Compute SHA-256 checksum of file content."""
    return hashlib.sha256(data).hexdigest()


# =============================================================================
# Implementations
# =============================================================================


class _S3CompatibleBase:
    """Base class for S3-compatible storage providers.

    Handles the common boto3 client operations shared by B2, S3, and R2.
    """

    def __init__(self, config: StorageConfig, provider_type: StorageProviderType) -> None:
        self._config = config
        self._provider_type = provider_type
        self._client = boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            region_name=config.region,
            config=BotoConfig(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        )
        logger.info(
            "storage_provider_initialized",
            provider=provider_type,
            bucket=config.bucket_name,
            region=config.region,
        )

    async def upload(
        self,
        key: str,
        data: bytes,
        metadata: dict[str, str] | None = None,
        content_type: str = "application/octet-stream",
    ) -> StorageResult:
        """Upload data using S3-compatible API. Multipart for > 100 MB (R11.7)."""
        size_bytes = len(data)
        upload_metadata = metadata or {}
        checksum = compute_checksum(data)

        try:
            if size_bytes > MULTIPART_THRESHOLD_BYTES:
                await self._multipart_upload(key, data, content_type, upload_metadata)
            else:
                self._client.put_object(
                    Bucket=self._config.bucket_name,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                    Metadata=upload_metadata,
                )

            logger.info(
                "storage_upload_complete",
                provider=self._provider_type,
                key=key,
                size_bytes=size_bytes,
                content_type=content_type,
            )

            return StorageResult(
                key=key,
                size_bytes=size_bytes,
                checksum_sha256=checksum,
                content_type=content_type,
                provider=self._provider_type,
            )

        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            if error_code in ("RequestTimeout", "ServiceUnavailable", "InternalError"):
                raise StorageUnavailableError(
                    f"Storage provider unreachable: {error_code}", key=key
                ) from exc
            raise StorageUploadError(
                f"Upload failed: {error_code} - {exc}", key=key
            ) from exc
        except Exception as exc:
            raise StorageUnavailableError(
                f"Storage provider unreachable: {exc}", key=key
            ) from exc

    async def _multipart_upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str],
    ) -> None:
        """Perform multipart upload for large files (R11.7)."""
        logger.info(
            "storage_multipart_upload_starting",
            key=key,
            size_bytes=len(data),
            chunk_size=MULTIPART_CHUNK_SIZE_BYTES,
        )

        mpu = self._client.create_multipart_upload(
            Bucket=self._config.bucket_name,
            Key=key,
            ContentType=content_type,
            Metadata=metadata,
        )
        upload_id = mpu["UploadId"]
        parts: list[dict[str, str | int]] = []

        try:
            part_number = 1
            offset = 0
            while offset < len(data):
                chunk = data[offset : offset + MULTIPART_CHUNK_SIZE_BYTES]
                response = self._client.upload_part(
                    Bucket=self._config.bucket_name,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=chunk,
                )
                parts.append({"ETag": response["ETag"], "PartNumber": part_number})
                offset += MULTIPART_CHUNK_SIZE_BYTES
                part_number += 1

            self._client.complete_multipart_upload(
                Bucket=self._config.bucket_name,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

            logger.info(
                "storage_multipart_upload_complete",
                key=key,
                parts_count=len(parts),
            )

        except Exception as exc:
            # Abort multipart upload on failure
            self._client.abort_multipart_upload(
                Bucket=self._config.bucket_name,
                Key=key,
                UploadId=upload_id,
            )
            logger.error(
                "storage_multipart_upload_aborted",
                key=key,
                error=str(exc),
            )
            raise

    async def download(self, key: str) -> bytes:
        """Download data from S3-compatible storage."""
        try:
            response = self._client.get_object(
                Bucket=self._config.bucket_name,
                Key=key,
            )
            return response["Body"].read()
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            if error_code in ("NoSuchKey", "404"):
                raise StorageNotFoundError(
                    f"Object not found: {key}", key=key
                ) from exc
            raise StorageDownloadError(
                f"Download failed: {error_code}", key=key
            ) from exc

    async def delete(self, key: str) -> None:
        """Delete an object from S3-compatible storage."""
        try:
            # Check existence first to raise NotFound if missing
            self._client.head_object(
                Bucket=self._config.bucket_name,
                Key=key,
            )
            self._client.delete_object(
                Bucket=self._config.bucket_name,
                Key=key,
            )
            logger.info("storage_object_deleted", provider=self._provider_type, key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            if error_code in ("NoSuchKey", "404", "NotFound"):
                raise StorageNotFoundError(
                    f"Object not found: {key}", key=key
                ) from exc
            raise StorageDeleteError(
                f"Delete failed: {error_code}", key=key
            ) from exc

    async def get_signed_url(
        self,
        key: str,
        expiry: int = DEFAULT_SIGNED_URL_EXPIRY_SECONDS,
    ) -> str:
        """Generate a signed URL. Uses CDN URL if configured (R11.4)."""
        # If CDN is configured and asset is public-accessible, prefer CDN
        if self._config.cdn_url:
            return f"{self._config.cdn_url}/{key}"

        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._config.bucket_name, "Key": key},
                ExpiresIn=expiry,
            )
            return url
        except ClientError as exc:
            raise StorageError(
                f"Failed to generate signed URL: {exc}", key=key
            ) from exc

    async def list_objects(self, prefix: str) -> list[ObjectInfo]:
        """List objects under a prefix."""
        objects: list[ObjectInfo] = []
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(
                Bucket=self._config.bucket_name, Prefix=prefix
            ):
                for obj in page.get("Contents", []):
                    objects.append(
                        ObjectInfo(
                            key=obj["Key"],
                            size_bytes=obj["Size"],
                            content_type="",  # Not available in list response
                            last_modified=obj["LastModified"],
                            checksum=obj.get("ETag", "").strip('"'),
                        )
                    )
        except ClientError as exc:
            logger.warning(
                "storage_list_objects_failed",
                prefix=prefix,
                error=str(exc),
            )
        return objects

    async def exists(self, key: str) -> bool:
        """Check if an object exists."""
        try:
            self._client.head_object(
                Bucket=self._config.bucket_name,
                Key=key,
            )
            return True
        except ClientError:
            return False

    def get_media_descriptor(
        self,
        key: str,
        mime_type: str,
        file_size_bytes: int | None = None,
        thumbnail_key: str | None = None,
        expiry: int = DEFAULT_SIGNED_URL_EXPIRY_SECONDS,
    ) -> MediaAccessDescriptor:
        """Build a MediaAccessDescriptor for an asset.

        Never returns raw URLs — always signed or CDN (R11.4).
        """
        if self._config.cdn_url:
            url = f"{self._config.cdn_url}/{key}"
            access_type = AccessType.CDN_URL
            expires_at = None
        else:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._config.bucket_name, "Key": key},
                ExpiresIn=expiry,
            )
            access_type = AccessType.SIGNED_URL
            expires_at = datetime.now(UTC) + timedelta(seconds=expiry)

        thumbnail_url = None
        if thumbnail_key and self._config.cdn_url:
            thumbnail_url = f"{self._config.cdn_url}/{thumbnail_key}"
        elif thumbnail_key:
            thumbnail_url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._config.bucket_name, "Key": thumbnail_key},
                ExpiresIn=expiry,
            )

        return MediaAccessDescriptor(
            access_type=access_type,
            url=url,
            expires_at=expires_at,
            mime_type=mime_type,
            thumbnail_url=thumbnail_url,
            provider=self._provider_type.value,
            file_size_bytes=file_size_bytes,
        )


class B2StorageProvider(_S3CompatibleBase):
    """Backblaze B2 storage provider — default platform storage.

    Uses the S3-compatible API. Supports multipart upload for large files.

    Validates: Requirements R11.1, R11.2, R11.4, R11.7, R11.12
    """

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config, StorageProviderType.B2)


class S3CompatibleProvider(_S3CompatibleBase):
    """Generic S3-compatible storage provider.

    Works with any S3-compatible storage: AWS S3, MinIO,
    DigitalOcean Spaces, Wasabi, customer-provided endpoints.

    Validates: Requirements R11.1, R11.2
    """

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config, StorageProviderType.S3)


class R2Provider(_S3CompatibleBase):
    """Cloudflare R2 storage provider.

    R2 is S3-compatible with zero egress fees. Uses the same
    S3 API interface as B2 and AWS S3.

    Validates: Requirements R11.1, R11.2
    """

    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config, StorageProviderType.R2)


# =============================================================================
# Registry / Factory
# =============================================================================


_PROVIDER_IMPLEMENTATIONS: dict[StorageProviderType, type[_S3CompatibleBase]] = {
    StorageProviderType.B2: B2StorageProvider,
    StorageProviderType.S3: S3CompatibleProvider,
    StorageProviderType.R2: R2Provider,
}


def create_storage_provider(
    provider_type: StorageProviderType,
    config: StorageConfig,
) -> _S3CompatibleBase:
    """Factory function to create a StorageProvider by type.

    Args:
        provider_type: Which storage backend to instantiate.
        config: Connection configuration for the provider.

    Returns:
        A configured storage provider instance.

    Raises:
        ValueError: If the provider_type is not supported.
    """
    impl_class = _PROVIDER_IMPLEMENTATIONS.get(provider_type)
    if impl_class is None:
        raise ValueError(
            f"Unsupported storage provider: {provider_type}. "
            f"Supported: {list(_PROVIDER_IMPLEMENTATIONS.keys())}"
        )
    return impl_class(config)


def create_default_storage_provider() -> B2StorageProvider:
    """Create the default B2 storage provider from environment variables.

    Reads B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME, B2_ENDPOINT_URL,
    B2_REGION, and B2_CDN_URL from environment.

    Returns:
        A configured B2StorageProvider.

    Raises:
        ValueError: If required environment variables are missing.
    """
    endpoint_url = os.getenv("B2_ENDPOINT_URL", "")
    access_key_id = os.getenv("B2_KEY_ID", "")
    secret_access_key = os.getenv("B2_APPLICATION_KEY", "")
    bucket_name = os.getenv("B2_BUCKET_NAME", "")
    region = os.getenv("B2_REGION", "us-east-005")
    cdn_url = os.getenv("B2_CDN_URL") or None

    if not all([endpoint_url, access_key_id, secret_access_key, bucket_name]):
        raise ValueError(
            "Missing required B2 environment variables. "
            "Set B2_ENDPOINT_URL, B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME."
        )

    config = StorageConfig(
        endpoint_url=endpoint_url,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        bucket_name=bucket_name,
        region=region,
        cdn_url=cdn_url,
    )
    return B2StorageProvider(config)
