-- =============================================================================
-- AI Studio: Creative DNA + Feedback tables (Sprint 7)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

-- Creative DNA: stores learned preferences per talent
CREATE TABLE IF NOT EXISTS creative_dna (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    talent_id UUID REFERENCES talent(id) ON DELETE CASCADE,
    preferred_styles JSONB DEFAULT '[]',
    avoided_styles JSONB DEFAULT '[]',
    color_palette JSONB DEFAULT '[]',
    camera_preferences JSONB DEFAULT '{}',
    wardrobe_preferences JSONB DEFAULT '{}',
    setting_preferences JSONB DEFAULT '{}',
    prompt_rules JSONB DEFAULT '[]',
    negative_prompt_rules JSONB DEFAULT '[]',
    lora_preferences JSONB DEFAULT '{}',
    model_preferences JSONB DEFAULT '{}',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_creative_dna_talent_id ON creative_dna(talent_id);
CREATE INDEX ix_creative_dna_project_id ON creative_dna(project_id);

-- Generation feedback: user ratings on outputs
CREATE TABLE IF NOT EXISTS generation_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    problems TEXT[],
    notes TEXT,
    context JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_gen_feedback_talent ON generation_feedback(talent_id);
CREATE INDEX ix_gen_feedback_job ON generation_feedback(job_id);
CREATE INDEX ix_gen_feedback_rating ON generation_feedback(rating);

-- Prompt history: tracks prompts and their outcomes
CREATE TABLE IF NOT EXISTS prompt_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    model TEXT,
    positive_prompt TEXT NOT NULL,
    negative_prompt TEXT,
    prompt_metadata JSONB DEFAULT '{}',
    result_rating INTEGER,
    result_problems TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_prompt_history_talent ON prompt_history(talent_id);
CREATE INDEX ix_prompt_history_model ON prompt_history(model);
CREATE INDEX ix_prompt_history_rating ON prompt_history(result_rating);

-- Style preferences: learned atomic preferences
CREATE TABLE IF NOT EXISTS style_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    talent_id UUID REFERENCES talent(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    preference_key TEXT NOT NULL,
    preference_value TEXT NOT NULL,
    confidence FLOAT DEFAULT 0.5,
    sample_count INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(talent_id, category, preference_key)
);

CREATE INDEX ix_style_prefs_talent ON style_preferences(talent_id);
