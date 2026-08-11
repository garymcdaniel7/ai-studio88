"""Unit tests for tenant-scoped query enforcement (Task 3.3).

Validates: Requirements R2.2, R2.6, R2.7, R2.8, R2.9, R2.10

Tests cover:
    - validate_org_id rejects empty string
    - validate_org_id rejects None
    - validate_org_id rejects quarantined UUID
    - validate_org_id passes valid UUIDs
    - Middleware returns 422 for quarantined UUID
    - Middleware returns 401 for missing auth
    - Cross-tenant GET returns 404 (not 403)
    - database.py functions use validate_org_id (quarantined UUID rejected)

Run with:
    pytest tests/unit/test_tenant_context.py -v
"""

from __future__ import annotations

import os
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend/ is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# =============================================================================
# Tests: backend/tenant_context.py — validate_org_id
# =============================================================================


@pytest.mark.unit
class TestValidateOrgId:
    """Tests for the centralized validate_org_id function."""

    def test_rejects_empty_string(self):
        """Empty string org_id must be rejected."""
        from backend.tenant_context import TenantValidationError, validate_org_id

        with pytest.raises(TenantValidationError) as exc_info:
            validate_org_id("")

        assert "org_id is required" in str(exc_info.value)

    def test_rejects_none(self):
        """None org_id must be rejected."""
        from backend.tenant_context import TenantValidationError, validate_org_id

        with pytest.raises(TenantValidationError) as exc_info:
            validate_org_id(None)

        assert "org_id is required" in str(exc_info.value)

    def test_rejects_quarantined_uuid(self):
        """Quarantined UUID (all zeros) must be rejected."""
        from backend.tenant_context import (
            QUARANTINED_UUID,
            TenantValidationError,
            validate_org_id,
        )

        with pytest.raises(TenantValidationError) as exc_info:
            validate_org_id(QUARANTINED_UUID)

        assert "Quarantined org_id rejected" in str(exc_info.value)
        assert "00000000-0000-0000-0000-000000000000" in str(exc_info.value)

    def test_passes_valid_uuid(self):
        """A normal UUID string passes validation and is returned."""
        from backend.tenant_context import validate_org_id

        org_id = str(uuid.uuid4())
        result = validate_org_id(org_id)
        assert result == org_id

    def test_passes_multiple_valid_uuids(self):
        """Various valid UUIDs all pass."""
        from backend.tenant_context import validate_org_id

        valid_ids = [
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "12345678-1234-1234-1234-123456789012",
            str(uuid.uuid4()),
        ]
        for org_id in valid_ids:
            result = validate_org_id(org_id)
            assert result == org_id

    def test_system_org_uuid_passes(self):
        """The system org UUID (all-zeros with 001 at end) is NOT quarantined."""
        from backend.tenant_context import validate_org_id

        system_org = "00000000-0000-0000-0000-000000000001"
        result = validate_org_id(system_org)
        assert result == system_org

    def test_quarantined_uuid_constant_is_correct(self):
        """Verify the QUARANTINED_UUID constant value."""
        from backend.tenant_context import QUARANTINED_UUID

        assert QUARANTINED_UUID == "00000000-0000-0000-0000-000000000000"

    def test_exception_is_value_error_subclass(self):
        """TenantValidationError is a ValueError subclass for backward compat."""
        from backend.tenant_context import TenantValidationError

        assert issubclass(TenantValidationError, ValueError)


# =============================================================================
# Tests: backend/middleware/tenant_middleware.py
# =============================================================================


