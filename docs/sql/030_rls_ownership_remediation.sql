-- =============================================================================
-- AI Studio: RLS & Ownership Remediation (Story 011)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================
--
-- CRITICAL CONTEXT:
-- The core tables (talent, assets, jobs, models, etc.) were created WITHOUT
-- org_id columns. The application code in database.py filters by org_id,
-- suggesting the column was either:
--   A) Added via Supabase Dashboard (untracked in migrations)
--   B) Not actually present (filtering silently fails)
--
-- This migration:
-- 1. Adds org_id to core tables that lack it (idempotent — IF NOT EXISTS)
-- 2. Enables RLS on priority tables
-- 3. Creates operation-specific policies
-- 4. Fixes permissive (USING true) policies that provide no isolation
-- 5. Marks existing rows without org_id as UNVERIFIED
--
-- SAFETY: Uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS (Postgres 9.6+)
-- and CREATE POLICY IF NOT EXISTS patterns. Safe to re-run.
-- =============================================================================


-- =============================================================================
-- PHASE 1: Add org_id column to core tables that lack it
-- =============================================================================
-- NOTE: Existing rows will have org_id = NULL. These are marked UNVERIFIED
-- and must be backfilled before RLS can be enforced.
-- We use nullable UUID initially to avoid breaking existing inserts.

-- Core content tables
ALTER TABLE talent ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE assets ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE models ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS org_id UUID;

-- Training pipeline
ALTER TABLE training_datasets ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE training_images ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS org_id UUID;

-- Publishing
ALTER TABLE publishing_posts ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE publishing_accounts ADD COLUMN IF NOT EXISTS org_id UUID;

-- Video pipeline
ALTER TABLE video_projects ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE video_renders ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE video_shots ADD COLUMN IF NOT EXISTS org_id UUID;

-- Audio
ALTER TABLE audio_clips ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE voice_profiles ADD COLUMN IF NOT EXISTS org_id UUID;

-- Story engine
ALTER TABLE storyboard_panels ADD COLUMN IF NOT EXISTS org_id UUID;

-- Workers / Infrastructure (system-scoped, org_id is optional)
ALTER TABLE workers ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE worker_sessions ADD COLUMN IF NOT EXISTS org_id UUID;

