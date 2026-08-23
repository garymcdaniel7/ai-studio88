"""Add connections table for Connections Hub.

Creates the connections table that models workspace and user integrations
with external services (AI providers, storage, social, compute, developer
tools, business tools). Includes ownership classification, lifecycle state,
auth method, capabilities, access control, and health monitoring.

Implements:
    - R85.1: Connection model with ownership, lifecycle, capabilities
    - R85.3: Connection categories (ai_provider, storage, social, compute, developer, business)
    - R85.4: Auth methods (oauth, api_key, ssh, mcp) with token reference
    - R92.1: Workspace-owned connections persist when members leave
    - R92.2: User-owned connections revoked from workspace on departure
    - R92.3: Ownership classification enforced at schema level

Revision ID: 20260813001
Revises: 20260812001
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260813001"
down_revision: Union[str, None] = "20260812003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create connections table with indexes, constraints, and RLS policies."""
    # =========================================================================
    # 1. Create connections table
    # =========================================================================
    op.create_table(
        "connections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Tenant isolation — workspace that owns this connection",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="NULL for workspace connections, set for user connections",
        ),
        sa.Column(
            "ownership",
            sa.String(20),
            nullable=False,
            comment="Connection ownership: user or workspace",
        ),
        sa.Column(
            "category",
            sa.String(30),
            nullable=False,
            comment="Connection category: ai_provider, storage, social, compute, developer, business",
        ),
        sa.Column(
            "provider_name",
            sa.String(100),
            nullable=False,
            comment="Provider identifier: openai, instagram, runpod, etc.",
        ),
        sa.Column(
            "display_name",
            sa.String(200),
            nullable=False,
            comment="Human-readable display name",
        ),
        sa.Column(
            "lifecycle_state",
            sa.String(30),
            nullable=False,
            server_default="connecting",
            comment="Lifecycle state: connecting, connected, degraded, reauth_required, disconnected, revoked",
        ),
        sa.Column(
            "auth_method",
            sa.String(20),
            nullable=False,
            comment="Auth method: oauth, api_key, ssh, mcp",
        ),
        sa.Column(
            "oauth_token_ref",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Reference to encrypted token in workspace_credentials table",
        ),
        sa.Column(
            "capabilities",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
            comment="Discovered provider capabilities (JSON array)",
        ),
        sa.Column(
            "allowed_roles",
            postgresql.ARRAY(sa.String),
            nullable=False,
            server_default="{owner,admin,editor}",
            comment="Roles allowed to use this connection",
        ),
        sa.Column(
            "tool_policy",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Per-tool allow/deny policy (JSON object)",
        ),
        sa.Column(
            "last_health_check_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of last health check",
        ),
        sa.Column(
            "health_status",
            sa.String(30),
            nullable=True,
            comment="Last health check result: healthy, degraded, unreachable",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # =========================================================================
    # 2. CHECK constraints
    # =========================================================================
    op.execute(sa.text("""
        ALTER TABLE connections
        ADD CONSTRAINT ck_connections_ownership
        CHECK (ownership IN ('user', 'workspace'));
    """))

    op.execute(sa.text("""
        ALTER TABLE connections
        ADD CONSTRAINT ck_connections_lifecycle_state
        CHECK (lifecycle_state IN (
            'connecting', 'connected', 'degraded',
            'reauth_required', 'disconnected', 'revoked'
        ));
    """))

    op.execute(sa.text("""
        ALTER TABLE connections
        ADD CONSTRAINT ck_connections_auth_method
        CHECK (auth_method IN ('oauth', 'api_key', 'ssh', 'mcp'));
    """))

    op.execute(sa.text("""
        ALTER TABLE connections
        ADD CONSTRAINT ck_connections_category
        CHECK (category IN (
            'ai_provider', 'storage', 'social',
            'compute', 'developer', 'business'
        ));
    """))

    # Enforce: user_id MUST be set when ownership = 'user'
    op.execute(sa.text("""
        ALTER TABLE connections
        ADD CONSTRAINT ck_connections_user_ownership
        CHECK (
            (ownership = 'workspace' AND user_id IS NULL)
            OR
            (ownership = 'user' AND user_id IS NOT NULL)
        );
    """))

    # =========================================================================
    # 3. Indexes
    # =========================================================================
    op.create_index(
        "ix_connections_org_id",
        "connections",
        ["org_id"],
    )
    op.create_index(
        "ix_connections_user_id",
        "connections",
        ["user_id"],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_connections_org_category",
        "connections",
        ["org_id", "category"],
    )

    # =========================================================================
    # 4. RLS policies — tenant isolation + user_id filter for USER connections
    # =========================================================================
    op.execute(sa.text("""
        ALTER TABLE connections ENABLE ROW LEVEL SECURITY;
    """))

    # Policy: Users can only see connections in their own org
    op.execute(sa.text("""
        CREATE POLICY connections_tenant_isolation ON connections
            FOR ALL
            USING (org_id = (auth.jwt() ->> 'org_id')::uuid);
    """))

    # Policy: USER connections are only visible to their owner
    # (workspace connections visible to all org members per allowed_roles)
    op.execute(sa.text("""
        CREATE POLICY connections_user_owner_access ON connections
            FOR ALL
            USING (
                ownership = 'workspace'
                OR (ownership = 'user' AND user_id = (auth.jwt() ->> 'sub')::uuid)
            );
    """))

    # =========================================================================
    # 5. updated_at trigger (auto-update on row modification)
    # =========================================================================
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION update_connections_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """))

    op.execute(sa.text("""
        CREATE TRIGGER trg_connections_updated_at
            BEFORE UPDATE ON connections
            FOR EACH ROW
            EXECUTE FUNCTION update_connections_updated_at();
    """))


def downgrade() -> None:
    """Drop connections table and associated objects."""
    # Drop trigger and function
    op.execute(sa.text(
        "DROP TRIGGER IF EXISTS trg_connections_updated_at ON connections;"
    ))
    op.execute(sa.text(
        "DROP FUNCTION IF EXISTS update_connections_updated_at();"
    ))

    # Drop RLS policies
    op.execute(sa.text(
        "DROP POLICY IF EXISTS connections_user_owner_access ON connections;"
    ))
    op.execute(sa.text(
        "DROP POLICY IF EXISTS connections_tenant_isolation ON connections;"
    ))

    # Drop indexes
    op.drop_index("ix_connections_org_category", table_name="connections")
    op.drop_index("ix_connections_user_id", table_name="connections")
    op.drop_index("ix_connections_org_id", table_name="connections")

    # Drop table (CASCADE removes constraints)
    op.drop_table("connections")
