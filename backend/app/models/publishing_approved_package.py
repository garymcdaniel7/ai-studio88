"""PublishingApprovedPackage ORM model.

An immutable record binding the exact state of a publishing package at
the moment of approval. Any change to a bound element after approval
invalidates the record and requires re-evaluation.

Bound elements:
    - Asset version (checksum)
    - Caption
    - Destination (platform, account, post_type)
    - Schedule
    - Targeting
    - Consent state snapshot
    - Disclosure settings
    - Policy state snapshot

Requirements: R79.1, R79.2, R79.3, R79.4, R79.5, R79.6
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class PublishingApprovedPackage(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Immutable publishing approval record.

    Once created, the core snapshot fields are NEVER modified. Invalidation
    sets invalidated_at + invalidation_reason and flips is_valid to False.

    The package_hash is a SHA-256 hash of the canonical JSON representation
    of all bound elements. This enables fast equality checks at publish time.

    Requirements: R79.1, R79.2, R79.3, R79.4, R79.5, R79.6
    """

    __tablename__ = "publishing_approved_packages"

    # Asset binding
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    asset_checksum: Mapped[str] = mapped_column(
        String(128), nullable=False
    )

    # Content binding
    caption: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Structured snapshot fields (stored as JSONB for schema evolution)
    destination: Mapped[dict] = mapped_column(JSONB, nullable=False)
    schedule: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    targeting: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    consent_state: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    disclosure_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    policy_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Optional references
    talent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Package integrity
    package_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )

    # Approval metadata
    approved_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Invalidation tracking
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invalidation_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    is_valid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    @property
    def is_active(self) -> bool:
        """Check if this approval is still valid (not invalidated)."""
        return self.is_valid and self.invalidated_at is None
