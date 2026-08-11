"""DisclosureAuditLog ORM model.

Persists every disclosure decision made at publish dispatch time.
Records what hooks were evaluated, which triggered, what policy
caused the trigger, and the exact text/tags applied to the content.

This provides the audit trail required for compliance (R80.6):
    - What disclosure was applied
    - What policy triggered it
    - When it was applied
    - To which post/asset/platform

Requirements: R80.6
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class DisclosureAuditLog(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Audit log entry for a disclosure decision at publish time.

    One row per hook evaluation per post dispatch. A single dispatch
    produces 4 rows (one per hook type), regardless of whether triggered.

    Requirements: R80.6
    """

    __tablename__ = "disclosure_audit_logs"

    # Reference to the scheduled post being dispatched
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # Reference to the asset being published
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Target platform (instagram, tiktok, youtube, etc.)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)

    # Hook type evaluated (AI_SYNTHETIC, SPONSORSHIP_COMMERCIAL, etc.)
    hook_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Whether this hook was triggered (disclosure was applied)
    triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # The disclosure text that was applied (None if not triggered)
    applied_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tags that were applied (None if not triggered)
    applied_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Reason why the hook was triggered or skipped
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Full hook metadata (C2PA details, platform config, etc.)
    metadata_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Snapshot of the workspace disclosure config at evaluation time
    config_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
