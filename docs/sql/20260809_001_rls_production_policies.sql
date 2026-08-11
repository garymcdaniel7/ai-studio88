-- =============================================================================
-- Migration: Production RLS Policies with USING + WITH CHECK Separation
--
-- PURPOSE: Apply production-grade RLS policies to ALL Category A tables with
-- proper USING (read) vs WITH CHECK (write) separation to prevent org_id
-- forgery on INSERT/UPDATE operations.
--
-- PATTERN:
--   SELECT/DELETE → USING clause only (can this user SEE/DELETE this row?)
--   INSERT → WITH CHECK clause only (is the user writing to their own org?)
--   UPDATE → USING (can they see it?) + WITH CHECK (are they writing valid org_id?)
--
-- This prevents an attacker from:
--   1. Reading another org's data (USING blocks)
--   2. Inserting data with a foreign org_id (WITH CHECK blocks)
--   3. Updating org_id to steal resources (WITH CHECK prevents changing org_id)
--
-- REQUIREMENTS: R6.3, R6.6, A2-029
-- PREREQUISITES: 20260804_003 and 20260806_003 applied (RLS enabled on tables)
--
-- SAFETY: Uses DROP POLICY IF EXISTS + CREATE POLICY (idempotent).
-- ROLLBACK: See rollback section at bottom of file.
-- =============================================================================

BEGIN;

-- =============================================================================
-- Helper: Create a reusable function for org membership check
-- This avoids duplicating the subquery in every policy.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.user_org_ids()
RETURNS SETOF UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT org_id FROM org_members
    WHERE user_id = auth.uid()
    AND status = 'active';
$$;

COMMENT ON FUNCTION public.user_org_ids() IS
    'Returns set of org_ids the authenticated user belongs to. Used in RLS policies.';

-- Grant execute to authenticated role (needed for RLS)
GRANT EXECUTE ON FUNCTION public.user_org_ids() TO authenticated;


-- =============================================================================
-- MACRO: Apply standard tenant isolation policies to a table
--
-- For each table, we create 4 operation-specific policies:
--   1. SELECT → USING (org_id IN user_org_ids())
--   2. INSERT → WITH CHECK (org_id IN user_org_ids())
--   3. UPDATE → USING + WITH CHECK (prevents org_id mutation)
--   4. DELETE → USING (org_id IN user_org_ids())
-- =============================================================================

