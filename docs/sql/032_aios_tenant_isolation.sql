-- =============================================================================
-- AI Studio: AIOS Tenant Isolation (Story 014)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================
--
-- OVERVIEW:
-- This migration enforces workspace ownership on all AIOS tables:
-- aios_sessions, aios_messages, aios_decisions, aios_approvals, aios_policies.
--
-- CHANGES:
-- 1. Add missing columns (org_id, user_id/actor attribution)
-- 2. Remove zero-UUID defaults (replace with NULL — explicit ownership required)
-- 3. Add foreign key constraints where missing
-- 4. Add tenant-scoped indexes
-- 5. Quarantine/mark legacy rows with zero-UUID org_id
-- 6. Enable RLS with operation-specific policies
--
-- OWNERSHIP MODEL:
-- - aios_sessions: DIRECT (org_id + user_id columns)
-- - aios_messages: INHERITED via session_id FK → aios_sessions.org_id
-- - aios_decisions: DIRECT (org_id column added here)
-- - aios_approvals: DIRECT (org_id column, already exists)
-- - aios_policies: DIRECT (org_id column, already exists, UNIQUE per org)
--
-- ZERO-UUID DISPOSITION:
-- The old DEFAULT '00000000-0000-0000-0000-000000000000' is NOT a valid org.
-- Rows with this value are marked UNVERIFIED in metadata and invisible to
-- tenant RLS policies (only service-role can see them for backfill).
--
-- SAFETY: Transactional, idempotent (IF NOT EXISTS, DROP IF EXISTS patterns).
-- =============================================================================

BEGIN;

-- =============================================================================
-- PHASE 1: Schema additions — add missing columns
-- =============================================================================

-- aios_sessions: add user_id for actor attribution
ALTER TABLE public.aios_sessions ADD COLUMN IF NOT EXISTS user_id UUID;

-- aios_decisions: add org_id + user_id (completely missing)
ALTER TABLE public.aios_decisions ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE public.aios_decisions ADD COLUMN IF NOT EXISTS user_id UUID;

-- aios_messages: add org_id for efficient tenant-safe queries (denormalized)
-- Without this, every message query would need a JOIN through sessions.
ALTER TABLE public.aios_messages ADD COLUMN IF NOT EXISTS org_id UUID;

-- aios_approvals: add user_id for who requested/decided
ALTER TABLE public.aios_approvals ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE public.aios_approvals ADD COLUMN IF NOT EXISTS decided_by UUID;

-- =============================================================================
-- PHASE 2: Remove zero-UUID defaults
-- =============================================================================
-- Replace with no default — callers MUST provide org_id explicitly.

ALTER TABLE public.aios_sessions ALTER COLUMN org_id DROP DEFAULT;
ALTER TABLE public.aios_approvals ALTER COLUMN org_id DROP DEFAULT;
ALTER TABLE public.aios_policies ALTER COLUMN org_id DROP DEFAULT;

-- =============================================================================
-- PHASE 3: Quarantine legacy zero-UUID rows
-- =============================================================================
-- Mark rows with the old zero-UUID as UNVERIFIED. They will be invisible
-- to RLS policies until manually backfilled to a valid org.

UPDATE public.aios_sessions
SET metadata = COALESCE(metadata, '{}'::jsonb) || '{"_ownership_status": "UNVERIFIED"}'::jsonb
WHERE org_id = '00000000-0000-0000-0000-000000000000'
  AND (metadata IS NULL OR NOT metadata ? '_ownership_status');

UPDATE public.aios_approvals
SET parameters = COALESCE(parameters, '{}'::jsonb) || '{"_ownership_status": "UNVERIFIED"}'::jsonb
WHERE org_id = '00000000-0000-0000-0000-000000000000'
  AND (parameters IS NULL OR NOT parameters ? '_ownership_status');

-- =============================================================================
-- PHASE 4: Add foreign key constraint on aios_decisions.session_id
-- =============================================================================
-- Currently missing — decisions reference sessions without FK integrity.

-- First, clean up any orphaned decisions that reference non-existent sessions
UPDATE public.aios_decisions
SET session_id = NULL
WHERE session_id IS NOT NULL
  AND session_id NOT IN (SELECT id FROM public.aios_sessions);

