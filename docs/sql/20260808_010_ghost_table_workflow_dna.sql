-- Ghost Table Migration: workflow_dna
-- Documents existing live schema (table created via code, no prior migration)
-- Date: 2026-08-08
-- Status: ALREADY APPLIED (documents current state for migration ledger)
-- Task: 1.2 (Schema Reconciliation)
-- Validates: Requirements R5.2, R5.5
--
-- NOTE: This table already HAS org_id (nullable, defaults to quarantined UUID).
-- The NOT NULL constraint and proper default will be addressed in Task 3.2.
-- This migration documents the CURRENT live state exactly.

CREATE TABLE IF NOT EXISTS public.workflow_dna (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    org_id UUID DEFAULT '00000000-0000-0000-0000-000000000000'::uuid,
    name TEXT NOT NULL DEFAULT ''::text,
    content_type TEXT NOT NULL DEFAULT 'image'::text,
    checkpoint TEXT DEFAULT ''::text,
    loras JSONB DEFAULT '[]'::jsonb,
    sampler TEXT DEFAULT 'euler'::text,
    scheduler TEXT DEFAULT 'normal'::text,
    cfg NUMERIC DEFAULT 7.0,
    steps INTEGER DEFAULT 20,
    width INTEGER DEFAULT 1024,
    height INTEGER DEFAULT 1024,
    negative_prompt TEXT DEFAULT ''::text,
    quality_score NUMERIC DEFAULT 0,
    success_rate NUMERIC DEFAULT 0,
    usage_count INTEGER DEFAULT 0,
    avg_generation_time NUMERIC DEFAULT 0,
    avg_cost NUMERIC DEFAULT 0,
    recommended_for TEXT[] DEFAULT '{}'::text[],
    talent_id UUID,
    source TEXT DEFAULT 'auto_learned'::text,
    config_snapshot JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT workflow_dna_pkey PRIMARY KEY (id)
);

-- Indexes matching live DB
CREATE INDEX IF NOT EXISTS ix_workflow_dna_content_type ON public.workflow_dna USING btree (content_type);
CREATE INDEX IF NOT EXISTS ix_workflow_dna_quality ON public.workflow_dna USING btree (quality_score DESC);
CREATE INDEX IF NOT EXISTS ix_workflow_dna_talent ON public.workflow_dna USING btree (talent_id);
