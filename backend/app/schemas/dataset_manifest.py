"""Pydantic v2 schemas for Training Dataset Manifests.

Provides request/response validation for the immutable dataset manifest
system. Dataset manifests are immutable records capturing exact files,
checksums, roles, and provenance used for a training job.

Once created, a manifest is NEVER modified. Verification detects
files that have been deleted or consent that has been revoked since
manifest creation.

Validates: Requirements R61.1, R61.2, R61.3, R61.4, R61.5, R61.6
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


# =============================================================================
# Enums
# =============================================================================


class AssetRole(str, enum.Enum):
    """Role of a file within a training dataset."""

    TRAINING_IMAGE = "training_image"
    REGULARIZATION_IMAGE = "regularization_image"
    CAPTION_FILE = "caption_file"
    MASK_IMAGE = "mask_image"
    METADATA = "metadata"


class ManifestFileProvenance(str, enum.Enum):
    """Provenance of a file in the manifest."""

    USER_UPLOAD = "user_upload"
    PLATFORM_GENERATED = "platform_generated"
    EXTERNAL_IMPORT = "external_import"
    AI_GENERATED = "ai_generated"


# =============================================================================
# Nested Schemas for JSONB Fields
# =============================================================================


class ManifestFileEntry(BaseSchema):
    """A single file entry within a dataset manifest.

    Each file has a unique reference, checksum for integrity verification,
    an asset role describing its purpose in training, and provenance.
    """

    file_ref: str = Field(
        min_length=1,
        max_length=500,
        description="Unique file reference identifier (asset_id or filename)",
    )
    storage_key: str = Field(
        min_length=1,
        max_length=1000,
        description="B2 storage key for the file",
    )
    sha256_checksum: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
        description="SHA-256 hex digest of the file contents",
    )
    asset_role: AssetRole = Field(
        description="Role of this file in the training dataset",
    )
    file_size_bytes: int = Field(
        ge=1,
        description="File size in bytes",
    )
    content_type: str = Field(
        min_length=1,
        max_length=100,
        description="MIME type of the file",
    )
    provenance: ManifestFileProvenance = Field(
        description="How this file was sourced",
    )


# =============================================================================
# Request Schemas
# =============================================================================


class DatasetManifestCreateRequest(BaseSchema):
    """Request schema for creating a dataset manifest.

    org_id is NEVER accepted from client — resolved from TenantContext.
    Once created, the manifest is immutable — no update endpoint exists.
    """

    talent_id: UUID = Field(
        description="Talent this training dataset is for",
    )
    files: list[ManifestFileEntry] = Field(
        min_length=1,
        max_length=10000,
        description="Array of file entries with checksums and roles",
    )
    consent_record_ids: list[UUID] = Field(
        default_factory=list,
        max_length=100,
        description="Consent record UUIDs authorising this training data usage",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class ManifestFileResponse(BaseSchema):
    """Response representation of a single manifest file entry."""

    file_ref: str
    storage_key: str
    sha256_checksum: str
    asset_role: str
    file_size_bytes: int
    content_type: str
    provenance: str


class DatasetManifestResponse(BaseSchema):
    """Response schema for a single dataset manifest."""

    id: UUID
    org_id: UUID
    version: UUID
    talent_id: UUID
    manifest_files: list[ManifestFileResponse]
    consent_record_ids: list[UUID]
    total_file_count: int
    total_size_bytes: int
    is_valid: bool
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DatasetManifestListResponse(BaseSchema):
    """Paginated list of dataset manifests."""

    items: list[DatasetManifestResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


# =============================================================================
# Verification Result Schema
# =============================================================================


class ManifestFileIssue(BaseSchema):
    """A single file-level issue detected during verification."""

    file_ref: str
    storage_key: str
    issue_type: str = Field(
        description="Type of issue: 'file_deleted', 'checksum_mismatch', "
        "'consent_revoked', 'file_inaccessible'",
    )
    detail: str = Field(
        description="Human-readable description of the issue",
    )


class ManifestVerificationResult(BaseSchema):
    """Result of verifying a dataset manifest for integrity and consent.

    If is_valid is False, the training job MUST be rejected.
    """

    manifest_id: UUID
    is_valid: bool
    issues: list[ManifestFileIssue] = Field(default_factory=list)
    files_checked: int = Field(ge=0)
    files_passed: int = Field(ge=0)
    consent_valid: bool
    verified_at: datetime


# =============================================================================
# Comparison Schema (R61.6)
# =============================================================================


class ManifestComparisonEntry(BaseSchema):
    """A single difference between two manifest versions."""

    change_type: str = Field(
        description="Type of change: 'added', 'removed', 'checksum_changed', 'role_changed'",
    )
    file_ref: str
    storage_key: str | None = None
    old_value: str | None = None
    new_value: str | None = None


class ManifestComparisonResult(BaseSchema):
    """Result of comparing two dataset manifest versions."""

    manifest_a_id: UUID
    manifest_b_id: UUID
    files_added: int = Field(ge=0)
    files_removed: int = Field(ge=0)
    files_changed: int = Field(ge=0)
    differences: list[ManifestComparisonEntry] = Field(default_factory=list)
