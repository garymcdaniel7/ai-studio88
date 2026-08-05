"""Training Dataset Lifecycle Tests (Story 091).

Proves: validation rules, readiness blocking, duplicate detection,
cross-tenant rejection, retry behavior, manifest creation, and counts.

Run with:
    pytest tests/unit/test_dataset_lifecycle.py -v
"""
from __future__ import annotations

import pytest

from backend.dataset_lifecycle import (
    ALLOWED_MIME_TYPES,
    MAX_DIMENSION,
    MAX_FILE_SIZE_BYTES,
    MIN_ACCEPTED_IMAGES,
    MIN_DIMENSION,
    MIN_FILE_SIZE_BYTES,
    DatasetImage,
    DatasetManifest,
    DatasetNotReadyError,
    ImageStatus,
    RejectionReason,
    TrainingDataset,
    add_image_to_dataset,
    assert_ready_for_training,
    create_manifest,
    exclude_image,
    mark_failed,
    retry_failed,
    validate_dataset,
    validate_image,
)


# =============================================================================
# Helpers
# =============================================================================


def _valid_image(**overrides) -> DatasetImage:
    defaults = {
        "org_id": "org-123",
        "filename": "photo_001.jpg",
        "storage_key": "/org-123/training/talent-1/ds-1/photo_001.jpg",
        "mime_type": "image/jpeg",
        "size_bytes": 500_000,
        "width": 1024,
        "height": 1024,
        "checksum_sha256": "abc123unique",
    }
    defaults.update(overrides)
    return DatasetImage(**defaults)


def _make_dataset(image_count: int = 0, org_id: str = "org-123") -> TrainingDataset:
    ds = TrainingDataset(org_id=org_id, talent_id="talent-1", user_id="user-1")
    for i in range(image_count):
        img = _valid_image(
            checksum_sha256=f"hash_{i}",
            filename=f"img_{i}.jpg",
            storage_key=f"/org-123/training/talent-1/ds/{i}.jpg",
        )
        add_image_to_dataset(ds, img)
    return ds


# =============================================================================
# Validation Rules
# =============================================================================


class TestValidationRules:

    @pytest.mark.unit
    def test_valid_image_accepted(self):
        """Image meeting all criteria is ACCEPTED."""
        img = _valid_image()
        result = validate_image(img, requesting_org_id="org-123")
        assert result.status == ImageStatus.ACCEPTED

    @pytest.mark.unit
    def test_invalid_mime_rejected(self):
        """Non-image MIME type is rejected."""
        img = _valid_image(mime_type="application/pdf")
        result = validate_image(img, requesting_org_id="org-123")
        assert result.status == ImageStatus.REJECTED
        assert result.rejection_reason == RejectionReason.INVALID_MIME

    @pytest.mark.unit
    def test_file_too_small_rejected(self):
        """File below minimum size is rejected."""
        img = _valid_image(size_bytes=1000)  # 1KB < 10KB minimum
        result = validate_image(img, requesting_org_id="org-123")
        assert result.status == ImageStatus.REJECTED
        assert result.rejection_reason == RejectionReason.FILE_TOO_SMALL

    @pytest.mark.unit
    def test_file_too_large_rejected(self):
        """File above maximum size is rejected."""
        img = _valid_image(size_bytes=25_000_000)  # 25MB > 20MB max
        result = validate_image(img, requesting_org_id="org-123")
        assert result.status == ImageStatus.REJECTED
        assert result.rejection_reason == RejectionReason.FILE_TOO_LARGE

    @pytest.mark.unit
    def test_dimensions_too_small_rejected(self):
        """Image below minimum dimensions is rejected."""
        img = _valid_image(width=256, height=256)
        result = validate_image(img, requesting_org_id="org-123")
        assert result.status == ImageStatus.REJECTED
        assert result.rejection_reason == RejectionReason.DIMENSIONS_TOO_SMALL

    @pytest.mark.unit
    def test_dimensions_too_large_rejected(self):
        """Image above maximum dimensions is rejected."""
        img = _valid_image(width=5000, height=5000)
        result = validate_image(img, requesting_org_id="org-123")
        assert result.status == ImageStatus.REJECTED
        assert result.rejection_reason == RejectionReason.DIMENSIONS_TOO_LARGE

    @pytest.mark.unit
    def test_missing_storage_key_rejected(self):
        """Image without confirmed storage is rejected."""
        img = _valid_image(storage_key="")
        result = validate_image(img, requesting_org_id="org-123")
        assert result.status == ImageStatus.REJECTED
        assert result.rejection_reason == RejectionReason.STORAGE_MISSING

    @pytest.mark.unit
    def test_webp_accepted(self):
        """WebP images are accepted."""
        img = _valid_image(mime_type="image/webp")
        result = validate_image(img, requesting_org_id="org-123")
        assert result.status == ImageStatus.ACCEPTED

    @pytest.mark.unit
    def test_png_accepted(self):
        """PNG images are accepted."""
        img = _valid_image(mime_type="image/png")
        result = validate_image(img, requesting_org_id="org-123")
        assert result.status == ImageStatus.ACCEPTED

    @pytest.mark.unit
    def test_validation_sets_timestamp(self):
        """Validation sets validated_at timestamp."""
        img = _valid_image()
        validate_image(img, requesting_org_id="org-123")
        assert img.validated_at is not None


