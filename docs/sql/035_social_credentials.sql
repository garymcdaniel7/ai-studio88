-- =============================================================================
-- AI Studio: Social Credentials Metadata (Story 027)
-- Token encryption handled by workspace_credentials (Story 023/034).
-- This table stores connection metadata, scopes, and lifecycle state.
-- =============================================================================

CREATE TABLE IF NOT EXISTS social_account_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    platform TEXT NOT NULL CHECK (platform IN ('instagram', 'tiktok', 'youtube', 'x')),
    account_id TEXT NOT NULL,  -- Provider-specific user/page ID
    account_name TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'expired', 'refresh_failed', 'revoked', 'scope_insufficient', 'pending')),
    granted_scopes TEXT[] DEFAULT '{}',
    required_scopes_met BOOLEAN DEFAULT false,
    expires_at TIMESTAMPTZ,
    last_refreshed_at TIMESTAMPTZ,
    connected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One active connection per (org, platform, account)
CREATE UNIQUE INDEX IF NOT EXISTS uq_social_connections_active
    ON social_account_connections(org_id, platform, account_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS ix_social_connections_org ON social_account_connections(org_id);
CREATE INDEX IF NOT EXISTS ix_social_connections_platform ON social_account_connections(platform);

-- RLS
ALTER TABLE social_account_connections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "social_connections_org_isolation" ON social_account_connections
    FOR ALL USING (
        org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active')
    ) WITH CHECK (
        org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active')
    );
