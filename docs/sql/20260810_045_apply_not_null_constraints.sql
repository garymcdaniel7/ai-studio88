-- =============================================================================
-- Migration 045: Apply NOT NULL constraints on org_id
-- Date: 2026-08-10
-- Task: 3.2 Apply org_id NOT NULL constraints and backfill
--
-- PURPOSE: Apply NOT NULL constraint to org_id on ALL Category A tables,
-- ONLY after migrations 041-044 have been verified (zero NULL org_id rows).
--
-- This migration MUST NOT be run until:
--   1. Migrations 040-044 have been applied successfully
--   2. scripts/verify_org_id_backfill.py confirms zero NULL rows
--   3. Application code has been updated to always provide org_id on writes
--
-- If any NULL rows remain, the verification block will ABORT the transaction.
--
-- REQUIREMENTS: R5.6, R2.1, R69.5
--
-- SAFETY: Transactional — aborts on any remaining NULLs.
-- ROLLBACK:
--   -- ALTER TABLE <table> ALTER COLUMN org_id DROP NOT NULL;
--   (for each table below)
-- =============================================================================

BEGIN;

-- =============================================================================
-- PRE-FLIGHT VERIFICATION
-- =============================================================================
-- Abort the ENTIRE migration if ANY NULL org_id rows remain.
-- Per R69.5: NOT NULL SHALL NOT be applied until all NULLs are classified.

DO $$ DECLARE
    tbl TEXT;
    null_count INT;
    tables_with_nulls TEXT[] := '{}';
BEGIN

    -- Check each table that should have org_id NOT NULL
    FOR tbl IN
        SELECT unnest(ARRAY[
            -- Core content (migration 042)
            'talent', 'assets', 'jobs', 'models', 'workflows',
            -- Existing nullable (migration 041)
            'aios_approvals', 'aios_policies', 'aios_sessions',
            'brain_collections', 'brain_conversations', 'brain_embeddings',
            'cost_records', 'job_costs', 'workflow_dna', 'brain_memory',
            -- Media (migration 043)
            'video_projects', 'video_shots', 'video_renders',
            'timeline_tracks', 'timeline_clips', 'timeline_exports',
            'voice_profiles', 'voice_samples', 'voice_datasets',
            'voice_dna', 'voice_training_jobs', 'voice_versions',
            'audio_clips', 'lip_sync_jobs', 'music_tracks_db',
            'sound_effects', 'songs', 'soundtrack_cues',
            'publishing_accounts', 'publishing_posts', 'analytics_snapshots',
            -- Intelligence (migration 044)
            'brain_sessions', 'brain_messages', 'brain_plans',
            'creative_dna', 'creative_rules', 'continuity_notes',
            'generation_feedback', 'prompt_history', 'style_preferences',
            'learning_events', 'prompts',
            'performance_dna', 'performance_memory', 'quality_scores',
            'production_insights',
            'sequences', 'cinematic_timelines', 'cinematic_tracks',
            'cinematic_items', 'cinematic_renders', 'editing_operations',
            'storyboard_panels',
            'brands', 'campaigns', 'content_calendar', 'products', 'series',
            'visual_dna', 'asset_collections', 'collection_items',
            'asset_relationships', 'wardrobes', 'outfits', 'collections',
            'talent_assets', 'talent_relationships', 'talent_voices',
            'workflow_runs', 'lora_versions', 'lora_evaluations',
            -- Training (from 20260804_009)
            'training_datasets', 'training_images', 'training_jobs'
        ])
    LOOP
        EXECUTE format(
            'SELECT count(*) FROM %I WHERE org_id IS NULL', tbl
        ) INTO null_count;

        IF null_count > 0 THEN
            tables_with_nulls := tables_with_nulls || tbl;
            RAISE WARNING 'TABLE % has % NULL org_id rows — CANNOT apply NOT NULL', tbl, null_count;
        END IF;
    END LOOP;

    IF array_length(tables_with_nulls, 1) > 0 THEN
        RAISE EXCEPTION
            'ABORT: % tables still have NULL org_id rows. Run backfill migrations first. Tables: %',
            array_length(tables_with_nulls, 1),
            array_to_string(tables_with_nulls, ', ');
    END IF;

    RAISE NOTICE 'PRE-FLIGHT PASSED: All target tables have zero NULL org_id rows.';
