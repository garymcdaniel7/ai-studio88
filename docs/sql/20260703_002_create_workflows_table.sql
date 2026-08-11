-- =============================================================================
-- AI Studio: Create workflows table (Sprint 3)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    trigger_type TEXT NOT NULL DEFAULT 'manual',
    steps JSONB NOT NULL DEFAULT '[]',
    definition JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_workflows_project_id ON workflows(project_id);
CREATE INDEX ix_workflows_status ON workflows(status);
CREATE INDEX ix_workflows_name ON workflows(name);

-- Constraint: valid status
ALTER TABLE workflows ADD CONSTRAINT chk_workflows_status
    CHECK (status IN ('draft', 'active', 'archived'));

-- Constraint: valid trigger type
ALTER TABLE workflows ADD CONSTRAINT chk_workflows_trigger
    CHECK (trigger_type IN ('manual', 'schedule', 'event', 'api'));

-- =============================================================================
-- Workflow runs track each execution of a workflow
-- =============================================================================

CREATE TABLE IF NOT EXISTS workflow_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'running',
    input JSONB DEFAULT '{}',
    output JSONB DEFAULT '{}',
    current_step INTEGER NOT NULL DEFAULT 0,
    total_steps INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_workflow_runs_workflow_id ON workflow_runs(workflow_id);
CREATE INDEX ix_workflow_runs_status ON workflow_runs(status);

ALTER TABLE workflow_runs ADD CONSTRAINT chk_workflow_runs_status
    CHECK (status IN ('running', 'completed', 'failed', 'cancelled'));
