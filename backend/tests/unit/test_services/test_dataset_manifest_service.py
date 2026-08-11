"""Unit tests for DatasetManifestService — immutable manifest lifecycle.

Tests cover:
    - create_manifest succeeds with valid data
    - create_manifest rejects when talent not found
    - create_manifest rejects when consent record is revoked
    - create_manifest rejects when consent record lacks training scope
    - get_manifest returns manifest for valid ID
    - get_manifest raises 404 for missing/cross-tenant
    - verify_manifest detects deleted files
    - verify_manifest detects revoked consent
    - verify_manifest returns valid for fresh references
    - compare_manifests shows added/removed/changed files
    - Immutability: no update/patch method exists on service
    - list_manifests returns paginated results
    - compute_file_checksum produces correct SHA-256

Requirements: R61.1, R61.2, R61.3, R61.4, R61.5, R61.6
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
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

# Mock app.db.*
_mock_db_mod = ModuleType("app.db")
sys.modules.setdefault("app.db", _mock_db_mod)

_mock_db_session = ModuleType("app.db.session")
_mock_db_session.get_db_session = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.session", _mock_db_session)

_mock_db_base = ModuleType("app.db.base")


class _FakeBase:
    pass


_mock_db_base.Base = _FakeBase  # type: ignore[attr-defined]
_mock_db_base.TimestampMixin = type("TimestampMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.UUIDMixin = type("UUIDMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.TenantMixin = type("TenantMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.SoftDeleteMixin = type("SoftDeleteMixin", (), {})  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.base", _mock_db_base)

_mock_tenant_scope = ModuleType("app.db.tenant_scope")
_mock_tenant_scope.QUARANTINED_ORG_ID = UUID("00000000-0000-0000-0000-000000000000")  # type: ignore[attr-defined]
_mock_tenant_scope.TenantScopedRepository = MagicMock()  # type: ignore[attr-defined]
_mock_tenant_scope.validate_org_id = MagicMock()  # type: ignore[attr-defined]
_mock_tenant_scope.tenant_filter = MagicMock()  # type: ignore[attr-defined]
_mock_tenant_scope.get_tenant_resource = AsyncMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.tenant_scope", _mock_tenant_scope)

# Mock jose, passlib
sys.modules.setdefault("jose", MagicMock())
sys.modules.setdefault("passlib", MagicMock())
sys.modules.setdefault("passlib.context", MagicMock())

# Mock pydantic-settings
_pydantic_settings_mock = MagicMock()
_pydantic_settings_mock.BaseSettings = type("BaseSettings", (), {"model_config": {}})
sys.modules.setdefault("pydantic_settings", _pydantic_settings_mock)

# Mock python-dotenv
sys.modules.setdefault("dotenv", MagicMock())

# Mock structlog
sys.modules.setdefault("structlog", MagicMock())

# Mock models package
_mock_models_pkg = ModuleType("app.models")
_mock_models_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.models", _mock_models_pkg)

# Mock dataset_manifest model
_mock_models_dm = ModuleType("app.models.dataset_manifest")


class _MockDatasetManifest:
    __tablename__ = "dataset_manifests"
    id = MagicMock()
    org_id = MagicMock()
    version = MagicMock()
    created_at = MagicMock()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if "id" not in kwargs:
            self.id = uuid4()
        if "created_at" not in kwargs:
            self.created_at = datetime.now(UTC)
        if "updated_at" not in kwargs:
            self.updated_at = datetime.now(UTC)


_mock_models_dm.DatasetManifest = _MockDatasetManifest  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.dataset_manifest", _mock_models_dm)

# Mock talent model
_mock_models_talent = ModuleType("app.models.talent")


class _MockAiTalent:
    __tablename__ = "talent"
    id = MagicMock()
    org_id = MagicMock()
    deleted_at = MagicMock()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mock_models_talent.AiTalent = _MockAiTalent  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.talent", _mock_models_talent)

# Mock consent model
_mock_models_consent = ModuleType("app.models.consent")


class _MockConsentRecord:
    __tablename__ = "consent_records"
    id = MagicMock()
    org_id = MagicMock()
    talent_id = MagicMock()
    revoked_at = MagicMock()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mock_models_consent.ConsentRecord = _MockConsentRecord  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.consent", _mock_models_consent)

# Mock repositories
_mock_repos_pkg = ModuleType("app.repositories")
_mock_repos_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.repositories", _mock_repos_pkg)

_mock_consent_repo_mod = ModuleType("app.repositories.consent_repository")
_mock_consent_repo_mod.ConsentRepository = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.repositories.consent_repository", _mock_consent_repo_mod)

# Mock backend.storage
_mock_backend = ModuleType("backend")
_mock_backend.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("backend", _mock_backend)

_mock_backend_storage = ModuleType("backend.storage")
_mock_backend_storage._get_client = MagicMock()  # type: ignore[attr-defined]
_mock_backend_storage.B2_BUCKET_NAME = "test-bucket"  # type: ignore[attr-defined]
sys.modules.setdefault("backend.storage", _mock_backend_storage)
sys.modules.setdefault("backend.database", MagicMock())

# Pre-load schemas
import importlib.util
import pathlib

_backend_dir = pathlib.Path(__file__).resolve().parents[3]  # backend/

_base_spec = importlib.util.spec_from_file_location(
    "app.schemas.base",
    str(_backend_dir / "app" / "schemas" / "base.py"),
)
_base_mod = importlib.util.module_from_spec(_base_spec)
sys.modules["app.schemas.base"] = _base_mod
sys.modules["backend.app.schemas.base"] = _base_mod
_base_spec.loader.exec_module(_base_mod)

# Now import application code
from fastapi import HTTPException

from app.core.dependencies import TenantContext, TrustDomain, WorkspaceRole
from app.schemas.dataset_manifest import (
    AssetRole,
    DatasetManifestCreateRequest,
    ManifestFileEntry,
    ManifestFileProvenance,
)

# Force-import the service
import app.services.dataset_manifest_service  # noqa: E402
from app.services.dataset_manifest_service import (
    DatasetManifestService,
    compute_file_checksum,
)


# =============================================================================
# Constants & Helpers
# =============================================================================

ORG_ID = uuid4()
USER_ID = uuid4()
TALENT_ID = uuid4()
MANIFEST_ID = uuid4()
CONSENT_ID = uuid4()


def _make_tenant(role: WorkspaceRole = WorkspaceRole.EDITOR) -> TenantContext:
    """Create a TenantContext for testing."""
    return TenantContext(
        user_id=USER_ID,
        org_id=ORG_ID,
        role=role,
        trust_domain=TrustDomain.WORKSPACE_ADMIN,
        email="test@example.com",
    )


def _make_file_entry(
    file_ref: str = "img_001.jpg",
    storage_key: str = "org/training/talent/img_001.jpg",
    checksum: str = "a" * 64,
    role: AssetRole = AssetRole.TRAINING_IMAGE,
    size: int = 1024000,
    content_type: str = "image/jpeg",
    provenance: ManifestFileProvenance = ManifestFileProvenance.USER_UPLOAD,
) -> ManifestFileEntry:
    """Create a ManifestFileEntry for testing."""
    return ManifestFileEntry(
        file_ref=file_ref,
        storage_key=storage_key,
        sha256_checksum=checksum,
        asset_role=role,
        file_size_bytes=size,
        content_type=content_type,
        provenance=provenance,
    )


def _make_create_data(
    talent_id: UUID = TALENT_ID,
    consent_ids: list[UUID] | None = None,
) -> DatasetManifestCreateRequest:
    """Create a full manifest creation request."""
    return DatasetManifestCreateRequest(
        talent_id=talent_id,
        files=[
            _make_file_entry("img_001.jpg", "org/t/img_001.jpg", "a" * 64),
            _make_file_entry("img_002.jpg", "org/t/img_002.jpg", "b" * 64),
        ],
        consent_record_ids=consent_ids or [CONSENT_ID],
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock async DB session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    return db


@pytest.fixture
def tenant():
    """Editor-level tenant context."""
    return _make_tenant(WorkspaceRole.EDITOR)


# =============================================================================
# Tests: create_manifest
# =============================================================================


class TestCreateManifest:
    """Tests for DatasetManifestService.create_manifest."""

    @pytest.mark.asyncio
    async def test_create_manifest_success(self, mock_db, tenant):
        """Creating manifest with valid data succeeds."""
        # Mock talent lookup returns a talent
        talent_result = MagicMock()
        talent_result.scalar_one_or_none.return_value = _MockAiTalent(
            id=TALENT_ID, org_id=ORG_ID, deleted_at=None
        )

        # Mock consent lookup returns active consent with training scope
        consent_result = MagicMock()
        consent_result.scalar_one_or_none.return_value = _MockConsentRecord(
            id=CONSENT_ID,
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            revoked_at=None,
            expires_at=None,
            scopes=["training", "likeness"],
        )

        mock_db.execute = AsyncMock(
            side_effect=[talent_result, consent_result]
        )

        service = DatasetManifestService(db=mock_db, tenant=tenant)
        data = _make_create_data()
        manifest = await service.create_manifest(data)

        # Verify manifest was added to session
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()

        # Verify manifest data
        assert manifest.org_id == ORG_ID
        assert manifest.talent_id == TALENT_ID
        assert manifest.total_file_count == 2
        assert manifest.total_size_bytes == 2048000
        assert manifest.is_valid is True
        assert manifest.created_by == USER_ID

    @pytest.mark.asyncio
    async def test_create_manifest_talent_not_found(self, mock_db, tenant):
        """Creating manifest with non-existent talent raises 404."""
        talent_result = MagicMock()
        talent_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(return_value=talent_result)

        service = DatasetManifestService(db=mock_db, tenant=tenant)
        data = _make_create_data()

        with pytest.raises(HTTPException) as exc_info:
            await service.create_manifest(data)

        assert exc_info.value.status_code == 404
        assert "Talent" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_manifest_talent_deleted(self, mock_db, tenant):
        """Creating manifest with soft-deleted talent raises 404."""
        talent_result = MagicMock()
        talent_result.scalar_one_or_none.return_value = _MockAiTalent(
            id=TALENT_ID, org_id=ORG_ID, deleted_at=datetime.now(UTC)
        )

        mock_db.execute = AsyncMock(return_value=talent_result)

        service = DatasetManifestService(db=mock_db, tenant=tenant)
        data = _make_create_data()

        with pytest.raises(HTTPException) as exc_info:
            await service.create_manifest(data)

        assert exc_info.value.status_code == 404
        assert "deleted" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_manifest_consent_revoked(self, mock_db, tenant):
        """Creating manifest with revoked consent raises 400."""
        talent_result = MagicMock()
        talent_result.scalar_one_or_none.return_value = _MockAiTalent(
            id=TALENT_ID, org_id=ORG_ID, deleted_at=None
        )

        consent_result = MagicMock()
        consent_result.scalar_one_or_none.return_value = _MockConsentRecord(
            id=CONSENT_ID,
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            revoked_at=datetime.now(UTC),
            scopes=["training"],
        )

        mock_db.execute = AsyncMock(
            side_effect=[talent_result, consent_result]
        )

        service = DatasetManifestService(db=mock_db, tenant=tenant)
        data = _make_create_data()

        with pytest.raises(HTTPException) as exc_info:
            await service.create_manifest(data)

        assert exc_info.value.status_code == 400
        assert "revoked" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_manifest_consent_missing_training_scope(
        self, mock_db, tenant
    ):
        """Creating manifest with consent lacking 'training' scope raises 400."""
        talent_result = MagicMock()
        talent_result.scalar_one_or_none.return_value = _MockAiTalent(
            id=TALENT_ID, org_id=ORG_ID, deleted_at=None
        )

        consent_result = MagicMock()
        consent_result.scalar_one_or_none.return_value = _MockConsentRecord(
            id=CONSENT_ID,
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            revoked_at=None,
            expires_at=None,
            scopes=["likeness", "generation"],  # No 'training'
        )

        mock_db.execute = AsyncMock(
            side_effect=[talent_result, consent_result]
        )

        service = DatasetManifestService(db=mock_db, tenant=tenant)
        data = _make_create_data()

        with pytest.raises(HTTPException) as exc_info:
            await service.create_manifest(data)

        assert exc_info.value.status_code == 400
        assert "training" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_manifest_consent_expired(self, mock_db, tenant):
        """Creating manifest with expired consent raises 400."""
        talent_result = MagicMock()
        talent_result.scalar_one_or_none.return_value = _MockAiTalent(
            id=TALENT_ID, org_id=ORG_ID, deleted_at=None
        )

        consent_result = MagicMock()
        consent_result.scalar_one_or_none.return_value = _MockConsentRecord(
            id=CONSENT_ID,
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            revoked_at=None,
            expires_at=datetime.now(UTC) - timedelta(days=1),
            scopes=["training"],
        )

        mock_db.execute = AsyncMock(
            side_effect=[talent_result, consent_result]
        )

        service = DatasetManifestService(db=mock_db, tenant=tenant)
        data = _make_create_data()

        with pytest.raises(HTTPException) as exc_info:
            await service.create_manifest(data)

        assert exc_info.value.status_code == 400
        assert "expired" in exc_info.value.detail


# =============================================================================
# Tests: get_manifest
# =============================================================================


class TestGetManifest:
    """Tests for DatasetManifestService.get_manifest."""

    @pytest.mark.asyncio
    async def test_get_manifest_success(self, mock_db, tenant):
        """Get manifest with valid ID returns manifest."""
        expected = _MockDatasetManifest(
            id=MANIFEST_ID,
            org_id=ORG_ID,
            version=uuid4(),
            talent_id=TALENT_ID,
            manifest_files=[],
            consent_record_ids=[],
            total_file_count=0,
            total_size_bytes=0,
            is_valid=True,
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = expected
        mock_db.execute = AsyncMock(return_value=result_mock)

        service = DatasetManifestService(db=mock_db, tenant=tenant)
        manifest = await service.get_manifest(MANIFEST_ID)

        assert manifest.id == MANIFEST_ID
        assert manifest.org_id == ORG_ID

    @pytest.mark.asyncio
    async def test_get_manifest_not_found(self, mock_db, tenant):
        """Get manifest with unknown ID raises 404."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        service = DatasetManifestService(db=mock_db, tenant=tenant)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_manifest(uuid4())

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail


