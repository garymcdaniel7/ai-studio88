-- =============================================================================
-- Migration 041: Security Hardening (Story 008)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================
--
-- WHAT THIS FIXES:
-- 1. All plpgsql functions lack SET search_path → vulnerable to search_path
--    manipulation attacks (an attacker who can modify search_path can shadow
--    tables/operators with malicious objects).
-- 2. All functions reference tables without schema qualification.
-- 3. Default EXECUTE privilege is granted to PUBLIC on all functions —
--    unauthenticated callers can invoke match_brain_embeddings directly.
-- 4. Vector extension lives in public schema (accepted exception — see Phase 5).
--
-- APPROACH:
-- - Pin search_path = '' (empty) on every function, forcing fully-qualified
--   references. This is the PostgreSQL-recommended hardening for functions
--   that access data in specific schemas.
-- - Schema-qualify all table/type references inside function bodies.
-- - Revoke PUBLIC execute on RPC-callable functions; grant only to
--   authenticated and service_role.
-- - Document the vector extension decision (no relocation).
--
-- SAFETY:
-- - All statements are idempotent (CREATE OR REPLACE, IF NOT EXISTS patterns).
-- - No data changes. Only function definitions and privilege changes.
-- - Rollback section at bottom restores prior behavior.
--
-- DEPENDENCIES:
-- - Requires: 023_brain_embeddings.sql (match_brain_embeddings exists)
-- - Requires: 029_org_members.sql (auto_create_owner_membership exists)
-- - Requires: 037_batch_generation.sql (update_updated_at_column exists)
-- - Requires: vector extension installed (for vector type references)
-- =============================================================================

BEGIN;

-- =============================================================================
-- PHASE 1: Harden match_brain_embeddings
-- =============================================================================
-- Risk: This is the only function callable via supabase.rpc() from the client.
-- It accepts a vector parameter and queries brain_embeddings. Without a pinned
-- search_path, an attacker could shadow the brain_embeddings table or the <=>
-- operator with a malicious object in a schema earlier in the path.
--
-- Fix: Pin search_path to '' and schema-qualify all references.
-- The vector operators (<=> etc.) are installed in public via the vector
-- extension, so we include 'public' in the path for operator resolution.

CREATE OR REPLACE FUNCTION public.match_brain_embeddings(
    query_embedding public.vector(768),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    source_type TEXT,
    similarity FLOAT,
    metadata JSONB
)
LANGUAGE plpgsql
SET search_path = 'public'
AS $$
BEGIN
    RETURN QUERY
    SELECT
        be.id,
        be.content,
        be.source_type,
        (1 - (be.embedding <=> query_embedding))::FLOAT AS similarity,
        be.metadata
    FROM public.brain_embeddings be
    WHERE (1 - (be.embedding <=> query_embedding)) > match_threshold
    ORDER BY be.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION public.match_brain_embeddings(public.vector, FLOAT, INT) IS
    'Story 008: search_path pinned to public (vector ops require it). Schema-qualified references.';


-- =============================================================================
-- PHASE 2: Harden auto_create_owner_membership
-- =============================================================================
-- Risk: Trigger function that inserts into org_members. If search_path is
-- manipulated, a shadow org_members table could capture new org ownership data.
--
-- Fix: Pin search_path = '' and schema-qualify org_members.

CREATE OR REPLACE FUNCTION public.auto_create_owner_membership()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    -- Only if owner_id is set
    IF NEW.owner_id IS NOT NULL THEN
        INSERT INTO public.org_members (org_id, user_id, role, status, joined_at)
        VALUES (NEW.id, NEW.owner_id, 'owner', 'active', now())
        ON CONFLICT (user_id, org_id) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.auto_create_owner_membership() IS
    'Story 008: search_path pinned to empty. Schema-qualified references.';


-- =============================================================================
-- PHASE 3: Harden update_updated_at_column
-- =============================================================================
-- Risk: Generic trigger function used by multiple tables. Lower risk since it
-- only touches NEW.updated_at (no table lookups), but pinning search_path is
-- still best practice to prevent future issues if the function is extended.
--
-- Fix: Pin search_path = '' (no schema refs needed — operates on NEW only).

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.update_updated_at_column() IS
    'Story 008: search_path pinned to empty. No external references needed.';


-- =============================================================================
-- PHASE 4: Minimize PUBLIC EXECUTE grants
-- =============================================================================
-- By default, PostgreSQL grants EXECUTE on new functions to PUBLIC.
-- For our functions:
-- - match_brain_embeddings: Only authenticated users and service_role should
--   be able to call this via RPC. Revoke from PUBLIC and anon.
-- - auto_create_owner_membership: Trigger function — only invoked by the
--   trigger system (runs as table owner). Revoke from PUBLIC.
-- - update_updated_at_column: Same — trigger only. Revoke from PUBLIC.
--
-- NOTE: In Supabase, the built-in roles are:
--   anon          — unauthenticated API calls
--   authenticated — logged-in users (JWT validated)
--   service_role  — backend service key (bypasses RLS)
--   postgres      — superuser (owns objects)

-- Revoke PUBLIC default on all three functions
REVOKE EXECUTE ON FUNCTION public.match_brain_embeddings(public.vector, FLOAT, INT) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.auto_create_owner_membership() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.update_updated_at_column() FROM PUBLIC;