# =============================================================================
# Duplicate Detection
# =============================================================================


class TestDuplicateDetection:

    @pytest.mark.unit
    def test_duplicate_checksum_rejected(self):
        """Image with checksum already in dataset is rejected."""
        img = _valid_image(checksum_sha256="duplicate_hash")
        existing = {"duplicate_hash"}
        result = validate_image(img, existing_checksums=existing, requesting_org_id="org-123")
        assert result.status == ImageStatus.REJECTED
        assert result.rejection_reason == RejectionReason.DUPLICATE_CHECKSUM

    @pytest.mark.unit
    def test_unique_checksum_accepted(self):
        """Image with unique checksum passes duplicate check."""
        img = _valid_image(checksum_sha256="unique_hash")
        existing = {"other_hash_1", "other_hash_2"}
        result = validate_image(img, existing_checksums=existing, requesting_org_id="org-123")
        assert result.status == ImageStatus.ACCEPTED

    @pytest.mark.unit
    def test_dataset_validate_detects_duplicates(self):
        """validate_dataset detects duplicates across images."""
        ds = TrainingDataset(org_id="org-123", talent_id="t-1", user_id="u-1")
        img1 = _valid_image(checksum_sha256="same_hash", filename="a.jpg")
        img2 = _valid_image(checksum_sha256="same_hash", filename="b.jpg")
        add_image_to_dataset(ds, img1)
        add_image_to_dataset(ds, img2)

        validate_dataset(ds)
        # First one accepted, second rejected as duplicate
        assert img1.status == ImageStatus.ACCEPTED
        assert img2.status == ImageStatus.REJECTED
        assert img2.rejection_reason == RejectionReason.DUPLICATE_CHECKSUM


# =============================================================================
# Cross-Tenant Rejection
# =============================================================================


class TestCrossTenant:

    @pytest.mark.unit
    def test_cross_tenant_image_rejected(self):
        """Image from different org is rejected."""
        img = _valid_image(org_id="org-other")
        result = validate_image(img, requesting_org_id="org-123")
        assert result.status == ImageStatus.REJECTED
        assert result.rejection_reason == RejectionReason.CROSS_TENANT

    @pytest.mark.unit
    def test_same_tenant_accepted(self):
        """Image from same org passes tenant check."""
        img = _valid_image(org_id="org-123")
        result = validate_image(img, requesting_org_id="org-123")
        assert result.status == ImageStatus.ACCEPTED


# =============================================================================
# Readiness Gate
# =============================================================================


