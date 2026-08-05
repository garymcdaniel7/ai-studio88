-- =============================================================================
-- AI Studio: Video Domain RLS Policies (Story 017)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================
-- Adds org_id columns (if missing) and RLS policies to video tables.
-- Child tables (video_shots, timeline_tracks) inherit ownership from
-- the parent video_projects table via FK.

-- Phase 1: Ensure org_id columns exist
ALTER TABLE video_projects ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE video_shots ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE video_renders ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE timeline_tracks ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE timeline_exports ADD COLUMN IF NOT EXISTS org_id UUID;

-- Phase 2: Indexes
CREATE INDEX IF NOT EXISTS ix_video_projects_org_id ON video_projects(org_id);
CREATE INDEX IF NOT EXISTS ix_video_shots_org_id ON video_shots(org_id);
CREATE INDEX IF NOT EXISTS ix_video_renders_org_id ON video_renders(org_id);

-- Phase 3: Enable RLS
ALTER TABLE video_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_shots ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_renders ENABLE ROW LEVEL SECURITY;
ALTER TABLE timeline_tracks ENABLE ROW LEVEL SECURITY;
ALTER TABLE timeline_exports ENABLE ROW LEVEL SECURITY;

-- Phase 4: Policies
DROP POLICY IF EXISTS "video_projects_org_isolation" ON video_projects;
CREATE POLICY "video_projects_org_isolation" ON video_projects
    FOR ALL USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid() AND om.status = 'active'
        )
    ) WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid() AND om.status = 'active'
        )
    );

DROP POLICY IF EXISTS "video_shots_org_isolation" ON video_shots;
CREATE POLICY "video_shots_org_isolation" ON video_shots
    FOR ALL USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid() AND om.status = 'active'
        )
    ) WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid() AND om.status = 'active'
        )
    );

DROP POLICY IF EXISTS "video_renders_org_isolation" ON video_renders;
CREATE POLICY "video_renders_org_isolation" ON video_renders
    FOR ALL USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid() AND om.status = 'active'
        )
    ) WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid() AND om.status = 'active'
        )
    );

DROP POLICY IF EXISTS "timeline_tracks_org_isolation" ON timeline_tracks;
CREATE POLICY "timeline_tracks_org_isolation" ON timeline_tracks
    FOR ALL USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid() AND om.status = 'active'
        )
    ) WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid() AND om.status = 'active'
        )
    );

DROP POLICY IF EXISTS "timeline_exports_org_isolation" ON timeline_exports;
CREATE POLICY "timeline_exports_org_isolation" ON timeline_exports
    FOR ALL USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid() AND om.status = 'active'
        )
    ) WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid() AND om.status = 'active'
        )
    );
