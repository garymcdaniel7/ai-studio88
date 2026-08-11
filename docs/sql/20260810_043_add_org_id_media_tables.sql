-- =============================================================================
-- Migration 043: Add org_id to media tables (video, audio, publishing)
-- Date: 2026-08-10
-- Task: 3.2 Apply org_id NOT NULL constraints and backfill
--
-- PURPOSE: Add org_id UUID column to video, audio, and publishing tables
-- that currently lack it, then backfill from founder's org.
--
-- TABLES COVERED:
--   Video: video_projects, video_shots, video_renders,
--          timeline_tracks, timeline_clips, timeline_exports
--   Audio: voice_profiles, voice_samples, voice_datasets,
--          voice_dna, voice_training_jobs, voice_versions,
--          audio_clips, lip_sync_jobs, music_tracks_db,
--          sound_effects, songs, soundtrack_cues
--   Publishing: publishing_accounts, publishing_posts, analytics_snapshots
--
-- NOTE: Training tables handled by 20260804_009_training_rls.sql.
--
-- PREREQUISITES:
--   - Migration 040 applied (_org_id_quarantine exists)
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
-- VIDEO TABLES
-- =============================================================================

-- Add org_id columns
ALTER TABLE video_projects ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE video_shots ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE video_renders ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE timeline_tracks ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE timeline_clips ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE timeline_exports ADD COLUMN IF NOT EXISTS org_id UUID;

-- Add indexes
CREATE INDEX IF NOT EXISTS ix_video_projects_org_id ON video_projects(org_id);
CREATE INDEX IF NOT EXISTS ix_video_shots_org_id ON video_shots(org_id);
CREATE INDEX IF NOT EXISTS ix_video_renders_org_id ON video_renders(org_id);
CREATE INDEX IF NOT EXISTS ix_timeline_tracks_org_id ON timeline_tracks(org_id);
CREATE INDEX IF NOT EXISTS ix_timeline_clips_org_id ON timeline_clips(org_id);
CREATE INDEX IF NOT EXISTS ix_timeline_exports_org_id ON timeline_exports(org_id);

-- Quarantine NULL rows
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'video_projects', id, 'NULL org_id — column added, founder-only', now()
FROM video_projects WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'video_shots', id, 'NULL org_id — column added, founder-only', now()
FROM video_shots WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'video_renders', id, 'NULL org_id — column added, founder-only', now()
FROM video_renders WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'timeline_tracks', id, 'NULL org_id — column added, founder-only', now()
FROM timeline_tracks WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'timeline_clips', id, 'NULL org_id — column added, founder-only', now()
FROM timeline_clips WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'timeline_exports', id, 'NULL org_id — column added, founder-only', now()
FROM timeline_exports WHERE org_id IS NULL;

-- Backfill
UPDATE video_projects SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE video_shots SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE video_renders SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE timeline_tracks SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE timeline_clips SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE timeline_exports SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

RAISE NOTICE 'Video tables: % total rows backfilled', total_backfilled;

-- =============================================================================
-- AUDIO TABLES
-- =============================================================================

total_backfilled := 0;

-- Add org_id columns
ALTER TABLE voice_profiles ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE voice_samples ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE voice_datasets ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE voice_dna ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE voice_training_jobs ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE voice_versions ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE audio_clips ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE lip_sync_jobs ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE music_tracks_db ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE sound_effects ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE songs ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE soundtrack_cues ADD COLUMN IF NOT EXISTS org_id UUID;

-- Add indexes
CREATE INDEX IF NOT EXISTS ix_voice_profiles_org_id ON voice_profiles(org_id);
CREATE INDEX IF NOT EXISTS ix_voice_samples_org_id ON voice_samples(org_id);
CREATE INDEX IF NOT EXISTS ix_voice_datasets_org_id ON voice_datasets(org_id);
CREATE INDEX IF NOT EXISTS ix_voice_dna_org_id ON voice_dna(org_id);
CREATE INDEX IF NOT EXISTS ix_voice_training_jobs_org_id ON voice_training_jobs(org_id);
CREATE INDEX IF NOT EXISTS ix_voice_versions_org_id ON voice_versions(org_id);
CREATE INDEX IF NOT EXISTS ix_audio_clips_org_id ON audio_clips(org_id);
CREATE INDEX IF NOT EXISTS ix_lip_sync_jobs_org_id ON lip_sync_jobs(org_id);
CREATE INDEX IF NOT EXISTS ix_music_tracks_db_org_id ON music_tracks_db(org_id);
CREATE INDEX IF NOT EXISTS ix_sound_effects_org_id ON sound_effects(org_id);
CREATE INDEX IF NOT EXISTS ix_songs_org_id ON songs(org_id);
CREATE INDEX IF NOT EXISTS ix_soundtrack_cues_org_id ON soundtrack_cues(org_id);

