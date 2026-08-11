"""Cost ORM models: CostReservation and CostEntry.

CostReservation represents an atomic pre-execution budget hold against a
tenant's entitlement. Reservations follow the lifecycle:
    active → committed → finalized | released | expired

CostEntry is an immutable ledger record of actual cost events. Entries are
never updated — they are append-only for audit integrity.

Three-tier cost classification:
    - customer_infrastructure: customer-owned compute (informational, not budgeted)
    - platform_expense: AI Studio's own operational costs (internal)
    - managed_compute: platform-managed compute charged to tenant (budgeted)

Validates: Requirements R14.1, R14.2, R14.12, R66.1
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class CostReservation(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Cost reservation — an atomic budget hold created before job execution.

    Always scoped to org_id. Cross-tenant access returns 404.
    Reservations expire at expires_at if not finalized or released.

    Status lifecycle: active → committed → finalized | released | expired
    """

    __tablename__ = "cost_reservations"

    # Reference to the job this reservation covers (optional for non-job costs)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # What operation this reservation covers
    operation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Reserved amount (pre-execution estimate)
    reserved_amount_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
    )

    # Actual amount (post-execution reconciliation)
    actual_amount_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    # Three-tier classification
    cost_classification: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="managed_compute",
        server_default="managed_compute",
    )

    # Reservation status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )

    # Which provider incurs this cost
    provider: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Expiration — reservation automatically expires if not finalized by this time
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # When the reservation was finalized (reconciled with actual cost)
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_cost_reservations_org_id", "org_id"),
        Index("ix_cost_reservations_job_id", "job_id"),
        Index(
            "ix_cost_reservations_org_status",
            "org_id",
            "status",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CostReservation(id={self.id}, org_id={self.org_id}, "
            f"job_id={self.job_id}, status={self.status}, "
            f"reserved={self.reserved_amount_usd})>"
        )


class CostEntry(Base, UUIDMixin, TenantMixin):
    """Cost entry — an immutable ledger record of a cost event.

    Cost entries are append-only: no updated_at column, no mutations.
    Each entry records a single cost event (reservation, commitment, actual,
    release, refund, or reconciliation).

    Always scoped to org_id. Cross-tenant access returns 404.
    """

    __tablename__ = "cost_entries"

    # Reference to the job that incurred this cost
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # Reference to the reservation this entry relates to
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # Type of cost event
    entry_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # Amount in USD (can be negative for releases/refunds)
    amount_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
    )

    # What operation incurred the cost
    operation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Which provider incurred the cost
    provider: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Three-tier classification
    cost_classification: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="managed_compute",
        server_default="managed_compute",
    )

    # Human-readable description of what happened
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Immutable creation timestamp (no updated_at for immutable records)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_cost_entries_org_id", "org_id"),
        Index("ix_cost_entries_job_id", "job_id"),
        Index("ix_cost_entries_reservation_id", "reservation_id"),
        Index(
            "ix_cost_entries_org_created",
            "org_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CostEntry(id={self.id}, org_id={self.org_id}, "
            f"entry_type={self.entry_type}, amount={self.amount_usd})>"
        )
