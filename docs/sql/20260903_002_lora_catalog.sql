-- Migration: External LoRA catalog (Civitai/purchased LoRAs for generation)
-- Run in: Supabase Dashboard > SQL Editor
-- Date: 2026-09-03
-- Purpose: index external LoRAs (Civitai downloads, Ko-Fi purchases) that the
-- Create/Advanced settings surface for stacking, with worker file path + model
-- lineage so generation can load them on the GPU worker.

CREATE TABLE IF NOT EXISTS lora_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    -- short slug used on the worker file (e.g. 'HMPenis_v2.0_H3')
    worker_filename TEXT NOT NULL,
    -- Civitai model/version ids (nullable for Ko-Fi/manual)
    civitai_model_id INTEGER,
    civitai_version_id INTEGER,
    -- base model the LoRA targets: 'krea2', 'h3', 'wan2.2', 'flux2', 'sdxl'
    base_model TEXT NOT NULL DEFAULT 'krea2',
    -- model 'lane': 'stills' | 'video' | 'both'
    lane TEXT NOT NULL DEFAULT 'both',
    -- categories/trigger tags for the picker
    tags TEXT[] DEFAULT '{}',
    trigger_words TEXT[] DEFAULT '{}',
    recommended_strength FLOAT DEFAULT 0.7,
    source TEXT DEFAULT 'civitai',          -- civitai | kofi | manual | trained
    purchase_status TEXT DEFAULT 'owned',   -- owned | early_access | gated
    status TEXT DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_lora_catalog_worker_filename ON lora_catalog(worker_filename);
CREATE INDEX IF NOT EXISTS ix_lora_catalog_base_model ON lora_catalog(base_model);
CREATE INDEX IF NOT EXISTS ix_lora_catalog_lane ON lora_catalog(lane);
CREATE INDEX IF NOT EXISTS ix_lora_catalog_status ON lora_catalog(status);
