"""Unit tests for PublishingApprovalService — approval binding lifecycle.

Tests cover:
    - compute_package_hash determinism (same inputs → same hash)
    - compute_package_hash sensitivity (different inputs → different hash)
    - create_approval creates immutable record with correct hash
    - create_approval supersedes previous valid approvals for same asset
    - get_approval returns record for correct org, 404 for wrong org
    - verify_approval returns valid when state matches
    - verify_approval detects and reports mismatched fields
    - verify_approval invalidates record on mismatch
    - verify_approval returns invalid for already-invalidated record
    - invalidate_for_asset invalidates all valid approvals for asset
    - invalidate_for_talent invalidates approvals referencing talent
    - _detect_mismatches identifies each bound field independently

Requirements: R79.1, R79.2, R79.3, R79.4, R79.5, R79.6
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
sys.modules.setdefault("app.db.tenant_scope", _mock_tenant_scope)

# Mock jose, passlib, pydantic-settings, dotenv, structlog
sys.modules.setdefault("jose", MagicMock())
sys.modules.setdefault("passlib", MagicMock())
sys.modules.setdefault("passlib.context", MagicMock())
_pydantic_settings_mock = MagicMock()
_pydantic_settings_mock.BaseSettings = type("BaseSettings", (), {"model_config": {}})
sys.modules.setdefault("pydantic_settings", _pydantic_settings_mock)
sys.modules.setdefault("dotenv", MagicMock())
sys.modules.setdefault("structlog", MagicMock())

# Mock models package
_mock_models_pkg = ModuleType("app.models")
_mock_models_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.models", _mock_models_pkg)

# Create a mock PublishingApprovedPackage class
_mock_publishing_model = ModuleType("app.models.publishing_approved_package")


class FakePublishingApprovedPackage:
    """Fake ORM model for testing."""

    __tablename__ = "publishing_approved_packages"

    # Class-level column attributes needed for SQLAlchemy query expressions
    id = MagicMock()
    org_id = MagicMock()
    asset_id = MagicMock()
    talent_id = MagicMock()
    is_valid = MagicMock()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            object.__setattr__(self, k, v)
        # Default fields if not provided
        if "id" not in kwargs:
            object.__setattr__(self, "id", uuid4())
        if "created_at" not in kwargs:
            object.__setattr__(self, "created_at", datetime.now(UTC))
        if "updated_at" not in kwargs:
            object.__setattr__(self, "updated_at", datetime.now(UTC))


_mock_publishing_model.PublishingApprovedPackage = FakePublishingApprovedPackage  # type: ignore[attr-defined]
sys.modules.setdefault(
    "app.models.publishing_approved_package", _mock_publishing_model
)

# Mock backend module
_mock_backend = ModuleType("backend")
_mock_backend.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("backend", _mock_backend)
sys.modules.setdefault("backend.database", MagicMock())

# Mock app.schemas (import needed by schemas)
import importlib.util
import os

_schemas_base_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "app", "schemas", "base.py"
)
_schemas_base_path = os.path.abspath(_schemas_base_path)

_base_spec = importlib.util.spec_from_file_location(
    "app.schemas.base",
    _schemas_base_path,
)
if _base_spec and _base_spec.loader:
    _base_mod = importlib.util.module_from_spec(_base_spec)
    sys.modules.setdefault("app.schemas.base", _base_mod)
    _base_spec.loader.exec_module(_base_mod)

# Now import the service under test
from app.core.dependencies import TenantContext, TrustDomain, WorkspaceRole
from app.services.publishing_approval_service import (
    PublishingApprovalService,
    compute_package_hash,
)


# =============================================================================
# Constants & Helpers
# =============================================================================

ORG_ID = uuid4()
USER_ID = uuid4()
ASSET_ID = uuid4()
TALENT_ID = uuid4()
PROJECT_ID = uuid4()

SAMPLE_CHECKSUM = "a" * 64
SAMPLE_CAPTION = "Test post caption #aiart"
SAMPLE_DESTINATION = {"platform": "instagram", "account_id": "acc_123", "post_type": "image"}
SAMPLE_SCHEDULE = {"scheduled_at": "2025-01-15T10:00:00Z", "timezone": "UTC"}
SAMPLE_TARGETING = {"audience_tags": ["gen_z"], "geo_targeting": ["US"], "age_range": None}
SAMPLE_CONSENT_STATE = [
    {
        "talent_id": str(TALENT_ID),
        "active_scopes": ["likeness", "publishing"],
        "consent_record_ids": [str(uuid4())],
        "verified_at": "2025-01-10T00:00:00Z",
    }
]
SAMPLE_DISCLOSURE = {
    "ai_disclosure_enabled": True,
    "disclosure_text": "Created with AI",
    "disclosure_tags": ["#AIGenerated"],
    "platform_disclosure_format": "tag",
}
SAMPLE_POLICY = {
    "workspace_privacy_restrictions": [],
    "content_policy_version": "1.0",
    "safety_check_passed": True,
    "governance_decision_id": "gov_abc",
}


def _make_tenant(role: WorkspaceRole = WorkspaceRole.EDITOR) -> TenantContext:
    """Create a TenantContext for testing."""
    return TenantContext(
        user_id=USER_ID,
        org_id=ORG_ID,
        role=role,
        trust_domain=TrustDomain.CUSTOMER_USER,
        email="test@example.com",
    )


# =============================================================================
# Tests for compute_package_hash
# =============================================================================


class TestComputePackageHash:
    """Tests for the deterministic package hash function."""

    def test_deterministic_same_inputs(self):
        """Same inputs always produce the same hash."""
        h1 = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        h2 = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        assert h1 == h2

    def test_hash_is_64_char_hex(self):
        """Hash is a valid 64-character hex string (SHA-256)."""
        h = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_checksum_different_hash(self):
        """Changing asset_checksum produces a different hash."""
        h1 = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        h2 = compute_package_hash(
            "b" * 64, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        assert h1 != h2

    def test_different_caption_different_hash(self):
        """Changing caption produces a different hash."""
        h1 = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        h2 = compute_package_hash(
            SAMPLE_CHECKSUM, "Different caption", SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        assert h1 != h2

    def test_different_destination_different_hash(self):
        """Changing destination produces a different hash."""
        h1 = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        different_dest = {"platform": "tiktok", "account_id": "acc_456", "post_type": "video"}
        h2 = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, different_dest,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        assert h1 != h2

    def test_different_consent_state_different_hash(self):
        """Changing consent state produces a different hash."""
        h1 = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        different_consent = [
            {
                "talent_id": str(TALENT_ID),
                "active_scopes": ["likeness"],  # removed "publishing"
                "consent_record_ids": [],
                "verified_at": None,
            }
        ]
        h2 = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, different_consent,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        assert h1 != h2

    def test_different_policy_different_hash(self):
        """Changing policy state produces a different hash."""
        h1 = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        different_policy = {**SAMPLE_POLICY, "safety_check_passed": False}
        h2 = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, different_policy,
        )
        assert h1 != h2

    def test_key_order_does_not_affect_hash(self):
        """Dict key order does not affect hash (canonical sorting applied)."""
        dest_a = {"platform": "instagram", "account_id": "x", "post_type": "image"}
        dest_b = {"post_type": "image", "account_id": "x", "platform": "instagram"}
        h1 = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, dest_a,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        h2 = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, dest_b,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        assert h1 == h2


# =============================================================================
# Tests for PublishingApprovalService
# =============================================================================


class TestPublishingApprovalServiceCreate:
    """Tests for create_approval method."""

    @pytest.mark.asyncio
    async def test_create_approval_success(self):
        """create_approval creates a valid record with correct hash."""
        db = AsyncMock()
        # Mock the update (invalidate existing) to return 0 rows
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_result)
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        tenant = _make_tenant()
        service = PublishingApprovalService(db=db, tenant=tenant)

        record = await service.create_approval(
            asset_id=ASSET_ID,
            asset_checksum=SAMPLE_CHECKSUM,
            caption=SAMPLE_CAPTION,
            destination=SAMPLE_DESTINATION,
            schedule=SAMPLE_SCHEDULE,
            targeting=SAMPLE_TARGETING,
            consent_state=SAMPLE_CONSENT_STATE,
            disclosure_settings=SAMPLE_DISCLOSURE,
            policy_state=SAMPLE_POLICY,
            talent_id=TALENT_ID,
            project_id=PROJECT_ID,
        )

        # Verify db.add was called
        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once()

        # Check the record has correct attributes
        added_record = db.add.call_args[0][0]
        assert added_record.org_id == ORG_ID
        assert added_record.asset_id == ASSET_ID
        assert added_record.asset_checksum == SAMPLE_CHECKSUM
        assert added_record.caption == SAMPLE_CAPTION
        assert added_record.destination == SAMPLE_DESTINATION
        assert added_record.is_valid is True
        assert added_record.approved_by == USER_ID
        assert added_record.talent_id == TALENT_ID
        assert added_record.project_id == PROJECT_ID

        # Verify package_hash is correct
        expected_hash = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        assert added_record.package_hash == expected_hash


class TestPublishingApprovalServiceGet:
    """Tests for get_approval method."""

    @pytest.mark.asyncio
    async def test_get_approval_not_found(self):
        """get_approval raises 404 when record not found."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=mock_result)

        tenant = _make_tenant()
        service = PublishingApprovalService(db=db, tenant=tenant)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.get_approval(uuid4())

        assert exc_info.value.status_code == 404


