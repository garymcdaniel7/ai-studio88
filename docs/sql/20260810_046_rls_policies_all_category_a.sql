-- =============================================================================
-- Migration 046: Comprehensive RLS Policies — ALL Category A Tables
-- =============================================================================
--
-- PURPOSE: Apply production-grade RLS policies with proper USING vs WITH CHECK
-- separation to ALL Category A tables identified in the Tenant Authorization
-- Contract. This migration supersedes and consolidates 20260809_001 by adding
-- service_role bypass policies and covering additional tables.
--
-- SECURITY MODEL:
--   SELECT  → USING only (can the user SEE this row?)
--   INSERT  → WITH CHECK only (is the user writing to their own org?)
--   UPDATE  → USING + WITH CHECK (can they see it AND are they writing a valid org_id?)
--   DELETE  → USING only (can the user DELETE this row?)
--   service_role → USING(true) WITH CHECK(true) for backend access
--
-- This prevents:
--   1. Reading another org's data (USING blocks)
--   2. Inserting data with a foreign org_id (WITH CHECK blocks on INSERT)
--   3. Mutating org_id to steal resources (WITH CHECK on UPDATE prevents change)
--   4. Authenticated users accessing platform-only tables (no policy = deny all)
--
-- REQUIREMENTS: R6.3, R6.6, A2-029
-- PREREQUISITES:
--   - org_members table exists with (user_id, org_id, status) columns
--   - org_id column added to all Category A tables (via migrations 042/043/044)
--   - RLS enabled on tables (this migration also ensures it)
--
-- IDEMPOTENCY: Uses DROP POLICY IF EXISTS before CREATE POLICY.
-- ROLLBACK: See end of file.
-- =============================================================================

BEGIN;

-- =============================================================================
-- PHASE 1: Helper Function — user_org_ids()
-- =============================================================================
-- Reusable STABLE function to avoid repeating the subquery in every policy.
-- SECURITY DEFINER + immutable search_path prevents search_path injection.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.user_org_ids()
RETURNS SETOF UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT org_id FROM public.org_members
    WHERE user_id = auth.uid()
    AND status = 'active';
$$;

COMMENT ON FUNCTION public.user_org_ids() IS
    'Returns org_ids for the authenticated user''s active memberships. Used in RLS policies.';

GRANT EXECUTE ON FUNCTION public.user_org_ids() TO authenticated;
GRANT EXECUTE ON FUNCTION public.user_org_ids() TO service_role;


-- =============================================================================
-- PHASE 2: Remove Ineffective Policies (qual=true)
-- =============================================================================
-- These 6 policies provide NO real tenant isolation and must be replaced.
-- =============================================================================

DROP POLICY IF EXISTS "brain_collections_all" ON brain_collections;
DROP POLICY IF EXISTS "brain_conversations_all" ON brain_conversations;
DROP POLICY IF EXISTS "brain_embeddings_all" ON brain_embeddings;
DROP POLICY IF EXISTS "cost_records_all" ON cost_records;
DROP POLICY IF EXISTS "job_costs_all" ON job_costs;
DROP POLICY IF EXISTS "social_connections_all" ON social_connections;
-- Also drop from the actual table name if different
DROP POLICY IF EXISTS "social_connections_all" ON social_account_connections;


-- =============================================================================
-- PHASE 3: Apply Standard 5-Policy Pattern to ALL Category A Tables
-- =============================================================================
-- Pattern: 4 per-operation tenant policies + 1 service_role bypass
-- Uses a DO block for maintainability. Tables that don't exist are skipped.
-- =============================================================================

