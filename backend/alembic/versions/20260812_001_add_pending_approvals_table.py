"""Add pending_approvals table for governance approval workflow.

Creates the pending_approvals table for the AIOS governance boundary
approval workflow. Actions that require human confirmation create
records here; approvals expire after 24 hours without action.

Protected action types:
  - delete_permanent: Hard-delete any resource
  - spend_over_threshold: Estimated cost > $5
  - launch_workers_bulk: 3+ simultaneous GPU workers
  - publish_social: Post to external social platforms
  - clone_voice: Voice cloning operations
  - destructive_tool: Any tool classified as "destructive"

Implements:
    - R30.1: AIOS governance approval model
    - R30.2: Action classification for approval gates
    - R30.3: Approval expiry (24h default)
    - R30.4: Approve/reject lifecycle
    - R30.5: Tenant-scoped approval isolation
    - R30.6: Approver role enforcement
    - R30.7: Audit trail for all approval decisions

Revision ID: 20260812001
Revises: 20260811001
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260812001"
down_revision: Union[str, None] = "20260811001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create pending_approvals table with indexes and RLS."""
    op.create_table(
        "pending_approvals",
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
            comment="Tenant isolation — workspace that owns this approval",
        ),
        sa.Column(
            "requesting_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="User who triggered the action requiring approval",
        ),
        sa.Column(
            "action_type",
            sa.Text(),
            nullable=False,
            comment="Type of action requiring approval (e.g., delete_permanent, spend_over_threshold)",
        ),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
            comment="Estimated cost in USD for paid actions",
        ),
        sa.Column(
            "parameters",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Action parameters (sanitized — no secrets)",
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="Approval lifecycle state",
        ),
        sa.Column(
            "resolved_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="User who approved or rejected",
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the approval was resolved",
        ),
        sa.Column(
            "rejection_reason",
            sa.Text(),
            nullable=True,
            comment="Reason for rejection (if rejected)",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Approval expires if not acted upon by this time",
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

    # CHECK constraint for status values
    op.execute(sa.text("""
        ALTER TABLE pending_approvals
        ADD CONSTRAINT ck_pending_approvals_status
        CHECK (status IN ('pending', 'approved', 'rejected', 'expired'));
    """))

    # Indexes
    op.create_index(
        "ix_pending_approvals_org_status",
        "pending_approvals",
        ["org_id", "status"],
    )
    op.create_index(
        "ix_pending_approvals_requesting_user",
        "pending_approvals",
        ["requesting_user_id"],
    )
    op.create_index(
        "ix_pending_approvals_expires_at",
        "pending_approvals",
        ["expires_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # RLS
    op.execute(sa.text("""
        ALTER TABLE pending_approvals ENABLE ROW LEVEL SECURITY;
    """))

    op.execute(sa.text("""
        CREATE POLICY "pending_approvals_tenant_isolation"
        ON pending_approvals
        FOR ALL
        USING (org_id = (
            SELECT om.org_id
            FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
              AND om.status = 'active'
            LIMIT 1
        ))
        WITH CHECK (org_id = (
            SELECT om.org_id
            FROM org_members om
            WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
              AND om.status = 'active'
            LIMIT 1
        ));
    """))


def downgrade() -> None:
    """Drop pending_approvals table."""
    op.execute(sa.text(
        'DROP POLICY IF EXISTS "pending_approvals_tenant_isolation" ON pending_approvals;'
    ))
    op.execute(sa.text("ALTER TABLE pending_approvals DISABLE ROW LEVEL SECURITY;"))

    op.drop_index(
        "ix_pending_approvals_expires_at", table_name="pending_approvals"
    )
    op.drop_index(
        "ix_pending_approvals_requesting_user", table_name="pending_approvals"
    )
    op.drop_index(
        "ix_pending_approvals_org_status", table_name="pending_approvals"
    )
    op.drop_table("pending_approvals")