-- Add FK (nullable — decisions can be session-independent for system operations)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_aios_decisions_session'
    ) THEN
        ALTER TABLE public.aios_decisions
        ADD CONSTRAINT fk_aios_decisions_session
        FOREIGN KEY (session_id) REFERENCES public.aios_sessions(id)
        ON DELETE SET NULL;
    END IF;
END $$;

-- =============================================================================
-- PHASE 5: Indexes for tenant-scoped queries
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_aios_sessions_org_id ON public.aios_sessions(org_id);
CREATE INDEX IF NOT EXISTS ix_aios_sessions_user_id ON public.aios_sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_aios_sessions_org_created ON public.aios_sessions(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_aios_messages_org_id ON public.aios_messages(org_id);
CREATE INDEX IF NOT EXISTS ix_aios_decisions_org_id ON public.aios_decisions(org_id);
CREATE INDEX IF NOT EXISTS ix_aios_decisions_org_created ON public.aios_decisions(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_aios_approvals_org_status ON public.aios_approvals(org_id, status);

-- =============================================================================
-- PHASE 6: Drop existing policies (idempotent)
-- =============================================================================

DROP POLICY IF EXISTS aios_sessions_select_own ON public.aios_sessions;
DROP POLICY IF EXISTS aios_sessions_insert_own ON public.aios_sessions;
DROP POLICY IF EXISTS aios_sessions_update_own ON public.aios_sessions;
DROP POLICY IF EXISTS aios_sessions_delete_own ON public.aios_sessions;

DROP POLICY IF EXISTS aios_messages_select_own ON public.aios_messages;
DROP POLICY IF EXISTS aios_messages_insert_own ON public.aios_messages;
DROP POLICY IF EXISTS aios_messages_delete_own ON public.aios_messages;

DROP POLICY IF EXISTS aios_decisions_select_own ON public.aios_decisions;
DROP POLICY IF EXISTS aios_decisions_insert_own ON public.aios_decisions;

DROP POLICY IF EXISTS aios_approvals_select_own ON public.aios_approvals;
DROP POLICY IF EXISTS aios_approvals_insert_own ON public.aios_approvals;
DROP POLICY IF EXISTS aios_approvals_update_own ON public.aios_approvals;

DROP POLICY IF EXISTS aios_policies_select_own ON public.aios_policies;
DROP POLICY IF EXISTS aios_policies_upsert_own ON public.aios_policies;

-- =============================================================================
-- PHASE 7: Enable RLS
-- =============================================================================

ALTER TABLE public.aios_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aios_sessions FORCE ROW LEVEL SECURITY;

ALTER TABLE public.aios_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aios_messages FORCE ROW LEVEL SECURITY;

ALTER TABLE public.aios_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aios_decisions FORCE ROW LEVEL SECURITY;

ALTER TABLE public.aios_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aios_approvals FORCE ROW LEVEL SECURITY;

ALTER TABLE public.aios_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aios_policies FORCE ROW LEVEL SECURITY;

-- =============================================================================
-- PHASE 8: RLS Policies — aios_sessions
-- =============================================================================

-- SELECT: Members see their org's sessions. Zero-UUID rows invisible.
CREATE POLICY aios_sessions_select_own ON public.aios_sessions
    FOR SELECT TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id != '00000000-0000-0000-0000-000000000000'::uuid
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- INSERT: Authenticated users create sessions in their own org.
-- WITH CHECK ensures org_id matches JWT and user_id is set.
CREATE POLICY aios_sessions_insert_own ON public.aios_sessions
    FOR INSERT TO authenticated
    WITH CHECK (
        org_id IS NOT NULL
        AND org_id != '00000000-0000-0000-0000-000000000000'::uuid
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
        AND user_id = auth.uid()
    );

-- UPDATE: Users can update their own sessions (e.g., status, message_count).
CREATE POLICY aios_sessions_update_own ON public.aios_sessions
    FOR UPDATE TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    )
    WITH CHECK (
        org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- DELETE: Users can delete their own sessions.
CREATE POLICY aios_sessions_delete_own ON public.aios_sessions
    FOR DELETE TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
        AND user_id = auth.uid()
    );

-- =============================================================================
-- PHASE 9: RLS Policies — aios_messages
-- =============================================================================

-- SELECT: Members see messages in their org's sessions.
CREATE POLICY aios_messages_select_own ON public.aios_messages
    FOR SELECT TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- INSERT: Members add messages to their org's sessions.
CREATE POLICY aios_messages_insert_own ON public.aios_messages
    FOR INSERT TO authenticated
    WITH CHECK (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- DELETE: Cascade from session delete handles this. Direct delete by org member.
CREATE POLICY aios_messages_delete_own ON public.aios_messages
    FOR DELETE TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- =============================================================================
-- PHASE 10: RLS Policies — aios_decisions
-- =============================================================================

-- SELECT: Members see their org's decision audit trail.
CREATE POLICY aios_decisions_select_own ON public.aios_decisions
    FOR SELECT TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- INSERT: Service-role inserts decisions (bypasses RLS).
-- Authenticated users can also insert if org_id matches.
CREATE POLICY aios_decisions_insert_own ON public.aios_decisions
    FOR INSERT TO authenticated
    WITH CHECK (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- =============================================================================
-- PHASE 11: RLS Policies — aios_approvals
-- =============================================================================

-- SELECT: Members see their org's approval queue.
CREATE POLICY aios_approvals_select_own ON public.aios_approvals
    FOR SELECT TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id != '00000000-0000-0000-0000-000000000000'::uuid
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- INSERT: Service inserts approvals (via backend). Auth users can propose.
CREATE POLICY aios_approvals_insert_own ON public.aios_approvals
    FOR INSERT TO authenticated
    WITH CHECK (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- UPDATE: Admin/owner can approve/reject.
CREATE POLICY aios_approvals_update_own ON public.aios_approvals
    FOR UPDATE TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
        AND EXISTS (
            SELECT 1 FROM public.org_members
            WHERE org_members.user_id = auth.uid()
              AND org_members.org_id = aios_approvals.org_id
              AND org_members.role IN ('admin', 'owner')
              AND org_members.status = 'active'
        )
    )
    WITH CHECK (
        org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- =============================================================================
-- PHASE 12: RLS Policies — aios_policies
-- =============================================================================

-- SELECT: Members see their org's AI policies.
CREATE POLICY aios_policies_select_own ON public.aios_policies
    FOR SELECT TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id != '00000000-0000-0000-0000-000000000000'::uuid
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- INSERT/UPDATE (upsert): Admin/owner can set policies.
CREATE POLICY aios_policies_upsert_own ON public.aios_policies
    FOR ALL TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
        AND EXISTS (
            SELECT 1 FROM public.org_members
            WHERE org_members.user_id = auth.uid()
              AND org_members.org_id = aios_policies.org_id
              AND org_members.role IN ('admin', 'owner')
              AND org_members.status = 'active'
        )
    )
    WITH CHECK (
        org_id = (auth.jwt() ->> 'org_id')::uuid
    );

COMMIT;

-- =============================================================================
-- ROLLBACK PROCEDURE:
-- =============================================================================
-- BEGIN;
-- DROP POLICY IF EXISTS aios_sessions_select_own ON public.aios_sessions;
-- DROP POLICY IF EXISTS aios_sessions_insert_own ON public.aios_sessions;
-- DROP POLICY IF EXISTS aios_sessions_update_own ON public.aios_sessions;
-- DROP POLICY IF EXISTS aios_sessions_delete_own ON public.aios_sessions;
-- DROP POLICY IF EXISTS aios_messages_select_own ON public.aios_messages;
-- DROP POLICY IF EXISTS aios_messages_insert_own ON public.aios_messages;
-- DROP POLICY IF EXISTS aios_messages_delete_own ON public.aios_messages;
-- DROP POLICY IF EXISTS aios_decisions_select_own ON public.aios_decisions;
-- DROP POLICY IF EXISTS aios_decisions_insert_own ON public.aios_decisions;
-- DROP POLICY IF EXISTS aios_approvals_select_own ON public.aios_approvals;
-- DROP POLICY IF EXISTS aios_approvals_insert_own ON public.aios_approvals;
-- DROP POLICY IF EXISTS aios_approvals_update_own ON public.aios_approvals;
-- DROP POLICY IF EXISTS aios_policies_select_own ON public.aios_policies;
-- DROP POLICY IF EXISTS aios_policies_upsert_own ON public.aios_policies;
-- ALTER TABLE public.aios_sessions DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.aios_messages DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.aios_decisions DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.aios_approvals DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.aios_policies DISABLE ROW LEVEL SECURITY;
-- COMMIT;
-- =============================================================================
