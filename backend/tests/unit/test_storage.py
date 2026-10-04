"""Focused compliance tests for the legacy B2 storage boundary.

All B2 calls are mocked. The tests cover the compatibility facade while the
provider-agnostic async implementation is covered by ``tests/unit/test_storage_provider.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from backend import storage


@pytest.fixture
def b2_client() -> MagicMock:
    """Return a mocked S3-compatible B2 client."""
    client = MagicMock()
    client.generate_presigned_url.return_value = (
        "https://s3.example.test/bucket/key?X-Amz-Signature=sentinel"
    )
    return client


@pytest.mark.unit
def test_upload_returns_signed_url_and_required_metadata(b2_client: MagicMock) -> None:
    """Uploads return a signed URL and persist org/job/content-type metadata."""
    org_id = str(uuid4())
    job_id = str(uuid4())
    key = f"{org_id}/images/{uuid4()}/{job_id}/output.webp"

    with (
        patch.object(storage, "_get_client", return_value=b2_client),
        patch.object(storage, "B2_CDN_URL", ""),
    ):
        result = storage.upload_file(
            b"image-bytes",
            key,
            "image/webp",
            org_id=org_id,
            job_id=job_id,
        )

    assert result.startswith("https://s3.example.test/")
    assert "X-Amz-Signature" in result
    call = b2_client.put_object.call_args.kwargs
    assert call["Metadata"] == {
        "org_id": org_id,
        "job_id": job_id,
        "content_type": "image/webp",
    }
    assert call["ContentType"] == "image/webp"


@pytest.mark.unit
def test_configured_cdn_url_is_used_instead_of_b2_url(b2_client: MagicMock) -> None:
    """Configured CDN delivery never exposes the B2 endpoint or bucket URL."""
    key = "org-123/images/talent-123/job-123/output.webp"

    with (
        patch.object(storage, "_get_client", return_value=b2_client),
        patch.object(storage, "B2_CDN_URL", "https://cdn.example.test/assets"),
    ):
        result = storage.upload_file(b"image-bytes", key, "image/webp")

    assert result == f"https://cdn.example.test/assets/{key}"
    b2_client.generate_presigned_url.assert_not_called()


@pytest.mark.unit
def test_raw_b2_url_from_provider_is_rejected(b2_client: MagicMock) -> None:
    """A provider URL without a signature cannot escape the storage boundary."""
    key = "org-123/images/output.webp"
    b2_client.generate_presigned_url.return_value = (
        f"https://s3.example.test/bucket/{key}"
    )

    with (
        patch.object(storage, "_get_client", return_value=b2_client),
        patch.object(storage, "B2_ENDPOINT_URL", "https://s3.example.test"),
        patch.object(storage, "B2_BUCKET_NAME", "bucket"),
        patch.object(storage, "B2_CDN_URL", ""),
        pytest.raises(storage.StorageUrlError, match="raw object URL"),
    ):
        storage.upload_file(b"image-bytes", key, "image/webp")


@pytest.mark.unit
def test_structured_key_is_immutable_and_tenant_scoped() -> None:
    """The new keyword contract creates the required tenant-scoped key shape."""
    key = storage.generate_storage_key(
        "output.webp",
        "images",
        org_id="org-123",
        talent_id="talent-123",
        job_id="job-123",
    )

    parts = key.split("/")
    assert parts[:4] == ["org-123", "images", "talent-123", "job-123"]
    assert parts[4].endswith("_output.webp")
    assert storage.generate_storage_key(
        "output.webp",
        "images",
        org_id="org-123",
        talent_id="talent-123",
        job_id="job-123",
    ) != key


@pytest.mark.unit
def test_large_upload_uses_multipart_and_preserves_metadata(b2_client: MagicMock) -> None:
    """Content over the configured threshold uses multipart and object metadata."""
    b2_client.create_multipart_upload.return_value = {"UploadId": "upload-1"}
    b2_client.upload_part.return_value = {"ETag": '"etag"'}
    key = "org-123/models/talent-123/job-123/model.safetensors"

    with (
        patch.object(storage, "_get_client", return_value=b2_client),
        patch.object(storage, "B2_CDN_URL", ""),
        patch.object(storage, "MULTIPART_THRESHOLD_BYTES", 4),
        patch.object(storage, "MULTIPART_CHUNK_SIZE_BYTES", 2),
    ):
        result = storage.upload_file(
            b"12345",
            key,
            "application/octet-stream",
            org_id="org-123",
            job_id="job-123",
        )

    assert "X-Amz-Signature" in result
    b2_client.put_object.assert_not_called()
    b2_client.create_multipart_upload.assert_called_once()
    assert b2_client.upload_part.call_count == 3
    b2_client.complete_multipart_upload.assert_called_once()
    assert b2_client.create_multipart_upload.call_args.kwargs["Metadata"] == {
        "org_id": "org-123",
        "job_id": "job-123",
        "content_type": "application/octet-stream",
    }


@pytest.mark.unit
def test_multipart_failure_aborts_upload(b2_client: MagicMock) -> None:
    """Multipart failures abort the remote upload and do not return a URL."""
    b2_client.create_multipart_upload.return_value = {"UploadId": "upload-1"}
    b2_client.upload_part.side_effect = ClientError(
        {"Error": {"Code": "ServiceUnavailable", "Message": "down"}},
        "UploadPart",
    )

    with (
        patch.object(storage, "_get_client", return_value=b2_client),
        patch.object(storage, "MULTIPART_THRESHOLD_BYTES", 1),
        pytest.raises(ClientError),
    ):
        storage.upload_file(b"12", "org-123/models/job-123/model.bin")

    b2_client.abort_multipart_upload.assert_called_once_with(
        Bucket=storage.B2_BUCKET_NAME,
        Key="org-123/models/job-123/model.bin",
        UploadId="upload-1",
    )


@pytest.mark.unit
def test_direct_delete_fails_closed_without_b2_call(b2_client: MagicMock) -> None:
    """Request-path deletion cannot hard-delete an object from B2."""
    with (
        patch.object(storage, "_get_client", return_value=b2_client),
        pytest.raises(storage.StorageDeletionRequiresLifecycleError, match="soft-delete"),
    ):
        storage.delete_file("org-123/images/job-123/output.webp")

    b2_client.delete_object.assert_not_called()


@pytest.mark.unit
def test_upload_client_error_is_propagated_without_secret_logging(b2_client: MagicMock) -> None:
    """Provider failures remain typed exceptions and no logging side effect is needed."""
    b2_client.put_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}},
        "PutObject",
    )

    with (
        patch.object(storage, "_get_client", return_value=b2_client),
        pytest.raises(ClientError),
    ):
        storage.upload_file(b"data", "org-123/images/job-123/output.png", "image/png")
