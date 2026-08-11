"""Production Gate ORM model.

Represents a production gate evaluation — the authoritative record of
whether a release passed all required checks before deployment.

This table is PLATFORM-LEVEL — it does NOT use TenantMixin (no org_id).
Each row captures a single gate evaluation run, its check results,
and the eventual approval (if all checks passed).

Key invariants:
    - Gate records are append-only — never modified after approval.
    - Each gate is linked to a Release Identity via release_identity_id.
    - Emergency gates have a 24-hour verification deadline.
    - All check results are stored as structured JSONB for auditability.

Validates: Requirements R83.1, R83.2, R83.6, R83.7, R83.8, R83.9
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class ProductionGate(Base, UUIDMixin):
    """Production gate evaluation — records gate check results and approval.

    Links to a ReleaseIdentity to ensure every gate passage has a traceable
    release identity (R83.1). Supports both full and emergency gate types.

    The checks column stores an array of check results, each containing:
        - check_name: str (e.g., "frontend_build")
        - passed: bool
        - evidence_url: str | None
        - message: str
        - checked_at: ISO timestamp

    Validates: R83.1, R83.2, R83.6, R83.7, R83.8, R83.9
    """

    __tablename__ = "production_gates"

    # ── Core fields ───────────────────────────────────────────────────────────

    release_identity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="FK to release_identities — binds gate to a specific release",
    )

    gate_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Gate evaluation type: 'full' or 'emergency'",
    )

    # ── Check results ─────────────────────────────────────────────────────────

    checks: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'[]'",
        comment="JSON array of check results (check_name, passed, evidence_url, message, checked_at)",
    )

    all_passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether all required checks passed for this gate type",
    )

    # ── Evidence and approval ─────────────────────────────────────────────────

    evidence_links: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'{}'",
        comment="JSON object mapping check names to evidence URLs/links",
    )

    approving_actor: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="UUID of the user or system that approved the gate passage",
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the gate was approved (None until all checks pass and actor approves)",
    )

    # ── Emergency release path ────────────────────────────────────────────────

    emergency_verification_due: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="For emergency gates: deadline for full verification (24h from approval)",
    )

    emergency_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether the emergency gate completed full post-release verification",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When this gate evaluation was initiated",
    )

    # ── Failure documentation (R83.5) ─────────────────────────────────────────

    failure_summary: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
        comment="Human-readable summary of failed checks and remediation paths",
    )

    __table_args__ = (
        Index("ix_production_gates_release_id", "release_identity_id"),
        Index("ix_production_gates_created", "created_at"),
        Index("ix_production_gates_type", "gate_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<ProductionGate(id={self.id}, "
            f"type={self.gate_type}, "
            f"all_passed={self.all_passed})>"
        )
