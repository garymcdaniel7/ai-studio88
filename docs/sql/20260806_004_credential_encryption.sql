-- =============================================================================
-- Migration 041: Credential Encryption & Plaintext Removal
-- Story 007 — Secure Credential Storage
-- =============================================================================
--
-- STATUS: TEMPLATE — DO NOT APPLY until Stories 004-006 are approved.
--
-- Problem:
--   social_connections stores access_token and refresh_token as plaintext TEXT.
--   The RLS policy uses USING(true) — allows any authenticated user to read
--   any row regardless of org_id.
--
-- Solution:
--   1. Replace wildcard RLS policy with proper org_id isolation
--   2. Migrate plaintext tokens to encrypted_* columns
--   3. Drop plaintext columns after migration verification
--   4. Fix the UNIQUE constraint (platform should be unique per org, not globally)
--
-- Migration strategy (3-phase):
--   Phase A: Add encrypted columns + new RLS (non-breaking)
--   Phase B: Backend migrates tokens to encrypted columns (app code change)
--   Phase C: Drop plaintext columns after verification period
--
-- =============================================================================

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE A: Add encrypted columns and fix RLS (non-breaking)
-- ─────────────────────────────────────────────────────────────────────────────

-- A1: Add encrypted columns alongside plaintext (allows gradual migration)
ALTER TABLE social_connections
    ADD COLUMN IF NOT EXISTS encrypted_access_token TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS encrypted_refresh_token TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS encryption_version INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS token_encrypted_at TIMESTAMPTZ;

-- A2: Drop the dangerous wildcard RLS policy
DROP POLICY IF EXISTS "social_connections_all" ON social_connections;

-- A3: Create proper org_id-scoped policies
CREATE POLICY social_connections_select_own_org ON social_connections
    FOR SELECT USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY social_connections_insert_own_org ON social_connections
    FOR INSERT WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY social_connections_update_own_org ON social_connections
    FOR UPDATE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

CREATE POLICY social_connections_delete_own_org ON social_connections
    FOR DELETE USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

-- A4: Fix the UNIQUE constraint — platform should be unique per org, not globally
-- Drop the global unique and create per-org unique
ALTER TABLE social_connections DROP CONSTRAINT IF EXISTS social_connections_platform_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_social_connections_org_platform
    ON social_connections(org_id, platform);

-- A5: Create a view that NEVER exposes token columns to client queries
-- (Defense-in-depth: even if RLS is bypassed, the view hides secrets)
CREATE OR REPLACE VIEW social_connections_safe AS
SELECT
    id,
    org_id,
    platform,
    status,
    token_type,
    expires_at,
    scope,
    metadata,
    created_at,
    updated_at,
    CASE WHEN encrypted_access_token != '' THEN 'encrypted'
         WHEN access_token != '' THEN 'plaintext'
         ELSE 'none'
    END AS token_state,
    encryption_version
FROM social_connections;

-- A6: Revoke direct SELECT on token columns from anon and authenticated roles
-- (Only service_role can read token columns directly)
REVOKE SELECT (access_token, refresh_token, encrypted_access_token, encrypted_refresh_token)
    ON social_connections FROM anon;
REVOKE SELECT (access_token, refresh_token, encrypted_access_token, encrypted_refresh_token)
    ON social_connections FROM authenticated;

-- Grant safe columns to authenticated
GRANT SELECT (id, org_id, platform, status, token_type, expires_at, scope, metadata, created_at, updated_at, encryption_version)
    ON social_connections TO authenticated;

COMMIT;


