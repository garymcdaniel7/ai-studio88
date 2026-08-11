-- =============================================================================
-- AI Studio: Production Intelligence tables (Phase 9)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

CREATE TABLE IF NOT EXISTS quality_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    identity_consistency FLOAT,
    prompt_adherence FLOAT,
    anatomy FLOAT,
    hands FLOAT,
    lighting FLOAT,
    composition FLOAT,
    cinematic_quality FLOAT,
    overall FLOAT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_quality_asset ON quality_scores(asset_id);

CREATE TABLE IF NOT EXISTS learning_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL DEFAULT 'observation',
    description TEXT,
    outcome TEXT,
    impact TEXT DEFAULT 'neutral',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_learning_type ON learning_events(event_type);
CREATE INDEX ix_learning_impact ON learning_events(impact);

CREATE TABLE IF NOT EXISTS production_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    reasoning TEXT,
    confidence FLOAT DEFAULT 0.8,
    priority TEXT DEFAULT 'medium',
    action TEXT,
    status TEXT DEFAULT 'pending',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_insights_agent ON production_insights(agent);
CREATE INDEX ix_insights_priority ON production_insights(priority);
