"""Secure Tenant-Scoped Storage — Story 024.

Private-by-default object storage with workspace-prefixed keys,
authorized signed URLs, path sanitization, and cross-tenant denial.

Key scheme:
    {org_id}/{asset_type}/{resource_id}/{uuid}_{sanitized_filename}

Examples:
    org_abc123/images/talent_xyz/a1b2c3d4_portrait.webp
    org_abc123/models/talent_xyz/lora_v3.safetensors
    org_abc123/training/talent_xyz/dataset/photo_001.jpg
    org_abc123/audio/voice_abc/clip_001.wav

Rules:
1. Objects are PRIVATE by default — never return raw public URLs.
2. Access is via signed URLs (expiring) or authorized proxy.
3. Every key MUST start with the trusted org_id prefix.
4. Filenames are sanitized (no path traversal, no special chars).
5. Cross-tenant access is impossible — keys are namespace-isolated.
6. Upload/download/delete require org_id from TenantContext.
7. Legacy public-style URLs are identified for migration.

Signed URL default expiry: 1 hour (3600 seconds).
Maximum expiry: 24 hours (86400 seconds).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from typing import Any

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

B2_KEY_ID = os.getenv("B2_KEY_ID", "")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY", "")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME", "")
B2_ENDPOINT_URL = os.getenv("B2_ENDPOINT_URL", "")
B2_REGION = os.getenv("B2_REGION", "us-east-005")

# Signed URL constraints
DEFAULT_SIGNED_URL_EXPIRY = 3600  # 1 hour
MAX_SIGNED_URL_EXPIRY = 86400  # 24 hours

# Filename sanitization
_UNSAFE_CHARS = re.compile(r"[^a-zA-Z0-9._\-]")
_PATH_TRAVERSAL = re.compile(r"\.\.|//|\\")
_MAX_FILENAME_LENGTH = 200


# =============================================================================
# Path Sanitization
# =============================================================================


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal and injection.

    Rules:
    - Replace spaces with underscores
    - Remove any character that isn't alphanumeric, dot, dash, or underscore
    - Reject path traversal attempts (.., //, \\)
    - Truncate to MAX_FILENAME_LENGTH
    - Must have at least 1 character after sanitization

    Raises:
        ValueError: If filename is empty or contains only unsafe characters.
    """
    if not filename or not filename.strip():
        raise ValueError("Filename cannot be empty")

    # Reject path traversal patterns
    if _PATH_TRAVERSAL.search(filename):
        raise ValueError(f"Filename contains path traversal: {filename[:50]}")

    # Take only the basename (strip any directory components)
    basename = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

    # Replace spaces
    sanitized = basename.replace(" ", "_")

    # Remove unsafe characters
    sanitized = _UNSAFE_CHARS.sub("", sanitized)

    # Truncate
    sanitized = sanitized[:_MAX_FILENAME_LENGTH]

    if not sanitized:
        raise ValueError("Filename contains only unsafe characters")

    return sanitized


def validate_org_id(org_id: str) -> str:
    """Validate org_id format and reject obviously invalid values.

    Raises:
        ValueError: If org_id is empty, a zero-UUID, or contains path chars.
    """
    if not org_id:
        raise ValueError("org_id is required for storage operations")

    # Reject zero-UUID
    if org_id == "00000000-0000-0000-0000-000000000000":
        raise ValueError("Zero-UUID is not a valid org_id for storage")

    # Reject path traversal in org_id
    if _PATH_TRAVERSAL.search(org_id):
        raise ValueError("org_id contains invalid characters")

    # Reject slashes
    if "/" in org_id or "\\" in org_id:
        raise ValueError("org_id cannot contain path separators")

    return org_id


# =============================================================================
# Key Builder
# =============================================================================


def build_storage_key(
    org_id: str,
    asset_type: str,
    original_filename: str,
    resource_id: str | None = None,
) -> str:
    """Build a tenant-scoped storage key.

    Pattern: {org_id}/{asset_type}/{resource_id}/{uuid}_{sanitized_filename}

    Args:
        org_id: Trusted workspace org_id (from TenantContext).
        asset_type: Category (images, models, training, audio, video).
        original_filename: User-provided filename (will be sanitized).
        resource_id: Optional resource identifier (talent_id, project_id).

    Returns:
        A safe, tenant-prefixed storage key.

    Raises:
        ValueError: If org_id or filename is invalid.
    """
    validated_org = validate_org_id(org_id)
    safe_filename = sanitize_filename(original_filename)
    unique_prefix = uuid.uuid4().hex[:12]

    # Sanitize asset_type
    safe_type = _UNSAFE_CHARS.sub("", asset_type) or "general"

    parts = [validated_org, safe_type]
    if resource_id:
        safe_resource = _UNSAFE_CHARS.sub("", resource_id)
        if safe_resource:
            parts.append(safe_resource)
    parts.append(f"{unique_prefix}_{safe_filename}")

    return "/".join(parts)


