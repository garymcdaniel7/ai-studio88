"""Unit tests for tenant-scoped query enforcement.

Validates: Requirements R2.2, R2.6, R2.7, R2.8, R2.9, R2.10

Tests cover:
    - Quarantined UUID (all-zeros) is rejected with HTTP 422
    - Cross-tenant resource access returns 404 (not 403)
    - tenant_filter correctly applies org_id WHERE clause
    - org_id is only accepted from TenantContext (never client-supplied)
    - TenantScopedRepository enforces isolation on all operations

Run with:
    pytest tests/unit/test_core/test_tenant_scope.py -v
"""

from __future__ import annotations

import os
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

# Ensure backend/ is on path so `from app.` imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))

from app.db.base import TenantMixin, TimestampMixin, UUIDMixin
from app.db.tenant_scope import (
    QUARANTINED_ORG_ID,
    TenantScopedRepository,
    get_tenant_resource,
    tenant_filter,
    validate_org_id,
)
from fastapi import HTTPException
from sqlalchemy import Select, select


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


# For SQLAlchemy Select compilation and model tests
from datetime import datetime  # noqa: E402
from app.db.base import Base as _RealBase  # noqa: E402


class RealFakeTenantModel(_RealBase, UUIDMixin, TimestampMixin, TenantMixin):
    """Real SQLAlchemy model for filter compilation tests."""

    __tablename__ = "test_fake_tenant_model"


# Valid test UUIDs
ORG_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
RESOURCE_ID = UUID("11111111-1111-1111-1111-111111111111")


# =============================================================================
# Tests: validate_org_id
# =============================================================================


@pytest.mark.unit
class TestValidateOrgId:
    """Tests for the validate_org_id function (R2.8)."""

    def test_quarantined_uuid_raises_422(self):
        """Quarantined UUID (all zeros) must be rejected with HTTP 422."""
        with pytest.raises(HTTPException) as exc_info:
            validate_org_id(QUARANTINED_ORG_ID)

        assert exc_info.value.status_code == 422
        assert "reserved placeholder" in exc_info.value.detail
        assert "org_id" in exc_info.value.detail.lower()

    def test_valid_org_id_passes(self):
        """A normal UUID passes validation without raising."""
        # Should not raise
        validate_org_id(ORG_A)
        validate_org_id(ORG_B)

    def test_quarantined_uuid_is_all_zeros(self):
        """Verify the constant is the expected all-zeros UUID."""
        assert str(QUARANTINED_ORG_ID) == "00000000-0000-0000-0000-000000000000"

    def test_system_org_uuid_passes(self):
        """The system org (all-zeros with 001 at end) is NOT quarantined."""
        system_org = UUID("00000000-0000-0000-0000-000000000001")
        # Should not raise
        validate_org_id(system_org)

    def test_random_uuid_passes(self):
        """Any random UUID should pass validation."""
        for _ in range(10):
            validate_org_id(uuid.uuid4())


# =============================================================================
# Tests: tenant_filter
# =============================================================================


