-- =============================================================================
-- Migration 041: Backfill existing nullable org_id columns
-- Date: 2026-08-10
-- Task: 3.2 Apply org_id NOT NULL constraints and backfill
--
-- PURPOSE: For tables that ALREADY have an org_id column (but nullable),
-- quarantine NULL rows into _org_id_quarantine, then backfill to founder org.
--
-- TABLES COVERED (already have org_id, nullable):
--   - aios_approvals, aios_policies, aios_sessions
--   - brain_collections, brain_conversations, brain_embeddings
--   - cost_records, job_costs
--   - workflow_dna, brain_memory
--
-- NOTE: training tables (training_datasets, training_images, training_jobs,
-- lora_versions, lora_evaluations, talent_loras) are handled by
-- 20260804_009_training_rls.sql — not duplicated here.
--
-- PREREQUISITES:
--   - Migration 040 applied (_org_id_quarantine table exists)
--   - FOUNDER_ORG_ID set to verified founder UUID before execution
--   - Backup taken
--
-- REQUIREMENTS: R5.6, R69.1, R69.2, R69.3, R69.5, R2.1
--
-- PROCESS:
--   1. Quarantine all NULL org_id rows (insert into _org_id_quarantine)
--   2. Backfill NULL org_id → founder org (verified single-founder platform)
--   3. Fix zero-UUID placeholder rows
--   4. Remove placeholder DEFAULT values
--
-- SAFETY: Transactional, idempotent.
-- ROLLBACK:
--   -- Reverse backfill (restore NULLs for quarantined rows):
--   -- UPDATE <table> SET org_id = NULL
--   --   WHERE id IN (SELECT row_id FROM _org_id_quarantine WHERE table_name = '<table>');
--   -- DELETE FROM _org_id_quarantine WHERE quarantined_at >= '<migration_timestamp>';
-- =============================================================================

BEGIN;

DO $$ DECLARE
    -- CONFIGURATION: Replace with actual founder org UUID before execution.
    -- Query: SELECT id FROM organizations ORDER BY created_at ASC LIMIT 1;
    FOUNDER_ORG UUID := '%%FOUNDER_ORG_ID%%';  -- REPLACE BEFORE RUNNING
    ZERO_UUID   UUID := '00000000-0000-0000-0000-000000000000';
    null_count  INT;
    backfilled  INT;
    total_quarantined INT := 0;
    total_backfilled  INT := 0;
BEGIN

-- =============================================================================
-- PHASE 1: Quarantine NULL org_id rows (record before modifying)
-- =============================================================================
-- Per R69.2: Document every NULL org_id row with reason and date before
-- any ownership assignment. This provides audit trail if assignments are wrong.

-- aios_approvals
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'aios_approvals', id,
    'NULL org_id — founder-only platform, auto-assigning to founder',
    now()
FROM aios_approvals WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_quarantined := total_quarantined + null_count;

-- aios_policies
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'aios_policies', id,
    'NULL org_id — founder-only platform, auto-assigning to founder',
    now()
FROM aios_policies WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_quarantined := total_quarantined + null_count;

-- aios_sessions
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'aios_sessions', id,
    'NULL org_id — founder-only platform, auto-assigning to founder',
    now()
FROM aios_sessions WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_quarantined := total_quarantined + null_count;

-- brain_collections
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'brain_collections', id,
    'NULL org_id — founder-only platform, auto-assigning to founder',
    now()
FROM brain_collections WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_quarantined := total_quarantined + null_count;

-- brain_conversations
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'brain_conversations', id,
    'NULL org_id — founder-only platform, auto-assigning to founder',
    now()
FROM brain_conversations WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_quarantined := total_quarantined + null_count;

-- brain_embeddings
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'brain_embeddings', id,
    'NULL org_id — founder-only platform, auto-assigning to founder',
    now()
FROM brain_embeddings WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_quarantined := total_quarantined + null_count;

-- cost_records
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'cost_records', id,
    'NULL org_id or system-org default — founder-only, reassigning to founder',
    now()
FROM cost_records WHERE org_id IS NULL OR org_id = ZERO_UUID;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_quarantined := total_quarantined + null_count;

