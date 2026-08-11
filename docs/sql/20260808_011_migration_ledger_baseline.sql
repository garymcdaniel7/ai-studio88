-- =============================================================================
-- Migration: Migration Ledger Baseline Registration
-- Task: 1.4 (Populate migration ledger and register baseline)
-- Date: 2026-08-08
-- =============================================================================
--
-- PURPOSE:
-- Creates the _migration_ledger table (idempotent) and registers baseline
-- entries for all ghost table migrations (20260808_001 through _010) that
-- are already applied to the live database.
--
-- IMPORTANT: This does NOT execute any actual schema changes against the
-- live database. It only establishes the ledger table and populates it with
-- status records for tracking purposes.
--
-- Validates: Requirements R5.4, R5.9, R5.10
-- =============================================================================

-- 1. Create the _migration_ledger table (idempotent — safe to re-run)
CREATE TABLE IF NOT EXISTS _migration_ledger (
    migration_id      TEXT PRIMARY KEY,
    sha256_checksum   TEXT NOT NULL,
    applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    status            TEXT DEFAULT 'applied',
    notes             TEXT
);

-- 2. Register baseline entries for ghost table migrations (already in live DB)
-- These tables were created via Dashboard or direct SQL before migrations existed.
-- Status 'baseline' means: already applied to live DB, documented for ledger tracking.

INSERT INTO _migration_ledger (migration_id, sha256_checksum, applied_at, status, notes)
VALUES
    ('20260808_001_ghost_table_talent',
     '-- populated by populate_migration_ledger.py --',
     now(), 'baseline',
     'Ghost table: talent. Already exists in live DB. Documented by Task 1.2.'),

    ('20260808_002_ghost_table_assets',
     '-- populated by populate_migration_ledger.py --',
     now(), 'baseline',
     'Ghost table: assets. Already exists in live DB. Documented by Task 1.2.'),

    ('20260808_003_ghost_table_service_settings',
     '-- populated by populate_migration_ledger.py --',
     now(), 'baseline',
     'Ghost table: service_settings. Already exists in live DB. Documented by Task 1.2.'),

    ('20260808_004_ghost_table_collections',
     '-- populated by populate_migration_ledger.py --',
     now(), 'baseline',
     'Ghost table: collections. Already exists in live DB. Documented by Task 1.2.'),

    ('20260808_005_ghost_table_prompts',
     '-- populated by populate_migration_ledger.py --',
     now(), 'baseline',
     'Ghost table: prompts. Already exists in live DB. Documented by Task 1.2.'),

    ('20260808_006_ghost_table_products',
     '-- populated by populate_migration_ledger.py --',
     now(), 'baseline',
     'Ghost table: products. Already exists in live DB. Documented by Task 1.2.'),

    ('20260808_007_ghost_table_content_calendar',
     '-- populated by populate_migration_ledger.py --',
     now(), 'baseline',
     'Ghost table: content_calendar. Already exists in live DB. Documented by Task 1.2.'),

    ('20260808_008_ghost_table_campaigns',
     '-- populated by populate_migration_ledger.py --',
     now(), 'baseline',
     'Ghost table: campaigns. Already exists in live DB. Documented by Task 1.2.'),

    ('20260808_009_ghost_table_performance_memory',
     '-- populated by populate_migration_ledger.py --',
     now(), 'baseline',
     'Ghost table: performance_memory. Already exists in live DB. Documented by Task 1.2.'),

    ('20260808_010_ghost_table_workflow_dna',
     '-- populated by populate_migration_ledger.py --',
     now(), 'baseline',
     'Ghost table: workflow_dna. Already exists in live DB. Documented by Task 1.2.')
ON CONFLICT (migration_id) DO NOTHING;

-- Note: The sha256_checksum values above are placeholders.
-- Run backend/scripts/populate_migration_ledger.py to compute real checksums
-- and update/insert all migration records with accurate hashes.
