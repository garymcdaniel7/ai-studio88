"""Add the shared craft library with global/tenant scope enforcement."""

from __future__ import annotations

from alembic import op

revision: str = "20260828001"
down_revision: str | None = "20260827001"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create global craft-only and tenant-owned recipe storage."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS craft_recipes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            "global" BOOLEAN NOT NULL DEFAULT FALSE,
            org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
            model TEXT NOT NULL,
            category TEXT NOT NULL,
            recipe JSONB NOT NULL DEFAULT '{}'::jsonb,
            rating_avg NUMERIC(3, 2) NOT NULL DEFAULT 0,
            uses INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'published',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (("global" = TRUE AND org_id IS NULL) OR ("global" = FALSE AND org_id IS NOT NULL))
        );
        CREATE INDEX IF NOT EXISTS ix_craft_recipes_global_rating
            ON craft_recipes ("global", rating_avg DESC, created_at DESC);
        CREATE INDEX IF NOT EXISTS ix_craft_recipes_org_rating
            ON craft_recipes (org_id, rating_avg DESC, created_at DESC);
        ALTER TABLE craft_recipes ENABLE ROW LEVEL SECURITY;
        ALTER TABLE craft_recipes FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS craft_recipes_visibility ON craft_recipes;
        CREATE POLICY craft_recipes_visibility ON craft_recipes
            FOR SELECT USING (
                "global" = TRUE OR org_id IS NOT NULL
                    AND org_id <> '00000000-0000-0000-0000-000000000000'::uuid
                    AND org_id = (auth.jwt() ->> 'org_id')::uuid
            );
        DROP POLICY IF EXISTS craft_recipes_tenant_write ON craft_recipes;
        CREATE POLICY craft_recipes_tenant_write ON craft_recipes
            FOR ALL USING (
                "global" = TRUE OR org_id IS NOT NULL
                    AND org_id <> '00000000-0000-0000-0000-000000000000'::uuid
                    AND org_id = (auth.jwt() ->> 'org_id')::uuid
            ) WITH CHECK (
                ("global" = TRUE AND org_id IS NULL) OR
                ("global" = FALSE AND org_id IS NOT NULL
                    AND org_id <> '00000000-0000-0000-0000-000000000000'::uuid
                    AND org_id = (auth.jwt() ->> 'org_id')::uuid)
            );
        """
    )


def downgrade() -> None:
    """Remove the craft library table and its policies/indexes."""
    op.execute("DROP TABLE IF EXISTS craft_recipes;")