-- job_costs
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'job_costs', id,
    'NULL org_id or system-org default — founder-only, reassigning to founder',
    now()
FROM job_costs WHERE org_id IS NULL OR org_id = ZERO_UUID;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_quarantined := total_quarantined + null_count;

-- workflow_dna
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'workflow_dna', id,
    'NULL org_id — founder-only platform, auto-assigning to founder',
    now()
FROM workflow_dna WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_quarantined := total_quarantined + null_count;

-- brain_memory
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'brain_memory', id,
    'NULL org_id — founder-only platform, auto-assigning to founder',
    now()
FROM brain_memory WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
total_quarantined := total_quarantined + null_count;

RAISE NOTICE 'PHASE 1 COMPLETE: % rows quarantined (audit trail created)', total_quarantined;

-- =============================================================================
-- PHASE 2: Backfill NULL org_id → founder org
-- =============================================================================
-- Per R5.6: For founder-only tables (verified by audit — only one non-system
-- org has ever existed), bulk assignment to founder org_id is acceptable.

UPDATE aios_approvals SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE aios_policies SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE aios_sessions SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE brain_collections SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE brain_conversations SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE brain_embeddings SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE cost_records SET org_id = FOUNDER_ORG WHERE org_id IS NULL OR org_id = ZERO_UUID;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE job_costs SET org_id = FOUNDER_ORG WHERE org_id IS NULL OR org_id = ZERO_UUID;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE workflow_dna SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE brain_memory SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

RAISE NOTICE 'PHASE 2 COMPLETE: % rows backfilled to founder org', total_backfilled;

-- =============================================================================
-- PHASE 3: Fix zero-UUID placeholder values
-- =============================================================================
-- The quarantined UUID (00000000-...) should never be used as an org_id.
-- Per R2.8: Platform SHALL reject this UUID with 422.

UPDATE aios_approvals SET org_id = FOUNDER_ORG WHERE org_id = ZERO_UUID;
UPDATE aios_policies SET org_id = FOUNDER_ORG WHERE org_id = ZERO_UUID;
UPDATE aios_sessions SET org_id = FOUNDER_ORG WHERE org_id = ZERO_UUID;
UPDATE brain_collections SET org_id = FOUNDER_ORG WHERE org_id = ZERO_UUID;
UPDATE brain_conversations SET org_id = FOUNDER_ORG WHERE org_id = ZERO_UUID;
UPDATE brain_embeddings SET org_id = FOUNDER_ORG WHERE org_id = ZERO_UUID;
UPDATE workflow_dna SET org_id = FOUNDER_ORG WHERE org_id = ZERO_UUID;
UPDATE brain_memory SET org_id = FOUNDER_ORG WHERE org_id = ZERO_UUID;

-- =============================================================================
-- PHASE 4: Remove placeholder DEFAULT values from column definitions
-- =============================================================================
-- These columns had DEFAULT quarantined-UUID or system-org values that
-- should be removed now that proper org_id is enforced at the service layer.

ALTER TABLE cost_records ALTER COLUMN org_id DROP DEFAULT;
ALTER TABLE job_costs ALTER COLUMN org_id DROP DEFAULT;
ALTER TABLE brain_collections ALTER COLUMN org_id DROP DEFAULT;

-- =============================================================================
-- PHASE 5: Mark quarantine records as resolved
-- =============================================================================
-- Since we bulk-assigned all to founder (verified single-founder platform),
-- mark the quarantine records as resolved.

UPDATE _org_id_quarantine
SET resolved_at = now(),
    resolution = 'assigned',
    assigned_org_id = FOUNDER_ORG
WHERE resolved_at IS NULL
  AND table_name IN (
    'aios_approvals', 'aios_policies', 'aios_sessions',
    'brain_collections', 'brain_conversations', 'brain_embeddings',
    'cost_records', 'job_costs', 'workflow_dna', 'brain_memory'
  );

RAISE NOTICE '=== Migration 041 complete ===';
RAISE NOTICE 'Quarantined: %', total_quarantined;
RAISE NOTICE 'Backfilled: %', total_backfilled;

END $$;

COMMIT;
