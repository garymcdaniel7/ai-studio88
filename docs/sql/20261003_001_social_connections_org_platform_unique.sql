-- =============================================================================
-- CTO remediation (2026-10-03): social_connections unique per (org_id, platform)
-- -----------------------------------------------------------------------------
-- Finding F2 (cto-posture-review-20261003): the table's only unique constraint
-- was UNIQUE(platform) — any tenant connecting a platform overwrote the prior
-- tenant's OAuth tokens (cross-tenant credential collision). The intended fix
-- already existed in 20260806_004 but was marked "DO NOT APPLY" template.
--
-- This migration: drop the global platform unique, create (org_id, platform).
-- Reversible: DROP INDEX uq_social_connections_org_platform; then re-add a
-- UNIQUE constraint on platform.
-- =============================================================================

BEGIN;

-- Drop the global "one row per platform for everyone" uniqueness
ALTER TABLE social_connections DROP CONSTRAINT IF EXISTS social_connections_platform_key;

-- Per-org uniqueness: each tenant may connect each platform exactly once
CREATE UNIQUE INDEX IF NOT EXISTS uq_social_connections_org_platform
    ON social_connections(org_id, platform);

COMMIT;
