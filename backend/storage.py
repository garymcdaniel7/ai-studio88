"""Backblaze B2 compatibility storage service.

This module preserves the legacy synchronous storage API used by older workers and
routers while enforcing the storage contract at its boundary:

* object keys can use the immutable tenant-scoped structure;
* upload responses are signed URLs or configured CDN URLs, never raw B2 URLs;
* object metadata carries the supplied tenant/job/content-type context;
* uploads larger than 100 MiB use multipart upload; and
* direct request-path deletion is disabled in favour of ``AssetService``'s
  soft-delete and pending-deletion workflow.

New code should prefer ``backend.app.providers.storage`` and
``backend.app.services.asset_service``. Existing callers remain source-compatible
and can adopt the additional keyword arguments incrementally.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Mapping

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

B2_KEY_ID = os.getenv("B2_KEY_ID", "")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY", "")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME", "")
B2_ENDPOINT_URL = os.getenv("B2_ENDPOINT_URL", "")
B2_CDN_URL = os.getenv("B2_CDN_URL", "").rstrip("/")
B2_REGION = os.getenv("B2_REGION", "us-east-005")

# Files strictly larger than this threshold use multipart upload.
MULTIPART_THRESHOLD_BYTES = 100 * 1024 * 1024
MULTIPART_CHUNK_SIZE_BYTES = 50 * 1024 * 1024
DEFAULT_SIGNED_URL_EXPIRY_SECONDS = 3600


class StorageUrlError(RuntimeError):
    """Raised when a provider returns an unsafe raw object URL."""


class StorageMetadataError(ValueError):
    """Raised when storage metadata cannot be represented safely."""


class StorageDeletionRequiresLifecycleError(RuntimeError):
    """Raised when a caller attempts request-path hard deletion.

    Physical deletion must happen through ``AssetService.process_pending_deletions``
    after the asset repository has recorded a soft delete.
    """


def _get_client():
    """Create a boto3 S3 client configured for Backblaze B2."""
    return boto3.client(
        "s3",
        endpoint_url=B2_ENDPOINT_URL,
        aws_access_key_id=B2_KEY_ID,
        aws_secret_access_key=B2_APPLICATION_KEY,
        region_name=B2_REGION,
    )


def compute_checksum(content: bytes) -> str:
    """Compute the SHA-256 checksum of file content."""
    return hashlib.sha256(content).hexdigest()


def generate_storage_key(
    original_filename: str,
    asset_type: str = "general",
    project_id: str | None = None,
    *,
    org_id: str | None = None,
    talent_id: str | None = None,
    job_id: str | None = None,
) -> str:
    """Generate an immutable storage key.

    When ``org_id`` is supplied, the key follows the storage contract:
    ``{org_id}/{asset_type}/{talent_id}/{job_id}/{filename}``, omitting optional
    identity segments that are not available. The legacy positional form is kept
    for existing callers and remains immutable once persisted; those callers should
    migrate to the tenant-scoped keyword form.
    """
    unique_id = uuid.uuid4().hex[:12]
    safe_filename = original_filename.replace(" ", "_").replace("/", "_").replace("\\", "_")

    if org_id:
        parts = [org_id, asset_type]
        if talent_id:
            parts.append(talent_id)
        if job_id:
            parts.append(job_id)
        parts.append(f"{unique_id}_{safe_filename}")
        return "/".join(parts)

    # Compatibility path: do not rewrite existing keys because storage keys are immutable.
    parts = []
    if project_id:
        parts.append(project_id)
    parts.append(asset_type)
    parts.append(f"{unique_id}_{safe_filename}")
    return "/".join(parts)


def _metadata_for_upload(
    storage_key: str,
    content_type: str,
    metadata: Mapping[str, str] | None,
    org_id: str | None,
    job_id: str | None,
) -> dict[str, str]:
    """Build provider metadata without logging credentials or file contents."""
    upload_metadata = {str(key): str(value) for key, value in (metadata or {}).items()}
    if org_id:
        upload_metadata["org_id"] = org_id
    if job_id:
        upload_metadata["job_id"] = job_id
    upload_metadata.setdefault("content_type", content_type)

    # A structured key provides safe defaults for callers that have already adopted
    # the immutable key contract but have not yet supplied keyword metadata.
    parts = storage_key.strip("/").split("/")
    if len(parts) >= 3:
        upload_metadata.setdefault("org_id", parts[0])
    if len(parts) >= 4:
        upload_metadata.setdefault("job_id", parts[-2])
    return upload_metadata


def _assert_delivery_url(url: str, storage_key: str) -> str:
    """Reject an unsigned endpoint/bucket URL before it can reach an API response."""
    raw_prefix = f"{B2_ENDPOINT_URL.rstrip('/')}/{B2_BUCKET_NAME}/{storage_key}"
    if (
        url == raw_prefix
        or url.startswith(f"{raw_prefix}/")
        or url.startswith(f"{raw_prefix}?")
    ):
        raise StorageUrlError("Storage provider returned a raw object URL")
    return url


def _delivery_url(client, storage_key: str, expires_in: int) -> str:
    """Return a configured CDN URL or a validated presigned URL."""
    if B2_CDN_URL:
        return f"{B2_CDN_URL}/{storage_key.lstrip('/')}"

    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": B2_BUCKET_NAME, "Key": storage_key},
        ExpiresIn=expires_in,
    )
    return _assert_delivery_url(url, storage_key)


def upload_file(
    content: bytes,
    storage_key: str,
    content_type: str = "application/octet-stream",
    *,
    org_id: str | None = None,
    job_id: str | None = None,
    metadata: Mapping[str, str] | None = None,
    expires_in: int = DEFAULT_SIGNED_URL_EXPIRY_SECONDS,
) -> str:
    """Upload bytes and return a signed/CDN delivery URL.

    The existing positional signature remains valid. New callers should provide
    ``org_id`` and ``job_id`` (or equivalent metadata) and use a tenant-scoped key.
    MIME/magic-byte and request-size validation remain at the upload/service boundary
    that accepts the user file; this low-level compatibility function does not weaken
    those checks or read beyond the supplied bytes.

    Raises:
        ClientError: If B2 rejects the upload or URL generation.
        StorageUrlError: If the provider returns an unsafe raw URL.
    """
    client = _get_client()
    upload_metadata = _metadata_for_upload(
        storage_key=storage_key,
        content_type=content_type,
        metadata=metadata,
        org_id=org_id,
        job_id=job_id,
    )

    try:
        if len(content) > MULTIPART_THRESHOLD_BYTES:
            _multipart_upload(client, storage_key, content, content_type, upload_metadata)
        else:
            client.put_object(
                Bucket=B2_BUCKET_NAME,
                Key=storage_key,
                Body=content,
                ContentType=content_type,
                Metadata=upload_metadata,
            )
        return _delivery_url(client, storage_key, expires_in)
    except ClientError:
        raise


def _multipart_upload(
    client,
    storage_key: str,
    content: bytes,
    content_type: str,
    metadata: dict[str, str],
) -> None:
    """Upload content in S3-compatible multipart parts and abort on failure."""
    response = client.create_multipart_upload(
        Bucket=B2_BUCKET_NAME,
        Key=storage_key,
        ContentType=content_type,
        Metadata=metadata,
    )
    upload_id = response["UploadId"]
    parts: list[dict[str, str | int]] = []

    try:
        for part_number, offset in enumerate(
            range(0, len(content), MULTIPART_CHUNK_SIZE_BYTES), start=1
        ):
            part = client.upload_part(
                Bucket=B2_BUCKET_NAME,
                Key=storage_key,
                UploadId=upload_id,
                PartNumber=part_number,
                Body=content[offset : offset + MULTIPART_CHUNK_SIZE_BYTES],
            )
            parts.append({"ETag": part["ETag"], "PartNumber": part_number})

        client.complete_multipart_upload(
            Bucket=B2_BUCKET_NAME,
            Key=storage_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
    except Exception:
        client.abort_multipart_upload(
            Bucket=B2_BUCKET_NAME,
            Key=storage_key,
            UploadId=upload_id,
        )
        raise


def delete_file(storage_key: str) -> bool:
    """Reject direct deletion; use the asset soft-delete service instead.

    This intentionally preserves the legacy callable name while removing its unsafe
    hard-delete side effect. ``AssetService.delete_asset`` must first persist the
    database soft-delete and pending deletion record; a worker then invokes the
    provider-specific ``delete`` method from that durable queue.
    """
    raise StorageDeletionRequiresLifecycleError(
        "Direct storage deletion is disabled; soft-delete the asset through AssetService"
    )


def get_signed_url(
    storage_key: str,
    expires_in: int = DEFAULT_SIGNED_URL_EXPIRY_SECONDS,
) -> str:
    """Generate a validated signed URL or configured CDN URL for private media."""
    return _delivery_url(_get_client(), storage_key, expires_in)


def download_file(storage_key: str) -> bytes:
    """Download a file from B2 and return its bytes."""
    client = _get_client()
    response = client.get_object(Bucket=B2_BUCKET_NAME, Key=storage_key)
    return response["Body"].read()
