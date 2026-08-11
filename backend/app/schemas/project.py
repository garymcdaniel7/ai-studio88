"""Pydantic v2 schemas for Projects with comprehensive input validation.

All inputs validated via explicit constraints:
    - UUID type for all IDs
    - min_length=1 for required strings (whitespace-only rejected)
    - max_length constraints on all string fields
    - Enum types for status fields

Validates: Requirements R4.1, R4.2, R4.3, R4.10, R15.1
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import Field

from backend.app.schemas.base import BaseSchema, PaginatedResponse, TenantResponseSchema
from backend.app.schemas.validation import DescriptionStr, NameStr


class ProjectStatus(str, enum.Enum):
    """Valid project statuses."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DRAFT = "draft"
    COMPLETED = "completed"


class ProjectCreate(BaseSchema):
    """Request schema for creating a new project.

    org_id is NEVER accepted from client — resolved from TenantContext.
    """

    name: NameStr = Field(..., description="Project name (1-100 chars, no whitespace-only)")
    description: DescriptionStr | None = Field(
        default=None, description="Project description (max 1000 chars)"
    )
    status: ProjectStatus = Field(
        default=ProjectStatus.ACTIVE, description="Project status"
    )
    talent_id: UUID | None = Field(
        default=None, description="Primary associated talent UUID"
    )


class ProjectUpdate(BaseSchema):
    """Request schema for updating a project (PATCH — partial update).

    All fields Optional. Only provided fields are updated.
    """

    name: NameStr | None = Field(
        default=None, description="Project name (1-100 chars)"
    )
    description: DescriptionStr | None = Field(
        default=None, description="Project description (max 1000 chars)"
    )
    status: ProjectStatus | None = Field(
        default=None, description="Project status"
    )
    talent_id: UUID | None = Field(
        default=None, description="Primary associated talent UUID"
    )


class ProjectResponse(TenantResponseSchema):
    """Response schema for a single project."""

    name: str
    description: str | None = None
    status: str
    talent_id: UUID | None = None


class ProjectListResponse(PaginatedResponse):
    """Paginated list of projects."""

    items: list[ProjectResponse]
