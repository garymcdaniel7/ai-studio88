-- =============================================================================
-- AI Studio: Talent & Creative Intelligence RLS (Story 016)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================
--
-- TABLES COVERED:
-- 1. talent — direct org_id (already added in 030)
-- 2. creative_dna — inherited via talent_id → talent.org_id
-- 3. generation_feedback — inherited via talent_id → talent.org_id
-- 4. continuity_notes — direct org_id (already in DIRECT_OWNED_TABLES)
-- 5. creative_rules — direct org_id (already in DIRECT_OWNED_TABLES)
-- 6. style_preferences — inherited via talent_id → talent.org_id
-- 7. prompt_history — inherited via talent_id → talent.org_id
--
-- OWNERSHIP MODEL:
-- - talent: DIRECT (org_id column)
-- - creative_dna, generation_feedback, style_preferences, prompt_history:
--   INHERITED via talent_id FK → talent.org_id
--   Also denormalized: org_id added directly for efficient queries
-- - continuity_notes, creative_rules: DIRECT (org_id column)
--
-- For inherited tables, we denormalize org_id onto each row so RLS policies
-- can filter without expensive JOINs. The application layer ensures org_id
-- is always set correctly on insert.
-- =============================================================================

BEGIN;

-- =============================================================================
-- PHASE 1: Add org_id to inherited tables (denormalized for RLS efficiency)
-- =============================================================================

ALTER TABLE public.creative_dna ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE public.generation_feedback ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE public.style_preferences ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE public.prompt_history ADD COLUMN IF NOT EXISTS org_id UUID;
-- continuity_notes and creative_rules already have org_id from 030

-- =============================================================================
-- PHASE 2: Indexes for tenant-scoped queries
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_talent_org_id ON public.talent(org_id);
CREATE INDEX IF NOT EXISTS ix_creative_dna_org_id ON public.creative_dna(org_id);
CREATE INDEX IF NOT EXISTS ix_creative_dna_talent_id ON public.creative_dna(talent_id);
CREATE INDEX IF NOT EXISTS ix_generation_feedback_org_id ON public.generation_feedback(org_id);
CREATE INDEX IF NOT EXISTS ix_generation_feedback_talent_id ON public.generation_feedback(talent_id);
CREATE INDEX IF NOT EXISTS ix_continuity_notes_org_id ON public.continuity_notes(org_id);
CREATE INDEX IF NOT EXISTS ix_creative_rules_org_id ON public.creative_rules(org_id);
CREATE INDEX IF NOT EXISTS ix_style_preferences_org_id ON public.style_preferences(org_id);
CREATE INDEX IF NOT EXISTS ix_style_preferences_talent_id ON public.style_preferences(talent_id);
CREATE INDEX IF NOT EXISTS ix_prompt_history_org_id ON public.prompt_history(org_id);
CREATE INDEX IF NOT EXISTS ix_prompt_history_talent_id ON public.prompt_history(talent_id);

-- =============================================================================
-- PHASE 3: Drop existing policies (idempotent re-run)
-- =============================================================================

DROP POLICY IF EXISTS talent_select_own ON public.talent;
DROP POLICY IF EXISTS talent_insert_own ON public.talent;
DROP POLICY IF EXISTS talent_update_own ON public.talent;
DROP POLICY IF EXISTS talent_delete_own ON public.talent;

DROP POLICY IF EXISTS creative_dna_select_own ON public.creative_dna;
DROP POLICY IF EXISTS creative_dna_insert_own ON public.creative_dna;
DROP POLICY IF EXISTS creative_dna_update_own ON public.creative_dna;

DROP POLICY IF EXISTS feedback_select_own ON public.generation_feedback;
DROP POLICY IF EXISTS feedback_insert_own ON public.generation_feedback;

DROP POLICY IF EXISTS continuity_select_own ON public.continuity_notes;
DROP POLICY IF EXISTS continuity_insert_own ON public.continuity_notes;
DROP POLICY IF EXISTS continuity_update_own ON public.continuity_notes;
DROP POLICY IF EXISTS continuity_delete_own ON public.continuity_notes;

DROP POLICY IF EXISTS rules_select_own ON public.creative_rules;
DROP POLICY IF EXISTS rules_insert_own ON public.creative_rules;
DROP POLICY IF EXISTS rules_delete_own ON public.creative_rules;

DROP POLICY IF EXISTS prefs_select_own ON public.style_preferences;
DROP POLICY IF EXISTS prefs_upsert_own ON public.style_preferences;

DROP POLICY IF EXISTS prompt_history_select_own ON public.prompt_history;
DROP POLICY IF EXISTS prompt_history_insert_own ON public.prompt_history;

-- =============================================================================
-- PHASE 4: Enable RLS
-- =============================================================================

