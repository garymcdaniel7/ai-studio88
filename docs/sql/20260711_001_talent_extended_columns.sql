-- Migration: Add extended columns to talent table + association tables
-- Run in: Supabase Dashboard > SQL Editor
-- Date: 2026-07-11

-- ═══════════════════════════════════════════════════════════════════════════════
-- 1. Add physical/creative columns to talent
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE talent ADD COLUMN IF NOT EXISTS height TEXT DEFAULT NULL;
ALTER TABLE talent ADD COLUMN IF NOT EXISTS hair_color TEXT DEFAULT NULL;
ALTER TABLE talent ADD COLUMN IF NOT EXISTS eye_color TEXT DEFAULT NULL;
ALTER TABLE talent ADD COLUMN IF NOT EXISTS body_type TEXT DEFAULT NULL;
ALTER TABLE talent ADD COLUMN IF NOT EXISTS negative_prompt TEXT DEFAULT NULL;
ALTER TABLE talent ADD COLUMN IF NOT EXISTS visual_style TEXT DEFAULT NULL;
ALTER TABLE talent ADD COLUMN IF NOT EXISTS best_for TEXT DEFAULT NULL;
ALTER TABLE talent ADD COLUMN IF NOT EXISTS persona TEXT DEFAULT NULL;
ALTER TABLE talent ADD COLUMN IF NOT EXISTS creative_dna JSONB DEFAULT NULL;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 2. Talent-to-Talent relationships (e.g. "Melissa wears Dress X")
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS talent_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    talent_id UUID NOT NULL REFERENCES talent(id) ON DELETE CASCADE,
    related_talent_id UUID NOT NULL REFERENCES talent(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL DEFAULT 'associated',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(talent_id, related_talent_id, relationship_type)
);
CREATE INDEX IF NOT EXISTS ix_talent_relationships_talent_id ON talent_relationships(talent_id);
CREATE INDEX IF NOT EXISTS ix_talent_relationships_related ON talent_relationships(related_talent_id);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 3. Talent-to-Asset many-to-many (any talent can link to any asset)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS talent_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    talent_id UUID NOT NULL REFERENCES talent(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'reference',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(talent_id, asset_id, role)
);
CREATE INDEX IF NOT EXISTS ix_talent_assets_talent_id ON talent_assets(talent_id);
CREATE INDEX IF NOT EXISTS ix_talent_assets_asset_id ON talent_assets(asset_id);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 4. Talent-to-Voice (multi-talent voice associations)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS talent_voices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    talent_id UUID NOT NULL REFERENCES talent(id) ON DELETE CASCADE,
    voice_profile_id UUID NOT NULL,
    is_primary BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(talent_id, voice_profile_id)
);
CREATE INDEX IF NOT EXISTS ix_talent_voices_talent_id ON talent_voices(talent_id);
