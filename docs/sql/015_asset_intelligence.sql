-- =============================================================================
-- AI Studio: Asset Intelligence & Scene Composer (Priority 10)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

-- Visual DNA for assets (how the system understands each asset)
CREATE TABLE IF NOT EXISTS visual_dna (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
    category TEXT NOT NULL DEFAULT 'general',
    subcategory TEXT,
    style TEXT,
    brand TEXT,
    material TEXT,
    color_palette JSONB DEFAULT '[]',
    primary_colors JSONB DEFAULT '[]',
    texture TEXT,
    luxury_score FLOAT DEFAULT 0.5,
    casual_score FLOAT DEFAULT 0.5,
    formal_score FLOAT DEFAULT 0.5,
    season JSONB DEFAULT '[]',
    occasion JSONB DEFAULT '[]',
    indoor_outdoor TEXT DEFAULT 'both',
    time_of_day JSONB DEFAULT '[]',
    recommended_pairings JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_visual_dna_asset ON visual_dna(asset_id);
CREATE INDEX ix_visual_dna_category ON visual_dna(category);

-- Asset collections (user-organized groups)
CREATE TABLE IF NOT EXISTS asset_collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT,
    collection_type TEXT DEFAULT 'general',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_collections_type ON asset_collections(collection_type);

-- Collection items (assets in a collection)
CREATE TABLE IF NOT EXISTS collection_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id UUID NOT NULL REFERENCES asset_collections(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    sort_order INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_collection_items_collection ON collection_items(collection_id);

-- Asset relationships (how assets relate to each other)
CREATE TABLE IF NOT EXISTS asset_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_a_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    asset_b_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL DEFAULT 'matches',
    strength FLOAT DEFAULT 0.8,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_relationships_a ON asset_relationships(asset_a_id);
CREATE INDEX ix_relationships_b ON asset_relationships(asset_b_id);

-- Wardrobes (reusable outfit collections per talent)
CREATE TABLE IF NOT EXISTS wardrobes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    wardrobe_type TEXT DEFAULT 'general',
    season TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_wardrobes_talent ON wardrobes(talent_id);

-- Outfits (specific looks)
CREATE TABLE IF NOT EXISTS outfits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wardrobe_id UUID NOT NULL REFERENCES wardrobes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    occasion TEXT,
    mood TEXT,
    luxury_score FLOAT DEFAULT 0.5,
    items JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_outfits_wardrobe ON outfits(wardrobe_id);

-- Scene templates (reusable scene compositions)
CREATE TABLE IF NOT EXISTS scene_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    category TEXT DEFAULT 'general',
    talent_count INTEGER DEFAULT 1,
    background_type TEXT,
    lighting_preset TEXT,
    camera_preset TEXT,
    pose_preset TEXT,
    wardrobe_style TEXT,
    mood TEXT,
    composition JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_scene_templates_category ON scene_templates(category);

-- Camera presets
CREATE TABLE IF NOT EXISTS camera_presets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    lens TEXT,
    focal_length TEXT,
    camera_movement TEXT,
    framing TEXT,
    height TEXT,
    distance TEXT,
    depth_of_field TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lighting presets
CREATE TABLE IF NOT EXISTS lighting_presets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    setup_type TEXT,
    time_of_day TEXT,
    indoor_outdoor TEXT DEFAULT 'both',
    mood TEXT,
    color_temperature TEXT,
    direction TEXT,
    intensity TEXT DEFAULT 'medium',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Pose presets
CREATE TABLE IF NOT EXISTS pose_presets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    category TEXT DEFAULT 'portrait',
    body_angle TEXT,
    head_angle TEXT,
    eye_direction TEXT,
    hand_positions TEXT,
    camera_orientation TEXT,
    emotion TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