class TestReadinessGate:

    @pytest.mark.unit
    def test_ready_with_enough_accepted(self):
        """Dataset with enough accepted images is ready."""
        ds = _make_dataset(image_count=MIN_ACCEPTED_IMAGES)
        validate_dataset(ds)
        assert ds.is_ready is True

    @pytest.mark.unit
    def test_not_ready_below_threshold(self):
        """Dataset below threshold is not ready."""
        ds = _make_dataset(image_count=2)
        validate_dataset(ds)
        assert ds.is_ready is False
        assert str(MIN_ACCEPTED_IMAGES) in ds.readiness_reason

    @pytest.mark.unit
    def test_not_ready_with_pending(self):
        """Dataset with pending images is not ready (even if count met)."""
        ds = _make_dataset(image_count=MIN_ACCEPTED_IMAGES)
        validate_dataset(ds)
        # Add one more pending
        add_image_to_dataset(ds, _valid_image(checksum_sha256="new_pending"))
        assert ds.is_ready is False
        assert "pending" in ds.readiness_reason

    @pytest.mark.unit
    def test_assert_ready_raises_on_not_ready(self):
        """assert_ready_for_training raises when not ready."""
        ds = _make_dataset(image_count=2)
        validate_dataset(ds)
        with pytest.raises(DatasetNotReadyError) as exc_info:
            assert_ready_for_training(ds)
        assert exc_info.value.accepted == 2
        assert exc_info.value.required == MIN_ACCEPTED_IMAGES

    @pytest.mark.unit
    def test_assert_ready_passes_when_ready(self):
        """assert_ready_for_training does not raise when ready."""
        ds = _make_dataset(image_count=MIN_ACCEPTED_IMAGES)
        validate_dataset(ds)
        assert_ready_for_training(ds)  # Should not raise

    @pytest.mark.unit
    def test_rejected_images_dont_count(self):
        """Rejected images don't count toward readiness."""
        ds = TrainingDataset(org_id="org-123", talent_id="t-1", user_id="u-1")
        # Add valid images below threshold
        for i in range(3):
            add_image_to_dataset(ds, _valid_image(checksum_sha256=f"ok_{i}"))
        # Add invalid images (won't count)
        for i in range(10):
            add_image_to_dataset(ds, _valid_image(
                checksum_sha256=f"bad_{i}", mime_type="application/pdf",
            ))
        validate_dataset(ds)
        assert ds.accepted_count == 3
        assert ds.rejected_count == 10
        assert ds.is_ready is False


# =============================================================================
# Retry
# =============================================================================


class TestRetry:

    @pytest.mark.unit
    def test_retry_resets_failed_to_pending(self):
        """retry_failed resets FAILED images to PENDING."""
        ds = _make_dataset(image_count=3)
        mark_failed(ds, ds.images[0].image_id, "Storage timeout")
        mark_failed(ds, ds.images[1].image_id, "Network error")

        retried = retry_failed(ds)
        assert len(retried) == 2
        assert all(img.status == ImageStatus.PENDING for img in retried)
        assert retried[0].retry_count == 1

    @pytest.mark.unit
    def test_retry_increments_counter(self):
        """Each retry increments retry_count."""
        ds = _make_dataset(image_count=1)
        mark_failed(ds, ds.images[0].image_id, "err")
        retry_failed(ds)
        mark_failed(ds, ds.images[0].image_id, "err again")
        retry_failed(ds)
        assert ds.images[0].retry_count == 2

    @pytest.mark.unit
    def test_retry_only_affects_failed(self):
        """retry_failed doesn't touch ACCEPTED or REJECTED images."""
        ds = _make_dataset(image_count=3)
        validate_dataset(ds)
        # Manually mark one as failed after validation
        ds.images[0].status = ImageStatus.FAILED
        ds.images[0].error_message = "late failure"

        retried = retry_failed(ds)
        assert len(retried) == 1
        assert ds.images[1].status == ImageStatus.ACCEPTED  # Unchanged
        assert ds.images[2].status == ImageStatus.ACCEPTED  # Unchanged


