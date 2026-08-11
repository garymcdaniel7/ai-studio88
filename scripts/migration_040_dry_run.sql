-- =============================================================================
-- DRY-RUN REPORT: Migration 040 Ownership Backfill
--
-- Run this BEFORE executing the actual migration to see what will be affected.
-- This is read-only — no data is modified.
-- =============================================================================

-- 1. Count NULL org_id rows per table
SELECT 'talent' AS table_name, count(*) AS null_org_id_rows FROM talent WHERE org_id IS NULL
UNION ALL SELECT 'assets', count(*) FROM assets WHERE org_id IS NULL
UNION ALL SELECT 'jobs', count(*) FROM jobs WHERE org_id IS NULL
UNION ALL SELECT 'models', count(*) FROM models WHERE org_id IS NULL
UNION ALL SELECT 'workflows', count(*) FROM workflows WHERE org_id IS NULL
UNION ALL SELECT 'scenes', count(*) FROM scenes WHERE org_id IS NULL
UNION ALL SELECT 'training_datasets', count(*) FROM training_datasets WHERE org_id IS NULL
UNION ALL SELECT 'training_jobs', count(*) FROM training_jobs WHERE org_id IS NULL
UNION ALL SELECT 'video_projects', count(*) FROM video_projects WHERE org_id IS NULL
UNION ALL SELECT 'audio_clips', count(*) FROM audio_clips WHERE org_id IS NULL
UNION ALL SELECT 'voice_profiles', count(*) FROM voice_profiles WHERE org_id IS NULL
UNION ALL SELECT 'publishing_posts', count(*) FROM publishing_posts WHERE org_id IS NULL
UNION ALL SELECT 'brain_sessions', count(*) FROM brain_sessions WHERE org_id IS NULL
UNION ALL SELECT 'brain_memory', count(*) FROM brain_memory WHERE org_id IS NULL
UNION ALL SELECT 'creative_dna', count(*) FROM creative_dna WHERE org_id IS NULL
UNION ALL SELECT 'performance_dna', count(*) FROM performance_dna WHERE org_id IS NULL
ORDER BY null_org_id_rows DESC;

-- 2. Count zero-UUID placeholder rows
SELECT 'aios_approvals' AS table_name, count(*) AS zero_uuid_rows
FROM aios_approvals WHERE org_id = '00000000-0000-0000-0000-000000000000'
UNION ALL SELECT 'aios_policies', count(*)
FROM aios_policies WHERE org_id = '00000000-0000-0000-0000-000000000000'
UNION ALL SELECT 'aios_sessions', count(*)
FROM aios_sessions WHERE org_id = '00000000-0000-0000-0000-000000000000'
ORDER BY zero_uuid_rows DESC;

-- 3. Count system-org DEFAULT rows (should become founder's)
SELECT 'cost_records' AS table_name, count(*) AS system_org_rows
FROM cost_records WHERE org_id = '00000000-0000-0000-0000-000000000001'
UNION ALL SELECT 'job_costs', count(*)
FROM job_costs WHERE org_id = '00000000-0000-0000-0000-000000000001'
UNION ALL SELECT 'brain_collections', count(*)
FROM brain_collections WHERE org_id = '00000000-0000-0000-0000-000000000001'
ORDER BY system_org_rows DESC;

-- 4. Story engine tables without org_id column
SELECT 'universes' AS table_name, count(*) AS total_rows FROM universes
UNION ALL SELECT 'characters', count(*) FROM characters
UNION ALL SELECT 'episodes', count(*) FROM episodes
UNION ALL SELECT 'shots', count(*) FROM shots
UNION ALL SELECT 'story_memory', count(*) FROM story_memory;

-- 5. Summary: total rows requiring migration
SELECT
    (SELECT count(*) FROM talent WHERE org_id IS NULL) +
    (SELECT count(*) FROM assets WHERE org_id IS NULL) +
    (SELECT count(*) FROM jobs WHERE org_id IS NULL) +
    (SELECT count(*) FROM models WHERE org_id IS NULL) +
    (SELECT count(*) FROM cost_records WHERE org_id = '00000000-0000-0000-0000-000000000001') +
    (SELECT count(*) FROM aios_approvals WHERE org_id = '00000000-0000-0000-0000-000000000000')
AS estimated_total_rows_to_migrate;
