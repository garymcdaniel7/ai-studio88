-- =============================================================================
-- 023: Brain Embeddings — Vector storage for RAG (long-term AI memory)
-- Requires: CREATE EXTENSION IF NOT EXISTS vector; (already done)
-- =============================================================================

CREATE TABLE IF NOT EXISTS brain_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'::uuid,
    conversation_id UUID DEFAULT NULL,
    collection_id UUID DEFAULT NULL,
    content TEXT NOT NULL,                 -- The text that was embedded
    embedding vector(768),                 -- Ollama nomic-embed-text produces 768-dim vectors
    source_type TEXT DEFAULT 'conversation', -- 'conversation', 'talent_dna', 'prompt', 'note'
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Vector similarity search index (IVFFlat for speed)
CREATE INDEX IF NOT EXISTS ix_brain_embeddings_vector ON brain_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);

CREATE INDEX IF NOT EXISTS ix_brain_embeddings_org_id ON brain_embeddings(org_id);
CREATE INDEX IF NOT EXISTS ix_brain_embeddings_collection_id ON brain_embeddings(collection_id);

ALTER TABLE brain_embeddings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "brain_embeddings_all" ON brain_embeddings FOR ALL USING (true);

-- Helper function: search for similar embeddings
CREATE OR REPLACE FUNCTION match_brain_embeddings(
    query_embedding vector(768),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    source_type TEXT,
    similarity FLOAT,
    metadata JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        be.id,
        be.content,
        be.source_type,
        1 - (be.embedding <=> query_embedding) AS similarity,
        be.metadata
    FROM brain_embeddings be
    WHERE 1 - (be.embedding <=> query_embedding) > match_threshold
    ORDER BY be.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
