-- =============================================================================
-- AI Studio: Video Pipeline tables (Priority 5)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

CREATE TABLE IF NOT EXISTS video_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    campaign_id UUID,
    story_id UUID,
    name TEXT NOT NULL,
    description TEXT,
    video_type TEXT NOT NULL DEFAULT 'reel',
    platform TEXT DEFAULT 'instagram',
    aspect_ratio TEXT DEFAULT '9:16',
    duration_seconds FLOAT DEFAULT 5.0,
    status TEXT DEFAULT 'draft',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_video_projects_talent ON video_projects(talent_id);
CREATE INDEX ix_video_projects_status ON video_projects(status);
CREATE INDEX ix_video_projects_type ON video_projects(video_type);

CREATE TABLE IF NOT EXISTS video_shots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
    scene_id UUID,
    shot_number INTEGER DEFAULT 1,
    prompt TEXT,
    negative_prompt TEXT,
    motion_prompt TEXT,
    input_asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    output_asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    provider TEXT DEFAULT 'simulation',
    model TEXT DEFAULT 'wan-2.1',
    duration_seconds FLOAT DEFAULT 3.0,
    fps INTEGER DEFAULT 24,
    resolution TEXT DEFAULT '1080x1920',
    camera_motion TEXT DEFAULT 'static',
    status TEXT DEFAULT 'planned',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_video_shots_project ON video_shots(video_project_id);
CREATE INDEX ix_video_shots_status ON video_shots(status);

CREATE TABLE IF NOT EXISTS video_renders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    provider TEXT DEFAULT 'simulation',
    worker_id UUID,
    status TEXT DEFAULT 'queued',
    output_asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    runtime_seconds FLOAT,
    error TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_video_renders_project ON video_renders(video_project_id);
CREATE INDEX ix_video_renders_status ON video_renders(status);

CREATE TABLE IF NOT EXISTS timeline_tracks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'Video',
    track_type TEXT NOT NULL DEFAULT 'video',
    order_index INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_timeline_tracks_project ON timeline_tracks(video_project_id);

CREATE TABLE IF NOT EXISTS timeline_clips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    track_id UUID NOT NULL REFERENCES timeline_tracks(id) ON DELETE CASCADE,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    start_time FLOAT DEFAULT 0.0,
    end_time FLOAT DEFAULT 3.0,
    duration_seconds FLOAT DEFAULT 3.0,
    clip_type TEXT DEFAULT 'video',
    effects JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_timeline_clips_track ON timeline_clips(track_id);

CREATE TABLE IF NOT EXISTS timeline_exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_project_id UUID NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    output_asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    export_format TEXT DEFAULT 'mp4',
    resolution TEXT DEFAULT '1080x1920',
    fps INTEGER DEFAULT 24,
    status TEXT DEFAULT 'queued',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX ix_timeline_exports_project ON timeline_exports(video_project_id);
