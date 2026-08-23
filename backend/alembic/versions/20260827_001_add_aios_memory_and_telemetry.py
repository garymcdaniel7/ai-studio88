"""Add tenant AIOS memory and generation telemetry tables."""

from __future__ import annotations

from alembic import op

revision: str = "20260827001"
down_revision: str | None = "20260826001"
branch_labels: tuple[str, ...] = ("aios_studio_craft",)
depends_on: str | None = None


def upgrade() -> None:
    """Create tenant-isolated memory and generation event records."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS aios_memory (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (org_id, key)
        );
        CREATE INDEX IF NOT EXISTS ix_aios_memory_org_updated
            ON aios_memory (org_id, updated_at DESC);
        ALTER TABLE aios_memory ENABLE ROW LEVEL SECURITY;
        ALTER TABLE aios_memory FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS aios_memory_tenant_isolation ON aios_memory;
        CREATE POLICY aios_memory_tenant_isolation ON aios_memory
            FOR ALL USING (org_id IS NOT NULL
                AND org_id <> '00000000-0000-0000-0000-000000000000'::uuid
                AND org_id = (auth.jwt() ->> 'org_id')::uuid) WITH CHECK (org_id IS NOT NULL
                AND org_id <> '00000000-0000-0000-0000-000000000000'::uuid
                AND org_id = (auth.jwt() ->> 'org_id')::uuid);

        CREATE TABLE IF NOT EXISTS generation_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            model TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            params JSONB NOT NULL DEFAULT '{}'::jsonb,
            seed BIGINT,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_generation_events_org_created
            ON generation_events (org_id, created_at DESC);
        ALTER TABLE generation_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE generation_events FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS generation_events_tenant_isolation ON generation_events;
        CREATE POLICY generation_events_tenant_isolation ON generation_events
            FOR ALL USING (org_id IS NOT NULL
                AND org_id <> '00000000-0000-0000-0000-000000000000'::uuid
                AND org_id = (auth.jwt() ->> 'org_id')::uuid) WITH CHECK (org_id IS NOT NULL
                AND org_id <> '00000000-0000-0000-0000-000000000000'::uuid
                AND org_id = (auth.jwt() ->> 'org_id')::uuid);

        CREATE TABLE IF NOT EXISTS recipe_ratings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            generation_event_id UUID NOT NULL REFERENCES generation_events(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            note TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_recipe_ratings_event_created
            ON recipe_ratings (generation_event_id, created_at DESC);
        ALTER TABLE recipe_ratings ENABLE ROW LEVEL SECURITY;
        ALTER TABLE recipe_ratings FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS recipe_ratings_tenant_isolation ON recipe_ratings;
        CREATE POLICY recipe_ratings_tenant_isolation ON recipe_ratings
            FOR ALL USING (generation_event_id IN (
                SELECT ge.id FROM generation_events ge
                WHERE ge.org_id IS NOT NULL
                  AND ge.org_id <> '00000000-0000-0000-0000-000000000000'::uuid
                  AND ge.org_id = (auth.jwt() ->> 'org_id')::uuid
            )) WITH CHECK (generation_event_id IN (
                SELECT ge.id FROM generation_events ge
                WHERE ge.org_id IS NOT NULL
                  AND ge.org_id <> '00000000-0000-0000-0000-000000000000'::uuid
                  AND ge.org_id = (auth.jwt() ->> 'org_id')::uuid
            ));
        """
    )


def downgrade() -> None:
    """Remove telemetry and memory objects created by this revision."""
    op.execute("DROP TABLE IF EXISTS recipe_ratings; DROP TABLE IF EXISTS generation_events; DROP TABLE IF EXISTS aios_memory;")
