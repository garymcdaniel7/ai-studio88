-- =============================================================================
-- AI Studio: Voice & Audio Tenant Isolation (Story 018)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================
--
-- TABLES COVERED:
-- 1. voice_profiles — DIRECT org_id (customer-owned voice identities)
-- 2. voice_samples — INHERITED via voice_profile_id FK (CASCADE delete)
-- 3. audio_clips — DIRECT org_id (generated audio output)
--
-- OWNERSHIP MODEL:
-- - voice_profiles: DIRECT (org_id column, added in migration 030)
-- - voice_samples: INHERITED via voice_profile_id FK → voice_profiles.org_id
--   Denormalized: org_id added for efficient RLS without JOIN
-- - audio_clips: DIRECT (org_id column, added in migration 030)
--
-- PUBLIC vs PRIVATE:
-- Provider catalog data (ElevenLabs voice list, MOSS available voices) is
-- retrieved live from provider APIs — not stored in tenant tables.
-- All data in these tables is PRIVATE customer content.
--
-- SENSITIVE DATA:
-- - voice_samples: contain raw audio files (biometric identity data)
-- - voice_profiles: contain provider voice_id (cloning reference)
-- - audio_clips: contain generated speech output
-- =============================================================================

BEGIN;

-- =============================================================================
-- PHASE 1: Add org_id to voice_samples (denormalized for RLS)
-- =============================================================================

ALTER TABLE public.voice_samples ADD COLUMN IF NOT EXISTS org_id UUID;

-- =============================================================================
-- PHASE 2: Indexes for tenant-scoped queries
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_voice_profiles_org_id ON public.voice_profiles(org_id);
CREATE INDEX IF NOT EXISTS ix_voice_profiles_org_talent ON public.voice_profiles(org_id, talent_id);
CREATE INDEX IF NOT EXISTS ix_voice_samples_org_id ON public.voice_samples(org_id);
CREATE INDEX IF NOT EXISTS ix_audio_clips_org_id ON public.audio_clips(org_id);
CREATE INDEX IF NOT EXISTS ix_audio_clips_org_profile ON public.audio_clips(org_id, voice_profile_id);

-- =============================================================================
-- PHASE 3: Drop existing policies (idempotent)
-- =============================================================================

DROP POLICY IF EXISTS voice_profiles_select_own ON public.voice_profiles;
DROP POLICY IF EXISTS voice_profiles_insert_own ON public.voice_profiles;
DROP POLICY IF EXISTS voice_profiles_update_own ON public.voice_profiles;
DROP POLICY IF EXISTS voice_profiles_delete_own ON public.voice_profiles;

DROP POLICY IF EXISTS voice_samples_select_own ON public.voice_samples;
DROP POLICY IF EXISTS voice_samples_insert_own ON public.voice_samples;
DROP POLICY IF EXISTS voice_samples_delete_own ON public.voice_samples;

DROP POLICY IF EXISTS audio_clips_select_own ON public.audio_clips;
DROP POLICY IF EXISTS audio_clips_insert_own ON public.audio_clips;
DROP POLICY IF EXISTS audio_clips_delete_own ON public.audio_clips;

-- =============================================================================
-- PHASE 4: Enable RLS
-- =============================================================================

ALTER TABLE public.voice_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voice_profiles FORCE ROW LEVEL SECURITY;

ALTER TABLE public.voice_samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voice_samples FORCE ROW LEVEL SECURITY;

ALTER TABLE public.audio_clips ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audio_clips FORCE ROW LEVEL SECURITY;

-- =============================================================================
-- PHASE 5: RLS Policies — voice_profiles
-- =============================================================================

CREATE POLICY voice_profiles_select_own ON public.voice_profiles
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY voice_profiles_insert_own ON public.voice_profiles
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY voice_profiles_update_own ON public.voice_profiles
    FOR UPDATE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY voice_profiles_delete_own ON public.voice_profiles
    FOR DELETE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

-- =============================================================================
-- PHASE 6: RLS Policies — voice_samples
-- =============================================================================

CREATE POLICY voice_samples_select_own ON public.voice_samples
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY voice_samples_insert_own ON public.voice_samples
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY voice_samples_delete_own ON public.voice_samples
    FOR DELETE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

-- =============================================================================
-- PHASE 7: RLS Policies — audio_clips
-- =============================================================================

CREATE POLICY audio_clips_select_own ON public.audio_clips
    FOR SELECT TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY audio_clips_insert_own ON public.audio_clips
    FOR INSERT TO authenticated
    WITH CHECK (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY audio_clips_delete_own ON public.audio_clips
    FOR DELETE TO authenticated
    USING (org_id IS NOT NULL AND org_id = (auth.jwt() ->> 'org_id')::uuid);

COMMIT;

-- =============================================================================
-- ROLLBACK:
-- =============================================================================
-- BEGIN;
-- DROP POLICY IF EXISTS voice_profiles_select_own ON public.voice_profiles;
-- DROP POLICY IF EXISTS voice_profiles_insert_own ON public.voice_profiles;
-- DROP POLICY IF EXISTS voice_profiles_update_own ON public.voice_profiles;
-- DROP POLICY IF EXISTS voice_profiles_delete_own ON public.voice_profiles;
-- DROP POLICY IF EXISTS voice_samples_select_own ON public.voice_samples;
-- DROP POLICY IF EXISTS voice_samples_insert_own ON public.voice_samples;
-- DROP POLICY IF EXISTS voice_samples_delete_own ON public.voice_samples;
-- DROP POLICY IF EXISTS audio_clips_select_own ON public.audio_clips;
-- DROP POLICY IF EXISTS audio_clips_insert_own ON public.audio_clips;
-- DROP POLICY IF EXISTS audio_clips_delete_own ON public.audio_clips;
-- ALTER TABLE public.voice_profiles DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.voice_samples DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.audio_clips DISABLE ROW LEVEL SECURITY;
-- COMMIT;
