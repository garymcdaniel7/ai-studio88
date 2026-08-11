"""Add job_leases table and idempotency index on jobs.

Creates the job_leases table for the job leasing system and adds
a partial unique index on jobs(org_id, idempotency_key) for idempotent
job submission deduplication.

Implements:
    - R21.3: Atomic lease with lease_token, worker_identity, lease_expiration
    - R21.11: Idempotency key deduplication
    - R64.2: Atomic tenant-aware claims (no two workers claim same job)
    - R64.4: Job type configurations (workload_class already on jobs table)

Revision ID: 20260810001
Revises: 20260809002
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260810001"
down_revision: Union[str, None] = "20260809002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create job_leases table and add idempotency index on jobs."""
    # =========================================================================
    # 1. Create job_leases table
    # =========================================================================
    op.create_table(
        "job_leases",
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
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "worker_identity",
            sa.String(255),
            nullable=False,
            comment="Identifies the claiming worker (hostname, instance ID, etc.)",
        ),
        sa.Column(
            "lease_token",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Secret token the lease holder presents for all operations",
        ),
        sa.Column(
            "lease_expiration",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When this lease expires if not renewed via heartbeat",
        ),
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Last heartbeat from the worker holding this lease",
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

    # Partial unique index: only one active (non-expired) lease per job
    op.execute(sa.text("""
        CREATE UNIQUE INDEX ix_job_leases_active_job
        ON job_leases (job_id)
        WHERE lease_expiration > now()
    """))

    # Index on lease_expiration for expired lease cleanup queries
    op.create_index(
        "ix_job_leases_expiration",
        "job_leases",
        ["lease_expiration"],
    )

    # Index on org_id for tenant-scoped queries
    op.create_index(
        "ix_job_leases_org_id",
        "job_leases",
        ["org_id"],
    )

    # =========================================================================
    # 2. Add partial unique index on jobs for idempotency key deduplication
    #    Only applies WHERE idempotency_key IS NOT NULL (most jobs won't have one)
    # =========================================================================
    op.execute(sa.text("""
        CREATE UNIQUE INDEX ix_jobs_org_idempotency_key
        ON jobs (org_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
    """))

    # =========================================================================
    # 3. Add index on jobs(status, priority) for efficient claim queries
    #    Used by FOR UPDATE SKIP LOCKED when claiming next job
    # =========================================================================
    op.create_index(
        "ix_jobs_status_priority",
        "jobs",
        ["status", "priority"],
    )

    # =========================================================================
    # 4. Add index on jobs(workload_class) for workload-class filtering
    # =========================================================================
    op.create_index(
        "ix_jobs_workload_class",
        "jobs",
        ["workload_class"],
    )

    # =========================================================================
    # 5. RLS policy for job_leases (tenant isolation)
    # =========================================================================
    op.execute(sa.text("""
        ALTER TABLE job_leases ENABLE ROW LEVEL SECURITY;
    """))

    op.execute(sa.text("""
        CREATE POLICY "job_leases_tenant_isolation"
        ON job_leases
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
    """Drop job_leases table and remove idempotency index from jobs."""
    # Drop RLS policy
    op.execute(sa.text("""
        DROP POLICY IF EXISTS "job_leases_tenant_isolation" ON job_leases;
    """))
    op.execute(sa.text("ALTER TABLE job_leases DISABLE ROW LEVEL SECURITY;"))

    # Drop indexes on jobs
    op.drop_index("ix_jobs_workload_class", table_name="jobs")
    op.drop_index("ix_jobs_status_priority", table_name="jobs")
    op.execute(sa.text("DROP INDEX IF EXISTS ix_jobs_org_idempotency_key;"))

    # Drop job_leases table (cascades indexes)
    op.drop_index("ix_job_leases_org_id", table_name="job_leases")
    op.drop_index("ix_job_leases_expiration", table_name="job_leases")
    op.execute(sa.text("DROP INDEX IF EXISTS ix_job_leases_active_job;"))
    op.drop_table("job_leases")
