"""Add production_gates table.

Creates the production_gates table for tracking production gate evaluations
and approvals. This is a platform-level table (no org_id) linked to
release_identities.

Implements:
    - R83.1: Bind every release to an immutable Release_Identity
    - R83.2: Required evidence checks before production deployment
    - R83.6: Record gate passage with identity, evidence, timestamp, actor
    - R83.7: Emergency release path with 24h full verification
    - R83.8: Deployment repeatability requirement
    - R83.9: No suppressed errors requirement

Revision ID: 20260823001
Revises: 20260822001
Create Date: 2026-08-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260823001"
down_revision: Union[str, None] = "20260822001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create production_gates table."""
    op.create_table(
        "production_gates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "release_identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="FK to release_identities — binds gate to a specific release",
        ),
        sa.Column(
            "gate_type",
            sa.String(20),
            nullable=False,
            comment="Gate evaluation type: 'full' or 'emergency'",
        ),
        sa.Column(
            "checks",
            postgresql.JSONB,
            nullable=False,
            server_default="'[]'::jsonb",
            comment="JSON array of check results",
        ),
        sa.Column(
            "all_passed",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="Whether all required checks passed",
        ),
        sa.Column(
            "evidence_links",
            postgresql.JSONB,
            nullable=False,
            server_default="'{}'::jsonb",
            comment="JSON object mapping check names to evidence URLs",
        ),
        sa.Column(
            "approving_actor",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="UUID of the user/system that approved the gate",
        ),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the gate was approved",
        ),
        sa.Column(
            "emergency_verification_due",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="For emergency gates: deadline for full verification (24h)",
        ),
        sa.Column(
            "emergency_verified",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="Whether emergency gate completed full post-release verification",
        ),
        sa.Column(
            "failure_summary",
            sa.String(2000),
            nullable=True,
            comment="Human-readable summary of failed checks and remediation paths",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When this gate evaluation was initiated",
        ),
    )

    # Indexes
    op.create_index(
        "ix_production_gates_release_id",
        "production_gates",
        ["release_identity_id"],
    )
    op.create_index(
        "ix_production_gates_created",
        "production_gates",
        ["created_at"],
    )
    op.create_index(
        "ix_production_gates_type",
        "production_gates",
        ["gate_type"],
    )

    # RLS — platform-level table accessed only by admin/owner via service layer
    op.execute("ALTER TABLE production_gates ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY "production_gates_platform_admin"
        ON production_gates
        FOR ALL
        USING (true)
        WITH CHECK (true)
        """
    )


def downgrade() -> None:
    """Drop production_gates table."""
    op.execute("DROP POLICY IF EXISTS \"production_gates_platform_admin\" ON production_gates")
    op.drop_index("ix_production_gates_type", table_name="production_gates")
    op.drop_index("ix_production_gates_created", table_name="production_gates")
    op.drop_index("ix_production_gates_release_id", table_name="production_gates")
    op.drop_table("production_gates")
