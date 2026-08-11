-- =============================================================================
-- Migration 20260808_012: Vector Extension Security
-- =============================================================================
--
-- !! MANUAL REVIEW REQUIRED — DO NOT APPLY AUTOMATICALLY !!
--
-- This migration moves the pgvector extension from the public schema to the
-- extensions schema and fixes the match_brain_embeddings function to use an
-- immutable search_path that includes the extensions schema.
--
-- WHY:
-- 1. Extensions in the public schema can pollute the namespace and create
--    operator/type shadowing risks. Supabase best practice is to install
--    extensions in a dedicated "extensions" schema.
-- 2. The match_brain_embeddings function (hardened in 20260806_006) currently
--    has `SET search_path = 'public'` which is correct only while vector lives
--    in public. After moving vector to extensions, the function needs access
--    to both schemas.
-- 3. Leaked-password protection (R5.12) is a Supabase Dashboard configuration
--    change, documented below but NOT a SQL operation.
--
-- RISK ASSESSMENT:
-- Moving the vector extension changes where the vector type, operators (<=>),
-- and operator classes (vector_cosine_ops) live. This WILL affect:
--   a) Column type resolution for brain_embeddings.embedding (vector(768))
--   b) Operator resolution for <=> in queries
--   c) IVFFlat index using vector_cosine_ops
--   d) Function signatures referencing vector(768)
--   e) Any application code using unqualified vector type references
--
-- VERIFICATION STEPS BEFORE APPLYING:
-- 1. Verify the extensions schema exists:
--      SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'extensions';
-- 2. Verify vector is currently in public:
--      SELECT extnamespace::regnamespace FROM pg_extension WHERE extname = 'vector';
-- 3. After applying, verify vector moved:
--      SELECT extnamespace::regnamespace FROM pg_extension WHERE extname = 'vector';
--      -- Should return 'extensions'
-- 4. Test match_brain_embeddings still works:
--      SELECT * FROM match_brain_embeddings(
--          (SELECT embedding FROM brain_embeddings LIMIT 1),
--          0.5, 3
--      );
-- 5. Verify IVFFlat index still functions:
--      EXPLAIN ANALYZE SELECT * FROM brain_embeddings
--      ORDER BY embedding <=> (SELECT embedding FROM brain_embeddings LIMIT 1)
--      LIMIT 5;
--
-- ROLLBACK PLAN:
-- If issues arise after applying:
--   ALTER EXTENSION vector SET SCHEMA public;
--   -- Then re-run 20260806_006_security_hardening.sql to restore function
--   -- with search_path = 'public' only.
--
-- DEPENDENCIES:
-- - Requires: extensions schema exists (Supabase creates this by default)
-- - Requires: 20260711_003_brain_embeddings.sql (vector extension + table)
-- - Requires: 20260806_006_security_hardening.sql (function search_path pinning)
-- - Supersedes: Phase 5 "Accepted Exception" in 20260806_006 (vector in public)
--
-- REQUIREMENTS COVERED: R5.11, R5.12, R6.8
-- =============================================================================

BEGIN;

-- =============================================================================
-- STEP 1: Ensure extensions schema exists
-- =============================================================================
-- Supabase projects create this schema by default, but verify to be safe.
CREATE SCHEMA IF NOT EXISTS extensions;

-- =============================================================================
-- STEP 2: Move vector extension from public to extensions schema
-- =============================================================================
-- This relocates all vector types, operators, and operator classes to the
-- extensions schema. Existing columns (brain_embeddings.embedding) retain
-- their data — only the schema location of the type definition changes.
--
-- NOTE: After this, unqualified references to vector(768) will only resolve
-- if search_path includes 'extensions'.

ALTER EXTENSION vector SET SCHEMA extensions;

