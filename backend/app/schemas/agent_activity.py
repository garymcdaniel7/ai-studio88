"""Pydantic schemas for agent activity feed.

Defines response models for:
    - Listing agent activity entries (paginated)
    - Individual activity entry

Each activity entry answers "What did Brain/Hermes do?" with:
    - timestamp, action type, outcome, cost (R99.4)

Validates: Requirements R99.1, R99.2, R99.3, R99.4, R30.15
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class ActivityTypeEnum(str, Enum):
    """Valid activity types for the agent activity feed."""

    RECOMMENDATION = "recommendation"
    TOOL_CALL = "tool_call"
    JOB_DISPATCH = "job_dispatch"
    APPROVAL_REQUEST = "approval_request"
    CONNECTION_USE = "connection_use"
    CHANGE_MADE = "change_made"
    FAILURE = "failure"
    COST_INCURRED = "cost_incurred"


class AgentActivityResponse(BaseSchema):
    """Response for a single agent activity entry.

    Each entry includes: timestamp, action type, outcome (success/failure/pending),
    and cost if applicable (R99.4).
    """

    id: UUID
    org_id: UUID
    user_id: UUID
    session_id: UUID | None = None
    activity_type: ActivityTypeEnum
    summary: str = Field(description="Human-readable description of what happened")
    detail: dict[str, Any] | None = Field(
        default=None,
        description="Structured detail about the activity (JSONB)",
    )
    outcome: str | None = Field(
        default=None,
        description="Outcome: success, failure, pending, or null",
    )
    cost_usd: Decimal | None = Field(
        default=None,
        description="Cost incurred for this activity (if applicable)",
    )
    created_at: datetime


class AgentActivityListResponse(BaseSchema):
    """Paginated list of agent activity entries."""

    items: list[AgentActivityResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
