-- =============================================================================
-- AI Studio: Voice, Audio, and Lip Sync Pipeline (Priority 6)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

CREATE TABLE IF NOT EXISTS voice_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    character_id UUID,
    name TEXT NOT NULL,
    provider TEXT DEFAULT 'simulation',
    provider_voice_id TEXT,
    voice_type TEXT DEFAULT 'character',
    language TEXT DEFAULT 'en',
    accent TEXT,
    gender TEXT,
    age_range TEXT,
    tone TEXT,
    speaking_style TEXT,
    speed FLOAT DEFAULT 1.0,
    pitch FLOAT DEFAULT 1.0,
    stability FLOAT DEFAULT 0.7,
    similarity FLOAT DEFAULT 0.8,
    status TEXT DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_voice_profiles_talent ON voice_profiles(talent_id);
CREATE INDEX ix_voice_profiles_status ON voice_profiles(status);

CREATE TABLE IF NOT EXISTS voice_samples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    voice_profile_id UUID NOT NULL REFERENCES voice_profiles(id) ON DELETE CASCADE,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    transcript TEXT,
    duration_seconds FLOAT DEFAULT 0.0,
    quality_score FLOAT DEFAULT 1.0,
    approved BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_voice_samples_profile ON voice_samples(voice_profile_id);

CREATE TABLE IF NOT EXISTS audio_clips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    voice_profile_id UUID REFERENCES voice_profiles(id) ON DELETE SET NULL,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    text TEXT,
    clip_type TEXT DEFAULT 'tts',
    duration_seconds FLOAT DEFAULT 0.0,
    provider TEXT DEFAULT 'simulation',
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'pending',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_audio_clips_profile ON audio_clips(voice_profile_id);
CREATE INDEX ix_audio_clips_status ON audio_clips(status);

CREATE TABLE IF NOT EXISTS lip_sync_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    video_asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    audio_asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    output_asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    provider TEXT DEFAULT 'simulation',
    worker_id UUID,
    status TEXT DEFAULT 'queued',
    input JSONB DEFAULT '{}',
    output JSONB DEFAULT '{}',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_lip_sync_status ON lip_sync_jobs(status);

CREATE TABLE IF NOT EXISTS music_tracks_db (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    mood TEXT,
    genre TEXT,
    tempo INTEGER DEFAULT 120,
    energy TEXT DEFAULT 'medium',
    duration_seconds FLOAT DEFAULT 0.0,
    provider TEXT DEFAULT 'library',
    license_type TEXT DEFAULT 'royalty_free',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_music_tracks_mood ON music_tracks_db(mood);

CREATE TABLE IF NOT EXISTS sound_effects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    category TEXT DEFAULT 'ambient',
    duration_seconds FLOAT DEFAULT 0.0,
    provider TEXT DEFAULT 'library',
    license_type TEXT DEFAULT 'royalty_free',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_sfx_category ON sound_effects(category);
