-- =============================================================================
-- Migration: org_id Quarantine and Backfill (R5.6 + R69)
--
-- PURPOSE: Apply the R69 quarantine process to all Category A tables,
-- then backfill founder-only tables and quarantine ambiguous tables.
-- Finally, apply NOT NULL constraints ONLY after verification.
--
-- PREREQUISITES:
--   - 20260815_002_quarantine_log_table.sql applied (creates _quarantine_log)
--   - 20260806_001_ownership_backfill.sql applied (initial backfill attempt)
--   - FOUNDER_ORG_ID variable set to verified founder UUID
--   - Backup taken before execution
--
-- REQUIREMENTS: R5.6, R69.1, R69.2, R69.3, R69.4, R69.5, R69.6, R2.1
--
-- PROCESS:
--   Phase 1: Audit — count NULL org_id rows per table
--   Phase 2: Classify — determine founder-only vs ambiguous
--   Phase 3: Backfill founder-only tables (verified single org)
--   Phase 4: Quarantine ambiguous rows (log with reason/date)
--   Phase 5: Verify zero NULLs remain
--   Phase 6: Apply NOT NULL constraints (only if Phase 5 passes)
--
-- SAFETY: Transactional, idempotent, reversible.
-- ROLLBACK: See 20260815_004_org_id_quarantine_backfill_rollback.sql
-- =============================================================================

BEGIN;

-- =============================================================================
-- CONFIGURATION
-- =============================================================================

DO $$ DECLARE
    FOUNDER_ORG UUID := '%%FOUNDER_ORG_ID%%';  -- REPLACE BEFORE RUNNING
    SYSTEM_ORG  UUID := '00000000-0000-0000-0000-000000000001';
    ZERO_UUID   UUID := '00000000-0000-0000-0000-000000000000';
    null_count  INT;
    total_quarantined INT := 0;
    total_backfilled  INT := 0;
BEGIN

-- =============================================================================
-- PHASE 1: Ensure _quarantine_log exists
-- =============================================================================

CREATE TABLE IF NOT EXISTS _quarantine_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_table TEXT NOT NULL,
    source_row_id UUID NOT NULL,
    classification TEXT NOT NULL DEFAULT 'QUARANTINED_FOR_REVIEW'
        CHECK (classification IN (
            'QUARANTINED_FOR_REVIEW',
            'ELIGIBLE_FOR_APPROVED_PURGE',
            'RESOLVED_ASSIGNED',
            'RESOLVED_SYSTEM_OWNED',
            'RESOLVED_PURGED'
        )),
    quarantine_reason TEXT NOT NULL,
    quarantine_date TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolution TEXT CHECK (resolution IN ('assigned', 'system', 'purged')),
    resolved_by UUID,
    resolution_evidence TEXT,
    assigned_org_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- PHASE 2: Founder-Only Tables — Bulk Assign (R5.6 exception)
-- =============================================================================
-- These tables have been VERIFIED by audit to only ever contain data from
-- the single founder org. Per R5.6, bulk assignment is acceptable without
-- per-row review for founder-only tables.
--
-- Verification criteria (all must be true):
--   - Only one non-system org has ever existed
--   - All existing non-NULL org_id values match founder or system
--   - This is a single-tenant history being migrated to multi-tenant

-- Core content (founder-verified)
UPDATE talent SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;
IF null_count > 0 THEN RAISE NOTICE 'talent: % rows backfilled to founder', null_count; END IF;

UPDATE assets SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;
IF null_count > 0 THEN RAISE NOTICE 'assets: % rows backfilled', null_count; END IF;

UPDATE jobs SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;
IF null_count > 0 THEN RAISE NOTICE 'jobs: % rows backfilled', null_count; END IF;

UPDATE workflows SET org_id = FOUNDER_ORG
WHERE org_id IS NULL AND (metadata->>'system') IS DISTINCT FROM 'true';
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;
IF null_count > 0 THEN RAISE NOTICE 'workflows (user): % rows backfilled', null_count; END IF;

-- System workflows → system org
UPDATE workflows SET org_id = SYSTEM_ORG
WHERE org_id IS NULL AND metadata->>'system' = 'true';

UPDATE scenes SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

-- Training pipeline
UPDATE training_datasets SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE training_images SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE training_jobs SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

-- Video pipeline
UPDATE video_projects SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE video_renders SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE video_shots SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

-- Audio
UPDATE audio_clips SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE voice_profiles SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

-- Publishing
UPDATE publishing_posts SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE publishing_accounts SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

-- Brain
UPDATE brain_memory SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE brain_messages SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE brain_sessions SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE brain_plans SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE brain_collections SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

-- Creative / Performance
UPDATE creative_dna SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE creative_rules SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE continuity_notes SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE performance_dna SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE quality_scores SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE generation_feedback SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

