"""Add support_sessions table for time-limited tenant access.

Platform Operators can request time-limited, scope-limited access to
tenant workspaces for support purposes. Sessions auto-expire and are
fully auditable.

Session lifecycle: REQUESTED → APPROVED → ACTIVE → EXPIRED/ENDED/REVOKED

Key constraints:
    - Auto-expires at expires_at (never becomes permanent membership)
    - Revocable immediately by Founder or approving operator
    - Scope-limited to permitted_surfaces and permitted_actions
    - Full audit trail via platform_operator_actions
    - Does NOT grant RLS bypass

NOTE: This table does NOT use tenant RLS — it is a platform-level entity
accessible only to authenticated Platform Operators with the
tenant_access_escalation or founder_authority capability.

Implements:
    - R33.8: Time-limited elevated access (audited, expiring)
    - R33.9: All operator actions logged with full audit trail
    - R97.5: No unrestricted permanent access to private content
    - R97.6: All operator actions logged
    - A2-006: Tenant support session architecture

Revision ID: 20260815001
Revises: 20260814001
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260815001"
down_revision: Union[str, None] = "20260814001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create support_sessions table."""
    op.create_table(
        "support_sessions",
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
            comment="Platform Operator requesting/holding the session",
        ),
        sa.Column(
            "target_org_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization/workspace being accessed",
        ),
        sa.Column(
            "reason",
            sa.Text(),
            nullable=False,
            comment="Documented reason for elevated access",
        ),
        sa.Column(
            "requested_capabilities",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            comment="Capabilities the operator asked for",
        ),
        sa.Column(
            "approved_capabilities",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            comment="Capabilities actually granted (may be subset)",
        ),
        sa.Column(
            "permitted_surfaces",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            comment=(
                "Data surfaces accessible during session: "
                "e.g. talent_metadata, job_history, cost_records"
            ),
        ),
        sa.Column(
            "permitted_actions",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            comment=(
                "Actions allowed during session: "
                "e.g. view, pause_job, revoke_connection"
            ),
        ),
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Operator who approved the escalation (NULL if pending)",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="When the session was created/requested",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Auto-expiration timestamp (max 4 hours default)",
        ),
        sa.Column(
            "ended_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Explicit early termination timestamp",
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'requested'"),
            comment="Session lifecycle status",
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
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'active', 'expired', 'revoked', 'completed')",
            name="ck_support_sessions_status",
        ),
    )

    # Index for finding sessions by operator
    op.create_index(
        "ix_support_sessions_operator",
        "support_sessions",
        ["operator_user_id"],
    )

    # Index for finding sessions targeting an org
    op.create_index(
        "ix_support_sessions_org",
        "support_sessions",
        ["target_org_id"],
    )

    # Partial index for quick lookup of active sessions
    op.execute(sa.text("""
        CREATE INDEX ix_support_sessions_active
        ON support_sessions (status)
        WHERE status = 'active';
    """))


def downgrade() -> None:
    """Drop support_sessions table."""
    op.execute(sa.text("DROP INDEX IF EXISTS ix_support_sessions_active;"))
    op.drop_index("ix_support_sessions_org", table_name="support_sessions")
    op.drop_index("ix_support_sessions_operator", table_name="support_sessions")
    op.drop_table("support_sessions")
