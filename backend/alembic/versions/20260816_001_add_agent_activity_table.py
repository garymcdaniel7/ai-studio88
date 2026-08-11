"""Add agent_activity table for user-facing activity feed.

Creates the agent_activity table to store a human-readable log of what
Brain/Hermes did on behalf of the user. Separate from engineering/debug
logs and system observability data.

Activity types:
    recommendation, tool_call, job_dispatch, approval_request,
    connection_use, change_made, failure, cost_incurred

Implements:
    - R99.1: Human-readable agent activity history
    - R99.2: Separate from engineering/debug logs
    - R99.3: Scoped to requesting user's sessions and workspace
    - R99.4: Each entry includes timestamp, action type, outcome, cost
    - R30.15: User-facing agent activity history

Revision ID: 20260816001
Revises: 20260815001
Create Date: 2026-08-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260816001"
down_revision: Union[str, None] = "20260815001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create agent_activity table with indexes and RLS."""
    op.create_table(
        "agent_activity",
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
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "activity_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "summary",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "detail",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "outcome",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Check constraint for valid activity types
        sa.CheckConstraint(
            "activity_type IN ("
            "'recommendation', 'tool_call', 'job_dispatch', "
            "'approval_request', 'connection_use', 'change_made', "
            "'failure', 'cost_incurred'"
            ")",
            name="ck_agent_activity_type",
        ),
    )

    # Composite index for user feed queries (org + user + time desc)
    op.create_index(
        "ix_agent_activity_org_user_created",
        "agent_activity",
        ["org_id", "user_id", sa.text("created_at DESC")],
    )

    # Index for filtering by activity type within an org
    op.create_index(
        "ix_agent_activity_org_type",
        "agent_activity",
        ["org_id", "activity_type"],
    )

    # Enable RLS
    op.execute("ALTER TABLE agent_activity ENABLE ROW LEVEL SECURITY")

    # RLS policy: users can only see activity in their org
    op.execute(
        """
        CREATE POLICY "agent_activity_org_isolation"
        ON agent_activity
        FOR ALL
        USING (org_id = (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid()
            AND om.status = 'active'
            LIMIT 1
        ))
        WITH CHECK (org_id = (
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = auth.uid()
            AND om.status = 'active'
            LIMIT 1
        ))
        """
    )


def downgrade() -> None:
    """Drop agent_activity table and its RLS policy."""
    op.execute(
        "DROP POLICY IF EXISTS \"agent_activity_org_isolation\" ON agent_activity"
    )
    op.drop_index("ix_agent_activity_org_type", table_name="agent_activity")
    op.drop_index("ix_agent_activity_org_user_created", table_name="agent_activity")
    op.drop_table("agent_activity")
