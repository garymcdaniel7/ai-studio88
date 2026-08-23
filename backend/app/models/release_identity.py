"""Release Identity ORM model.

Represents an immutable record linking all artifacts that constitute a
production release: commit SHA, frontend/backend build artifacts,
migration set, configuration version, model manifest, and deployment IDs.

This table is PLATFORM-LEVEL — it does NOT use TenantMixin (no org_id).
Each row is an immutable snapshot created during deployment and never
modified after creation.

Key invariants:
    - Once created, a release identity record is NEVER updated or deleted.
    - Exactly one record has is_current=True at any given time.
    - Deployments that cannot produce a complete Release_Identity are rejected.
    - The record is surfaced in /ready, structured logs, job records, and
      error reports for full traceability.

Validates: Requirements R72.1, R72.2, R72.3, R72.4, R72.5, R72.6
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class ReleaseIdentity(Base, UUIDMixin):
    """Immutable release identity — one record per production deployment.

    Links: commit SHA, frontend artifact, backend artifact, migration set,
    config version, model manifest, and deployment IDs into a single
    traceable identity.

    This table is append-only. Records are never updated or deleted.
    The is_current flag is managed atomically — only one row may be
    True at any given time (enforced by partial unique index).

    Validates: R72.1, R72.2, R72.3, R72.4, R72.5, R72.6
    """

    __tablename__ = "release_identities"

    # ── Core identity fields ──────────────────────────────────────────────────

    git_commit_sha: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        comment="Full 40-character git commit SHA for this release",
    )

    frontend_artifact: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Frontend build artifact ID (Vercel deployment ID or build hash)",
    )

    backend_artifact: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Backend artifact ID (Docker image digest or deployment ID)",
    )

    migration_set: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Current migration head (Alembic revision ID or comma-separated applied set)",
    )

    config_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Configuration/environment version identifier (hash of active config)",
    )

    model_manifest: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'{}'",
        comment="JSON object mapping model names to versions/checksums deployed",
    )

    deployment_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'[]'",
        comment="JSON array of deployment identifiers (Vercel, Railway, etc.)",
    )

    # ── Lifecycle fields ──────────────────────────────────────────────────────

    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether this is the currently active release (only one True at a time)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When this release identity was created (deployment time)",
    )

    created_by: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Identity of the deployer (user ID, CI system, etc.)",
    )

    __table_args__ = (
        Index("ix_release_identities_commit", "git_commit_sha"),
        Index("ix_release_identities_created", "created_at"),
        Index(
            "ix_release_identities_current",
            "is_current",
            unique=True,
            postgresql_where=text("is_current IS TRUE"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ReleaseIdentity(id={self.id}, "
            f"commit={self.git_commit_sha[:7]}, "
            f"is_current={self.is_current})>"
        )

    def to_version_info(self) -> dict:
        """Return version info safe for HTTP responses (no secrets).

        Used in /ready endpoint and structured log context.
        """
        return {
            "release_id": str(self.id),
            "git_commit_sha": self.git_commit_sha[:7],
            "frontend_artifact": self.frontend_artifact,
            "backend_artifact": self.backend_artifact,
            "migration_set": self.migration_set,
            "config_version": self.config_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
