"""Unit tests for ConsentService — consent record lifecycle management.

Tests cover:
    - create_consent succeeds with valid data
    - create_consent auto-increments version per talent
    - create_consent raises 404 if talent not found
    - update_consent succeeds on active record
    - update_consent raises 400 on revoked record
    - revoke_consent succeeds on active record
    - revoke_consent raises 400 on already-revoked record
    - list_consent returns paginated results
    - list_consent filters by talent_id
    - list_consent filters active_only
    - Schema validation for scopes, provenance, and revoke reason

Requirements: R10.2, R10.3, A2-004
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
# The test venv has incomplete deps (missing jose, passlib, etc).
# =============================================================================

# SQLAlchemy mocks
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

# Mock jose, passlib (transitive deps of app.core.security)
sys.modules.setdefault("jose", MagicMock())
sys.modules.setdefault("passlib", MagicMock())
sys.modules.setdefault("passlib.context", MagicMock())

# Mock pydantic-settings (for app.core.config)
_pydantic_settings_mock = MagicMock()
_pydantic_settings_mock.BaseSettings = type("BaseSettings", (), {"model_config": {}})
sys.modules.setdefault("pydantic_settings", _pydantic_settings_mock)

# Mock python-dotenv
sys.modules.setdefault("dotenv", MagicMock())

# Mock structlog
sys.modules.setdefault("structlog", MagicMock())

# Mock models
_mock_models_pkg = ModuleType("app.models")
_mock_models_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.models", _mock_models_pkg)

_mock_models_consent = ModuleType("app.models.consent")


class _MockConsentRecord:
    __tablename__ = "consent_records"

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mock_models_consent.ConsentRecord = _MockConsentRecord  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.consent", _mock_models_consent)

_mock_models_talent = ModuleType("app.models.talent")


class _MockAiTalent:
    __tablename__ = "talent"
    id = MagicMock()
    org_id = MagicMock()
    deleted_at = MagicMock()


_mock_models_talent.AiTalent = _MockAiTalent  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.talent", _mock_models_talent)

# Mock repositories package
_mock_repos_pkg = ModuleType("app.repositories")
_mock_repos_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.repositories", _mock_repos_pkg)

_mock_consent_repo_mod = ModuleType("app.repositories.consent_repository")
_mock_consent_repo_mod.ConsentRepository = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.repositories.consent_repository", _mock_consent_repo_mod)

_mock_talent_repo_mod = ModuleType("app.repositories.talent_repository")
_mock_talent_repo_mod.TalentRepository = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.repositories.talent_repository", _mock_talent_repo_mod)

# Mock backend module (some imports use backend.app path)
_mock_backend = ModuleType("backend")
_mock_backend.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("backend", _mock_backend)
sys.modules.setdefault("backend.database", MagicMock())

# Mock backend.app as a package (not MagicMock!) so backend.app.schemas works
_mock_backend_app = ModuleType("backend.app")
_mock_backend_app.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("backend.app", _mock_backend_app)

# Mock backend.app.schemas path for the schemas __init__.py imports
# The app/schemas/__init__.py imports from backend.app.schemas.base and .validation.
# We pre-register those modules so the import doesn't fail.
_mock_backend_app_schemas = ModuleType("backend.app.schemas")
_mock_backend_app_schemas.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("backend.app.schemas", _mock_backend_app_schemas)

# Pre-load the real base and validation modules under both paths
# We need to use __import__ to avoid triggering __init__
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

# Force-import consent_service so patching works
import app.services.consent_service  # noqa: E402


# =============================================================================
# Constants & Helpers
# =============================================================================

ORG_ID = uuid4()
USER_ID = uuid4()
TALENT_ID = uuid4()
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


class FakeConsentRecord:
    """Fake ConsentRecord for testing without ORM."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid4())
        self.org_id = kwargs.get("org_id", ORG_ID)
        self.talent_id = kwargs.get("talent_id", TALENT_ID)
        self.scopes = kwargs.get("scopes", ["generation", "likeness"])
        self.evidence_type = kwargs.get("evidence_type", "signed_document")
        self.evidence_url = kwargs.get("evidence_url", None)
        self.grantor_identity = kwargs.get("grantor_identity", "Jane Doe")
        self.granted_at = kwargs.get("granted_at", datetime.now(UTC))
        self.expires_at = kwargs.get("expires_at", None)
        self.revoked_at = kwargs.get("revoked_at", None)
        self.revocation_reason = kwargs.get("revocation_reason", None)
        self.restrictions = kwargs.get("restrictions", {})
        self.provenance = kwargs.get("provenance", "SELF_ATTESTED")
        self.version = kwargs.get("version", 1)
        self.verification_state = kwargs.get("verification_state", "unverified")
        self.created_at = kwargs.get("created_at", datetime.now(UTC))
        self.updated_at = kwargs.get("updated_at", datetime.now(UTC))

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= datetime.now(UTC):
            return False
        return True


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock async DB session."""
    return AsyncMock()


@pytest.fixture
def tenant():
    """Editor-level tenant context."""
    return _make_tenant(WorkspaceRole.EDITOR)


# =============================================================================
# Tests: create_consent
# =============================================================================


@pytest.mark.unit
class TestCreateConsent:
    """Tests for ConsentService.create_consent."""

    @pytest.mark.asyncio
    async def test_create_consent_success(self, mock_db, tenant):
        """Creating consent with valid data returns a record."""
        record = FakeConsentRecord(talent_id=TALENT_ID, version=1)

        with patch(
            "app.services.consent_service.ConsentRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.create = AsyncMock(return_value=record)
            repo_instance.get_next_version = AsyncMock(return_value=1)

            from app.services.consent_service import ConsentService

            service = ConsentService(db=mock_db, tenant=tenant)
            service._repo = repo_instance
            service._validate_talent_exists = AsyncMock()

            result = await service.create_consent(
                talent_id=TALENT_ID,
                scopes=["generation", "likeness"],
                provenance="SELF_ATTESTED",
                evidence_type="signed_document",
            )

            assert result.talent_id == TALENT_ID
            assert result.version == 1
            repo_instance.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_consent_talent_not_found(self, mock_db, tenant):
        """Creating consent for non-existent talent raises 404."""
        with patch(
            "app.services.consent_service.ConsentRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value

            from app.services.consent_service import ConsentService

            service = ConsentService(db=mock_db, tenant=tenant)
            service._repo = repo_instance
            service._validate_talent_exists = AsyncMock(
                side_effect=HTTPException(status_code=404, detail="Talent not found")
            )

            with pytest.raises(HTTPException) as exc_info:
                await service.create_consent(
                    talent_id=uuid4(),
                    scopes=["generation"],
                    provenance="SELF_ATTESTED",
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_consent_auto_increments_version(self, mock_db, tenant):
        """Version auto-increments per talent."""
        record = FakeConsentRecord(talent_id=TALENT_ID, version=3)

        with patch(
            "app.services.consent_service.ConsentRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.create = AsyncMock(return_value=record)
            repo_instance.get_next_version = AsyncMock(return_value=3)

            from app.services.consent_service import ConsentService

            service = ConsentService(db=mock_db, tenant=tenant)
            service._repo = repo_instance
            service._validate_talent_exists = AsyncMock()

            result = await service.create_consent(
                talent_id=TALENT_ID,
                scopes=["voice"],
                provenance="REPRESENTATIVE",
            )

            repo_instance.get_next_version.assert_called_once_with(TALENT_ID)
            assert result.version == 3


# =============================================================================
# Tests: update_consent
# =============================================================================


@pytest.mark.unit
class TestUpdateConsent:
    """Tests for ConsentService.update_consent."""

    @pytest.mark.asyncio
    async def test_update_consent_success(self, mock_db, tenant):
        """Updating an active consent record succeeds."""
        record = FakeConsentRecord(verification_state="unverified")
        updated_record = FakeConsentRecord(verification_state="verified")

        with patch(
            "app.services.consent_service.ConsentRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_by_id = AsyncMock(return_value=record)
            repo_instance.update = AsyncMock(return_value=updated_record)

            from app.services.consent_service import ConsentService

            service = ConsentService(db=mock_db, tenant=tenant)
            service._repo = repo_instance

            result = await service.update_consent(
                CONSENT_ID, verification_state="verified"
            )

            assert result.verification_state == "verified"
            repo_instance.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_revoked_consent_raises_400(self, mock_db, tenant):
        """Updating a revoked consent record raises 400."""
        record = FakeConsentRecord(
            revoked_at=datetime.now(UTC),
            revocation_reason="No longer valid",
        )

        with patch(
            "app.services.consent_service.ConsentRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_by_id = AsyncMock(return_value=record)

            from app.services.consent_service import ConsentService

            service = ConsentService(db=mock_db, tenant=tenant)
            service._repo = repo_instance

            with pytest.raises(HTTPException) as exc_info:
                await service.update_consent(
                    CONSENT_ID, verification_state="verified"
                )

            assert exc_info.value.status_code == 400
            assert "revoked" in exc_info.value.detail.lower()


# =============================================================================
# Tests: revoke_consent
# =============================================================================


@pytest.mark.unit
class TestRevokeConsent:
    """Tests for ConsentService.revoke_consent."""

    @pytest.mark.asyncio
    async def test_revoke_consent_success(self, mock_db, tenant):
        """Revoking an active consent record succeeds."""
        active_record = FakeConsentRecord(revoked_at=None)
        revoked_record = FakeConsentRecord(
            revoked_at=datetime.now(UTC),
            revocation_reason="Withdrawn by talent",
        )

        with patch(
            "app.services.consent_service.ConsentRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_by_id = AsyncMock(return_value=active_record)
            repo_instance.revoke = AsyncMock(return_value=revoked_record)

            from app.services.consent_service import ConsentService

            service = ConsentService(db=mock_db, tenant=tenant)
            service._repo = repo_instance

            result = await service.revoke_consent(
                CONSENT_ID, "Withdrawn by talent"
            )

            assert result.revoked_at is not None
            assert result.revocation_reason == "Withdrawn by talent"
            repo_instance.revoke.assert_called_once_with(
                CONSENT_ID, "Withdrawn by talent"
            )

    @pytest.mark.asyncio
    async def test_revoke_already_revoked_raises_400(self, mock_db, tenant):
        """Revoking an already-revoked record raises 400."""
        record = FakeConsentRecord(
            revoked_at=datetime.now(UTC),
            revocation_reason="Already gone",
        )

        with patch(
            "app.services.consent_service.ConsentRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_by_id = AsyncMock(return_value=record)

            from app.services.consent_service import ConsentService

            service = ConsentService(db=mock_db, tenant=tenant)
            service._repo = repo_instance

            with pytest.raises(HTTPException) as exc_info:
                await service.revoke_consent(CONSENT_ID, "Trying again")

            assert exc_info.value.status_code == 400
            assert "already revoked" in exc_info.value.detail.lower()


# =============================================================================
# Tests: list_consent
# =============================================================================


@pytest.mark.unit
class TestListConsent:
    """Tests for ConsentService.list_consent."""

    @pytest.mark.asyncio
    async def test_list_consent_returns_paginated(self, mock_db, tenant):
        """Listing consent returns items and total."""
        records = [FakeConsentRecord(), FakeConsentRecord()]

        with patch(
            "app.services.consent_service.ConsentRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.list_all = AsyncMock(return_value=(records, 2))

            from app.services.consent_service import ConsentService

            service = ConsentService(db=mock_db, tenant=tenant)
            service._repo = repo_instance

            items, total = await service.list_consent(limit=20, offset=0)

            assert len(items) == 2
            assert total == 2
            repo_instance.list_all.assert_called_once_with(
                limit=20,
                offset=0,
                talent_id=None,
                scope=None,
                active_only=False,
            )

    @pytest.mark.asyncio
    async def test_list_consent_filters_by_talent(self, mock_db, tenant):
        """Listing consent with talent_id filter passes it to repo."""
        with patch(
            "app.services.consent_service.ConsentRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.list_all = AsyncMock(return_value=([], 0))

            from app.services.consent_service import ConsentService

            service = ConsentService(db=mock_db, tenant=tenant)
            service._repo = repo_instance

            await service.list_consent(talent_id=TALENT_ID)

            call_kwargs = repo_instance.list_all.call_args[1]
            assert call_kwargs["talent_id"] == TALENT_ID

    @pytest.mark.asyncio
    async def test_list_consent_filters_active_only(self, mock_db, tenant):
        """Listing consent with active_only=True passes filter."""
        with patch(
            "app.services.consent_service.ConsentRepository"
        ) as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.list_all = AsyncMock(return_value=([], 0))

            from app.services.consent_service import ConsentService

            service = ConsentService(db=mock_db, tenant=tenant)
            service._repo = repo_instance

            await service.list_consent(active_only=True)

            call_kwargs = repo_instance.list_all.call_args[1]
            assert call_kwargs["active_only"] is True


# =============================================================================
# Tests: Schema validation
# =============================================================================


@pytest.mark.unit
class TestConsentSchemas:
    """Tests for consent Pydantic schemas."""

    def test_create_request_requires_scopes(self):
        """ConsentCreateRequest requires at least one scope."""
        from app.schemas.consent import ConsentCreateRequest

        with pytest.raises(Exception):
            ConsentCreateRequest(
                talent_id=uuid4(),
                scopes=[],
                provenance="SELF_ATTESTED",
            )

    def test_create_request_valid(self):
        """ConsentCreateRequest accepts valid data."""
        from app.schemas.consent import ConsentCreateRequest

        req = ConsentCreateRequest(
            talent_id=uuid4(),
            scopes=["generation", "likeness"],
            provenance="SELF_ATTESTED",
        )
        assert len(req.scopes) == 2
        assert req.provenance.value == "SELF_ATTESTED"

    def test_revoke_request_requires_reason(self):
        """ConsentRevokeRequest requires a non-empty reason."""
        from app.schemas.consent import ConsentRevokeRequest

        with pytest.raises(Exception):
            ConsentRevokeRequest(revocation_reason="")

    def test_revoke_request_valid(self):
        """ConsentRevokeRequest accepts valid reason."""
        from app.schemas.consent import ConsentRevokeRequest

        req = ConsentRevokeRequest(revocation_reason="Talent withdrew consent")
        assert req.revocation_reason == "Talent withdrew consent"

    def test_consent_scope_enum_values(self):
        """ConsentScope enum has all expected values."""
        from app.schemas.consent import ConsentScope

        expected = {
            "likeness", "voice", "training", "generation",
            "adult_content", "commercial", "publishing", "client_work",
        }
        actual = {s.value for s in ConsentScope}
        assert actual == expected

    def test_is_active_property_active_record(self):
        """is_active returns True for active records."""
        record = FakeConsentRecord()
        assert record.is_active is True

    def test_is_active_property_revoked(self):
        """is_active returns False for revoked records."""
        record = FakeConsentRecord(revoked_at=datetime.now(UTC))
        assert record.is_active is False

    def test_is_active_property_expired(self):
        """is_active returns False for expired records."""
        record = FakeConsentRecord(
            expires_at=datetime.now(UTC) - timedelta(days=1)
        )
        assert record.is_active is False
