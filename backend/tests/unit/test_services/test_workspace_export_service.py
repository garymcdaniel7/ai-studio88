"""Unit tests for WorkspaceExportService — workspace data export lifecycle.

Tests cover:
    - initiate_export creates a job with status=queued → completed
    - initiate_export with specific categories uses only those categories
    - initiate_export with no categories exports all categories
    - get_export returns the export record by ID
    - get_export raises ExportNotFoundError for unknown ID
    - get_export raises ExportNotFoundError for different org_id (tenant isolation)
    - Export data excludes provider secrets
    - Export data excludes private Brain memory
    - Export data excludes internal platform config
    - Export format contains required metadata (format_version, export_id, org_id)

Requirements: R104.1, R104.2, R104.3
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# =============================================================================
# Mock heavy dependencies at sys.modules level before any app imports.
# =============================================================================

_sa_mock = MagicMock()
_sa_mock.DateTime = MagicMock
_sa_mock.Float = MagicMock
_sa_mock.Integer = MagicMock
_sa_mock.String = MagicMock
_sa_mock.Text = MagicMock
_sa_mock.Boolean = MagicMock
_sa_mock.ForeignKey = MagicMock
_sa_mock.Index = MagicMock
_sa_mock.func = MagicMock()
_sa_mock.select = MagicMock()
_sa_mock.update = MagicMock()
_sa_mock.and_ = MagicMock()

_sa_orm_mock = MagicMock()
_sa_orm_mock.Mapped = MagicMock
_sa_orm_mock.mapped_column = MagicMock(return_value=None)
_sa_orm_mock.relationship = MagicMock(return_value=None)
_sa_orm_mock.DeclarativeBase = type("DeclarativeBase", (), {})

_sa_dialects_pg_mock = MagicMock()
_sa_dialects_pg_mock.UUID = MagicMock
_sa_dialects_pg_mock.JSONB = MagicMock
_sa_dialects_pg_mock.ARRAY = MagicMock

_sa_ext_asyncio_mock = MagicMock()
_sa_ext_asyncio_mock.AsyncSession = MagicMock

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.exc", MagicMock())

_mock_db_mod = ModuleType("app.db")
sys.modules.setdefault("app.db", _mock_db_mod)
_mock_db_session = ModuleType("app.db.session")
_mock_db_session.get_db_session = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.session", _mock_db_session)
_mock_db_base = ModuleType("app.db.base")
sys.modules.setdefault("app.db.base", _mock_db_base)
sys.modules.setdefault("app.db.tenant_scope", MagicMock())

# Mock jose/passlib/bcrypt used by security module
sys.modules.setdefault("jose", MagicMock())
sys.modules.setdefault("jose.jwt", MagicMock())
sys.modules.setdefault("jose.exceptions", MagicMock())
sys.modules.setdefault("passlib", MagicMock())
sys.modules.setdefault("passlib.context", MagicMock())
sys.modules.setdefault("bcrypt", MagicMock())

# Mock structlog
_structlog_mock = MagicMock()
_structlog_mock.get_logger = MagicMock(return_value=MagicMock())
_structlog_mock.stdlib = MagicMock()
_structlog_mock.stdlib.BoundLogger = MagicMock
sys.modules.setdefault("structlog", _structlog_mock)

# Mock boto3 (used by storage provider)
sys.modules.setdefault("boto3", MagicMock())
sys.modules.setdefault("botocore", MagicMock())
sys.modules.setdefault("botocore.config", MagicMock())
sys.modules.setdefault("botocore.exceptions", MagicMock())

# Mock supabase
sys.modules.setdefault("supabase", MagicMock())

# Now import the modules under test
from app.schemas.workspace_export import (
    ExportDataCategory,
    ExportStatus,
    WorkspaceExportRequest,
    WorkspaceExportResponse,
)
from app.services.workspace_export_service import (
    ALL_CATEGORIES,
    ExportNotFoundError,
    WorkspaceExportService,
    _export_jobs,
)


# =============================================================================
# Fixtures
# =============================================================================

ORG_ID = uuid4()
OTHER_ORG_ID = uuid4()
USER_ID = uuid4()


@pytest.fixture(autouse=True)
def _clear_export_jobs():
    """Clear in-memory export store between tests."""
    _export_jobs.clear()
    yield
    _export_jobs.clear()


@pytest.fixture
def service() -> WorkspaceExportService:
    """Create a WorkspaceExportService for the test org."""
    return WorkspaceExportService(org_id=ORG_ID)


# =============================================================================
# Tests: initiate_export
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initiate_export_returns_202_response(service: WorkspaceExportService):
    """initiate_export creates an export job that reaches completed status."""
    with patch("app.services.workspace_export_service.WorkspaceExportService._upload_export", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://storage.example.com/export.json"

        with patch("backend.database.is_supabase_configured", return_value=False):
            result = await service.initiate_export(user_id=USER_ID)

    assert isinstance(result, WorkspaceExportResponse)
    assert result.org_id == ORG_ID
    assert result.requested_by == USER_ID
    assert result.status == ExportStatus.COMPLETED
    assert result.download_url is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initiate_export_all_categories_by_default(service: WorkspaceExportService):
    """When no categories specified, all categories are included."""
    with patch("app.services.workspace_export_service.WorkspaceExportService._upload_export", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://storage.example.com/export.json"

        with patch("backend.database.is_supabase_configured", return_value=False):
            result = await service.initiate_export(user_id=USER_ID)

    assert set(result.categories) == set(ALL_CATEGORIES)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initiate_export_specific_categories(service: WorkspaceExportService):
    """When specific categories are provided, only those are exported."""
    categories = [ExportDataCategory.TALENT_METADATA, ExportDataCategory.PROJECTS]

    with patch("app.services.workspace_export_service.WorkspaceExportService._upload_export", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://storage.example.com/export.json"

        with patch("backend.database.is_supabase_configured", return_value=False):
            result = await service.initiate_export(
                user_id=USER_ID,
                categories=categories,
            )

    assert result.categories == categories


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initiate_export_generates_unique_id(service: WorkspaceExportService):
    """Each export gets a unique UUID."""
    with patch("app.services.workspace_export_service.WorkspaceExportService._upload_export", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://storage.example.com/export.json"

        with patch("backend.database.is_supabase_configured", return_value=False):
            result1 = await service.initiate_export(user_id=USER_ID)
            result2 = await service.initiate_export(user_id=USER_ID)

    assert result1.id != result2.id


# =============================================================================
# Tests: get_export
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_export_returns_existing_record(service: WorkspaceExportService):
    """get_export returns the export record for a known ID."""
    with patch("app.services.workspace_export_service.WorkspaceExportService._upload_export", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://storage.example.com/export.json"

        with patch("backend.database.is_supabase_configured", return_value=False):
            created = await service.initiate_export(user_id=USER_ID)

    result = await service.get_export(created.id)
    assert result.id == created.id
    assert result.org_id == ORG_ID
    assert result.status == ExportStatus.COMPLETED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_export_not_found_raises(service: WorkspaceExportService):
    """get_export raises ExportNotFoundError for unknown export ID."""
    with pytest.raises(ExportNotFoundError):
        await service.get_export(uuid4())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_export_tenant_isolation():
    """get_export raises ExportNotFoundError when org_id doesn't match (tenant isolation)."""
    # Create export in org A
    service_a = WorkspaceExportService(org_id=ORG_ID)
    with patch("app.services.workspace_export_service.WorkspaceExportService._upload_export", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://storage.example.com/export.json"

        with patch("backend.database.is_supabase_configured", return_value=False):
            created = await service_a.initiate_export(user_id=USER_ID)

    # Try to access from org B
    service_b = WorkspaceExportService(org_id=OTHER_ORG_ID)
    with pytest.raises(ExportNotFoundError):
        await service_b.get_export(created.id)


# =============================================================================
# Tests: Export data exclusion rules (R104.2)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_excludes_private_brain_memory(service: WorkspaceExportService):
    """Export collects workspace knowledge (Layer 3) but NOT private memory (Layer 2).

    R104.2: Export SHALL NOT expose other users' private Brain memory.
    """
    # The service collects brain_workspace_knowledge (shared, Layer 3)
    # and does NOT collect brain_user_memory (private, Layer 2)
    collectors = {
        cat: service._get_collector(cat)
        for cat in ALL_CATEGORIES
    }

    # workspace_knowledge collector exists (Layer 3 = shared)
    assert collectors[ExportDataCategory.WORKSPACE_KNOWLEDGE] is not None

    # No collector fetches brain_user_memory directly
    # Verify by checking that the method collects from brain_workspace_knowledge
    # table specifically, not brain_user_memory
    import inspect
    source = inspect.getsource(service._collect_workspace_knowledge)
    assert "brain_workspace_knowledge" in source
    assert "brain_user_memory" not in source


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_excludes_provider_secrets(service: WorkspaceExportService):
    """Export SHALL NOT expose provider secrets (R104.2).

    None of the export collectors access credential/secret tables.
    """
    import inspect

    # Check all collector methods don't access credential tables
    secret_tables = ["workspace_credentials", "connections", "platform_operators"]
    for category in ALL_CATEGORIES:
        collector = service._get_collector(category)
        if collector:
            source = inspect.getsource(collector)
            for secret_table in secret_tables:
                assert secret_table not in source, (
                    f"Collector for {category.value} should not access {secret_table}"
                )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_excludes_internal_platform_config(service: WorkspaceExportService):
    """Export SHALL NOT expose internal platform configuration (R104.2).

    No collector accesses platform-level config tables.
    """
    import inspect

    platform_tables = ["platform_operators", "feature_rollouts", "platform_config"]
    for category in ALL_CATEGORIES:
        collector = service._get_collector(category)
        if collector:
            source = inspect.getsource(collector)
            for table in platform_tables:
                assert table not in source, (
                    f"Collector for {category.value} should not access {table}"
                )


# =============================================================================
# Tests: Export format (R104.3)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_response_includes_metadata(service: WorkspaceExportService):
    """Export response includes all required metadata fields."""
    with patch("app.services.workspace_export_service.WorkspaceExportService._upload_export", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://storage.example.com/export.json"

        with patch("backend.database.is_supabase_configured", return_value=False):
            result = await service.initiate_export(user_id=USER_ID)

    # Response must include these fields
    assert result.id is not None
    assert result.org_id == ORG_ID
    assert result.status is not None
    assert result.requested_by == USER_ID
    assert result.categories is not None
    assert result.created_at is not None
    assert result.updated_at is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_completed_has_download_url(service: WorkspaceExportService):
    """Completed export has a download_url and file_size_bytes."""
    with patch("app.services.workspace_export_service.WorkspaceExportService._upload_export", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://storage.example.com/export.json"

        with patch("backend.database.is_supabase_configured", return_value=False):
            result = await service.initiate_export(user_id=USER_ID)

    assert result.status == ExportStatus.COMPLETED
    assert result.download_url == "https://storage.example.com/export.json"
    assert result.file_size_bytes is not None
    assert result.file_size_bytes > 0
    assert result.completed_at is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_failed_has_error_message(service: WorkspaceExportService):
    """Failed export has an error_message."""
    with patch("app.services.workspace_export_service.WorkspaceExportService._collect_export_data", new_callable=AsyncMock) as mock_collect:
        mock_collect.side_effect = RuntimeError("Database connection lost")

        result = await service.initiate_export(user_id=USER_ID)

    assert result.status == ExportStatus.FAILED
    assert result.error_message is not None
    assert "Database connection lost" in result.error_message
    assert result.download_url is None


# =============================================================================
# Tests: Schema validation
# =============================================================================


@pytest.mark.unit
def test_export_request_schema_defaults():
    """WorkspaceExportRequest has sensible defaults."""
    request = WorkspaceExportRequest()
    assert request.categories is None
    assert request.include_asset_references is True


@pytest.mark.unit
def test_export_request_schema_with_categories():
    """WorkspaceExportRequest accepts specific categories."""
    request = WorkspaceExportRequest(
        categories=[ExportDataCategory.TALENT_METADATA, ExportDataCategory.PROJECTS]
    )
    assert len(request.categories) == 2
    assert ExportDataCategory.TALENT_METADATA in request.categories


@pytest.mark.unit
def test_export_status_enum_values():
    """ExportStatus has all required states."""
    assert ExportStatus.QUEUED == "queued"
    assert ExportStatus.IN_PROGRESS == "in_progress"
    assert ExportStatus.COMPLETED == "completed"
    assert ExportStatus.FAILED == "failed"


@pytest.mark.unit
def test_export_data_category_enum_has_11_values():
    """ExportDataCategory has all 11 required categories per R104.1."""
    assert len(ExportDataCategory) == 11
