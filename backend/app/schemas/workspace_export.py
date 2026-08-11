"""Pydantic v2 schemas for workspace data export.

Defines request/response models for the workspace export API.
Export produces a machine-readable JSON archive of workspace data.

Export includes: Talent metadata, Creative DNA, recipes, projects,
prompts, provenance, workflows, model metadata, asset references,
consent records, workspace knowledge.

Export SHALL NOT expose: provider secrets, other users' private Brain
memory, internal platform config.

Validates: Requirements R104.1, R104.2, R104.3
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class ExportStatus(StrEnum):
    """Status of a workspace export job."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportDataCategory(StrEnum):
    """Categories of data available for export."""

    TALENT_METADATA = "talent_metadata"
    CREATIVE_DNA = "creative_dna"
    RECIPES = "recipes"
    PROJECTS = "projects"
    PROMPTS = "prompts"
    PROVENANCE = "provenance"
    WORKFLOWS = "workflows"
    MODEL_METADATA = "model_metadata"
    ASSET_REFERENCES = "asset_references"
    CONSENT_RECORDS = "consent_records"
    WORKSPACE_KNOWLEDGE = "workspace_knowledge"


class WorkspaceExportRequest(BaseSchema):
    """Request schema for initiating a workspace data export.

    If categories is omitted or empty, all available categories are exported.
    """

    categories: list[ExportDataCategory] | None = Field(
        default=None,
        description=(
            "Specific data categories to export. "
            "If omitted, all categories are included."
        ),
    )
    include_asset_references: bool = Field(
        default=True,
        description="Include asset storage key references in export.",
    )


class WorkspaceExportResponse(BaseSchema):
    """Response schema for a workspace export job."""

    id: UUID
    org_id: UUID
    status: ExportStatus
    requested_by: UUID
    categories: list[ExportDataCategory]
    download_url: str | None = Field(
        default=None,
        description="Signed download URL (available when status=completed).",
    )
    file_size_bytes: int | None = Field(
        default=None,
        description="Size of the export file in bytes (available when completed).",
    )
    error_message: str | None = Field(
        default=None,
        description="Error details (available when status=failed).",
    )
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
