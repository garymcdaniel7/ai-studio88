"""Create the integer consumer-credit ledger.

The existing cost ledger is USD-denominated infrastructure accounting. This
revision creates the separate tenant-scoped integer-credit ledger used for
consumer generation metering.

The repository's historical Alembic directory contains duplicate revision IDs
and broken down-revision references, so this revision is intentionally a
standalone branch. It must be applied by the single migration runner only
after the repository migration graph is repaired or the operator targets this
revision explicitly.

Revision ID: 20260825001
Revises: None
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260825001"
down_revision: str | None = "20260824001"
branch_labels: str | Sequence[str] | None = ("credit_metering",)
depends_on: str | Sequence[str] | None = None


CREDIT_ENTRY_TYPE = sa.Enum(
    "grant",
    "debit",
    "refund",
    "expire",
    name="credit_ledger_entry_type",
)


def upgrade() -> None:
    """Create the tenant-scoped credit ledger, indexes, and RLS policy."""
    CREDIT_ENTRY_TYPE.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "credit_ledger",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_type", CREDIT_ENTRY_TYPE, nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ref_id", sa.Text(), nullable=True),
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
        sa.CheckConstraint("amount <> 0", name="ck_credit_ledger_amount_nonzero"),
        sa.CheckConstraint(
            "balance_after >= 0",
            name="ck_credit_ledger_balance_nonnegative",
        ),
    )

    op.create_index("ix_credit_ledger_org_id", "credit_ledger", ["org_id"])
    op.create_index(
        "ix_credit_ledger_org_created_at",
        "credit_ledger",
        ["org_id", "created_at"],
    )
    op.create_index("ix_credit_ledger_ref_id", "credit_ledger", ["ref_id"])

    op.execute(sa.text("ALTER TABLE credit_ledger ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            """
            CREATE POLICY "credit_ledger_tenant_isolation" ON credit_ledger
                FOR ALL
                USING (org_id IN (
                    SELECT om.org_id FROM org_members om
                    WHERE om.user_id = auth.uid()
                    AND om.status = 'active'
                ))
            """
        )
    )


def downgrade() -> None:
    """Drop the credit ledger policy, table, indexes, and enum type."""
    op.execute(
        sa.text(
            'DROP POLICY IF EXISTS "credit_ledger_tenant_isolation" '
            "ON credit_ledger"
        )
    )
    op.drop_index("ix_credit_ledger_ref_id", table_name="credit_ledger")
    op.drop_index("ix_credit_ledger_org_created_at", table_name="credit_ledger")
    op.drop_index("ix_credit_ledger_org_id", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    CREDIT_ENTRY_TYPE.drop(op.get_bind(), checkfirst=True)