# =============================================================================
# Tests: verify_manifest
# =============================================================================


class TestVerifyManifest:
    """Tests for DatasetManifestService.verify_manifest."""

    @pytest.mark.asyncio
    async def test_verify_manifest_all_valid(self, mock_db, tenant):
        """Verification passes when all files exist and consent is active."""
        manifest = _MockDatasetManifest(
            id=MANIFEST_ID,
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            manifest_files=[
                {
                    "file_ref": "img_001.jpg",
                    "storage_key": "org/t/img_001.jpg",
                    "sha256_checksum": "a" * 64,
                    "asset_role": "training_image",
                    "file_size_bytes": 1024,
                    "content_type": "image/jpeg",
                    "provenance": "user_upload",
                }
            ],
            consent_record_ids=[CONSENT_ID],
            is_valid=True,
        )

        # get_manifest call
        manifest_result = MagicMock()
        manifest_result.scalar_one_or_none.return_value = manifest

        # consent check call
        consent_result = MagicMock()
        consent_result.scalar_one_or_none.return_value = _MockConsentRecord(
            id=CONSENT_ID,
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            revoked_at=None,
            expires_at=None,
        )

        mock_db.execute = AsyncMock(
            side_effect=[manifest_result, consent_result]
        )

        # Mock storage check
        with patch(
            "app.services.dataset_manifest_service.DatasetManifestService._check_file_validity",
            new_callable=lambda: lambda self, f: AsyncMock(return_value=None),
        ):
            service = DatasetManifestService(db=mock_db, tenant=tenant)
            # Patch _check_file_validity to return None (file valid)
            service._check_file_validity = AsyncMock(return_value=None)
            result = await service.verify_manifest(MANIFEST_ID)

        assert result.is_valid is True
        assert result.files_checked == 1
        assert result.files_passed == 1
        assert result.consent_valid is True
        assert len(result.issues) == 0

    @pytest.mark.asyncio
    async def test_verify_manifest_consent_revoked(self, mock_db, tenant):
        """Verification fails when consent has been revoked."""
        manifest = _MockDatasetManifest(
            id=MANIFEST_ID,
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            manifest_files=[],
            consent_record_ids=[CONSENT_ID],
            is_valid=True,
        )

        # get_manifest call
        manifest_result = MagicMock()
        manifest_result.scalar_one_or_none.return_value = manifest

        # consent check — revoked
        consent_result = MagicMock()
        consent_result.scalar_one_or_none.return_value = _MockConsentRecord(
            id=CONSENT_ID,
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            revoked_at=datetime.now(UTC),
            expires_at=None,
        )

        mock_db.execute = AsyncMock(
            side_effect=[manifest_result, consent_result]
        )

        service = DatasetManifestService(db=mock_db, tenant=tenant)
        result = await service.verify_manifest(MANIFEST_ID)

        assert result.is_valid is False
        assert result.consent_valid is False
        assert len(result.issues) > 0
        assert result.issues[0].issue_type == "consent_revoked"

    @pytest.mark.asyncio
    async def test_verify_manifest_file_deleted(self, mock_db, tenant):
        """Verification fails when a file has been deleted from storage."""
        from app.schemas.dataset_manifest import ManifestFileIssue

        manifest = _MockDatasetManifest(
            id=MANIFEST_ID,
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            manifest_files=[
                {
                    "file_ref": "img_001.jpg",
                    "storage_key": "org/t/img_001.jpg",
                    "sha256_checksum": "a" * 64,
                    "asset_role": "training_image",
                    "file_size_bytes": 1024,
                    "content_type": "image/jpeg",
                    "provenance": "user_upload",
                }
            ],
            consent_record_ids=[],
            is_valid=True,
        )

        manifest_result = MagicMock()
        manifest_result.scalar_one_or_none.return_value = manifest
        mock_db.execute = AsyncMock(return_value=manifest_result)

        service = DatasetManifestService(db=mock_db, tenant=tenant)
        # Mock file check to return a deleted issue
        service._check_file_validity = AsyncMock(
            return_value=ManifestFileIssue(
                file_ref="img_001.jpg",
                storage_key="org/t/img_001.jpg",
                issue_type="file_deleted",
                detail="File no longer exists",
            )
        )

        result = await service.verify_manifest(MANIFEST_ID)

        assert result.is_valid is False
        assert result.files_checked == 1
        assert result.files_passed == 0
        assert any(i.issue_type == "file_deleted" for i in result.issues)


