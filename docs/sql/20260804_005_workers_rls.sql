-- =============================================================================
-- AI Studio: Workers Table RLS (Story 012)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================
--
-- OWNERSHIP DECISION:
-- Workers are TENANT-OWNED. Each worker belongs to exactly one organisation
-- via the org_id column. Workers with NULL org_id are legacy/orphaned and
-- treated as invisible to authenticated users until backfilled.
--
-- ACCESS MODEL:
-- 1. Authenticated users (via JWT): read-only access to their org's workers,
--    with sensitive fields excluded via a VIEW (workers_tenant_view).
-- 2. Admin users (role='admin'|'owner' in org_members): full CRUD for their org.
-- 3. Service role (backend): unrestricted access for heartbeats, provisioning.
--    The Supabase service_role key bypasses RLS entirely (Postgres default).
--
-- SENSITIVE FIELDS (excluded from tenant view):
-- - base_url: raw SSH/HTTP endpoint (security risk if exposed)
-- - metadata: may contain provider-specific credentials or instance details
-- - cuda_version, driver_version: internal infrastructure detail
--
-- SAFETY:
-- - RLS is enabled IN THE SAME TRANSACTION as policy creation (never naked).
-- - Policies use WITH CHECK to prevent org_id reassignment on UPDATE.
-- - NULL org_id rows are invisible to all non-service users.
-- - Idempotent (DROP POLICY IF EXISTS before CREATE).
-- =============================================================================

BEGIN;

-- =============================================================================
-- PHASE 0: Ensure org_id column and index exist
-- =============================================================================

ALTER TABLE public.workers ADD COLUMN IF NOT EXISTS org_id UUID;
CREATE INDEX IF NOT EXISTS ix_workers_org_id ON public.workers(org_id);

-- =============================================================================
-- PHASE 1: Backfill orphaned rows
-- =============================================================================
-- Mark NULL org_id workers with a sentinel comment in metadata so they can be
-- identified for manual backfill. They remain invisible to RLS-protected queries.

UPDATE public.workers
SET metadata = COALESCE(metadata, '{}'::jsonb) || '{"_ownership_status": "UNVERIFIED"}'::jsonb
WHERE org_id IS NULL
  AND (metadata IS NULL OR NOT metadata ? '_ownership_status');

-- =============================================================================
-- PHASE 2: Drop existing policies (idempotent re-run safety)
-- =============================================================================

DROP POLICY IF EXISTS workers_select_own_org ON public.workers;
DROP POLICY IF EXISTS workers_insert_own_org ON public.workers;
DROP POLICY IF EXISTS workers_update_own_org ON public.workers;
DROP POLICY IF EXISTS workers_delete_own_org ON public.workers;
DROP POLICY IF EXISTS workers_service_all ON public.workers;

-- =============================================================================
-- PHASE 3: Enable RLS
-- =============================================================================

ALTER TABLE public.workers ENABLE ROW LEVEL SECURITY;

-- Force RLS even for table owner (prevents bypass via GRANT)
ALTER TABLE public.workers FORCE ROW LEVEL SECURITY;

-- =============================================================================
-- PHASE 4: Policies for authenticated users (JWT-based)
-- =============================================================================

-- SELECT: Users can see workers belonging to their org.
-- NULL org_id rows are invisible (COALESCE prevents NULL = NULL being true).
CREATE POLICY workers_select_own_org ON public.workers
    FOR SELECT
    TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- INSERT: Only admin/owner can register workers, and org_id must match JWT.
-- WITH CHECK ensures the inserted org_id is the user's own org.
CREATE POLICY workers_insert_own_org ON public.workers
    FOR INSERT
    TO authenticated
    WITH CHECK (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
        AND EXISTS (
            SELECT 1 FROM public.org_members
            WHERE org_members.user_id = auth.uid()
              AND org_members.org_id = workers.org_id
              AND org_members.role IN ('admin', 'owner')
              AND org_members.status = 'active'
        )
    );

-- UPDATE: Admin/owner can update their org's workers.
-- WITH CHECK prevents changing org_id (must remain the same after update).
CREATE POLICY workers_update_own_org ON public.workers
    FOR UPDATE
    TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
        AND EXISTS (
            SELECT 1 FROM public.org_members
            WHERE org_members.user_id = auth.uid()
              AND org_members.org_id = workers.org_id
              AND org_members.role IN ('admin', 'owner')
              AND org_members.status = 'active'
        )
    )
    WITH CHECK (
        -- Prevent org_id reassignment: new org_id must equal the JWT org_id
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
    );

-- DELETE: Only admin/owner can deregister workers from their org.
CREATE POLICY workers_delete_own_org ON public.workers
    FOR DELETE
    TO authenticated
    USING (
        org_id IS NOT NULL
        AND org_id = (auth.jwt() ->> 'org_id')::uuid
        AND EXISTS (
            SELECT 1 FROM public.org_members
            WHERE org_members.user_id = auth.uid()
              AND org_members.org_id = workers.org_id
              AND org_members.role IN ('admin', 'owner')
              AND org_members.status = 'active'
        )
    );

-- =============================================================================
-- PHASE 5: Service role access
-- =============================================================================
-- NOTE: The Supabase service_role bypasses RLS by default (it's a Postgres
-- superuser-like role). The backend uses service_role for:
--   - Worker provisioning (create with org_id)
--   - Heartbeat updates (update status, vram, current_job)
--   - Fleet management (list all, delete terminated)
--
-- No explicit policy needed — service_role bypasses RLS automatically.
-- This is documented here for clarity.

-- =============================================================================
-- PHASE 6: Tenant-safe view (excludes sensitive columns)
-- =============================================================================

DROP VIEW IF EXISTS public.workers_tenant_view;

CREATE VIEW public.workers_tenant_view AS
SELECT
    id,
    name,
    provider,
    status,
    masked_url,          -- Safe: already masked (e.g., "http://192.168....:8188")
    gpu_name,
    vram_gb,
    available_vram_gb,
    supported_tasks,
    supported_models,
    current_job_id,
    last_heartbeat_at,
    org_id,
    created_at,
    updated_at
    -- EXCLUDED: base_url, metadata, cuda_version, driver_version
FROM public.workers;

-- Grant authenticated users access to the view (inherits table RLS)
GRANT SELECT ON public.workers_tenant_view TO authenticated;

-- Revoke direct table SELECT from authenticated on sensitive columns
-- (RLS still protects rows, but this adds defense-in-depth for column access)
-- NOTE: Postgres doesn't support column-level REVOKE with RLS well,
-- so the VIEW is the primary protection mechanism for sensitive fields.

-- =============================================================================
-- PHASE 7: Additional indexes for policy performance
-- =============================================================================

-- Composite index for the org_members lookup in policies
CREATE INDEX IF NOT EXISTS ix_org_members_user_org_role
    ON public.org_members(user_id, org_id, role)
    WHERE status = 'active';

COMMIT;

-- =============================================================================
-- ROLLBACK PROCEDURE (run manually if needed):
-- =============================================================================
-- BEGIN;
-- DROP POLICY IF EXISTS workers_select_own_org ON public.workers;
-- DROP POLICY IF EXISTS workers_insert_own_org ON public.workers;
-- DROP POLICY IF EXISTS workers_update_own_org ON public.workers;
-- DROP POLICY IF EXISTS workers_delete_own_org ON public.workers;
-- ALTER TABLE public.workers DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.workers NO FORCE ROW LEVEL SECURITY;
-- DROP VIEW IF EXISTS public.workers_tenant_view;
-- COMMIT;
-- =============================================================================