DO $apply_policies$ DECLARE
    tables TEXT[] := ARRAY[
        -- ─── Core Content ───
        'talent',
        'assets',
        'jobs',
        'models',
        'workflows',

        -- ─── Training ───
        'training_datasets',
        'training_images',
        'training_jobs',
        'lora_versions',
        'lora_evaluations',

        -- ─── Video ───
        'video_projects',
        'video_shots',
        'video_renders',
        'timeline_tracks',
        'timeline_clips',
        'timeline_exports',

        -- ─── Audio ───
        'voice_profiles',
        'voice_samples',
        'voice_datasets',
        'voice_dna',
        'voice_training_jobs',
        'voice_versions',
        'audio_clips',
        'lip_sync_jobs',
        'music_tracks_db',
        'sound_effects',
        'songs',
        'soundtrack_cues',

        -- ─── Publishing ───
        'publishing_accounts',
        'publishing_posts',
        'analytics_snapshots',

        -- ─── Brain ───
        'brain_sessions',
        'brain_messages',
        'brain_plans',
        'brain_memory',
        'brain_collections',
        'brain_conversations',
        'brain_embeddings',

        -- ─── AIOS ───
        'aios_sessions',
        'aios_messages',
        'aios_decisions',
        'aios_approvals',
        'aios_policies',

        -- ─── Creative ───
        'creative_dna',
        'creative_rules',
        'continuity_notes',
        'generation_feedback',
        'prompt_history',
        'style_preferences',
        'learning_events',
        'prompts',

        -- ─── Performance ───
        'performance_dna',
        'performance_memory',
        'quality_scores',
        'production_insights',

        -- ─── Cinematic ───
        'sequences',
        'cinematic_timelines',
        'cinematic_tracks',
        'cinematic_items',
        'cinematic_renders',
        'editing_operations',
        'storyboard_panels',

        -- ─── Company ───
        'brands',
        'campaigns',
        'content_calendar',
        'products',
        'series',

        -- ─── Asset Intelligence ───
        'visual_dna',
        'asset_collections',
        'collection_items',
        'asset_relationships',
        'wardrobes',
        'outfits',
        'collections',

        -- ─── Remaining Tenant Tables ───
        'talent_assets',
        'talent_relationships',
        'talent_voices',
        'workflow_runs',
        'workflow_dna',
        'social_account_connections',

        -- ─── Billing ───
        'cost_records',
        'job_costs',

        -- ─── Credentials ───
        'workspace_credentials',

        -- ─── Projects ───
        'projects',
        'project_assets',

        -- ─── Lifecycle / Provenance / Batch / Governance ───
        'lifecycle_transitions',
        'entity_holds',
        'asset_provenance',
        'asset_lineage',
        'provenance_amendments',
        'generation_batches',
        'batch_variation_jobs',
        'durable_approvals',
        'governance_policy_audit',
        'infra_audit_log',
        'creative_recipes',

        -- ─── Story Engine ───
        'universes',
        'characters',
        'episodes',
        'shots',
        'story_memory',

        -- ─── Object Intelligence ───
        'object_dna',
        'product_dna',
        'digital_twins',
        'digital_twin_versions',
        'virtual_tryon_jobs',
        'product_views_360',
        'scene_dna',
        'material_profiles',

        -- ─── Company (remaining) ───
        'studios',
        'brand_campaigns',
        'team_members',
        'approval_requests',
        'clients',
        'asset_licenses',

        -- ─── Credentials (remaining) ───
        'credential_audit_log'
    ];
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY tables
    LOOP
        -- Skip if table doesn't exist in public schema
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = tbl
        ) THEN
            RAISE NOTICE 'SKIP (not found): %', tbl;
            CONTINUE;
        END IF;

        -- Skip if table doesn't have an org_id column
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = tbl AND column_name = 'org_id'
        ) THEN
            RAISE NOTICE 'SKIP (no org_id): %', tbl;
            CONTINUE;
        END IF;

        -- ── Ensure RLS is enabled ──
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tbl);

        -- ── Drop existing policies (idempotent) ──
        -- Legacy "all" or "org_isolation" policies
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', tbl || '_all', tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', tbl || '_org_isolation', tbl);
        -- Legacy per-operation policies from 20260809_001
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', tbl || '_select_own_org', tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', tbl || '_insert_own_org', tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', tbl || '_update_own_org', tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', tbl || '_delete_own_org', tbl);
        -- Legacy training RLS (from 009)
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', tbl || '_org_isolation', tbl);
        -- New per-operation policies (in case re-running)
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', 'tenant_iso_select_' || tbl, tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', 'tenant_iso_insert_' || tbl, tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', 'tenant_iso_update_' || tbl, tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', 'tenant_iso_delete_' || tbl, tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', 'service_role_bypass_' || tbl, tbl);
        -- Training-specific naming from 009
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', tbl || '_org_isolation', tbl);

        -- ── SELECT: Can only read rows from user's org(s) ──
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT USING (org_id IN (SELECT public.user_org_ids()))',
            'tenant_iso_select_' || tbl, tbl
        );

        -- ── INSERT: WITH CHECK prevents inserting with a foreign org_id ──
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR INSERT WITH CHECK (org_id IN (SELECT public.user_org_ids()))',
            'tenant_iso_insert_' || tbl, tbl
        );

        -- ── UPDATE: USING ensures visibility; WITH CHECK prevents org_id mutation ──
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR UPDATE USING (org_id IN (SELECT public.user_org_ids())) WITH CHECK (org_id IN (SELECT public.user_org_ids()))',
            'tenant_iso_update_' || tbl, tbl
        );

        -- ── DELETE: USING ensures can only delete own org's rows ──
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR DELETE USING (org_id IN (SELECT public.user_org_ids()))',
            'tenant_iso_delete_' || tbl, tbl
        );

        -- ── SERVICE_ROLE BYPASS: Backend service-role key bypasses tenant filtering ──
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR ALL TO service_role USING (true) WITH CHECK (true)',
            'service_role_bypass_' || tbl, tbl
        );

        RAISE NOTICE 'APPLIED: 5 RLS policies (4 tenant + 1 service_role bypass) on %', tbl;
    END LOOP;