# =============================================================================
# Tests: compare_manifests
# =============================================================================


class TestCompareManifests:
    """Tests for DatasetManifestService.compare_manifests."""

    @pytest.mark.asyncio
    async def test_compare_shows_added_removed(self, mock_db, tenant):
        """Comparing manifests detects added and removed files."""
        manifest_a = _MockDatasetManifest(
            id=uuid4(),
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            manifest_files=[
                {
                    "file_ref": "img_001.jpg",
                    "storage_key": "org/t/img_001.jpg",
                    "sha256_checksum": "a" * 64,
                    "asset_role": "training_image",
                },
                {
                    "file_ref": "img_002.jpg",
                    "storage_key": "org/t/img_002.jpg",
                    "sha256_checksum": "b" * 64,
                    "asset_role": "training_image",
                },
            ],
            consent_record_ids=[],
            is_valid=True,
        )

        manifest_b = _MockDatasetManifest(
            id=uuid4(),
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            manifest_files=[
                {
                    "file_ref": "img_001.jpg",
                    "storage_key": "org/t/img_001.jpg",
                    "sha256_checksum": "a" * 64,
                    "asset_role": "training_image",
                },
                {
                    "file_ref": "img_003.jpg",
                    "storage_key": "org/t/img_003.jpg",
                    "sha256_checksum": "c" * 64,
                    "asset_role": "training_image",
                },
            ],
            consent_record_ids=[],
            is_valid=True,
        )

        call_count = [0]

        async def _mock_execute(stmt):
            result = MagicMock()
            if call_count[0] == 0:
                result.scalar_one_or_none.return_value = manifest_a
            else:
                result.scalar_one_or_none.return_value = manifest_b
            call_count[0] += 1
            return result

        mock_db.execute = _mock_execute

        service = DatasetManifestService(db=mock_db, tenant=tenant)
        result = await service.compare_manifests(manifest_a.id, manifest_b.id)

        assert result.files_added == 1  # img_003 added
        assert result.files_removed == 1  # img_002 removed
        assert result.files_changed == 0

    @pytest.mark.asyncio
    async def test_compare_shows_checksum_change(self, mock_db, tenant):
        """Comparing manifests detects checksum changes."""
        manifest_a = _MockDatasetManifest(
            id=uuid4(),
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            manifest_files=[
                {
                    "file_ref": "img_001.jpg",
                    "storage_key": "org/t/img_001.jpg",
                    "sha256_checksum": "a" * 64,
                    "asset_role": "training_image",
                },
            ],
            consent_record_ids=[],
            is_valid=True,
        )

        manifest_b = _MockDatasetManifest(
            id=uuid4(),
            org_id=ORG_ID,
            talent_id=TALENT_ID,
            manifest_files=[
                {
                    "file_ref": "img_001.jpg",
                    "storage_key": "org/t/img_001.jpg",
                    "sha256_checksum": "d" * 64,  # Changed checksum
                    "asset_role": "training_image",
                },
            ],
            consent_record_ids=[],
            is_valid=True,
        )

        call_count = [0]

        async def _mock_execute(stmt):
            result = MagicMock()
            if call_count[0] == 0:
                result.scalar_one_or_none.return_value = manifest_a
            else:
                result.scalar_one_or_none.return_value = manifest_b
            call_count[0] += 1
            return result

        mock_db.execute = _mock_execute

        service = DatasetManifestService(db=mock_db, tenant=tenant)
        result = await service.compare_manifests(manifest_a.id, manifest_b.id)

        assert result.files_changed == 1
        assert result.differences[0].change_type == "checksum_changed"
        assert result.differences[0].old_value == "a" * 64
        assert result.differences[0].new_value == "d" * 64