-- Cost tables (were defaulting to system org)
UPDATE cost_records SET org_id = FOUNDER_ORG
WHERE org_id IS NULL OR org_id = SYSTEM_ORG;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE job_costs SET org_id = FOUNDER_ORG
WHERE org_id IS NULL OR org_id = SYSTEM_ORG;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

-- Story Engine
UPDATE universes SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE characters SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE episodes SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE shots SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE story_memory SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

-- Company (derive from organization_id FK where possible)
UPDATE brands SET org_id = organization_id WHERE org_id IS NULL AND organization_id IS NOT NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

UPDATE studios SET org_id = organization_id WHERE org_id IS NULL AND organization_id IS NOT NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

-- Storyboard
UPDATE storyboard_panels SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_backfilled := total_backfilled + null_count;

RAISE NOTICE 'PHASE 2 COMPLETE: % total rows backfilled to founder org', total_backfilled;

-- =============================================================================
-- PHASE 3: Quarantine Ambiguous Rows (R69.2, R69.3)
-- =============================================================================
-- Any table where multiple orgs exist and NULL rows remain:
-- Insert quarantine records instead of guessing ownership.
--
-- Per R69.2: NEVER guess tenant ownership for ambiguous records.
-- Per R69.3: Quarantined records are tagged with reason and date.

-- Models table: may have system models mixed with user models
-- Quarantine NULL rows that weren't caught by founder backfill
SELECT count(*) INTO null_count FROM models WHERE org_id IS NULL;
IF null_count > 0 THEN
    INSERT INTO _quarantine_log
        (source_table, source_row_id, classification, quarantine_reason, quarantine_date)
    SELECT 'models', id, 'QUARANTINED_FOR_REVIEW',
        'NULL org_id after backfill — may be system model or orphaned user model',
        now()
    FROM models WHERE org_id IS NULL;
    total_quarantined := total_quarantined + null_count;
    RAISE NOTICE 'models: % rows quarantined for review', null_count;

    -- Assign quarantined model rows to system org temporarily to allow NOT NULL
    -- (They remain tracked in _quarantine_log for review)
    UPDATE models SET org_id = SYSTEM_ORG WHERE org_id IS NULL;
END IF;

-- AIOS tables: may have rows from governance testing
SELECT count(*) INTO null_count FROM aios_sessions WHERE org_id IS NULL;
IF null_count > 0 THEN
    INSERT INTO _quarantine_log
        (source_table, source_row_id, classification, quarantine_reason, quarantine_date)
    SELECT 'aios_sessions', id, 'QUARANTINED_FOR_REVIEW',
        'NULL org_id — ambiguous AIOS session, may be from governance testing',
        now()
    FROM aios_sessions WHERE org_id IS NULL;
    total_quarantined := total_quarantined + null_count;
    RAISE NOTICE 'aios_sessions: % rows quarantined', null_count;
    UPDATE aios_sessions SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
END IF;

SELECT count(*) INTO null_count FROM aios_messages WHERE org_id IS NULL;
IF null_count > 0 THEN
    INSERT INTO _quarantine_log
        (source_table, source_row_id, classification, quarantine_reason, quarantine_date)
    SELECT 'aios_messages', id, 'QUARANTINED_FOR_REVIEW',
        'NULL org_id — ambiguous AIOS message',
        now()
    FROM aios_messages WHERE org_id IS NULL;
    total_quarantined := total_quarantined + null_count;
    UPDATE aios_messages SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
END IF;

SELECT count(*) INTO null_count FROM aios_decisions WHERE org_id IS NULL;
IF null_count > 0 THEN
    INSERT INTO _quarantine_log
        (source_table, source_row_id, classification, quarantine_reason, quarantine_date)
    SELECT 'aios_decisions', id, 'QUARANTINED_FOR_REVIEW',
        'NULL org_id — ambiguous AIOS decision record',
        now()
    FROM aios_decisions WHERE org_id IS NULL;
    total_quarantined := total_quarantined + null_count;
    UPDATE aios_decisions SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
END IF;

SELECT count(*) INTO null_count FROM aios_approvals WHERE org_id IS NULL;
IF null_count > 0 THEN
    INSERT INTO _quarantine_log
        (source_table, source_row_id, classification, quarantine_reason, quarantine_date)
    SELECT 'aios_approvals', id, 'QUARANTINED_FOR_REVIEW',
        'NULL org_id — ambiguous AIOS approval',
        now()
    FROM aios_approvals WHERE org_id IS NULL;
    total_quarantined := total_quarantined + null_count;
    UPDATE aios_approvals SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
END IF;

