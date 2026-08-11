-- Migration 037: Durable Batch Generation Tables (Story 109)
--
-- Creates:
--   1. generation_batches — parent batch records with immutable shared settings
--   2. batch_variation_jobs — per-variation child jobs with state, cost, output
--
-- Run: psql $SUPABASE_URL -f docs/sql/037_batch_generation.sql

-- =============================================================================
-- 1. generation_batches — Durable batch records
-- =============================================================================

CREATE TABLE IF NOT EXISTS generation_batches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id        TEXT UNIQUE NOT NULL,                    -- application-generated e.g. "batch-abc123"
    idempotency_key TEXT,                                   -- client-supplied for duplicate detection
    org_id          UUID NOT NULL,                          -- tenant scope
    user_id         TEXT NOT NULL,                          -- submitting user

    -- Immutable shared specification (frozen at submission)
    model           TEXT NOT NULL DEFAULT 'flux-dev',
    prompt          TEXT NOT NULL DEFAULT '',
    negative_prompt TEXT NOT NULL DEFAULT '',
    width           INT NOT NULL DEFAULT 1024,
    height          INT NOT NULL DEFAULT 1024,
    steps           INT NOT NULL DEFAULT 20,
    cfg_scale       REAL NOT NULL DEFAULT 7.0,
    spec_hash       TEXT NOT NULL DEFAULT '',               -- deterministic hash of specification
    context_package_id TEXT NOT NULL DEFAULT '',

    -- Batch control
    requested_count INT NOT NULL DEFAULT 1,
    state           TEXT NOT NULL DEFAULT 'submitted',      -- submitted | in_progress | completed | cancelled

    -- Cost aggregates
    total_estimated_usd REAL NOT NULL DEFAULT 0.0,
    total_actual_usd    REAL NOT NULL DEFAULT 0.0,

    -- Timing
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE UNIQUE INDEX IF NOT EXISTS ix_generation_batches_idempotency
    ON generation_batches (idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key != '';

CREATE INDEX IF NOT EXISTS ix_generation_batches_org_id
    ON generation_batches (org_id);

CREATE INDEX IF NOT EXISTS ix_generation_batches_user_id
    ON generation_batches (user_id);

CREATE INDEX IF NOT EXISTS ix_generation_batches_state
    ON generation_batches (state)
    WHERE state IN ('submitted', 'in_progress');

CREATE INDEX IF NOT EXISTS ix_generation_batches_created_at
    ON generation_batches (created_at DESC);

-- RLS
ALTER TABLE generation_batches ENABLE ROW LEVEL SECURITY;

CREATE POLICY "batches_org_isolation" ON generation_batches
    FOR ALL
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- =============================================================================
-- 2. batch_variation_jobs — Per-variation child jobs
-- =============================================================================

CREATE TABLE IF NOT EXISTS batch_variation_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          TEXT UNIQUE NOT NULL,                    -- application-generated e.g. "var-abc123"
    batch_id        TEXT NOT NULL REFERENCES generation_batches(batch_id) ON DELETE CASCADE,
    org_id          UUID NOT NULL,                          -- denormalized for RLS

    -- Variation identity
    variation_index INT NOT NULL DEFAULT 0,
    seed            INT NOT NULL DEFAULT -1,
    extra_settings  JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- State
    state           TEXT NOT NULL DEFAULT 'queued',          -- queued | executing | completed | failed | cancelled

    -- Output
    asset_id        TEXT,                                   -- FK to assets table (completed variations)
    error_message   TEXT,

    -- Cost
    cost_estimated_usd REAL NOT NULL DEFAULT 0.0,
    cost_actual_usd    REAL,

    -- Retry lineage
    attempt         INT NOT NULL DEFAULT 1,
    parent_job_id   TEXT,                                   -- previous attempt's job_id

    -- Timing
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_batch_variation_jobs_batch_id
    ON batch_variation_jobs (batch_id);

CREATE INDEX IF NOT EXISTS ix_batch_variation_jobs_org_id
    ON batch_variation_jobs (org_id);

CREATE INDEX IF NOT EXISTS ix_batch_variation_jobs_state
    ON batch_variation_jobs (state)
    WHERE state IN ('queued', 'executing');

CREATE INDEX IF NOT EXISTS ix_batch_variation_jobs_parent
    ON batch_variation_jobs (parent_job_id)
    WHERE parent_job_id IS NOT NULL;

-- RLS
ALTER TABLE batch_variation_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "variation_jobs_org_isolation" ON batch_variation_jobs
    FOR ALL
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid);


-- =============================================================================
-- 3. Updated_at trigger
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_generation_batches_updated_at
    BEFORE UPDATE ON generation_batches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_batch_variation_jobs_updated_at
    BEFORE UPDATE ON batch_variation_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- =============================================================================
-- 4. Rollback
-- =============================================================================
-- DROP TABLE IF EXISTS batch_variation_jobs;
-- DROP TABLE IF EXISTS generation_batches;
