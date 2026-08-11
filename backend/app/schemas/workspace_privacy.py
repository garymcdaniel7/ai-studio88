"""Pydantic schemas for workspace privacy configuration API.

Request/response schemas for the workspace privacy restriction
endpoints (GET/PUT /api/v1/workspace/privacy).

Validates: Requirements R103.1, R103.2, R103.3
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, StrictBaseSchema


# =============================================================================
# Enums
# =============================================================================


class RestrictionTypeEnum(str, Enum):
    """Valid workspace privacy restriction types."""

    LOCAL_MODELS_ONLY = "local_models_only"
    CUSTOMER_COMPUTE_ONLY = "customer_compute_only"
    APPROVED_LLM_ONLY = "approved_llm_only"
    NO_EXTERNAL_LLM_FOR_PROJECT = "no_external_llm_for_project"
    APPROVED_STORAGE_ONLY = "approved_storage_only"
    TALENT_PROVIDER_RESTRICTION = "talent_provider_restriction"
    PROJECT_PRIVACY = "project_privacy"


# =============================================================================
# Request Schemas
# =============================================================================


class WorkspacePrivacyRestrictionCreate(StrictBaseSchema):
    """Request schema for creating a workspace privacy restriction.

    Used by PUT /api/v1/workspace/privacy (upsert or add).
    """

    restriction_type: RestrictionTypeEnum = Field(
        description="Type of privacy restriction to apply.",
    )
    restriction_target: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Optional target scope (project_id, talent_id). "
            "NULL means workspace-wide restriction."
        ),
    )
    allowed_providers: list[str] = Field(
        default_factory=list,
        max_length=50,
        description=(
            "Provider names explicitly allowed (whitelist). "
            "Empty list means no whitelist filtering."
        ),
    )
    denied_providers: list[str] = Field(
        default_factory=list,
        max_length=50,
        description=(
            "Provider names explicitly denied (blocklist). "
            "These providers will never be used for this restriction scope."
        ),
    )


class WorkspacePrivacyConfigUpdate(StrictBaseSchema):
    """Request schema for updating workspace privacy restrictions.

    Used by PUT /api/v1/workspace/privacy. Replaces all restrictions
    for the workspace with the provided list.
    """

    restrictions: list[WorkspacePrivacyRestrictionCreate] = Field(
        default_factory=list,
        max_length=50,
        description="Complete list of privacy restrictions for this workspace.",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class WorkspacePrivacyRestrictionResponse(BaseSchema):
    """Single privacy restriction in a response."""

    id: UUID
    org_id: UUID
    restriction_type: RestrictionTypeEnum
    restriction_target: str | None = None
    allowed_providers: list[str] = Field(default_factory=list)
    denied_providers: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WorkspacePrivacyConfigResponse(BaseSchema):
    """Response schema for workspace privacy configuration.

    Returns the full list of active privacy restrictions for the workspace.
    """

    org_id: UUID
    restrictions: list[WorkspacePrivacyRestrictionResponse] = Field(
        default_factory=list,
    )
