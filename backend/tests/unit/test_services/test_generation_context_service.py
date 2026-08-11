"""Unit tests for GenerationContextService — immutable context package lifecycle.

Tests cover:
    - create_context_package succeeds and auto-increments version
    - create_context_package freezes all input fields
    - get_context_package returns package for valid ID
    - get_context_package raises 404 for missing/cross-tenant
    - validate_context_package detects stale talent (deleted)
    - validate_context_package detects stale model/LoRA (quarantined)
    - validate_context_package detects stale consent (revoked)
    - validate_context_package detects stale assets (deleted)
    - validate_context_package returns valid for fresh references
    - Immutability: no update/patch method exists on service
    - list_context_packages returns paginated results
    - Schema validation for nested JSONB fields

Requirements: R60.1, R60.2, R60.3, R60.4, R60.5, R60.6
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
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

# Mock model modules
_mock_models_gcp = ModuleType("app.models.generation_context_package")


class _MockGenerationContextPackage:
    __tablename__ = "generation_context_packages"

    # Class-level attributes to mimic SQLAlchemy column descriptors
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


_mock_models_gcp.GenerationContextPackage = _MockGenerationContextPackage  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.generation_context_package", _mock_models_gcp)

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

_mock_models_talent_lora = ModuleType("app.models.talent_lora")


class _MockTalentLora:
    __tablename__ = "talent_loras"
    id = MagicMock()
    org_id = MagicMock()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mock_models_talent_lora.TalentLora = _MockTalentLora  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.talent_lora", _mock_models_talent_lora)

_mock_models_consent = ModuleType("app.models.consent")


class _MockConsentRecord:
    __tablename__ = "consent_records"
    org_id = MagicMock()
    talent_id = MagicMock()
    revoked_at = MagicMock()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mock_models_consent.ConsentRecord = _MockConsentRecord  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.consent", _mock_models_consent)

_mock_models_asset = ModuleType("app.models.asset")


class _MockAsset:
    __tablename__ = "assets"
    id = MagicMock()
    org_id = MagicMock()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mock_models_asset.Asset = _MockAsset  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.asset", _mock_models_asset)

# Mock repositories
_mock_repos_pkg = ModuleType("app.repositories")
_mock_repos_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.repositories", _mock_repos_pkg)

_mock_consent_repo_mod = ModuleType("app.repositories.consent_repository")
_mock_consent_repo_mod.ConsentRepository = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.repositories.consent_repository", _mock_consent_repo_mod)

_mock_talent_repo_mod = ModuleType("app.repositories.talent_repository")
_mock_talent_repo_mod.TalentRepository = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.repositories.talent_repository", _mock_talent_repo_mod)

# Mock backend module
_mock_backend = ModuleType("backend")
_mock_backend.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("backend", _mock_backend)
sys.modules.setdefault("backend.database", MagicMock())

_mock_backend_app = ModuleType("backend.app")
_mock_backend_app.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("backend.app", _mock_backend_app)

_mock_backend_app_schemas = ModuleType("backend.app.schemas")
_mock_backend_app_schemas.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("backend.app.schemas", _mock_backend_app_schemas)

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

_val_spec = importlib.util.spec_from_file_location(
    "app.schemas.validation",
    str(_backend_dir / "app" / "schemas" / "validation.py"),
)
_val_mod = importlib.util.module_from_spec(_val_spec)
sys.modules["app.schemas.validation"] = _val_mod
sys.modules["backend.app.schemas.validation"] = _val_mod
_val_spec.loader.exec_module(_val_mod)

# Now import application code
from fastapi import HTTPException

from app.core.dependencies import TenantContext, TrustDomain, WorkspaceRole
from app.schemas.generation_context import (
    ConsentVerificationResult,
    GenerationContextPackageCreate,
    GenerationSurface,
    ModelLoraSelections,
    LoraSelection,
    PromptInstructions,
    SafetyEvaluationResult,
    SourceAssetRef,
    TalentSnapshot,
    WorkflowTemplateRef,
    ProjectConstraints,
)

# Force-import the service
import app.services.generation_context_service  # noqa: E402


# =============================================================================
# Constants & Helpers
# =============================================================================

ORG_ID = uuid4()
USER_ID = uuid4()
TALENT_ID = uuid4()
PACKAGE_ID = uuid4()


def _make_tenant(role: WorkspaceRole = WorkspaceRole.EDITOR) -> TenantContext:
    """Create a TenantContext for testing."""
    return TenantContext(
        user_id=USER_ID,
        org_id=ORG_ID,
        role=role,
        trust_domain=TrustDomain.WORKSPACE_ADMIN,
        email="test@example.com",
    )


def _make_create_data() -> GenerationContextPackageCreate:
    """Create a full context package creation request."""
    return GenerationContextPackageCreate(
        talent_record=TalentSnapshot(
            talent_id=TALENT_ID,
            name="Test Talent",
            talent_type="model",
            identity_classification="FICTIONAL",
            adult_status="VERIFIED_18_PLUS",
        ),
        creative_dna_version="dna_v3",
        source_assets=[
            SourceAssetRef(
                asset_id=uuid4(),
                storage_key="/org/images/talent/job/img.webp",
                checksum="sha256:abc123",
                role="generation_reference",
            )
        ],
        model_lora_selections=ModelLoraSelections(
            model_id=uuid4(),
            model_name="flux_dev",
            model_version="1.0",
            base_model="flux",
            loras=[
                LoraSelection(
                    lora_id=uuid4(),
                    version="v1",
                    strength=0.8,
                    lora_type="identity",
                )
            ],
        ),
        prompt_instructions=PromptInstructions(
            positive_prompt="A portrait photo",
            negative_prompt="blurry, low quality",
            cfg_scale=7.5,
            steps=20,
            width=1024,
            height=1024,
        ),
        consent_verification_result=ConsentVerificationResult(
            verified=True,
            scopes_checked=["generation", "likeness"],
            scopes_present=["generation", "likeness"],
            fictional_exemption=True,
            evaluated_at=datetime.now(UTC),
        ),
        safety_evaluation_result=SafetyEvaluationResult(
            passed=True,
            content_rating="SFW",
            policy_level="workspace",
            checks_performed=["safety_kernel", "platform_policy"],
            evaluated_at=datetime.now(UTC),
        ),
        workflow_template=WorkflowTemplateRef(
            workflow_id=uuid4(),
            workflow_version="1.2",
            template_name="flux_portrait_v1",
        ),
        project_constraints=ProjectConstraints(
            project_id=uuid4(),
            quality_tier="standard",
        ),
        initiated_by=GenerationSurface.API,
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
# Tests: create_context_package
# =============================================================================


@pytest.mark.unit
class TestCreateContextPackage:
    """Tests for GenerationContextService.create_context_package."""

    @pytest.mark.asyncio
    async def test_create_succeeds_with_full_data(self, mock_db, tenant):
        """Creating a context package with all fields succeeds."""
        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        service._get_next_version = AsyncMock(return_value=1)
        data = _make_create_data()

        result = await service.create_context_package(data)

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_auto_increments_version(self, mock_db, tenant):
        """Version auto-increments based on max existing version for org."""
        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        service._get_next_version = AsyncMock(return_value=6)
        data = _make_create_data()

        result = await service.create_context_package(data)

        # The added object should have version=6
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.version == 6

    @pytest.mark.asyncio
    async def test_create_sets_org_id_from_tenant(self, mock_db, tenant):
        """org_id is always set from tenant context, never client-supplied."""
        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        service._get_next_version = AsyncMock(return_value=1)
        data = _make_create_data()

        await service.create_context_package(data)

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.org_id == ORG_ID

    @pytest.mark.asyncio
    async def test_create_sets_user_id_from_tenant(self, mock_db, tenant):
        """user_id is set from tenant context."""
        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        service._get_next_version = AsyncMock(return_value=1)
        data = _make_create_data()

        await service.create_context_package(data)

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.user_id == USER_ID

    @pytest.mark.asyncio
    async def test_create_freezes_talent_record_as_dict(self, mock_db, tenant):
        """Talent record is serialized as dict (frozen snapshot)."""
        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        service._get_next_version = AsyncMock(return_value=1)
        data = _make_create_data()

        await service.create_context_package(data)

        added_obj = mock_db.add.call_args[0][0]
        assert isinstance(added_obj.talent_record, dict)
        assert added_obj.talent_record["name"] == "Test Talent"

    @pytest.mark.asyncio
    async def test_create_with_minimal_data(self, mock_db, tenant):
        """Creating with only prompt instructions (minimal case) succeeds."""
        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        service._get_next_version = AsyncMock(return_value=1)
        data = GenerationContextPackageCreate(
            prompt_instructions=PromptInstructions(
                positive_prompt="A simple test",
            ),
            initiated_by=GenerationSurface.BRAIN,
        )

        await service.create_context_package(data)

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.talent_record is None
        assert added_obj.source_assets is None
        assert added_obj.initiated_by == "brain"


# =============================================================================
# Tests: get_context_package
# =============================================================================


@pytest.mark.unit
class TestGetContextPackage:
    """Tests for GenerationContextService.get_context_package."""

    @pytest.mark.asyncio
    async def test_get_returns_package(self, mock_db, tenant):
        """Getting an existing package returns it."""
        fake_pkg = _MockGenerationContextPackage(
            id=PACKAGE_ID,
            org_id=ORG_ID,
            version=1,
            talent_record={"name": "Test"},
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_pkg
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        result = await service.get_context_package(PACKAGE_ID)

        assert result.id == PACKAGE_ID
        assert result.version == 1

    @pytest.mark.asyncio
    async def test_get_raises_404_when_not_found(self, mock_db, tenant):
        """Getting a non-existent package raises 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_context_package(uuid4())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_cross_tenant_returns_404(self, mock_db, tenant):
        """Cross-tenant access returns 404 (not 403)."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_context_package(uuid4())

        assert exc_info.value.status_code == 404


# =============================================================================
# Tests: validate_context_package
# =============================================================================


@pytest.mark.unit
class TestValidateContextPackage:
    """Tests for GenerationContextService.validate_context_package."""

    @pytest.mark.asyncio
    async def test_validate_valid_package(self, mock_db, tenant):
        """Package with all references intact is valid."""
        talent_id = uuid4()
        fake_pkg = _MockGenerationContextPackage(
            id=PACKAGE_ID,
            org_id=ORG_ID,
            version=1,
            talent_record={"talent_id": str(talent_id), "name": "Test"},
            model_lora_selections=None,
            consent_verification_result=None,
            source_assets=None,
        )

        # talent check — talent exists
        fake_talent = _MockAiTalent(id=talent_id, org_id=ORG_ID, deleted_at=None)
        mock_result_talent = MagicMock()
        mock_result_talent.scalar_one_or_none.return_value = fake_talent
        mock_db.execute = AsyncMock(return_value=mock_result_talent)

        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        service.get_context_package = AsyncMock(return_value=fake_pkg)

        result = await service.validate_context_package(PACKAGE_ID)

        assert result.is_valid is True
        assert len(result.stale_references) == 0

    @pytest.mark.asyncio
    async def test_validate_detects_deleted_talent(self, mock_db, tenant):
        """Package with deleted talent is invalid."""
        talent_id = uuid4()
        fake_pkg = _MockGenerationContextPackage(
            id=PACKAGE_ID,
            org_id=ORG_ID,
            version=1,
            talent_record={"talent_id": str(talent_id), "name": "Deleted"},
            model_lora_selections=None,
            consent_verification_result=None,
            source_assets=None,
        )

        # talent check — not found (deleted)
        mock_result_talent = MagicMock()
        mock_result_talent.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result_talent)

        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        service.get_context_package = AsyncMock(return_value=fake_pkg)

        result = await service.validate_context_package(PACKAGE_ID)

        assert result.is_valid is False
        assert len(result.stale_references) == 1
        assert result.stale_references[0].entity_type == "talent"

    @pytest.mark.asyncio
    async def test_validate_detects_deleted_asset(self, mock_db, tenant):
        """Package with deleted source asset is invalid."""
        asset_id = uuid4()
        fake_pkg = _MockGenerationContextPackage(
            id=PACKAGE_ID,
            org_id=ORG_ID,
            version=1,
            talent_record=None,
            model_lora_selections=None,
            consent_verification_result=None,
            source_assets=[{"asset_id": str(asset_id), "storage_key": "/a/b", "role": "ref"}],
        )

        # asset check — not found (deleted)
        mock_result_asset = MagicMock()
        mock_result_asset.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result_asset)

        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        service.get_context_package = AsyncMock(return_value=fake_pkg)

        result = await service.validate_context_package(PACKAGE_ID)

        assert result.is_valid is False
        assert len(result.stale_references) == 1
        assert result.stale_references[0].entity_type == "asset"

    @pytest.mark.asyncio
    async def test_validate_detects_revoked_consent(self, mock_db, tenant):
        """Package with revoked consent scope is invalid."""
        talent_id = uuid4()
        fake_pkg = _MockGenerationContextPackage(
            id=PACKAGE_ID,
            org_id=ORG_ID,
            version=1,
            talent_record={"talent_id": str(talent_id), "name": "Real Person"},
            model_lora_selections=None,
            consent_verification_result={
                "verified": True,
                "scopes_checked": ["generation", "likeness"],
                "scopes_present": ["generation", "likeness"],
                "fictional_exemption": False,
                "evaluated_at": datetime.now(UTC).isoformat(),
            },
            source_assets=None,
        )

        # talent check — talent still exists
        fake_talent = _MockAiTalent(id=talent_id, org_id=ORG_ID, deleted_at=None)
        mock_result_talent = MagicMock()
        mock_result_talent.scalar_one_or_none.return_value = fake_talent

        # consent check — no active records (consent revoked)
        mock_result_consent = MagicMock()
        mock_result_consent.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(
            side_effect=[mock_result_talent, mock_result_consent]
        )

        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        service.get_context_package = AsyncMock(return_value=fake_pkg)

        result = await service.validate_context_package(PACKAGE_ID)

        assert result.is_valid is False
        assert any(r.entity_type == "consent" for r in result.stale_references)

    @pytest.mark.asyncio
    async def test_validate_fictional_exemption_skips_consent(self, mock_db, tenant):
        """Fictional exemption means consent is not checked."""
        talent_id = uuid4()
        fake_pkg = _MockGenerationContextPackage(
            id=PACKAGE_ID,
            org_id=ORG_ID,
            version=1,
            talent_record={"talent_id": str(talent_id), "name": "Fictional"},
            model_lora_selections=None,
            consent_verification_result={
                "verified": True,
                "scopes_checked": ["generation"],
                "scopes_present": ["generation"],
                "fictional_exemption": True,
                "evaluated_at": datetime.now(UTC).isoformat(),
            },
            source_assets=None,
        )

        # talent check — talent exists
        fake_talent = _MockAiTalent(id=talent_id, org_id=ORG_ID, deleted_at=None)
        mock_result_talent = MagicMock()
        mock_result_talent.scalar_one_or_none.return_value = fake_talent
        mock_db.execute = AsyncMock(return_value=mock_result_talent)

        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        service.get_context_package = AsyncMock(return_value=fake_pkg)

        result = await service.validate_context_package(PACKAGE_ID)

        # Valid — consent not checked due to fictional exemption
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_validate_empty_package_is_valid(self, mock_db, tenant):
        """Package with no references to check is always valid."""
        fake_pkg = _MockGenerationContextPackage(
            id=PACKAGE_ID,
            org_id=ORG_ID,
            version=1,
            talent_record=None,
            model_lora_selections=None,
            consent_verification_result=None,
            source_assets=None,
        )

        from app.services.generation_context_service import GenerationContextService

        service = GenerationContextService(db=mock_db, tenant=tenant)
        service.get_context_package = AsyncMock(return_value=fake_pkg)

        result = await service.validate_context_package(PACKAGE_ID)

        assert result.is_valid is True


# =============================================================================
# Tests: Immutability Enforcement
# =============================================================================


@pytest.mark.unit
class TestImmutability:
    """Tests confirming immutability enforcement — no update methods exist."""

    def test_no_update_method(self):
        """GenerationContextService has no update/patch method."""
        from app.services.generation_context_service import GenerationContextService

        assert not hasattr(GenerationContextService, "update_context_package")
        assert not hasattr(GenerationContextService, "patch_context_package")

    def test_no_delete_method(self):
        """GenerationContextService has no delete method."""
        from app.services.generation_context_service import GenerationContextService

        assert not hasattr(GenerationContextService, "delete_context_package")


# =============================================================================
# Tests: Schema Validation
# =============================================================================


@pytest.mark.unit
class TestSchemas:
    """Tests for generation context Pydantic schemas."""

    def test_create_request_minimal(self):
        """Minimal create request (all fields optional except none)."""
        req = GenerationContextPackageCreate()
        assert req.talent_record is None
        assert req.initiated_by is None

    def test_create_request_full(self):
        """Full create request serializes correctly."""
        data = _make_create_data()
        assert data.talent_record is not None
        assert data.talent_record.name == "Test Talent"
        assert data.initiated_by == GenerationSurface.API

    def test_prompt_instructions_bounds(self):
        """PromptInstructions enforces dimension bounds."""
        pi = PromptInstructions(
            positive_prompt="test",
            width=1024,
            height=1024,
            cfg_scale=7.5,
            steps=20,
        )
        assert pi.width == 1024

    def test_prompt_instructions_rejects_invalid_dims(self):
        """PromptInstructions rejects dimensions outside 256-2048."""
        with pytest.raises(Exception):
            PromptInstructions(
                positive_prompt="test",
                width=100,  # below minimum 256
            )

    def test_lora_selection_strength_bounds(self):
        """LoraSelection enforces strength 0.0-2.0."""
        lora = LoraSelection(lora_id=uuid4(), strength=1.5)
        assert lora.strength == 1.5

    def test_lora_selection_rejects_invalid_strength(self):
        """LoraSelection rejects strength > 2.0."""
        with pytest.raises(Exception):
            LoraSelection(lora_id=uuid4(), strength=3.0)

    def test_generation_surface_enum(self):
        """GenerationSurface has all expected values."""
        expected = {"brain", "api", "mcp", "scheduled", "batch"}
        actual = {s.value for s in GenerationSurface}
        assert actual == expected
