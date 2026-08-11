-- =============================================================================
-- AI Studio: Continuity notes + creative rules (Phase D)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

CREATE TABLE IF NOT EXISTS continuity_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    category TEXT NOT NULL DEFAULT 'general',
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    priority INTEGER DEFAULT 5,
    active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_continuity_talent ON continuity_notes(talent_id);
CREATE INDEX ix_continuity_project ON continuity_notes(project_id);
CREATE INDEX ix_continuity_category ON continuity_notes(category);

CREATE TABLE IF NOT EXISTS creative_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    rule_type TEXT NOT NULL DEFAULT 'include',
    category TEXT NOT NULL DEFAULT 'prompt',
    rule TEXT NOT NULL,
    reason TEXT,
    confidence FLOAT DEFAULT 0.8,
    source TEXT DEFAULT 'manual',
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_rules_talent ON creative_rules(talent_id);
CREATE INDEX ix_rules_type ON creative_rules(rule_type);
CREATE INDEX ix_rules_category ON creative_rules(category);

-- rule_type: 'include' (always add) or 'avoid' (add to negative)
-- category: 'prompt', 'style', 'lighting', 'wardrobe', 'camera', 'model', 'workflow'
-- source: 'manual' (user set), 'learned' (from feedback), 'dna' (from creative DNA)
