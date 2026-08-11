-- Migration: 060_create_worker_instances
-- Purpose: Durable state for Worker Orchestrator (R13.8)
-- The worker_instances table replaces in-memory WorkerSession tracking.

CREATE TABLE IF NOT EXISTS worker_instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    provider_name TEXT NOT NULL,
    provider_instance_id TEXT DEFAULT '',
    gpu_name TEXT DEFAULT '',
    gpu_vram_gb NUMERIC(6,2) DEFAULT 0.0,
    host TEXT DEFAULT '',
    port INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'provisioning'
        CHECK (status IN (
            'provisioning', 'booting', 'installing',
            'ready', 'busy', 'idle',
            'terminated', 'failed'
        )),
    hourly_rate NUMERIC(8,4) DEFAULT 0.0,
    current_job_id UUID,
    consecutive_health_failures INTEGER DEFAULT 0,
    last_health_check_at TIMESTAMPTZ,
    last_job_completed_at TIMESTAMPTZ,
    total_cost_usd NUMERIC(10,4) DEFAULT 0.0,
    jobs_completed INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    terminated_at TIMESTAMPTZ
);

-- Index for fleet limit queries (active workers per org)
CREATE INDEX ix_worker_instances_org_status
    ON worker_instances(org_id, status)
    WHERE status NOT IN ('terminated', 'failed');

-- Index for health check loop (all active workers)
CREATE INDEX ix_worker_instances_active
    ON worker_instances(status)
    WHERE status IN ('provisioning', 'booting', 'ready', 'busy', 'idle');

-- Index for daily spend calculation
CREATE INDEX ix_worker_instances_org_created
    ON worker_instances(org_id, created_at);

-- RLS
ALTER TABLE worker_instances ENABLE ROW LEVEL SECURITY;

CREATE POLICY "worker_instances_org_isolation" ON worker_instances
    FOR ALL
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid);

COMMENT ON TABLE worker_instances IS
    'Durable GPU worker state — persists across backend restarts (R13.8)';
