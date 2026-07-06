-- =============================================================================
-- 020: Cost Tracking — Persistent cost records for billing and analytics
-- =============================================================================

-- Worker session costs (GPU time)
CREATE TABLE IF NOT EXISTS cost_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'::uuid,
    session_id TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    duration_seconds FLOAT NOT NULL,
    hourly_rate FLOAT NOT NULL,
    total_cost FLOAT NOT NULL,
    gpu_name TEXT DEFAULT '',
    provider TEXT DEFAULT 'vast_ai',
    jobs_completed INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_cost_records_org_id ON cost_records(org_id);
CREATE INDEX IF NOT EXISTS ix_cost_records_created_at ON cost_records(created_at);
CREATE INDEX IF NOT EXISTS ix_cost_records_provider ON cost_records(provider);

-- Per-job costs (generation, training, voice, etc.)
CREATE TABLE IF NOT EXISTS job_costs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'::uuid,
    job_type TEXT NOT NULL,             -- 'generation', 'training', 'voice', 'video'
    model TEXT DEFAULT '',              -- model used (e.g. 'sdxl-turbo', 'llama3.1:8b')
    provider TEXT DEFAULT '',           -- provider used (e.g. 'comfyui', 'elevenlabs', 'vast')
    duration_seconds FLOAT DEFAULT 0,
    estimated_cost FLOAT DEFAULT 0,     -- estimated GPU cost based on duration * hourly_rate
    api_cost FLOAT DEFAULT 0,           -- direct API cost (e.g. ElevenLabs characters)
    total_cost FLOAT DEFAULT 0,         -- estimated_cost + api_cost
    input_summary TEXT DEFAULT '',      -- e.g. prompt text (truncated), training config
    output_summary TEXT DEFAULT '',     -- e.g. filename, asset_id
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_job_costs_org_id ON job_costs(org_id);
CREATE INDEX IF NOT EXISTS ix_job_costs_job_type ON job_costs(job_type);
CREATE INDEX IF NOT EXISTS ix_job_costs_created_at ON job_costs(created_at);

-- RLS
ALTER TABLE cost_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_costs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "cost_records_org_isolation" ON cost_records
    FOR ALL USING (org_id = '00000000-0000-0000-0000-000000000001'::uuid);

CREATE POLICY "job_costs_org_isolation" ON job_costs
    FOR ALL USING (org_id = '00000000-0000-0000-0000-000000000001'::uuid);
