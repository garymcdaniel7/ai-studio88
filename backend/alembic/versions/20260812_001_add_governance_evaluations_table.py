"""Add governance_evaluations table for audit logging.

Creates the governance_evaluations table for persisting all
governance boundary evaluation records. Every AI-initiated side
effect must have a governance_evaluation record before execution.

Implements:
    - R59.6: Every evaluation logged with full context
    - R59.7: All AI-initiated side effects auditable

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
    """Create governance_evaluations table."""
    op.create_table(
        "governance_evaluations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "evaluation_id",
            sa.Text(),
            nullable=False,
            comment="Unique evaluation ID from GovernanceResult (eval-<hex>)",
        ),
        sa.Column(
            "correlation_id",
            sa.Text(),
            nullable=True,
            comment="Request correlation ID for observability (gov-<hex>)",
        ),
        sa.Column(
            "action_type",
            sa.Text(),
            nullable=False,
            comment="What action was being evaluated",
        ),
        sa.Column(
            "identity",
            sa.Text(),
            nullable=True,
            comment="Who/what requested the action (user_id or service identity)",
        ),
        sa.Column(
            "trust_domain",
            sa.Text(),
            nullable=True,
            comment="Trust domain of the requestor",
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Tenant org_id (NULL for system/unauthenticated evaluations)",
        ),
        sa.Column(
            "role",
            sa.Text(),
            nullable=True,
            comment="Role of the requestor within the tenant",
        ),
        sa.Column(
            "risk_classification",
            sa.Text(),
            nullable=False,
            comment="Risk level: read_only, low_impact, medium_impact, high_impact, destructive",
        ),
        sa.Column(
            "decision",
            sa.Text(),
            nullable=False,
            comment="Governance decision: allow, deny, require_approval",
        ),
        sa.Column(
            "denial_reason",
            sa.Text(),
            nullable=True,
            comment="Human-readable reason for denial/approval requirement",
        ),
        sa.Column(
            "required_approval_type",
            sa.Text(),
            nullable=True,
            comment="Type of approval required (if decision=require_approval)",
        ),
        sa.Column(
            "is_degraded",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Whether the evaluation ran in degraded mode",
        ),
        sa.Column(
            "failed_checks",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment="List of checks that failed or were unavailable",
        ),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(10, 4),
            nullable=True,
            comment="Estimated cost of the action in USD",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Indexes
    op.create_index(
        "ix_governance_evaluations_org_created",
        "governance_evaluations",
        ["org_id", "created_at"],
    )
    op.create_index(
        "ix_governance_evaluations_evaluation_id",
        "governance_evaluations",
        ["evaluation_id"],
        unique=True,
    )
    op.create_index(
        "ix_governance_evaluations_action_decision",
        "governance_evaluations",
        ["action_type", "decision"],
    )

    # RLS
    op.execute(sa.text(
        "ALTER TABLE governance_evaluations ENABLE ROW LEVEL SECURITY;"
    ))

    op.execute(sa.text("""
        CREATE POLICY "governance_evaluations_tenant_isolation"
        ON governance_evaluations
        FOR ALL
        USING (
            org_id IS NULL
            OR org_id = (
                SELECT om.org_id
                FROM org_members om
                WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
                  AND om.status = 'active'
                LIMIT 1
            )
        )
        WITH CHECK (
            org_id IS NULL
            OR org_id = (
                SELECT om.org_id
                FROM org_members om
                WHERE om.user_id = (auth.jwt() ->> 'sub')::uuid
                  AND om.status = 'active'
                LIMIT 1
            )
        );
    """))


def downgrade() -> None:
    """Drop governance_evaluations table."""
    op.execute(sa.text(
        'DROP POLICY IF EXISTS "governance_evaluations_tenant_isolation"'
        " ON governance_evaluations;"
    ))
    op.execute(sa.text(
        "ALTER TABLE governance_evaluations DISABLE ROW LEVEL SECURITY;"
    ))

    op.drop_index(
        "ix_governance_evaluations_action_decision",
        table_name="governance_evaluations",
    )
    op.drop_index(
        "ix_governance_evaluations_evaluation_id",
        table_name="governance_evaluations",
    )
    op.drop_index(
        "ix_governance_evaluations_org_created",
        table_name="governance_evaluations",
    )
    op.drop_table("governance_evaluations")
