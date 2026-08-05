-- =============================================================================
-- AI Studio: Storyboard & Production Tenant Isolation (Story 020)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================
--
-- TABLES COVERED:
-- 1. storyboards — DIRECT org_id (already has org_id NOT NULL from 028)
-- 2. storyboard_panels — org_id added in 030 (cinematic studio)
-- 3. universes — DIRECT org_id (add here, story engine root)
-- 4. episodes — INHERITED via universe_id → universes.org_id (denormalize)
-- 5. scenes — INHERITED via episode_id → episodes (denormalize)
-- 6. shots — INHERITED via scene_id → scenes (denormalize)
-- 7. characters — INHERITED via universe_id → universes (denormalize)
-- 8. story_memory — INHERITED via universe_id → universes (denormalize)
--
-- NOTE: storyboards already has RLS from 028_projects.sql ("project_org_isolation").
-- We ADD proper operation-specific policies alongside the existing permissive one.
-- The story engine tables (universes, episodes, scenes, shots, characters,
-- story_memory) get org_id denormalized for efficient RLS.
--
-- PERSISTENCE MODEL:
-- Storyboards are the authoritative server-side record of production state.
-- Browser state is cache/optimistic only — server truth wins on conflict.
-- =============================================================================

BEGIN;

-- =============================================================================
-- PHASE 1: Add org_id to story engine tables (denormalized for RLS)
-- =============================================================================

ALTER TABLE public.universes ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE public.episodes ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE public.scenes ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE public.shots ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE public.characters ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE public.story_memory ADD COLUMN IF NOT EXISTS org_id UUID;

-- Add user_id attribution to storyboards (who created/last edited)
ALTER TABLE public.storyboards ADD COLUMN IF NOT EXISTS user_id UUID;

-- =============================================================================
-- PHASE 2: Indexes for tenant-scoped queries
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_storyboards_org_id ON public.storyboards(org_id);
CREATE INDEX IF NOT EXISTS ix_storyboards_org_status ON public.storyboards(org_id, status);
CREATE INDEX IF NOT EXISTS ix_storyboard_panels_org_id ON public.storyboard_panels(org_id);
CREATE INDEX IF NOT EXISTS ix_universes_org_id ON public.universes(org_id);
CREATE INDEX IF NOT EXISTS ix_episodes_org_id ON public.episodes(org_id);
CREATE INDEX IF NOT EXISTS ix_scenes_org_id ON public.scenes(org_id);
CREATE INDEX IF NOT EXISTS ix_shots_org_id ON public.shots(org_id);
CREATE INDEX IF NOT EXISTS ix_characters_org_id ON public.characters(org_id);
CREATE INDEX IF NOT EXISTS ix_story_memory_org_id ON public.story_memory(org_id);

-- =============================================================================
-- PHASE 3: Drop existing policies (idempotent)
-- =============================================================================

-- storyboards already has a policy from 028, drop for replacement
DROP POLICY IF EXISTS "project_org_isolation" ON public.storyboards;
DROP POLICY IF EXISTS storyboards_select_own ON public.storyboards;
DROP POLICY IF EXISTS storyboards_insert_own ON public.storyboards;
DROP POLICY IF EXISTS storyboards_update_own ON public.storyboards;
DROP POLICY IF EXISTS storyboards_delete_own ON public.storyboards;

DROP POLICY IF EXISTS storyboard_panels_select_own ON public.storyboard_panels;
DROP POLICY IF EXISTS storyboard_panels_insert_own ON public.storyboard_panels;
DROP POLICY IF EXISTS storyboard_panels_update_own ON public.storyboard_panels;
DROP POLICY IF EXISTS storyboard_panels_delete_own ON public.storyboard_panels;

DROP POLICY IF EXISTS universes_select_own ON public.universes;
DROP POLICY IF EXISTS universes_insert_own ON public.universes;
DROP POLICY IF EXISTS universes_update_own ON public.universes;
DROP POLICY IF EXISTS universes_delete_own ON public.universes;

DROP POLICY IF EXISTS episodes_select_own ON public.episodes;
DROP POLICY IF EXISTS episodes_insert_own ON public.episodes;
DROP POLICY IF EXISTS episodes_update_own ON public.episodes;

DROP POLICY IF EXISTS scenes_select_own ON public.scenes;
DROP POLICY IF EXISTS scenes_insert_own ON public.scenes;
DROP POLICY IF EXISTS scenes_update_own ON public.scenes;

