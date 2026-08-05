-- =============================================================================
-- AI Studio: Governance Policy Audit Trail (Story 026)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

BEGIN;

-- Immutable audit log for every governance policy change
CREATE TABLE IF NOT EXISTS governance_policy_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    previous_policies JSONB NOT NULL DEFAULT '{}',
    new_policies JSONB NOT NULL DEFAULT '{}',
    changed_fields TEXT[] NOT NULL DEFAULT '{}',
    reason TEXT DEFAULT '',
    version INT NOT NULL DEFAULT 1,
    request_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS ix_governance_audit_org ON governance_policy_audit(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_governance_audit_actor ON governance_policy_audit(actor_id);

-- RLS
ALTER TABLE governance_policy_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance_policy_audit FORCE ROW LEVEL SECURITY;

-- Only admins/owners can read audit trail for their org
CREATE POLICY governance_audit_select_own ON governance_policy_audit
    FOR SELECT TO authenticated
    USING (
        org_id = (auth.jwt() ->> 'org_id')::uuid
        AND EXISTS (
            SELECT 1 FROM public.org_members
            WHERE org_members.user_id = auth.uid()
              AND org_members.org_id = governance_policy_audit.org_id
              AND org_members.role IN ('admin', 'owner')
              AND org_members.status = 'active'
        )
    );

-- INSERT only via service-role (backend)
-- No authenticated INSERT policy = denied for direct client access

COMMIT;
