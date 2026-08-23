"""Add dataset_manifests table for training dataset manifests.

Training dataset manifests are immutable records of exact files, checksums,
roles, and provenance used for a training job. Once created, no field may
be modified. Workers verify checksums before starting paid GPU training.

Requirements: R61.1, R61.2, R61.3, R61.4, R61.5, R61.6

Revision ID: 20260822_001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID


# revision identifiers, used by Alembic.
revision = "20260822001"
down_revision = "20260821001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create dataset_manifests table with indexes."""
    op.create_table(
        "dataset_manifests",
        sa.Column("id", UUID(as_uuid=True),
                  primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", UUID(as_uuid=True), nullable=False),
        sa.Column("talent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_files", JSONB, nullable=False),
        sa.Column("consent_record_ids",
                  ARRAY(UUID(as_uuid=True)), nullable=False,
                  server_default="{}"),
        sa.Column("total_file_count", sa.Integer, nullable=False),
        sa.Column("total_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("is_valid", sa.Boolean, nullable=False,
                  server_default="true"),
        sa.Column("invalidated_at",
                  sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidation_reason",
                  sa.String(500), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False,
                  server_default=sa.text("now()")),
    )

    # Primary tenant isolation index
    op.create_index(
        "ix_dataset_manifests_org_id",
        "dataset_manifests",
        ["org_id"],
    )

    # Talent lookup index
    op.create_index(
        "ix_dataset_manifests_talent_id",
        "dataset_manifests",
        ["talent_id"],
    )

    # Composite index for per-org per-talent queries
    op.create_index(
        "ix_dataset_manifests_org_talent",
        "dataset_manifests",
        ["org_id", "talent_id"],
    )

    # Version lookup (unique per manifest)
    op.create_index(
        "ix_dataset_manifests_version",
        "dataset_manifests",
        ["version"],
        unique=True,
    )

    # Enable RLS
    op.execute(sa.text("""
        ALTER TABLE dataset_manifests ENABLE ROW LEVEL SECURITY;
    """))

    # RLS policy: tenant isolation
    op.execute(sa.text("""
        CREATE POLICY "dataset_manifests_tenant_isolation" ON dataset_manifests
            FOR ALL
            USING (org_id IN (
                SELECT om.org_id FROM org_members om
                WHERE om.user_id = auth.uid()
            ));
    """))


def downgrade() -> None:
    """Drop dataset_manifests table and associated objects."""
    op.execute(sa.text(
        'DROP POLICY IF EXISTS "dataset_manifests_tenant_isolation"'
        " ON dataset_manifests;"
    ))
    op.drop_index("ix_dataset_manifests_version",
                  table_name="dataset_manifests")
    op.drop_index("ix_dataset_manifests_org_talent",
                  table_name="dataset_manifests")
    op.drop_index("ix_dataset_manifests_talent_id",
                  table_name="dataset_manifests")
    op.drop_index("ix_dataset_manifests_org_id",
                  table_name="dataset_manifests")
    op.drop_table("dataset_manifests")