-- Quarantine NULL rows
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'voice_profiles', id, 'NULL org_id — column added, founder-only', now()
FROM voice_profiles WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'voice_samples', id, 'NULL org_id — column added, founder-only', now()
FROM voice_samples WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'voice_datasets', id, 'NULL org_id — column added, founder-only', now()
FROM voice_datasets WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'voice_dna', id, 'NULL org_id — column added, founder-only', now()
FROM voice_dna WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'voice_training_jobs', id, 'NULL org_id — column added, founder-only', now()
FROM voice_training_jobs WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'voice_versions', id, 'NULL org_id — column added, founder-only', now()
FROM voice_versions WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'audio_clips', id, 'NULL org_id — column added, founder-only', now()
FROM audio_clips WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'lip_sync_jobs', id, 'NULL org_id — column added, founder-only', now()
FROM lip_sync_jobs WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'music_tracks_db', id, 'NULL org_id — column added, founder-only', now()
FROM music_tracks_db WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'sound_effects', id, 'NULL org_id — column added, founder-only', now()
FROM sound_effects WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'songs', id, 'NULL org_id — column added, founder-only', now()
FROM songs WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'soundtrack_cues', id, 'NULL org_id — column added, founder-only', now()
FROM soundtrack_cues WHERE org_id IS NULL;

-- Backfill
UPDATE voice_profiles SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE voice_samples SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE voice_datasets SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE voice_dna SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE voice_training_jobs SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE voice_versions SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE audio_clips SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE lip_sync_jobs SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE music_tracks_db SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE sound_effects SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE songs SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE soundtrack_cues SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

RAISE NOTICE 'Audio tables: % total rows backfilled', total_backfilled;

-- =============================================================================
-- PUBLISHING TABLES
-- =============================================================================

total_backfilled := 0;

-- Add org_id columns
ALTER TABLE publishing_accounts ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE publishing_posts ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE analytics_snapshots ADD COLUMN IF NOT EXISTS org_id UUID;

-- Add indexes
CREATE INDEX IF NOT EXISTS ix_publishing_accounts_org_id ON publishing_accounts(org_id);
CREATE INDEX IF NOT EXISTS ix_publishing_posts_org_id ON publishing_posts(org_id);
CREATE INDEX IF NOT EXISTS ix_analytics_snapshots_org_id ON analytics_snapshots(org_id);

-- Quarantine NULL rows
INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'publishing_accounts', id, 'NULL org_id — column added, founder-only', now()
FROM publishing_accounts WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'publishing_posts', id, 'NULL org_id — column added, founder-only', now()
FROM publishing_posts WHERE org_id IS NULL;

INSERT INTO _org_id_quarantine (table_name, row_id, reason, quarantined_at)
SELECT 'analytics_snapshots', id, 'NULL org_id — column added, founder-only', now()
FROM analytics_snapshots WHERE org_id IS NULL;

-- Backfill
UPDATE publishing_accounts SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE publishing_posts SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

UPDATE analytics_snapshots SET org_id = FOUNDER_ORG WHERE org_id IS NULL;
GET DIAGNOSTICS backfilled = ROW_COUNT;
total_backfilled := total_backfilled + backfilled;

RAISE NOTICE 'Publishing tables: % total rows backfilled', total_backfilled;

-- =============================================================================
-- Mark quarantine records as resolved
-- =============================================================================

UPDATE _org_id_quarantine
SET resolved_at = now(),
    resolution = 'assigned',
    assigned_org_id = FOUNDER_ORG
WHERE resolved_at IS NULL
  AND table_name IN (
    'video_projects', 'video_shots', 'video_renders',
    'timeline_tracks', 'timeline_clips', 'timeline_exports',
    'voice_profiles', 'voice_samples', 'voice_datasets',
    'voice_dna', 'voice_training_jobs', 'voice_versions',
    'audio_clips', 'lip_sync_jobs', 'music_tracks_db',
    'sound_effects', 'songs', 'soundtrack_cues',
    'publishing_accounts', 'publishing_posts', 'analytics_snapshots'
  );

RAISE NOTICE '=== Migration 043 complete: Media tables org_id added and backfilled ===';

END $$;

COMMIT;
