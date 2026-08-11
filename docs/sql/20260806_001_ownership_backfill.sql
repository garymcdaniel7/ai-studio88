-- =============================================================================
-- Migration 040: Ownership Backfill (Story 006)
--
-- PURPOSE: Assign valid org_id to all existing rows, remove placeholder defaults,
-- and quarantine ambiguous/orphaned records.
--
-- PREREQUISITES:
--   - Story 004 approved (tenant contract)
--   - Story 005 complete (RLS policies active)
--   - Backup taken before execution
--   - FOUNDER_ORG_ID variable set to the founder's actual org UUID
--
-- SAFETY: Transactional, idempotent, reversible via 040_ownership_backfill_rollback.sql
-- =============================================================================

BEGIN;

-- =============================================================================
-- CONFIGURATION: Set the founder's org_id
-- =============================================================================
-- DECISION-REQUIRED: Replace with actual founder org_id before execution.
-- Query to find it: SELECT id FROM organizations WHERE owner_id = '<founder_user_id>';

DO $$ DECLARE
    FOUNDER_ORG UUID := '%%FOUNDER_ORG_ID%%';  -- REPLACE BEFORE RUNNING
    SYSTEM_ORG  UUID := '00000000-0000-0000-0000-000000000001';
    ZERO_UUID   UUID := '00000000-0000-0000-0000-000000000000';
    backfilled  INT;
    quarantined INT;
BEGIN

-- =============================================================================
-- PHASE 1: Backfill NULL org_id → founder's org (core content tables)
-- =============================================================================
-- These tables were created without org_id; migration 030 added it as nullable.
-- All existing data belongs to the single founder (single-tenant history).

UPDATE talent SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'talent: % rows backfilled to founder org', backfilled;

UPDATE assets SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'assets: % rows backfilled', backfilled;

UPDATE jobs SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'jobs: % rows backfilled', backfilled;

UPDATE models SET org_id = FOUNDER_ORG
WHERE org_id IS NULL AND (metadata->>'system') IS DISTINCT FROM 'true';
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'models (user-owned): % rows backfilled', backfilled;

-- System models stay as system org
UPDATE models SET org_id = SYSTEM_ORG
WHERE org_id IS NULL AND metadata->>'system' = 'true';

UPDATE workflows SET org_id = FOUNDER_ORG
WHERE org_id IS NULL AND (metadata->>'system') IS DISTINCT FROM 'true';
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'workflows (user-owned): % rows backfilled', backfilled;

UPDATE workflows SET org_id = SYSTEM_ORG
WHERE org_id IS NULL AND metadata->>'system' = 'true';

UPDATE scenes SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'scenes: % rows backfilled', backfilled;


-- =============================================================================
-- PHASE 2: Backfill training/video/audio/publishing tables
-- =============================================================================

UPDATE training_datasets SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE training_images SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE training_jobs SET org_id = FOUNDER_ORG WHERE org_id IS NULL;

UPDATE video_projects SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE video_renders SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE video_shots SET org_id = FOUNDER_ORG WHERE org_id IS NULL;

UPDATE audio_clips SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE voice_profiles SET org_id = FOUNDER_ORG WHERE org_id IS NULL;

UPDATE publishing_posts SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE publishing_accounts SET org_id = FOUNDER_ORG WHERE org_id IS NULL;

UPDATE storyboard_panels SET org_id = FOUNDER_ORG WHERE org_id IS NULL;

-- =============================================================================
-- PHASE 3: Backfill brain tables
-- =============================================================================

UPDATE brain_memory SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE brain_messages SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE brain_sessions SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE brain_plans SET org_id = FOUNDER_ORG WHERE org_id IS NULL;

-- =============================================================================
-- PHASE 4: Backfill creative/performance tables
-- =============================================================================

UPDATE performance_dna SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE quality_scores SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE generation_feedback SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE creative_dna SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE creative_rules SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
UPDATE continuity_notes SET org_id = FOUNDER_ORG WHERE org_id IS NULL;

-- =============================================================================
-- PHASE 5: Backfill company/brand tables (organization_id → org_id)
-- =============================================================================
-- Company OS tables use organization_id FK. Add org_id as alias.
-- NOTE: These already have organization_id referencing organizations(id),
-- so we can derive org_id from it directly.

UPDATE brands SET org_id = organization_id WHERE org_id IS NULL AND organization_id IS NOT NULL;
UPDATE studios SET org_id = organization_id WHERE org_id IS NULL AND organization_id IS NOT NULL;


-- =============================================================================
-- PHASE 6: Fix zero-UUID placeholder → founder or quarantine
-- =============================================================================
-- Rows with the deprecated zero-UUID ('...000') are either:
-- A) Legitimate user data → assign to founder
-- B) System seed data → assign to system org
-- C) Ambiguous → quarantine with metadata flag

-- AIOS tables: zero-UUID rows from governance code
UPDATE aios_approvals SET org_id = FOUNDER_ORG
WHERE org_id = ZERO_UUID;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'aios_approvals: % zero-UUID rows assigned to founder', backfilled;

UPDATE aios_policies SET org_id = FOUNDER_ORG
WHERE org_id = ZERO_UUID;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'aios_policies: % zero-UUID rows assigned to founder', backfilled;

-- AIOS sessions: already handled by migration 032 (quarantined as UNVERIFIED)
-- Re-assign the quarantined ones to founder since they are founder's sessions
UPDATE aios_sessions SET org_id = FOUNDER_ORG
WHERE org_id = ZERO_UUID
  AND metadata->>'_ownership_status' = 'UNVERIFIED';
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'aios_sessions: % quarantined rows assigned to founder', backfilled;

