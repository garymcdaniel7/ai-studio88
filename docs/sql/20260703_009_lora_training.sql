-- =============================================================================
-- AI Studio: LoRA Training tables (Priority 4)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

-- Training Datasets
CREATE TABLE IF NOT EXISTS training_datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    image_count INTEGER DEFAULT 0,
    storage_prefix TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_training_datasets_talent ON training_datasets(talent_id);
CREATE INDEX ix_training_datasets_status ON training_datasets(status);

-- Training Images (per dataset)
CREATE TABLE IF NOT EXISTS training_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID NOT NULL REFERENCES training_datasets(id) ON DELETE CASCADE,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    storage_key TEXT,
    caption TEXT,
    tags TEXT[],
    quality_score FLOAT DEFAULT 1.0,
    included BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_training_images_dataset ON training_images(dataset_id);
CREATE INDEX ix_training_images_included ON training_images(included);

-- Training Jobs
CREATE TABLE IF NOT EXISTS training_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    dataset_id UUID REFERENCES training_datasets(id) ON DELETE SET NULL,
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    base_model_id UUID REFERENCES models(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    training_provider TEXT DEFAULT 'simulation',
    worker_id UUID,
    config JSONB DEFAULT '{}',
    output_lora_asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    output_model_id UUID REFERENCES models(id) ON DELETE SET NULL,
    logs TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_training_jobs_talent ON training_jobs(talent_id);
CREATE INDEX ix_training_jobs_status ON training_jobs(status);
CREATE INDEX ix_training_jobs_dataset ON training_jobs(dataset_id);

-- LoRA Versions
CREATE TABLE IF NOT EXISTS lora_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    model_id UUID REFERENCES models(id) ON DELETE SET NULL,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    version INTEGER DEFAULT 1,
    name TEXT NOT NULL,
    trigger_words TEXT[],
    base_model TEXT,
    recommended_strength FLOAT DEFAULT 0.7,
    status TEXT DEFAULT 'active',
    training_job_id UUID REFERENCES training_jobs(id) ON DELETE SET NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_lora_versions_talent ON lora_versions(talent_id);
CREATE INDEX ix_lora_versions_status ON lora_versions(status);

-- LoRA Evaluations
CREATE TABLE IF NOT EXISTS lora_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lora_version_id UUID NOT NULL REFERENCES lora_versions(id) ON DELETE CASCADE,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    identity_score FLOAT,
    realism_score FLOAT,
    flexibility_score FLOAT,
    notes TEXT,
    test_asset_ids JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_lora_evaluations_version ON lora_evaluations(lora_version_id);