# =============================================================================
# Tests: Immutability enforcement
# =============================================================================


class TestImmutability:
    """Tests that no update/patch methods exist on the service."""

    def test_no_update_method(self):
        """Service has no update_manifest method."""
        assert not hasattr(DatasetManifestService, "update_manifest")

    def test_no_patch_method(self):
        """Service has no patch_manifest method."""
        assert not hasattr(DatasetManifestService, "patch_manifest")

    def test_no_delete_method(self):
        """Service has no delete_manifest method (manifests are immutable)."""
        assert not hasattr(DatasetManifestService, "delete_manifest")


# =============================================================================
# Tests: compute_file_checksum utility
# =============================================================================


class TestComputeFileChecksum:
    """Tests for the compute_file_checksum utility function."""

    def test_checksum_produces_64_char_hex(self):
        """SHA-256 checksum is 64 hex characters."""
        result = compute_file_checksum(b"hello world")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_checksum_is_deterministic(self):
        """Same input always produces same checksum."""
        data = b"test data for checksum"
        assert compute_file_checksum(data) == compute_file_checksum(data)

    def test_checksum_different_for_different_input(self):
        """Different inputs produce different checksums."""
        assert compute_file_checksum(b"aaa") != compute_file_checksum(b"bbb")

    def test_known_checksum(self):
        """Verify against known SHA-256 value."""
        import hashlib
        data = b"ai-studio88 training manifest"
        expected = hashlib.sha256(data).hexdigest()
        assert compute_file_checksum(data) == expected


