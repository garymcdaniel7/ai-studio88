-- =============================================================================
-- AI Studio: Production Company OS & Multi-Brand (Priority 12)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

-- Organizations (top-level entity)
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE,
    plan TEXT DEFAULT 'starter',
    owner_id UUID,
    logo_asset_id UUID,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Studios (production units within an org)
CREATE TABLE IF NOT EXISTS studios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    focus TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_studios_org ON studios(organization_id);

-- Brands
CREATE TABLE IF NOT EXISTS brands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    studio_id UUID REFERENCES studios(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT,
    logo_asset_id UUID,
    primary_color TEXT,
    secondary_color TEXT,
    brand_voice TEXT,
    visual_identity JSONB DEFAULT '{}',
    preferred_models JSONB DEFAULT '[]',
    preferred_workflows JSONB DEFAULT '[]',
    target_audience TEXT,
    creative_guidelines JSONB DEFAULT '{}',
    approval_rules JSONB DEFAULT '{}',
    publishing_schedule JSONB DEFAULT '{}',
    status TEXT DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_brands_org ON brands(organization_id);
CREATE INDEX ix_brands_studio ON brands(studio_id);

-- Campaigns (multi-brand aware)
CREATE TABLE IF NOT EXISTS brand_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID REFERENCES brands(id) ON DELETE SET NULL,
    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    objective TEXT,
    platforms JSONB DEFAULT '[]',
    budget_usd FLOAT DEFAULT 0.0,
    target_audience TEXT,
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    status TEXT DEFAULT 'planning',
    deliverables JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_brand_campaigns_brand ON brand_campaigns(brand_id);
CREATE INDEX ix_brand_campaigns_status ON brand_campaigns(status);

-- Team members (roles + permissions)
CREATE TABLE IF NOT EXISTS team_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT,
    role TEXT DEFAULT 'viewer',
    permissions JSONB DEFAULT '[]',
    status TEXT DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_team_org ON team_members(organization_id);
CREATE INDEX ix_team_role ON team_members(role);

-- Approval requests
CREATE TABLE IF NOT EXISTS approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    brand_id UUID REFERENCES brands(id) ON DELETE SET NULL,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    requested_by TEXT,
    assigned_to TEXT,
    approval_type TEXT DEFAULT 'creative',
    status TEXT DEFAULT 'pending',
    notes TEXT,
    decided_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_approvals_status ON approval_requests(status);
CREATE INDEX ix_approvals_brand ON approval_requests(brand_id);

-- Clients (future ready)
CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    company TEXT,
    email TEXT,
    phone TEXT,
    brand_guidelines JSONB DEFAULT '{}',
    status TEXT DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_clients_org ON clients(organization_id);

-- Licenses (asset usage tracking)
CREATE TABLE IF NOT EXISTS asset_licenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
    license_type TEXT DEFAULT 'internal',
    usage_scope TEXT DEFAULT 'unlimited',
    expires_at TIMESTAMPTZ,
    holder TEXT,
    copyright_notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_licenses_asset ON asset_licenses(asset_id);
