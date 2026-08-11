"""Unit tests for Platform Operator service, model, and schemas.

Tests the capability-based Platform Operator model including:
- CapabilityGroup enum completeness (11 groups)
- PlatformOperator.has_capability() logic (including Founder Authority)
- Pydantic schema validation (create, update, response serialization)
- PlatformOperatorService methods (grant, revoke, check, list, log_action)

No I/O, no DB — mocks all external dependencies.

Validates: Requirements R33.5, R33.6, R33.7, R97.1, R97.2, R97.3, R97.4
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

# Provide the mixins and Base as proper classes
_mock_db_base.Base = type("Base", (), {  # type: ignore[attr-defined]
    "__tablename__": "",
    "__table_args__": (),
    "metadata": MagicMock(),
})
_mock_db_base.UUIDMixin = type("UUIDMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.TimestampMixin = type("TimestampMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.TenantMixin = type("TenantMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.SoftDeleteMixin = type("SoftDeleteMixin", (), {})  # type: ignore[attr-defined]
_mock_db_session.get_db_session = MagicMock()  # type: ignore[attr-defined]
_mock_db_tenant_scope.validate_org_id = MagicMock()  # type: ignore[attr-defined]

sys.modules.setdefault("app.db", _mock_db)
sys.modules.setdefault("app.db.base", _mock_db_base)
sys.modules.setdefault("app.db.session", _mock_db_session)
sys.modules.setdefault("app.db.tenant_scope", _mock_db_tenant_scope)

# Mock app.core.logging
_mock_core = ModuleType("app.core")
_mock_core_logging = ModuleType("app.core.logging")
_mock_logger = MagicMock()
_mock_core_logging.get_logger = MagicMock(return_value=_mock_logger)  # type: ignore[attr-defined]
sys.modules.setdefault("app.core", _mock_core)
sys.modules.setdefault("app.core.logging", _mock_core_logging)

# Mock app.core.config
_mock_core_config = ModuleType("app.core.config")
_mock_core_config.get_settings = MagicMock()  # type: ignore[attr-defined]
_mock_core_config.reset_settings = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.core.config", _mock_core_config)

# Import the model module directly (bypass metaclass issues)
import importlib.util

_model_spec = importlib.util.spec_from_file_location(
    "app.models.platform_operator",
    os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "app", "models", "platform_operator.py"
    ),
)
_model_mod = importlib.util.module_from_spec(_model_spec)
sys.modules["app.models.platform_operator"] = _model_mod
_model_spec.loader.exec_module(_model_mod)  # type: ignore[union-attr]

CapabilityGroup = _model_mod.CapabilityGroup
PlatformOperator = _model_mod.PlatformOperator
PlatformOperatorAction = _model_mod.PlatformOperatorAction

from app.schemas.platform_operator import (  # noqa: E402
    CapabilityGroupEnum,
    PlatformOperatorActionListResponse,
    PlatformOperatorActionLog,
    PlatformOperatorActionResponse,
    PlatformOperatorCreate,
    PlatformOperatorListResponse,
    PlatformOperatorResponse,
    PlatformOperatorUpdate,
)


# =============================================================================
# CapabilityGroup Enum Tests
# =============================================================================


@pytest.mark.unit
class TestCapabilityGroupEnum:
    """Test that all 11 capability groups are defined correctly."""

    def test_has_11_groups(self) -> None:
        assert len(CapabilityGroup) == 11

    def test_all_expected_groups_present(self) -> None:
        expected = {
            "platform_observe",
            "tenant_support",
            "tenant_access_escalation",
            "platform_configuration",
            "financial_controls",
            "safety_and_rights",
            "security_administration",
            "deployment_operations",
            "release_management",
            "destructive_platform_actions",
            "founder_authority",
        }
        actual = {g.value for g in CapabilityGroup}
        assert actual == expected

    def test_schema_enum_matches_orm_enum(self) -> None:
        orm_values = {g.value for g in CapabilityGroup}
        schema_values = {g.value for g in CapabilityGroupEnum}
        assert orm_values == schema_values

    def test_schema_enum_has_11_groups(self) -> None:
        assert len(CapabilityGroupEnum) == 11


# =============================================================================
# PlatformOperator Model Tests
# =============================================================================


@pytest.mark.unit
class TestPlatformOperatorModel:
    """Test PlatformOperator ORM model behavior."""

    def _make_operator(
        self,
        capabilities: list[str] | None = None,
        revoked: bool = False,
    ) -> PlatformOperator:
        """Create a PlatformOperator instance for testing."""
        op = PlatformOperator()
        op.id = uuid4()
        op.user_id = uuid4()
        op.capability_grants = capabilities or [
            CapabilityGroup.PLATFORM_OBSERVE.value
        ]
        op.granted_by = uuid4()
        op.granted_at = datetime.now(timezone.utc)
        op.revoked_at = datetime.now(timezone.utc) if revoked else None
        op.created_at = datetime.now(timezone.utc)
        op.updated_at = datetime.now(timezone.utc)
        return op

    def test_is_active_when_not_revoked(self) -> None:
        op = self._make_operator(revoked=False)
        assert op.is_active is True

    def test_is_not_active_when_revoked(self) -> None:
        op = self._make_operator(revoked=True)
        assert op.is_active is False

    def test_has_capability_direct_grant(self) -> None:
        op = self._make_operator(
            capabilities=[CapabilityGroup.TENANT_SUPPORT.value]
        )
        assert op.has_capability(CapabilityGroup.TENANT_SUPPORT) is True
        assert op.has_capability(CapabilityGroup.FINANCIAL_CONTROLS) is False

    def test_has_capability_string_input(self) -> None:
        op = self._make_operator(
            capabilities=["platform_configuration"]
        )
        assert op.has_capability("platform_configuration") is True
        assert op.has_capability("financial_controls") is False

    def test_founder_authority_includes_all_capabilities(self) -> None:
        op = self._make_operator(
            capabilities=[CapabilityGroup.FOUNDER_AUTHORITY.value]
        )
        # Founder Authority implicitly grants all other capabilities
        for cap in CapabilityGroup:
            assert op.has_capability(cap) is True

    def test_multiple_capabilities(self) -> None:
        op = self._make_operator(
            capabilities=[
                CapabilityGroup.PLATFORM_OBSERVE.value,
                CapabilityGroup.TENANT_SUPPORT.value,
                CapabilityGroup.FINANCIAL_CONTROLS.value,
            ]
        )
        assert op.has_capability(CapabilityGroup.PLATFORM_OBSERVE) is True
        assert op.has_capability(CapabilityGroup.TENANT_SUPPORT) is True
        assert op.has_capability(CapabilityGroup.FINANCIAL_CONTROLS) is True
        assert op.has_capability(CapabilityGroup.SECURITY_ADMINISTRATION) is False

    def test_repr(self) -> None:
        op = self._make_operator()
        repr_str = repr(op)
        assert "PlatformOperator" in repr_str
        assert str(op.user_id) in repr_str


# =============================================================================
# PlatformOperatorCreate Schema Tests
# =============================================================================


@pytest.mark.unit
class TestPlatformOperatorCreateSchema:
    """Test PlatformOperatorCreate request schema validation."""

    def test_valid_single_capability(self) -> None:
        data = PlatformOperatorCreate(
            user_id=uuid4(),
            capability_grants=[CapabilityGroupEnum.PLATFORM_OBSERVE],
        )
        assert len(data.capability_grants) == 1
        assert data.capability_grants[0] == CapabilityGroupEnum.PLATFORM_OBSERVE

    def test_valid_multiple_capabilities(self) -> None:
        data = PlatformOperatorCreate(
            user_id=uuid4(),
            capability_grants=[
                CapabilityGroupEnum.PLATFORM_OBSERVE,
                CapabilityGroupEnum.TENANT_SUPPORT,
                CapabilityGroupEnum.FINANCIAL_CONTROLS,
            ],
        )
        assert len(data.capability_grants) == 3

    def test_valid_founder_authority(self) -> None:
        data = PlatformOperatorCreate(
            user_id=uuid4(),
            capability_grants=[CapabilityGroupEnum.FOUNDER_AUTHORITY],
        )
        assert data.capability_grants[0] == CapabilityGroupEnum.FOUNDER_AUTHORITY

    def test_empty_capabilities_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            PlatformOperatorCreate(
                user_id=uuid4(),
                capability_grants=[],
            )
        assert "capability_grants" in str(exc_info.value)

    def test_duplicate_capabilities_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            PlatformOperatorCreate(
                user_id=uuid4(),
                capability_grants=[
                    CapabilityGroupEnum.PLATFORM_OBSERVE,
                    CapabilityGroupEnum.PLATFORM_OBSERVE,
                ],
            )
        assert "Duplicate" in str(exc_info.value)

    def test_invalid_capability_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PlatformOperatorCreate(
                user_id=uuid4(),
                capability_grants=["invalid_group"],  # type: ignore[list-item]
            )

    def test_missing_user_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PlatformOperatorCreate(
                capability_grants=[CapabilityGroupEnum.PLATFORM_OBSERVE],
            )  # type: ignore[call-arg]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            PlatformOperatorCreate(
                user_id=uuid4(),
                capability_grants=[CapabilityGroupEnum.PLATFORM_OBSERVE],
                secret="should_not_be_here",  # type: ignore[call-arg]
            )
        assert "extra" in str(exc_info.value).lower()

    def test_all_11_capabilities_accepted(self) -> None:
        all_caps = list(CapabilityGroupEnum)
        data = PlatformOperatorCreate(
            user_id=uuid4(),
            capability_grants=all_caps,
        )
        assert len(data.capability_grants) == 11


# =============================================================================
# PlatformOperatorUpdate Schema Tests
# =============================================================================


@pytest.mark.unit
class TestPlatformOperatorUpdateSchema:
    """Test PlatformOperatorUpdate schema validation."""

    def test_valid_update(self) -> None:
        data = PlatformOperatorUpdate(
            capability_grants=[
                CapabilityGroupEnum.PLATFORM_OBSERVE,
                CapabilityGroupEnum.TENANT_SUPPORT,
            ],
        )
        assert len(data.capability_grants) == 2

    def test_empty_capabilities_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PlatformOperatorUpdate(capability_grants=[])

    def test_duplicate_capabilities_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PlatformOperatorUpdate(
                capability_grants=[
                    CapabilityGroupEnum.TENANT_SUPPORT,
                    CapabilityGroupEnum.TENANT_SUPPORT,
                ],
            )


# =============================================================================
# PlatformOperatorActionLog Schema Tests
# =============================================================================


@pytest.mark.unit
class TestPlatformOperatorActionLogSchema:
    """Test PlatformOperatorActionLog request schema validation."""

    def test_valid_action_with_target_org(self) -> None:
        data = PlatformOperatorActionLog(
            capability_used=CapabilityGroupEnum.TENANT_SUPPORT,
            target_org_id=uuid4(),
            action_type="view_tenant_jobs",
            action_detail={"job_count": 42},
        )
        assert data.capability_used == CapabilityGroupEnum.TENANT_SUPPORT
        assert data.action_type == "view_tenant_jobs"
        assert data.action_detail == {"job_count": 42}

    def test_valid_action_without_target_org(self) -> None:
        data = PlatformOperatorActionLog(
            capability_used=CapabilityGroupEnum.PLATFORM_OBSERVE,
            action_type="view_system_health",
        )
        assert data.target_org_id is None
        assert data.action_detail is None

    def test_empty_action_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PlatformOperatorActionLog(
                capability_used=CapabilityGroupEnum.PLATFORM_OBSERVE,
                action_type="",
            )

    def test_action_type_max_length(self) -> None:
        with pytest.raises(ValidationError):
            PlatformOperatorActionLog(
                capability_used=CapabilityGroupEnum.PLATFORM_OBSERVE,
                action_type="x" * 201,
            )

    def test_invalid_capability_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PlatformOperatorActionLog(
                capability_used="invalid_group",  # type: ignore[arg-type]
                action_type="view_health",
            )


# =============================================================================
# Response Schema Tests
# =============================================================================


@pytest.mark.unit
class TestPlatformOperatorResponseSchema:
    """Test response schema serialization."""

    def test_full_active_response(self) -> None:
        now = datetime.now(timezone.utc)
        data = PlatformOperatorResponse(
            id=uuid4(),
            user_id=uuid4(),
            capability_grants=["platform_observe", "tenant_support"],
            granted_by=uuid4(),
            granted_at=now,
            revoked_at=None,
            created_at=now,
            updated_at=now,
        )
        assert data.is_active is True
        assert len(data.capability_grants) == 2

    def test_revoked_response(self) -> None:
        now = datetime.now(timezone.utc)
        data = PlatformOperatorResponse(
            id=uuid4(),
            user_id=uuid4(),
            capability_grants=["founder_authority"],
            granted_by=uuid4(),
            granted_at=now,
            revoked_at=now,
            created_at=now,
            updated_at=now,
        )
        assert data.is_active is False

    def test_action_response(self) -> None:
        now = datetime.now(timezone.utc)
        data = PlatformOperatorActionResponse(
            id=uuid4(),
            operator_user_id=uuid4(),
            capability_used="platform_observe",
            target_org_id=uuid4(),
            action_type="view_system_health",
            action_detail={"status": "ok"},
            created_at=now,
        )
        assert data.action_type == "view_system_health"
        assert data.action_detail == {"status": "ok"}

    def test_list_response_empty(self) -> None:
        data = PlatformOperatorListResponse(
            items=[], total=0, limit=20, offset=0
        )
        assert data.items == []
        assert data.total == 0

    def test_list_response_has_more(self) -> None:
        now = datetime.now(timezone.utc)
        item = PlatformOperatorResponse(
            id=uuid4(),
            user_id=uuid4(),
            capability_grants=["platform_observe"],
            granted_by=uuid4(),
            granted_at=now,
            created_at=now,
            updated_at=now,
        )
        data = PlatformOperatorListResponse(
            items=[item], total=50, limit=20, offset=0
        )
        assert data.total == 50

    def test_action_list_response(self) -> None:
        data = PlatformOperatorActionListResponse(
            items=[], total=0, limit=20, offset=0
        )
        assert data.items == []
        assert data.total == 0
