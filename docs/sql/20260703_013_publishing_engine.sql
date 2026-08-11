-- =============================================================================
-- AI Studio: Publishing, Social, and Analytics (Priority 8)
-- Run in Supabase Dashboard → SQL Editor
-- =============================================================================

CREATE TABLE IF NOT EXISTS publishing_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    platform TEXT NOT NULL,
    account_name TEXT NOT NULL,
    provider TEXT DEFAULT 'simulation',
    status TEXT DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_pub_accounts_platform ON publishing_accounts(platform);

CREATE TABLE IF NOT EXISTS publishing_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    talent_id UUID REFERENCES talent(id) ON DELETE SET NULL,
    campaign_id UUID,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    account_id UUID REFERENCES publishing_accounts(id) ON DELETE SET NULL,
    platform TEXT NOT NULL,
    post_type TEXT DEFAULT 'image',
    caption TEXT,
    hashtags TEXT[],
    scheduled_for TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    status TEXT DEFAULT 'draft',
    provider TEXT DEFAULT 'simulation',
    provider_post_id TEXT,
    approval_status TEXT DEFAULT 'pending',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_pub_posts_platform ON publishing_posts(platform);
CREATE INDEX ix_pub_posts_status ON publishing_posts(status);
CREATE INDEX ix_pub_posts_scheduled ON publishing_posts(scheduled_for);
CREATE INDEX ix_pub_posts_talent ON publishing_posts(talent_id);

CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID REFERENCES publishing_posts(id) ON DELETE SET NULL,
    platform TEXT,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    reach INTEGER DEFAULT 0,
    impressions INTEGER DEFAULT 0,
    watch_time_seconds INTEGER DEFAULT 0,
    completion_rate FLOAT DEFAULT 0.0,
    click_through_rate FLOAT DEFAULT 0.0,
    follower_delta INTEGER DEFAULT 0,
    revenue_usd FLOAT DEFAULT 0.0,
    engagement_rate FLOAT DEFAULT 0.0,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX ix_analytics_post ON analytics_snapshots(post_id);
CREATE INDEX ix_analytics_platform ON analytics_snapshots(platform);
CREATE INDEX ix_analytics_captured ON analytics_snapshots(captured_at DESC);

CREATE TABLE IF NOT EXISTS platform_packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    platform TEXT NOT NULL,
    aspect_ratio TEXT,
    resolution TEXT,
    duration_seconds FLOAT,
    caption TEXT,
    hashtags TEXT[],
    thumbnail_asset_id UUID,
    meets_requirements BOOLEAN DEFAULT true,
    issues JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_packages_platform ON platform_packages(platform);
CREATE INDEX ix_packages_asset ON platform_packages(asset_id);