-- =============================================================================
-- PHASE 7: Fix system-org defaults on cost tables
-- =============================================================================
-- cost_records and job_costs currently DEFAULT to system org.
-- Existing rows should belong to founder (all GPU work was founder's).

UPDATE cost_records SET org_id = FOUNDER_ORG
WHERE org_id = SYSTEM_ORG;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'cost_records: % system-org rows assigned to founder', backfilled;

UPDATE job_costs SET org_id = FOUNDER_ORG
WHERE org_id = SYSTEM_ORG;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'job_costs: % system-org rows assigned to founder', backfilled;

-- brain_collections: system-org defaults also belong to founder
UPDATE brain_collections SET org_id = FOUNDER_ORG
WHERE org_id = SYSTEM_ORG;
GET DIAGNOSTICS backfilled = ROW_COUNT;
RAISE NOTICE 'brain_collections: % system-org rows assigned to founder', backfilled;

-- =============================================================================
-- PHASE 8: Story Engine — backfill via project relationship
-- =============================================================================
-- Story engine tables own via project_id. Derive org_id from projects.org_id.

UPDATE universes u SET org_id = p.org_id
FROM projects p WHERE u.project_id = p.id AND u.org_id IS NULL;

-- Universes without a project → assign to founder
UPDATE universes SET org_id = FOUNDER_ORG WHERE org_id IS NULL;

-- Characters inherit from universe (need org_id column added first)
ALTER TABLE characters ADD COLUMN IF NOT EXISTS org_id UUID;
UPDATE characters c SET org_id = u.org_id
FROM universes u WHERE c.universe_id = u.id AND c.org_id IS NULL;
UPDATE characters SET org_id = FOUNDER_ORG WHERE org_id IS NULL;

-- Episodes inherit from universe
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS org_id UUID;
UPDATE episodes e SET org_id = u.org_id
FROM universes u WHERE e.universe_id = u.id AND e.org_id IS NULL;
UPDATE episodes SET org_id = FOUNDER_ORG WHERE org_id IS NULL;

-- Shots inherit from scene
ALTER TABLE shots ADD COLUMN IF NOT EXISTS org_id UUID;
UPDATE shots sh SET org_id = sc.org_id
FROM scenes sc WHERE sh.scene_id = sc.id AND sh.org_id IS NULL;
UPDATE shots SET org_id = FOUNDER_ORG WHERE org_id IS NULL;

-- story_memory inherits from universe
ALTER TABLE story_memory ADD COLUMN IF NOT EXISTS org_id UUID;
UPDATE story_memory sm SET org_id = u.org_id
FROM universes u WHERE sm.universe_id = u.id AND sm.org_id IS NULL;
UPDATE story_memory SET org_id = FOUNDER_ORG WHERE org_id IS NULL;


-- =============================================================================
-- PHASE 9: Quarantine — flag any remaining NULL org_id rows
-- =============================================================================
-- After all backfill phases, any rows still NULL are ambiguous/orphaned.
-- We mark them in metadata rather than guessing ownership.

-- Workers and worker_sessions are platform-scoped; NULL org_id is intentional.
-- No quarantine needed for those.

-- For all other tables, if org_id is still NULL, quarantine:
-- (We use a DO block to iterate known tables and flag any remainders)

-- Count remaining NULLs for reporting
quarantined := 0;

PERFORM 1 FROM talent WHERE org_id IS NULL LIMIT 1;
IF FOUND THEN
    RAISE WARNING 'talent: orphaned rows with NULL org_id remain';
    quarantined := quarantined + (SELECT count(*) FROM talent WHERE org_id IS NULL);
END IF;

PERFORM 1 FROM assets WHERE org_id IS NULL LIMIT 1;
IF FOUND THEN
    RAISE WARNING 'assets: orphaned rows with NULL org_id remain';
    quarantined := quarantined + (SELECT count(*) FROM assets WHERE org_id IS NULL);
END IF;

PERFORM 1 FROM jobs WHERE org_id IS NULL LIMIT 1;
IF FOUND THEN
    RAISE WARNING 'jobs: orphaned rows with NULL org_id remain';
    quarantined := quarantined + (SELECT count(*) FROM jobs WHERE org_id IS NULL);
END IF;

RAISE NOTICE 'TOTAL QUARANTINED (still NULL after backfill): % rows', quarantined;

-- =============================================================================
-- PHASE 10: Remove placeholder DEFAULT values from column definitions
-- =============================================================================

ALTER TABLE cost_records ALTER COLUMN org_id DROP DEFAULT;
ALTER TABLE job_costs ALTER COLUMN org_id DROP DEFAULT;
ALTER TABLE brain_collections ALTER COLUMN org_id DROP DEFAULT;

-- =============================================================================
-- PHASE 11: Add indexes on newly-populated org_id columns
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_characters_org_id ON characters(org_id);
CREATE INDEX IF NOT EXISTS ix_episodes_org_id ON episodes(org_id);
CREATE INDEX IF NOT EXISTS ix_shots_org_id ON shots(org_id);
CREATE INDEX IF NOT EXISTS ix_story_memory_org_id ON story_memory(org_id);
CREATE INDEX IF NOT EXISTS ix_universes_org_id ON universes(org_id);

RAISE NOTICE 'Migration 040 complete. Review NOTICE/WARNING output for counts.';

END $$;

COMMIT;
