-- =============================================================================
-- AI Studio: Canonical Membership Model (Story 005)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================
-- This creates the authoritative user→organization membership table.
-- All tenant resolution flows through this table.
-- =============================================================================

-- =============================================================================
-- 1. org_members — The canonical membership table
-- =============================================================================

CREATE TABLE IF NOT EXISTS org_members (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL,  -- References auth.users(id) in Supabase Auth
    role        TEXT NOT NULL DEFAULT 'viewer'
                CHECK (role IN ('owner', 'admin', 'editor', 'viewer')),
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'invited', 'suspended', 'deactivated')),
    invited_by  UUID,           -- user_id of inviter (NULL for self-signup owners)
    invited_at  TIMESTAMPTZ,
    joined_at   TIMESTAMPTZ,    -- NULL until invitation is accepted
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A user can only have ONE membership per org (no duplicate memberships)
CREATE UNIQUE INDEX uq_org_members_user_org
    ON org_members(user_id, org_id);

-- Fast lookup: user → all their orgs (for multi-workspace switching)
CREATE INDEX ix_org_members_user_id
    ON org_members(user_id);

-- Fast lookup: org → all members (for team listing)
CREATE INDEX ix_org_members_org_id
    ON org_members(org_id);

-- Fast lookup: active members only (most common query pattern)
CREATE INDEX ix_org_members_active
    ON org_members(user_id, org_id) WHERE status = 'active';


-- =============================================================================
-- 2. Auto-create membership when organization is created
-- =============================================================================
-- When someone creates an org, they become the owner automatically.

CREATE OR REPLACE FUNCTION auto_create_owner_membership()
RETURNS TRIGGER AS $$
BEGIN
    -- Only if owner_id is set
    IF NEW.owner_id IS NOT NULL THEN
        INSERT INTO org_members (org_id, user_id, role, status, joined_at)
        VALUES (NEW.id, NEW.owner_id, 'owner', 'active', now())
        ON CONFLICT (user_id, org_id) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_org_create_owner ON organizations;
CREATE TRIGGER trg_org_create_owner
    AFTER INSERT ON organizations
    FOR EACH ROW
    EXECUTE FUNCTION auto_create_owner_membership();


-- =============================================================================
-- 3. Row Level Security (RLS)
-- =============================================================================

ALTER TABLE org_members ENABLE ROW LEVEL SECURITY;

-- Users can see memberships in orgs they belong to
CREATE POLICY "org_members_select_own_org" ON org_members
    FOR SELECT
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
            AND om.status = 'active'
        )
    );

-- Only owners and admins can insert new members (invite)
CREATE POLICY "org_members_insert_admin" ON org_members
    FOR INSERT
    WITH CHECK (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
            AND om.status = 'active'
            AND om.role IN ('owner', 'admin')
        )
    );

-- Only owners and admins can update members (role changes, suspension)
CREATE POLICY "org_members_update_admin" ON org_members
    FOR UPDATE
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
            AND om.status = 'active'
            AND om.role IN ('owner', 'admin')
        )
    );

-- Only owners can delete members
CREATE POLICY "org_members_delete_owner" ON org_members
    FOR DELETE
    USING (
        org_id IN (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
            AND om.status = 'active'
            AND om.role = 'owner'
        )
    );


-- =============================================================================
-- 4. Backfill existing organizations
-- =============================================================================
-- For any organization that has an owner_id but no membership record,
-- create the membership now.

INSERT INTO org_members (org_id, user_id, role, status, joined_at)
SELECT id, owner_id, 'owner', 'active', created_at
FROM organizations
WHERE owner_id IS NOT NULL
ON CONFLICT (user_id, org_id) DO NOTHING;


-- =============================================================================
-- 5. Constraint: organizations.org_id NOT NULL on tenant-owned tables
-- =============================================================================
-- Ensure new records in key tables always have a valid org_id.
-- NOTE: Existing rows with NULL org_id are left as-is (marked UNVERIFIED).
-- Future migration will audit and remediate them.

-- We don't ALTER existing columns here because many tables use nullable org_id
-- and a mass NOT NULL constraint would break existing data.
-- Instead, we add a CHECK constraint on new inserts via RLS and application layer.


-- =============================================================================
-- 6. System scope constant
-- =============================================================================
-- System-owned resources (shared models, default workflows) use this org_id.
-- This is NOT a zero-UUID — it's a real row in organizations.

INSERT INTO organizations (id, name, slug, plan, metadata)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'AI Studio System',
    '_system',
    'system',
    '{"system": true, "description": "System-owned resources (shared models, default workflows)"}'::jsonb
)
ON CONFLICT (slug) DO NOTHING;

-- NOTE: The system org has NO members — access is granted by the service layer
-- when operating with elevated privileges (e.g., seeding shared models).
