"""Add compute_availability_config and compute_selective_grants tables.

Implements the compute availability modes (DISABLED/SELECTIVE/ENABLED)
that allow the Founder to control platform-managed compute without code
deployment, architecture changes, or service restart.

State changes propagate via configuration within 60 seconds (service
caches current state with TTL-based refresh).

Implements:
    - R86.1: Compute availability state model (DISABLED/SELECTIVE/ENABLED)
    - R86.2: DISABLED enforcement — 403 regardless of request origin
    - R86.3: SELECTIVE enablement by workspace/plan/cohort/workload/provider/promotion
    - R86.5: State changes via configuration alone (no code deploy, no restart)
    - R13.14: Platform compute cost protection — disabled state blocks all
    - R13.15: No compute without state check
    - R13.16: Founder-controlled compute state

Revision ID: 20260811001
Revises: 20260810003
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260811001"
down_revision: Union[str, None] = "20260810003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create compute_availability_config and compute_selective_grants tables."""
    # =========================================================================
    # 1. Create compute_availability_config table (platform-level, no org_id)
    # =========================================================================
    op.create_table(
        "compute_availability_config",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "state",
            sa.String(20),
            nullable=False,
            comment="Compute availability state: disabled, selective, enabled",
        ),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="User ID of the Founder/operator who changed the state",
        ),
        sa.Column(
            "reason",
            sa.Text(),
            nullable=True,
            comment="Optional reason for the state change",
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="When the state was changed",
        ),
    )

    # CHECK constraint for valid states
    op.execute(sa.text("""
        ALTER TABLE compute_availability_config
        ADD CONSTRAINT ck_compute_availability_state
        CHECK (state IN ('disabled', 'selective', 'enabled'));
    """))

    # Index on changed_at for fetching latest state
    op.create_index(
        "ix_compute_availability_config_changed_at",
        "compute_availability_config",
        ["changed_at"],
    )

    # Insert initial row: DISABLED (safe default)
    op.execute(sa.text("""
        INSERT INTO compute_availability_config (id, state, changed_by, reason, changed_at)
        VALUES (
            gen_random_uuid(),
            'disabled',
            '00000000-0000-0000-0000-000000000000',
            'Initial state — platform compute disabled by default',
            now()
        );
    """))

    # =========================================================================
    # 2. Create compute_selective_grants table (platform-level, no tenant RLS)
    # =========================================================================
    op.create_table(
        "compute_selective_grants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "grant_type",
            sa.String(30),
            nullable=False,
            comment="Type of selective grant: workspace, plan, cohort, workload, provider, promotion",
        ),
        sa.Column(
            "grant_target",
            sa.String(255),
            nullable=False,
            comment="Target identifier: workspace_id, plan_name, cohort_id, workload class, provider name",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="NULL = permanent until revoked",
        ),
        sa.Column(
            "granted_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="User ID of the Founder/operator who created the grant",
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the grant was revoked (NULL = active)",
        ),
        sa.Column(
            "revoked_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="User ID of the operator who revoked the grant",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # CHECK constraint for valid grant types
    op.execute(sa.text("""
        ALTER TABLE compute_selective_grants
        ADD CONSTRAINT ck_compute_selective_grants_type
        CHECK (grant_type IN (
            'workspace', 'plan', 'cohort', 'workload', 'provider', 'promotion'
        ));
    """))

    # Indexes for efficient lookup
    op.create_index(
        "ix_compute_selective_grants_type_target",
        "compute_selective_grants",
        ["grant_type", "grant_target"],
    )
    op.create_index(
        "ix_compute_selective_grants_active",
        "compute_selective_grants",
        ["grant_type", "grant_target"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    # =========================================================================
    # 3. NO tenant RLS — these are platform-level entities
    #    Accessed only by authenticated Platform Operators with Founder Authority
    # =========================================================================
    # Per design: "Platform-level entities use explicit privileged paths with
    # service-role queries, NOT tenant RLS."


def downgrade() -> None:
    """Drop compute_availability_config and compute_selective_grants tables."""
    # Drop compute_selective_grants
    op.drop_index(
        "ix_compute_selective_grants_active",
        table_name="compute_selective_grants",
    )
    op.drop_index(
        "ix_compute_selective_grants_type_target",
        table_name="compute_selective_grants",
    )
    op.drop_table("compute_selective_grants")

    # Drop compute_availability_config
    op.drop_index(
        "ix_compute_availability_config_changed_at",
        table_name="compute_availability_config",
    )
    op.drop_table("compute_availability_config")
