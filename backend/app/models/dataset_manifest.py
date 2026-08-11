"""Dataset Manifest ORM model.

An immutable, versioned record of exact files, checksums, roles, and
provenance used for a training job. Once created, a manifest is NEVER
modified — enabling full reproducibility, consent traceability, and
worker-side integrity verification.

Every training job references the exact Dataset_Manifest version used.
Workers verify downloaded files match manifest checksums before starting
any paid GPU training.

Validates: Requirements R61.1, R61.2, R61.3, R61.4, R61.5, R61.6
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class DatasetManifest(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Immutable training dataset manifest.

    Captures the exact files, checksums, asset roles, provenance, and
    consent references used for a training job. Once stored, no field
    may be modified. Integrity verification is performed at job dispatch
    time — if any referenced file has been deleted or consent revoked,
    the training job is rejected.

    Always scoped to org_id. Cross-tenant access returns 404.
    """

    __tablename__ = "dataset_manifests"

    # Unique version identifier (UUID, not incremental)
    version: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4,
        comment="Unique immutable version identifier for this manifest",
    )

    # Talent relationship
    talent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Talent this training dataset is for",
    )

    # File entries (JSONB array of file references with checksums)
    manifest_files: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment=(
            "Array of file entries: [{file_ref, storage_key, sha256_checksum, "
            "asset_role, file_size_bytes, content_type, provenance}]"
        ),
    )

    # Consent references
    consent_record_ids: Mapped[list] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
        comment="UUIDs of consent records authorising this training data usage",
    )

    # Computed summary fields
    total_file_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Total number of files in this manifest",
    )

    total_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Sum of all file sizes in bytes",
    )

    # Validity tracking (for post-creation invalidation detection)
    is_valid: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Whether this manifest is still valid (files exist, consent active)",
    )

    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Timestamp when manifest was detected as invalid",
    )

    invalidation_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        default=None,
        comment="Reason manifest was invalidated (file deleted, consent revoked)",
    )

    # Audit: who created this manifest
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="User who created this manifest",
    )
