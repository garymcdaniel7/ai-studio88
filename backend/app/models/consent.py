"""ConsentRecord ORM model.

A versioned, scoped, revocable consent record for AI Talent.
Consent is NOT a boolean flag — it is a first-class subsystem with provenance
tracking and enforcement through the Governance Boundary.

Requirements: R10.2, R10.3, R10.12, A2-004
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class ConsentRecord(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A single grant of consent for a specific talent and scope set.

    Consent records are immutable once created (no UPDATE on core fields).
    Revocation sets revoked_at + revocation_reason but preserves the record
    for audit purposes.

    Scopes:
        LIKENESS, VOICE, TRAINING, GENERATION, ADULT_CONTENT,
        COMMERCIAL, PUBLISHING, CLIENT_WORK

    Enforcement:
        - Missing/expired/revoked consent → 403 CONSENT_REQUIRED or CONSENT_REVOKED
        - FICTIONAL identity_classification talent exempt from generation consent
        - Scope-specific evaluation: only relevant scopes checked per operation

    Requirements: R10.2, R10.3, R10.12, 39.6, A2-004
    """

    __tablename__ = "consent_records"

    talent_id: Mapped["uuid.UUID"] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False
    )
    evidence_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    grantor_identity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default="now()"
    )
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    restrictions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    provenance: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    verification_state: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unverified"
    )

    @property
    def is_active(self) -> bool:
        """Check if this consent record is currently active (not revoked, not expired)."""
        from datetime import UTC, datetime as dt

        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= dt.now(UTC):
            return False
        return True
