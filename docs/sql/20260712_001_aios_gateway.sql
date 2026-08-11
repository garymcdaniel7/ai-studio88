-- AIOS Intelligence Gateway tables
-- Phase 1: Sessions, Messages, Decisions

CREATE TABLE IF NOT EXISTS aios_sessions (
    id TEXT PRIMARY KEY,
    org_id UUID DEFAULT '00000000-0000-0000-0000-000000000000',
    mode TEXT DEFAULT 'creative',
    talent_id UUID,
    project_id UUID,
    message_count INT DEFAULT 0,
    status TEXT DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_aios_sessions_created ON aios_sessions(created_at DESC);

CREATE TABLE IF NOT EXISTS aios_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES aios_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,  -- user, assistant, system
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_aios_messages_session ON aios_messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS aios_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT,
    decision_type TEXT NOT NULL,  -- chat, plan, tool_invoke, routing
    provider TEXT NOT NULL,       -- ollama, openai, anthropic
    model TEXT NOT NULL,          -- llama3.1:8b, gpt-4o, claude-sonnet-4-20250514
    input_summary TEXT DEFAULT '',
    output_summary TEXT DEFAULT '',
    latency_ms INT DEFAULT 0,
    tokens_used INT,
    cost_usd NUMERIC(10, 6),
    mode TEXT DEFAULT '',
    confidence NUMERIC(3, 2),
    reasoning TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_aios_decisions_session ON aios_decisions(session_id);
CREATE INDEX IF NOT EXISTS ix_aios_decisions_provider ON aios_decisions(provider);
CREATE INDEX IF NOT EXISTS ix_aios_decisions_created ON aios_decisions(created_at DESC);
