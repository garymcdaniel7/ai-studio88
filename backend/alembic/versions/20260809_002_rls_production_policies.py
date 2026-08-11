"""Apply production RLS policies with USING + WITH CHECK separation.

Creates per-operation RLS policies on all Category A tables:
    - SELECT: USING (org_id IN user_org_ids())
    - INSERT: WITH CHECK (org_id IN user_org_ids())
    - UPDATE: USING + WITH CHECK (prevents org_id mutation)
    - DELETE: USING (org_id IN user_org_ids())

Also creates the user_org_ids() helper function for efficient policy evaluation.

Requirements: R6.3, R6.6, A2-029

Revision ID: 20260809002
Revises: 20260809001
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260809002"
down_revision: Union[str, None] = "20260809001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# All Category A tables that get the standard 4-policy pattern
STANDARD_TABLES = [
    "talent", "assets", "jobs", "scenes",
    "training_datasets", "training_images", "training_jobs",
    "lora_versions", "lora_evaluations",
    "video_projects", "video_shots", "video_renders",
    "timeline_tracks", "timeline_clips", "timeline_exports",
    "voice_profiles", "voice_samples", "audio_clips",
    "lip_sync_jobs", "music_tracks_db", "sound_effects",
    "publishing_accounts", "publishing_posts", "analytics_snapshots",
    "brain_sessions", "brain_messages", "brain_plans",
    "brain_memory", "brain_collections", "brain_conversations",
    "brain_embeddings",
    "aios_sessions", "aios_messages", "aios_decisions",
    "aios_approvals", "aios_policies",
    "universes", "characters", "episodes", "shots", "story_memory",
    "creative_dna", "creative_rules", "continuity_notes",
    "generation_feedback", "prompt_history", "style_preferences",
    "performance_dna", "performance_memory", "quality_scores",
    "voice_dna", "voice_datasets", "voice_training_jobs", "voice_versions",
    "object_dna", "product_dna", "digital_twins", "digital_twin_versions",
    "virtual_tryon_jobs", "product_views_360", "scene_dna", "material_profiles",
    "visual_dna", "asset_collections", "collection_items",
    "asset_relationships", "wardrobes", "outfits",
    "sequences", "cinematic_timelines", "cinematic_tracks",
    "cinematic_items", "storyboard_panels", "cinematic_renders",
    "editing_operations",
    "brands", "studios", "brand_campaigns", "team_members",
    "approval_requests", "clients", "asset_licenses",
    "workspace_credentials", "credential_audit_log",
    "social_account_connections",
    "cost_records", "job_costs",
    "lifecycle_transitions", "entity_holds",
    "asset_provenance", "asset_lineage", "provenance_amendments",
    "generation_batches", "batch_variation_jobs",
    "durable_approvals", "governance_policy_audit", "infra_audit_log",
    "creative_recipes",
    "projects", "project_assets",
]


def upgrade() -> None:
    """Create user_org_ids() function and apply 4-policy RLS to all Category A tables."""
    # Create the helper function
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION public.user_org_ids()
        RETURNS SETOF UUID
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT org_id FROM org_members
            WHERE user_id = auth.uid()
            AND status = 'active';
        $$;
    """))

    op.execute(sa.text(
        "GRANT EXECUTE ON FUNCTION public.user_org_ids() TO authenticated;"
    ))

    # Apply standard 4-policy pattern to each table
    for tbl in STANDARD_TABLES:
        _apply_standard_policies(tbl)

    # Special cases: models and workflows (system org readable by all)
    _apply_shared_readable_policies("models")
    _apply_shared_readable_policies("workflows")

    # Workers: service_role only (RLS enabled, no policies)
    op.execute(sa.text("ALTER TABLE workers ENABLE ROW LEVEL SECURITY;"))

    # org_members: read-only for authenticated users
    op.execute(sa.text("ALTER TABLE org_members ENABLE ROW LEVEL SECURITY;"))
    op.execute(sa.text("""
        CREATE POLICY org_members_select_own_org ON org_members
            FOR SELECT USING (org_id IN (SELECT user_org_ids()));
    """))


