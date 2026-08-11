"""External Deletion Tracking ORM model.

Tracks the lifecycle of asset deletions from external storage providers
(Backblaze B2, S3, etc.). Ensures the platform never claims an external
object is deleted unless deletion has been confirmed by the provider.

States:
    REMOVED_FROM_STUDIO       — DB soft-deleted, storage untouched
    EXTERNAL_DELETION_REQUESTED — Storage API delete call issued
    EXTERNAL_DELETION_CONFIRMED — Storage confirms removal (HEAD → 404)
    EXTERNAL_DELETION_FAILED    — Storage API failed, retry needed
    RETAINED_LEGAL_HOLD         — Deletion blocked by legal hold
    RETAINED_BACKUP             — May exist in backups per retention policy

Validates: Requirements R105.1, R105.2, R105.3
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class DeletionState(str, enum.Enum):
    """External deletion propagation states per R105.1."""

    REMOVED_FROM_STUDIO = "removed_from_studio"
    EXTERNAL_DELETION_REQUESTED = "external_deletion_requested"
    EXTERNAL_DELETION_CONFIRMED = "external_deletion_confirmed"
    EXTERNAL_DELETION_FAILED = "external_deletion_failed"
    RETAINED_LEGAL_HOLD = "retained_legal_hold"
    RETAINED_BACKUP = "retained_backup"


# Maximum retry attempts before surfacing to Platform Operators
MAX_RETRY_ATTEMPTS = 5


class ExternalDeletionTracking(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Tracks deletion propagation to external storage providers.

    Each record represents a single asset's deletion lifecycle through
    external storage. The platform NEVER claims an asset is externally
    deleted unless the provider confirms removal (R105.2).

    Failed deletions are retried with exponential backoff. After
    MAX_RETRY_ATTEMPTS failures, a notification is surfaced to
    Platform Operators for investigation (R105.3).
    """

    __tablename__ = "external_deletion_tracking"

    # The asset being deleted
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    # Storage key in the external provider (e.g., B2 object key)
    storage_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Current deletion state
    deletion_state: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=DeletionState.REMOVED_FROM_STUDIO.value,
        server_default=DeletionState.REMOVED_FROM_STUDIO.value,
    )

    # External storage provider name (e.g., "b2", "s3", "r2")
    provider: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="b2",
    )

    # Timestamps for lifecycle tracking
    requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # Last error message from failed deletion attempt
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Legal hold reference (case ID, if deletion is blocked)
    legal_hold_ref: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    __table_args__ = (
        Index("ix_ext_deletion_org_state", "org_id", "deletion_state"),
        Index("ix_ext_deletion_asset", "asset_id"),
        Index("ix_ext_deletion_org_failed", "org_id", "deletion_state",
              postgresql_where=("deletion_state = 'external_deletion_failed'")),
    )

    def __repr__(self) -> str:
        return (
            f"<ExternalDeletionTracking(id={self.id}, asset_id={self.asset_id}, "
            f"state={self.deletion_state}, provider={self.provider}, "
            f"retry_count={self.retry_count})>"
        )
