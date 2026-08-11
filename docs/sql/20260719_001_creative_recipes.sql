-- Creative Recipes — proven generation combinations that learn over time
-- Recipes replace manual parameter configuration for non-technical users.

CREATE TABLE IF NOT EXISTS creative_recipes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL DEFAULT 'portrait', -- portrait, product, landscape, editorial, video, social
    content_type TEXT NOT NULL DEFAULT 'image', -- image, video, audio

    -- Technical configuration (hidden from users)
    model TEXT NOT NULL DEFAULT 'flux2-klein',
    loras JSONB DEFAULT '[]'::jsonb, -- [{id, strength}]
    sampler TEXT DEFAULT 'euler',
    scheduler TEXT DEFAULT 'normal',
    cfg FLOAT DEFAULT 1.0,
    steps INT DEFAULT 4,
    negative_prompt TEXT DEFAULT 'ugly, blurry, deformed',
    width INT DEFAULT 1024,
    height INT DEFAULT 1024,

    -- Intelligence (learned over time)
    quality_score FLOAT DEFAULT 0.0, -- 0-5, from user ratings
    success_rate FLOAT DEFAULT 1.0, -- historical success percentage
    times_used INT DEFAULT 0,
    avg_generation_time FLOAT DEFAULT 0.0, -- seconds
    avg_cost FLOAT DEFAULT 0.0, -- USD per generation

    -- Metadata
    created_by TEXT DEFAULT 'system', -- system, user, ai_learned
    recommended_for TEXT[] DEFAULT '{}', -- tags: luxury, fashion, portrait, etc
    compatible_talent_types TEXT[] DEFAULT '{}', -- model, influencer, product, etc
    is_public BOOLEAN DEFAULT false,

    -- Learning
    feedback_history JSONB DEFAULT '[]'::jsonb, -- [{rating, date}]
    auto_improvements JSONB DEFAULT '[]'::jsonb, -- [{field, old, new, reason}]

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_creative_recipes_org_id ON creative_recipes(org_id);
CREATE INDEX IF NOT EXISTS ix_creative_recipes_category ON creative_recipes(category);
CREATE INDEX IF NOT EXISTS ix_creative_recipes_model ON creative_recipes(model);
CREATE INDEX IF NOT EXISTS ix_creative_recipes_quality ON creative_recipes(quality_score DESC);

-- RLS
ALTER TABLE creative_recipes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "recipe_org_isolation" ON creative_recipes
    FOR ALL
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid OR is_public = true);

-- Seed system recipes (available to all orgs)
INSERT INTO creative_recipes (org_id, name, description, category, content_type, model, cfg, steps, sampler, scheduler, negative_prompt, width, height, quality_score, created_by, recommended_for, is_public) VALUES
-- Portrait recipes
('00000000-0000-0000-0000-000000000000', 'Studio Portrait', 'Clean studio headshot with soft lighting', 'portrait', 'image', 'flux2-dev', 3.5, 20, 'euler', 'normal', 'ugly, blurry, deformed, extra limbs', 1024, 1024, 4.5, 'system', ARRAY['portrait', 'headshot', 'professional'], true),
('00000000-0000-0000-0000-000000000000', 'Golden Hour Portrait', 'Warm outdoor portrait with golden hour lighting', 'portrait', 'image', 'flux2-dev', 3.5, 20, 'euler', 'normal', 'ugly, blurry, overexposed, harsh shadows', 1024, 1024, 4.7, 'system', ARRAY['portrait', 'outdoor', 'warm', 'golden'], true),
('00000000-0000-0000-0000-000000000000', 'Fast Draft Portrait', 'Quick portrait for iteration and testing', 'portrait', 'image', 'flux2-klein', 1.0, 4, 'euler', 'normal', 'ugly, blurry', 1024, 1024, 3.8, 'system', ARRAY['portrait', 'fast', 'draft'], true),

-- Editorial recipes
('00000000-0000-0000-0000-000000000000', 'Magazine Cover', 'High-fashion editorial with dramatic lighting', 'editorial', 'image', 'flux2-dev', 3.5, 25, 'euler', 'normal', 'ugly, amateur, low quality, blurry', 1024, 1344, 4.8, 'system', ARRAY['editorial', 'fashion', 'magazine', 'luxury'], true),
('00000000-0000-0000-0000-000000000000', 'Street Style', 'Candid street photography aesthetic', 'editorial', 'image', 'flux2-klein', 1.0, 4, 'euler', 'normal', 'ugly, studio, posed, artificial', 1024, 1024, 4.2, 'system', ARRAY['street', 'candid', 'lifestyle', 'urban'], true),

-- Product recipes
('00000000-0000-0000-0000-000000000000', 'Clean Product Shot', 'Product on white/marble background', 'product', 'image', 'flux2-dev', 3.5, 20, 'euler', 'normal', 'ugly, blurry, busy background, text', 1024, 1024, 4.6, 'system', ARRAY['product', 'ecommerce', 'clean', 'professional'], true),
('00000000-0000-0000-0000-000000000000', 'Luxury Product', 'Premium product photography with moody lighting', 'product', 'image', 'flux2-dev', 3.5, 25, 'euler', 'normal', 'ugly, cheap, plastic, low quality', 1024, 1024, 4.7, 'system', ARRAY['product', 'luxury', 'premium', 'moody'], true),

-- Landscape recipes
('00000000-0000-0000-0000-000000000000', 'Cinematic Landscape', 'Wide cinematic landscape with dramatic sky', 'landscape', 'image', 'flux2-dev', 3.5, 20, 'euler', 'normal', 'ugly, blurry, flat, boring', 1344, 768, 4.4, 'system', ARRAY['landscape', 'cinematic', 'wide', 'dramatic'], true),

-- Social recipes
('00000000-0000-0000-0000-000000000000', 'Instagram Square', 'Optimized for Instagram feed posts', 'social', 'image', 'flux2-klein', 1.0, 4, 'euler', 'normal', 'ugly, blurry, text, watermark', 1080, 1080, 4.0, 'system', ARRAY['instagram', 'social', 'square', 'feed'], true),
('00000000-0000-0000-0000-000000000000', 'TikTok/Reel', 'Vertical format for short-form video thumbnails', 'social', 'image', 'flux2-klein', 1.0, 4, 'euler', 'normal', 'ugly, blurry, horizontal', 768, 1344, 3.9, 'system', ARRAY['tiktok', 'reel', 'vertical', 'short-form'], true)

ON CONFLICT DO NOTHING;
