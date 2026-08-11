"""Workspace Content Ownership schemas.

Pydantic schemas for content inventory, member departure processing,
and account deletion eligibility.

Validates: Requirements R96.1, R96.2, R96.3, R96.4
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class ContentType(str, Enum):
    """Types of workspace content owned by the organization."""

    TALENT = "talent"
    PROJECT = "project"
    ASSET = "asset"
    LORA_MODEL = "lora_model"
    CREATIVE_DNA = "creative_dna"
    RECIPE = "recipe"
    WORKFLOW = "workflow"
    KNOWLEDGE = "knowledge"


class JobDisposition(str, Enum):
    """How unfinished jobs are handled during departure."""

    REASSIGNED = "reassigned"
    PAUSED = "paused"


# =============================================================================
# Content Inventory
# =============================================================================


class ContentInventoryItem(BaseSchema):
    """A single item in the workspace content inventory."""

    content_type: ContentType
    count: int = Field(ge=0, description="Number of items of this type created by the user")


class ContentInventoryResponse(BaseSchema):
    """Content inventory for a user within a workspace.

    Shows what workspace-owned content the user has created. All content
    belongs to the workspace (org_id) regardless of who created it.
    """

    org_id: UUID
    user_id: UUID
    items: list[ContentInventoryItem]
    total_items: int = Field(ge=0)


# =============================================================================
# Member Departure
# =============================================================================


class AffectedJob(BaseSchema):
    """A job affected by member departure."""

    job_id: UUID
    job_type: str
    status: str
    disposition: JobDisposition


class DepartureSummary(BaseSchema):
    """Summary of a member departure processing result.

    Validates: R96.2
    """

    org_id: UUID
    departing_user_id: UUID
    processed_at: datetime

    # Content stays with workspace (R96.1)
    workspace_content_preserved: int = Field(
        ge=0,
        description="Total workspace-owned content items that remain accessible",
    )

    # Connection cleanup (R96.2)
    personal_connections_revoked: int = Field(
        ge=0,
        description="Personal connections revoked from workspace use",
    )
    workspace_connections_preserved: int = Field(
        ge=0,
        description="Workspace connections that remain functional",
    )
    connections_flagged_for_reauth: int = Field(
        ge=0,
        description="Connections flagged for reauthorization (scheduled ops)",
    )

    # Job reassignment (R96.2)
    jobs_reassigned: int = Field(ge=0)
    jobs_paused: int = Field(ge=0)
    affected_jobs: list[AffectedJob]


class DepartureResponse(BaseSchema):
    """API response for member departure endpoint."""

    summary: DepartureSummary
    message: str


# =============================================================================
# Account Deletion Eligibility
# =============================================================================


class AccountDeletionEligibility(BaseSchema):
    """Whether a user is eligible to delete their account.

    Validates: R96.3 — Account deletion requires ownership transfer first.
    """

    user_id: UUID
    org_id: UUID
    eligible: bool
    reason: str | None = None
    is_sole_owner: bool = Field(
        description="True if user is the only owner of this workspace",
    )
    other_owners_count: int = Field(
        ge=0,
        description="Number of other owners in this workspace",
    )
