-- =============================================================================
-- AI Studio: Story Engine tables (Phase E)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

-- Universes: top-level creative world
CREATE TABLE IF NOT EXISTS universes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT,
    genre TEXT,
    tone TEXT,
    setting TEXT,
    rules JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_universes_project ON universes(project_id);

-- Characters: recurring people in a universe
CREATE TABLE IF NOT EXISTS characters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    universe_id UUID REFERENCES universes(id) ON DELETE CASCADE,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT,
    personality TEXT,
    goals TEXT,
    backstory TEXT,
    voice_style TEXT,
    wardrobe_default TEXT,
    visual_dna JSONB DEFAULT '{}',
    relationships JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_characters_universe ON characters(universe_id);
CREATE INDEX ix_characters_talent ON characters(talent_id);

-- Episodes: individual content pieces
CREATE TABLE IF NOT EXISTS episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    universe_id UUID REFERENCES universes(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    episode_number INTEGER DEFAULT 1,
    status TEXT DEFAULT 'draft',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_episodes_universe ON episodes(universe_id);
CREATE INDEX ix_episodes_status ON episodes(status);

-- Scenes: segments within an episode
CREATE TABLE IF NOT EXISTS scenes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
    scene_number INTEGER DEFAULT 1,
    title TEXT,
    purpose TEXT,
    location TEXT,
    time_of_day TEXT DEFAULT 'day',
    weather TEXT DEFAULT 'clear',
    mood TEXT,
    characters JSONB DEFAULT '[]',
    dialogue JSONB DEFAULT '[]',
    camera_style TEXT,
    music TEXT,
    desired_emotion TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_scenes_episode ON scenes(episode_id);

-- Shots: individual generation units
CREATE TABLE IF NOT EXISTS shots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scene_id UUID REFERENCES scenes(id) ON DELETE CASCADE,
    shot_number INTEGER DEFAULT 1,
    shot_type TEXT DEFAULT 'medium',
    description TEXT,
    characters JSONB DEFAULT '[]',
    camera_movement TEXT,
    duration_seconds FLOAT DEFAULT 3.0,
    dialogue TEXT,
    action TEXT,
    mood TEXT,
    transition TEXT DEFAULT 'cut',
    generation_params JSONB DEFAULT '{}',
    status TEXT DEFAULT 'planned',
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_shots_scene ON shots(scene_id);
CREATE INDEX ix_shots_status ON shots(status);

-- Story Memory: persistent events in the universe
CREATE TABLE IF NOT EXISTS story_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    universe_id UUID REFERENCES universes(id) ON DELETE CASCADE,
    character_id UUID REFERENCES characters(id) ON DELETE SET NULL,
    episode_id UUID REFERENCES episodes(id) ON DELETE SET NULL,
    scene_id UUID REFERENCES scenes(id) ON DELETE SET NULL,
    event TEXT NOT NULL,
    category TEXT DEFAULT 'event',
    active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_memory_universe ON story_memory(universe_id);
CREATE INDEX ix_memory_character ON story_memory(character_id);
CREATE INDEX ix_memory_category ON story_memory(category);
