-- =============================================================================
-- AI Studio: Models, LoRAs, and Workflow Templates (Priority 2)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

-- AI Models (checkpoints, LoRAs, VAEs, ControlNets, etc.)
CREATE TABLE IF NOT EXISTS models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    family TEXT NOT NULL DEFAULT 'flux',
    type TEXT NOT NULL DEFAULT 'checkpoint',
    provider TEXT,
    storage_path TEXT,
    local_path TEXT,
    version TEXT DEFAULT '1.0',
    required_vram_gb FLOAT DEFAULT 12.0,
    supported_resolutions JSONB DEFAULT '[]',
    supported_tasks JSONB DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'available',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_models_family ON models(family);
CREATE INDEX ix_models_type ON models(type);
CREATE INDEX ix_models_status ON models(status);

-- type: checkpoint, lora, vae, controlnet, ipadapter, upscaler, embedding
-- status: available, downloading, unavailable, deprecated

-- Workflow Templates (stored ComfyUI workflows)
CREATE TABLE IF NOT EXISTS workflow_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    category TEXT DEFAULT 'image',
    provider TEXT DEFAULT 'comfyui',
    required_models JSONB DEFAULT '[]',
    parameters JSONB DEFAULT '{}',
    workflow_json JSONB DEFAULT '{}',
    version TEXT DEFAULT '1.0',
    status TEXT DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_wf_templates_category ON workflow_templates(category);
CREATE INDEX ix_wf_templates_provider ON workflow_templates(provider);
CREATE INDEX ix_wf_templates_status ON workflow_templates(status);

-- category: image, video, upscale, training, editing, voice
-- status: active, draft, deprecated
