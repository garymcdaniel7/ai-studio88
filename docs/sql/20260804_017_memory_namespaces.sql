-- =============================================================================
-- AI Studio: Memory Namespace Isolation (Story 040)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================
--
-- Adds namespace, scope, provenance, retention, and audience isolation to
-- brain_memory. Fixes the global UNIQUE constraint to be org-scoped.
--
-- NAMESPACES:
--   user_private   — Only the creating user can read/write
--   founder_private — Workspace founder only (never in customer sessions)
--   workspace_shared — All workspace members can read; editors+ write
--   project        — Scoped to a specific project within workspace
--   customer       — Scoped to external customer conversations
-- =============================================================================

BEGIN;

-- Phase 1: Add missing columns
ALTER TABLE public.brain_memory ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE public.brain_memory ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE public.brain_memory ADD COLUMN IF NOT EXISTS namespace TEXT DEFAULT 'workspace_shared';
ALTER TABLE public.brain_memory ADD COLUMN IF NOT EXISTS audience TEXT DEFAULT 'workspace';
ALTER TABLE public.brain_memory ADD COLUMN IF NOT EXISTS project_id UUID;
ALTER TABLE public.brain_memory ADD COLUMN IF NOT EXISTS provenance TEXT DEFAULT 'inferred';
ALTER TABLE public.brain_memory ADD COLUMN IF NOT EXISTS retention_class TEXT DEFAULT 'standard';
ALTER TABLE public.brain_memory ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE public.brain_memory ADD COLUMN IF NOT EXISTS skip_memory BOOLEAN DEFAULT FALSE;

-- Phase 2: Fix the global UNIQUE constraint → org-scoped
-- Drop the old global constraint (allows cross-tenant collision)
ALTER TABLE public.brain_memory DROP CONSTRAINT IF EXISTS brain_memory_category_key_key;
-- Create org-scoped uniqueness
CREATE UNIQUE INDEX IF NOT EXISTS uq_brain_memory_org_category_key
    ON public.brain_memory(org_id, category, key)
    WHERE org_id IS NOT NULL;

-- Phase 3: Indexes for scoped retrieval
CREATE INDEX IF NOT EXISTS ix_brain_memory_org_id ON public.brain_memory(org_id);
CREATE INDEX IF NOT EXISTS ix_brain_memory_user_id ON public.brain_memory(user_id);
CREATE INDEX IF NOT EXISTS ix_brain_memory_namespace ON public.brain_memory(namespace);
CREATE INDEX IF NOT EXISTS ix_brain_memory_org_namespace ON public.brain_memory(org_id, namespace);
CREATE INDEX IF NOT EXISTS ix_brain_memory_project ON public.brain_memory(project_id);
CREATE INDEX IF NOT EXISTS ix_brain_memory_expires ON public.brain_memory(expires_at)
    WHERE expires_at IS NOT NULL;

-- Phase 4: Quarantine legacy rows (no org_id = UNVERIFIED)
UPDATE public.brain_memory
SET source = COALESCE(source, 'user') || ':UNVERIFIED'
WHERE org_id IS NULL
  AND source NOT LIKE '%UNVERIFIED%';

-- Phase 5: RLS
ALTER TABLE public.brain_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.brain_memory FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS brain_memory_select_own ON public.brain_memory;
DROP POLICY IF EXISTS brain_memory_insert_own ON public.brain_memory;
DROP POLICY IF EXISTS brain_memory_update_own ON public.brain_memory;
DROP POLICY IF EXISTS brain_memory_delete_own ON public.brain_memory;

CREATE POLICY brain_memory_select_own ON public.brain_memory
    FOR SELECT TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
        AND (
            namespace IN ('workspace_shared', 'project')
            OR (namespace = 'user_private' AND user_id = auth.uid())
            OR (namespace = 'founder_private' AND user_id = auth.uid())
        )
    );

CREATE POLICY brain_memory_insert_own ON public.brain_memory
    FOR INSERT TO authenticated
    WITH CHECK (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    );

CREATE POLICY brain_memory_update_own ON public.brain_memory
    FOR UPDATE TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
        AND (
            namespace IN ('workspace_shared', 'project')
            OR user_id = auth.uid()
        )
    )
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY brain_memory_delete_own ON public.brain_memory
    FOR DELETE TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
        AND (
            namespace IN ('workspace_shared', 'project')
            OR user_id = auth.uid()
        )
    );

COMMIT;
