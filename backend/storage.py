"""Backblaze B2 storage service.

Handles file upload, download, and deletion via the S3-compatible API.
All files are stored with structured keys: {project_id}/{asset_type}/{filename}
"""
from __future__ import annotations

import hashlib
import os
import uuid
from io import BytesIO
from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

B2_KEY_ID = os.getenv("B2_KEY_ID", "")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY", "")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME", "")
B2_ENDPOINT_URL = os.getenv("B2_ENDPOINT_URL", "")
B2_REGION = os.getenv("B2_REGION", "us-east-005")


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
    """Compute SHA-256 checksum of file content."""
    return hashlib.sha256(content).hexdigest()


def generate_storage_key(
    original_filename: str,
    asset_type: str = "general",
    project_id: str | None = None,
) -> str:
    """Generate a unique storage key for B2.

    Pattern: {project_id}/{asset_type}/{uuid}_{original_filename}
    """
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
) -> str:
    """Upload file content to B2.

    Args:
        content: Raw file bytes
        storage_key: The key/path to store under in B2
        content_type: MIME type of the file

    Returns:
        The public URL of the uploaded file

    Raises:
        ClientError: If the upload fails
    """
    client = _get_client()
    client.put_object(
        Bucket=B2_BUCKET_NAME,
        Key=storage_key,
        Body=content,
        ContentType=content_type,
    )
    # Construct public URL
    public_url = f"{B2_ENDPOINT_URL}/{B2_BUCKET_NAME}/{storage_key}"
    return public_url


def delete_file(storage_key: str) -> bool:
    """Delete a file from B2.

    Returns:
        True if deleted, False if not found
    """
    client = _get_client()
    try:
        client.delete_object(Bucket=B2_BUCKET_NAME, Key=storage_key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":
            return False
        raise


def get_signed_url(storage_key: str, expires_in: int = 3600) -> str:
    """Generate a time-limited signed URL for private file access."""
    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": B2_BUCKET_NAME, "Key": storage_key},
        ExpiresIn=expires_in,
    )