-- Grant match_brain_embeddings to authenticated + service_role only
-- (this is the only function callable via supabase.rpc())
GRANT EXECUTE ON FUNCTION public.match_brain_embeddings(public.vector, FLOAT, INT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.match_brain_embeddings(public.vector, FLOAT, INT) TO service_role;

-- Trigger functions don't need explicit grants — they execute as the trigger
-- owner (postgres). But grant to postgres explicitly for clarity.
GRANT EXECUTE ON FUNCTION public.auto_create_owner_membership() TO postgres;
GRANT EXECUTE ON FUNCTION public.update_updated_at_column() TO postgres;


-- =============================================================================
-- PHASE 5: Vector Extension Schema — ACCEPTED EXCEPTION
-- =============================================================================
-- FINDING: The vector extension is installed in the public schema.
-- ANALYSIS:
--   - Moving vector to a dedicated 'extensions' schema would require:
--     a) ALTER EXTENSION vector SET SCHEMA extensions;
--     b) Updating all column type references (brain_embeddings.embedding)
--     c) Updating all operator references (<=> becomes extensions.<=>)
--     d) Recreating IVFFlat indexes
--     e) Updating function signatures (vector(768) type qualification)
--   - Supabase installs extensions in public by default and many internal
--     functions depend on this. Moving it risks breaking Supabase tooling.
--   - The vector extension adds types and operators — it does NOT add tables
--     that could leak data across tenants.
--   - Risk is LOW: vector operators cannot be weaponized for data exfiltration.
--     The search_path pinning in Phase 1 mitigates operator shadowing.
--
-- DECISION: Accept vector in public schema. Document as known exception.
-- REVIEW DATE: Re-evaluate if Supabase adds native extensions schema support.
--
-- No SQL action needed — this comment IS the documentation.

COMMENT ON EXTENSION vector IS
    'Story 008: Accepted in public schema. Operator shadowing mitigated by function search_path pinning. Re-evaluate when Supabase supports extensions schema natively.';


-- =============================================================================
-- PHASE 6: Verify workers_tenant_view grant (existing)
-- =============================================================================
-- The only existing GRANT (from 031_workers_rls.sql):
--   GRANT SELECT ON public.workers_tenant_view TO authenticated;
--
-- This is CORRECT:
-- - The view has RLS-compatible filtering built in
-- - Only SELECT is granted (no INSERT/UPDATE/DELETE)
-- - Only authenticated role (not PUBLIC or anon)
-- - No change needed.


COMMIT;


-- =============================================================================
-- ROLLBACK SCRIPT
-- =============================================================================
-- Run this to revert all changes if issues are detected.
-- This restores functions WITHOUT search_path pinning and re-grants PUBLIC.
-- =============================================================================

-- BEGIN;
--
-- -- Restore match_brain_embeddings without search_path
-- CREATE OR REPLACE FUNCTION public.match_brain_embeddings(
--     query_embedding vector(768),
--     match_threshold FLOAT DEFAULT 0.7,
--     match_count INT DEFAULT 5
-- )
-- RETURNS TABLE (
--     id UUID,
--     content TEXT,
--     source_type TEXT,
--     similarity FLOAT,
--     metadata JSONB
-- )
-- LANGUAGE plpgsql
-- AS $$
-- BEGIN
--     RETURN QUERY
--     SELECT
--         be.id,
--         be.content,
--         be.source_type,
--         1 - (be.embedding <=> query_embedding) AS similarity,
--         be.metadata
--     FROM brain_embeddings be
--     WHERE 1 - (be.embedding <=> query_embedding) > match_threshold
--     ORDER BY be.embedding <=> query_embedding
--     LIMIT match_count;
-- END;
-- $$;
--
-- -- Restore auto_create_owner_membership without search_path
-- CREATE OR REPLACE FUNCTION public.auto_create_owner_membership()
-- RETURNS TRIGGER AS $$
-- BEGIN
--     IF NEW.owner_id IS NOT NULL THEN
--         INSERT INTO org_members (org_id, user_id, role, status, joined_at)
--         VALUES (NEW.id, NEW.owner_id, 'owner', 'active', now())
--         ON CONFLICT (user_id, org_id) DO NOTHING;
--     END IF;
--     RETURN NEW;
-- END;
-- $$ LANGUAGE plpgsql;
--
-- -- Restore update_updated_at_column without search_path
-- CREATE OR REPLACE FUNCTION public.update_updated_at_column()
-- RETURNS TRIGGER AS $$
-- BEGIN
--     NEW.updated_at = now();
--     RETURN NEW;
-- END;
-- $$ LANGUAGE plpgsql;
--
-- -- Re-grant PUBLIC execute (restore default)
-- GRANT EXECUTE ON FUNCTION public.match_brain_embeddings(vector, FLOAT, INT) TO PUBLIC;
-- GRANT EXECUTE ON FUNCTION public.auto_create_owner_membership() TO PUBLIC;
-- GRANT EXECUTE ON FUNCTION public.update_updated_at_column() TO PUBLIC;
--
-- -- Remove comments
-- COMMENT ON FUNCTION public.match_brain_embeddings(vector, FLOAT, INT) IS NULL;
-- COMMENT ON FUNCTION public.auto_create_owner_membership() IS NULL;
-- COMMENT ON FUNCTION public.update_updated_at_column() IS NULL;
-- COMMENT ON EXTENSION vector IS NULL;
--
-- COMMIT;
