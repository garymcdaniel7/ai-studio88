-- =============================================================================
-- AI Studio: Workspace Credentials (Story 023)
-- Encrypted per-workspace provider credential storage
-- =============================================================================

CREATE TABLE IF NOT EXISTS workspace_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,  -- vast_ai, runpod, backblaze_b2, openai, etc.
    environment TEXT NOT NULL DEFAULT 'production',
    ownership TEXT NOT NULL DEFAULT 'customer' CHECK (ownership IN ('platform', 'customer')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'rotated', 'revoked', 'expired')),
    key_id TEXT NOT NULL DEFAULT '',  -- Non-secret identifier/hint (e.g., first 8 chars)
    encrypted_secret TEXT NOT NULL,   -- Fernet-encrypted blob (NEVER plaintext)
    version INT NOT NULL DEFAULT 1,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    rotated_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Only one active credential per (org, provider, environment)
CREATE UNIQUE INDEX IF NOT EXISTS uq_workspace_credentials_active
    ON workspace_credentials(org_id, provider, environment)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS ix_workspace_credentials_org ON workspace_credentials(org_id);
CREATE INDEX IF NOT EXISTS ix_workspace_credentials_provider ON workspace_credentials(provider);

-- RLS
ALTER TABLE workspace_credentials ENABLE ROW LEVEL SECURITY;

-- Only org members can see their own credentials (masked — app layer enforces no secret exposure)
CREATE POLICY "workspace_credentials_org_isolation" ON workspace_credentials
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

-- Audit table for credential operations
CREATE TABLE IF NOT EXISTS credential_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    provider TEXT NOT NULL,
    action TEXT NOT NULL,  -- store, resolve, rotate, revoke, validate
    actor TEXT NOT NULL,
    credential_id UUID,
    details TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_credential_audit_org ON credential_audit_log(org_id);
CREATE INDEX IF NOT EXISTS ix_credential_audit_created ON credential_audit_log(created_at DESC);

ALTER TABLE credential_audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "credential_audit_org_isolation" ON credential_audit_log
    FOR SELECT USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid() AND om.status = 'active'
        )
    );
