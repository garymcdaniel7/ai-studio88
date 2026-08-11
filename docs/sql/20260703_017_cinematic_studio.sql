-- =============================================================================
-- AI Studio: Cinematic Studio & Timeline Engine (Priority 11)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

-- Sequences (group scenes within an episode)
CREATE TABLE IF NOT EXISTS sequences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id UUID,
    name TEXT NOT NULL,
    sequence_number INTEGER DEFAULT 1,
    purpose TEXT,
    mood TEXT,
    duration_seconds FLOAT DEFAULT 0.0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_sequences_episode ON sequences(episode_id);

-- Cinematic timelines
CREATE TABLE IF NOT EXISTS cinematic_timelines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    episode_id UUID,
    name TEXT NOT NULL,
    duration_seconds FLOAT DEFAULT 0.0,
    fps INTEGER DEFAULT 24,
    resolution TEXT DEFAULT '1920x1080',
    aspect_ratio TEXT DEFAULT '16:9',
    status TEXT DEFAULT 'editing',
    color_grade TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_cin_timelines_project ON cinematic_timelines(project_id);
CREATE INDEX ix_cin_timelines_status ON cinematic_timelines(status);

-- Timeline tracks (multi-track support)
CREATE TABLE IF NOT EXISTS cinematic_tracks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timeline_id UUID NOT NULL REFERENCES cinematic_timelines(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'Video 1',
    track_type TEXT NOT NULL DEFAULT 'video',
    order_index INTEGER DEFAULT 0,
    muted BOOLEAN DEFAULT false,
    locked BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_cin_tracks_timeline ON cinematic_tracks(timeline_id);

-- Timeline items (clips on tracks)
CREATE TABLE IF NOT EXISTS cinematic_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    track_id UUID NOT NULL REFERENCES cinematic_tracks(id) ON DELETE CASCADE,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    shot_id UUID,
    item_type TEXT DEFAULT 'clip',
    start_time FLOAT DEFAULT 0.0,
    duration FLOAT DEFAULT 3.0,
    in_point FLOAT DEFAULT 0.0,
    out_point FLOAT DEFAULT 0.0,
    transition_in TEXT DEFAULT 'cut',
    transition_out TEXT DEFAULT 'cut',
    speed FLOAT DEFAULT 1.0,
    effects JSONB DEFAULT '[]',
    color_grade TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_cin_items_track ON cinematic_items(track_id);

-- Storyboard panels
CREATE TABLE IF NOT EXISTS storyboard_panels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id UUID,
    scene_id UUID,
    shot_id UUID,
    panel_number INTEGER DEFAULT 1,
    description TEXT,
    camera TEXT,
    dialogue TEXT,
    action TEXT,
    mood TEXT,
    duration_seconds FLOAT DEFAULT 3.0,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    workflow_id UUID,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_storyboard_episode ON storyboard_panels(episode_id);
CREATE INDEX ix_storyboard_scene ON storyboard_panels(scene_id);

-- Render jobs
CREATE TABLE IF NOT EXISTS cinematic_renders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timeline_id UUID REFERENCES cinematic_timelines(id) ON DELETE SET NULL,
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    format TEXT DEFAULT 'mp4',
    resolution TEXT DEFAULT '1920x1080',
    fps INTEGER DEFAULT 24,
    codec TEXT DEFAULT 'h264',
    quality TEXT DEFAULT 'high',
    status TEXT DEFAULT 'queued',
    output_asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    runtime_seconds FLOAT,
    file_size_bytes BIGINT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX ix_cin_renders_timeline ON cinematic_renders(timeline_id);
CREATE INDEX ix_cin_renders_status ON cinematic_renders(status);

-- Editing operations log
CREATE TABLE IF NOT EXISTS editing_operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timeline_id UUID REFERENCES cinematic_timelines(id) ON DELETE CASCADE,
    operation TEXT NOT NULL,
    target_item_id UUID,
    parameters JSONB DEFAULT '{}',
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_editing_ops_timeline ON editing_operations(timeline_id);
