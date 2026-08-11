-- Ghost Table Migration: assets
-- Documents existing live schema (table created via Dashboard, no prior migration)
-- Date: 2026-08-08
-- Status: ALREADY APPLIED (documents current state for migration ledger)
-- Task: 1.2 (Schema Reconciliation)
-- Validates: Requirements R5.2, R5.5
--
-- NOTE: Do NOT add org_id here — that is Task 3.2.
-- This migration documents the CURRENT live state exactly.

CREATE TABLE IF NOT EXISTS public.assets (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id UUID,
    talent_id UUID,
    type TEXT NOT NULL DEFAULT 'general'::text,
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT 'application/octet-stream'::text,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    storage_provider TEXT NOT NULL DEFAULT 'backblaze_b2'::text,
    storage_key TEXT NOT NULL,
    public_url TEXT,
    thumbnail_url TEXT,
    checksum TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    tags TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT assets_pkey PRIMARY KEY (id)
);

-- Indexes matching live DB
CREATE INDEX IF NOT EXISTS ix_assets_created_at ON public.assets USING btree (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_assets_project_id ON public.assets USING btree (project_id);
CREATE INDEX IF NOT EXISTS ix_assets_talent_id ON public.assets USING btree (talent_id);
CREATE INDEX IF NOT EXISTS ix_assets_type ON public.assets USING btree (type);
