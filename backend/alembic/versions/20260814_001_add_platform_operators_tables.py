"""Add platform_operators and platform_operator_actions tables.

Creates the capability-based Platform Operator model replacing
the undifferentiated Super Admin. Platform Operators receive
granular capability grants (not god-role access).

Capability groups:
    - Platform Observe
    - Tenant Support
    - Tenant Access Escalation
    - Platform Configuration
    - Financial Controls
    - Safety & Rights
    - Security Administration
    - Deployment/Operations
    - Release Management
    - Destructive Platform Actions
    - Founder Authority

NOTE: These tables do NOT use tenant RLS — they are platform-level
entities accessible only to authenticated Platform Operators with
appropriate capability grants.

Implements:
    - R33.5: Capability-based model with 11 groups
    - R33.6: Subset grants (not all operators need equal access)
    - R33.7: Founder retains broadest capability set
    - R97.1: Replace Super Admin concept
    - R97.2: Define capability groups
    - R97.3: Subset assignment
    - R97.4: Founder broadest set

Revision ID: 20260814001
Revises: 20260813001
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260814001"
down_revision: Union[str, None] = "20260813001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create platform_operators and platform_operator_actions tables."""
    # =========================================================================
    # platform_operators — active operator grants
    # =========================================================================
    op.create_table(
        "platform_operators",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Authenticated user who is granted operator capabilities",
        ),
        sa.Column(
            "capability_grants",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            comment="Array of capability group names granted to this operator",
        ),
        sa.Column(
            "granted_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="User who granted these capabilities (typically Founder)",
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="When capabilities were granted",
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When capabilities were revoked (NULL = active)",
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

    # Partial unique index: only one active (non-revoked) operator record per user
    op.execute(sa.text("""
        CREATE UNIQUE INDEX uq_platform_operators_active_user
        ON platform_operators (user_id)
        WHERE revoked_at IS NULL;
    """))

    # Index for user lookups
    op.create_index(
        "ix_platform_operators_user_id",
        "platform_operators",
        ["user_id"],
    )

    # =========================================================================
    # platform_operator_actions — full audit trail
    # =========================================================================
    op.create_table(
        "platform_operator_actions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "operator_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="The operator who performed the action",
        ),
        sa.Column(
            "capability_used",
            sa.Text(),
            nullable=False,
            comment="Which capability group authorized this action",
        ),
        sa.Column(
            "target_org_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Target tenant (if action is tenant-scoped)",
        ),
        sa.Column(
            "action_type",
            sa.Text(),
            nullable=False,
            comment="Type of action performed",
        ),
        sa.Column(
            "action_detail",
            postgresql.JSONB(),
            nullable=True,
            comment="Structured detail about the action",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Indexes for querying audit trail
    op.create_index(
        "ix_po_actions_operator",
        "platform_operator_actions",
        ["operator_user_id"],
    )
    op.create_index(
        "ix_po_actions_org",
        "platform_operator_actions",
        ["target_org_id"],
    )
    op.create_index(
        "ix_po_actions_created",
        "platform_operator_actions",
        ["created_at"],
    )


def downgrade() -> None:
    """Drop platform operator tables."""
    op.drop_index("ix_po_actions_created", table_name="platform_operator_actions")
    op.drop_index("ix_po_actions_org", table_name="platform_operator_actions")
    op.drop_index("ix_po_actions_operator", table_name="platform_operator_actions")
    op.drop_table("platform_operator_actions")

    op.drop_index("ix_platform_operators_user_id", table_name="platform_operators")
    op.execute(sa.text(
        "DROP INDEX IF EXISTS uq_platform_operators_active_user;"
    ))
    op.drop_table("platform_operators")