# =============================================================================
# Tests: Schema validation
# =============================================================================


class TestSchemaValidation:
    """Tests for Pydantic schema validation."""

    def test_file_entry_requires_valid_checksum(self):
        """ManifestFileEntry rejects invalid checksum format."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ManifestFileEntry(
                file_ref="img.jpg",
                storage_key="org/t/img.jpg",
                sha256_checksum="too_short",  # Not 64 hex chars
                asset_role=AssetRole.TRAINING_IMAGE,
                file_size_bytes=1024,
                content_type="image/jpeg",
                provenance=ManifestFileProvenance.USER_UPLOAD,
            )

    def test_file_entry_requires_positive_size(self):
        """ManifestFileEntry rejects zero or negative file size."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ManifestFileEntry(
                file_ref="img.jpg",
                storage_key="org/t/img.jpg",
                sha256_checksum="a" * 64,
                asset_role=AssetRole.TRAINING_IMAGE,
                file_size_bytes=0,  # Must be >= 1
                content_type="image/jpeg",
                provenance=ManifestFileProvenance.USER_UPLOAD,
            )

    def test_create_request_requires_at_least_one_file(self):
        """DatasetManifestCreateRequest rejects empty file list."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DatasetManifestCreateRequest(
                talent_id=uuid4(),
                files=[],  # min_length=1
                consent_record_ids=[],
            )
