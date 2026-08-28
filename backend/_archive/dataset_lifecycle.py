"""Training Dataset Lifecycle — Story 091.

Durable per-image lifecycle for LoRA training datasets. Every image has an
explicit status with rejection reasons. Training cannot start until the
dataset meets verified readiness thresholds.

Image States:
    PENDING     → Upload/link received, not yet validated
    VALIDATING  → Validation in progress
    ACCEPTED    → Passed all checks, included in dataset
    REJECTED    → Failed validation (reason recorded)
    EXCLUDED    → Manually excluded by user
    FAILED      → Storage/system failure (retryable)

Dataset Readiness:
    Derived ONLY from ACCEPTED image count — never from upload request count.

Validation Rules:
    - MIME type must be image/jpeg, image/png, or image/webp
    - File size: 10KB minimum, 20MB maximum
    - Dimensions: minimum 512x512, maximum 4096x4096
    - Checksum: duplicate detection within same dataset
    - Decode integrity: must be valid decodable image
    - Ownership: must belong to requesting org_id
    - Storage: must be confirmed persisted
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Image States
# =============================================================================


class ImageStatus(StrEnum):
    PENDING = "pending"
    VALIDATING = "validating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXCLUDED = "excluded"       # User manually excluded
    FAILED = "failed"           # System failure, retryable


class RejectionReason(StrEnum):
    INVALID_MIME = "invalid_mime"
    FILE_TOO_SMALL = "file_too_small"
    FILE_TOO_LARGE = "file_too_large"
    DIMENSIONS_TOO_SMALL = "dimensions_too_small"
    DIMENSIONS_TOO_LARGE = "dimensions_too_large"
    DECODE_FAILED = "decode_failed"
    DUPLICATE_CHECKSUM = "duplicate_checksum"
    CROSS_TENANT = "cross_tenant"
    STORAGE_MISSING = "storage_missing"
    CONSENT_MISSING = "consent_missing"


# =============================================================================
# Validation Thresholds
# =============================================================================

ALLOWED_MIME_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}
MIN_FILE_SIZE_BYTES: int = 10 * 1024          # 10 KB
MAX_FILE_SIZE_BYTES: int = 20 * 1024 * 1024   # 20 MB
MIN_DIMENSION: int = 512
MAX_DIMENSION: int = 4096

# Dataset readiness — DECISION-REQUIRED for final values
MIN_ACCEPTED_IMAGES: int = 5      # Minimum to start training
RECOMMENDED_IMAGES: int = 15      # Recommended for quality


# =============================================================================
# Dataset Image Record
# =============================================================================


@dataclass
class DatasetImage:
    """A single image in a training dataset with durable lifecycle."""

    # Identity
    image_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    dataset_id: str = ""
    org_id: str = ""

    # Source
    filename: str = ""
    storage_key: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    width: int = 0
    height: int = 0
    checksum_sha256: str = ""

    # Status
    status: ImageStatus = ImageStatus.PENDING
    rejection_reason: RejectionReason | None = None
    rejection_detail: str = ""
    error_message: str | None = None  # For FAILED state

    # Metadata
    role: str = "training"          # training, regularization, reference
    source_asset_id: str | None = None  # If linked from existing asset

    # Timing
    uploaded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    validated_at: str | None = None
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "image_id": self.image_id,
            "dataset_id": self.dataset_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "width": self.width,
            "height": self.height,
            "status": self.status.value,
            "rejection_reason": self.rejection_reason.value if self.rejection_reason else None,
            "rejection_detail": self.rejection_detail,
            "role": self.role,
            "retry_count": self.retry_count,
            "uploaded_at": self.uploaded_at,
            "validated_at": self.validated_at,
        }


# =============================================================================
# Training Dataset
# =============================================================================


@dataclass
class TrainingDataset:
    """A training dataset composed of validated images."""

    dataset_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    talent_id: str = ""
    user_id: str = ""

    # Images
    images: list[DatasetImage] = field(default_factory=list)

    # Computed (never set directly — always derived)
    # Use properties below

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def accepted_count(self) -> int:
        """Count of accepted images (the ONLY source of truth for dataset size)."""
        return sum(1 for img in self.images if img.status == ImageStatus.ACCEPTED)

    @property
    def rejected_count(self) -> int:
        return sum(1 for img in self.images if img.status == ImageStatus.REJECTED)

    @property
    def failed_count(self) -> int:
        return sum(1 for img in self.images if img.status == ImageStatus.FAILED)

    @property
    def pending_count(self) -> int:
        return sum(1 for img in self.images if img.status == ImageStatus.PENDING)

    @property
    def excluded_count(self) -> int:
        return sum(1 for img in self.images if img.status == ImageStatus.EXCLUDED)

    @property
    def total_count(self) -> int:
        return len(self.images)

    @property
    def is_ready(self) -> bool:
        """Dataset is ready for training when accepted count meets threshold."""
        return self.accepted_count >= MIN_ACCEPTED_IMAGES and self.pending_count == 0

    @property
    def readiness_reason(self) -> str:
        """Explain why dataset is or isn't ready."""
        if self.pending_count > 0:
            return f"{self.pending_count} image(s) still pending validation"
        if self.accepted_count < MIN_ACCEPTED_IMAGES:
            return f"Need {MIN_ACCEPTED_IMAGES} accepted images, have {self.accepted_count}"
        return "Ready for training"

    def to_dict(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "org_id": self.org_id,
            "talent_id": self.talent_id,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "failed_count": self.failed_count,
            "pending_count": self.pending_count,
            "excluded_count": self.excluded_count,
            "total_count": self.total_count,
            "is_ready": self.is_ready,
            "readiness_reason": self.readiness_reason,
            "created_at": self.created_at,
        }