DROP POLICY IF EXISTS shots_select_own ON public.shots;
DROP POLICY IF EXISTS shots_insert_own ON public.shots;
DROP POLICY IF EXISTS shots_update_own ON public.shots;

DROP POLICY IF EXISTS characters_select_own ON public.characters;
DROP POLICY IF EXISTS characters_insert_own ON public.characters;
DROP POLICY IF EXISTS characters_update_own ON public.characters;

DROP POLICY IF EXISTS story_memory_select_own ON public.story_memory;
DROP POLICY IF EXISTS story_memory_insert_own ON public.story_memory;

-- =============================================================================
-- PHASE 4: Enable RLS on story engine tables
-- =============================================================================
-- storyboards already has RLS enabled from 028, but FORCE it
ALTER TABLE public.storyboards FORCE ROW LEVEL SECURITY;

ALTER TABLE public.storyboard_panels ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.storyboard_panels FORCE ROW LEVEL SECURITY;

ALTER TABLE public.universes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.universes FORCE ROW LEVEL SECURITY;

ALTER TABLE public.episodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.episodes FORCE ROW LEVEL SECURITY;

ALTER TABLE public.scenes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scenes FORCE ROW LEVEL SECURITY;

ALTER TABLE public.shots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shots FORCE ROW LEVEL SECURITY;

ALTER TABLE public.characters ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.characters FORCE ROW LEVEL SECURITY;

ALTER TABLE public.story_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.story_memory FORCE ROW LEVEL SECURITY;

-- =============================================================================
-- PHASE 5: RLS Policies — storyboards (replace permissive policy from 028)
-- =============================================================================

CREATE POLICY storyboards_select_own ON public.storyboards
    FOR SELECT TO authenticated
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY storyboards_insert_own ON public.storyboards
    FOR INSERT TO authenticated
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY storyboards_update_own ON public.storyboards
    FOR UPDATE TO authenticated
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY storyboards_delete_own ON public.storyboards
    FOR DELETE TO authenticated
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

-- =============================================================================
-- PHASE 6: RLS Policies — storyboard_panels
-- =============================================================================

CREATE POLICY storyboard_panels_select_own ON public.storyboard_panels
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY storyboard_panels_insert_own ON public.storyboard_panels
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY storyboard_panels_update_own ON public.storyboard_panels
    FOR UPDATE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY storyboard_panels_delete_own ON public.storyboard_panels
    FOR DELETE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

-- =============================================================================
-- PHASE 7: RLS Policies — universes (story engine root)
-- =============================================================================

CREATE POLICY universes_select_own ON public.universes
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY universes_insert_own ON public.universes
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY universes_update_own ON public.universes
    FOR UPDATE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY universes_delete_own ON public.universes
    FOR DELETE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

-- =============================================================================
-- PHASE 8: RLS Policies — episodes, scenes, shots, characters, story_memory
-- =============================================================================

-- Episodes
CREATE POLICY episodes_select_own ON public.episodes
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY episodes_insert_own ON public.episodes
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY episodes_update_own ON public.episodes
    FOR UPDATE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

-- Scenes
CREATE POLICY scenes_select_own ON public.scenes
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY scenes_insert_own ON public.scenes
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY scenes_update_own ON public.scenes
    FOR UPDATE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

-- Shots
CREATE POLICY shots_select_own ON public.shots
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY shots_insert_own ON public.shots
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY shots_update_own ON public.shots
    FOR UPDATE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

-- Characters
CREATE POLICY characters_select_own ON public.characters
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY characters_insert_own ON public.characters
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY characters_update_own ON public.characters
    FOR UPDATE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

-- Story Memory
CREATE POLICY story_memory_select_own ON public.story_memory
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY story_memory_insert_own ON public.story_memory
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

COMMIT;

-- =============================================================================
-- ROLLBACK:
-- =============================================================================
-- BEGIN;
-- DROP POLICY IF EXISTS storyboards_select_own ON public.storyboards;
-- DROP POLICY IF EXISTS storyboards_insert_own ON public.storyboards;
-- DROP POLICY IF EXISTS storyboards_update_own ON public.storyboards;
-- DROP POLICY IF EXISTS storyboards_delete_own ON public.storyboards;
-- ... (drop all policies, then DISABLE RLS on each table)
-- COMMIT;
