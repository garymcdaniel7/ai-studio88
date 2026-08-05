-- =============================================================================
-- AI Studio: Durable Approvals (Story 035)
-- Single-use, argument-bound, expirable approval records.
-- =============================================================================

CREATE TABLE IF NOT EXISTS durable_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    command_id UUID NOT NULL,  -- Bound ActionCommand
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    requesting_user_id UUID NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    tool TEXT NOT NULL,
    argument_hash TEXT NOT NULL,  -- SHA256 of canonical parameters
    estimated_cost_usd FLOAT DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'consumed', 'rejected', 'expired', 'invalidated')),
    display_summary TEXT DEFAULT '',
    -- Decision
    approver_user_id UUID,
    decision_reason TEXT DEFAULT '',
    execution_command_id UUID,
    -- Timestamps
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    -- Metadata
    metadata JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_durable_approvals_org ON durable_approvals(org_id);
CREATE INDEX IF NOT EXISTS ix_durable_approvals_status ON durable_approvals(status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS ix_durable_approvals_command ON durable_approvals(command_id);
CREATE INDEX IF NOT EXISTS ix_durable_approvals_expires ON durable_approvals(expires_at) WHERE status = 'pending';

-- RLS
ALTER TABLE durable_approvals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "durable_approvals_org_isolation" ON durable_approvals
    FOR ALL USING (
        org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active')
    ) WITH CHECK (
        org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active')
    );
