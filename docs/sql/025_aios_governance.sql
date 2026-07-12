-- AIOS Governance tables
-- Phase 3: Approval queue, policies

CREATE TABLE IF NOT EXISTS aios_approvals (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    org_id UUID DEFAULT '00000000-0000-0000-0000-000000000000',
    tool TEXT NOT NULL,
    parameters JSONB DEFAULT '{}',
    reasoning TEXT DEFAULT '',
    estimated_cost_usd NUMERIC(10, 6) DEFAULT 0,
    estimated_time_seconds NUMERIC(10, 2) DEFAULT 0,
    proposed_by_agent TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, approved, rejected, expired
    rejection_reason TEXT DEFAULT '',
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_aios_approvals_status ON aios_approvals(status);
CREATE INDEX IF NOT EXISTS ix_aios_approvals_org ON aios_approvals(org_id);
CREATE INDEX IF NOT EXISTS ix_aios_approvals_session ON aios_approvals(session_id);

CREATE TABLE IF NOT EXISTS aios_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    org_id UUID DEFAULT '00000000-0000-0000-0000-000000000000',
    policies JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id)
);
