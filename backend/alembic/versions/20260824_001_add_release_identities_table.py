"""Add release_identities table.

Creates the release_identities table for tracking immutable deployment
records. Each record links a git commit, build artifacts, migration set,
config version, model manifest, and deployment IDs into a single traceable
identity.

This is a platform-level table (no org_id) — release identities are global.
Records are append-only: never updated or deleted after creation.

Implements:
    - R72.1: Immutable Release_Identity linking all artifacts
    - R72.2: Surfaced in /ready, logs, job records, error reports
    - R72.3: Stored as immutable record, never modified
    - R72.4: Retrievable by timestamp or correlation ID
    - R72.5: Reject deployments with incomplete identity
    - R72.6: Support Release_Identity comparison

Revision ID: 20260824001
Revises: 20260823001
Create Date: 2026-08-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260824001"
down_revision: Union[str, None] = "20260823001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create release_identities table."""
    op.create_table(
        "release_identities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "git_commit_sha",
            sa.String(40),
            nullable=False,
            comment="Full 40-character git commit SHA for this release",
        ),
        sa.Column(
            "frontend_artifact",
            sa.String(200),
            nullable=False,
            comment="Frontend build artifact ID (Vercel deployment ID or build hash)",
        ),
        sa.Column(
            "backend_artifact",
            sa.String(200),
            nullable=False,
            comment="Backend artifact ID (Docker image digest or deployment ID)",
        ),
        sa.Column(
            "migration_set",
            sa.Text(),
            nullable=False,
            comment="Current migration head (Alembic revision ID or comma-separated applied set)",
        ),
        sa.Column(
            "config_version",
            sa.String(100),
            nullable=False,
            comment="Configuration/environment version identifier (hash of active config)",
        ),
        sa.Column(
            "model_manifest",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="JSON object mapping model names to versions/checksums deployed",
        ),
        sa.Column(
            "deployment_ids",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment="JSON array of deployment identifiers (Vercel, Railway, etc.)",
        ),
        sa.Column(
            "is_current",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Whether this is the currently active release (only one True at a time)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When this release identity was created (deployment time)",
        ),
        sa.Column(
            "created_by",
            sa.String(200),
            nullable=True,
            comment="Identity of the deployer (user ID, CI system, etc.)",
        ),
    )

    # Indexes
    op.create_index(
        "ix_release_identities_commit",
        "release_identities",
        ["git_commit_sha"],
    )
    op.create_index(
        "ix_release_identities_created",
        "release_identities",
        ["created_at"],
    )
    # Partial unique index: only one row may have is_current=True
    op.create_index(
        "ix_release_identities_current",
        "release_identities",
        ["is_current"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )


def downgrade() -> None:
    """Drop release_identities table and indexes."""
    op.drop_index("ix_release_identities_current", table_name="release_identities")
    op.drop_index("ix_release_identities_created", table_name="release_identities")
    op.drop_index("ix_release_identities_commit", table_name="release_identities")
    op.drop_table("release_identities")