END $apply_policies$;


-- =============================================================================
-- PHASE 4: Special Cases — Models & Workflows (System Resources Readable)
-- =============================================================================
-- System-org resources (org_id = '...001') are readable by all authenticated
-- users. User-org resources follow standard tenant isolation.
-- =============================================================================

-- ── models: System models readable by all, own-org models writable ──
DO $models_special$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'models'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'models' AND column_name = 'org_id'
    ) THEN
        -- Drop standard policies just applied (we need special SELECT)
        DROP POLICY IF EXISTS "tenant_iso_select_models" ON public.models;

        -- SELECT: own org OR system org (shared models)
        CREATE POLICY "tenant_iso_select_models" ON public.models
            FOR SELECT
            USING (
                org_id IN (SELECT public.user_org_ids())
                OR org_id = '00000000-0000-0000-0000-000000000001'::uuid
            );

        RAISE NOTICE 'APPLIED: Special SELECT policy on models (includes system org)';
    END IF;
END $models_special$;

-- ── workflows: System workflows readable by all, own-org writable ──
DO $workflows_special$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'workflows'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'workflows' AND column_name = 'org_id'
    ) THEN
        -- Drop standard policy just applied (we need special SELECT)
        DROP POLICY IF EXISTS "tenant_iso_select_workflows" ON public.workflows;

        -- SELECT: own org OR system org (shared workflows)
        CREATE POLICY "tenant_iso_select_workflows" ON public.workflows
            FOR SELECT
            USING (
                org_id IN (SELECT public.user_org_ids())
                OR org_id = '00000000-0000-0000-0000-000000000001'::uuid
            );

        RAISE NOTICE 'APPLIED: Special SELECT policy on workflows (includes system org)';
    END IF;
END $workflows_special$;


-- =============================================================================
-- PHASE 5: Special Cases — Organizations & Org Members
-- =============================================================================
-- These use `id` (not org_id) for the ownership check.
-- =============================================================================

-- ── organizations: Users can only see their own org ──
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "organizations_select_own" ON public.organizations;
DROP POLICY IF EXISTS "tenant_iso_select_organizations" ON public.organizations;
DROP POLICY IF EXISTS "service_role_bypass_organizations" ON public.organizations;

CREATE POLICY "tenant_iso_select_organizations" ON public.organizations
    FOR SELECT
    USING (id IN (SELECT public.user_org_ids()));

-- No INSERT/UPDATE/DELETE for authenticated — managed by service_role only
CREATE POLICY "service_role_bypass_organizations" ON public.organizations
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ── org_members: Users can see memberships within their own org(s) ──
ALTER TABLE public.org_members ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "org_members_select_own_org" ON public.org_members;
DROP POLICY IF EXISTS "tenant_iso_select_org_members" ON public.org_members;
DROP POLICY IF EXISTS "service_role_bypass_org_members" ON public.org_members;

CREATE POLICY "tenant_iso_select_org_members" ON public.org_members
    FOR SELECT
    USING (org_id IN (SELECT public.user_org_ids()));

-- No INSERT/UPDATE/DELETE for authenticated — managed by service_role (provisioning)
CREATE POLICY "service_role_bypass_org_members" ON public.org_members
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);


-- =============================================================================
-- PHASE 6: Special Case — Workers (Platform-Scoped, Service-Role Only)
-- =============================================================================
-- Workers is Category C (platform-operational). RLS enabled with NO tenant
-- policies = deny all for authenticated role. Only service_role can access.
-- =============================================================================

ALTER TABLE public.workers ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "workers_select_own_org" ON public.workers;
DROP POLICY IF EXISTS "workers_insert_own_org" ON public.workers;
DROP POLICY IF EXISTS "workers_update_own_org" ON public.workers;
DROP POLICY IF EXISTS "workers_delete_own_org" ON public.workers;
DROP POLICY IF EXISTS "service_role_bypass_workers" ON public.workers;

-- Only service_role can access workers (platform infrastructure)
CREATE POLICY "service_role_bypass_workers" ON public.workers
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);


