-- =============================================================================
-- AI Studio: Create jobs table (Sprint 2)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    workflow_id UUID,
    type TEXT NOT NULL DEFAULT 'image_generation',
    status TEXT NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 5,
    input JSONB DEFAULT '{}',
    output JSONB DEFAULT '{}',
    worker_name TEXT,
    worker_id TEXT,
    progress INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Performance indexes
CREATE INDEX ix_jobs_status ON jobs(status);
CREATE INDEX ix_jobs_type ON jobs(type);
CREATE INDEX ix_jobs_project_id ON jobs(project_id);
CREATE INDEX ix_jobs_talent_id ON jobs(talent_id);
CREATE INDEX ix_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX ix_jobs_priority_status ON jobs(priority DESC, created_at ASC) WHERE status = 'queued';

-- Constraint: valid status values
ALTER TABLE jobs ADD CONSTRAINT chk_jobs_status
    CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled'));

-- Constraint: valid priority range (1=lowest, 10=highest)
ALTER TABLE jobs ADD CONSTRAINT chk_jobs_priority
    CHECK (priority BETWEEN 1 AND 10);

-- Constraint: progress range
ALTER TABLE jobs ADD CONSTRAINT chk_jobs_progress
    CHECK (progress BETWEEN 0 AND 100);