@pytest.mark.unit
class TestTenantMiddleware:
    """Tests for the tenant middleware FastAPI dependency."""

    @pytest.mark.asyncio
    async def test_returns_422_for_quarantined_uuid(self):
        """Middleware returns HTTP 422 when resolved org_id is quarantined."""
        from fastapi import HTTPException

        from backend.middleware.tenant_middleware import get_authenticated_org_id
        from backend.tenant_context import QUARANTINED_UUID

        # Mock request with tenant_context that has quarantined org_id
        mock_tenant_ctx = MagicMock()
        mock_tenant_ctx.org_id = uuid.UUID(QUARANTINED_UUID)

        mock_request = MagicMock()
        mock_request.state.tenant_context = mock_tenant_ctx

        with pytest.raises(HTTPException) as exc_info:
            await get_authenticated_org_id(mock_request)

        assert exc_info.value.status_code == 422
        assert "reserved placeholder" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_returns_401_for_missing_auth(self):
        """Middleware returns HTTP 401 when no authentication is present."""
        from fastapi import HTTPException

        from backend.middleware.tenant_middleware import get_authenticated_org_id

        # Mock request with no tenant_context and no authorization header
        mock_request = MagicMock()
        mock_request.state = MagicMock(spec=[])  # empty spec = no attributes
        mock_request.headers = MagicMock()
        mock_request.headers.get = MagicMock(return_value=None)

        # Mock settings to not be in dev mode
        with patch(
            "backend.app.core.config.get_settings"
        ) as mock_settings:
            settings_instance = MagicMock()
            settings_instance.auth_dev_mode = False
            settings_instance.environment = "production"
            mock_settings.return_value = settings_instance

            with pytest.raises(HTTPException) as exc_info:
                await get_authenticated_org_id(mock_request)

            assert exc_info.value.status_code == 401
            assert "Authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_returns_valid_org_id_from_tenant_context(self):
        """Middleware returns org_id when TenantContext is valid."""
        from backend.middleware.tenant_middleware import get_authenticated_org_id

        valid_org_id = uuid.uuid4()
        mock_tenant_ctx = MagicMock()
        mock_tenant_ctx.org_id = valid_org_id

        mock_request = MagicMock()
        mock_request.state.tenant_context = mock_tenant_ctx

        result = await get_authenticated_org_id(mock_request)
        assert result == str(valid_org_id)

    @pytest.mark.asyncio
    async def test_returns_401_for_invalid_bearer_format(self):
        """Middleware returns 401 for malformed Authorization header."""
        from fastapi import HTTPException

        from backend.middleware.tenant_middleware import get_authenticated_org_id

        mock_request = MagicMock()
        # No tenant_context on state
        mock_request.state = MagicMock(spec=[])  # empty spec = no attributes

        # Malformed authorization header (no "Bearer" prefix)
        mock_request.headers = MagicMock()
        mock_request.headers.get = MagicMock(
            side_effect=lambda key, default=None: (
                "Basic abc123" if key == "authorization" else default
            )
        )

        with patch(
            "backend.app.core.config.get_settings"
        ) as mock_settings:
            settings_instance = MagicMock()
            settings_instance.auth_dev_mode = False
            settings_instance.environment = "production"
            mock_settings.return_value = settings_instance

            with pytest.raises(HTTPException) as exc_info:
                await get_authenticated_org_id(mock_request)

            assert exc_info.value.status_code == 401


# =============================================================================
# Tests: Cross-tenant GET returns 404 (not 403)
# =============================================================================


@pytest.mark.unit
class TestCrossTenantReturns404:
    """Verify cross-tenant access returns 404 (not 403) per R2.7.

    This is tested at the repository layer (app/db/tenant_scope.py) since
    the database functions use .eq("org_id", org_id) which naturally returns
    empty results for cross-tenant access, which callers surface as 404.
    """

    @pytest.mark.asyncio
    async def test_get_tenant_resource_returns_404_not_403(self):
        """Cross-tenant resource access returns 404, never 403."""
        from fastapi import HTTPException

        # Use the same import path as tests/unit/test_core/test_tenant_scope.py
        sys.path.insert(
            0, os.path.join(os.path.dirname(__file__), "..", "..", "backend")
        )
        from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin
        from app.db.tenant_scope import get_tenant_resource

        class _CrossTenantModelA(Base, UUIDMixin, TimestampMixin, TenantMixin):
            __tablename__ = "test_cross_tenant_a"

        # Mock session returns None (resource not found for this org)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        org_a = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        resource_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_resource(
                db=mock_db,
                model=_CrossTenantModelA,
                resource_id=resource_id,
                org_id=org_a,
                resource_name="Talent",
            )

        # MUST be 404 (not 403) — prevents information leakage
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_tenant_resource_never_returns_403(self):
        """Even when resource exists in another org, response is 404 not 403."""
        from fastapi import HTTPException

        sys.path.insert(
            0, os.path.join(os.path.dirname(__file__), "..", "..", "backend")
        )
        from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin
        from app.db.tenant_scope import get_tenant_resource

        class _CrossTenantModelB(Base, UUIDMixin, TimestampMixin, TenantMixin):
            __tablename__ = "test_cross_tenant_b"

        # Return None — the query filtered by org_id didn't find it
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        org_b = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        resource_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_resource(
                db=mock_db,
                model=_CrossTenantModelB,
                resource_id=resource_id,
                org_id=org_b,
                resource_name="Asset",
            )

        # Verify it's not a 403
        assert exc_info.value.status_code != 403
        assert exc_info.value.status_code == 404


