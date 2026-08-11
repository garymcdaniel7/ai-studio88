"""Add social analytics tables for performance intelligence.

Creates tables for social performance analytics and market intelligence:
- social_accounts: Connected social platform accounts
- social_content: Published content items linked to accounts
- social_metric_snapshots: Point-in-time metric observations
- social_watchlists: Named watchlists for competitive intelligence
- social_watchlist_members: Tracked entities within watchlists
- social_derived_insights: Analysis results and recommendations
- social_experiments: A/B content experiments

All tables are workspace-scoped (org_id NOT NULL) with tenant isolation RLS.

Implements:
    - R107.1: Social performance analytics from connected platforms
    - R107.2: Normalized metrics with workspace/account/post associations
    - R43.7: Social analytics in dedicated schema area
    - A2-007: Expanded social intelligence data model

Revision ID: 20260821001
Revises: 20260820002
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260821001"
down_revision: Union[str, None] = "20260820002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create social analytics tables with indexes, constraints, and RLS."""

    # =========================================================================
    # 1. social_accounts
    # =========================================================================
    op.create_table(
        "social_accounts",
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
            comment="Tenant isolation — workspace that owns this account",
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="FK to connections table providing this account",
        ),
        sa.Column(
            "platform",
            sa.String(50),
            nullable=False,
            comment="Platform identifier: instagram, tiktok, youtube",
        ),
        sa.Column(
            "account_external_id",
            sa.String(255),
            nullable=False,
            comment="Platform's unique account identifier",
        ),
        sa.Column(
            "account_name",
            sa.String(255),
            nullable=True,
            comment="Display name on the platform",
        ),
        sa.Column(
            "account_url",
            sa.Text,
            nullable=True,
            comment="URL to the account profile on the platform",
        ),
        sa.Column(
            "capabilities",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="What this account connection can do (JSON object)",
        ),
        sa.Column(
            "sync_state",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Sync lifecycle state: last_sync, cursor, rate_limit_state, etc.",
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

    op.create_index("ix_social_accounts_org_id", "social_accounts", ["org_id"])
    op.create_index(
        "ix_social_accounts_connection_id", "social_accounts", ["connection_id"]
    )
    op.create_index(
        "ix_social_accounts_org_platform", "social_accounts", ["org_id", "platform"]
    )

    # =========================================================================
    # 2. social_content
    # =========================================================================
    op.create_table(
        "social_content",
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
            comment="Tenant isolation",
        ),
        sa.Column(
            "social_account_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="FK to social_accounts table",
        ),
        sa.Column(
            "platform_content_id",
            sa.String(255),
            nullable=False,
            comment="Platform's unique post/content identifier",
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Linked AI Studio asset (if published from here)",
        ),
        sa.Column(
            "talent_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Associated talent entity",
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Associated project",
        ),
        sa.Column(
            "platform",
            sa.String(50),
            nullable=False,
            comment="Platform identifier: instagram, tiktok, youtube",
        ),
        sa.Column(
            "content_type",
            sa.String(50),
            nullable=True,
            comment="Content type: image, video, carousel, story, reel",
        ),
        sa.Column(
            "caption",
            sa.Text,
            nullable=True,
            comment="Post caption/text",
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the content was published on the platform",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Additional platform-specific metadata (JSON)",
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

    op.create_index(
        "ix_social_content_org_platform", "social_content", ["org_id", "platform"]
    )
    op.create_index(
        "ix_social_content_account_id", "social_content", ["social_account_id"]
    )
    op.create_index(
        "ix_social_content_org_talent", "social_content", ["org_id", "talent_id"]
    )
    op.create_index(
        "ix_social_content_published_at", "social_content", ["org_id", "published_at"]
    )

    # =========================================================================
    # 3. social_metric_snapshots
    # =========================================================================
    op.create_table(
        "social_metric_snapshots",
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
            comment="Tenant isolation",
        ),
        sa.Column(
            "social_account_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="FK to social_accounts (account-level metrics)",
        ),
        sa.Column(
            "social_content_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="FK to social_content (content-level metrics)",
        ),
        sa.Column(
            "snapshot_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="When we recorded this observation",
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Metric values: views, likes, comments, shares, reach, etc.",
        ),
        sa.Column(
            "provenance",
            sa.String(50),
            nullable=False,
            comment="Data provenance: FIRST_PARTY_CONNECTED, PUBLIC_PLATFORM_DATA, etc.",
        ),
        sa.Column(
            "collection_method",
            sa.String(50),
            nullable=True,
            comment="How metrics were collected: api_sync, manual_import, public_scrape",
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

    op.create_index(
        "ix_social_metric_snapshots_org_time",
        "social_metric_snapshots",
        ["org_id", "snapshot_at"],
    )
    op.create_index(
        "ix_social_metric_snapshots_content",
        "social_metric_snapshots",
        ["social_content_id", "snapshot_at"],
    )
    op.create_index(
        "ix_social_metric_snapshots_account",
        "social_metric_snapshots",
        ["social_account_id", "snapshot_at"],
    )

    # =========================================================================
    # 4. social_watchlists
    # =========================================================================
    op.create_table(
        "social_watchlists",
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
            comment="Tenant isolation",
        ),
        sa.Column(
            "name",
            sa.String(200),
            nullable=False,
            comment="Watchlist name",
        ),
        sa.Column(
            "description",
            sa.Text,
            nullable=True,
            comment="Watchlist description/purpose",
        ),
        sa.Column(
            "category",
            sa.String(50),
            nullable=True,
            comment="Optional category: competitor, inspiration, industry, etc.",
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

    op.create_index("ix_social_watchlists_org_id", "social_watchlists", ["org_id"])

    # =========================================================================
    # 5. social_watchlist_members
    # =========================================================================
    op.create_table(
        "social_watchlist_members",
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
            comment="Tenant isolation",
        ),
        sa.Column(
            "watchlist_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="FK to social_watchlists",
        ),
        sa.Column(
            "platform",
            sa.String(50),
            nullable=True,
            comment="Platform (NULL = cross-platform)",
        ),
        sa.Column(
            "account_identifier",
            sa.String(255),
            nullable=False,
            comment="@handle, #hashtag, brand name, or topic",
        ),
        sa.Column(
            "display_name",
            sa.String(255),
            nullable=True,
            comment="Human-readable display name for this member",
        ),
        sa.Column(
            "watch_type",
            sa.String(50),
            nullable=False,
            comment="Type: creator, brand, competitor, topic, hashtag",
        ),
        sa.Column(
            "notes",
            sa.Text,
            nullable=True,
            comment="User notes about this watchlist member",
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

    op.create_index(
        "ix_social_watchlist_members_watchlist",
        "social_watchlist_members",
        ["watchlist_id"],
    )
    op.create_index(
        "ix_social_watchlist_members_org",
        "social_watchlist_members",
        ["org_id"],
    )

    # CHECK constraint for watch_type
    op.execute(sa.text("""
        ALTER TABLE social_watchlist_members
        ADD CONSTRAINT ck_social_watchlist_members_watch_type
        CHECK (watch_type IN ('creator', 'brand', 'competitor', 'topic', 'hashtag'));
    """))

    # =========================================================================
    # 6. social_derived_insights
    # =========================================================================
    op.create_table(
        "social_derived_insights",
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
            comment="Tenant isolation",
        ),
        sa.Column(
            "insight_type",
            sa.String(50),
            nullable=False,
            comment="Insight type: trend, anomaly, recommendation, pattern, comparison",
        ),
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Subject entity ID (talent, content, account, watchlist member)",
        ),
        sa.Column(
            "content",
            postgresql.JSONB,
            nullable=False,
            comment="Structured insight data",
        ),
        sa.Column(
            "confidence",
            sa.Numeric(3, 2),
            nullable=True,
            comment="Confidence score 0.00-1.00",
        ),
        sa.Column(
            "source_metrics_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
            comment="References to metric snapshots supporting this insight",
        ),
        sa.Column(
            "provenance",
            sa.String(50),
            nullable=False,
            comment="Provenance: DERIVED_ANALYSIS, AI_INTERPRETATION, STATISTICAL_PATTERN",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this insight becomes stale (NULL = no expiry)",
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

    op.create_index(
        "ix_social_derived_insights_org_type",
        "social_derived_insights",
        ["org_id", "insight_type"],
    )
    op.create_index(
        "ix_social_derived_insights_subject",
        "social_derived_insights",
        ["org_id", "subject_id"],
    )

    # CHECK constraint for insight_type
    op.execute(sa.text("""
        ALTER TABLE social_derived_insights
        ADD CONSTRAINT ck_social_derived_insights_type
        CHECK (insight_type IN ('trend', 'anomaly', 'recommendation', 'pattern', 'comparison'));
    """))

    # CHECK constraint for provenance
    op.execute(sa.text("""
        ALTER TABLE social_derived_insights
        ADD CONSTRAINT ck_social_derived_insights_provenance
        CHECK (provenance IN (
            'DERIVED_ANALYSIS', 'AI_INTERPRETATION',
            'STATISTICAL_PATTERN', 'OBSERVED_FACT'
        ));
    """))

    # =========================================================================
    # 7. social_experiments
    # =========================================================================
    op.create_table(
        "social_experiments",
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
            comment="Tenant isolation",
        ),
        sa.Column(
            "name",
            sa.String(200),
            nullable=False,
            comment="Experiment name",
        ),
        sa.Column(
            "hypothesis",
            sa.Text,
            nullable=False,
            comment="Hypothesis being tested",
        ),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="draft",
            comment="Status: draft, active, observing, completed, cancelled",
        ),
        sa.Column(
            "content_variants",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Content variant descriptions (baseline and variants)",
        ),
        sa.Column(
            "target_metric",
            sa.String(100),
            nullable=True,
            comment="Primary metric being measured",
        ),
        sa.Column(
            "observation_window",
            postgresql.JSONB,
            nullable=True,
            comment="Start/end dates for measurement period",
        ),
        sa.Column(
            "linked_content_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
            comment="social_content rows in this experiment",
        ),
        sa.Column(
            "results",
            postgresql.JSONB,
            nullable=True,
            comment="Experiment results once observation is complete",
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

    op.create_index(
        "ix_social_experiments_org_status",
        "social_experiments",
        ["org_id", "status"],
    )

    # CHECK constraint for status
    op.execute(sa.text("""
        ALTER TABLE social_experiments
        ADD CONSTRAINT ck_social_experiments_status
        CHECK (status IN ('draft', 'active', 'observing', 'completed', 'cancelled'));
    """))

    # =========================================================================
    # 8. RLS policies — workspace-scoped tenant isolation for all tables
    # =========================================================================
    _tables = [
        "social_accounts",
        "social_content",
        "social_metric_snapshots",
        "social_watchlists",
        "social_watchlist_members",
        "social_derived_insights",
        "social_experiments",
    ]

    for table in _tables:
        op.execute(sa.text(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        """))

        # USING clause for SELECT/DELETE
        op.execute(sa.text(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
                FOR ALL
                USING (
                    org_id IN (
                        SELECT om.org_id FROM org_members om
                        WHERE om.user_id = auth.uid()
                        AND om.status = 'active'
                    )
                )
                WITH CHECK (
                    org_id IN (
                        SELECT om.org_id FROM org_members om
                        WHERE om.user_id = auth.uid()
                        AND om.status = 'active'
                    )
                );
        """))

    # =========================================================================
    # 9. updated_at triggers for all tables
    # =========================================================================
    for table in _tables:
        func_name = f"update_{table}_updated_at"
        trigger_name = f"trg_{table}_updated_at"

        op.execute(sa.text(f"""
            CREATE OR REPLACE FUNCTION {func_name}()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = now();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))

        op.execute(sa.text(f"""
            CREATE TRIGGER {trigger_name}
                BEFORE UPDATE ON {table}
                FOR EACH ROW
                EXECUTE FUNCTION {func_name}();
        """))


def downgrade() -> None:
    """Drop all social analytics tables and associated objects."""
    _tables = [
        "social_experiments",
        "social_derived_insights",
        "social_watchlist_members",
        "social_watchlists",
        "social_metric_snapshots",
        "social_content",
        "social_accounts",
    ]

    for table in _tables:
        func_name = f"update_{table}_updated_at"
        trigger_name = f"trg_{table}_updated_at"

        # Drop trigger and function
        op.execute(sa.text(
            f"DROP TRIGGER IF EXISTS {trigger_name} ON {table};"
        ))
        op.execute(sa.text(
            f"DROP FUNCTION IF EXISTS {func_name}();"
        ))

        # Drop RLS policy
        op.execute(sa.text(
            f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};"
        ))

    # Drop tables in reverse dependency order
    for table in _tables:
        op.drop_table(table)
