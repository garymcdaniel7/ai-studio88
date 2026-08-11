-- =============================================================================
-- Migration 044: Add org_id to intelligence, creative, performance, cinematic,
--               company, and remaining Category A tables
-- Date: 2026-08-10
-- Task: 3.2 Apply org_id NOT NULL constraints and backfill
--
-- PURPOSE: Add org_id UUID column to all remaining Category A tables that
-- lack it, then backfill from founder's org.
--
-- TABLE GROUPS COVERED:
--   Brain: brain_sessions, brain_messages, brain_plans
--   Creative: creative_dna, creative_rules, continuity_notes,
--             generation_feedback, prompt_history, style_preferences,
--             learning_events, prompts
--   Performance: performance_dna, performance_memory, quality_scores,
--                production_insights
--   Cinematic: sequences, cinematic_timelines, cinematic_tracks,
--              cinematic_items, cinematic_renders, editing_operations,
--              storyboard_panels
--   Company: brands, campaigns, content_calendar, products, series
--   Asset Intelligence: visual_dna, asset_collections, collection_items,
--                       asset_relationships, wardrobes, outfits, collections
--   Story Engine: (characters, episodes, shots, story_memory already have
--                  org_id from 20260806_001_ownership_backfill.sql)
--   Remaining: talent_assets, talent_relationships, talent_voices,
--              workflow_runs, lora_versions, lora_evaluations
--
-- NOTE: Some tables may already have org_id from earlier migrations.
-- Uses ADD COLUMN IF NOT EXISTS for idempotency.
--
-- PREREQUISITES:
--   - Migrations 040-043 applied
--   - FOUNDER_ORG_ID set to verified founder UUID
--   - Backup taken
--
-- REQUIREMENTS: R5.6, R69.1, R69.2, R69.5, R2.1
--
-- SAFETY: Additive migration. Uses IF NOT EXISTS for idempotency.
-- ROLLBACK:
--   -- ALTER TABLE <table> DROP COLUMN IF EXISTS org_id;
--   -- DROP INDEX IF EXISTS ix_<table>_org_id;
--   -- DELETE FROM _org_id_quarantine WHERE table_name IN (...);
-- =============================================================================

BEGIN;

DO $$ DECLARE
    FOUNDER_ORG UUID := '%%FOUNDER_ORG_ID%%';  -- REPLACE BEFORE RUNNING
    null_count  INT;
    backfilled  INT;
    total_backfilled INT := 0;
BEGIN

-- =============================================================================
-- BRAIN TABLES
-- =============================================================================

ALTER TABLE brain_sessions ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE brain_messages ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE brain_plans ADD COLUMN IF NOT EXISTS org_id UUID;

CREATE INDEX IF NOT EXISTS ix_brain_sessions_org_id ON brain_sessions(org_id);
CREATE INDEX IF NOT EXISTS ix_brain_messages_org_id ON brain_messages(org_id);
CREATE INDEX IF NOT EXISTS ix_brain_plans_org_id ON brain_plans(org_id);

-- Quarantine + Backfill
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'brain_sessions', id, 'NULL org_id — column added, founder-only', now()
FROM brain_sessions WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'brain_messages', id, 'NULL org_id — column added, founder-only', now()
FROM brain_messages WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'brain_plans', id, 'NULL org_id — column added, founder-only', now()
FROM brain_plans WHERE org_id IS NULL;

UPDATE brain_sessions SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE brain_messages SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE brain_plans SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

RAISE NOTICE 'Brain tables: % rows backfilled', total_backfilled;

-- =============================================================================
-- CREATIVE TABLES
-- =============================================================================

total_backfilled := 0;

ALTER TABLE creative_dna ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE creative_rules ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE continuity_notes ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE generation_feedback ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE prompt_history ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE style_preferences ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE learning_events ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE prompts ADD COLUMN IF NOT EXISTS org_id UUID;

CREATE INDEX IF NOT EXISTS ix_creative_dna_org_id ON creative_dna(org_id);
CREATE INDEX IF NOT EXISTS ix_creative_rules_org_id ON creative_rules(org_id);
CREATE INDEX IF NOT EXISTS ix_continuity_notes_org_id ON continuity_notes(org_id);
CREATE INDEX IF NOT EXISTS ix_generation_feedback_org_id ON generation_feedback(org_id);
CREATE INDEX IF NOT EXISTS ix_prompt_history_org_id ON prompt_history(org_id);
CREATE INDEX IF NOT EXISTS ix_style_preferences_org_id ON style_preferences(org_id);
CREATE INDEX IF NOT EXISTS ix_learning_events_org_id ON learning_events(org_id);
CREATE INDEX IF NOT EXISTS ix_prompts_org_id ON prompts(org_id);