# =============================================================================
# Tests: database.py integration — validate_org_id enforcement
# =============================================================================


@pytest.mark.unit
class TestDatabaseValidateOrgId:
    """Verify database.py functions reject quarantined UUID via validate_org_id."""

    def test_get_projects_rejects_quarantined_uuid(self):
        """get_projects raises TenantValidationError for quarantined UUID."""
        from backend.tenant_context import QUARANTINED_UUID, TenantValidationError

        # Import get_projects — it calls validate_org_id at the top
        from backend.database import get_projects

        with pytest.raises(TenantValidationError) as exc_info:
            get_projects(QUARANTINED_UUID)

        assert "Quarantined" in str(exc_info.value)

    def test_get_talent_rejects_empty_string(self):
        """get_talent raises TenantValidationError for empty org_id."""
        from backend.tenant_context import TenantValidationError

        from backend.database import get_talent

        with pytest.raises(TenantValidationError):
            get_talent("")

    def test_get_talent_rejects_none(self):
        """get_talent raises TenantValidationError for None."""
        from backend.tenant_context import TenantValidationError

        from backend.database import get_talent

        with pytest.raises(TenantValidationError):
            get_talent(None)

    def test_create_talent_rejects_quarantined_uuid(self):
        """create_talent rejects quarantined UUID before inserting."""
        from backend.tenant_context import QUARANTINED_UUID, TenantValidationError

        from backend.database import create_talent

        with pytest.raises(TenantValidationError):
            create_talent({"name": "test"}, QUARANTINED_UUID)

    def test_get_assets_rejects_quarantined_uuid(self):
        """get_assets rejects quarantined UUID."""
        from backend.tenant_context import QUARANTINED_UUID, TenantValidationError

        from backend.database import get_assets

        with pytest.raises(TenantValidationError):
            get_assets(QUARANTINED_UUID)

    def test_get_jobs_rejects_quarantined_uuid(self):
        """get_jobs rejects quarantined UUID."""
        from backend.tenant_context import QUARANTINED_UUID, TenantValidationError

        from backend.database import get_jobs

        with pytest.raises(TenantValidationError):
            get_jobs(QUARANTINED_UUID)

    def test_delete_asset_rejects_quarantined_uuid(self):
        """delete_asset rejects quarantined UUID."""
        from backend.tenant_context import QUARANTINED_UUID, TenantValidationError

        from backend.database import delete_asset

        with pytest.raises(TenantValidationError):
            delete_asset("some-id", QUARANTINED_UUID)

    def test_get_workers_db_rejects_quarantined_uuid(self):
        """get_workers_db rejects quarantined UUID."""
        from backend.tenant_context import QUARANTINED_UUID, TenantValidationError

        from backend.database import get_workers_db

        with pytest.raises(TenantValidationError):
            get_workers_db(QUARANTINED_UUID)


# =============================================================================
# Tests: org_id never from client request parameters (R2.10)
# =============================================================================


@pytest.mark.unit
class TestOrgIdNeverFromClient:
    """Verify architectural constraint: org_id only from TenantContext.

    The middleware resolves org_id from JWT, and database.py functions
    receive it as a parameter (which must come from middleware, not request).
    """

    def test_middleware_does_not_read_org_id_from_query_params(self):
        """get_authenticated_org_id does not inspect query parameters."""
        import inspect

        from backend.middleware.tenant_middleware import get_authenticated_org_id

        sig = inspect.signature(get_authenticated_org_id)
        # The only parameter is `request: Request`
        params = list(sig.parameters.keys())
        assert params == ["request"]
        # No org_id parameter exists
        assert "org_id" not in params

    def test_validate_org_id_returns_the_input(self):
        """validate_org_id returns the validated org_id (passthrough)."""
        from backend.tenant_context import validate_org_id

        org_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        result = validate_org_id(org_id)
        assert result == org_id
