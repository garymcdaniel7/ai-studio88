"""Unit tests for Release Identity service, model, and schemas.

Tests the immutable Release Identity system including:
- ReleaseIdentityCreate schema validation (completeness, hex SHA)
- ReleaseIdentityService.validate_completeness() logic
- Incomplete release rejection (R72.5)
- Service create/query/compare flows (mocked DB)

No I/O, no DB — mocks all external dependencies.

Validates: Requirements R72.1, R72.2, R72.3, R72.4, R72.5, R72.6
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

# =============================================================================
# Mock sqlalchemy and app.db BEFORE importing modules that depend on it.
# =============================================================================

_sa_mock = MagicMock()
_sa_ext_mock = MagicMock()
_sa_ext_asyncio_mock = MagicMock()

_sa_ext_asyncio_mock.AsyncEngine = MagicMock
_sa_ext_asyncio_mock.AsyncSession = MagicMock
_sa_ext_asyncio_mock.async_sessionmaker = MagicMock
_sa_ext_asyncio_mock.create_async_engine = MagicMock

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.ext", _sa_ext_mock)
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.orm", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", MagicMock())
sys.modules.setdefault("sqlalchemy.exc", MagicMock())

# Mock app.db as a package with sub-modules
_mock_db = ModuleType("app.db")
_mock_db_base = ModuleType("app.db.base")
_mock_db_session = ModuleType("app.db.session")
_mock_db_tenant_scope = ModuleType("app.db.tenant_scope")

_mock_db_base.Base = type("Base", (), {
    "__tablename__": "",
    "__table_args__": (),
    "metadata": MagicMock(),
})
_mock_db_base.UUIDMixin = type("UUIDMixin", (), {})
_mock_db_base.TimestampMixin = type("TimestampMixin", (), {})
_mock_db_base.TenantMixin = type("TenantMixin", (), {})
_mock_db_base.SoftDeleteMixin = type("SoftDeleteMixin", (), {})
_mock_db_session.get_db_session = MagicMock()
_mock_db_tenant_scope.validate_org_id = MagicMock()

sys.modules.setdefault("app.db", _mock_db)
sys.modules.setdefault("app.db.base", _mock_db_base)
sys.modules.setdefault("app.db.session", _mock_db_session)
sys.modules.setdefault("app.db.tenant_scope", _mock_db_tenant_scope)

# Mock app.core.logging
_mock_core = ModuleType("app.core")
_mock_core_logging = ModuleType("app.core.logging")
_mock_logger = MagicMock()
_mock_core_logging.get_logger = MagicMock(return_value=_mock_logger)
sys.modules.setdefault("app.core", _mock_core)
sys.modules.setdefault("app.core.logging", _mock_core_logging)

# Mock app.core.config
_mock_core_config = ModuleType("app.core.config")
_mock_core_config.get_settings = MagicMock()
_mock_core_config.reset_settings = MagicMock()
sys.modules.setdefault("app.core.config", _mock_core_config)

# =============================================================================
# Import modules via importlib to bypass app.models.__init__.py imports
# =============================================================================
import importlib.util

# Load the ORM model directly (bypasses __init__.py which loads all models)
_model_spec = importlib.util.spec_from_file_location(
    "app.models.release_identity",
    os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "app", "models", "release_identity.py"
    ),
)
_model_mod = importlib.util.module_from_spec(_model_spec)
sys.modules["app.models.release_identity"] = _model_mod
_model_spec.loader.exec_module(_model_mod)  # type: ignore[union-attr]

ReleaseIdentity = _model_mod.ReleaseIdentity

# Import schemas (pure Pydantic, no SA dependency issues)
from app.schemas.release_identity import (  # noqa: E402
    ReleaseIdentityCompareResponse,
    ReleaseIdentityCreate,
    ReleaseIdentityListResponse,
    ReleaseIdentityResponse,
    ReleaseIdentityVersionInfo,
)

# Load the service module directly
_service_spec = importlib.util.spec_from_file_location(
    "app.services.release_identity_service",
    os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "app", "services", "release_identity_service.py"
    ),
)
_service_mod = importlib.util.module_from_spec(_service_spec)
sys.modules["app.services.release_identity_service"] = _service_mod
_service_spec.loader.exec_module(_service_mod)  # type: ignore[union-attr]

IncompleteReleaseError = _service_mod.IncompleteReleaseError
ReleaseIdentityService = _service_mod.ReleaseIdentityService
ReleaseNotFoundError = _service_mod.ReleaseNotFoundError


# =============================================================================
# Schema Validation Tests
# =============================================================================


@pytest.mark.unit
class TestReleaseIdentityCreateSchema:
    """Test ReleaseIdentityCreate Pydantic schema validation."""

    def _valid_data(self) -> dict:
        """Return a valid creation payload."""
        return {
            "git_commit_sha": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            "frontend_artifact": "vercel-dep-abc123",
            "backend_artifact": "docker-sha256:deadbeef",
            "migration_set": "alembic-head-abc123",
            "config_version": "config-v2-hash-xyz",
            "model_manifest": {"sdxl": "v1.0", "flux": "v2.1"},
            "deployment_ids": ["vercel-123", "railway-456"],
            "created_by": "ci-pipeline",
        }

    def test_valid_creation(self) -> None:
        """Happy path: all fields present and valid."""
        data = self._valid_data()
        schema = ReleaseIdentityCreate(**data)
        assert schema.git_commit_sha == data["git_commit_sha"]
        assert schema.frontend_artifact == data["frontend_artifact"]
        assert schema.backend_artifact == data["backend_artifact"]
        assert schema.migration_set == data["migration_set"]
        assert schema.config_version == data["config_version"]
        assert schema.model_manifest == data["model_manifest"]
        assert schema.deployment_ids == data["deployment_ids"]

    def test_short_commit_sha_valid(self) -> None:
        """Short (7-char) commit SHA is valid."""
        data = self._valid_data()
        data["git_commit_sha"] = "a1b2c3d"
        schema = ReleaseIdentityCreate(**data)
        assert schema.git_commit_sha == "a1b2c3d"

    def test_commit_sha_too_short(self) -> None:
        """Commit SHA under 7 chars is rejected."""
        data = self._valid_data()
        data["git_commit_sha"] = "abc"
        with pytest.raises(ValidationError) as exc_info:
            ReleaseIdentityCreate(**data)
        assert "min_length" in str(exc_info.value).lower() or "at least 7" in str(exc_info.value).lower()

    def test_commit_sha_non_hex_rejected(self) -> None:
        """Non-hexadecimal commit SHA is rejected."""
        data = self._valid_data()
        data["git_commit_sha"] = "zzzzzzz"
        with pytest.raises(ValidationError) as exc_info:
            ReleaseIdentityCreate(**data)
        assert "hexadecimal" in str(exc_info.value).lower()

    def test_missing_git_commit_sha(self) -> None:
        """Missing git_commit_sha raises ValidationError."""
        data = self._valid_data()
        del data["git_commit_sha"]
        with pytest.raises(ValidationError):
            ReleaseIdentityCreate(**data)

    def test_missing_frontend_artifact(self) -> None:
        """Missing frontend_artifact raises ValidationError."""
        data = self._valid_data()
        del data["frontend_artifact"]
        with pytest.raises(ValidationError):
            ReleaseIdentityCreate(**data)

    def test_missing_backend_artifact(self) -> None:
        """Missing backend_artifact raises ValidationError."""
        data = self._valid_data()
        del data["backend_artifact"]
        with pytest.raises(ValidationError):
            ReleaseIdentityCreate(**data)

    def test_missing_migration_set(self) -> None:
        """Missing migration_set raises ValidationError."""
        data = self._valid_data()
        del data["migration_set"]
        with pytest.raises(ValidationError):
            ReleaseIdentityCreate(**data)

    def test_empty_frontend_artifact_rejected(self) -> None:
        """Empty string frontend_artifact is rejected (min_length=1)."""
        data = self._valid_data()
        data["frontend_artifact"] = ""
        with pytest.raises(ValidationError):
            ReleaseIdentityCreate(**data)

    def test_model_manifest_defaults_to_empty_dict(self) -> None:
        """model_manifest defaults to empty dict if omitted."""
        data = self._valid_data()
        del data["model_manifest"]
        schema = ReleaseIdentityCreate(**data)
        assert schema.model_manifest == {}

    def test_deployment_ids_defaults_to_empty_list(self) -> None:
        """deployment_ids defaults to empty list if omitted."""
        data = self._valid_data()
        del data["deployment_ids"]
        schema = ReleaseIdentityCreate(**data)
        assert schema.deployment_ids == []

    def test_commit_sha_normalized_to_lowercase(self) -> None:
        """Commit SHA is normalized to lowercase."""
        data = self._valid_data()
        data["git_commit_sha"] = "A1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6E7F8A9B0"
        schema = ReleaseIdentityCreate(**data)
        assert schema.git_commit_sha == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"

    def test_whitespace_only_config_version_rejected(self) -> None:
        """Whitespace-only config_version fails (stripped to empty by BaseSchema)."""
        data = self._valid_data()
        data["config_version"] = "   "
        with pytest.raises(ValidationError):
            ReleaseIdentityCreate(**data)


# =============================================================================
# Service validate_completeness Tests
# =============================================================================


@pytest.mark.unit
class TestValidateCompleteness:
    """Test ReleaseIdentityService.validate_completeness() method.

    Validates: R72.5 — reject deployments that cannot produce
    a complete Release_Identity.
    """

    def _valid_create_data(self) -> ReleaseIdentityCreate:
        return ReleaseIdentityCreate(
            git_commit_sha="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            frontend_artifact="vercel-dep-abc123",
            backend_artifact="docker-sha256:deadbeef",
            migration_set="alembic-head-abc123",
            config_version="config-v2-hash-xyz",
        )

    def test_valid_data_passes(self) -> None:
        """Complete data passes validation without raising."""
        data = self._valid_create_data()
        # Should not raise
        ReleaseIdentityService.validate_completeness(data)

    def test_missing_git_commit_sha_raises(self) -> None:
        """Empty git_commit_sha raises IncompleteReleaseError.

        Note: Pydantic won't allow truly empty (min_length=7), but
        the service validates post-schema as defense in depth.
        """
        # Build with a valid SHA, then monkeypatch to simulate empty
        data = self._valid_create_data()
        object.__setattr__(data, "git_commit_sha", "")
        with pytest.raises(IncompleteReleaseError) as exc_info:
            ReleaseIdentityService.validate_completeness(data)
        assert "git_commit_sha" in exc_info.value.missing_fields

    def test_missing_frontend_artifact_raises(self) -> None:
        """Empty frontend_artifact raises IncompleteReleaseError."""
        data = self._valid_create_data()
        object.__setattr__(data, "frontend_artifact", "")
        with pytest.raises(IncompleteReleaseError) as exc_info:
            ReleaseIdentityService.validate_completeness(data)
        assert "frontend_artifact" in exc_info.value.missing_fields

    def test_missing_backend_artifact_raises(self) -> None:
        """Empty backend_artifact raises IncompleteReleaseError."""
        data = self._valid_create_data()
        object.__setattr__(data, "backend_artifact", "")
        with pytest.raises(IncompleteReleaseError) as exc_info:
            ReleaseIdentityService.validate_completeness(data)
        assert "backend_artifact" in exc_info.value.missing_fields

    def test_missing_migration_set_raises(self) -> None:
        """Empty migration_set raises IncompleteReleaseError."""
        data = self._valid_create_data()
        object.__setattr__(data, "migration_set", "")
        with pytest.raises(IncompleteReleaseError) as exc_info:
            ReleaseIdentityService.validate_completeness(data)
        assert "migration_set" in exc_info.value.missing_fields

    def test_multiple_missing_fields(self) -> None:
        """Multiple missing fields are all reported."""
        data = self._valid_create_data()
        object.__setattr__(data, "git_commit_sha", "")
        object.__setattr__(data, "frontend_artifact", "   ")
        with pytest.raises(IncompleteReleaseError) as exc_info:
            ReleaseIdentityService.validate_completeness(data)
        assert len(exc_info.value.missing_fields) == 2
        assert "git_commit_sha" in exc_info.value.missing_fields
        assert "frontend_artifact" in exc_info.value.missing_fields

    def test_whitespace_only_treated_as_missing(self) -> None:
        """Fields containing only whitespace are treated as missing."""
        data = self._valid_create_data()
        object.__setattr__(data, "backend_artifact", "   ")
        with pytest.raises(IncompleteReleaseError) as exc_info:
            ReleaseIdentityService.validate_completeness(data)
        assert "backend_artifact" in exc_info.value.missing_fields


# =============================================================================
# Service create_release Tests (mocked DB)
# =============================================================================


@pytest.mark.unit
class TestReleaseIdentityServiceCreate:
    """Test ReleaseIdentityService.create_release() with mocked DB."""

    def _valid_create_data(self) -> ReleaseIdentityCreate:
        return ReleaseIdentityCreate(
            git_commit_sha="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            frontend_artifact="vercel-dep-abc123",
            backend_artifact="docker-sha256:deadbeef",
            migration_set="alembic-head-abc123",
            config_version="config-v2-hash-xyz",
            model_manifest={"sdxl": "v1.0"},
            deployment_ids=["vercel-123"],
            created_by="ci-pipeline",
        )

    @pytest.mark.asyncio
    async def test_create_release_success(self) -> None:
        """Successful release creation deactivates previous and persists new."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock())
        mock_db.flush = AsyncMock()
        mock_db.add = MagicMock()

        # Patch ReleaseIdentity constructor to return a mock
        mock_release = MagicMock()
        mock_release.id = uuid4()
        mock_release.is_current = True
        mock_release.git_commit_sha = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
        mock_release.frontend_artifact = "vercel-dep-abc123"
        mock_release.backend_artifact = "docker-sha256:deadbeef"
        mock_release.migration_set = "alembic-head-abc123"
        mock_release.config_version = "config-v2-hash-xyz"
        mock_release.created_by = "ci-pipeline"

        with patch.object(_service_mod, "ReleaseIdentity", return_value=mock_release):
            service = ReleaseIdentityService(mock_db)
            data = self._valid_create_data()
            result = await service.create_release(data)

        # Should have called execute (to deactivate previous) and add + flush
        mock_db.execute.assert_called_once()
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

        # The returned object should be the mock release
        assert result is mock_release

    @pytest.mark.asyncio
    async def test_create_release_incomplete_rejected(self) -> None:
        """Incomplete release data raises IncompleteReleaseError (R72.5)."""
        mock_db = AsyncMock()
        service = ReleaseIdentityService(mock_db)

        data = self._valid_create_data()
        object.__setattr__(data, "git_commit_sha", "")

        with pytest.raises(IncompleteReleaseError):
            await service.create_release(data)

        # Should NOT have called DB operations
        mock_db.add.assert_not_called()
        mock_db.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_release_immutable(self) -> None:
        """Verify that created release records are not modified after creation.

        R72.3: Immutable record created during deployment, never modified.
        """
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock())
        mock_db.flush = AsyncMock()
        mock_db.add = MagicMock()

        mock_release = MagicMock()
        mock_release.id = uuid4()

        with patch.object(_service_mod, "ReleaseIdentity", return_value=mock_release):
            service = ReleaseIdentityService(mock_db)
            data = self._valid_create_data()
            await service.create_release(data)

        # Verify no update calls were made on the new record
        # (only the deactivate-previous execute should have run)
        assert mock_db.execute.call_count == 1  # Only deactivate