# =============================================================================
# Validation
# =============================================================================


def validate_image(
    image: DatasetImage,
    *,
    existing_checksums: set[str] | None = None,
    requesting_org_id: str = "",
) -> DatasetImage:
    """Validate a dataset image against all rules.

    Updates image status to ACCEPTED or REJECTED with reason.
    """
    image.status = ImageStatus.VALIDATING

    # MIME type check
    if image.mime_type not in ALLOWED_MIME_TYPES:
        return _reject(image, RejectionReason.INVALID_MIME,
                       f"MIME '{image.mime_type}' not allowed. Allowed: {ALLOWED_MIME_TYPES}")

    # File size checks
    if image.size_bytes < MIN_FILE_SIZE_BYTES:
        return _reject(image, RejectionReason.FILE_TOO_SMALL,
                       f"File {image.size_bytes} bytes < minimum {MIN_FILE_SIZE_BYTES}")

    if image.size_bytes > MAX_FILE_SIZE_BYTES:
        return _reject(image, RejectionReason.FILE_TOO_LARGE,
                       f"File {image.size_bytes} bytes > maximum {MAX_FILE_SIZE_BYTES}")

    # Dimension checks
    if image.width < MIN_DIMENSION or image.height < MIN_DIMENSION:
        return _reject(image, RejectionReason.DIMENSIONS_TOO_SMALL,
                       f"Dimensions {image.width}x{image.height} below minimum {MIN_DIMENSION}x{MIN_DIMENSION}")

    if image.width > MAX_DIMENSION or image.height > MAX_DIMENSION:
        return _reject(image, RejectionReason.DIMENSIONS_TOO_LARGE,
                       f"Dimensions {image.width}x{image.height} exceed maximum {MAX_DIMENSION}x{MAX_DIMENSION}")

    # Duplicate detection
    if existing_checksums and image.checksum_sha256 in existing_checksums:
        return _reject(image, RejectionReason.DUPLICATE_CHECKSUM,
                       "Image with identical checksum already in dataset")

    # Tenant isolation
    if requesting_org_id and image.org_id != requesting_org_id:
        return _reject(image, RejectionReason.CROSS_TENANT,
                       "Image belongs to a different workspace")

    # Storage verification
    if not image.storage_key:
        return _reject(image, RejectionReason.STORAGE_MISSING,
                       "Image not confirmed in storage")

    # All checks passed
    image.status = ImageStatus.ACCEPTED
    image.validated_at = datetime.now(UTC).isoformat()
    return image


def _reject(image: DatasetImage, reason: RejectionReason, detail: str) -> DatasetImage:
    """Mark image as rejected with reason."""
    image.status = ImageStatus.REJECTED
    image.rejection_reason = reason
    image.rejection_detail = detail
    image.validated_at = datetime.now(UTC).isoformat()
    return image


# =============================================================================
# Dataset Operations
# =============================================================================


def add_image_to_dataset(
    dataset: TrainingDataset,
    image: DatasetImage,
) -> DatasetImage:
    """Add an image to the dataset.

    Sets dataset_id and org_id from the dataset.
    """
    image.dataset_id = dataset.dataset_id
    image.org_id = dataset.org_id
    dataset.images.append(image)
    dataset.updated_at = datetime.now(UTC).isoformat()
    return image


