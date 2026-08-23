"""Add tenant voice-profile references used by the local lip-sync layer."""

from __future__ import annotations

from alembic import op

revision: str = "20260829001"
down_revision: str | None = "20260828001"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create or extend voice_profiles without replacing legacy voice data."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS voice_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
            character TEXT NOT NULL DEFAULT '',
            tts_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
            sample_ref TEXT,
            talent_id UUID,
            name TEXT,
            provider TEXT,
            provider_voice_id TEXT,
            settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        ALTER TABLE voice_profiles ADD COLUMN IF NOT EXISTS org_id UUID;
        ALTER TABLE voice_profiles ADD COLUMN IF NOT EXISTS character TEXT NOT NULL DEFAULT '';
        ALTER TABLE voice_profiles ADD COLUMN IF NOT EXISTS tts_ref JSONB NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE voice_profiles ADD COLUMN IF NOT EXISTS sample_ref TEXT;
        CREATE INDEX IF NOT EXISTS ix_voice_profiles_org_character
            ON voice_profiles (org_id, character);
        ALTER TABLE voice_profiles ENABLE ROW LEVEL SECURITY;
        ALTER TABLE voice_profiles FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS voice_profiles_tenant_isolation ON voice_profiles;
        CREATE POLICY voice_profiles_tenant_isolation ON voice_profiles
            FOR ALL USING (org_id IS NOT NULL
                AND org_id <> '00000000-0000-0000-0000-000000000000'::uuid
                AND org_id = (auth.jwt() ->> 'org_id')::uuid) WITH CHECK (org_id IS NOT NULL
                AND org_id <> '00000000-0000-0000-0000-000000000000'::uuid
                AND org_id = (auth.jwt() ->> 'org_id')::uuid);
        """
    )


def downgrade() -> None:
    """Remove only the additive policy/index; preserve legacy voice profile rows."""
    op.execute(
        """
        DROP POLICY IF EXISTS voice_profiles_tenant_isolation ON voice_profiles;
        DROP INDEX IF EXISTS ix_voice_profiles_org_character;
        """
    )
