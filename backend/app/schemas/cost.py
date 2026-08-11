"""Pydantic v2 schemas for Cost Reservations and Cost Entries.

Provides request/response validation for the cost reservation and
reconciliation system. Three-tier cost classification:
    - customer_infrastructure: customer-owned compute (informational)
    - platform_expense: internal operational costs
    - managed_compute: platform-managed compute charged to tenant

Validates: Requirements R14.1, R14.2, R14.12, R66.1
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


# =============================================================================
# Enums
# =============================================================================


class CostClassification(str, enum.Enum):
    """Three-tier cost classification per R14 amended."""

    CUSTOMER_INFRASTRUCTURE = "customer_infrastructure"
    PLATFORM_EXPENSE = "platform_expense"
    MANAGED_COMPUTE = "managed_compute"


class ReservationStatus(str, enum.Enum):
    """Cost reservation lifecycle states."""

    ACTIVE = "active"
    COMMITTED = "committed"
    FINALIZED = "finalized"
    RELEASED = "released"
    EXPIRED = "expired"


class CostEntryType(str, enum.Enum):
    """Types of cost ledger entries."""

    RESERVATION = "reservation"
    COMMITMENT = "commitment"
    ACTUAL = "actual"
    RELEASE = "release"
    REFUND = "refund"
    RECONCILIATION = "reconciliation"


# =============================================================================
# Request Schemas
# =============================================================================


class CostReservationCreate(BaseSchema):
    """Request schema for creating a cost reservation.

    org_id is NEVER accepted from client — resolved from TenantContext.
    """

    job_id: UUID | None = Field(
        default=None, description="Associated job UUID (if job-related)"
    )
    operation: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Operation that will incur the cost",
    )
    reserved_amount_usd: Decimal = Field(
        ...,
        ge=Decimal("0.0001"),
        le=Decimal("99999.9999"),
        description="Estimated cost to reserve (USD)",
    )
    cost_classification: CostClassification = Field(
        default=CostClassification.MANAGED_COMPUTE,
        description="Cost classification tier",
    )
    provider: str | None = Field(
        default=None,
        max_length=100,
        description="Provider that will incur the cost",
    )
    expires_at: datetime = Field(
        ..., description="When this reservation expires if not finalized"
    )


class CostReservationFinalize(BaseSchema):
    """Request schema for finalizing a cost reservation with actual cost."""

    actual_amount_usd: Decimal = Field(
        ...,
        ge=Decimal("0"),
        le=Decimal("99999.9999"),
        description="Actual cost incurred (USD)",
    )


class CostEntryCreate(BaseSchema):
    """Request schema for recording a cost entry.

    org_id is NEVER accepted from client — resolved from TenantContext.
    Cost entries are immutable once created.
    """

    job_id: UUID | None = Field(
        default=None, description="Associated job UUID"
    )
    reservation_id: UUID | None = Field(
        default=None, description="Associated reservation UUID"
    )
    entry_type: CostEntryType = Field(
        ..., description="Type of cost event"
    )
    amount_usd: Decimal = Field(
        ...,
        ge=Decimal("-99999.9999"),
        le=Decimal("99999.9999"),
        description="Cost amount in USD (negative for releases/refunds)",
    )
    operation: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Operation that incurred the cost",
    )
    provider: str | None = Field(
        default=None,
        max_length=100,
        description="Provider that incurred the cost",
    )
    cost_classification: CostClassification = Field(
        default=CostClassification.MANAGED_COMPUTE,
        description="Cost classification tier",
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Human-readable description of the cost event",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class CostReservationResponse(BaseSchema):
    """Response schema for a single cost reservation."""

    id: UUID
    org_id: UUID
    job_id: UUID | None = None
    operation: str
    reserved_amount_usd: Decimal
    actual_amount_usd: Decimal | None = None
    cost_classification: str
    status: str
    provider: str | None = None
    expires_at: datetime
    finalized_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CostEntryResponse(BaseSchema):
    """Response schema for a single cost entry."""

    id: UUID
    org_id: UUID
    job_id: UUID | None = None
    reservation_id: UUID | None = None
    entry_type: str
    amount_usd: Decimal
    operation: str
    provider: str | None = None
    cost_classification: str
    description: str | None = None
    created_at: datetime


class CostReservationListResponse(BaseSchema):
    """Paginated list of cost reservations."""

    items: list[CostReservationResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class CostEntryListResponse(BaseSchema):
    """Paginated list of cost entries."""

    items: list[CostEntryResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class CostSummaryResponse(BaseSchema):
    """Summary of cost spend for an organization."""

    today_spend_usd: Decimal = Field(
        default=Decimal("0"), description="Total spend today (UTC)"
    )
    month_spend_usd: Decimal = Field(
        default=Decimal("0"), description="Total spend this calendar month"
    )
    active_reservations_usd: Decimal = Field(
        default=Decimal("0"), description="Total amount currently reserved"
    )
    breakdown_by_classification: dict[str, Decimal] = Field(
        default_factory=dict,
        description="Spend breakdown by cost classification",
    )
    breakdown_by_provider: dict[str, Decimal] = Field(
        default_factory=dict,
        description="Spend breakdown by provider",
    )