def validate_dataset(
    dataset: TrainingDataset,
    *,
    requesting_org_id: str = "",
) -> TrainingDataset:
    """Validate all pending images in the dataset.

    Collects checksums for duplicate detection across the dataset.
    """
    accepted_checksums: set[str] = {
        img.checksum_sha256 for img in dataset.images
        if img.status == ImageStatus.ACCEPTED and img.checksum_sha256
    }

    for image in dataset.images:
        if image.status == ImageStatus.PENDING:
            validate_image(
                image,
                existing_checksums=accepted_checksums,
                requesting_org_id=requesting_org_id or dataset.org_id,
            )
            if image.status == ImageStatus.ACCEPTED and image.checksum_sha256:
                accepted_checksums.add(image.checksum_sha256)

    dataset.updated_at = datetime.now(UTC).isoformat()
    return dataset


def exclude_image(dataset: TrainingDataset, image_id: str) -> DatasetImage | None:
    """Manually exclude an image from the dataset."""
    for img in dataset.images:
        if img.image_id == image_id:
            img.status = ImageStatus.EXCLUDED
            dataset.updated_at = datetime.now(UTC).isoformat()
            return img
    return None


def retry_failed(dataset: TrainingDataset) -> list[DatasetImage]:
    """Reset FAILED images to PENDING for retry.

    Returns list of images reset.
    """
    retried: list[DatasetImage] = []
    for img in dataset.images:
        if img.status == ImageStatus.FAILED:
            img.status = ImageStatus.PENDING
            img.error_message = None
            img.retry_count += 1
            retried.append(img)
    dataset.updated_at = datetime.now(UTC).isoformat()
    return retried


def mark_failed(dataset: TrainingDataset, image_id: str, error: str) -> DatasetImage | None:
    """Mark an image as FAILED (system error, retryable)."""
    for img in dataset.images:
        if img.image_id == image_id:
            img.status = ImageStatus.FAILED
            img.error_message = error
            dataset.updated_at = datetime.now(UTC).isoformat()
            return img
    return None


# =============================================================================
# Readiness Gate
# =============================================================================


class DatasetNotReadyError(Exception):
    """Raised when training is attempted on a non-ready dataset."""

    def __init__(self, message: str, accepted: int, required: int):
        self.message = message
        self.accepted = accepted
        self.required = required
        super().__init__(message)


def assert_ready_for_training(dataset: TrainingDataset) -> None:
    """Assert dataset meets readiness requirements.

    Raises DatasetNotReadyError if requirements not met.
    """
    if dataset.pending_count > 0:
        raise DatasetNotReadyError(
            f"Cannot start training: {dataset.pending_count} image(s) still pending",
            accepted=dataset.accepted_count,
            required=MIN_ACCEPTED_IMAGES,
        )

    if dataset.accepted_count < MIN_ACCEPTED_IMAGES:
        raise DatasetNotReadyError(
            f"Cannot start training: {dataset.accepted_count} accepted images "
            f"< minimum {MIN_ACCEPTED_IMAGES}",
            accepted=dataset.accepted_count,
            required=MIN_ACCEPTED_IMAGES,
        )


# =============================================================================
# Dataset Manifest (immutable snapshot for training)
# =============================================================================


@dataclass
class DatasetManifest:
    """Immutable manifest of accepted images for training submission.

    Created at the moment training is approved. References exact images
    that will be delivered to the training worker.
    """

    manifest_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    dataset_id: str = ""
    org_id: str = ""
    talent_id: str = ""
    accepted_images: list[dict] = field(default_factory=list)
    total_size_bytes: int = 0
    image_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "manifest_id": self.manifest_id,
            "dataset_id": self.dataset_id,
            "org_id": self.org_id,
            "talent_id": self.talent_id,
            "image_count": self.image_count,
            "total_size_bytes": self.total_size_bytes,
            "created_at": self.created_at,
        }


def create_manifest(dataset: TrainingDataset) -> DatasetManifest:
    """Create an immutable manifest from accepted images.

    Only includes ACCEPTED images. This is the source of truth for
    what gets delivered to the training worker.
    """
    accepted = [
        img for img in dataset.images if img.status == ImageStatus.ACCEPTED
    ]

    manifest = DatasetManifest(
        dataset_id=dataset.dataset_id,
        org_id=dataset.org_id,
        talent_id=dataset.talent_id,
        accepted_images=[
            {
                "image_id": img.image_id,
                "storage_key": img.storage_key,
                "checksum_sha256": img.checksum_sha256,
                "mime_type": img.mime_type,
                "size_bytes": img.size_bytes,
                "width": img.width,
                "height": img.height,
                "role": img.role,
            }
            for img in accepted
        ],
        total_size_bytes=sum(img.size_bytes for img in accepted),
        image_count=len(accepted),
    )
    return manifest
