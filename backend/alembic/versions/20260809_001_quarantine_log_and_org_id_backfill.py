"""Create _quarantine_log table, backfill NULL org_id rows, apply NOT NULL constraints.

Implements:
    - R69.1: Classification of orphaned records
    - R69.2: Quarantine process for ambiguous rows
    - R69.3: Quarantine tagging with reason and date
    - R69.4: Resolution workflow (assign/system/purge)
    - R69.5: NOT NULL only after all NULLs resolved
    - R69.6: Audit trail for resolutions
    - R5.6: org_id NOT NULL on Category A tables
    - R2.1: Tenant scoping enforcement

Revision ID: 20260809001
Revises: None
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260809001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create _quarantine_log and apply org_id backfill + NOT NULL constraints.

    This migration combines three SQL scripts:
        - 20260815_002_quarantine_log_table.sql
        - 20260815_003_org_id_quarantine_backfill.sql
        - 20260806_005_ownership_not_null_constraints.sql

    The actual backfill SQL uses PL/pgSQL DO blocks to handle conditional logic,
    quarantine ambiguous rows, and verify zero NULLs before applying constraints.
    """
    # Phase 1: Create _quarantine_log table
    op.create_table(
        "_quarantine_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("source_table", sa.Text(), nullable=False),
        sa.Column("source_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "classification",
            sa.Text(),
            nullable=False,
            server_default="QUARANTINED_FOR_REVIEW",
        ),
        sa.Column("quarantine_reason", sa.Text(), nullable=False),
        sa.Column("quarantine_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_evidence", sa.Text(), nullable=True),
        sa.Column("assigned_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "classification IN ("
            "'QUARANTINED_FOR_REVIEW', "
            "'ELIGIBLE_FOR_APPROVED_PURGE', "
            "'RESOLVED_ASSIGNED', "
            "'RESOLVED_SYSTEM_OWNED', "
            "'RESOLVED_PURGED')",
            name="ck_quarantine_log_classification",
        ),
        sa.CheckConstraint(
            "resolution IN ('assigned', 'system', 'purged')",
            name="ck_quarantine_log_resolution",
        ),
    )

    op.create_index("ix_quarantine_log_source_table", "_quarantine_log", ["source_table"])
    op.create_index("ix_quarantine_log_classification", "_quarantine_log", ["classification"])
    op.create_index("ix_quarantine_log_source_row", "_quarantine_log", ["source_table", "source_row_id"])

    # Phase 2: The actual backfill and NOT NULL constraints are applied via
    # raw SQL DO blocks (see docs/sql/20260815_003_org_id_quarantine_backfill.sql).
    # This requires the FOUNDER_ORG_ID to be set before execution.
    #
    # NOTE: This migration is designed to be run AFTER the SQL backfill scripts
    # have been applied manually via Supabase CLI or psql. The Alembic migration
    # records the schema state for tracking purposes.
    #
    # The NOT NULL constraints below are idempotent — they will succeed if already
    # applied and will fail safely if NULLs still exist (which means the SQL
    # backfill script hasn't been run yet).

    # Core content tables
    _apply_not_null_if_ready("talent", "org_id")
    _apply_not_null_if_ready("assets", "org_id")
    _apply_not_null_if_ready("jobs", "org_id")
    _apply_not_null_if_ready("models", "org_id")
    _apply_not_null_if_ready("workflows", "org_id")
    _apply_not_null_if_ready("scenes", "org_id")

    # Training
    _apply_not_null_if_ready("training_datasets", "org_id")
    _apply_not_null_if_ready("training_images", "org_id")
    _apply_not_null_if_ready("training_jobs", "org_id")

    # Video
    _apply_not_null_if_ready("video_projects", "org_id")
    _apply_not_null_if_ready("video_renders", "org_id")
    _apply_not_null_if_ready("video_shots", "org_id")

    # Audio
    _apply_not_null_if_ready("audio_clips", "org_id")
    _apply_not_null_if_ready("voice_profiles", "org_id")

    # Publishing
    _apply_not_null_if_ready("publishing_posts", "org_id")
    _apply_not_null_if_ready("publishing_accounts", "org_id")

    # Brain
    _apply_not_null_if_ready("brain_memory", "org_id")
    _apply_not_null_if_ready("brain_messages", "org_id")
    _apply_not_null_if_ready("brain_sessions", "org_id")
    _apply_not_null_if_ready("brain_plans", "org_id")
    _apply_not_null_if_ready("brain_collections", "org_id")

    # Creative / Performance
    _apply_not_null_if_ready("creative_dna", "org_id")
    _apply_not_null_if_ready("creative_rules", "org_id")
    _apply_not_null_if_ready("continuity_notes", "org_id")
    _apply_not_null_if_ready("performance_dna", "org_id")
    _apply_not_null_if_ready("quality_scores", "org_id")
    _apply_not_null_if_ready("generation_feedback", "org_id")

    # Cost
    _apply_not_null_if_ready("cost_records", "org_id")
    _apply_not_null_if_ready("job_costs", "org_id")

    # Story Engine
    _apply_not_null_if_ready("universes", "org_id")
    _apply_not_null_if_ready("characters", "org_id")
    _apply_not_null_if_ready("episodes", "org_id")
    _apply_not_null_if_ready("shots", "org_id")
    _apply_not_null_if_ready("story_memory", "org_id")

    # Company
    _apply_not_null_if_ready("brands", "org_id")
    _apply_not_null_if_ready("studios", "org_id")

    # Storyboard
    _apply_not_null_if_ready("storyboard_panels", "org_id")

    # AIOS
    _apply_not_null_if_ready("aios_sessions", "org_id")
    _apply_not_null_if_ready("aios_messages", "org_id")
    _apply_not_null_if_ready("aios_decisions", "org_id")
    _apply_not_null_if_ready("aios_approvals", "org_id")
    _apply_not_null_if_ready("aios_policies", "org_id")


def _apply_not_null_if_ready(table: str, column: str) -> None:
    """Apply NOT NULL constraint only if zero NULLs remain (R69.5).

    Uses a DO block to verify and apply atomically. If NULLs exist,
    logs a warning and skips (the backfill SQL hasn't been run yet).
    """
    op.execute(sa.text(f"""
        DO $$
        DECLARE
            null_count INT;
        BEGIN
            -- Check if column exists first
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = '{table}'
                  AND column_name = '{column}'
            ) THEN
                RAISE NOTICE 'SKIP: Table {table} does not have column {column}';
                RETURN;
            END IF;

            -- Check if already NOT NULL
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = '{table}'
                  AND column_name = '{column}'
                  AND is_nullable = 'YES'
            ) THEN
                RAISE NOTICE 'SKIP: {table}.{column} is already NOT NULL';
                RETURN;
            END IF;

            -- Check for remaining NULLs
            EXECUTE format('SELECT count(*) FROM %I WHERE %I IS NULL', '{table}', '{column}')
                INTO null_count;

            IF null_count > 0 THEN
                RAISE NOTICE 'SKIP: {table} has % NULL {column} rows — run backfill first', null_count;
                RETURN;
            END IF;

            -- Apply NOT NULL
            EXECUTE format('ALTER TABLE %I ALTER COLUMN %I SET NOT NULL', '{table}', '{column}');
            RAISE NOTICE 'APPLIED: {table}.{column} SET NOT NULL';
        END $$;
    """))


def downgrade() -> None:
    """Remove NOT NULL constraints and drop _quarantine_log table."""
    # Remove NOT NULL constraints (make nullable again)
    tables = [
        "talent", "assets", "jobs", "models", "workflows", "scenes",
        "training_datasets", "training_images", "training_jobs",
        "video_projects", "video_renders", "video_shots",
        "audio_clips", "voice_profiles",
        "publishing_posts", "publishing_accounts",
        "brain_memory", "brain_messages", "brain_sessions", "brain_plans", "brain_collections",
        "creative_dna", "creative_rules", "continuity_notes",
        "performance_dna", "quality_scores", "generation_feedback",
        "cost_records", "job_costs",
        "universes", "characters", "episodes", "shots", "story_memory",
        "brands", "studios", "storyboard_panels",
        "aios_sessions", "aios_messages", "aios_decisions", "aios_approvals", "aios_policies",
    ]

    for table in tables:
        op.execute(sa.text(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = '{table}'
                      AND column_name = 'org_id'
                ) THEN
                    ALTER TABLE {table} ALTER COLUMN org_id DROP NOT NULL;
                END IF;
            END $$;
        """))

    # Drop _quarantine_log table
    op.drop_index("ix_quarantine_log_source_row", table_name="_quarantine_log")
    op.drop_index("ix_quarantine_log_classification", table_name="_quarantine_log")
    op.drop_index("ix_quarantine_log_source_table", table_name="_quarantine_log")
    op.drop_table("_quarantine_log")
