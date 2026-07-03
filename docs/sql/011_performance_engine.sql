-- =============================================================================
-- AI Studio: Performance Engine (Priority 7)
-- Voice training, song studio, performance memory, series continuity
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

-- Voice Training Datasets
CREATE TABLE IF NOT EXISTS voice_datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    voice_profile_id UUID,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    character_id UUID,
    name TEXT NOT NULL,
    description TEXT,
    sample_count INTEGER DEFAULT 0,
    total_duration_seconds FLOAT DEFAULT 0.0,
    status TEXT DEFAULT 'draft',
    consent_confirmed BOOLEAN DEFAULT false,
    usage_rights TEXT,
    source TEXT,
    license_notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_voice_datasets_talent ON voice_datasets(talent_id);

-- Voice Training Jobs
CREATE TABLE IF NOT EXISTS voice_training_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    voice_profile_id UUID,
    voice_dataset_id UUID REFERENCES voice_datasets(id) ON DELETE SET NULL,
    provider TEXT DEFAULT 'simulation',
    worker_id UUID,
    status TEXT DEFAULT 'queued',
    config JSONB DEFAULT '{}',
    output_asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    logs TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_voice_training_status ON voice_training_jobs(status);

-- Voice Versions (trained voice models)
CREATE TABLE IF NOT EXISTS voice_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    voice_profile_id UUID,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    character_id UUID,
    training_job_id UUID REFERENCES voice_training_jobs(id) ON DELETE SET NULL,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    version INTEGER DEFAULT 1,
    name TEXT NOT NULL,
    provider TEXT,
    status TEXT DEFAULT 'active',
    quality_score FLOAT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_voice_versions_talent ON voice_versions(talent_id);

-- Voice DNA (per character — how they speak)
CREATE TABLE IF NOT EXISTS voice_dna (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    character_id UUID,
    personality TEXT,
    vocabulary TEXT,
    cadence TEXT,
    energy TEXT DEFAULT 'medium',
    warmth TEXT DEFAULT 'warm',
    confidence TEXT DEFAULT 'confident',
    humor TEXT,
    pacing TEXT DEFAULT 'moderate',
    filler_words JSONB DEFAULT '[]',
    slang JSONB DEFAULT '[]',
    avoid_words JSONB DEFAULT '[]',
    singing_range TEXT,
    singing_style TEXT,
    singing_genre TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_voice_dna_talent ON voice_dna(talent_id);

-- Songs
CREATE TABLE IF NOT EXISTS songs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    story_id UUID,
    episode_id UUID,
    scene_id UUID,
    character_id UUID,
    title TEXT NOT NULL,
    genre TEXT,
    mood TEXT,
    tempo INTEGER DEFAULT 120,
    musical_key TEXT,
    lyrics TEXT,
    vocal_style TEXT,
    instrumental_style TEXT,
    duration_seconds FLOAT DEFAULT 0.0,
    provider TEXT DEFAULT 'simulation',
    output_asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'draft',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_songs_story ON songs(story_id);
CREATE INDEX ix_songs_episode ON songs(episode_id);

-- Performance Memory (how a character was performing at a given moment)
CREATE TABLE IF NOT EXISTS performance_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    universe_id UUID,
    character_id UUID,
    episode_id UUID,
    scene_id UUID,
    shot_id UUID,
    emotion TEXT,
    energy_level TEXT,
    body_position TEXT,
    facing_direction TEXT,
    wardrobe TEXT,
    props_held JSONB DEFAULT '[]',
    location TEXT,
    time_of_day TEXT,
    weather TEXT,
    dialogue_state TEXT,
    voice_emotion TEXT,
    movement_direction TEXT,
    eyeline TEXT,
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_perf_memory_character ON performance_memory(character_id);
CREATE INDEX ix_perf_memory_episode ON performance_memory(episode_id);
CREATE INDEX ix_perf_memory_scene ON performance_memory(scene_id);

-- Performance DNA (how a character performs generally)
CREATE TABLE IF NOT EXISTS performance_dna (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    character_id UUID,
    body_language TEXT,
    smile_frequency TEXT DEFAULT 'moderate',
    eyebrow_movement TEXT DEFAULT 'expressive',
    eye_contact TEXT DEFAULT 'direct',
    head_tilts TEXT DEFAULT 'occasional',
    walking_style TEXT,
    hand_gestures TEXT DEFAULT 'moderate',
    laugh_style TEXT,
    breathing_pattern TEXT,
    idle_animations JSONB DEFAULT '[]',
    camera_awareness TEXT DEFAULT 'natural',
    signature_moves JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_perf_dna_talent ON performance_dna(talent_id);

-- Series structure (enhances story engine)
CREATE TABLE IF NOT EXISTS series (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    universe_id UUID,
    name TEXT NOT NULL,
    description TEXT,
    genre TEXT,
    platform TEXT DEFAULT 'youtube',
    episode_count INTEGER DEFAULT 0,
    season_count INTEGER DEFAULT 1,
    status TEXT DEFAULT 'planning',
    opening_theme_song_id UUID,
    ending_theme_song_id UUID,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_series_universe ON series(universe_id);

-- Soundtrack cues (music attached to story moments)
CREATE TABLE IF NOT EXISTS soundtrack_cues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id UUID,
    scene_id UUID,
    shot_id UUID,
    song_id UUID REFERENCES songs(id) ON DELETE SET NULL,
    cue_type TEXT DEFAULT 'background',
    start_time FLOAT DEFAULT 0.0,
    duration_seconds FLOAT DEFAULT 0.0,
    volume FLOAT DEFAULT 0.8,
    fade_in BOOLEAN DEFAULT false,
    fade_out BOOLEAN DEFAULT false,
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_soundtrack_episode ON soundtrack_cues(episode_id);
CREATE INDEX ix_soundtrack_scene ON soundtrack_cues(scene_id);
