-- =============================================================================
-- AI Studio: Persistent Workers table (Priority 3)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

CREATE TABLE IF NOT EXISTS workers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'local',
    status TEXT NOT NULL DEFAULT 'offline',
    base_url TEXT,
    masked_url TEXT,
    gpu_name TEXT,
    vram_gb FLOAT DEFAULT 0.0,
    available_vram_gb FLOAT DEFAULT 0.0,
    cuda_version TEXT,
    driver_version TEXT,
    supported_tasks JSONB DEFAULT '[]',
    supported_models JSONB DEFAULT '[]',
    current_job_id UUID,
    last_heartbeat_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_workers_status ON workers(status);
CREATE INDEX ix_workers_provider ON workers(provider);
CREATE INDEX ix_workers_last_heartbeat ON workers(last_heartbeat_at);

-- status: online, busy, offline, error
-- provider: local, vast_ai, runpod, shadow_pc, custom
