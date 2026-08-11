-- 018_object_intelligence.sql
-- Object Intelligence Engine: Object DNA, Product DNA, Digital Twins,
-- Virtual Try-On, 360 Product Rotation, Scene DNA, Material Profiles

-- =============================================================================
-- Object DNA
-- =============================================================================
CREATE TABLE IF NOT EXISTS object_dna (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    name TEXT,
    category TEXT DEFAULT 'general',
    -- Geometry & Dimensions
    shape JSONB DEFAULT '{}',
    dimensions JSONB DEFAULT '{}',
    estimated_scale TEXT,
    -- Materials & Surface
    materials JSONB DEFAULT '[]',
    textures JSONB DEFAULT '[]',
    surface_properties JSONB DEFAULT '{}',
    reflection_profile JSONB DEFAULT '{}',
    shadow_behavior JSONB DEFAULT '{}',
    transparency FLOAT DEFAULT 0.0,
    -- Visual Details
    logos JSONB DEFAULT '[]',
    branding JSONB DEFAULT '{}',
    hardware JSONB DEFAULT '[]',
    parts JSONB DEFAULT '[]',
    -- Views
    front_view_url TEXT,
    back_view_url TEXT,
    left_view_url TEXT,
    right_view_url TEXT,
    top_view_url TEXT,
    bottom_view_url TEXT,
    -- Intelligence
    luxury_score FLOAT DEFAULT 0.5,
    style_tags JSONB DEFAULT '[]',
    recommended_environments JSONB DEFAULT '[]',
    recommended_lighting JSONB DEFAULT '[]',
    recommended_camera_angles JSONB DEFAULT '[]',
    recommended_poses JSONB DEFAULT '[]',
    recommended_workflows JSONB DEFAULT '[]',
    recommended_models JSONB DEFAULT '[]',
    recommended_loras JSONB DEFAULT '[]',
    compatible_characters JSONB DEFAULT '[]',
    compatible_wardrobe JSONB DEFAULT '[]',
    compatible_props JSONB DEFAULT '[]',
    usage_history JSONB DEFAULT '[]',
    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_object_dna_asset ON object_dna(asset_id);
CREATE INDEX IF NOT EXISTS idx_object_dna_category ON object_dna(category);

-- =============================================================================
-- Product DNA
-- =============================================================================
CREATE TABLE IF NOT EXISTS product_dna (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    object_dna_id UUID REFERENCES object_dna(id),
    -- Classification
    product_category TEXT DEFAULT 'general',
    commercial_category TEXT,
    brand TEXT,
    -- Physical Properties
    geometry JSONB DEFAULT '{}',
    dimensions JSONB DEFAULT '{}',
    materials JSONB DEFAULT '[]',
    color_palette JSONB DEFAULT '[]',
    texture JSONB DEFAULT '{}',
    reflectivity FLOAT DEFAULT 0.0,
    -- Branding
    logos JSONB DEFAULT '[]',
    branding JSONB DEFAULT '{}',
    -- Scores
    luxury_score FLOAT DEFAULT 0.5,
    style_score FLOAT DEFAULT 0.5,
    lifestyle_score FLOAT DEFAULT 0.5,
    -- Production Profiles
    camera_profile JSONB DEFAULT '{}',
    lighting_profile JSONB DEFAULT '{}',
    animation_profile JSONB DEFAULT '{}',
    -- Recommendations
    recommended_backgrounds JSONB DEFAULT '[]',
    recommended_scenes JSONB DEFAULT '[]',
    recommended_accessories JSONB DEFAULT '[]',
    recommended_wardrobe JSONB DEFAULT '[]',
    recommended_characters JSONB DEFAULT '[]',
    -- Marketing
    marketing_tags JSONB DEFAULT '[]',
    seo_keywords JSONB DEFAULT '[]',
    future_variants JSONB DEFAULT '[]',
    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_product_dna_category ON product_dna(product_category);
CREATE INDEX IF NOT EXISTS idx_product_dna_brand ON product_dna(brand);

-- =============================================================================
-- Digital Twins
-- =============================================================================
CREATE TABLE IF NOT EXISTS digital_twins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    object_dna_id UUID REFERENCES object_dna(id),
    product_dna_id UUID REFERENCES product_dna(id),
    status TEXT DEFAULT 'active',
    current_version INT DEFAULT 1,
    -- Twin Data
    canonical_views JSONB DEFAULT '{}',
    mesh_url TEXT,
    gaussian_splat_url TEXT,
    usd_url TEXT,
    gltf_url TEXT,
    -- Properties
    properties JSONB DEFAULT '{}',
    variant_history JSONB DEFAULT '[]',
    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS digital_twin_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    digital_twin_id UUID NOT NULL REFERENCES digital_twins(id),
    version_number INT NOT NULL,
    change_description TEXT,
    snapshot JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_twin_versions_twin ON digital_twin_versions(digital_twin_id);

-- =============================================================================
-- Virtual Try-On Jobs
-- =============================================================================
CREATE TABLE IF NOT EXISTS virtual_tryon_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    talent_id UUID NOT NULL,
    -- Items to try on (at least one required)
    wardrobe_item_id UUID,
    accessory_id UUID,
    product_dna_id UUID REFERENCES product_dna(id),
    -- Job Config
    source_image_url TEXT,
    pose TEXT,
    lighting TEXT,
    camera_angle TEXT,
    -- Status
    status TEXT DEFAULT 'pending',
    result_url TEXT,
    result_metadata JSONB DEFAULT '{}',
    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tryon_talent ON virtual_tryon_jobs(talent_id);
CREATE INDEX IF NOT EXISTS idx_tryon_status ON virtual_tryon_jobs(status);

-- =============================================================================
-- 360 Product Views
-- =============================================================================
CREATE TABLE IF NOT EXISTS product_views_360 (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_dna_id UUID NOT NULL REFERENCES product_dna(id),
    view_count INT DEFAULT 12,
    status TEXT DEFAULT 'pending',
    -- Render Config
    rotation_axis TEXT DEFAULT 'y',
    resolution TEXT DEFAULT '2048x2048',
    background TEXT DEFAULT 'transparent',
    lighting TEXT DEFAULT 'studio',
    -- Results
    frame_urls JSONB DEFAULT '[]',
    video_url TEXT,
    interactive_viewer_url TEXT,
    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_360_product ON product_views_360(product_dna_id);

-- =============================================================================
-- Scene DNA
-- =============================================================================
CREATE TABLE IF NOT EXISTS scene_dna (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    -- Composition Elements
    talent_ids JSONB DEFAULT '[]',
    wardrobe_ids JSONB DEFAULT '[]',
    product_ids JSONB DEFAULT '[]',
    prop_ids JSONB DEFAULT '[]',
    -- Environment
    background TEXT,
    lighting TEXT,
    camera TEXT,
    pose TEXT,
    mood TEXT,
    music TEXT,
    voice TEXT,
    -- Production
    workflow_id UUID,
    render_settings JSONB DEFAULT '{}',
    models JSONB DEFAULT '[]',
    loras JSONB DEFAULT '[]',
    -- Timeline
    timeline_links JSONB DEFAULT '[]',
    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scene_dna_category ON scene_dna(category);

-- =============================================================================
-- Material Profiles
-- =============================================================================
CREATE TABLE IF NOT EXISTS material_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    material_type TEXT NOT NULL,
    -- Properties
    reflectivity FLOAT DEFAULT 0.0,
    transparency FLOAT DEFAULT 0.0,
    roughness FLOAT DEFAULT 0.5,
    metallic FLOAT DEFAULT 0.0,
    -- Rendering Recommendations
    recommended_lighting JSONB DEFAULT '{}',
    recommended_hdri TEXT,
    recommended_camera JSONB DEFAULT '{}',
    recommended_workflow TEXT,
    shadow_handling JSONB DEFAULT '{}',
    reflection_handling JSONB DEFAULT '{}',
    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_material_type ON material_profiles(material_type);