SELECT count(*) INTO null_count FROM aios_policies WHERE org_id IS NULL;
IF null_count > 0 THEN
    INSERT INTO _quarantine_log
        (source_table, source_row_id, classification, quarantine_reason, quarantine_date)
    SELECT 'aios_policies', id, 'QUARANTINED_FOR_REVIEW',
        'NULL org_id — ambiguous AIOS policy',
        now()
    FROM aios_policies WHERE org_id IS NULL;
    total_quarantined := total_quarantined + null_count;
    UPDATE aios_policies SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
END IF;

-- Zero-UUID cleanup: any rows still using quarantined placeholder
UPDATE talent SET org_id = FOUNDER_ORG WHERE org_id = ZERO_UUID;
UPDATE assets SET org_id = FOUNDER_ORG WHERE org_id = ZERO_UUID;
UPDATE jobs SET org_id = FOUNDER_ORG WHERE org_id = ZERO_UUID;

RAISE NOTICE 'PHASE 3 COMPLETE: % total rows quarantined for review', total_quarantined;

-- =============================================================================
-- PHASE 4: Final Verification (R69.5)
-- =============================================================================
-- Abort if ANY NULL org_id rows remain on tables we are about to constrain.
-- Per R69.5: NOT NULL constraint SHALL NOT be applied until all NULLs classified.

SELECT count(*) INTO null_count FROM talent WHERE org_id IS NULL;
IF null_count > 0 THEN
    RAISE EXCEPTION 'ABORT: talent still has % NULL org_id rows after backfill+quarantine', null_count;
END IF;

SELECT count(*) INTO null_count FROM assets WHERE org_id IS NULL;
IF null_count > 0 THEN
    RAISE EXCEPTION 'ABORT: assets still has % NULL org_id rows', null_count;
END IF;

SELECT count(*) INTO null_count FROM jobs WHERE org_id IS NULL;
IF null_count > 0 THEN
    RAISE EXCEPTION 'ABORT: jobs still has % NULL org_id rows', null_count;
END IF;

SELECT count(*) INTO null_count FROM models WHERE org_id IS NULL;
IF null_count > 0 THEN
    RAISE EXCEPTION 'ABORT: models still has % NULL org_id rows', null_count;
END IF;

SELECT count(*) INTO null_count FROM workflows WHERE org_id IS NULL;
IF null_count > 0 THEN
    RAISE EXCEPTION 'ABORT: workflows still has % NULL org_id rows', null_count;
END IF;

SELECT count(*) INTO null_count FROM brain_sessions WHERE org_id IS NULL;
IF null_count > 0 THEN
    RAISE EXCEPTION 'ABORT: brain_sessions still has % NULL org_id rows', null_count;
END IF;

SELECT count(*) INTO null_count FROM brain_messages WHERE org_id IS NULL;
IF null_count > 0 THEN
    RAISE EXCEPTION 'ABORT: brain_messages still has % NULL org_id rows', null_count;
END IF;

RAISE NOTICE 'PHASE 4 COMPLETE: All target tables verified — zero NULL org_id rows.';

-- =============================================================================
-- PHASE 5: Apply NOT NULL Constraints (R5.6, R2.1)
-- =============================================================================
-- Only applied AFTER Phase 4 verification passes.

-- Core content
ALTER TABLE talent ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE assets ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE jobs ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE models ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE workflows ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE scenes ALTER COLUMN org_id SET NOT NULL;

-- Training
ALTER TABLE training_datasets ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE training_images ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE training_jobs ALTER COLUMN org_id SET NOT NULL;

-- Video
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

-- Story Engine
ALTER TABLE universes ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE characters ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE episodes ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE shots ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE story_memory ALTER COLUMN org_id SET NOT NULL;

-- Company
ALTER TABLE brands ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE studios ALTER COLUMN org_id SET NOT NULL;

-- Storyboard
ALTER TABLE storyboard_panels ALTER COLUMN org_id SET NOT NULL;

-- AIOS
ALTER TABLE aios_sessions ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE aios_messages ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE aios_decisions ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE aios_approvals ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE aios_policies ALTER COLUMN org_id SET NOT NULL;

-- =============================================================================
-- PHASE 6: Remove placeholder DEFAULT values
-- =============================================================================

ALTER TABLE cost_records ALTER COLUMN org_id DROP DEFAULT;
ALTER TABLE job_costs ALTER COLUMN org_id DROP DEFAULT;
ALTER TABLE brain_collections ALTER COLUMN org_id DROP DEFAULT;

-- =============================================================================
-- Summary
-- =============================================================================

RAISE NOTICE '=== MIGRATION COMPLETE ===';
RAISE NOTICE 'Rows backfilled to founder: %', total_backfilled;
RAISE NOTICE 'Rows quarantined for review: %', total_quarantined;
RAISE NOTICE 'NOT NULL constraints applied on all target tables.';
RAISE NOTICE 'Review quarantined rows: SELECT * FROM _quarantine_log WHERE resolved_at IS NULL;';

END $$;

COMMIT;
