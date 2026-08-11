-- =============================================================================
-- Migration 041: Add NOT NULL Constraints on org_id (Story 006)
--
-- PREREQUISITES:
--   - Migration 040 complete (all rows backfilled)
--   - Dry-run confirms zero NULL org_id rows on target tables
--   - Application code updated to always provide org_id on writes
--
-- SAFETY: Run AFTER confirming backfill is complete.
-- Reversible via: ALTER TABLE <table> ALTER COLUMN org_id DROP NOT NULL;
-- =============================================================================

BEGIN;

-- =============================================================================
-- Verification: Abort if any NULLs remain
-- =============================================================================

DO $$
DECLARE
    null_count INT;
BEGIN
    SELECT count(*) INTO null_count FROM talent WHERE org_id IS NULL;
    IF null_count > 0 THEN
        RAISE EXCEPTION 'ABORT: talent has % NULL org_id rows. Run 040 first.', null_count;
    END IF;

    SELECT count(*) INTO null_count FROM assets WHERE org_id IS NULL;
    IF null_count > 0 THEN
        RAISE EXCEPTION 'ABORT: assets has % NULL org_id rows.', null_count;
    END IF;

    SELECT count(*) INTO null_count FROM jobs WHERE org_id IS NULL;
    IF null_count > 0 THEN
        RAISE EXCEPTION 'ABORT: jobs has % NULL org_id rows.', null_count;
    END IF;

    SELECT count(*) INTO null_count FROM models WHERE org_id IS NULL;
    IF null_count > 0 THEN
        RAISE EXCEPTION 'ABORT: models has % NULL org_id rows.', null_count;
    END IF;
END $$;


-- =============================================================================
-- Apply NOT NULL constraints
-- =============================================================================
-- Core content tables (Category A — must always have org_id)

ALTER TABLE talent ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE assets ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE jobs ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE models ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE workflows ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE scenes ALTER COLUMN org_id SET NOT NULL;

-- Training pipeline
ALTER TABLE training_datasets ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE training_images ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE training_jobs ALTER COLUMN org_id SET NOT NULL;

-- Video pipeline
ALTER TABLE video_projects ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE video_renders ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE video_shots ALTER COLUMN org_id SET NOT NULL;

-- Audio
ALTER TABLE audio_clips ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE voice_profiles ALTER COLUMN org_id SET NOT NULL;

-- Publishing
ALTER TABLE publishing_posts ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE publishing_accounts ALTER COLUMN org_id SET NOT NULL;

-- Brain
ALTER TABLE brain_memory ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE brain_messages ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE brain_sessions ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE brain_plans ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE brain_collections ALTER COLUMN org_id SET NOT NULL;

-- Creative / Performance
ALTER TABLE creative_dna ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE creative_rules ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE continuity_notes ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE performance_dna ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE quality_scores ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE generation_feedback ALTER COLUMN org_id SET NOT NULL;

-- Cost
ALTER TABLE cost_records ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE job_costs ALTER COLUMN org_id SET NOT NULL;

-- Story Engine (newly added org_id columns)
ALTER TABLE universes ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE characters ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE episodes ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE shots ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE story_memory ALTER COLUMN org_id SET NOT NULL;

-- Company (org_id column, supplementing organization_id FK)
ALTER TABLE brands ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE studios ALTER COLUMN org_id SET NOT NULL;

-- Storyboard
ALTER TABLE storyboard_panels ALTER COLUMN org_id SET NOT NULL;

-- =============================================================================
-- NOTE: Workers and worker_sessions remain nullable (platform-scoped).
-- NOTE: organization_id FK on Company OS tables is NOT modified here.
-- =============================================================================

COMMIT;