-- Quarantine + Backfill
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'creative_dna', id, 'NULL org_id — column added, founder-only', now()
FROM creative_dna WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'creative_rules', id, 'NULL org_id — column added, founder-only', now()
FROM creative_rules WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'continuity_notes', id, 'NULL org_id — column added, founder-only', now()
FROM continuity_notes WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'generation_feedback', id, 'NULL org_id — column added, founder-only', now()
FROM generation_feedback WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'prompt_history', id, 'NULL org_id — column added, founder-only', now()
FROM prompt_history WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'style_preferences', id, 'NULL org_id — column added, founder-only', now()
FROM style_preferences WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'learning_events', id, 'NULL org_id — column added, founder-only', now()
FROM learning_events WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'prompts', id, 'NULL org_id — column added, founder-only', now()
FROM prompts WHERE org_id IS NULL;

UPDATE creative_dna SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE creative_rules SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE continuity_notes SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE generation_feedback SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE prompt_history SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE style_preferences SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE learning_events SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE prompts SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

RAISE NOTICE 'Creative tables: % rows backfilled', total_backfilled;

-- =============================================================================
-- PERFORMANCE TABLES
-- =============================================================================

total_backfilled := 0;

ALTER TABLE performance_dna ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE performance_memory ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE quality_scores ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE production_insights ADD COLUMN IF NOT EXISTS org_id UUID;

CREATE INDEX IF NOT EXISTS ix_performance_dna_org_id ON performance_dna(org_id);
CREATE INDEX IF NOT EXISTS ix_performance_memory_org_id ON performance_memory(org_id);
CREATE INDEX IF NOT EXISTS ix_quality_scores_org_id ON quality_scores(org_id);
CREATE INDEX IF NOT EXISTS ix_production_insights_org_id ON production_insights(org_id);

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'performance_dna', id, 'NULL org_id — column added, founder-only', now()
FROM performance_dna WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'performance_memory', id, 'NULL org_id — column added, founder-only', now()
FROM performance_memory WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'quality_scores', id, 'NULL org_id — column added, founder-only', now()
FROM quality_scores WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'production_insights', id, 'NULL org_id — column added, founder-only', now()
FROM production_insights WHERE org_id IS NULL;

UPDATE performance_dna SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE performance_memory SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE quality_scores SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE production_insights SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

RAISE NOTICE 'Performance tables: % rows backfilled', total_backfilled;

-- =============================================================================
-- CINEMATIC TABLES
-- =============================================================================

total_backfilled := 0;

ALTER TABLE sequences ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE cinematic_timelines ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE cinematic_tracks ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE cinematic_items ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE cinematic_renders ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE editing_operations ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE storyboard_panels ADD COLUMN IF NOT EXISTS org_id UUID;

CREATE INDEX IF NOT EXISTS ix_sequences_org_id ON sequences(org_id);
CREATE INDEX IF NOT EXISTS ix_cinematic_timelines_org_id ON cinematic_timelines(org_id);
CREATE INDEX IF NOT EXISTS ix_cinematic_tracks_org_id ON cinematic_tracks(org_id);
CREATE INDEX IF NOT EXISTS ix_cinematic_items_org_id ON cinematic_items(org_id);
CREATE INDEX IF NOT EXISTS ix_cinematic_renders_org_id ON cinematic_renders(org_id);
CREATE INDEX IF NOT EXISTS ix_editing_operations_org_id ON editing_operations(org_id);
CREATE INDEX IF NOT EXISTS ix_storyboard_panels_org_id ON storyboard_panels(org_id);

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'sequences', id, 'NULL org_id — column added, founder-only', now()
FROM sequences WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'cinematic_timelines', id, 'NULL org_id — column added, founder-only', now()
FROM cinematic_timelines WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'cinematic_tracks', id, 'NULL org_id — column added, founder-only', now()
FROM cinematic_tracks WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'cinematic_items', id, 'NULL org_id — column added, founder-only', now()
FROM cinematic_items WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'cinematic_renders', id, 'NULL org_id — column added, founder-only', now()
FROM cinematic_renders WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'editing_operations', id, 'NULL org_id — column added, founder-only', now()
FROM editing_operations WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'storyboard_panels', id, 'NULL org_id — column added, founder-only', now()
FROM storyboard_panels WHERE org_id IS NULL;

UPDATE sequences SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE cinematic_timelines SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE cinematic_tracks SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE cinematic_items SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE cinematic_renders SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE editing_operations SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE storyboard_panels SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

RAISE NOTICE 'Cinematic tables: % rows backfilled', total_backfilled;

-- =============================================================================
-- COMPANY / COMMERCE TABLES
-- =============================================================================

total_backfilled := 0;

ALTER TABLE brands ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE content_calendar ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE products ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE series ADD COLUMN IF NOT EXISTS org_id UUID;

CREATE INDEX IF NOT EXISTS ix_brands_org_id ON brands(org_id);
CREATE INDEX IF NOT EXISTS ix_campaigns_org_id ON campaigns(org_id);
CREATE INDEX IF NOT EXISTS ix_content_calendar_org_id ON content_calendar(org_id);
CREATE INDEX IF NOT EXISTS ix_products_org_id ON products(org_id);
CREATE INDEX IF NOT EXISTS ix_series_org_id ON series(org_id);

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'brands', id, 'NULL org_id — column added, founder-only', now()
FROM brands WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'campaigns', id, 'NULL org_id — column added, founder-only', now()
FROM campaigns WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'content_calendar', id, 'NULL org_id — column added, founder-only', now()
FROM content_calendar WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'products', id, 'NULL org_id — column added, founder-only', now()
FROM products WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'series', id, 'NULL org_id — column added, founder-only', now()
FROM series WHERE org_id IS NULL;

