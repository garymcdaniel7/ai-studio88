"""Pydantic schemas for workspace fallback preferences API.

Request/response schemas for the workspace fallback configuration
endpoints (GET/PUT /api/v1/workspace/fallback).

Validates: Requirements R26.3, R26.4, R26.9, R102.1, R102.2, R102.3
"""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, StrictBaseSchema


# =============================================================================
# Enums
# =============================================================================


class FallbackModeEnum(str, Enum):
    """Workspace fallback mode for API serialization."""

    AUTO = "auto"
    ASK = "ask"
    STRICT = "strict"


# =============================================================================
# Request Schemas
# =============================================================================


class WorkspaceFallbackConfigUpdate(StrictBaseSchema):
    """Request schema for updating workspace fallback preferences.

    Used by PUT /api/v1/workspace/fallback.
    """

    fallback_mode: FallbackModeEnum = Field(
        default=FallbackModeEnum.AUTO,
        description=(
            "Fallback behavior when preferred provider is unavailable. "
            "AUTO: route to next, ASK: confirm before switching, "
            "STRICT: fail/queue"
        ),
    )
    denied_providers: list[str] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Provider names blocked by privacy policy. "
            "These providers will never be used regardless of fallback mode."
        ),
    )


# =============================================================================
# Response Schemas
# =============================================================================


class WorkspaceFallbackConfigResponse(BaseSchema):
    """Response schema for workspace fallback configuration."""

    org_id: UUID
    fallback_mode: FallbackModeEnum
    denied_providers: list[str] = Field(default_factory=list)
