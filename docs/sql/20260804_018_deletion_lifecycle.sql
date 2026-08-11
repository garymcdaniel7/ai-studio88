-- Recoverable Deletion Lifecycle (Story 069)
-- Adds lifecycle state columns and transition audit table.

-- 1. Lifecycle state column on supported entities
-- Default: 'active'. Queries filter by this column.

ALTER TABLE ai_talent ADD COLUMN IF NOT EXISTS lifecycle_state TEXT NOT NULL DEFAULT 'active';
ALTER TABLE ai_talent ADD COLUMN IF NOT EXISTS trashed_at TIMESTAMPTZ;
ALTER TABLE ai_talent ADD COLUMN IF NOT EXISTS trashed_by UUID;
ALTER TABLE ai_talent ADD COLUMN IF NOT EXISTS trash_reason TEXT;
ALTER TABLE ai_talent ADD COLUMN IF NOT EXISTS retention_policy TEXT NOT NULL DEFAULT 'UNVERIFIED';

ALTER TABLE content_jobs ADD COLUMN IF NOT EXISTS lifecycle_state TEXT NOT NULL DEFAULT 'active';
ALTER TABLE content_jobs ADD COLUMN IF NOT EXISTS trashed_at TIMESTAMPTZ;
ALTER TABLE content_jobs ADD COLUMN IF NOT EXISTS trashed_by UUID;
ALTER TABLE content_jobs ADD COLUMN IF NOT EXISTS trash_reason TEXT;
ALTER TABLE content_jobs ADD COLUMN IF NOT EXISTS retention_policy TEXT NOT NULL DEFAULT 'UNVERIFIED';

ALTER TABLE lora_models ADD COLUMN IF NOT EXISTS lifecycle_state TEXT NOT NULL DEFAULT 'active';
ALTER TABLE lora_models ADD COLUMN IF NOT EXISTS trashed_at TIMESTAMPTZ;
ALTER TABLE lora_models ADD COLUMN IF NOT EXISTS trashed_by UUID;
ALTER TABLE lora_models ADD COLUMN IF NOT EXISTS trash_reason TEXT;
ALTER TABLE lora_models ADD COLUMN IF NOT EXISTS retention_policy TEXT NOT NULL DEFAULT 'UNVERIFIED';

ALTER TABLE workflows ADD COLUMN IF NOT EXISTS lifecycle_state TEXT NOT NULL DEFAULT 'active';
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS trashed_at TIMESTAMPTZ;
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS trashed_by UUID;
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS trash_reason TEXT;
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS retention_policy TEXT NOT NULL DEFAULT 'UNVERIFIED';

ALTER TABLE brain_conversations ADD COLUMN IF NOT EXISTS lifecycle_state TEXT NOT NULL DEFAULT 'active';
ALTER TABLE brain_conversations ADD COLUMN IF NOT EXISTS trashed_at TIMESTAMPTZ;
ALTER TABLE brain_conversations ADD COLUMN IF NOT EXISTS trashed_by UUID;
ALTER TABLE brain_conversations ADD COLUMN IF NOT EXISTS trash_reason TEXT;
ALTER TABLE brain_conversations ADD COLUMN IF NOT EXISTS retention_policy TEXT NOT NULL DEFAULT 'UNVERIFIED';

-- Projects table (if exists)
ALTER TABLE projects ADD COLUMN IF NOT EXISTS lifecycle_state TEXT NOT NULL DEFAULT 'active';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS trashed_at TIMESTAMPTZ;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS trashed_by UUID;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS trash_reason TEXT;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS retention_policy TEXT NOT NULL DEFAULT 'UNVERIFIED';

-- Campaigns table (if exists)
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS lifecycle_state TEXT NOT NULL DEFAULT 'active';
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS trashed_at TIMESTAMPTZ;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS trashed_by UUID;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS trash_reason TEXT;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS retention_policy TEXT NOT NULL DEFAULT 'UNVERIFIED';

-- 2. Indexes for default query filtering
CREATE INDEX IF NOT EXISTS ix_ai_talent_lifecycle ON ai_talent(org_id, lifecycle_state);
CREATE INDEX IF NOT EXISTS ix_content_jobs_lifecycle ON content_jobs(org_id, lifecycle_state);
CREATE INDEX IF NOT EXISTS ix_lora_models_lifecycle ON lora_models(org_id, lifecycle_state);
CREATE INDEX IF NOT EXISTS ix_workflows_lifecycle ON workflows(org_id, lifecycle_state);
CREATE INDEX IF NOT EXISTS ix_brain_conversations_lifecycle ON brain_conversations(org_id, lifecycle_state);
CREATE INDEX IF NOT EXISTS ix_projects_lifecycle ON projects(org_id, lifecycle_state);
CREATE INDEX IF NOT EXISTS ix_campaigns_lifecycle ON campaigns(org_id, lifecycle_state);

-- 3. Lifecycle transition audit table
CREATE TABLE IF NOT EXISTS lifecycle_transitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     TEXT NOT NULL,
    entity_id       UUID NOT NULL,
    org_id          UUID NOT NULL,
    prior_state     TEXT NOT NULL,
    new_state       TEXT NOT NULL,
    action          TEXT NOT NULL,
    actor_id        UUID NOT NULL,
    actor_role      TEXT NOT NULL DEFAULT 'owner',
    reason          TEXT DEFAULT '',
    hold_type       TEXT,
    hold_expires_at TIMESTAMPTZ,
    restored_name   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_lifecycle_transitions_entity
    ON lifecycle_transitions(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_lifecycle_transitions_org
    ON lifecycle_transitions(org_id, created_at DESC);

-- RLS on transition audit
ALTER TABLE lifecycle_transitions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "lifecycle_transitions_org_isolation" ON lifecycle_transitions
    FOR ALL
    USING (org_id = (current_setting('request.jwt.claims', true)::json ->> 'org_id')::uuid);

-- 4. Entity holds table
CREATE TABLE IF NOT EXISTS entity_holds (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     TEXT NOT NULL,
    entity_id       UUID NOT NULL,
    org_id          UUID NOT NULL,
    hold_type       TEXT NOT NULL,
    placed_by       UUID NOT NULL,
    reason          TEXT NOT NULL,
    placed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ,
    released_at     TIMESTAMPTZ,
    released_by     UUID
);

CREATE INDEX IF NOT EXISTS ix_entity_holds_entity
    ON entity_holds(entity_type, entity_id) WHERE released_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_entity_holds_org
    ON entity_holds(org_id);

ALTER TABLE entity_holds ENABLE ROW LEVEL SECURITY;

CREATE POLICY "entity_holds_org_isolation" ON entity_holds
    FOR ALL
    USING (org_id = (current_setting('request.jwt.claims', true)::json ->> 'org_id')::uuid);
