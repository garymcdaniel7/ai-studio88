-- Migration Ledger Bootstrap (Story 067)
-- This is migration #000 — it must be applied BEFORE all other migrations.
-- It creates the _migration_ledger table that tracks all future migration state.
--
-- This migration is idempotent (IF NOT EXISTS) and can be safely re-run.

CREATE TABLE IF NOT EXISTS _migration_ledger (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_id    TEXT NOT NULL,
    checksum        TEXT NOT NULL,
    environment     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'applied',
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_ms     INTEGER DEFAULT 0,
    release_id      TEXT DEFAULT '',
    commit_sha      TEXT DEFAULT '',
    error_message   TEXT DEFAULT '',
    applied_by      TEXT DEFAULT 'migration_ledger',
    UNIQUE(migration_id, environment)
);

-- Index for fast lookups by environment and time
CREATE INDEX IF NOT EXISTS ix_migration_ledger_env
    ON _migration_ledger(environment, applied_at);

-- RLS: _migration_ledger is a system table, not tenant-scoped.
-- Only service-role access is permitted (no anon/authenticated access).
ALTER TABLE _migration_ledger ENABLE ROW LEVEL SECURITY;

-- No policies = deny all for non-service-role connections.
-- Service role bypasses RLS by default in Supabase.
