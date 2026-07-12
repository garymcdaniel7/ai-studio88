-- AIOS Knowledge Graph tables
-- Phase 4: Workflow DNA + knowledge search indexes

CREATE TABLE IF NOT EXISTS workflow_dna (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID DEFAULT '00000000-0000-0000-0000-000000000000',
    name TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT 'image',   -- image, video, voice
    checkpoint TEXT DEFAULT '',                    -- model filename
    loras JSONB DEFAULT '[]',                     -- [{model_id, strength, trigger_words}]
    sampler TEXT DEFAULT 'euler',
    scheduler TEXT DEFAULT 'normal',
    cfg NUMERIC(5, 2) DEFAULT 7.0,
    steps INT DEFAULT 20,
    width INT DEFAULT 1024,
    height INT DEFAULT 1024,
    negative_prompt TEXT DEFAULT '',
    quality_score NUMERIC(3, 2) DEFAULT 0,        -- 1-5 average user rating
    success_rate NUMERIC(3, 2) DEFAULT 0,         -- 0-1 fraction rated 4+
    usage_count INT DEFAULT 0,
    avg_generation_time NUMERIC(10, 2) DEFAULT 0,
    avg_cost NUMERIC(10, 6) DEFAULT 0,
    recommended_for TEXT[] DEFAULT '{}',           -- categories: portrait, luxury, etc.
    talent_id UUID,                               -- NULL for general recipes
    source TEXT DEFAULT 'auto_learned',           -- auto_learned, manual, community
    config_snapshot JSONB DEFAULT '{}',           -- full generation config
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_workflow_dna_content_type ON workflow_dna(content_type);
CREATE INDEX IF NOT EXISTS ix_workflow_dna_quality ON workflow_dna(quality_score DESC);
CREATE INDEX IF NOT EXISTS ix_workflow_dna_talent ON workflow_dna(talent_id);
CREATE INDEX IF NOT EXISTS ix_workflow_dna_checkpoint ON workflow_dna(checkpoint);
