"""Cross-tenant isolation and security tests for secure storage — Story 024.

Tests verify:
  - Tenant-scoped key generation includes org_id prefix
  - Path sanitization rejects traversal attacks
  - Cross-tenant access is denied (upload, download, delete, signed URL)
  - Zero-UUID org_id is rejected
  - Signed URL expiry is bounded
  - Legacy public URL detection works
  - Key ownership validation works
  - Filename sanitization handles edge cases
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.secure_storage import (
    DEFAULT_SIGNED_URL_EXPIRY,
    MAX_SIGNED_URL_EXPIRY,
    build_storage_key,
    extract_org_from_key,
    is_legacy_public_url,
    key_belongs_to_org,
    migrate_key_to_tenant,
    sanitize_filename,
    validate_org_id,
)

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "org-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ZERO_UUID = "00000000-0000-0000-0000-000000000000"


# =============================================================================
# Filename Sanitization
# =============================================================================


@pytest.mark.unit
class TestFilenameSanitization:
    """Verify filename sanitization prevents attacks."""

    def test_normal_filename(self):
        assert sanitize_filename("portrait.webp") == "portrait.webp"

    def test_spaces_replaced(self):
        assert sanitize_filename("my photo.jpg") == "my_photo.jpg"

    def test_special_chars_removed(self):
        result = sanitize_filename("file<>name|test.png")
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result

    def test_path_traversal_rejected(self):
        with pytest.raises(ValueError, match="path traversal"):
            sanitize_filename("../../etc/passwd")

    def test_double_slash_rejected(self):
        with pytest.raises(ValueError, match="path traversal"):
            sanitize_filename("path//to//file.txt")

    def test_backslash_rejected(self):
        with pytest.raises(ValueError, match="path traversal"):
            sanitize_filename("path\\to\\file.txt")

    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            sanitize_filename("")

    def test_only_unsafe_chars_rejected(self):
        with pytest.raises(ValueError, match="only unsafe characters"):
            sanitize_filename("<<<>>>|||")

    def test_directory_stripped(self):
        assert sanitize_filename("/var/uploads/file.txt") == "file.txt"

    def test_long_filename_truncated(self):
        long_name = "a" * 300 + ".png"
        result = sanitize_filename(long_name)
        assert len(result) <= 200


# =============================================================================
# org_id Validation
# =============================================================================


@pytest.mark.unit
class TestOrgIdValidation:
    """Verify org_id validation rejects invalid values."""

    def test_valid_org_id(self):
        assert validate_org_id(TENANT_A) == TENANT_A

    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="org_id is required"):
            validate_org_id("")

    def test_zero_uuid_rejected(self):
        with pytest.raises(ValueError, match="Zero-UUID"):
            validate_org_id(ZERO_UUID)

    def test_path_traversal_in_org_rejected(self):
        with pytest.raises(ValueError, match="invalid characters"):
            validate_org_id("../../../etc")

    def test_slash_in_org_rejected(self):
        with pytest.raises(ValueError, match="path separators"):
            validate_org_id("org/evil")


# =============================================================================
# Key Building
# =============================================================================


@pytest.mark.unit
class TestKeyBuilder:
    """Verify tenant-scoped key generation."""

    def test_key_starts_with_org_id(self):
        key = build_storage_key(TENANT_A, "images", "photo.webp")
        assert key.startswith(TENANT_A + "/")

    def test_key_includes_asset_type(self):
        key = build_storage_key(TENANT_A, "models", "lora.safetensors")
        assert "/models/" in key

    def test_key_includes_resource_id(self):
        key = build_storage_key(TENANT_A, "training", "img.jpg", resource_id="talent_123")
        assert "/talent_123/" in key

    def test_key_has_unique_prefix(self):
        key1 = build_storage_key(TENANT_A, "images", "same.jpg")
        key2 = build_storage_key(TENANT_A, "images", "same.jpg")
        assert key1 != key2  # UUID prefix makes them unique

    def test_key_sanitizes_filename(self):
        key = build_storage_key(TENANT_A, "images", "my photo (1).jpg")
        assert " " not in key
        assert "(" not in key

    def test_different_orgs_produce_different_prefixes(self):
        key_a = build_storage_key(TENANT_A, "images", "file.jpg")
        key_b = build_storage_key(TENANT_B, "images", "file.jpg")
        assert key_a.split("/")[0] != key_b.split("/")[0]


# =============================================================================
# Key Ownership
# =============================================================================


@pytest.mark.unit
class TestKeyOwnership:
    """Verify key ownership validation."""

    def test_key_belongs_to_correct_org(self):
        key = f"{TENANT_A}/images/abc123_photo.webp"
        assert key_belongs_to_org(key, TENANT_A) is True

    def test_key_does_not_belong_to_other_org(self):
        key = f"{TENANT_A}/images/abc123_photo.webp"
        assert key_belongs_to_org(key, TENANT_B) is False

    def test_extract_org_from_valid_key(self):
        key = f"{TENANT_A}/models/lora.safetensors"
        assert extract_org_from_key(key) == TENANT_A

    def test_extract_org_from_legacy_key(self):
        """Legacy keys without org prefix return the first segment."""
        key = "project123/images/photo.jpg"
        assert extract_org_from_key(key) == "project123"


# =============================================================================
# Cross-Tenant Denial
# =============================================================================


@pytest.mark.unit
class TestCrossTenantDenial:
    """Verify cross-tenant storage operations are denied."""

    def test_upload_to_other_orgs_key_denied(self):
        from backend.secure_storage import upload_private
        key = f"{TENANT_B}/images/stolen.jpg"
        with pytest.raises(ValueError, match="does not belong to org"):
            upload_private(TENANT_A, b"data", key)

    def test_download_from_other_orgs_key_denied(self):
        from backend.secure_storage import download_private
        key = f"{TENANT_B}/images/secret.jpg"
        with pytest.raises(ValueError, match="does not belong to org"):
            download_private(TENANT_A, key)

    def test_delete_other_orgs_key_denied(self):
        from backend.secure_storage import delete_private
        key = f"{TENANT_B}/models/model.safetensors"
        with pytest.raises(ValueError, match="does not belong to org"):
            delete_private(TENANT_A, key)

    def test_signed_url_for_other_orgs_key_denied(self):
        from backend.secure_storage import get_authorized_url
        key = f"{TENANT_B}/audio/voice.wav"
        with pytest.raises(ValueError, match="does not belong to org"):
            get_authorized_url(TENANT_A, key)


# =============================================================================
# Signed URL Expiry
# =============================================================================


@pytest.mark.unit
class TestSignedUrlExpiry:
    """Verify signed URL expiry is bounded."""

    @patch("backend.secure_storage._get_client")
    def test_default_expiry(self, mock_client_fn):
        from backend.secure_storage import get_authorized_url
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.generate_presigned_url.return_value = "https://signed.url"

        key = f"{TENANT_A}/images/photo.jpg"
        get_authorized_url(TENANT_A, key)

        call_kwargs = mock_client.generate_presigned_url.call_args
        assert call_kwargs[1]["ExpiresIn"] == DEFAULT_SIGNED_URL_EXPIRY

    @patch("backend.secure_storage._get_client")
    def test_max_expiry_capped(self, mock_client_fn):
        from backend.secure_storage import get_authorized_url
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.generate_presigned_url.return_value = "https://signed.url"

        key = f"{TENANT_A}/images/photo.jpg"
        get_authorized_url(TENANT_A, key, expires_in=999999)  # Way over max

        call_kwargs = mock_client.generate_presigned_url.call_args
        assert call_kwargs[1]["ExpiresIn"] == MAX_SIGNED_URL_EXPIRY

    @patch("backend.secure_storage._get_client")
    def test_min_expiry_enforced(self, mock_client_fn):
        from backend.secure_storage import get_authorized_url
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.generate_presigned_url.return_value = "https://signed.url"

        key = f"{TENANT_A}/images/photo.jpg"
        get_authorized_url(TENANT_A, key, expires_in=5)  # Under minimum

        call_kwargs = mock_client.generate_presigned_url.call_args
        assert call_kwargs[1]["ExpiresIn"] >= 60


# =============================================================================
# Legacy URL Detection
# =============================================================================


@pytest.mark.unit
class TestLegacyUrlDetection:
    """Verify legacy public URL detection."""

    def test_legacy_url_detected(self):
        # Simulate a legacy URL with short key prefix
        import backend.secure_storage as ss
        ss.B2_ENDPOINT_URL = "https://s3.us-east-005.backblazeb2.com"
        ss.B2_BUCKET_NAME = "ai-studio88"
        url = "https://s3.us-east-005.backblazeb2.com/ai-studio88/images/abc_photo.jpg"
        assert is_legacy_public_url(url) is True

    def test_empty_url_not_legacy(self):
        assert is_legacy_public_url("") is False

    def test_none_url_not_legacy(self):
        assert is_legacy_public_url(None) is False  # type: ignore


# =============================================================================
# Migration Helper
# =============================================================================


@pytest.mark.unit
class TestMigrationHelper:
    """Verify legacy key migration."""

    def test_migrate_preserves_filename(self):
        new_key = migrate_key_to_tenant("images/abc_photo.jpg", TENANT_A)
        assert new_key.startswith(TENANT_A + "/")
        assert "photo.jpg" in new_key

    def test_migrate_sanitizes_filename(self):
        new_key = migrate_key_to_tenant("old/path/../evil.txt", TENANT_A)
        # Should not contain traversal in the result
        assert ".." not in new_key


# =============================================================================
# Upload org_id injection
# =============================================================================


@pytest.mark.unit
class TestUploadOrgInjection:
    """Verify upload includes org metadata."""

    @patch("backend.secure_storage._get_client")
    def test_upload_sets_org_metadata(self, mock_client_fn):
        from backend.secure_storage import upload_private
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        key = f"{TENANT_A}/images/abc_photo.jpg"
        upload_private(TENANT_A, b"image data", key, "image/jpeg")

        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Metadata"]["org-id"] == TENANT_A
        assert call_kwargs["Key"] == key
