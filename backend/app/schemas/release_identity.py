"""Pydantic v2 schemas for Release Identity.

Request/response validation for the immutable Release Identity system.
Each release identity links a git commit, build artifacts, migration state,
config version, and model manifest into a single traceable record.

Validates: Requirements R72.1, R72.2, R72.3, R72.4, R72.5, R72.6
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


# =============================================================================
# Request Schemas
# =============================================================================


class ReleaseIdentityCreate(BaseSchema):
    """Request schema for creating a new Release Identity during deployment.

    All required fields must be present — deployments that cannot produce
    a complete Release_Identity are rejected (R72.5).
    """

    git_commit_sha: str = Field(
        ...,
        min_length=7,
        max_length=40,
        description="Git commit SHA (7-40 characters)",
    )
    frontend_artifact: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Frontend build artifact ID (Vercel deployment ID or build hash)",
    )
    backend_artifact: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Backend artifact ID (Docker image digest or deployment ID)",
    )
    migration_set: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Current migration head or comma-separated applied migration IDs",
    )
    config_version: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Configuration version identifier (hash of active config)",
    )
    model_manifest: dict = Field(
        default_factory=dict,
        description="JSON object mapping model names to their deployed versions/checksums",
    )
    deployment_ids: list[str] = Field(
        default_factory=list,
        description="List of deployment identifiers (Vercel, Railway, etc.)",
    )
    created_by: str | None = Field(
        default=None,
        max_length=200,
        description="Identity of the deployer (user ID, CI system, etc.)",
    )

    @field_validator("git_commit_sha")
    @classmethod
    def validate_commit_sha(cls, v: str) -> str:
        """Ensure commit SHA is a valid hex string."""
        v = v.strip().lower()
        if not all(c in "0123456789abcdef" for c in v):
            msg = "git_commit_sha must be a hexadecimal string"
            raise ValueError(msg)
        return v


# =============================================================================
# Response Schemas
# =============================================================================


class ReleaseIdentityResponse(BaseSchema):
    """Response schema for a single Release Identity record."""

    id: UUID
    git_commit_sha: str
    frontend_artifact: str
    backend_artifact: str
    migration_set: str
    config_version: str
    model_manifest: dict
    deployment_ids: list
    is_current: bool
    created_at: datetime
    created_by: str | None = None


class ReleaseIdentityVersionInfo(BaseSchema):
    """Compact version info for /ready responses and structured logs."""

    release_id: str
    git_commit_sha: str = Field(description="Short SHA (7 chars)")
    frontend_artifact: str
    backend_artifact: str
    migration_set: str
    config_version: str
    created_at: str | None = None


class ReleaseIdentityListResponse(BaseSchema):
    """Paginated list of Release Identity records."""

    items: list[ReleaseIdentityResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class ReleaseIdentityCompareResponse(BaseSchema):
    """Comparison between two release identities (R72.6)."""

    from_release: ReleaseIdentityResponse
    to_release: ReleaseIdentityResponse
    changes: dict = Field(
        default_factory=dict,
        description="Diff of what changed between releases",
    )