def extract_org_from_key(storage_key: str) -> str | None:
    """Extract the org_id prefix from a storage key.

    Returns None if the key doesn't follow the tenant-scoped pattern.
    Used for cross-tenant validation.
    """
    parts = storage_key.split("/", 1)
    if len(parts) >= 2:
        return parts[0]
    return None


def key_belongs_to_org(storage_key: str, org_id: str) -> bool:
    """Check if a storage key belongs to the specified org.

    Used to validate that a download/delete request targets the
    correct tenant's objects.
    """
    key_org = extract_org_from_key(storage_key)
    return key_org == org_id


# =============================================================================
# Secure Storage Client
# =============================================================================


def _get_client():
    """Create a boto3 S3 client configured for Backblaze B2."""
    if not B2_KEY_ID or not B2_APPLICATION_KEY:
        raise RuntimeError("B2 storage credentials not configured")
    return boto3.client(
        "s3",
        endpoint_url=B2_ENDPOINT_URL,
        aws_access_key_id=B2_KEY_ID,
        aws_secret_access_key=B2_APPLICATION_KEY,
        region_name=B2_REGION,
    )


def compute_checksum(content: bytes) -> str:
    """Compute SHA-256 checksum of file content."""
    return hashlib.sha256(content).hexdigest()


def upload_private(
    org_id: str,
    content: bytes,
    storage_key: str,
    content_type: str = "application/octet-stream",
    metadata: dict[str, str] | None = None,
) -> str:
    """Upload file content to private B2 storage.

    The object is stored PRIVATELY — no public URL is returned.
    Access is only via get_authorized_url().

    Args:
        org_id: Trusted workspace org_id (validates key ownership).
        content: Raw file bytes.
        storage_key: Must start with org_id prefix.
        content_type: MIME type.
        metadata: Optional B2 object metadata (org_id, job_id, etc.).

    Returns:
        The storage key (NOT a URL — use get_authorized_url for access).

    Raises:
        ValueError: If key doesn't belong to the specified org.
        ClientError: If upload fails.
    """
    validated_org = validate_org_id(org_id)

    if not key_belongs_to_org(storage_key, validated_org):
        raise ValueError(
            f"Storage key does not belong to org {validated_org[:8]}..."
        )

    client = _get_client()

    # Always include org_id in object metadata for defense-in-depth
    obj_metadata = {"org-id": validated_org}
    if metadata:
        obj_metadata.update(metadata)

    client.put_object(
        Bucket=B2_BUCKET_NAME,
        Key=storage_key,
        Body=content,
        ContentType=content_type,
        Metadata=obj_metadata,
    )

    return storage_key


def get_authorized_url(
    org_id: str,
    storage_key: str,
    expires_in: int = DEFAULT_SIGNED_URL_EXPIRY,
) -> str:
    """Generate an authorized, expiring signed URL for private access.

    Cross-tenant access is denied — the key must belong to the org.

    Args:
        org_id: Trusted workspace org_id.
        storage_key: The object key to access.
        expires_in: URL validity in seconds (max 24 hours).

    Returns:
        A time-limited signed URL.

    Raises:
        ValueError: If key doesn't belong to org or expiry is too long.
    """
    validated_org = validate_org_id(org_id)

    if not key_belongs_to_org(storage_key, validated_org):
        raise ValueError(
            f"Access denied: key does not belong to org {validated_org[:8]}..."
        )

    # Clamp expiry
    expires_in = min(max(expires_in, 60), MAX_SIGNED_URL_EXPIRY)

    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": B2_BUCKET_NAME, "Key": storage_key},
        ExpiresIn=expires_in,
    )


