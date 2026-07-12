-- Talent Relationships — associates any talent to any other talent
-- Supports: friends, couple, wears, uses, lives_in, holds, pairs_with, displayed_in, variant_of, appears_with

CREATE TABLE IF NOT EXISTS talent_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID DEFAULT '00000000-0000-0000-0000-000000000000',
    talent_id UUID NOT NULL,
    related_talent_id UUID NOT NULL,
    relationship_type TEXT NOT NULL DEFAULT 'associated',
    notes TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(talent_id, related_talent_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS ix_talent_relationships_talent ON talent_relationships(talent_id);
CREATE INDEX IF NOT EXISTS ix_talent_relationships_related ON talent_relationships(related_talent_id);
CREATE INDEX IF NOT EXISTS ix_talent_relationships_type ON talent_relationships(relationship_type);

COMMENT ON TABLE talent_relationships IS 'Associates any talent entity to another (person↔wardrobe, person↔background, person↔person, etc.)';