END $$;

-- =============================================================================
-- APPLY NOT NULL CONSTRAINTS
-- =============================================================================
-- Grouped by migration for clarity.

-- Core content (migration 042)
ALTER TABLE talent ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE assets ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE jobs ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE models ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE workflows ALTER COLUMN org_id SET NOT NULL;

-- Existing nullable (migration 041)
ALTER TABLE aios_approvals ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE aios_policies ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE aios_sessions ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE brain_collections ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE brain_conversations ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE brain_embeddings ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE cost_records ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE job_costs ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE workflow_dna ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE brain_memory ALTER COLUMN org_id SET NOT NULL;

-- Video (migration 043)
ALTER TABLE video_projects ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE video_shots ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE video_renders ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE timeline_tracks ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE timeline_clips ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE timeline_exports ALTER COLUMN org_id SET NOT NULL;

-- Audio (migration 043)
ALTER TABLE voice_profiles ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE voice_samples ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE voice_datasets ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE voice_dna ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE voice_training_jobs ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE voice_versions ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE audio_clips ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE lip_sync_jobs ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE music_tracks_db ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE sound_effects ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE songs ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE soundtrack_cues ALTER COLUMN org_id SET NOT NULL;

-- Publishing (migration 043)
ALTER TABLE publishing_accounts ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE publishing_posts ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE analytics_snapshots ALTER COLUMN org_id SET NOT NULL;

-- Brain (migration 044)
ALTER TABLE brain_sessions ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE brain_messages ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE brain_plans ALTER COLUMN org_id SET NOT NULL;

-- Creative (migration 044)
ALTER TABLE creative_dna ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE creative_rules ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE continuity_notes ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE generation_feedback ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE prompt_history ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE style_preferences ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE learning_events ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE prompts ALTER COLUMN org_id SET NOT NULL;

-- Performance (migration 044)
ALTER TABLE performance_dna ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE performance_memory ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE quality_scores ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE production_insights ALTER COLUMN org_id SET NOT NULL;

-- Cinematic (migration 044)
ALTER TABLE sequences ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE cinematic_timelines ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE cinematic_tracks ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE cinematic_items ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE cinematic_renders ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE editing_operations ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE storyboard_panels ALTER COLUMN org_id SET NOT NULL;

-- Company (migration 044)
ALTER TABLE brands ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE campaigns ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE content_calendar ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE products ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE series ALTER COLUMN org_id SET NOT NULL;

-- Asset intelligence (migration 044)
ALTER TABLE visual_dna ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE asset_collections ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE collection_items ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE asset_relationships ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE wardrobes ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE outfits ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE collections ALTER COLUMN org_id SET NOT NULL;

-- Remaining (migration 044)
ALTER TABLE talent_assets ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE talent_relationships ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE talent_voices ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE workflow_runs ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE lora_versions ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE lora_evaluations ALTER COLUMN org_id SET NOT NULL;

-- Training (from 20260804_009 — may already be NOT NULL)
ALTER TABLE training_datasets ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE training_images ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE training_jobs ALTER COLUMN org_id SET NOT NULL;

-- =============================================================================
-- NOTE: The following tables are intentionally EXCLUDED:
--   - workers (Category C — platform-operational, no tenant dimension)
--   - worker_sessions (Category C)
--   - _org_id_quarantine (Category C — the quarantine table itself)
--   - _migration_ledger (Category C)
--   - organizations (Category D — is the tenant root)
--   - org_members (Category D)
--   - platform_packages, workflow_templates, etc. (Category B — system/shared)
-- =============================================================================

COMMIT;
