"""Add generation_context_packages table for immutable context snapshots.

Generation context packages are versioned, immutable snapshots of all inputs
resolved before job dispatch. Once created, they are NEVER modified.

All generation surfaces (Brain, API, MCP, scheduled, batch) use the same
canonical boundary. Stale references are detected at validation time.

Implements:
    - R60.1: Resolve approved context into versioned, immutable package
    - R60.2: Assigned unique version ID, stored in Supabase, never modified
    - R60.3: Job record references exact context package version
    - R60.4: All generation surfaces use same canonical boundary
    - R60.5: Stale references → job rejected
    - R60.6: Support context package comparison

Revision ID: 20260819001
Revises: 20260818001
Create Date: 2026-08-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260819001"
down_revision: Union[str, None] = "20260818001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create generation_context_packages table with indexes and RLS."""
    op.create_table(
        "generation_context_packages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization scope (tenant isolation)",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            comment="Auto-incrementing version number per org",
        ),
        sa.Column(
            "talent_record",
            postgresql.JSONB(),
            nullable=True,
            comment="Frozen talent snapshot at time of package creation",
        ),
        sa.Column(
            "creative_dna_version",
            sa.String(100),
            nullable=True,
            comment="Creative DNA version ID used for this generation",
        ),
        sa.Column(
            "source_assets",
            postgresql.JSONB(),
            nullable=True,
            comment="Array of source asset references with checksums",
        ),
        sa.Column(
            "model_lora_selections",
            postgresql.JSONB(),
            nullable=True,
            comment="Model/LoRA configuration with versions and strengths",
        ),
        sa.Column(
            "prompt_instructions",
            postgresql.JSONB(),
            nullable=True,
            comment="Prompt configuration (positive, negative, params)",
        ),
        sa.Column(
            "consent_verification_result",
            postgresql.JSONB(),
            nullable=True,
            comment="Consent check outcome at assembly time",
        ),
        sa.Column(
            "safety_evaluation_result",
            postgresql.JSONB(),
            nullable=True,
            comment="Safety policy evaluation at assembly time",
        ),
        sa.Column(
            "workflow_template",
            postgresql.JSONB(),
            nullable=True,
            comment="Workflow configuration reference",
        ),
        sa.Column(
            "project_constraints",
            postgresql.JSONB(),
            nullable=True,
            comment="Project-level constraints bounding generation",
        ),
        sa.Column(
            "initiated_by",
            sa.String(50),
            nullable=True,
            comment="Generation surface: brain, api, mcp, scheduled, batch",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="User who initiated the generation request",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Primary tenant isolation index
    op.create_index(
        "ix_generation_context_packages_org_id",
        "generation_context_packages",
        ["org_id"],
    )

    # Composite index for version lookups per org
    op.create_index(
        "ix_generation_context_packages_org_version",
        "generation_context_packages",
        ["org_id", "version"],
        unique=True,
    )

    # Index for user lookups
    op.create_index(
        "ix_generation_context_packages_user_id",
        "generation_context_packages",
        ["user_id"],
    )

    # Index for time-based queries
    op.create_index(
        "ix_generation_context_packages_created_at",
        "generation_context_packages",
        ["org_id", "created_at"],
    )

    # Enable RLS
    op.execute(sa.text("""
        ALTER TABLE generation_context_packages ENABLE ROW LEVEL SECURITY;
    """))

    # RLS policy: tenant isolation with USING + WITH CHECK
    op.execute(sa.text("""
        CREATE POLICY "gcp_tenant_isolation" ON generation_context_packages
            FOR ALL
            USING (org_id IN (
                SELECT om.org_id FROM org_members om
                WHERE om.user_id = auth.uid() AND om.status = 'active'
            ))
            WITH CHECK (org_id IN (
                SELECT om.org_id FROM org_members om
                WHERE om.user_id = auth.uid() AND om.status = 'active'
            ));
    """))


def downgrade() -> None:
    """Drop generation_context_packages table and associated objects."""
    op.execute(sa.text(
        'DROP POLICY IF EXISTS "gcp_tenant_isolation" '
        "ON generation_context_packages;"
    ))
    op.drop_index(
        "ix_generation_context_packages_created_at",
        table_name="generation_context_packages",
    )
    op.drop_index(
        "ix_generation_context_packages_user_id",
        table_name="generation_context_packages",
    )
    op.drop_index(
        "ix_generation_context_packages_org_version",
        table_name="generation_context_packages",
    )
    op.drop_index(
        "ix_generation_context_packages_org_id",
        table_name="generation_context_packages",
    )
    op.drop_table("generation_context_packages")
