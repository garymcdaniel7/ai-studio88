"""Add feature_rollouts table.

Platform-level configuration table for feature rollout controls.
Allows Founder/Platform Operators to enable or disable capabilities
by scope (global, plan, workspace, cohort, user, workload, provider)
without requiring code deployment.

NOT tenant-scoped — platform-level entity managed exclusively by
Platform Operators with Platform Configuration capability.

Implements:
    - R106.1: Rollout by plan, workspace, cohort, user, workload, provider
    - R106.2: Feature rollout applies to platform-managed GPU, hybrid, adult, etc.
    - R106.3: DISABLED capabilities inaccessible through ALL surfaces
    - R19.9: DISABLED state handling
    - R19.10: Feature rollout controls without code deployment

Revision ID: 20260816001
Revises: 20260815001
Create Date: 2026-08-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260816002"
down_revision: Union[str, None] = "20260816001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create feature_rollouts table."""
    op.create_table(
        "feature_rollouts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "capability_name",
            sa.Text(),
            nullable=False,
            comment="Name of the capability being controlled",
        ),
        sa.Column(
            "rollout_scope",
            sa.Text(),
            nullable=False,
            comment="Scope of the rollout rule: global, plan, workspace, cohort, user, workload, provider",
        ),
        sa.Column(
            "scope_target",
            sa.Text(),
            nullable=True,
            comment="Target identifier for the scope (plan name, workspace_id, user_id, etc.). NULL for global scope.",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether the capability is enabled (true) or disabled (false) for this scope/target",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this rollout rule expires. NULL = permanent until deleted.",
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="User ID of the operator who created this rollout rule",
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

    # CHECK constraint for valid rollout scopes
    op.execute(sa.text("""
        ALTER TABLE feature_rollouts
        ADD CONSTRAINT ck_feature_rollouts_scope
        CHECK (rollout_scope IN (
            'global', 'plan', 'workspace', 'cohort', 'user', 'workload', 'provider'
        ));
    """))

    # Index on capability_name for lookup
    op.create_index(
        "ix_feature_rollouts_capability_name",
        "feature_rollouts",
        ["capability_name"],
    )

    # Composite index for scope queries
    op.create_index(
        "ix_feature_rollouts_capability_scope",
        "feature_rollouts",
        ["capability_name", "rollout_scope"],
    )

    # ==========================================================================
    # NO tenant RLS — this is a platform-level entity.
    # Accessed only by authenticated Platform Operators with Platform
    # Configuration capability. Per design: "Platform-level entities use
    # explicit privileged paths with service-role queries, NOT tenant RLS."
    # ==========================================================================


def downgrade() -> None:
    """Drop feature_rollouts table."""
    op.drop_index(
        "ix_feature_rollouts_capability_scope",
        table_name="feature_rollouts",
    )
    op.drop_index(
        "ix_feature_rollouts_capability_name",
        table_name="feature_rollouts",
    )
    op.drop_table("feature_rollouts")