-- Helper function to apply the standard 4-policy pattern
-- (PostgreSQL doesn't support macros, so we use DO blocks per table)

DO $apply_policies$ DECLARE
    tables TEXT[] := ARRAY[
        -- Core content
        'talent', 'assets', 'jobs', 'scenes',
        -- Training
        'training_datasets', 'training_images', 'training_jobs',
        'lora_versions', 'lora_evaluations',
        -- Video
        'video_projects', 'video_shots', 'video_renders',
        'timeline_tracks', 'timeline_clips', 'timeline_exports',
        -- Audio
        'voice_profiles', 'voice_samples', 'audio_clips',
        'lip_sync_jobs', 'music_tracks_db', 'sound_effects',
        -- Publishing
        'publishing_accounts', 'publishing_posts', 'analytics_snapshots',
        -- Brain
        'brain_sessions', 'brain_messages', 'brain_plans',
        'brain_memory', 'brain_collections', 'brain_conversations',
        'brain_embeddings',
        -- AIOS
        'aios_sessions', 'aios_messages', 'aios_decisions',
        'aios_approvals', 'aios_policies',
        -- Story Engine
        'universes', 'characters', 'episodes', 'shots', 'story_memory',
        -- Creative / Performance
        'creative_dna', 'creative_rules', 'continuity_notes',
        'generation_feedback', 'prompt_history', 'style_preferences',
        'performance_dna', 'performance_memory', 'quality_scores',
        'voice_dna', 'voice_datasets', 'voice_training_jobs', 'voice_versions',
        -- Object Intelligence
        'object_dna', 'product_dna', 'digital_twins', 'digital_twin_versions',
        'virtual_tryon_jobs', 'product_views_360', 'scene_dna', 'material_profiles',
        -- Asset Intelligence
        'visual_dna', 'asset_collections', 'collection_items',
        'asset_relationships', 'wardrobes', 'outfits',
        -- Cinematic
        'sequences', 'cinematic_timelines', 'cinematic_tracks',
        'cinematic_items', 'storyboard_panels', 'cinematic_renders',
        'editing_operations',
        -- Company
        'brands', 'studios', 'brand_campaigns', 'team_members',
        'approval_requests', 'clients', 'asset_licenses',
        -- Credentials
        'workspace_credentials', 'credential_audit_log',
        'social_account_connections',
        -- Billing
        'cost_records', 'job_costs',
        -- Lifecycle
        'lifecycle_transitions', 'entity_holds',
        -- Provenance
        'asset_provenance', 'asset_lineage', 'provenance_amendments',
        -- Batch
        'generation_batches', 'batch_variation_jobs',
        -- Governance
        'durable_approvals', 'governance_policy_audit', 'infra_audit_log',
        -- Recipes
        'creative_recipes',
        -- Projects
        'projects', 'project_assets'
    ];
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY tables
    LOOP
        -- Skip if table doesn't exist
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = tbl
        ) THEN
            RAISE NOTICE 'SKIP: Table % does not exist', tbl;
            CONTINUE;
        END IF;

        -- Skip if table doesn't have org_id column
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = tbl AND column_name = 'org_id'
        ) THEN
            RAISE NOTICE 'SKIP: Table % does not have org_id column', tbl;
            CONTINUE;
        END IF;

        -- Ensure RLS is enabled
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);

        -- Drop any existing permissive "all" policies that provide no real isolation
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_org_isolation', tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_all', tbl);

        -- Drop old per-operation policies if they exist (we're replacing them)
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_select_own_org', tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_insert_own_org', tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_update_own_org', tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_delete_own_org', tbl);

        -- ── SELECT: Can only read rows belonging to user's org(s) ──
        EXECUTE format(
            'CREATE POLICY %I ON %I FOR SELECT USING (org_id IN (SELECT user_org_ids()))',
            tbl || '_select_own_org', tbl
        );

        -- ── INSERT: Can only insert rows with org_id matching user's org(s) ──
        -- This WITH CHECK prevents inserting with a foreign org_id
        EXECUTE format(
            'CREATE POLICY %I ON %I FOR INSERT WITH CHECK (org_id IN (SELECT user_org_ids()))',
            tbl || '_insert_own_org', tbl
        );

        -- ── UPDATE: USING ensures user can only see their rows,
        -- WITH CHECK prevents mutating org_id to a foreign value ──
        EXECUTE format(
            'CREATE POLICY %I ON %I FOR UPDATE USING (org_id IN (SELECT user_org_ids())) WITH CHECK (org_id IN (SELECT user_org_ids()))',
            tbl || '_update_own_org', tbl
        );

        -- ── DELETE: Can only delete rows belonging to user's org(s) ──
        EXECUTE format(
            'CREATE POLICY %I ON %I FOR DELETE USING (org_id IN (SELECT user_org_ids()))',
            tbl || '_delete_own_org', tbl
        );

        RAISE NOTICE 'APPLIED: 4 RLS policies on %', tbl;
    END LOOP;
END $apply_policies$;


-- =============================================================================
-- SPECIAL CASES: Tables with different access patterns
-- =============================================================================

-- ── models: System models (system org) readable by all, writable by own org ──
DROP POLICY IF EXISTS models_org_isolation ON models;
DROP POLICY IF EXISTS models_select_own_org ON models;
DROP POLICY IF EXISTS models_insert_own_org ON models;
DROP POLICY IF EXISTS models_update_own_org ON models;
DROP POLICY IF EXISTS models_delete_own_org ON models;

