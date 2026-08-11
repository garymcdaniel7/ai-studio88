-- Asset Lifecycle Extension Migration
-- Extends the existing `assets` table for full lifecycle management.
-- Date: 2026-08-15
-- Task: 11.2 (Asset metadata and lifecycle management)
-- Validates: Requirements R11.3, R11.5, R11.6, R11.7, R11.9, R11.10
--
-- Changes:
--   1. Add org_id NOT NULL column (required for tenant isolation)
--   2. Add job_id column (links asset to generation/training job)
--   3. Add deleted_at column (soft-delete support per R11.5)
--   4. Add asset_type column (image, video, audio, model, training)
--   5. Add content_type column (normalized MIME type per R11.9)
--   6. Add checksum_sha256 column (content integrity verification)
--   7. Add indexes for org-scoped queries
--   8. Create pending_asset_deletions table for async cleanup (R11.5)
--
-- NOTES:
--   - The base `assets` table was created in 20260808_002_ghost_table_assets.sql
--   - This migration ADDS columns rather than recreating the table.
--   - org_id backfill should be completed before applying NOT NULL constraint
--     (per R69 quarantine process).

-- ═══════════════════════════════════════════════════════════════════════════════
-- 1. Add org_id column (nullable first, then backfill + constrain)
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.assets
    ADD COLUMN IF NOT EXISTS org_id UUID;

-- NOTE: After backfilling org_id values, apply:
-- ALTER TABLE public.assets ALTER COLUMN org_id SET NOT NULL;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 2. Add job_id column
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.assets
    ADD COLUMN IF NOT EXISTS job_id UUID;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 3. Add deleted_at column for soft-delete (R11.5)
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.assets
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 4. Add asset_type column (normalized from existing 'type' column)
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.assets
    ADD COLUMN IF NOT EXISTS asset_type TEXT NOT NULL DEFAULT 'image';

-- ═══════════════════════════════════════════════════════════════════════════════
-- 5. Add content_type column (maps from existing 'mime_type' column)
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.assets
    ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'application/octet-stream';

-- Backfill content_type from existing mime_type
UPDATE public.assets
SET content_type = mime_type
WHERE content_type = 'application/octet-stream' AND mime_type IS NOT NULL;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 6. Add checksum_sha256 column
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.assets
    ADD COLUMN IF NOT EXISTS checksum_sha256 TEXT;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 7. Add indexes for tenant-scoped queries
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS ix_assets_org_id
    ON public.assets(org_id);

CREATE INDEX IF NOT EXISTS ix_assets_org_talent
    ON public.assets(org_id, talent_id);

CREATE INDEX IF NOT EXISTS ix_assets_org_job
    ON public.assets(org_id, job_id);

CREATE INDEX IF NOT EXISTS ix_assets_org_asset_type
    ON public.assets(org_id, asset_type);

-- Partial index excluding soft-deleted records
CREATE INDEX IF NOT EXISTS ix_assets_org_active
    ON public.assets(org_id, created_at DESC)
    WHERE deleted_at IS NULL;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 8. Create pending_asset_deletions table (R11.5)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.pending_asset_deletions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    org_id UUID NOT NULL,
    storage_key TEXT NOT NULL,
    storage_provider TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    error TEXT,

    CONSTRAINT fk_pending_deletions_asset
        FOREIGN KEY (asset_id) REFERENCES public.assets(id)
);

CREATE INDEX IF NOT EXISTS ix_pending_deletions_unprocessed
    ON public.pending_asset_deletions(scheduled_at)
    WHERE processed_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_pending_deletions_org
    ON public.pending_asset_deletions(org_id);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 9. RLS policies for assets table (tenant isolation, R11.10)
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.assets ENABLE ROW LEVEL SECURITY;

-- Users can only see/modify assets in their own org
CREATE POLICY "asset_org_isolation" ON public.assets
    FOR ALL
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);

-- RLS on pending deletions
ALTER TABLE public.pending_asset_deletions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "pending_deletions_org_isolation" ON public.pending_asset_deletions
    FOR ALL
    USING (org_id = (auth.jwt() ->> 'org_id')::uuid)
    WITH CHECK (org_id = (auth.jwt() ->> 'org_id')::uuid);