def _apply_standard_policies(tbl: str) -> None:
    """Apply the standard 4-policy pattern to a table (idempotent)."""
    op.execute(sa.text(f"""
        DO $$
        BEGIN
            -- Skip if table doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = '{tbl}'
            ) THEN
                RAISE NOTICE 'SKIP: Table {tbl} does not exist';
                RETURN;
            END IF;

            -- Skip if no org_id column
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = '{tbl}' AND column_name = 'org_id'
            ) THEN
                RAISE NOTICE 'SKIP: Table {tbl} missing org_id column';
                RETURN;
            END IF;

            -- Enable RLS
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', '{tbl}');

            -- Drop existing policies
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_org_isolation', '{tbl}');
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_all', '{tbl}');
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_select_own_org', '{tbl}');
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_insert_own_org', '{tbl}');
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_update_own_org', '{tbl}');
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_delete_own_org', '{tbl}');

            -- SELECT: USING only
            EXECUTE format(
                'CREATE POLICY %I ON %I FOR SELECT USING (org_id IN (SELECT user_org_ids()))',
                '{tbl}_select_own_org', '{tbl}'
            );

            -- INSERT: WITH CHECK only (prevents foreign org_id on insert)
            EXECUTE format(
                'CREATE POLICY %I ON %I FOR INSERT WITH CHECK (org_id IN (SELECT user_org_ids()))',
                '{tbl}_insert_own_org', '{tbl}'
            );

            -- UPDATE: USING + WITH CHECK (prevents org_id mutation)
            EXECUTE format(
                'CREATE POLICY %I ON %I FOR UPDATE USING (org_id IN (SELECT user_org_ids())) WITH CHECK (org_id IN (SELECT user_org_ids()))',
                '{tbl}_update_own_org', '{tbl}'
            );

            -- DELETE: USING only
            EXECUTE format(
                'CREATE POLICY %I ON %I FOR DELETE USING (org_id IN (SELECT user_org_ids()))',
                '{tbl}_delete_own_org', '{tbl}'
            );

            RAISE NOTICE 'APPLIED: 4 RLS policies on {tbl}';
        END $$;
    """))


def _apply_shared_readable_policies(tbl: str) -> None:
    """Apply policies where system org content is readable by all."""
    op.execute(sa.text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = '{tbl}'
            ) THEN
                RETURN;
            END IF;

            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', '{tbl}');
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_org_isolation', '{tbl}');
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_select_own_org', '{tbl}');
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_insert_own_org', '{tbl}');
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_update_own_org', '{tbl}');
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_delete_own_org', '{tbl}');

            -- SELECT: own org OR system org (shared resources)
            EXECUTE format(
                'CREATE POLICY %I ON %I FOR SELECT USING (org_id = ''00000000-0000-0000-0000-000000000001''::uuid OR org_id IN (SELECT user_org_ids()))',
                '{tbl}_select_own_org', '{tbl}'
            );

            -- INSERT: own org only
            EXECUTE format(
                'CREATE POLICY %I ON %I FOR INSERT WITH CHECK (org_id IN (SELECT user_org_ids()))',
                '{tbl}_insert_own_org', '{tbl}'
            );

            -- UPDATE: own org only (can't modify system resources)
            EXECUTE format(
                'CREATE POLICY %I ON %I FOR UPDATE USING (org_id IN (SELECT user_org_ids())) WITH CHECK (org_id IN (SELECT user_org_ids()))',
                '{tbl}_update_own_org', '{tbl}'
            );

            -- DELETE: own org only
            EXECUTE format(
                'CREATE POLICY %I ON %I FOR DELETE USING (org_id IN (SELECT user_org_ids()))',
                '{tbl}_delete_own_org', '{tbl}'
            );
        END $$;
    """))


def downgrade() -> None:
    """Drop all RLS policies and the helper function."""
    # Drop policies from all tables
    all_tables = STANDARD_TABLES + ["models", "workflows"]
    for tbl in all_tables:
        op.execute(sa.text(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{tbl}'
                ) THEN
                    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_select_own_org', '{tbl}');
                    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_insert_own_org', '{tbl}');
                    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_update_own_org', '{tbl}');
                    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', '{tbl}_delete_own_org', '{tbl}');
                END IF;
            END $$;
        """))

    # Drop org_members policy
    op.execute(sa.text(
        "DROP POLICY IF EXISTS org_members_select_own_org ON org_members;"
    ))

    # Drop helper function
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.user_org_ids();"))