CREATE POLICY models_select_own_org ON models
    FOR SELECT USING (
        org_id = '00000000-0000-0000-0000-000000000001'::uuid  -- system models
        OR org_id IN (SELECT user_org_ids())
    );

CREATE POLICY models_insert_own_org ON models
    FOR INSERT WITH CHECK (org_id IN (SELECT user_org_ids()));

CREATE POLICY models_update_own_org ON models
    FOR UPDATE
    USING (org_id IN (SELECT user_org_ids()))
    WITH CHECK (org_id IN (SELECT user_org_ids()));

CREATE POLICY models_delete_own_org ON models
    FOR DELETE USING (org_id IN (SELECT user_org_ids()));


-- ── workflows: System workflows readable by all, writable by own org ──
DROP POLICY IF EXISTS workflows_org_isolation ON workflows;
DROP POLICY IF EXISTS workflows_select_own_org ON workflows;
DROP POLICY IF EXISTS workflows_insert_own_org ON workflows;
DROP POLICY IF EXISTS workflows_update_own_org ON workflows;
DROP POLICY IF EXISTS workflows_delete_own_org ON workflows;

CREATE POLICY workflows_select_own_org ON workflows
    FOR SELECT USING (
        org_id = '00000000-0000-0000-0000-000000000001'::uuid
        OR org_id IN (SELECT user_org_ids())
    );

CREATE POLICY workflows_insert_own_org ON workflows
    FOR INSERT WITH CHECK (org_id IN (SELECT user_org_ids()));

CREATE POLICY workflows_update_own_org ON workflows
    FOR UPDATE
    USING (org_id IN (SELECT user_org_ids()))
    WITH CHECK (org_id IN (SELECT user_org_ids()));

CREATE POLICY workflows_delete_own_org ON workflows
    FOR DELETE USING (org_id IN (SELECT user_org_ids()));


-- ── organizations: Users can only see their own org (via id, not org_id) ──
DROP POLICY IF EXISTS organizations_select_own ON organizations;

CREATE POLICY organizations_select_own ON organizations
    FOR SELECT USING (id IN (SELECT user_org_ids()));

-- No INSERT/UPDATE/DELETE — only service_role manages organizations.


-- ── org_members: Users can see memberships for their org(s) ──
ALTER TABLE org_members ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS org_members_select_own_org ON org_members;
CREATE POLICY org_members_select_own_org ON org_members
    FOR SELECT USING (org_id IN (SELECT user_org_ids()));

-- No INSERT/UPDATE/DELETE — managed by service_role (provisioning service).


-- ── workers: Infrastructure-scoped — service_role only ──
-- RLS enabled with NO policies = blocks all authenticated access
ALTER TABLE workers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workers_select_own_org ON workers;
DROP POLICY IF EXISTS workers_insert_own_org ON workers;
DROP POLICY IF EXISTS workers_update_own_org ON workers;
DROP POLICY IF EXISTS workers_delete_own_org ON workers;
-- Intentionally no policies — service_role only.


-- =============================================================================
-- Verification query (run after applying)
-- =============================================================================
-- SELECT tablename, policyname, permissive, roles, cmd, qual, with_check
-- FROM pg_policies
-- WHERE schemaname = 'public'
-- ORDER BY tablename, cmd;


COMMIT;


-- =============================================================================
-- ROLLBACK
-- =============================================================================
-- BEGIN;
-- DROP FUNCTION IF EXISTS public.user_org_ids();
--
-- -- For each table, drop the 4 policies:
-- DO $rollback$ DECLARE
--     tables TEXT[] := ARRAY[...same list...];
--     tbl TEXT;
-- BEGIN
--     FOREACH tbl IN ARRAY tables LOOP
--         EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_select_own_org', tbl);
--         EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_insert_own_org', tbl);
--         EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_update_own_org', tbl);
--         EXECUTE format('DROP POLICY IF EXISTS %I ON %I', tbl || '_delete_own_org', tbl);
--     END LOOP;
-- END $rollback$;
-- COMMIT;