ALTER TABLE public.talent ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.talent FORCE ROW LEVEL SECURITY;

ALTER TABLE public.creative_dna ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.creative_dna FORCE ROW LEVEL SECURITY;

ALTER TABLE public.generation_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.generation_feedback FORCE ROW LEVEL SECURITY;

ALTER TABLE public.continuity_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.continuity_notes FORCE ROW LEVEL SECURITY;

ALTER TABLE public.creative_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.creative_rules FORCE ROW LEVEL SECURITY;

ALTER TABLE public.style_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.style_preferences FORCE ROW LEVEL SECURITY;

ALTER TABLE public.prompt_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prompt_history FORCE ROW LEVEL SECURITY;

-- =============================================================================
-- PHASE 5: RLS Policies — talent
-- =============================================================================

CREATE POLICY talent_select_own ON public.talent
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY talent_insert_own ON public.talent
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY talent_update_own ON public.talent
    FOR UPDATE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY talent_delete_own ON public.talent
    FOR DELETE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

-- =============================================================================
-- PHASE 6: RLS Policies — creative_dna
-- =============================================================================

CREATE POLICY creative_dna_select_own ON public.creative_dna
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY creative_dna_insert_own ON public.creative_dna
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY creative_dna_update_own ON public.creative_dna
    FOR UPDATE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

-- =============================================================================
-- PHASE 7: RLS Policies — generation_feedback
-- =============================================================================

CREATE POLICY feedback_select_own ON public.generation_feedback
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY feedback_insert_own ON public.generation_feedback
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

-- =============================================================================
-- PHASE 8: RLS Policies — continuity_notes
-- =============================================================================

CREATE POLICY continuity_select_own ON public.continuity_notes
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY continuity_insert_own ON public.continuity_notes
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY continuity_update_own ON public.continuity_notes
    FOR UPDATE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY continuity_delete_own ON public.continuity_notes
    FOR DELETE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

-- =============================================================================
-- PHASE 9: RLS Policies — creative_rules
-- =============================================================================

CREATE POLICY rules_select_own ON public.creative_rules
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY rules_insert_own ON public.creative_rules
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY rules_delete_own ON public.creative_rules
    FOR DELETE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

-- =============================================================================
-- PHASE 10: RLS Policies — style_preferences
-- =============================================================================

CREATE POLICY prefs_select_own ON public.style_preferences
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY prefs_upsert_own ON public.style_preferences
    FOR ALL TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

-- =============================================================================
-- PHASE 11: RLS Policies — prompt_history
-- =============================================================================

CREATE POLICY prompt_history_select_own ON public.prompt_history
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY prompt_history_insert_own ON public.prompt_history
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

COMMIT;

-- =============================================================================
-- ROLLBACK:
-- =============================================================================
-- BEGIN;
-- DROP POLICY IF EXISTS talent_select_own ON public.talent;
-- DROP POLICY IF EXISTS talent_insert_own ON public.talent;
-- DROP POLICY IF EXISTS talent_update_own ON public.talent;
-- DROP POLICY IF EXISTS talent_delete_own ON public.talent;
-- DROP POLICY IF EXISTS creative_dna_select_own ON public.creative_dna;
-- DROP POLICY IF EXISTS creative_dna_insert_own ON public.creative_dna;
-- DROP POLICY IF EXISTS creative_dna_update_own ON public.creative_dna;
-- DROP POLICY IF EXISTS feedback_select_own ON public.generation_feedback;
-- DROP POLICY IF EXISTS feedback_insert_own ON public.generation_feedback;
-- DROP POLICY IF EXISTS continuity_select_own ON public.continuity_notes;
-- DROP POLICY IF EXISTS continuity_insert_own ON public.continuity_notes;
-- DROP POLICY IF EXISTS continuity_update_own ON public.continuity_notes;
-- DROP POLICY IF EXISTS continuity_delete_own ON public.continuity_notes;
-- DROP POLICY IF EXISTS rules_select_own ON public.creative_rules;
-- DROP POLICY IF EXISTS rules_insert_own ON public.creative_rules;
-- DROP POLICY IF EXISTS rules_delete_own ON public.creative_rules;
-- DROP POLICY IF EXISTS prefs_select_own ON public.style_preferences;
-- DROP POLICY IF EXISTS prefs_upsert_own ON public.style_preferences;
-- DROP POLICY IF EXISTS prompt_history_select_own ON public.prompt_history;
-- DROP POLICY IF EXISTS prompt_history_insert_own ON public.prompt_history;
-- ALTER TABLE public.talent DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.creative_dna DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.generation_feedback DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.continuity_notes DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.creative_rules DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.style_preferences DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.prompt_history DISABLE ROW LEVEL SECURITY;
-- COMMIT;