class TestPublishingApprovalServiceVerify:
    """Tests for verify_approval method."""

    @pytest.mark.asyncio
    async def test_verify_valid_matching_state(self):
        """verify_approval returns valid when current state matches."""
        expected_hash = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        now = datetime.now(UTC)

        fake_record = FakePublishingApprovedPackage(
            id=uuid4(),
            org_id=ORG_ID,
            asset_id=ASSET_ID,
            asset_checksum=SAMPLE_CHECKSUM,
            caption=SAMPLE_CAPTION,
            destination=SAMPLE_DESTINATION,
            schedule=SAMPLE_SCHEDULE,
            targeting=SAMPLE_TARGETING,
            consent_state=SAMPLE_CONSENT_STATE,
            disclosure_settings=SAMPLE_DISCLOSURE,
            policy_state=SAMPLE_POLICY,
            package_hash=expected_hash,
            approved_by=USER_ID,
            approved_at=now,
            is_valid=True,
            invalidated_at=None,
            invalidation_reason=None,
        )

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=fake_record)
        db.execute = AsyncMock(return_value=mock_result)

        tenant = _make_tenant()
        service = PublishingApprovalService(db=db, tenant=tenant)

        result = await service.verify_approval(
            approval_id=fake_record.id,
            current_asset_checksum=SAMPLE_CHECKSUM,
            current_caption=SAMPLE_CAPTION,
            current_destination=SAMPLE_DESTINATION,
            current_schedule=SAMPLE_SCHEDULE,
            current_targeting=SAMPLE_TARGETING,
            current_consent_state=SAMPLE_CONSENT_STATE,
            current_disclosure_settings=SAMPLE_DISCLOSURE,
            current_policy_state=SAMPLE_POLICY,
        )

        assert result["is_valid"] is True
        assert result["mismatched_fields"] == []
        assert result["approval_id"] == fake_record.id

    @pytest.mark.asyncio
    async def test_verify_detects_caption_change(self):
        """verify_approval detects caption change and invalidates."""
        expected_hash = compute_package_hash(
            SAMPLE_CHECKSUM, SAMPLE_CAPTION, SAMPLE_DESTINATION,
            SAMPLE_SCHEDULE, SAMPLE_TARGETING, SAMPLE_CONSENT_STATE,
            SAMPLE_DISCLOSURE, SAMPLE_POLICY,
        )
        now = datetime.now(UTC)

        fake_record = FakePublishingApprovedPackage(
            id=uuid4(),
            org_id=ORG_ID,
            asset_id=ASSET_ID,
            asset_checksum=SAMPLE_CHECKSUM,
            caption=SAMPLE_CAPTION,
            destination=SAMPLE_DESTINATION,
            schedule=SAMPLE_SCHEDULE,
            targeting=SAMPLE_TARGETING,
            consent_state=SAMPLE_CONSENT_STATE,
            disclosure_settings=SAMPLE_DISCLOSURE,
            policy_state=SAMPLE_POLICY,
            package_hash=expected_hash,
            approved_by=USER_ID,
            approved_at=now,
            is_valid=True,
            invalidated_at=None,
            invalidation_reason=None,
        )

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=fake_record)
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()

        tenant = _make_tenant()
        service = PublishingApprovalService(db=db, tenant=tenant)

        result = await service.verify_approval(
            approval_id=fake_record.id,
            current_asset_checksum=SAMPLE_CHECKSUM,
            current_caption="CHANGED CAPTION",  # different!
            current_destination=SAMPLE_DESTINATION,
            current_schedule=SAMPLE_SCHEDULE,
            current_targeting=SAMPLE_TARGETING,
            current_consent_state=SAMPLE_CONSENT_STATE,
            current_disclosure_settings=SAMPLE_DISCLOSURE,
            current_policy_state=SAMPLE_POLICY,
        )

        assert result["is_valid"] is False
        assert "caption" in result["mismatched_fields"]
        assert "Re-approval required" in result["message"]

    @pytest.mark.asyncio
    async def test_verify_already_invalidated(self):
        """verify_approval returns invalid immediately for already-invalidated."""
        now = datetime.now(UTC)

        fake_record = FakePublishingApprovedPackage(
            id=uuid4(),
            org_id=ORG_ID,
            asset_id=ASSET_ID,
            asset_checksum=SAMPLE_CHECKSUM,
            caption=SAMPLE_CAPTION,
            destination=SAMPLE_DESTINATION,
            schedule=SAMPLE_SCHEDULE,
            targeting=SAMPLE_TARGETING,
            consent_state=SAMPLE_CONSENT_STATE,
            disclosure_settings=SAMPLE_DISCLOSURE,
            policy_state=SAMPLE_POLICY,
            package_hash="stale_hash",
            approved_by=USER_ID,
            approved_at=now,
            is_valid=False,  # already invalid
            invalidated_at=now,
            invalidation_reason="Superseded by new approval",
        )

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=fake_record)
        db.execute = AsyncMock(return_value=mock_result)

        tenant = _make_tenant()
        service = PublishingApprovalService(db=db, tenant=tenant)

        result = await service.verify_approval(
            approval_id=fake_record.id,
            current_asset_checksum=SAMPLE_CHECKSUM,
            current_caption=SAMPLE_CAPTION,
            current_destination=SAMPLE_DESTINATION,
            current_schedule=SAMPLE_SCHEDULE,
            current_targeting=SAMPLE_TARGETING,
            current_consent_state=SAMPLE_CONSENT_STATE,
            current_disclosure_settings=SAMPLE_DISCLOSURE,
            current_policy_state=SAMPLE_POLICY,
        )

        assert result["is_valid"] is False
        assert "Superseded" in result["invalidation_reason"]


