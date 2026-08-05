-- Migration 036: Infrastructure Authorization Tables
-- Story 022: Role-based access control for infrastructure endpoints
--
-- Creates:
--   1. infra_audit_log — durable audit trail for infrastructure operations
--   2. Adds org_id to worker_sessions for tenant-scoped worker ownership
--
-- Run: psql $SUPABASE_URL -f docs/sql/036_infra_authorization.sql

-- =============================================================================
-- 1. infra_audit_log — Audit trail for infrastructure operations
-- =============================================================================

CREATE TABLE IF NOT EXISTS infra_audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID,                                       -- tenant scope (nullable for system events)
    actor_id    TEXT NOT NULL,                              -- user_id from JWT
    actor_email TEXT,                                       -- informational
    role        TEXT NOT NULL,                              -- role at time of action
    action      TEXT NOT NULL,                              -- e.g. 'launch_worker', 'stop_fleet'
    capability  TEXT NOT NULL,                              -- e.g. 'infra:admin'
    resource_type TEXT,                                     -- e.g. 'worker', 'host'
    resource_id TEXT,                                       -- e.g. worker_id, host_id
    request_data JSONB DEFAULT '{}'::jsonb,                 -- sanitized request payload
    result      TEXT NOT NULL DEFAULT 'success',            -- success | denied | error
    denial_reason TEXT,                                     -- why access was denied (if result=denied)
    requires_approval BOOLEAN DEFAULT FALSE,               -- flagged for approval flow
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS ix_infra_audit_log_org_id
    ON infra_audit_log (org_id);

CREATE INDEX IF NOT EXISTS ix_infra_audit_log_actor_id
    ON infra_audit_log (actor_id);

CREATE INDEX IF NOT EXISTS ix_infra_audit_log_action
    ON infra_audit_log (action);

CREATE INDEX IF NOT EXISTS ix_infra_audit_log_timestamp
    ON infra_audit_log (timestamp DESC);

CREATE INDEX IF NOT EXISTS ix_infra_audit_log_result
    ON infra_audit_log (result)
    WHERE result = 'denied';

-- RLS: users can see audit events for their own org
ALTER TABLE infra_audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "audit_org_isolation" ON infra_audit_log
    FOR SELECT
    USING (
        org_id = (auth.jwt() ->> 'org_id')::uuid
        OR org_id IS NULL  -- system events visible to all authenticated
    );

-- Only the service role can INSERT (backend writes via service key)
CREATE POLICY "audit_insert_service_only" ON infra_audit_log
    FOR INSERT
    WITH CHECK (true);  -- service_role bypasses RLS; anon/authenticated blocked by default


-- =============================================================================
-- 2. Add org_id to worker_sessions for tenant-scoped ownership
-- =============================================================================

-- Add org_id column if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'worker_sessions' AND column_name = 'org_id'
    ) THEN
        ALTER TABLE worker_sessions ADD COLUMN org_id UUID;
    END IF;
END $$;

-- Index for tenant filtering
CREATE INDEX IF NOT EXISTS ix_worker_sessions_org_id
    ON worker_sessions (org_id);

-- RLS policy: users can only see their org's worker sessions
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'worker_sessions' AND policyname = 'worker_sessions_org_isolation'
    ) THEN
        ALTER TABLE worker_sessions ENABLE ROW LEVEL SECURITY;

        CREATE POLICY "worker_sessions_org_isolation" ON worker_sessions
            FOR ALL
            USING (org_id = (auth.jwt() ->> 'org_id')::uuid);
    END IF;
END $$;


-- =============================================================================
-- 3. Rollback
-- =============================================================================
-- To rollback this migration:
--
-- DROP TABLE IF EXISTS infra_audit_log;
-- ALTER TABLE worker_sessions DROP COLUMN IF EXISTS org_id;
-- DROP INDEX IF EXISTS ix_worker_sessions_org_id;
-- DROP POLICY IF EXISTS "worker_sessions_org_isolation" ON worker_sessions;
