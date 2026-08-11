-- =============================================================================
-- AI Studio: Brain tables (Priority 8.5)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

CREATE TABLE IF NOT EXISTS brain_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    context JSONB DEFAULT '{}',
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS brain_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES brain_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'user',
    content TEXT NOT NULL,
    plan_id TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_brain_messages_session ON brain_messages(session_id);

CREATE TABLE IF NOT EXISTS brain_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES brain_sessions(id) ON DELETE SET NULL,
    request TEXT NOT NULL,
    tasks JSONB DEFAULT '[]',
    reasoning TEXT,
    estimated_seconds INTEGER DEFAULT 0,
    confidence FLOAT DEFAULT 0.8,
    modules_involved JSONB DEFAULT '[]',
    status TEXT DEFAULT 'created',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_brain_plans_session ON brain_plans(session_id);

CREATE TABLE IF NOT EXISTS brain_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    confidence FLOAT DEFAULT 0.8,
    source TEXT DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(category, key)
);

CREATE INDEX ix_brain_memory_category ON brain_memory(category);
