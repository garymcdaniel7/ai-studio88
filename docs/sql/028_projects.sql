-- Projects — the primary organizational unit in AI Studio V2
-- Everything belongs to a project: assets, jobs, storyboards, publishing plans.

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active', -- active, archived, completed
    category TEXT DEFAULT 'campaign', -- campaign, collection, story, product, personal

    -- Visual
    thumbnail_url TEXT, -- Auto-generated from first asset
    color TEXT DEFAULT '#7c3aed', -- Purple default, user can customize

    -- Content tracking
    asset_count INT DEFAULT 0,
    video_count INT DEFAULT 0,
    generation_count INT DEFAULT 0,
    total_cost FLOAT DEFAULT 0.0,

    -- Relationships
    talent_ids UUID[] DEFAULT '{}', -- Talent associated with this project
    recipe_ids UUID[] DEFAULT '{}', -- Recipes used in this project
    brand_kit_id UUID, -- Optional brand kit association

    -- Brain context
    brain_session_id TEXT, -- Associated Brain conversation
    notes TEXT, -- User notes / brief

    -- Publishing
    publish_platforms TEXT[] DEFAULT '{}', -- instagram, tiktok, youtube, etc
    scheduled_posts INT DEFAULT 0,
    published_posts INT DEFAULT 0,

    -- Metadata
    tags TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_projects_org_id ON projects(org_id);
CREATE INDEX IF NOT EXISTS ix_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS ix_projects_created_at ON projects(created_at DESC);

-- RLS
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY "project_org_isolation" ON projects
    FOR ALL
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

-- Link table: project ↔ assets
CREATE TABLE IF NOT EXISTS project_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    position INT DEFAULT 0, -- For ordering in storyboard
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_project_assets_project ON project_assets(project_id);
CREATE INDEX IF NOT EXISTS ix_project_assets_asset ON project_assets(asset_id);