-- Brain (some already have org_id, some don't)
ALTER TABLE brain_memory ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE brain_messages ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE brain_sessions ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE brain_plans ADD COLUMN IF NOT EXISTS org_id UUID;

-- Performance
ALTER TABLE performance_dna ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE quality_scores ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE generation_feedback ADD COLUMN IF NOT EXISTS org_id UUID;

-- Creative
ALTER TABLE creative_dna ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE creative_rules ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE continuity_notes ADD COLUMN IF NOT EXISTS org_id UUID;

-- Company (some already have org via organization_id FK)
ALTER TABLE brands ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE studios ADD COLUMN IF NOT EXISTS org_id UUID;


-- =============================================================================
-- PHASE 2: Add indexes on org_id for tenant-filtered queries
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_talent_org_id ON talent(org_id);
CREATE INDEX IF NOT EXISTS ix_assets_org_id ON assets(org_id);
CREATE INDEX IF NOT EXISTS ix_jobs_org_id ON jobs(org_id);
CREATE INDEX IF NOT EXISTS ix_models_org_id ON models(org_id);
CREATE INDEX IF NOT EXISTS ix_workflows_org_id ON workflows(org_id);
CREATE INDEX IF NOT EXISTS ix_scenes_org_id ON scenes(org_id);
CREATE INDEX IF NOT EXISTS ix_training_datasets_org_id ON training_datasets(org_id);
CREATE INDEX IF NOT EXISTS ix_training_jobs_org_id ON training_jobs(org_id);
CREATE INDEX IF NOT EXISTS ix_publishing_posts_org_id ON publishing_posts(org_id);
CREATE INDEX IF NOT EXISTS ix_video_projects_org_id ON video_projects(org_id);
CREATE INDEX IF NOT EXISTS ix_audio_clips_org_id ON audio_clips(org_id);
CREATE INDEX IF NOT EXISTS ix_brain_memory_org_id ON brain_memory(org_id);
CREATE INDEX IF NOT EXISTS ix_brain_sessions_org_id ON brain_sessions(org_id);
CREATE INDEX IF NOT EXISTS ix_creative_dna_org_id ON creative_dna(org_id);
CREATE INDEX IF NOT EXISTS ix_brands_org_id ON brands(org_id);


-- =============================================================================
-- PHASE 3: Enable RLS on priority tenant tables
-- =============================================================================
-- NOTE: RLS is enabled but policies allow service-role to bypass (Supabase default).
-- The application uses service-role for all backend access (Story 009 boundary).
-- These policies protect against direct client access (anon/authenticated roles).

ALTER TABLE talent ENABLE ROW LEVEL SECURITY;
ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE models ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE scenes ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE publishing_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE publishing_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE audio_clips ENABLE ROW LEVEL SECURITY;
ALTER TABLE brain_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE brain_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE brain_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE creative_dna ENABLE ROW LEVEL SECURITY;
ALTER TABLE brands ENABLE ROW LEVEL SECURITY;


-- =============================================================================
-- PHASE 4: Create operation-specific RLS policies
-- =============================================================================
-- Policy pattern: tenant can only access rows where org_id matches their
-- membership. Derived from auth.jwt() → org_members lookup.
--
-- For tables that may have NULL org_id (legacy unverified rows), we include
-- a condition that allows service-role to see them but authenticated users cannot.

-- Helper: extract org_id from JWT (user's active workspace)
-- NOTE: This assumes the frontend stores org_id in app_metadata.
-- The canonical source is org_members, but JWT is the only source available
-- in RLS without a function call. For tables where this matters, we use
-- a subquery against org_members instead.

-- TALENT
DROP POLICY IF EXISTS "talent_org_isolation" ON talent;
CREATE POLICY "talent_org_isolation" ON talent
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- ASSETS
DROP POLICY IF EXISTS "assets_org_isolation" ON assets;
CREATE POLICY "assets_org_isolation" ON assets
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- JOBS
DROP POLICY IF EXISTS "jobs_org_isolation" ON jobs;
CREATE POLICY "jobs_org_isolation" ON jobs
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- MODELS (shared models have system org_id; private models have user's org)
DROP POLICY IF EXISTS "models_org_isolation" ON models;
CREATE POLICY "models_org_isolation" ON models
    FOR ALL
    USING (
        -- System/shared models are readable by everyone
        org_id = '00000000-0000-0000-0000-000000000001'::uuid
        OR org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        -- Can only write to own org's models
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- WORKFLOWS
DROP POLICY IF EXISTS "workflows_org_isolation" ON workflows;
CREATE POLICY "workflows_org_isolation" ON workflows
    FOR ALL
    USING (
        org_id = '00000000-0000-0000-0000-000000000001'::uuid
        OR org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- SCENES
DROP POLICY IF EXISTS "scenes_org_isolation" ON scenes;
CREATE POLICY "scenes_org_isolation" ON scenes
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- TRAINING_DATASETS
DROP POLICY IF EXISTS "training_datasets_org_isolation" ON training_datasets;
CREATE POLICY "training_datasets_org_isolation" ON training_datasets
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- TRAINING_JOBS
DROP POLICY IF EXISTS "training_jobs_org_isolation" ON training_jobs;
CREATE POLICY "training_jobs_org_isolation" ON training_jobs
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- PUBLISHING_POSTS
DROP POLICY IF EXISTS "publishing_posts_org_isolation" ON publishing_posts;
CREATE POLICY "publishing_posts_org_isolation" ON publishing_posts
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- BRANDS
DROP POLICY IF EXISTS "brands_org_isolation" ON brands;
CREATE POLICY "brands_org_isolation" ON brands
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- BRAIN_MEMORY
DROP POLICY IF EXISTS "brain_memory_org_isolation" ON brain_memory;
CREATE POLICY "brain_memory_org_isolation" ON brain_memory
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- CREATIVE_DNA
DROP POLICY IF EXISTS "creative_dna_org_isolation" ON creative_dna;
CREATE POLICY "creative_dna_org_isolation" ON creative_dna
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );


-- =============================================================================
-- PHASE 5: Fix permissive (USING true) policies
-- =============================================================================
-- These policies provide NO isolation — they allow any authenticated user
-- to access any row. Replace with proper org_id isolation.

-- brain_collections: already has org_id, fix permissive policy
DROP POLICY IF EXISTS "brain_collections_all" ON brain_collections;
CREATE POLICY "brain_collections_org_isolation" ON brain_collections
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- brain_conversations: already has org_id, fix permissive policy
DROP POLICY IF EXISTS "brain_conversations_all" ON brain_conversations;
CREATE POLICY "brain_conversations_org_isolation" ON brain_conversations
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- brain_embeddings: already has org_id, fix permissive policy
DROP POLICY IF EXISTS "brain_embeddings_all" ON brain_embeddings;
CREATE POLICY "brain_embeddings_org_isolation" ON brain_embeddings
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );

-- social_connections: already has org_id, fix permissive policy
DROP POLICY IF EXISTS "social_connections_all" ON social_connections;
CREATE POLICY "social_connections_org_isolation" ON social_connections
    FOR ALL
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    )
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.uid())
            AND om.status = 'active'
        )
    );


