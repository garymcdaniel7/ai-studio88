"""Add provider_reputation table.

Creates the provider reputation table for persisting per-provider
performance metrics, enabling dynamic ranking and auto-quarantine.

Metrics tracked:
    - Positive signals: startup_latency, queue_latency, generation_duration,
      failure_rate_24h, cost_variance, availability_7d, model_cache_readiness,
      quality_acceptance_rate
    - Negative signals: cleanup_failures, cost_overruns, timeout_rate,
      connection_failures
    - Quarantine: is_quarantined, quarantined_at, quarantine_reason
    - Ranking: overall_score (computed from all metrics)

Implements:
    - R65.1: Per-provider performance metrics
    - R65.2: Negative signal tracking
    - R65.3: Dynamic learned ranking
    - R65.4: Auto-quarantine at >30% failure rate
    - R65.5: Persist to Supabase (survives server restart)
    - R65.6: Expose to Platform Operators for review

Revision ID: 20260820001
Revises: 20260819002
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260820001"
down_revision: Union[str, None] = "20260819002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create provider_reputation table with indexes and RLS."""
    # =========================================================================
    # 1. Create provider_reputation table
    # =========================================================================
    op.create_table(
        "provider_reputation",
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
        # Provider identification
        sa.Column(
            "provider_name",
            sa.String(100),
            nullable=False,
            comment="Compute provider identifier (e.g., 'runpod', 'fluidstack')",
        ),
        sa.Column(
            "provider_type",
            sa.String(50),
            nullable=False,
            server_default="compute",
            comment="Provider type: compute, llm, storage, voice",
        ),
        # Positive signal metrics
        sa.Column(
            "startup_latency_seconds",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Average time to boot/connect (seconds)",
        ),
        sa.Column(
            "queue_latency_seconds",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Average time spent waiting in queue (seconds)",
        ),
        sa.Column(
            "generation_duration_seconds",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Average job execution duration (seconds)",
        ),
        sa.Column(
            "failure_rate_24h",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Rolling 24-hour failure rate (0.0-1.0)",
        ),
        sa.Column(
            "cost_variance",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Average estimate vs actual cost deviation (ratio)",
        ),
        sa.Column(
            "availability_7d",
            sa.Float(),
            nullable=False,
            server_default="1.0",
            comment="7-day rolling availability (0.0-1.0)",
        ),
        sa.Column(
            "model_cache_readiness",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Fraction of required models pre-loaded (0.0-1.0)",
        ),
        sa.Column(
            "quality_acceptance_rate",
            sa.Float(),
            nullable=False,
            server_default="1.0",
            comment="User acceptance rate of outputs (0.0-1.0)",
        ),
        # Negative signal metrics
        sa.Column(
            "cleanup_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of instances not terminated properly",
        ),
        sa.Column(
            "cost_overruns",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of jobs exceeding budget estimate",
        ),
        sa.Column(
            "timeout_rate",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Fraction of jobs that timed out (0.0-1.0)",
        ),
        sa.Column(
            "connection_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of connection failures",
        ),
        # Aggregate counters
        sa.Column(
            "total_jobs",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Total jobs processed",
        ),
        sa.Column(
            "successful_jobs",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Total successful jobs",
        ),
        sa.Column(
            "failed_jobs",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Total failed jobs",
        ),
        sa.Column(
            "total_cost_usd",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Cumulative cost incurred (USD)",
        ),
        # Quarantine
        sa.Column(
            "is_quarantined",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether provider is excluded from dispatch",
        ),
        sa.Column(
            "quarantined_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When quarantine began",
        ),
        sa.Column(
            "quarantine_reason",
            sa.Text(),
            nullable=True,
            comment="Reason for quarantine",
        ),
        # Ranking
        sa.Column(
            "overall_score",
            sa.Float(),
            nullable=False,
            server_default="0.5",
            comment="Computed overall reputation score (0.0-1.0)",
        ),
        # Extended metadata
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=True,
            comment="Extended provider metadata (gpu_type, region, vram_gb)",
        ),
        # Last job timestamp
        sa.Column(
            "last_job_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the last job outcome was recorded",
        ),
        # Timestamps
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

    # =========================================================================
    # 2. Indexes
    # =========================================================================
    op.create_index(
        "ix_provider_reputation_org_id",
        "provider_reputation",
        ["org_id"],
    )
    op.create_index(
        "ix_provider_reputation_org_provider",
        "provider_reputation",
        ["org_id", "provider_name"],
        unique=True,
    )
    op.create_index(
        "ix_provider_reputation_org_score",
        "provider_reputation",
        ["org_id", "overall_score"],
    )
    op.create_index(
        "ix_provider_reputation_quarantined",
        "provider_reputation",
        ["org_id", "is_quarantined"],
    )

    # =========================================================================
    # 3. CHECK constraints
    # =========================================================================
    op.execute(sa.text("""
        ALTER TABLE provider_reputation
        ADD CONSTRAINT ck_provider_reputation_provider_type
        CHECK (provider_type IN ('compute', 'llm', 'storage', 'voice'));
    """))

    # =========================================================================
    # 4. RLS policies
    # =========================================================================
    op.execute(sa.text("""
        ALTER TABLE provider_reputation ENABLE ROW LEVEL SECURITY;
    """))

    op.execute(sa.text("""
        CREATE POLICY "provider_reputation_tenant_isolation"
        ON provider_reputation
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
    """Drop provider_reputation table."""
    # Drop RLS policy
    op.execute(sa.text(
        'DROP POLICY IF EXISTS "provider_reputation_tenant_isolation" ON provider_reputation;'
    ))
    op.execute(sa.text("ALTER TABLE provider_reputation DISABLE ROW LEVEL SECURITY;"))

    # Drop indexes
    op.drop_index("ix_provider_reputation_quarantined", table_name="provider_reputation")
    op.drop_index("ix_provider_reputation_org_score", table_name="provider_reputation")
    op.drop_index("ix_provider_reputation_org_provider", table_name="provider_reputation")
    op.drop_index("ix_provider_reputation_org_id", table_name="provider_reputation")

    # Drop table
    op.drop_table("provider_reputation")