# =============================================================================
# Exclusion
# =============================================================================


class TestExclusion:

    @pytest.mark.unit
    def test_exclude_sets_status(self):
        """exclude_image marks image as EXCLUDED."""
        ds = _make_dataset(image_count=3)
        validate_dataset(ds)
        result = exclude_image(ds, ds.images[1].image_id)
        assert result is not None
        assert result.status == ImageStatus.EXCLUDED

    @pytest.mark.unit
    def test_excluded_not_counted_as_accepted(self):
        """Excluded images don't count toward accepted."""
        ds = _make_dataset(image_count=MIN_ACCEPTED_IMAGES)
        validate_dataset(ds)
        assert ds.accepted_count == MIN_ACCEPTED_IMAGES
        exclude_image(ds, ds.images[0].image_id)
        assert ds.accepted_count == MIN_ACCEPTED_IMAGES - 1

    @pytest.mark.unit
    def test_exclude_nonexistent_returns_none(self):
        """Excluding non-existent image returns None."""
        ds = _make_dataset(image_count=1)
        result = exclude_image(ds, "ghost-id")
        assert result is None


# =============================================================================
# Manifest
# =============================================================================


class TestManifest:

    @pytest.mark.unit
    def test_manifest_only_includes_accepted(self):
        """Manifest contains only ACCEPTED images."""
        ds = _make_dataset(image_count=6)
        validate_dataset(ds)
        # Reject one, exclude another
        ds.images[0].status = ImageStatus.REJECTED
        ds.images[1].status = ImageStatus.EXCLUDED

        manifest = create_manifest(ds)
        assert manifest.image_count == 4  # 6 - 1 rejected - 1 excluded

    @pytest.mark.unit
    def test_manifest_has_storage_keys(self):
        """Manifest images include storage_key and checksum."""
        ds = _make_dataset(image_count=MIN_ACCEPTED_IMAGES)
        validate_dataset(ds)
        manifest = create_manifest(ds)
        for img_entry in manifest.accepted_images:
            assert img_entry["storage_key"]
            assert img_entry["checksum_sha256"]

    @pytest.mark.unit
    def test_manifest_total_size(self):
        """Manifest records total size in bytes."""
        ds = _make_dataset(image_count=3)
        validate_dataset(ds)
        manifest = create_manifest(ds)
        assert manifest.total_size_bytes == 500_000 * 3

    @pytest.mark.unit
    def test_manifest_serializable(self):
        """Manifest.to_dict() is JSON-serializable."""
        import json
        ds = _make_dataset(image_count=MIN_ACCEPTED_IMAGES)
        validate_dataset(ds)
        manifest = create_manifest(ds)
        json.dumps(manifest.to_dict())


# =============================================================================
# Counts
# =============================================================================


class TestCounts:

    @pytest.mark.unit
    def test_counts_derived_from_status(self):
        """All counts are derived from actual image statuses."""
        ds = TrainingDataset(org_id="org-1", talent_id="t-1", user_id="u-1")
        for i in range(3):
            img = _valid_image(checksum_sha256=f"a_{i}")
            img.status = ImageStatus.ACCEPTED
            ds.images.append(img)
        for i in range(2):
            img = _valid_image(checksum_sha256=f"r_{i}")
            img.status = ImageStatus.REJECTED
            ds.images.append(img)
        img = _valid_image(checksum_sha256="f_0")
        img.status = ImageStatus.FAILED
        ds.images.append(img)

        assert ds.accepted_count == 3
        assert ds.rejected_count == 2
        assert ds.failed_count == 1
        assert ds.total_count == 6

    @pytest.mark.unit
    def test_dataset_serializable(self):
        """TrainingDataset.to_dict() is JSON-serializable."""
        import json
        ds = _make_dataset(image_count=3)
        validate_dataset(ds)
        json.dumps(ds.to_dict())