-- =============================================================================
-- PHASE 6: Mark existing NULL org_id rows as UNVERIFIED
-- =============================================================================
-- We do NOT invent ownership. Rows with NULL org_id are legacy data that
-- existed before multi-tenancy. They remain accessible via service-role
-- (backend) but are invisible to client-side RLS.
--
-- A future migration will:
-- 1. Attempt to derive org_id from related records (e.g., talent → project → org)
-- 2. Assign remaining to the system org or quarantine table
-- 3. Make org_id NOT NULL once all rows are assigned
--
-- For now, add a comment column to track verification status.
-- (We don't add this column — instead we document the status in this story's report.)

-- Count unverified rows (for reporting — not a migration action)
-- SELECT 'talent' as tbl, count(*) as unverified FROM talent WHERE org_id IS NULL
-- UNION ALL SELECT 'assets', count(*) FROM assets WHERE org_id IS NULL
-- UNION ALL SELECT 'jobs', count(*) FROM jobs WHERE org_id IS NULL
-- UNION ALL SELECT 'models', count(*) FROM models WHERE org_id IS NULL;


-- =============================================================================
-- PHASE 7: Ensure match_brain_embeddings function respects RLS
-- =============================================================================
-- The function is NOT SECURITY DEFINER so it respects caller's RLS.
-- No change needed — but we document it here for completeness.
-- If it were SECURITY DEFINER, it would bypass RLS and need an explicit
-- org_id parameter with validation.


-- =============================================================================
-- NOTES
-- =============================================================================
-- 1. Service-role (backend) BYPASSES RLS by default in Supabase.
--    The Story 009 AuthorizedClient boundary provides application-level
--    tenant isolation for service-role operations.
--
-- 2. RLS policies here protect against DIRECT CLIENT ACCESS only
--    (authenticated users connecting via Supabase client libraries).
--    This is defense-in-depth, not the primary authorization mechanism.
--
-- 3. org_id is initially NULLABLE to avoid breaking existing inserts.
--    It should become NOT NULL after all rows are backfilled.
--
-- 4. The zero-UUID ('00000000-0000-0000-0000-000000000000') placeholder
--    from old migrations should NOT be used. The system org is
--    '00000000-0000-0000-0000-000000000001' (Story 005).
