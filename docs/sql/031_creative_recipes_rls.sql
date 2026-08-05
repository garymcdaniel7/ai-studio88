-- =============================================================================
-- AI Studio: Creative Recipes — Operation-Specific RLS (Story 013)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================
--
-- Replaces the broad FOR ALL policy with explicit per-operation rules:
--   SELECT: public recipes readable by all authenticated users + own org
--   INSERT: only into own org, cannot create public recipes
--   UPDATE: only own org's recipes, cannot change org_id or escalate is_public
--   DELETE: only own org's recipes, cannot delete public/system recipes
--
-- System/public recipe writes require service-role (backend Story 009 boundary).
--
-- Also fixes seeded data: migrates zero-UUID org_id to system org ('...001').
-- =============================================================================


-- =============================================================================
-- PHASE 1: Fix legacy seeded data — zero-UUID → system org
-- =============================================================================
-- The original seed used '00000000-0000-0000-0000-000000000000' (zero-UUID).
-- The canonical system org is '00000000-0000-0000-0000-000000000001' (Story 005).

UPDATE creative_recipes
SET org_id = '00000000-0000-0000-0000-000000000001'::uuid
WHERE org_id = '00000000-0000-0000-0000-000000000000'::uuid;


-- =============================================================================
-- PHASE 2: Drop the broad FOR ALL policy
-- =============================================================================

DROP POLICY IF EXISTS "recipe_org_isolation" ON creative_recipes;

-- Also drop Story 030 policy if it was applied (from the general RLS sweep)
DROP POLICY IF EXISTS "creative_recipes_org_isolation" ON creative_recipes;


-- =============================================================================
-- PHASE 3: Create operation-specific policies
-- =============================================================================

-- ---------------------------------------------------------------------------
-- SELECT: Authenticated users can read:
--   1. Public recipes (is_public = true) — regardless of org
--   2. Their own org's recipes (public or private)
-- ---------------------------------------------------------------------------
CREATE POLICY "recipes_select"
    ON creative_recipes
    FOR SELECT
    USING (
        is_public = true
        OR org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid()
            AND om.status = 'active'
        )
    );

-- ---------------------------------------------------------------------------
-- INSERT: Users can only create recipes in their own org.
--   - org_id must match their active membership
--   - is_public must be false (only system/admin can make recipes public)
--   - created_by must be 'user' or 'ai_learned' (not 'system')
-- ---------------------------------------------------------------------------
CREATE POLICY "recipes_insert"
    ON creative_recipes
    FOR INSERT
    WITH CHECK (
        -- Must belong to user's org
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid()
            AND om.status = 'active'
        )
        -- Cannot self-publish as public (requires admin/system action)
        AND is_public = false
        -- Cannot claim system authorship
        AND created_by != 'system'
    );

-- ---------------------------------------------------------------------------
-- UPDATE: Users can only update recipes they own (via org membership).
--   - Cannot change org_id (ownership is immutable)
--   - Cannot set is_public = true (escalation blocked)
--   - Cannot modify system recipes (created_by = 'system')
--
-- USING: which rows the user can see for update (existing row filter)
-- WITH CHECK: what the row must look like AFTER the update (new values filter)
-- ---------------------------------------------------------------------------
CREATE POLICY "recipes_update"
    ON creative_recipes
    FOR UPDATE
    USING (
        -- Can only target rows in own org
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid()
            AND om.status = 'active'
        )
        -- Cannot modify system recipes via client
        AND created_by != 'system'
    )
    WITH CHECK (
        -- After update, org_id must still match (no ownership transfer)
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid()
            AND om.status = 'active'
        )
        -- Cannot escalate to public via update
        AND is_public = false
        -- Cannot claim system authorship via update
        AND created_by != 'system'
    );

-- ---------------------------------------------------------------------------
-- DELETE: Users can only delete recipes they own.
--   - Cannot delete public recipes (even in own org — requires admin)
--   - Cannot delete system recipes
-- ---------------------------------------------------------------------------
CREATE POLICY "recipes_delete"
    ON creative_recipes
    FOR DELETE
    USING (
        -- Must be in user's org
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid()
            AND om.status = 'active'
        )
        -- Cannot delete public recipes via client (requires service-role/admin)
        AND is_public = false
        -- Cannot delete system recipes
        AND created_by != 'system'
    );


-- =============================================================================
-- PHASE 4: Verify RLS is enabled (idempotent)
-- =============================================================================

ALTER TABLE creative_recipes ENABLE ROW LEVEL SECURITY;


-- =============================================================================
-- NOTES
-- =============================================================================
-- 
-- ACCESS MATRIX:
--
-- | Actor              | SELECT public | SELECT own org | INSERT own | UPDATE own | DELETE own | Write public/system |
-- |--------------------|:---:|:---:|:---:|:---:|:---:|:---:|
-- | Authenticated user | ✅ | ✅ | ✅ (private only) | ✅ (private only) | ✅ (private only) | ❌ |
-- | Other org user     | ✅ (public only) | ❌ | ❌ | ❌ | ❌ | ❌ |
-- | Anonymous          | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
-- | Service-role       | ✅ (bypasses RLS) | ✅ | ✅ | ✅ | ✅ | ✅ (via AuthorizedClient) |
--
-- IMMUTABILITY RULES:
-- - org_id cannot be changed by client users (WITH CHECK enforces same org)
-- - is_public cannot be set to true by client users (WITH CHECK blocks)
-- - created_by = 'system' rows cannot be modified or deleted by client users
-- - Public flag can only be toggled via service-role (admin action)
--
-- SYSTEM/PUBLIC RECIPE UPDATES:
-- Handled by backend service-role via AuthorizedClient with SystemContext.
-- The RLS policies don't apply to service-role — Story 009 boundary enforces
-- that only authorized system operations can modify public/system recipes.
--
-- ROLLBACK:
-- DROP POLICY IF EXISTS "recipes_select" ON creative_recipes;
-- DROP POLICY IF EXISTS "recipes_insert" ON creative_recipes;
-- DROP POLICY IF EXISTS "recipes_update" ON creative_recipes;
-- DROP POLICY IF EXISTS "recipes_delete" ON creative_recipes;
-- CREATE POLICY "recipe_org_isolation" ON creative_recipes FOR ALL
--     USING (org_id = (auth.jwt() ->> 'org_id')::uuid OR is_public = true);
