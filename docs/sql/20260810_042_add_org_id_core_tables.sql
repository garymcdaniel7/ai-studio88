-- =============================================================================
-- Migration 042: Add org_id to core content tables
-- Date: 2026-08-10
-- Task: 3.2 Apply org_id NOT NULL constraints and backfill
--
-- PURPOSE: Add org_id UUID column (nullable initially) to core content tables
-- that currently lack it entirely, then backfill from founder's org and
-- quarantine any ambiguous rows.
--
-- TABLES COVERED:
--   - talent (Category A — core entity)
--   - assets (Category A — generated/uploaded content)
--   - jobs (Category A — generation/training jobs)
--   - models (Category A — model registry, mixed user + system)
--   - workflows (Category A — user workflows, mixed with system templates)
--
-- NOTE: If these tables already have org_id from a prior migration (e.g.,
-- ghost table migrations), this uses ADD COLUMN IF NOT EXISTS to be idempotent.
--
-- NOTE: training tables are handled by 20260804_009_training_rls.sql.
--
-- PREREQUISITES:
--   - Migration 040 applied (_org_id_quarantine table exists)
--   - FOUNDER_ORG_ID set to verified founder UUID
--   - Backup taken
--
-- REQUIREMENTS: R5.6, R69.1, R69.2, R69.5, R2.1
--
-- SAFETY: Additive migration. No columns dropped.
-- ROLLBACK:
--   -- ALTER TABLE talent DROP COLUMN IF EXISTS org_id;
--   -- ALTER TABLE assets DROP COLUMN IF EXISTS org_id;
--   -- ALTER TABLE jobs DROP COLUMN IF EXISTS org_id;
--   -- ALTER TABLE models DROP COLUMN IF EXISTS org_id;
--   -- ALTER TABLE workflows DROP COLUMN IF EXISTS org_id;
--   -- DROP INDEX IF EXISTS ix_talent_org_id;
--   -- DROP INDEX IF EXISTS ix_assets_org_id;
--   -- DROP INDEX IF EXISTS ix_jobs_org_id;
--   -- DROP INDEX IF EXISTS ix_models_org_id;
--   -- DROP INDEX IF EXISTS ix_workflows_org_id;
--   -- DELETE FROM _org_id_quarantine WHERE table_name IN ('talent','assets','jobs','models','workflows');
-- =============================================================================

BEGIN;

DO $$ DECLARE
    FOUNDER_ORG UUID := '%%FOUNDER_ORG_ID%%';  -- REPLACE BEFORE RUNNING
    SYSTEM_ORG  UUID := '00000000-0000-0000-0000-000000000001';
    null_count  INT;
    backfilled  INT;
BEGIN

-- =============================================================================
-- STEP 1: Add org_id column to each table (nullable initially)
-- =============================================================================

ALTER TABLE talent ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE assets ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE models ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS org_id UUID;

-- =============================================================================
-- STEP 2: Create indexes on org_id (needed for efficient tenant-scoped queries)
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_talent_org_id ON talent(org_id);
CREATE INDEX IF NOT EXISTS ix_assets_org_id ON assets(org_id);
CREATE INDEX IF NOT EXISTS ix_jobs_org_id ON jobs(org_id);
CREATE INDEX IF NOT EXISTS ix_models_org_id ON models(org_id);
CREATE INDEX IF NOT EXISTS ix_workflows_org_id ON workflows(org_id);

-- =============================================================================
-- STEP 3: Quarantine NULL rows (audit trail before backfill)
-- =============================================================================

-- talent
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'talent', id,
    'NULL org_id — column newly added, founder-only platform',
    now()
FROM talent WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
IF null_count > 0 THEN
    RAISE NOTICE 'talent: % rows quarantined', null_count;
END IF;

-- assets
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'assets', id,
    'NULL org_id — column newly added, founder-only platform',
    now()
FROM assets WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
IF null_count > 0 THEN
    RAISE NOTICE 'assets: % rows quarantined', null_count;
END IF;

-- jobs
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'jobs', id,
    'NULL org_id — column newly added, founder-only platform',
    now()
FROM jobs WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
IF null_count > 0 THEN
    RAISE NOTICE 'jobs: % rows quarantined', null_count;
END IF;

