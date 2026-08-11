"""Add workspace_privacy_config table.

Per-workspace privacy restriction configuration. Controls which providers
and infrastructure a workspace's data can flow through. Restriction types
include: local_models_only, customer_compute_only, approved_llm_only,
no_external_llm_for_project, approved_storage_only,
talent_provider_restriction, project_privacy.

Brain/Hermes, LLM routing, job dispatch, and all execution paths
respect these restrictions.

Implements:
    - R103.1: Workspace-level privacy and provider restrictions
    - R103.2: All execution paths check restrictions
    - R103.3: Appropriate error when restrictions prevent fulfillment

Revision ID: 20260817001
Revises: 20260816001
Create Date: 2026-08-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260817001"
down_revision: Union[str, None] = "20260816001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create workspace_privacy_config table."""
    op.create_table(
        "workspace_privacy_config",
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
            comment="Organisation owning this privacy restriction",
        ),
        sa.Column(
            "restriction_type",
            sa.Text(),
            nullable=False,
            comment="Type of privacy restriction being applied",
        ),
        sa.Column(
            "restriction_target",
            sa.Text(),
            nullable=True,
            comment="Optional target (project_id, talent_id) for scoped restrictions. NULL = workspace-wide.",
        ),
        sa.Column(
            "allowed_providers",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
            comment="Provider names explicitly allowed (whitelist). Empty = no whitelist filter.",
        ),
        sa.Column(
            "denied_providers",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
            comment="Provider names explicitly denied (blocklist).",
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

    # CHECK constraint for valid restriction types
    op.execute(sa.text("""
        ALTER TABLE workspace_privacy_config
        ADD CONSTRAINT ck_workspace_privacy_config_restriction_type
        CHECK (restriction_type IN (
            'local_models_only',
            'customer_compute_only',
            'approved_llm_only',
            'no_external_llm_for_project',
            'approved_storage_only',
            'talent_provider_restriction',
            'project_privacy'
        ));
    """))

    # Index on org_id for tenant-scoped queries
    op.create_index(
        "ix_workspace_privacy_config_org_id",
        "workspace_privacy_config",
        ["org_id"],
    )

    # Composite index for type-based lookup within a workspace
    op.create_index(
        "ix_workspace_privacy_config_org_type",
        "workspace_privacy_config",
        ["org_id", "restriction_type"],
    )

    # ==========================================================================
    # RLS: Tenant-scoped. Admin/owner only for writes.
    # Per design: "workspace_privacy_config | Tenant RLS (org_id) |
    # Admin/owner only for writes"
    # ==========================================================================
    op.execute(sa.text(
        "ALTER TABLE workspace_privacy_config ENABLE ROW LEVEL SECURITY;"
    ))
    op.execute(sa.text("""
        CREATE POLICY "tenant_isolation" ON workspace_privacy_config
            FOR ALL
            USING (org_id IN (
                SELECT om.org_id FROM org_members om
                WHERE om.user_id = auth.uid() AND om.status = 'active'
            ))
            WITH CHECK (org_id IN (
                SELECT om.org_id FROM org_members om
                WHERE om.user_id = auth.uid() AND om.status = 'active'
            ));
    """))


def downgrade() -> None:
    """Drop workspace_privacy_config table."""
    op.drop_index(
        "ix_workspace_privacy_config_org_type",
        table_name="workspace_privacy_config",
    )
    op.drop_index(
        "ix_workspace_privacy_config_org_id",
        table_name="workspace_privacy_config",
    )
    op.drop_table("workspace_privacy_config")
