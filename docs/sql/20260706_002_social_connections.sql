-- =============================================================================
-- 021: Social Connections — OAuth tokens for publishing platforms
-- =============================================================================

CREATE TABLE IF NOT EXISTS social_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'::uuid,
    platform TEXT NOT NULL UNIQUE,
    status TEXT DEFAULT 'connected',
    access_token TEXT DEFAULT '',
    refresh_token TEXT DEFAULT '',
    token_type TEXT DEFAULT 'bearer',
    expires_at TIMESTAMPTZ,
    scope TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_social_connections_platform ON social_connections(platform);
CREATE INDEX IF NOT EXISTS ix_social_connections_org_id ON social_connections(org_id);

ALTER TABLE social_connections ENABLE ROW LEVEL SECURITY;
CREATE POLICY "social_connections_all" ON social_connections FOR ALL USING (true);