-- For brands: try to derive org_id from organization_id FK if present
UPDATE brands SET org_id = organization_id
WHERE org_id IS NULL AND organization_id IS NOT NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

-- Remaining brands without organization_id → founder
UPDATE brands SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE campaigns SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE content_calendar SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE products SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE series SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

RAISE NOTICE 'Company/commerce tables: % rows backfilled', total_backfilled;

-- =============================================================================
-- ASSET INTELLIGENCE TABLES
-- =============================================================================

total_backfilled := 0;

ALTER TABLE visual_dna ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE asset_collections ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE collection_items ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE asset_relationships ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE wardrobes ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE outfits ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE collections ADD COLUMN IF NOT EXISTS org_id UUID;

CREATE INDEX IF NOT EXISTS ix_visual_dna_org_id ON visual_dna(org_id);
CREATE INDEX IF NOT EXISTS ix_asset_collections_org_id ON asset_collections(org_id);
CREATE INDEX IF NOT EXISTS ix_collection_items_org_id ON collection_items(org_id);
CREATE INDEX IF NOT EXISTS ix_asset_relationships_org_id ON asset_relationships(org_id);
CREATE INDEX IF NOT EXISTS ix_wardrobes_org_id ON wardrobes(org_id);
CREATE INDEX IF NOT EXISTS ix_outfits_org_id ON outfits(org_id);
CREATE INDEX IF NOT EXISTS ix_collections_org_id ON collections(org_id);

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'visual_dna', id, 'NULL org_id — column added, founder-only', now()
FROM visual_dna WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'asset_collections', id, 'NULL org_id — column added, founder-only', now()
FROM asset_collections WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'collection_items', id, 'NULL org_id — column added, founder-only', now()
FROM collection_items WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'asset_relationships', id, 'NULL org_id — column added, founder-only', now()
FROM asset_relationships WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'wardrobes', id, 'NULL org_id — column added, founder-only', now()
FROM wardrobes WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'outfits', id, 'NULL org_id — column added, founder-only', now()
FROM outfits WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'collections', id, 'NULL org_id — column added, founder-only', now()
FROM collections WHERE org_id IS NULL;

UPDATE visual_dna SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE asset_collections SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE collection_items SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE asset_relationships SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE wardrobes SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE outfits SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE collections SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

RAISE NOTICE 'Asset intelligence tables: % rows backfilled', total_backfilled;

-- =============================================================================
-- REMAINING TABLES (talent relations, workflow runs, lora)
-- =============================================================================

total_backfilled := 0;

ALTER TABLE talent_assets ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE talent_relationships ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE talent_voices ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE lora_versions ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE lora_evaluations ADD COLUMN IF NOT EXISTS org_id UUID;

CREATE INDEX IF NOT EXISTS ix_talent_assets_org_id ON talent_assets(org_id);
CREATE INDEX IF NOT EXISTS ix_talent_relationships_org_id ON talent_relationships(org_id);
CREATE INDEX IF NOT EXISTS ix_talent_voices_org_id ON talent_voices(org_id);
CREATE INDEX IF NOT EXISTS ix_workflow_runs_org_id ON workflow_runs(org_id);
CREATE INDEX IF NOT EXISTS ix_lora_versions_org_id ON lora_versions(org_id);
CREATE INDEX IF NOT EXISTS ix_lora_evaluations_org_id ON lora_evaluations(org_id);

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'talent_assets', id, 'NULL org_id — column added, founder-only', now()
FROM talent_assets WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'talent_relationships', id, 'NULL org_id — column added, founder-only', now()
FROM talent_relationships WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'talent_voices', id, 'NULL org_id — column added, founder-only', now()
FROM talent_voices WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'workflow_runs', id, 'NULL org_id — column added, founder-only', now()
FROM workflow_runs WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'lora_versions', id, 'NULL org_id — column added, founder-only', now()
FROM lora_versions WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'lora_evaluations', id, 'NULL org_id — column added, founder-only', now()
FROM lora_evaluations WHERE org_id IS NULL;

UPDATE talent_assets SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE talent_relationships SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE talent_voices SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE workflow_runs SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE lora_versions SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE lora_evaluations SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

RAISE NOTICE 'Remaining tables: % rows backfilled', total_backfilled;

-- =============================================================================
-- Mark all quarantine records from this migration as resolved
-- =============================================================================

UPDATE _org_id_quarantine
SET resolved_at = now(),
    resolution = 'assigned',
    assigned_org_id = FOUNDER_ORG
WHERE resolved_at IS NULL
  AND reason LIKE '%column added, founder-only%';

RAISE NOTICE '=== Migration 044 complete: Intelligence + remaining tables org_id added ===';

END $$;

COMMIT;