-- models (may have system models — quarantine separately)
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'models', id,
    CASE
        WHEN metadata->>'system' = 'true'
            THEN 'NULL org_id — system model, assigning to system org'
        ELSE 'NULL org_id — column newly added, founder-only platform'
    END,
    now()
FROM models WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
IF null_count > 0 THEN
    RAISE NOTICE 'models: % rows quarantined', null_count;
END IF;

-- workflows (may have system templates)
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'workflows', id,
    CASE
        WHEN metadata->>'system' = 'true'
            THEN 'NULL org_id — system workflow template, assigning to system org'
        ELSE 'NULL org_id — column newly added, founder-only platform'
    END,
    now()
FROM workflows WHERE org_id IS NULL;
GET DIAGNOSTICS null_count = ROW_COUNT;
IF null_count > 0 THEN
    RAISE NOTICE 'workflows: % rows quarantined', null_count;
END IF;

-- =============================================================================
-- STEP 4: Backfill org_id
-- =============================================================================
-- Per R5.6: For founder-only tables, bulk assignment is acceptable.
-- System models/workflows get the system org UUID.

-- talent: all rows → founder
UPDATE talent SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'talent: % rows backfilled to founder', backfilled;

-- assets: all rows → founder
UPDATE assets SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'assets: % rows backfilled to founder', backfilled;

-- jobs: all rows → founder
UPDATE jobs SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'jobs: % rows backfilled to founder', backfilled;

-- models: system models → system org, user models → founder
UPDATE models SET org_id = SYSTEM_ORG
WHERE org_id IS NULL AND metadata->>'system' = 'true';
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'models (system): % rows assigned to system org', backfilled;

UPDATE models SET org_id = FOUNDER_ORG
WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'models (user): % rows backfilled to founder', backfilled;

-- workflows: system templates → system org, user workflows → founder
UPDATE workflows SET org_id = SYSTEM_ORG
WHERE org_id IS NULL AND metadata->>'system' = 'true';
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'workflows (system): % rows assigned to system org', backfilled;

UPDATE workflows SET org_id = FOUNDER_ORG
WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'workflows (user): % rows backfilled to founder', backfilled;

-- =============================================================================
-- STEP 5: Mark quarantine records as resolved
-- =============================================================================

UPDATE _org_id_quarantine
SET resolved_at = now(),
    resolution = 'assigned',
    assigned_org_id = FOUNDER_ORG
WHERE resolved_at IS NULL
  AND table_name IN ('talent', 'assets', 'jobs')
  AND reason LIKE '%founder-only%';

UPDATE _org_id_quarantine
SET resolved_at = now(),
    resolution = 'assigned',
    assigned_org_id = FOUNDER_ORG
WHERE resolved_at IS NULL
  AND table_name IN ('models', 'workflows')
  AND reason LIKE '%founder-only%';

UPDATE _org_id_quarantine
SET resolved_at = now(),
    resolution = 'system_owned',
    assigned_org_id = SYSTEM_ORG
WHERE resolved_at IS NULL
  AND table_name IN ('models', 'workflows')
  AND reason LIKE '%system%';

-- =============================================================================
-- STEP 6: Verification
-- =============================================================================

SELECT count(*) INTO null_count FROM talent WHERE org_id IS NULL;
IF null_count > 0 THEN
    RAISE WARNING 'talent: % rows still have NULL org_id after backfill', null_count;
END IF;

SELECT count(*) INTO null_count FROM assets WHERE org_id IS NULL;
IF null_count > 0 THEN
    RAISE WARNING 'assets: % rows still have NULL org_id after backfill', null_count;
END IF;

SELECT count(*) INTO null_count FROM jobs WHERE org_id IS NULL;
IF null_count > 0 THEN
    RAISE WARNING 'jobs: % rows still have NULL org_id after backfill', null_count;
END IF;

SELECT count(*) INTO null_count FROM models WHERE org_id IS NULL;
IF null_count > 0 THEN
    RAISE WARNING 'models: % rows still have NULL org_id after backfill', null_count;
END IF;

SELECT count(*) INTO null_count FROM workflows WHERE org_id IS NULL;
IF null_count > 0 THEN
    RAISE WARNING 'workflows: % rows still have NULL org_id after backfill', null_count;
END IF;

RAISE NOTICE '=== Migration 042 complete: Core tables org_id added and backfilled ===';

END $$;

COMMIT;
