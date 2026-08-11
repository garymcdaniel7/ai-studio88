"""Add notifications table.

Creates the notifications table for in-app notification delivery
with per-category preferences and mandatory notification enforcement.

Categories:
    - job_completed, job_failed
    - approval_requested, approval_resolved
    - connection_expired, provider_unavailable
    - publishing_result, budget_threshold
    - safety_action (MANDATORY), hermes_needs_input

Implements:
    - R101.1: Canonical notification model with categories
    - R101.2: In-app canonical delivery channel
    - R101.3: Per-category preferences with mandatory override

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
    """Create notifications table with indexes and RLS."""
    op.create_table(
        "notifications",
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
            comment="Target user for this notification",
        ),
        sa.Column(
            "category",
            sa.Text(),
            nullable=False,
            comment="Notification category (job_completed, safety_action, etc.)",
        ),
        sa.Column(
            "title",
            sa.Text(),
            nullable=False,
            comment="Short notification title",
        ),
        sa.Column(
            "body",
            sa.Text(),
            nullable=True,
            comment="Extended notification body",
        ),
        sa.Column(
            "action_url",
            sa.Text(),
            nullable=True,
            comment="Deep link within the application",
        ),
        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether the user has read this notification",
        ),
        sa.Column(
            "is_mandatory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Mandatory notifications (safety, takedown) cannot be disabled",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Additional structured data (job_id, asset_id, etc.)",
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

    # CHECK constraint for category values
    op.execute(sa.text("""
        ALTER TABLE notifications
        ADD CONSTRAINT ck_notifications_category
        CHECK (category IN (
            'job_completed', 'job_failed',
            'approval_requested', 'approval_resolved',
            'connection_expired', 'provider_unavailable',
            'publishing_result', 'budget_threshold',
            'safety_action', 'hermes_needs_input'
        ));
    """))

    # Indexes
    op.create_index(
        "ix_notifications_org_user",
        "notifications",
        ["org_id", "user_id"],
    )
    op.create_index(
        "ix_notifications_org_user_unread",
        "notifications",
        ["org_id", "user_id", "is_read"],
    )
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["org_id", "user_id", "created_at"],
    )

    # RLS
    op.execute(sa.text("""
        ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
    """))

    op.execute(sa.text("""
        CREATE POLICY "notifications_tenant_isolation"
        ON notifications
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
    """Drop notifications table."""
    op.execute(sa.text(
        'DROP POLICY IF EXISTS "notifications_tenant_isolation" ON notifications;'
    ))
    op.execute(sa.text("ALTER TABLE notifications DISABLE ROW LEVEL SECURITY;"))

    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_index("ix_notifications_org_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_org_user", table_name="notifications")
    op.drop_table("notifications")
