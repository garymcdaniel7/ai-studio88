"""JobLease ORM model.

Represents an active lease on a job held by a worker. At most one active
(non-expired) lease exists per job at any time. Workers must present the
lease_token for heartbeat/completion operations (stale worker rejection).

State machine: queued → claimed → running → completed | failed | cancelled | lease_expired
- lease_expired → queued (re-queue if attempt_count < max_attempts)
- lease_expired → failed (if attempt_count >= max_attempts)

Validates: Requirements R21.3, R21.4, R21.5, R21.12, R64.2
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class JobLease(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Job lease entity — represents a worker's exclusive claim on a job.

    Each lease has a unique lease_token that the worker must present for
    heartbeat, progress updates, and result submission. Expired lease holders
    are rejected (stale worker rejection per R21.12).

    Only one active (non-expired) lease per job_id is enforced via a partial
    unique index on (job_id) WHERE lease_expiration > now().
    """

    __tablename__ = "job_leases"

    # Foreign key to jobs table
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Worker identification
    worker_identity: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Identifies the claiming worker (hostname, instance ID, etc.)",
    )

    # Secret token — holder must present this for heartbeat/completion
    lease_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4,
        comment="Secret token the lease holder presents for all operations",
    )

    # Lease timing
    lease_expiration: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When this lease expires if not renewed via heartbeat",
    )

    # Last heartbeat timestamp
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Last heartbeat from the worker holding this lease",
    )

    # Relationship to Job (optional, for convenient navigation)
    job: Mapped["Job"] = relationship("Job", lazy="raise")

    __table_args__ = (
        # Partial unique index: only one active (non-expired) lease per job.
        # This is the primary mechanism preventing double-claiming.
        Index(
            "ix_job_leases_active_job",
            "job_id",
            unique=True,
            postgresql_where=(lease_expiration > func.now()),
        ),
        # Index for finding expired leases during cleanup
        Index(
            "ix_job_leases_expiration",
            "lease_expiration",
        ),
        # Index for org_id (TenantMixin adds the column, we add explicit index)
        Index(
            "ix_job_leases_org_id",
            "org_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<JobLease(id={self.id}, job_id={self.job_id}, "
            f"worker={self.worker_identity}, "
            f"expires={self.lease_expiration})>"
        )