-- =============================================================================
-- STEP 3: Fix match_brain_embeddings search_path
-- =============================================================================
-- The function previously had SET search_path = 'public' (from 20260806_006).
-- Now that vector lives in extensions, the function needs access to both
-- schemas: extensions (for vector type and operators) and public (for
-- brain_embeddings table).
--
-- Using SET search_path = 'extensions, public' ensures:
-- - vector(768) type resolves from extensions
-- - <=> operator resolves from extensions
-- - brain_embeddings table resolves from public
-- - The search_path is IMMUTABLE (set at function creation, not inherited
--   from caller) which prevents search_path injection attacks.

CREATE OR REPLACE FUNCTION public.match_brain_embeddings(
    query_embedding extensions.vector(768),
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
SET search_path = 'extensions, public'
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

COMMENT ON FUNCTION public.match_brain_embeddings(extensions.vector, FLOAT, INT) IS
    'Migration 012: search_path set to extensions,public (immutable). Vector extension relocated to extensions schema.';

-- =============================================================================
-- STEP 4: Preserve EXECUTE grants (from 20260806_006)
-- =============================================================================
-- The CREATE OR REPLACE resets grants, so re-apply the restricted grants.
REVOKE EXECUTE ON FUNCTION public.match_brain_embeddings(extensions.vector, FLOAT, INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.match_brain_embeddings(extensions.vector, FLOAT, INT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.match_brain_embeddings(extensions.vector, FLOAT, INT) TO service_role;

COMMIT;


-- =============================================================================
-- STEP 5: Leaked-Password Protection (NON-SQL — Dashboard Configuration)
-- =============================================================================
-- This is NOT a SQL migration. It is a Supabase Auth configuration change.
-- See docs/sql/20260806_007_leaked_password_protection.sql for full details.
--
-- SUMMARY:
-- 1. Go to: Supabase Dashboard -> Authentication -> Providers -> Email
-- 2. Under "Password Protection", enable "Leaked password protection"
-- 3. Set action to "Block" (or "Warn" initially for monitoring)
-- 4. Save changes
--
-- Alternatively, use the Management API:
--   curl -X PATCH "https://api.supabase.com/v1/projects/{project_ref}/config/auth" \
--     -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
--     -H "Content-Type: application/json" \
--     -d '{"security": {"leaked_password_protection": {"enabled": true, "mode": "block"}}}'
--
-- This satisfies R5.12 (enable leaked-password protection).


-- =============================================================================
-- ROLLBACK SCRIPT
-- =============================================================================
-- Run this to revert all changes if issues arise.
-- =============================================================================

-- BEGIN;
--
-- -- Move vector extension back to public schema
-- ALTER EXTENSION vector SET SCHEMA public;
--
-- -- Restore match_brain_embeddings with search_path = 'public' only
-- CREATE OR REPLACE FUNCTION public.match_brain_embeddings(
--     query_embedding public.vector(768),
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
-- SET search_path = 'public'
-- AS $$
-- BEGIN
--     RETURN QUERY
--     SELECT
--         be.id,
--         be.content,
--         be.source_type,
--         (1 - (be.embedding <=> query_embedding))::FLOAT AS similarity,
--         be.metadata
--     FROM public.brain_embeddings be
--     WHERE (1 - (be.embedding <=> query_embedding)) > match_threshold
--     ORDER BY be.embedding <=> query_embedding
--     LIMIT match_count;
-- END;
-- $$;
--
-- -- Restore grants
-- REVOKE EXECUTE ON FUNCTION public.match_brain_embeddings(public.vector, FLOAT, INT) FROM PUBLIC;
-- GRANT EXECUTE ON FUNCTION public.match_brain_embeddings(public.vector, FLOAT, INT) TO authenticated;
-- GRANT EXECUTE ON FUNCTION public.match_brain_embeddings(public.vector, FLOAT, INT) TO service_role;
--
-- COMMENT ON FUNCTION public.match_brain_embeddings(public.vector, FLOAT, INT) IS
--     'Rolled back: vector extension returned to public schema.';
--
-- COMMIT;