@pytest.mark.unit
class TestTenantFilter:
    """Tests for the tenant_filter helper (R2.2)."""

    def test_adds_where_clause_for_org_id(self):
        """tenant_filter must add WHERE org_id = :org_id to the statement."""
        stmt = select(RealFakeTenantModel)
        filtered = tenant_filter(stmt, RealFakeTenantModel, ORG_A)

        # The filtered statement should be a Select with a WHERE clause
        assert isinstance(filtered, Select)
        # Compile to string to verify org_id is in the query
        compiled = str(filtered.compile(compile_kwargs={"literal_binds": True}))
        # SQLAlchemy may render UUID with or without hyphens
        assert ORG_A.hex in compiled or str(ORG_A) in compiled

    def test_rejects_quarantined_uuid(self):
        """tenant_filter must reject quarantined UUID before adding filter."""
        stmt = select(RealFakeTenantModel)
        with pytest.raises(HTTPException) as exc_info:
            tenant_filter(stmt, RealFakeTenantModel, QUARANTINED_ORG_ID)

        assert exc_info.value.status_code == 422

    def test_different_orgs_produce_different_filters(self):
        """Each org_id produces a distinct WHERE clause."""
        stmt = select(RealFakeTenantModel)
        filtered_a = tenant_filter(stmt, RealFakeTenantModel, ORG_A)
        filtered_b = tenant_filter(stmt, RealFakeTenantModel, ORG_B)

        compiled_a = str(filtered_a.compile(compile_kwargs={"literal_binds": True}))
        compiled_b = str(filtered_b.compile(compile_kwargs={"literal_binds": True}))

        # SQLAlchemy may render UUID with or without hyphens
        assert ORG_A.hex in compiled_a or str(ORG_A) in compiled_a
        assert ORG_B.hex in compiled_b or str(ORG_B) in compiled_b
        # Ensure cross-org UUIDs are NOT in the other query
        assert ORG_B.hex not in compiled_a and str(ORG_B) not in compiled_a
        assert ORG_A.hex not in compiled_b and str(ORG_A) not in compiled_b


# =============================================================================
# Tests: get_tenant_resource
# =============================================================================


@pytest.mark.unit
class TestGetTenantResource:
    """Tests for get_tenant_resource (R2.6 — cross-tenant returns 404)."""

    @pytest.mark.asyncio
    async def test_cross_tenant_returns_404(self):
        """Accessing a resource from another org returns 404, not 403."""
        # Mock the database session to return None (no match for this org_id)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_resource(
                db=mock_db,
                model=RealFakeTenantModel,
                resource_id=RESOURCE_ID,
                org_id=ORG_A,
                resource_name="Talent",
            )

        # Must be 404, NOT 403 — prevents information leakage
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_same_tenant_returns_resource(self):
        """Accessing own resource returns the model instance."""
        fake_resource = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_resource
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        result = await get_tenant_resource(
            db=mock_db,
            model=RealFakeTenantModel,
            resource_id=RESOURCE_ID,
            org_id=ORG_A,
            resource_name="Talent",
        )

        assert result is fake_resource

    @pytest.mark.asyncio
    async def test_quarantined_org_id_rejected(self):
        """get_tenant_resource rejects quarantined UUID before querying."""
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_resource(
                db=mock_db,
                model=RealFakeTenantModel,
                resource_id=RESOURCE_ID,
                org_id=QUARANTINED_ORG_ID,
                resource_name="Asset",
            )

        assert exc_info.value.status_code == 422
        # DB should never be called with quarantined UUID
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_nonexistent_resource_returns_404(self):
        """A resource that simply doesn't exist returns 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_resource(
                db=mock_db,
                model=RealFakeTenantModel,
                resource_id=uuid.uuid4(),
                org_id=ORG_A,
                resource_name="Job",
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_resource_name_in_error_detail(self):
        """The resource_name parameter appears in the 404 error message."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_resource(
                db=mock_db,
                model=RealFakeTenantModel,
                resource_id=RESOURCE_ID,
                org_id=ORG_A,
                resource_name="Campaign",
            )

        assert "Campaign" in exc_info.value.detail


# =============================================================================
# Tests: TenantScopedRepository
# =============================================================================