-- =============================================================================
-- PHASE 7: Verification Query
-- =============================================================================
-- Run after applying to confirm all policies are in place:
--
-- SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
-- FROM pg_policies
-- WHERE schemaname = 'public'
-- ORDER BY tablename, cmd;
--
-- Expected: Each Category A table should have exactly 5 policies:
--   tenant_iso_select_{table}   (cmd=SELECT)
--   tenant_iso_insert_{table}   (cmd=INSERT)
--   tenant_iso_update_{table}   (cmd=UPDATE)
--   tenant_iso_delete_{table}   (cmd=DELETE)
--   service_role_bypass_{table} (cmd=ALL, roles={service_role})
-- =============================================================================

COMMIT;


-- =============================================================================
-- ROLLBACK INSTRUCTIONS
-- =============================================================================
-- To reverse this migration, execute:
--
-- BEGIN;
--
-- DO $rollback$ DECLARE
--     tables TEXT[] := ARRAY[
--         'talent', 'assets', 'jobs', 'models', 'workflows',
--         'training_datasets', 'training_images', 'training_jobs',
--         'lora_versions', 'lora_evaluations',
--         'video_projects', 'video_shots', 'video_renders',
--         'timeline_tracks', 'timeline_clips', 'timeline_exports',
--         'voice_profiles', 'voice_samples', 'voice_datasets',
--         'voice_dna', 'voice_training_jobs', 'voice_versions',
--         'audio_clips', 'lip_sync_jobs', 'music_tracks_db',
--         'sound_effects', 'songs', 'soundtrack_cues',
--         'publishing_accounts', 'publishing_posts', 'analytics_snapshots',
--         'brain_sessions', 'brain_messages', 'brain_plans',
--         'brain_memory', 'brain_collections', 'brain_conversations',
--         'brain_embeddings',
--         'aios_sessions', 'aios_messages', 'aios_decisions',
--         'aios_approvals', 'aios_policies',
--         'creative_dna', 'creative_rules', 'continuity_notes',
--         'generation_feedback', 'prompt_history', 'style_preferences',
--         'learning_events', 'prompts',
--         'performance_dna', 'performance_memory', 'quality_scores',
--         'production_insights',
--         'sequences', 'cinematic_timelines', 'cinematic_tracks',
--         'cinematic_items', 'cinematic_renders', 'editing_operations',
--         'storyboard_panels',
--         'brands', 'campaigns', 'content_calendar', 'products', 'series',
--         'visual_dna', 'asset_collections', 'collection_items',
--         'asset_relationships', 'wardrobes', 'outfits', 'collections',
--         'talent_assets', 'talent_relationships', 'talent_voices',
--         'workflow_runs', 'workflow_dna', 'social_account_connections',
--         'cost_records', 'job_costs',
--         'workspace_credentials',
--         'projects', 'project_assets',
--         'lifecycle_transitions', 'entity_holds',
--         'asset_provenance', 'asset_lineage', 'provenance_amendments',
--         'generation_batches', 'batch_variation_jobs',
--         'durable_approvals', 'governance_policy_audit', 'infra_audit_log',
--         'creative_recipes',
--         'universes', 'characters', 'episodes', 'shots', 'story_memory',
--         'object_dna', 'product_dna', 'digital_twins', 'digital_twin_versions',
--         'virtual_tryon_jobs', 'product_views_360', 'scene_dna', 'material_profiles',
--         'studios', 'brand_campaigns', 'team_members',
--         'approval_requests', 'clients', 'asset_licenses',
--         'credential_audit_log'
--     ];
--     tbl TEXT;
-- BEGIN
--     FOREACH tbl IN ARRAY tables LOOP
--         EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', 'tenant_iso_select_' || tbl, tbl);
--         EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', 'tenant_iso_insert_' || tbl, tbl);
--         EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', 'tenant_iso_update_' || tbl, tbl);
--         EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', 'tenant_iso_delete_' || tbl, tbl);
--         EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', 'service_role_bypass_' || tbl, tbl);
--     END LOOP;
-- END $rollback$;
--
-- DROP POLICY IF EXISTS "tenant_iso_select_organizations" ON public.organizations;
-- DROP POLICY IF EXISTS "service_role_bypass_organizations" ON public.organizations;
-- DROP POLICY IF EXISTS "tenant_iso_select_org_members" ON public.org_members;
-- DROP POLICY IF EXISTS "service_role_bypass_org_members" ON public.org_members;
-- DROP POLICY IF EXISTS "service_role_bypass_workers" ON public.workers;
--
-- DROP FUNCTION IF EXISTS public.user_org_ids();
--
-- COMMIT;
