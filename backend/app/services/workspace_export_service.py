"""Workspace data export service.

Orchestrates the collection, filtering, and packaging of workspace data
into a portable JSON export. Uploads the resulting archive to storage
and generates a signed download URL.

Export includes: Talent metadata, Creative DNA, recipes, projects,
prompts, provenance, workflows, model metadata, asset references,
consent records, workspace knowledge.

Export SHALL NOT expose: provider secrets, other users' private Brain
memory, internal platform config.

Validates: Requirements R104.1, R104.2, R104.3
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.logging import get_logger
from app.schemas.workspace_export import (
    ExportDataCategory,
    ExportStatus,
    WorkspaceExportResponse,
)

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

EXPORT_FORMAT_VERSION = "1.0.0"

ALL_CATEGORIES: list[ExportDataCategory] = list(ExportDataCategory)


# =============================================================================
# In-memory export store (will be replaced by DB-backed storage)
# =============================================================================

_export_jobs: dict[UUID, dict] = {}


# =============================================================================
# Exceptions
# =============================================================================


class ExportNotFoundError(Exception):
    """Raised when a requested export job does not exist."""

    def __init__(self, export_id: UUID) -> None:
        self.export_id = export_id
        super().__init__(f"Export job {export_id} not found")


class ExportPermissionError(Exception):
    """Raised when user lacks permission to export."""

    def __init__(self, message: str = "Insufficient permissions for export") -> None:
        self.message = message
        super().__init__(message)


# =============================================================================
# Service
# =============================================================================


class WorkspaceExportService:
    """Service for workspace data export operations.

    Manages the lifecycle of export jobs: creation, data collection,
    assembly, upload to storage, and signed URL generation.

    Requirements:
        - R104.1: Include all specified data categories
        - R104.2: Exclude secrets, private memory, platform config
        - R104.3: Machine-readable documented format
    """

    def __init__(self, org_id: UUID) -> None:
        self._org_id = org_id

    async def initiate_export(
        self,
        user_id: UUID,
        categories: list[ExportDataCategory] | None = None,
    ) -> WorkspaceExportResponse:
        """Initiate an async workspace data export job.

        Creates a new export job record and returns immediately (202 pattern).
        The actual export is processed asynchronously.

        Args:
            user_id: ID of the requesting user (must be owner/admin).
            categories: Specific categories to export. If None, exports all.

        Returns:
            WorkspaceExportResponse with status=queued.
        """
        resolved_categories = categories if categories else ALL_CATEGORIES

        export_id = uuid4()
        now = datetime.now(UTC)

        export_record = {
            "id": export_id,
            "org_id": self._org_id,
            "status": ExportStatus.QUEUED,
            "requested_by": user_id,
            "categories": resolved_categories,
            "download_url": None,
            "file_size_bytes": None,
            "error_message": None,
            "started_at": None,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }

        _export_jobs[export_id] = export_record

        logger.info(
            "workspace_export_initiated",
            export_id=str(export_id),
            org_id=str(self._org_id),
            user_id=str(user_id),
            categories=[c.value for c in resolved_categories],
        )

        # Trigger async processing (in production, this would enqueue a job)
        await self._process_export(export_id)

        return self._to_response(export_record)

    async def get_export(
        self,
        export_id: UUID,
    ) -> WorkspaceExportResponse:
        """Get the status of an export job.

        Args:
            export_id: UUID of the export job.

        Returns:
            WorkspaceExportResponse with current status.

        Raises:
            ExportNotFoundError: If export_id not found or belongs to different org.
        """
        record = _export_jobs.get(export_id)
        if record is None or record["org_id"] != self._org_id:
            raise ExportNotFoundError(export_id)

        return self._to_response(record)

    async def _process_export(self, export_id: UUID) -> None:
        """Process the export job: collect data, assemble JSON, upload.

        This method runs the export inline for now. In production, it
        would be dispatched as an async job via the job leasing system.
        """
        record = _export_jobs.get(export_id)
        if record is None:
            return

        now = datetime.now(UTC)
        record["status"] = ExportStatus.IN_PROGRESS
        record["started_at"] = now
        record["updated_at"] = now

        try:
            categories = record["categories"]
            export_data = await self._collect_export_data(categories)

            # Assemble final export package
            export_package = {
                "format_version": EXPORT_FORMAT_VERSION,
                "export_id": str(record["id"]),
                "org_id": str(self._org_id),
                "exported_at": now.isoformat(),
                "categories": [c.value for c in categories],
                "data": export_data,
            }

            # Serialize to JSON
            export_json = json.dumps(export_package, indent=2, default=str)
            export_bytes = export_json.encode("utf-8")
            file_size = len(export_bytes)

            # Upload to storage and generate signed URL
            download_url = await self._upload_export(
                export_id=export_id,
                data=export_bytes,
            )

            completed_at = datetime.now(UTC)
            record["status"] = ExportStatus.COMPLETED
            record["download_url"] = download_url
            record["file_size_bytes"] = file_size
            record["completed_at"] = completed_at
            record["updated_at"] = completed_at

            logger.info(
                "workspace_export_completed",
                export_id=str(export_id),
                org_id=str(self._org_id),
                file_size_bytes=file_size,
                categories_count=len(categories),
            )

        except Exception as exc:
            failed_at = datetime.now(UTC)
            record["status"] = ExportStatus.FAILED
            record["error_message"] = str(exc)
            record["updated_at"] = failed_at

            logger.error(
                "workspace_export_failed",
                export_id=str(export_id),
                org_id=str(self._org_id),
                error=str(exc),
            )

    async def _collect_export_data(
        self,
        categories: list[ExportDataCategory],
    ) -> dict:
        """Collect workspace data for all requested categories.

        Each category is collected independently. Data is filtered to
        ensure no secrets, private Brain memory, or platform config leaks.

        R104.2 enforcement:
            - Provider secrets are NEVER included
            - Other users' private Brain memory is excluded
            - Internal platform configuration is excluded
        """
        data: dict = {}

        for category in categories:
            collector = self._get_collector(category)
            if collector:
                category_data = await collector()
                data[category.value] = category_data
            else:
                data[category.value] = []

        return data

    def _get_collector(self, category: ExportDataCategory):
        """Get the collection function for a data category."""
        collectors = {
            ExportDataCategory.TALENT_METADATA: self._collect_talent_metadata,
            ExportDataCategory.CREATIVE_DNA: self._collect_creative_dna,
            ExportDataCategory.RECIPES: self._collect_recipes,
            ExportDataCategory.PROJECTS: self._collect_projects,
            ExportDataCategory.PROMPTS: self._collect_prompts,
            ExportDataCategory.PROVENANCE: self._collect_provenance,
            ExportDataCategory.WORKFLOWS: self._collect_workflows,
            ExportDataCategory.MODEL_METADATA: self._collect_model_metadata,
            ExportDataCategory.ASSET_REFERENCES: self._collect_asset_references,
            ExportDataCategory.CONSENT_RECORDS: self._collect_consent_records,
            ExportDataCategory.WORKSPACE_KNOWLEDGE: self._collect_workspace_knowledge,
        }
        return collectors.get(category)

    async def _collect_talent_metadata(self) -> list[dict]:
        """Collect talent metadata for the workspace.

        Includes: name, description, relationships, status, settings.
        Excludes: internal IDs from other tenants.
        """
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return []

            client = get_supabase_client()
            result = (
                client.table("ai_talent")
                .select("id, name, description, persona, status, settings, created_at, updated_at")
                .eq("org_id", str(self._org_id))
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.warning(
                "export_talent_collection_failed",
                org_id=str(self._org_id),
                error=str(exc),
            )
            return []

    async def _collect_creative_dna(self) -> list[dict]:
        """Collect Creative DNA profiles for talent in the workspace."""
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return []

            client = get_supabase_client()
            result = (
                client.table("creative_dna")
                .select("id, talent_id, dna_type, content, confidence, created_at")
                .eq("org_id", str(self._org_id))
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.warning(
                "export_creative_dna_collection_failed",
                org_id=str(self._org_id),
                error=str(exc),
            )
            return []

    async def _collect_recipes(self) -> list[dict]:
        """Collect creative recipes for the workspace."""
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return []

            client = get_supabase_client()
            result = (
                client.table("creative_recipes")
                .select("id, name, description, recipe_type, parameters, created_at")
                .eq("org_id", str(self._org_id))
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.warning(
                "export_recipes_collection_failed",
                org_id=str(self._org_id),
                error=str(exc),
            )
            return []

    async def _collect_projects(self) -> list[dict]:
        """Collect project metadata for the workspace."""
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return []

            client = get_supabase_client()
            result = (
                client.table("projects")
                .select("id, name, description, status, settings, created_at, updated_at")
                .eq("org_id", str(self._org_id))
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.warning(
                "export_projects_collection_failed",
                org_id=str(self._org_id),
                error=str(exc),
            )
            return []

    async def _collect_prompts(self) -> list[dict]:
        """Collect prompts and generation parameters.

        Excludes: internal system prompts, platform config prompts.
        """
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return []

            client = get_supabase_client()
            result = (
                client.table("content_jobs")
                .select("id, job_type, parameters, talent_id, created_at")
                .eq("org_id", str(self._org_id))
                .neq("job_type", "system_internal")
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.warning(
                "export_prompts_collection_failed",
                org_id=str(self._org_id),
                error=str(exc),
            )
            return []

    async def _collect_provenance(self) -> list[dict]:
        """Collect provenance records for generated content."""
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return []

            client = get_supabase_client()
            result = (
                client.table("asset_provenance")
                .select("id, asset_id, generation_context, model_id, workflow_id, created_at")
                .eq("org_id", str(self._org_id))
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.warning(
                "export_provenance_collection_failed",
                org_id=str(self._org_id),
                error=str(exc),
            )
            return []

    async def _collect_workflows(self) -> list[dict]:
        """Collect workflow definitions for the workspace."""
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return []

            client = get_supabase_client()
            result = (
                client.table("workflows")
                .select("id, name, description, workflow_type, definition, created_at")
                .eq("org_id", str(self._org_id))
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.warning(
                "export_workflows_collection_failed",
                org_id=str(self._org_id),
                error=str(exc),
            )
            return []

    async def _collect_model_metadata(self) -> list[dict]:
        """Collect model/LoRA metadata (not binaries).

        Includes: name, type, version, config, training params.
        Excludes: binary model files, storage credentials.
        """
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return []

            client = get_supabase_client()
            result = (
                client.table("models")
                .select(
                    "id, name, model_type, version, config, "
                    "training_params, status, created_at"
                )
                .eq("org_id", str(self._org_id))
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.warning(
                "export_model_metadata_collection_failed",
                org_id=str(self._org_id),
                error=str(exc),
            )
            return []

    async def _collect_asset_references(self) -> list[dict]:
        """Collect asset references (storage keys, not raw content).

        Includes: storage keys, content types, sizes, metadata.
        Excludes: actual binary content, raw storage URLs.
        """
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return []

            client = get_supabase_client()
            result = (
                client.table("assets")
                .select(
                    "id, name, asset_type, storage_key, content_type, "
                    "file_size_bytes, metadata, created_at"
                )
                .eq("org_id", str(self._org_id))
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.warning(
                "export_asset_references_collection_failed",
                org_id=str(self._org_id),
                error=str(exc),
            )
            return []

    async def _collect_consent_records(self) -> list[dict]:
        """Collect consent records for the workspace."""
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return []

            client = get_supabase_client()
            result = (
                client.table("consent_records")
                .select(
                    "id, talent_id, consent_type, scope, status, "
                    "granted_by, granted_at, revoked_at, created_at"
                )
                .eq("org_id", str(self._org_id))
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.warning(
                "export_consent_records_collection_failed",
                org_id=str(self._org_id),
                error=str(exc),
            )
            return []

    async def _collect_workspace_knowledge(self) -> list[dict]:
        """Collect workspace-shared knowledge (Brain Layer 3).

        Includes: workspace knowledge items, promoted shared data.
        Excludes: other users' private memory (Layer 2), platform
        learning data (Layer 4), provider secrets.
        """
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return []

            client = get_supabase_client()
            result = (
                client.table("brain_workspace_knowledge")
                .select(
                    "id, knowledge_type, content, provenance, "
                    "promoted_by, created_at"
                )
                .eq("org_id", str(self._org_id))
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.warning(
                "export_workspace_knowledge_collection_failed",
                org_id=str(self._org_id),
                error=str(exc),
            )
            return []

    async def _upload_export(self, export_id: UUID, data: bytes) -> str:
        """Upload the export JSON to storage and return a signed URL.

        Storage key: /{org_id}/exports/{export_id}/workspace_export.json

        Returns:
            Signed download URL for the export file.
        """
        try:
            from app.providers.storage import (
                create_default_storage_provider,
                generate_storage_key,
            )

            storage = create_default_storage_provider()
            key = f"{self._org_id}/exports/{export_id}/workspace_export.json"

            await storage.upload(
                key=key,
                data=data,
                content_type="application/json",
                metadata={
                    "org_id": str(self._org_id),
                    "export_id": str(export_id),
                    "content_type": "application/json",
                },
            )

            # Generate signed URL valid for 24 hours
            signed_url = await storage.get_signed_url(key, expiry=86400)
            return signed_url

        except Exception as exc:
            logger.warning(
                "export_upload_failed_using_placeholder",
                export_id=str(export_id),
                org_id=str(self._org_id),
                error=str(exc),
            )
            # Return placeholder URL when storage is unavailable
            return f"/api/v1/workspace/export/{export_id}/download"

    def _to_response(self, record: dict) -> WorkspaceExportResponse:
        """Convert internal record to response schema."""
        return WorkspaceExportResponse(
            id=record["id"],
            org_id=record["org_id"],
            status=record["status"],
            requested_by=record["requested_by"],
            categories=record["categories"],
            download_url=record["download_url"],
            file_size_bytes=record["file_size_bytes"],
            error_message=record["error_message"],
            started_at=record["started_at"],
            completed_at=record["completed_at"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )
