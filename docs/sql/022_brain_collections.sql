-- =============================================================================
-- 022: Brain Collections & Conversations — Persistent AI Brain memory
-- =============================================================================

-- Collections group conversations for shared context
CREATE TABLE IF NOT EXISTS brain_collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'::uuid,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#7c3aed',
    talent_id UUID DEFAULT NULL,          -- Optional: connect to AI Talent for creative DNA
    description TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Conversations persist chat sessions
CREATE TABLE IF NOT EXISTS brain_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'::uuid,
    collection_id UUID DEFAULT NULL REFERENCES brain_collections(id) ON DELETE SET NULL,
    title TEXT DEFAULT 'New Conversation',
    mode TEXT DEFAULT 'creative',          -- creative, prompt_engineer, script_writer, etc.
    messages JSONB DEFAULT '[]',           -- Array of {role, content, time}
    summary TEXT DEFAULT '',               -- AI-generated summary for context injection
    message_count INT DEFAULT 0,
    talent_id UUID DEFAULT NULL,           -- Optional: talent context for this conversation
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_brain_collections_org_id ON brain_collections(org_id);
CREATE INDEX IF NOT EXISTS ix_brain_conversations_org_id ON brain_conversations(org_id);
CREATE INDEX IF NOT EXISTS ix_brain_conversations_collection_id ON brain_conversations(collection_id);

ALTER TABLE brain_collections ENABLE ROW LEVEL SECURITY;
ALTER TABLE brain_conversations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "brain_collections_all" ON brain_collections FOR ALL USING (true);
CREATE POLICY "brain_conversations_all" ON brain_conversations FOR ALL USING (true);
