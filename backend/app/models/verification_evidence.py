"""Verification Evidence ORM model.

Represents a single independent verification evidence record — proof that
a requirement was verified by a specific method at a specific time.

This table is PLATFORM-LEVEL — it does NOT use TenantMixin (no org_id).
Verification evidence is tracked at the platform infrastructure level,
not per-tenant.

Key invariants:
    - Evidence records are append-only — never modified after creation.
    - Developer assertion alone is insufficient for PRODUCTION classification.
    - At least two independent mechanisms required per R82.3.
    - Each record captures method, evidence location, date, and verifier.

Validates: Requirements R82.1, R82.2, R82.3, R82.4, R82.5, R82.6
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class VerificationEvidence(Base, UUIDMixin):
    """Verification evidence record — proof that a requirement was independently verified.

    Links requirement_id to verification method, evidence location, result,
    timestamp, and verifier identity. Used to determine whether a feature
    can be classified as PRODUCTION (requires independent non-developer evidence).

    Validates: R82.1, R82.2, R82.3, R82.4, R82.5, R82.6
    """

    __tablename__ = "verification_evidence"

    # ── Core fields ───────────────────────────────────────────────────────────

    requirement_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Requirement identifier (e.g. 'R82.1', 'R2.14')",
    )

    feature_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Feature being verified (e.g. 'tenant_isolation', 'auth_enforcement')",
    )

    method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Verification method: automated_test, human_review, hermes_inspection, adversarial_test",
    )

    evidence_location: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        comment="Path/URL to evidence (test file, CI run, sign-off doc)",
    )

    evidence_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type: test_suite, ci_run, manual_sign_off, red_team_report",
    )

    # ── Result ────────────────────────────────────────────────────────────────

    passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="Whether the verification passed",
    )

    # ── Timing and identity ───────────────────────────────────────────────────

    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the verification was performed",
    )

    verifier_identity: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Who verified: user email, 'hermes', 'red_team', system name",
    )

    # ── Optional notes ────────────────────────────────────────────────────────

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional notes about this verification",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When this record was created",
    )

    __table_args__ = (
        Index("ix_verification_evidence_requirement", "requirement_id"),
        Index("ix_verification_evidence_feature", "feature_name"),
        Index("ix_verification_evidence_method", "method"),
        Index("ix_verification_evidence_verified_at", "verified_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<VerificationEvidence(id={self.id}, "
            f"req={self.requirement_id}, "
            f"method={self.method}, "
            f"passed={self.passed})>"
        )