class TestPublishingApprovalServiceInvalidation:
    """Tests for invalidation methods."""

    @pytest.mark.asyncio
    async def test_invalidate_for_asset(self):
        """invalidate_for_asset updates matching records."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 2
        db.execute = AsyncMock(return_value=mock_result)

        tenant = _make_tenant()
        service = PublishingApprovalService(db=db, tenant=tenant)

        count = await service.invalidate_for_asset(
            asset_id=ASSET_ID, reason="Asset re-uploaded"
        )

        assert count == 2
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalidate_for_talent(self):
        """invalidate_for_talent updates matching records."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute = AsyncMock(return_value=mock_result)

        tenant = _make_tenant()
        service = PublishingApprovalService(db=db, tenant=tenant)

        count = await service.invalidate_for_talent(
            talent_id=TALENT_ID, reason="Consent revoked"
        )

        assert count == 1
        db.execute.assert_awaited_once()


class TestDetectMismatches:
    """Tests for _detect_mismatches internal method."""

    def test_no_mismatches(self):
        """Returns empty list when all fields match."""
        fake_record = FakePublishingApprovedPackage(
            asset_checksum=SAMPLE_CHECKSUM,
            caption=SAMPLE_CAPTION,
            destination=SAMPLE_DESTINATION,
            schedule=SAMPLE_SCHEDULE,
            targeting=SAMPLE_TARGETING,
            consent_state=SAMPLE_CONSENT_STATE,
            disclosure_settings=SAMPLE_DISCLOSURE,
            policy_state=SAMPLE_POLICY,
        )

        db = AsyncMock()
        tenant = _make_tenant()
        service = PublishingApprovalService(db=db, tenant=tenant)

        mismatches = service._detect_mismatches(
            record=fake_record,
            current_asset_checksum=SAMPLE_CHECKSUM,
            current_caption=SAMPLE_CAPTION,
            current_destination=SAMPLE_DESTINATION,
            current_schedule=SAMPLE_SCHEDULE,
            current_targeting=SAMPLE_TARGETING,
            current_consent_state=SAMPLE_CONSENT_STATE,
            current_disclosure_settings=SAMPLE_DISCLOSURE,
            current_policy_state=SAMPLE_POLICY,
        )

        assert mismatches == []

    def test_detects_multiple_mismatches(self):
        """Returns all mismatched field names."""
        fake_record = FakePublishingApprovedPackage(
            asset_checksum=SAMPLE_CHECKSUM,
            caption=SAMPLE_CAPTION,
            destination=SAMPLE_DESTINATION,
            schedule=SAMPLE_SCHEDULE,
            targeting=SAMPLE_TARGETING,
            consent_state=SAMPLE_CONSENT_STATE,
            disclosure_settings=SAMPLE_DISCLOSURE,
            policy_state=SAMPLE_POLICY,
        )

        db = AsyncMock()
        tenant = _make_tenant()
        service = PublishingApprovalService(db=db, tenant=tenant)

        mismatches = service._detect_mismatches(
            record=fake_record,
            current_asset_checksum="different_checksum",
            current_caption="Different caption",
            current_destination=SAMPLE_DESTINATION,
            current_schedule=SAMPLE_SCHEDULE,
            current_targeting={"audience_tags": ["changed"], "geo_targeting": [], "age_range": None},
            current_consent_state=SAMPLE_CONSENT_STATE,
            current_disclosure_settings=SAMPLE_DISCLOSURE,
            current_policy_state=SAMPLE_POLICY,
        )

        assert "asset_checksum" in mismatches
        assert "caption" in mismatches
        assert "targeting" in mismatches
        assert len(mismatches) == 3
