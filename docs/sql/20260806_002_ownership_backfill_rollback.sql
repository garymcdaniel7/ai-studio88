-- =============================================================================
-- ROLLBACK: Migration 040 — Ownership Backfill
--
-- Reverses all changes from 040_ownership_backfill.sql.
-- Run this if the migration needs to be undone.
-- =============================================================================

BEGIN;

-- Restore DEFAULT values removed in Phase 10
ALTER TABLE cost_records ALTER COLUMN org_id
    SET DEFAULT '00000000-0000-0000-0000-000000000001'::uuid;
ALTER TABLE job_costs ALTER COLUMN org_id
    SET DEFAULT '00000000-0000-0000-0000-000000000001'::uuid;
ALTER TABLE brain_collections ALTER COLUMN org_id
    SET DEFAULT '00000000-0000-0000-0000-000000000001'::uuid;

-- Drop indexes added in Phase 11
DROP INDEX IF EXISTS ix_characters_org_id;
DROP INDEX IF EXISTS ix_episodes_org_id;
DROP INDEX IF EXISTS ix_shots_org_id;
DROP INDEX IF EXISTS ix_story_memory_org_id;
DROP INDEX IF EXISTS ix_universes_org_id;

-- Drop org_id columns added to story engine tables in Phase 8
-- (only if they didn't exist before this migration)
ALTER TABLE characters DROP COLUMN IF EXISTS org_id;
ALTER TABLE episodes DROP COLUMN IF EXISTS org_id;
ALTER TABLE shots DROP COLUMN IF EXISTS org_id;
ALTER TABLE story_memory DROP COLUMN IF EXISTS org_id;

-- NOTE: We do NOT revert the backfill of existing rows (talent, assets, etc.)
-- because setting org_id back to NULL would break RLS and tenant filtering.
-- The backfill is a one-way data correction.
--
-- If a full rollback to NULL is needed (emergency), run:
-- UPDATE talent SET org_id = NULL WHERE org_id = '%%FOUNDER_ORG_ID%%';
-- (Repeat for each table — but this will break all tenant queries)

COMMIT;

-- =============================================================================
-- ROLLBACK: Migration 041 — NOT NULL Constraints
-- Run this BEFORE rolling back 040.
-- =============================================================================

-- ALTER TABLE talent ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE assets ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE jobs ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE models ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE workflows ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE scenes ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE training_datasets ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE training_images ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE training_jobs ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE video_projects ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE video_renders ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE video_shots ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE audio_clips ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE voice_profiles ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE publishing_posts ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE publishing_accounts ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE brain_memory ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE brain_messages ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE brain_sessions ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE brain_plans ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE brain_collections ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE creative_dna ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE creative_rules ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE continuity_notes ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE performance_dna ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE quality_scores ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE generation_feedback ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE cost_records ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE job_costs ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE universes ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE brands ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE studios ALTER COLUMN org_id DROP NOT NULL;
-- ALTER TABLE storyboard_panels ALTER COLUMN org_id DROP NOT NULL;
