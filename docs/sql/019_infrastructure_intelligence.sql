-- =============================================================================
-- AI Studio: Infrastructure Intelligence (Phase 13 Priority 1)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

-- Track every connection attempt for learning and reputation scoring
CREATE TABLE IF NOT EXISTS worker_connection_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    offer_id INTEGER NOT NULL,
    instance_id INTEGER,
    gpu_name TEXT NOT NULL DEFAULT 'unknown',
    gpu_ram_mb INTEGER NOT NULL DEFAULT 0,
    region TEXT DEFAULT '',
    country TEXT DEFAULT '',
    provider TEXT NOT NULL DEFAULT 'vast_ai',
    status TEXT NOT NULL DEFAULT 'pending',  -- success, failed, timeout
    boot_time_seconds FLOAT,
    ssh_verified_at TIMESTAMPTZ,
    comfyui_verified_at TIMESTAMPTZ,
    failure_reason TEXT,
    hourly_cost FLOAT NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_conn_attempts_status ON worker_connection_attempts(status);
CREATE INDEX ix_conn_attempts_gpu ON worker_connection_attempts(gpu_name);
CREATE INDEX ix_conn_attempts_provider ON worker_connection_attempts(provider);
CREATE INDEX ix_conn_attempts_created ON worker_connection_attempts(created_at DESC);

-- Active and historical worker sessions
CREATE TABLE IF NOT EXISTS worker_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id INTEGER,
    worker_name TEXT NOT NULL DEFAULT '',
    gpu_name TEXT NOT NULL DEFAULT '',
    ssh_host TEXT DEFAULT '',
    ssh_port INTEGER DEFAULT 0,
    comfyui_url TEXT,
    status TEXT NOT NULL DEFAULT 'connecting',
    models_loaded JSONB DEFAULT '[]',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    total_cost FLOAT DEFAULT 0.0,
    jobs_completed INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX ix_worker_sessions_status ON worker_sessions(status);
CREATE INDEX ix_worker_sessions_instance ON worker_sessions(instance_id);
CREATE INDEX ix_worker_sessions_started ON worker_sessions(started_at DESC);

-- status: connecting, booting, installing, downloading_model, starting_comfyui,
--         ready, generating, error, stopped, destroyed