def delete_private(org_id: str, storage_key: str) -> bool:
    """Delete a private object, scoped to tenant.

    Cross-tenant deletion is denied.

    Returns:
        True if deleted, False if not found.

    Raises:
        ValueError: If key doesn't belong to org.
    """
    validated_org = validate_org_id(org_id)

    if not key_belongs_to_org(storage_key, validated_org):
        raise ValueError(
            f"Delete denied: key does not belong to org {validated_org[:8]}..."
        )

    client = _get_client()
    try:
        client.delete_object(Bucket=B2_BUCKET_NAME, Key=storage_key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":
            return False
        raise


def download_private(org_id: str, storage_key: str) -> bytes:
    """Download a private object, scoped to tenant.

    Cross-tenant download is denied.

    Raises:
        ValueError: If key doesn't belong to org.
        ClientError: If object doesn't exist.
    """
    validated_org = validate_org_id(org_id)

    if not key_belongs_to_org(storage_key, validated_org):
        raise ValueError(
            f"Download denied: key does not belong to org {validated_org[:8]}..."
        )

    client = _get_client()
    response = client.get_object(Bucket=B2_BUCKET_NAME, Key=storage_key)
    return response["Body"].read()


# =============================================================================
# Legacy URL Migration Helpers
# =============================================================================


def is_legacy_public_url(url: str) -> bool:
    """Detect if a URL is a legacy public-style B2 URL.

    Legacy pattern: {endpoint}/{bucket}/{key} (no org_id prefix in key).
    New pattern: always accessed via signed URLs, key starts with org_id.
    """
    if not url:
        return False
    # Legacy public URLs contain the endpoint directly
    if B2_ENDPOINT_URL and url.startswith(B2_ENDPOINT_URL):
        # Extract key part
        prefix = f"{B2_ENDPOINT_URL}/{B2_BUCKET_NAME}/"
        if url.startswith(prefix):
            key = url[len(prefix):]
            # If key doesn't start with a UUID-like org_id, it's legacy
            parts = key.split("/", 1)
            if parts and len(parts[0]) < 30:  # org_ids are UUIDs (36 chars)
                return True
    return False


def migrate_key_to_tenant(
    legacy_key: str,
    org_id: str,
    asset_type: str = "migrated",
) -> str:
    """Generate a new tenant-scoped key for a legacy object.

    Does NOT move the object — just computes what the new key should be.
    Actual migration requires copy + delete in a batch job.

    Returns:
        New tenant-scoped key.
    """
    validated_org = validate_org_id(org_id)
    # Preserve the original filename from the legacy key
    filename = legacy_key.rsplit("/", 1)[-1] if "/" in legacy_key else legacy_key
    safe_filename = sanitize_filename(filename)
    return f"{validated_org}/{asset_type}/{safe_filename}"


# =============================================================================
# Backward Compatibility (transitional)
# =============================================================================
# These functions maintain the old API surface during migration.
# They should be replaced with the secure versions as callers are updated.


def generate_storage_key(
    original_filename: str,
    asset_type: str = "general",
    project_id: str | None = None,
    org_id: str | None = None,
) -> str:
    """Generate a storage key — TRANSITIONAL.

    If org_id is provided, uses the new tenant-scoped pattern.
    If not, uses the legacy pattern (DEPRECATED, will be removed).

    New callers MUST provide org_id.
    """
    if org_id:
        return build_storage_key(org_id, asset_type, original_filename, resource_id=project_id)

    # Legacy fallback (DEPRECATED — callers must be migrated)
    logger.warning(
        "generate_storage_key called without org_id — using legacy pattern. "
        "This is DEPRECATED and will be removed."
    )
    unique_id = uuid.uuid4().hex[:12]
    safe_filename = original_filename.replace(" ", "_").replace("/", "_")
    parts = []
    if project_id:
        parts.append(project_id)
    parts.append(asset_type)
    parts.append(f"{unique_id}_{safe_filename}")
    return "/".join(parts)


def upload_file(
    content: bytes,
    storage_key: str,
    content_type: str = "application/octet-stream",
    org_id: str | None = None,
) -> str:
    """Upload file — TRANSITIONAL.

    If org_id is provided, uses private upload and returns the key.
    If not, uses legacy behavior and returns a public URL (DEPRECATED).

    New callers MUST provide org_id and call get_authorized_url() for access.
    """
    if org_id:
        return upload_private(org_id, content, storage_key, content_type)

    # Legacy fallback (DEPRECATED)
    logger.warning(
        "upload_file called without org_id — returning public URL. "
        "This is DEPRECATED and will be removed."
    )
    client = _get_client()
    client.put_object(
        Bucket=B2_BUCKET_NAME,
        Key=storage_key,
        Body=content,
        ContentType=content_type,
    )
    return f"{B2_ENDPOINT_URL}/{B2_BUCKET_NAME}/{storage_key}"


def get_signed_url(storage_key: str, expires_in: int = 3600) -> str:
    """Generate a signed URL — legacy compatibility.

    Does NOT validate tenant ownership. Use get_authorized_url() instead.
    """
    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": B2_BUCKET_NAME, "Key": storage_key},
        ExpiresIn=expires_in,
    )


def download_file(storage_key: str) -> bytes:
    """Download file — legacy compatibility.

    Does NOT validate tenant ownership. Use download_private() instead.
    """
    client = _get_client()
    response = client.get_object(Bucket=B2_BUCKET_NAME, Key=storage_key)
    return response["Body"].read()


def delete_file(storage_key: str) -> bool:
    """Delete file — legacy compatibility.

    Does NOT validate tenant ownership. Use delete_private() instead.
    """
    client = _get_client()
    try:
        client.delete_object(Bucket=B2_BUCKET_NAME, Key=storage_key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":
            return False
        raise