-- =============================================================================
-- PHASE B: Token Migration (run by backend application code)
-- =============================================================================
-- This phase is NOT a SQL migration — it's an application task:
--
-- 1. Query all rows where access_token != '' AND encrypted_access_token = ''
-- 2. For each row:
--    a. Encrypt access_token using CredentialService._encrypt()
--    b. Encrypt refresh_token using CredentialService._encrypt()
--    c. UPDATE encrypted_access_token, encrypted_refresh_token, encryption_version=1
-- 3. Verify: count(encrypted_access_token != '') == count(access_token != '')
--
-- Application code (backend/scripts/migrate_social_tokens.py):
--
-- async def migrate_tokens():
--     """One-time migration: plaintext → encrypted."""
--     from backend.credentials import _encrypt
--     rows = await db.fetch("SELECT id, access_token, refresh_token FROM social_connections WHERE access_token != '' AND encrypted_access_token = ''")
--     for row in rows:
--         enc_access = _encrypt(row['access_token'])
--         enc_refresh = _encrypt(row['refresh_token']) if row['refresh_token'] else ''
--         await db.execute(
--             "UPDATE social_connections SET encrypted_access_token=$1, encrypted_refresh_token=$2, encryption_version=1, token_encrypted_at=now() WHERE id=$3",
--             enc_access, enc_refresh, row['id']
--         )
--     logger.info(f"Migrated {len(rows)} social connection tokens to encrypted storage")


-- =============================================================================
-- PHASE C: Drop plaintext columns (run AFTER Phase B verification)
-- =============================================================================
-- ONLY run after confirming:
--   1. All rows have encryption_version >= 1
--   2. Backend code no longer reads access_token/refresh_token directly
--   3. Token refresh flow uses encrypted columns
--
-- BEGIN;
--
-- -- Verify no un-migrated rows remain
-- DO $$
-- BEGIN
--     IF EXISTS (
--         SELECT 1 FROM social_connections
--         WHERE access_token != '' AND encrypted_access_token = ''
--     ) THEN
--         RAISE EXCEPTION 'Un-migrated plaintext tokens exist — cannot drop columns';
--     END IF;
-- END $$;
--
-- -- Drop plaintext columns
-- ALTER TABLE social_connections DROP COLUMN IF EXISTS access_token;
-- ALTER TABLE social_connections DROP COLUMN IF EXISTS refresh_token;
--
-- -- Update the safe view
-- CREATE OR REPLACE VIEW social_connections_safe AS
-- SELECT
--     id, org_id, platform, status, token_type, expires_at,
--     scope, metadata, created_at, updated_at,
--     'encrypted' AS token_state,
--     encryption_version
-- FROM social_connections;
--
-- COMMIT;


-- =============================================================================
-- ROLLBACK (Phase A only)
-- =============================================================================
-- BEGIN;
--
-- -- Restore wildcard policy (INSECURE — only for emergency rollback)
-- DROP POLICY IF EXISTS social_connections_select_own_org ON social_connections;
-- DROP POLICY IF EXISTS social_connections_insert_own_org ON social_connections;
-- DROP POLICY IF EXISTS social_connections_update_own_org ON social_connections;
-- DROP POLICY IF EXISTS social_connections_delete_own_org ON social_connections;
-- CREATE POLICY "social_connections_all" ON social_connections FOR ALL USING (true);
--
-- -- Restore global unique (if needed)
-- DROP INDEX IF EXISTS uq_social_connections_org_platform;
-- ALTER TABLE social_connections ADD CONSTRAINT social_connections_platform_key UNIQUE (platform);
--
-- -- Drop encrypted columns
-- ALTER TABLE social_connections DROP COLUMN IF EXISTS encrypted_access_token;
-- ALTER TABLE social_connections DROP COLUMN IF EXISTS encrypted_refresh_token;
-- ALTER TABLE social_connections DROP COLUMN IF EXISTS encryption_version;
-- ALTER TABLE social_connections DROP COLUMN IF EXISTS token_encrypted_at;
--
-- -- Drop safe view
-- DROP VIEW IF EXISTS social_connections_safe;
--
-- -- Restore column access
-- GRANT SELECT ON social_connections TO authenticated;
--
-- COMMIT;
