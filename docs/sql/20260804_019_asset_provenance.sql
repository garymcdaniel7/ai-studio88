-- Asset Provenance Contract (Story 073)
-- Complete lineage for all generated outputs.

-- 1. Asset provenance table
CREATE TABLE IF NOT EXISTS asset_provenance (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id                UUID NOT NULL UNIQUE,
    org_id                  UUID NOT NULL,
    media_type              TEXT NOT NULL,
    provenance_state        TEXT NOT NULL DEFAULT 'pending',
    -- Actor
    user_id                 UUID NOT NULL,
    -- Generation
    job_id                  TEXT,
    spec_hash               TEXT,
    effective_prompt        TEXT DEFAULT '',
    effective_negative_prompt TEXT DEFAULT '',
    seed_used               INTEGER,
    steps_used              INTEGER,
    cfg_scale_used          NUMERIC(5,2),
    width                   INTEGER,
    height                  INTEGER,
    duration_seconds        NUMERIC(10,2),
    -- Model
    model_id                TEXT DEFAULT '',
    model_version           TEXT DEFAULT '',
    lora_id                 TEXT,
    lora_version            TEXT,
    lora_strength           NUMERIC(4,2),
    -- Workflow
    workflow_id             UUID,
    workflow_version         TEXT,
    -- Context
    project_id              UUID,
    session_id              TEXT,
    campaign_id             UUID,
    talent_id               UUID,
    -- Storage
    storage_key             TEXT NOT NULL DEFAULT '',
    checksum_sha256         TEXT NOT NULL DEFAULT '',
    mime_type               TEXT NOT NULL DEFAULT '',
    size_bytes              BIGINT DEFAULT 0,
    -- Cost
    cost_estimated_usd      NUMERIC(10,4),
    cost_actual_usd         NUMERIC(10,4),
    provider                TEXT DEFAULT '',
    gpu_type                TEXT,
    runtime_seconds         NUMERIC(10,2),
    -- Consent
    consent_evidence_ids    UUID[] DEFAULT '{}',
    -- Timestamps
    generation_started_at   TIMESTAMPTZ,
    generation_completed_at TIMESTAMPTZ,
    registered_at           TIMESTAMPTZ DEFAULT now(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_asset_provenance_org ON asset_provenance(org_id);
CREATE INDEX IF NOT EXISTS ix_asset_provenance_job ON asset_provenance(job_id);
CREATE INDEX IF NOT EXISTS ix_asset_provenance_talent ON asset_provenance(talent_id) WHERE talent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_asset_provenance_state ON asset_provenance(org_id, provenance_state);

-- RLS
ALTER TABLE asset_provenance ENABLE ROW LEVEL SECURITY;

CREATE POLICY "asset_provenance_org_isolation" ON asset_provenance
    FOR ALL
    USING (org_id = (current_setting('request.jwt.claims', true)::json ->> 'org_id')::uuid);

-- 2. Lineage links table (parent-child relationships)
CREATE TABLE IF NOT EXISTS asset_lineage (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_asset_id      UUID NOT NULL,
    parent_asset_id     UUID NOT NULL,
    relationship        TEXT NOT NULL DEFAULT 'derived_from',
    org_id              UUID NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(child_asset_id, parent_asset_id)
);

CREATE INDEX IF NOT EXISTS ix_asset_lineage_child ON asset_lineage(child_asset_id);
CREATE INDEX IF NOT EXISTS ix_asset_lineage_parent ON asset_lineage(parent_asset_id);
CREATE INDEX IF NOT EXISTS ix_asset_lineage_org ON asset_lineage(org_id);

ALTER TABLE asset_lineage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "asset_lineage_org_isolation" ON asset_lineage
    FOR ALL
    USING (org_id = (current_setting('request.jwt.claims', true)::json ->> 'org_id')::uuid);

-- 3. Provenance amendments (audited corrections)
CREATE TABLE IF NOT EXISTS provenance_amendments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id        UUID NOT NULL,
    org_id          UUID NOT NULL,
    field_name      TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    reason          TEXT NOT NULL,
    amended_by      UUID NOT NULL,
    amended_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_provenance_amendments_asset ON provenance_amendments(asset_id);

ALTER TABLE provenance_amendments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "provenance_amendments_org_isolation" ON provenance_amendments
    FOR ALL
    USING (org_id = (current_setting('request.jwt.claims', true)::json ->> 'org_id')::uuid);
