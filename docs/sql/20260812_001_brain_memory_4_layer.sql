-- =============================================================================
-- AI Studio: Brain Memory 4-Layer Architecture (Task 16.1)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================
-- Creates 4 tables for the Brain memory layer system:
--   1. brain_user_memory     — Per-user private memory with provenance tracking
--   2. brain_workspace_knowledge — Workspace-level knowledge promoted from users
--   3. brain_conversations   — Per-user conversation sessions with modes
--   4. brain_messages        — Messages within conversations
--
-- Implements: R93.1, R94.1, R29.1
-- =============================================================================


-- =============================================================================
-- 1. brain_user_memory — Per-user private memory with provenance hierarchy
-- =============================================================================

CREATE TABLE IF NOT EXISTS brain_user_memory (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL,
    user_id                 UUID NOT NULL,
    memory_type             TEXT NOT NULL,
    content                 JSONB NOT NULL,
    provenance              TEXT NOT NULL
                            CHECK (provenance IN (
                                'USER_CONFIRMED', 'OBSERVED', 'IMPORTED',
                                'INFERRED', 'SUGGESTED'
                            )),
    confidence              NUMERIC(3,2),
    is_active               BOOLEAN NOT NULL DEFAULT true,
    source_conversation_id  UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_brain_user_memory_org_user
    ON brain_user_memory(org_id, user_id);

CREATE INDEX ix_brain_user_memory_org_id
    ON brain_user_memory(org_id);


-- =============================================================================
-- 2. brain_workspace_knowledge — Workspace-promoted knowledge
-- =============================================================================

CREATE TABLE IF NOT EXISTS brain_workspace_knowledge (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    knowledge_type  TEXT NOT NULL,
    content         JSONB NOT NULL,
    promoted_by     UUID,
    promoted_from   UUID REFERENCES brain_user_memory(id) ON DELETE SET NULL,
    provenance      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_brain_workspace_knowledge_org_id
    ON brain_workspace_knowledge(org_id);


-- =============================================================================
-- 3. brain_conversations — Per-user conversation sessions
-- =============================================================================

CREATE TABLE IF NOT EXISTS brain_conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    user_id         UUID NOT NULL,
    trust_domain    TEXT NOT NULL DEFAULT 'CUSTOMER_USER',
    mode            TEXT NOT NULL DEFAULT 'creative',
    title           TEXT,
    is_archived     BOOLEAN NOT NULL DEFAULT false,
    message_count   INTEGER NOT NULL DEFAULT 0,
    last_message_at TIMESTAMPTZ,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_brain_conversations_org_user_created
    ON brain_conversations(org_id, user_id, created_at DESC);


-- =============================================================================
-- 4. brain_messages — Messages within conversations
-- =============================================================================

CREATE TABLE IF NOT EXISTS brain_messages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES brain_conversations(id) ON DELETE CASCADE,
    org_id              UUID NOT NULL,
    user_id             UUID NOT NULL,
    actor               TEXT NOT NULL
                        CHECK (actor IN ('user', 'brain', 'hermes', 'system')),
    content             TEXT NOT NULL,
    tool_refs           JSONB NOT NULL DEFAULT '[]',
    context_snapshot    JSONB,
    token_count         INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_brain_messages_conversation_created
    ON brain_messages(conversation_id, created_at);

CREATE INDEX ix_brain_messages_org_id
    ON brain_messages(org_id);


-- =============================================================================
-- 5. Row Level Security — Tenant isolation via org_members
-- =============================================================================

-- brain_user_memory
ALTER TABLE brain_user_memory ENABLE ROW LEVEL SECURITY;

CREATE POLICY "brain_user_memory_tenant_isolation" ON brain_user_memory
    FOR ALL
    USING (org_id IN (
        SELECT om.org_id FROM org_members om
        WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
          AND om.status = 'active'
    ))
    WITH CHECK (org_id IN (
        SELECT om.org_id FROM org_members om
        WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
          AND om.status = 'active'
    ));

-- brain_workspace_knowledge
ALTER TABLE brain_workspace_knowledge ENABLE ROW LEVEL SECURITY;

CREATE POLICY "brain_workspace_knowledge_tenant_isolation" ON brain_workspace_knowledge
    FOR ALL
    USING (org_id IN (
        SELECT om.org_id FROM org_members om
        WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
          AND om.status = 'active'
    ))
    WITH CHECK (org_id IN (
        SELECT om.org_id FROM org_members om
        WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
          AND om.status = 'active'
    ));

-- brain_conversations
ALTER TABLE brain_conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "brain_conversations_tenant_isolation" ON brain_conversations
    FOR ALL
    USING (org_id IN (
        SELECT om.org_id FROM org_members om
        WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
          AND om.status = 'active'
    ))
    WITH CHECK (org_id IN (
        SELECT om.org_id FROM org_members om
        WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
          AND om.status = 'active'
    ));

-- brain_messages
ALTER TABLE brain_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "brain_messages_tenant_isolation" ON brain_messages
    FOR ALL
    USING (org_id IN (
        SELECT om.org_id FROM org_members om
        WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
          AND om.status = 'active'
    ))
    WITH CHECK (org_id IN (
        SELECT om.org_id FROM org_members om
        WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
          AND om.status = 'active'
    ));
