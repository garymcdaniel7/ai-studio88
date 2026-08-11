"""Add cost_reservations and cost_entries tables.

Creates the cost reservation and immutable cost ledger tables for the
atomic cost reservation and reconciliation system.

Three-tier cost classification:
    - customer_infrastructure: customer-owned compute (informational)
    - platform_expense: AI Studio's own operational costs
    - managed_compute: platform-managed compute charged to tenant

Implements:
    - R14.1: Cost estimation before job execution
    - R14.2: Cost reservation against budget
    - R14.12: Three-tier cost classification
    - R66.1: Atomic budget reservation

Revision ID: 20260810003
Revises: 20260810002
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260810003"
down_revision: Union[str, None] = "20260810002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create cost_reservations and cost_entries tables."""
    # =========================================================================
    # 1. Create cost_reservations table
    # =========================================================================
    op.create_table(
        "cost_reservations",
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
            "job_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Associated job (NULL for non-job cost reservations)",
        ),
        sa.Column(
            "operation",
            sa.Text(),
            nullable=False,
            comment="Operation that will incur the cost",
        ),
        sa.Column(
            "reserved_amount_usd",
            sa.Numeric(10, 4),
            nullable=False,
            comment="Estimated cost reserved (USD)",
        ),
        sa.Column(
            "actual_amount_usd",
            sa.Numeric(10, 4),
            nullable=True,
            comment="Actual cost after reconciliation (USD)",
        ),
        sa.Column(
            "cost_classification",
            sa.String(30),
            nullable=False,
            server_default="managed_compute",
            comment="Three-tier classification: customer_infrastructure, platform_expense, managed_compute",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="Reservation lifecycle: active, committed, finalized, released, expired",
        ),
        sa.Column(
            "provider",
            sa.String(100),
            nullable=True,
            comment="Provider that incurs this cost",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Reservation expires if not finalized by this time",
        ),
        sa.Column(
            "finalized_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the reservation was reconciled with actual cost",
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

    # CHECK constraints
    op.execute(sa.text("""
        ALTER TABLE cost_reservations
        ADD CONSTRAINT ck_cost_reservations_classification
        CHECK (cost_classification IN (
            'customer_infrastructure', 'platform_expense', 'managed_compute'
        ));
    """))

    op.execute(sa.text("""
        ALTER TABLE cost_reservations
        ADD CONSTRAINT ck_cost_reservations_status
        CHECK (status IN (
            'active', 'committed', 'finalized', 'released', 'expired'
        ));
    """))

    # Indexes
    op.create_index(
        "ix_cost_reservations_org_id",
        "cost_reservations",
        ["org_id"],
    )
    op.create_index(
        "ix_cost_reservations_job_id",
        "cost_reservations",
        ["job_id"],
    )
    op.create_index(
        "ix_cost_reservations_org_status",
        "cost_reservations",
        ["org_id", "status"],
    )

    # =========================================================================
    # 2. Create cost_entries table (immutable — no updated_at)
    # =========================================================================
    op.create_table(
        "cost_entries",
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
            "job_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Associated job",
        ),
        sa.Column(
            "reservation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Associated cost reservation",
        ),
        sa.Column(
            "entry_type",
            sa.String(30),
            nullable=False,
            comment="Type of cost event: reservation, commitment, actual, release, refund, reconciliation",
        ),
        sa.Column(
            "amount_usd",
            sa.Numeric(10, 4),
            nullable=False,
            comment="Cost amount in USD (negative for releases/refunds)",
        ),
        sa.Column(
            "operation",
            sa.Text(),
            nullable=False,
            comment="Operation that incurred the cost",
        ),
        sa.Column(
            "provider",
            sa.String(100),
            nullable=True,
            comment="Provider that incurred the cost",
        ),
        sa.Column(
            "cost_classification",
            sa.String(30),
            nullable=False,
            server_default="managed_compute",
            comment="Three-tier classification",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Human-readable description of the cost event",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # CHECK constraints
    op.execute(sa.text("""
        ALTER TABLE cost_entries
        ADD CONSTRAINT ck_cost_entries_entry_type
        CHECK (entry_type IN (
            'reservation', 'commitment', 'actual', 'release', 'refund', 'reconciliation'
        ));
    """))

    op.execute(sa.text("""
        ALTER TABLE cost_entries
        ADD CONSTRAINT ck_cost_entries_classification
        CHECK (cost_classification IN (
            'customer_infrastructure', 'platform_expense', 'managed_compute'
        ));
    """))

    # Indexes
    op.create_index(
        "ix_cost_entries_org_id",
        "cost_entries",
        ["org_id"],
    )
    op.create_index(
        "ix_cost_entries_job_id",
        "cost_entries",
        ["job_id"],
    )
    op.create_index(
        "ix_cost_entries_reservation_id",
        "cost_entries",
        ["reservation_id"],
    )
    op.create_index(
        "ix_cost_entries_org_created",
        "cost_entries",
        ["org_id", "created_at"],
    )

    # =========================================================================
    # 3. RLS policies for both tables
    # =========================================================================
    op.execute(sa.text("""
        ALTER TABLE cost_reservations ENABLE ROW LEVEL SECURITY;
    """))

    op.execute(sa.text("""
        CREATE POLICY "cost_reservations_tenant_isolation"
        ON cost_reservations
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

    op.execute(sa.text("""
        ALTER TABLE cost_entries ENABLE ROW LEVEL SECURITY;
    """))

    op.execute(sa.text("""
        CREATE POLICY "cost_entries_tenant_isolation"
        ON cost_entries
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
    """Drop cost_reservations and cost_entries tables."""
    # Drop RLS policies
    op.execute(sa.text(
        'DROP POLICY IF EXISTS "cost_entries_tenant_isolation" ON cost_entries;'
    ))
    op.execute(sa.text("ALTER TABLE cost_entries DISABLE ROW LEVEL SECURITY;"))

    op.execute(sa.text(
        'DROP POLICY IF EXISTS "cost_reservations_tenant_isolation" ON cost_reservations;'
    ))
    op.execute(sa.text("ALTER TABLE cost_reservations DISABLE ROW LEVEL SECURITY;"))

    # Drop cost_entries indexes and table
    op.drop_index("ix_cost_entries_org_created", table_name="cost_entries")
    op.drop_index("ix_cost_entries_reservation_id", table_name="cost_entries")
    op.drop_index("ix_cost_entries_job_id", table_name="cost_entries")
    op.drop_index("ix_cost_entries_org_id", table_name="cost_entries")
    op.drop_table("cost_entries")

    # Drop cost_reservations indexes and table
    op.drop_index("ix_cost_reservations_org_status", table_name="cost_reservations")
    op.drop_index("ix_cost_reservations_job_id", table_name="cost_reservations")
    op.drop_index("ix_cost_reservations_org_id", table_name="cost_reservations")
    op.drop_table("cost_reservations")