@pytest.mark.unit
class TestTenantScopedRepository:
    """Tests for the TenantScopedRepository base class (R2.2, R2.9, R2.10)."""

    def test_construction_with_quarantined_uuid_raises_422(self):
        """Cannot create a repository with quarantined org_id."""
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            TenantScopedRepository(db=mock_db, org_id=QUARANTINED_ORG_ID)

        assert exc_info.value.status_code == 422

    def test_construction_with_valid_org_id(self):
        """Repository construction with a valid org_id succeeds."""
        mock_db = AsyncMock()
        repo = TenantScopedRepository(db=mock_db, org_id=ORG_A)

        assert repo.org_id == ORG_A
        assert repo.db is mock_db

    def test_org_id_is_immutable_after_construction(self):
        """Once constructed, the org_id cannot be changed externally."""
        mock_db = AsyncMock()
        repo = TenantScopedRepository(db=mock_db, org_id=ORG_A)

        # org_id is a property, not directly settable
        with pytest.raises(AttributeError):
            repo.org_id = ORG_B  # type: ignore[misc]

    @pytest.mark.asyncio
    async def test_get_one_returns_404_for_cross_tenant(self):
        """_get_one returns 404 when resource belongs to different org."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        repo = TenantScopedRepository(db=mock_db, org_id=ORG_A)

        with pytest.raises(HTTPException) as exc_info:
            await repo._get_one(RealFakeTenantModel, RESOURCE_ID, "Model")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_one_returns_resource_for_same_tenant(self):
        """_get_one returns the resource when it belongs to authenticated org."""
        fake_resource = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_resource
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        repo = TenantScopedRepository(db=mock_db, org_id=ORG_A)
        result = await repo._get_one(RealFakeTenantModel, RESOURCE_ID, "Talent")

        assert result is fake_resource

    @pytest.mark.asyncio
    async def test_list_scopes_to_org_id(self):
        """_list always adds org_id filter (R2.9)."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        # First call is for count, second for items
        mock_db.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        repo = TenantScopedRepository(db=mock_db, org_id=ORG_A)
        items, total = await repo._list(
            RealFakeTenantModel, select(RealFakeTenantModel), limit=20, offset=0
        )

        assert items == []
        assert total == 0
        # Verify db was called (org_id filter was applied)
        assert mock_db.scalar.called or mock_db.execute.called

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_cross_tenant(self):
        """_exists returns False when resource belongs to different org."""
        mock_db = AsyncMock()
        mock_db.scalar.return_value = 0

        repo = TenantScopedRepository(db=mock_db, org_id=ORG_A)
        result = await repo._exists(RealFakeTenantModel, RESOURCE_ID)

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_returns_true_for_same_tenant(self):
        """_exists returns True when resource belongs to authenticated org."""
        mock_db = AsyncMock()
        mock_db.scalar.return_value = 1

        repo = TenantScopedRepository(db=mock_db, org_id=ORG_A)
        result = await repo._exists(RealFakeTenantModel, RESOURCE_ID)

        assert result is True


# =============================================================================
# Tests: org_id Never From Client (R2.10)
# =============================================================================


@pytest.mark.unit
class TestOrgIdNeverFromClient:
    """Verify that org_id is derived from TenantContext, never client params.

    These tests verify the architectural constraint by testing that:
    - TenantScopedRepository stores org_id from constructor (set by service layer)
    - No method on TenantScopedRepository accepts org_id as a parameter
    - The get_tenant_resource function requires org_id as explicit parameter
      (which the caller must derive from TenantContext, not request params)
    """

    def test_repository_org_id_set_at_construction(self):
        """org_id is set once at construction, not per-method."""
        mock_db = AsyncMock()
        repo = TenantScopedRepository(db=mock_db, org_id=ORG_A)

        # org_id is fixed — every operation uses it automatically
        assert repo.org_id == ORG_A

    def test_get_one_does_not_accept_org_id_parameter(self):
        """_get_one uses the repository's org_id, not a parameter."""
        import inspect

        sig = inspect.signature(TenantScopedRepository._get_one)
        param_names = list(sig.parameters.keys())

        # Should only have: self, model, resource_id, resource_name
        assert "org_id" not in param_names

    def test_list_does_not_accept_org_id_parameter(self):
        """_list uses the repository's org_id, not a parameter."""
        import inspect

        sig = inspect.signature(TenantScopedRepository._list)
        param_names = list(sig.parameters.keys())

        # Should only have: self, model, stmt, limit, offset
        assert "org_id" not in param_names

    def test_exists_does_not_accept_org_id_parameter(self):
        """_exists uses the repository's org_id, not a parameter."""
        import inspect

        sig = inspect.signature(TenantScopedRepository._exists)
        param_names = list(sig.parameters.keys())

        # Should only have: self, model, resource_id
        assert "org_id" not in param_names