# =============================================================================
# Service get_current Tests (mocked DB)
# =============================================================================


@pytest.mark.unit
class TestReleaseIdentityServiceGetCurrent:
    """Test ReleaseIdentityService.get_current() with mocked DB."""

    @pytest.mark.asyncio
    async def test_get_current_returns_active(self) -> None:
        """get_current returns the record with is_current=True."""
        mock_release = MagicMock()
        mock_release.is_current = True
        mock_release.git_commit_sha = "abc1234"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_release

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ReleaseIdentityService(mock_db)
        result = await service.get_current()

        assert result is mock_release
        assert result.is_current is True

    @pytest.mark.asyncio
    async def test_get_current_returns_none_when_empty(self) -> None:
        """get_current returns None when no release has been registered."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ReleaseIdentityService(mock_db)
        result = await service.get_current()

        assert result is None


# =============================================================================
# Response Schema Tests
# =============================================================================


@pytest.mark.unit
class TestReleaseIdentityResponseSchema:
    """Test ReleaseIdentityResponse Pydantic schema serialization."""

    def test_response_serialization(self) -> None:
        """Response schema correctly serializes a release identity."""
        now = datetime.now(timezone.utc)
        release_id = uuid4()

        response = ReleaseIdentityResponse(
            id=release_id,
            git_commit_sha="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            frontend_artifact="vercel-dep-abc123",
            backend_artifact="docker-sha256:deadbeef",
            migration_set="alembic-head-abc123",
            config_version="config-v2-hash-xyz",
            model_manifest={"sdxl": "v1.0"},
            deployment_ids=["vercel-123", "railway-456"],
            is_current=True,
            created_at=now,
            created_by="ci-pipeline",
        )

        assert response.id == release_id
        assert response.is_current is True
        assert response.model_manifest == {"sdxl": "v1.0"}
        assert response.deployment_ids == ["vercel-123", "railway-456"]

    def test_version_info_schema(self) -> None:
        """ReleaseIdentityVersionInfo provides compact info for /ready."""
        info = ReleaseIdentityVersionInfo(
            release_id="some-uuid",
            git_commit_sha="a1b2c3d",
            frontend_artifact="vercel-123",
            backend_artifact="docker-abc",
            migration_set="head-xyz",
            config_version="v2",
            created_at="2025-01-01T00:00:00Z",
        )

        assert info.git_commit_sha == "a1b2c3d"
        assert len(info.git_commit_sha) == 7


# =============================================================================
# Exception Tests
# =============================================================================


@pytest.mark.unit
class TestReleaseIdentityExceptions:
    """Test custom exception classes."""

    def test_incomplete_release_error(self) -> None:
        """IncompleteReleaseError carries missing fields."""
        exc = IncompleteReleaseError(["git_commit_sha", "frontend_artifact"])
        assert exc.code == "INCOMPLETE_RELEASE_IDENTITY"
        assert "git_commit_sha" in exc.message
        assert "frontend_artifact" in exc.message
        assert exc.missing_fields == ["git_commit_sha", "frontend_artifact"]

    def test_release_not_found_error(self) -> None:
        """ReleaseNotFoundError carries the identifier."""
        exc = ReleaseNotFoundError("some-uuid")
        assert exc.code == "RELEASE_NOT_FOUND"
        assert "some-uuid" in exc.message
