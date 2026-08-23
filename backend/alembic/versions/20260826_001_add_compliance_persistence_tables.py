"""Add durable quarantine asset indexes and takedown cases.

Revision ID: 20260826001
Revises: 20260825001
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260826001"
down_revision: str | None = "20260825001"
branch_labels: str | Sequence[str] | None = ("compliance_persistence",)
depends_on: str | Sequence[str] | None = None

TAKEDOWN_STATUS = postgresql.ENUM(
    "received",
    "escalated",
    "removed",
    name="takedown_case_status",
    create_type=False,
)


TENANT_POLICY = "org_id IN (SELECT om.org_id FROM org_members om WHERE om.user_id = auth.uid() AND om.status = 'active')"


def upgrade() -> None:
    """Create durable pHash/quarantine state, takedown workflow state, and tenant RLS."""
    TAKEDOWN_STATUS.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "quarantined_assets",
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
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("phash", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=sa.text("'asset-index'")),
        sa.Column("source_type", sa.Text(), nullable=False, server_default=sa.text("'asset'")),
        sa.Column(
            "matched_terms",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_quarantined", sa.Boolean(), nullable=False, server_default=sa.false()),
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
        sa.UniqueConstraint("org_id", "asset_id", name="uq_quarantined_assets_org_asset"),
    )
    op.create_index("ix_quarantined_assets_org_id", "quarantined_assets", ["org_id"])
    op.create_index("ix_quarantined_assets_asset_id", "quarantined_assets", ["asset_id"])
    op.create_index("ix_quarantined_assets_phash", "quarantined_assets", ["phash"])
    op.create_index(
        "ix_quarantined_assets_org_quarantined",
        "quarantined_assets",
        ["org_id", "is_quarantined"],
    )

    op.create_table(
        "takedown_cases",
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
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claimant_email", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", TAKEDOWN_STATUS, nullable=False, server_default=sa.text("'received'")),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "affected_asset_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("sla_breached", sa.Boolean(), nullable=False, server_default=sa.false()),
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
    op.create_index("ix_takedown_cases_org_id", "takedown_cases", ["org_id"])
    op.create_index("ix_takedown_cases_asset_id", "takedown_cases", ["asset_id"])
    op.create_index("ix_takedown_cases_status", "takedown_cases", ["status"])
    op.create_index("ix_takedown_cases_sla_deadline", "takedown_cases", ["sla_deadline_at"])

    for table in ("quarantined_assets", "takedown_cases"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"""
                CREATE POLICY {table}_tenant_isolation ON {table}
                    FOR ALL
                    USING ({TENANT_POLICY})
                    WITH CHECK ({TENANT_POLICY})
                """
            )
        )


def downgrade() -> None:
    """Drop durable compliance tables, policies, indexes, and status enum."""
    for table in ("takedown_cases", "quarantined_assets"):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))

    op.drop_index("ix_takedown_cases_sla_deadline", table_name="takedown_cases")
    op.drop_index("ix_takedown_cases_status", table_name="takedown_cases")
    op.drop_index("ix_takedown_cases_asset_id", table_name="takedown_cases")
    op.drop_index("ix_takedown_cases_org_id", table_name="takedown_cases")
    op.drop_table("takedown_cases")

    op.drop_index("ix_quarantined_assets_org_quarantined", table_name="quarantined_assets")
    op.drop_index("ix_quarantined_assets_phash", table_name="quarantined_assets")
    op.drop_index("ix_quarantined_assets_asset_id", table_name="quarantined_assets")
    op.drop_index("ix_quarantined_assets_org_id", table_name="quarantined_assets")
    op.drop_table("quarantined_assets")
    TAKEDOWN_STATUS.drop(op.get_bind(), checkfirst=True)
