"""Pydantic v2 schemas for Support Sessions.

Request/response validation for the time-limited tenant access support
session model. Platform Operators request scope-limited sessions to
access workspace data for support purposes.

Validates: Requirements R33.8, R33.9, R97.5, R97.6, A2-006
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


# =============================================================================
# Enums
# =============================================================================


class SupportSessionStatusEnum(enum.StrEnum):
    """Support session lifecycle statuses."""

    REQUESTED = "requested"
    APPROVED = "approved"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    COMPLETED = "completed"


# =============================================================================
# Request Schemas
# =============================================================================


class SupportSessionRequest(BaseSchema):
    """Request schema for creating a support session.

    The operator_user_id is server-derived from the authenticated
    Platform Operator's identity — never client-supplied.
    """

    target_org_id: UUID = Field(
        ...,
        description="Organization/workspace to access",
    )
    reason: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Documented reason for requesting elevated access",
    )
    requested_capabilities: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Capability groups requested for this session",
    )
    permitted_surfaces: list[str] = Field(
        default_factory=list,
        max_length=50,
        description=(
            "Data surfaces to access: talent_metadata, job_history, "
            "cost_records, configuration, connection_status"
        ),
    )
    permitted_actions: list[str] = Field(
        default_factory=list,
        max_length=50,
        description=(
            "Actions to perform: view, pause_job, revoke_connection, "
            "reset_credential"
        ),
    )
    duration_minutes: int = Field(
        default=60,
        ge=5,
        le=240,
        description="Requested session duration in minutes (5-240, default 60)",
    )

    @field_validator("reason")
    @classmethod
    def validate_reason_not_empty(cls, v: str) -> str:
        """Ensure reason contains meaningful content."""
        if not v.strip():
            msg = "Reason must contain meaningful content"
            raise ValueError(msg)
        return v


class SupportSessionApprove(BaseSchema):
    """Request schema for approving a support session.

    The approver may grant a subset of the requested capabilities
    and further restrict surfaces/actions.
    """

    approved_capabilities: list[str] | None = Field(
        default=None,
        max_length=20,
        description=(
            "Capabilities to grant (subset of requested). "
            "If None, grants all requested capabilities."
        ),
    )
    permitted_surfaces: list[str] | None = Field(
        default=None,
        max_length=50,
        description=(
            "Override permitted surfaces (subset of requested). "
            "If None, uses originally requested surfaces."
        ),
    )
    permitted_actions: list[str] | None = Field(
        default=None,
        max_length=50,
        description=(
            "Override permitted actions (subset of requested). "
            "If None, uses originally requested actions."
        ),
    )


class SupportSessionRevoke(BaseSchema):
    """Request schema for revoking/ending a support session."""

    reason: str = Field(
        default="",
        max_length=1000,
        description="Optional reason for revoking the session",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class SupportSessionResponse(BaseSchema):
    """Response schema for a single support session record."""

    id: UUID
    operator_user_id: UUID
    target_org_id: UUID
    reason: str
    requested_capabilities: list[str] | None = None
    approved_capabilities: list[str] | None = None
    permitted_surfaces: list[str] | None = None
    permitted_actions: list[str] | None = None
    approved_by: UUID | None = None
    started_at: datetime
    expires_at: datetime
    ended_at: datetime | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    @property
    def is_expired(self) -> bool:
        """Check if session has passed its expiry time."""
        return datetime.now(self.expires_at.tzinfo) >= self.expires_at

    @property
    def is_active(self) -> bool:
        """Check if session is currently active and not expired."""
        return self.status == SupportSessionStatusEnum.ACTIVE and not self.is_expired


class SupportSessionListResponse(BaseSchema):
    """Paginated list of support sessions."""

    items: list[SupportSessionResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
