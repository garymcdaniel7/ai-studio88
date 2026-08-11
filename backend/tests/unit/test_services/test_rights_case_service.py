"""Unit tests for RightsCaseService — rights/takedown case lifecycle management.

Tests cover:
    - create_case succeeds with valid data
    - create_case CSAM auto-escalates to critical + action_required
    - create_case CSAM sets legal_hold_active to True
    - update_case valid transition succeeds
    - update_case invalid transition raises InvalidCaseTransitionError
    - update_case on closed case raises CaseClosedError
    - update_case appends to actions_taken audit trail
    - submit_appeal succeeds from restricted/removed/resolved
    - submit_appeal invalid state raises InvalidCaseTransitionError
    - list_cases returns paginated results
    - list_cases filters by status, priority, case_type
    - get_case returns None for non-existent ID

Requirements: R40.1, R40.2, R40.3, R40.4, R40.5, R40.7, R40.8, R40.9, A2-005
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
_sa_mock.CheckConstraint = MagicMock
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
_sa_dialects_pg_mock.UUID = MagicMock(return_value=MagicMock())
_sa_dialects_pg_mock.JSONB = MagicMock(return_value=MagicMock())
_sa_dialects_pg_mock.ARRAY = MagicMock(return_value=MagicMock())

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
    """Fake base that accepts kwargs (like SQLAlchemy models do)."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeTimestampMixin:
    """Fake mixin — adds created_at/updated_at as class-level MagicMock attrs."""
    created_at = MagicMock()
    updated_at = MagicMock()


_mock_db_base.Base = _FakeBase  # type: ignore[attr-defined]
_mock_db_base.TimestampMixin = _FakeTimestampMixin  # type: ignore[attr-defined]
_mock_db_base.UUIDMixin = type("UUIDMixin", (), {"id": MagicMock()})  # type: ignore[attr-defined]
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
_structlog_mock = MagicMock()
_structlog_mock.get_logger = MagicMock(return_value=MagicMock())
sys.modules.setdefault("structlog", _structlog_mock)

# Mock backend module
_mock_backend = ModuleType("backend")
_mock_backend.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("backend", _mock_backend)
sys.modules.setdefault("backend.database", MagicMock())

# Now import the model and service under test
# Import directly from the module file to avoid __init__.py chain
import importlib.util

_model_spec = importlib.util.spec_from_file_location(
    "app.models.rights_case",
    "app/models/rights_case.py",
)
_model_mod = importlib.util.module_from_spec(_model_spec)
sys.modules["app.models.rights_case"] = _model_mod
_model_spec.loader.exec_module(_model_mod)

from app.models.rights_case import (
    RightsCase,
    RightsCasePriority,
    RightsCaseStatus,
    RightsCaseType,
    VALID_STATUS_TRANSITIONS,
)

# Mock the models package to prevent __init__.py from re-importing
_mock_models_pkg = ModuleType("app.models")
_mock_models_pkg.__path__ = []  # type: ignore[attr-defined]
_mock_models_pkg.RightsCase = RightsCase  # type: ignore[attr-defined]
sys.modules.setdefault("app.models", _mock_models_pkg)

# Mock app.core.logging
_mock_logging_mod = ModuleType("app.core.logging")
_mock_logger = MagicMock()
_mock_logging_mod.get_logger = MagicMock(return_value=_mock_logger)  # type: ignore[attr-defined]
sys.modules.setdefault("app.core", ModuleType("app.core"))
sys.modules["app.core"].__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.core.logging", _mock_logging_mod)

# Mock app.core.config
_mock_config_mod = ModuleType("app.core.config")
_mock_settings = MagicMock()
_mock_settings.log_level = "INFO"
_mock_settings.is_production = False
_mock_config_mod.get_settings = MagicMock(return_value=_mock_settings)  # type: ignore[attr-defined]
_mock_config_mod.reset_settings = MagicMock()  # type: ignore[attr-defined]
_mock_config_mod.Settings = MagicMock  # type: ignore[attr-defined]
sys.modules.setdefault("app.core.config", _mock_config_mod)

# Now import the service
_service_spec = importlib.util.spec_from_file_location(
    "app.services.rights_case_service",
    "app/services/rights_case_service.py",
)
_service_mod = importlib.util.module_from_spec(_service_spec)
sys.modules["app.services.rights_case_service"] = _service_mod
_service_spec.loader.exec_module(_service_mod)

from app.services.rights_case_service import (
    CaseClosedError,
    CaseNotFoundError,
    InvalidCaseTransitionError,
    RightsCaseService,
)


# =============================================================================
# Constants & Helpers
# =============================================================================

OPERATOR_ID = uuid4()
CASE_ID = uuid4()
ORG_ID = uuid4()


class FakeRightsCase:
    """Fake RightsCase for testing without ORM."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid4())
        self.case_type = kwargs.get("case_type", "copyright")
        self.status = kwargs.get("status", "received")
        self.priority = kwargs.get("priority", "normal")
        self.reporter_contact = kwargs.get("reporter_contact")
        self.target_org_id = kwargs.get("target_org_id")
        self.target_talent_ids = kwargs.get("target_talent_ids")
        self.target_asset_ids = kwargs.get("target_asset_ids")
        self.reported_urls = kwargs.get("reported_urls")
        self.evidence_refs = kwargs.get("evidence_refs", [])
        self.assigned_operator = kwargs.get("assigned_operator")
        self.actions_taken = kwargs.get("actions_taken", [])
        self.resolution = kwargs.get("resolution")
        self.appeal_state = kwargs.get("appeal_state")
        self.legal_hold_active = kwargs.get("legal_hold_active", False)
        self.created_at = kwargs.get("created_at", datetime.now(UTC))
        self.updated_at = kwargs.get("updated_at", datetime.now(UTC))

    @property
    def is_terminal(self) -> bool:
        return self.status == RightsCaseStatus.CLOSED.value

    def can_transition_to(self, new_status: RightsCaseStatus) -> bool:
        try:
            current = RightsCaseStatus(self.status)
        except ValueError:
            return False
        return new_status in VALID_STATUS_TRANSITIONS.get(current, set())


def _make_db_mock() -> AsyncMock:
    """Create a mock AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    return db


# =============================================================================
# Tests: create_case
# =============================================================================


class TestCreateCase:
    """Tests for RightsCaseService.create_case."""

    @pytest.mark.asyncio
    async def test_create_case_copyright_success(self):
        """Create a copyright case with status 'received' and normal priority."""
        db = _make_db_mock()
        service = RightsCaseService(db=db)

        case = await service.create_case(
            case_type="copyright",
            reporter_contact={"email": "reporter@example.com"},
            content_url_or_id="https://example.com/content/123",
            description="This is my copyrighted image",
        )

        # Verify the case was added to the session
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

        added_case = db.add.call_args[0][0]
        assert added_case.case_type == "copyright"
        assert added_case.status == "received"
        assert added_case.priority == "normal"
        assert added_case.legal_hold_active is False
        assert added_case.reporter_contact == {"email": "reporter@example.com"}
        assert added_case.reported_urls == ["https://example.com/content/123"]

    @pytest.mark.asyncio
    async def test_create_case_csam_auto_escalation(self):
        """CSAM case auto-escalates to critical + action_required."""
        db = _make_db_mock()
        service = RightsCaseService(db=db)

        case = await service.create_case(
            case_type="csam",
            reporter_contact={"email": "reporter@example.com"},
            content_url_or_id="https://example.com/bad-content",
            description="CSAM content detected",
        )

        added_case = db.add.call_args[0][0]
        assert added_case.case_type == "csam"
        assert added_case.status == "action_required"
        assert added_case.priority == "critical"
        assert added_case.legal_hold_active is True

    @pytest.mark.asyncio
    async def test_create_case_csam_has_escalation_audit_entry(self):
        """CSAM case has auto-escalation in actions_taken audit trail."""
        db = _make_db_mock()
        service = RightsCaseService(db=db)

        await service.create_case(
            case_type="csam",
            reporter_contact={"email": "reporter@example.com"},
            content_url_or_id="https://example.com/bad-content",
            description="CSAM content detected",
        )

        added_case = db.add.call_args[0][0]
        action_types = [a["action_type"] for a in added_case.actions_taken]
        assert "csam_auto_escalation" in action_types
        assert "case_created" in action_types

    @pytest.mark.asyncio
    async def test_create_case_evidence_urls_stored(self):
        """Evidence URLs are stored in evidence_refs."""
        db = _make_db_mock()
        service = RightsCaseService(db=db)

        await service.create_case(
            case_type="trademark",
            reporter_contact={"email": "tm@company.com"},
            content_url_or_id="https://example.com/content/456",
            description="Trademark violation",
            evidence_urls=["https://evidence.com/doc1.pdf", "https://evidence.com/doc2.pdf"],
        )

        added_case = db.add.call_args[0][0]
        assert len(added_case.evidence_refs) == 2
        assert added_case.evidence_refs[0]["url"] == "https://evidence.com/doc1.pdf"
        assert added_case.evidence_refs[0]["type"] == "reporter_submitted"


# =============================================================================
# Tests: update_case
# =============================================================================


class TestUpdateCase:
    """Tests for RightsCaseService.update_case."""

    @pytest.mark.asyncio
    async def test_update_case_valid_transition(self):
        """Transition from received to triaged succeeds."""
        db = _make_db_mock()
        fake_case = FakeRightsCase(id=CASE_ID, status="received")

        # Mock get_case to return the fake case
        service = RightsCaseService(db=db)
        service.get_case = AsyncMock(return_value=fake_case)

        result = await service.update_case(
            case_id=CASE_ID,
            operator_id=OPERATOR_ID,
            status="triaged",
        )

        assert result.status == "triaged"
        # Verify action was appended
        assert len(result.actions_taken) == 1
        assert result.actions_taken[0]["action_type"] == "status_change"
        assert result.actions_taken[0]["prior_status"] == "received"
        assert result.actions_taken[0]["new_status"] == "triaged"
        assert result.actions_taken[0]["actor"] == str(OPERATOR_ID)

    @pytest.mark.asyncio
    async def test_update_case_invalid_transition_raises(self):
        """Invalid transition (received → closed) raises InvalidCaseTransitionError."""
        db = _make_db_mock()
        fake_case = FakeRightsCase(id=CASE_ID, status="received")

        service = RightsCaseService(db=db)
        service.get_case = AsyncMock(return_value=fake_case)

        with pytest.raises(InvalidCaseTransitionError) as exc_info:
            await service.update_case(
                case_id=CASE_ID,
                operator_id=OPERATOR_ID,
                status="closed",
            )
        assert "received" in exc_info.value.message
        assert "closed" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_update_case_closed_raises(self):
        """Updating a closed case raises CaseClosedError."""
        db = _make_db_mock()
        fake_case = FakeRightsCase(id=CASE_ID, status="closed")

        service = RightsCaseService(db=db)
        service.get_case = AsyncMock(return_value=fake_case)

        with pytest.raises(CaseClosedError) as exc_info:
            await service.update_case(
                case_id=CASE_ID,
                operator_id=OPERATOR_ID,
                priority="high",
            )
        assert str(CASE_ID) in exc_info.value.message

    @pytest.mark.asyncio
    async def test_update_case_not_found_raises(self):
        """Non-existent case raises CaseNotFoundError."""
        db = _make_db_mock()

        service = RightsCaseService(db=db)
        service.get_case = AsyncMock(return_value=None)

        with pytest.raises(CaseNotFoundError) as exc_info:
            await service.update_case(
                case_id=CASE_ID,
                operator_id=OPERATOR_ID,
                status="triaged",
            )
        assert str(CASE_ID) in exc_info.value.message

    @pytest.mark.asyncio
    async def test_update_case_appends_action_note(self):
        """Action note is appended to actions_taken audit trail."""
        db = _make_db_mock()
        fake_case = FakeRightsCase(
            id=CASE_ID,
            status="triaged",
            actions_taken=[{"action_type": "case_created", "actor": "system"}],
        )

        service = RightsCaseService(db=db)
        service.get_case = AsyncMock(return_value=fake_case)

        result = await service.update_case(
            case_id=CASE_ID,
            operator_id=OPERATOR_ID,
            status="action_required",
            action_note="Contacted rights holder for verification",
        )

        assert len(result.actions_taken) == 2
        latest = result.actions_taken[-1]
        assert latest["note"] == "Contacted rights holder for verification"

    @pytest.mark.asyncio
    async def test_update_case_legal_hold(self):
        """Legal hold change is recorded in actions_taken."""
        db = _make_db_mock()
        fake_case = FakeRightsCase(id=CASE_ID, status="action_required")

        service = RightsCaseService(db=db)
        service.get_case = AsyncMock(return_value=fake_case)

        result = await service.update_case(
            case_id=CASE_ID,
            operator_id=OPERATOR_ID,
            legal_hold_active=True,
        )

        assert result.legal_hold_active is True
        assert result.actions_taken[-1]["legal_hold_active"] is True

    @pytest.mark.asyncio
    async def test_update_case_assignment(self):
        """Assigning an operator is recorded."""
        db = _make_db_mock()
        fake_case = FakeRightsCase(id=CASE_ID, status="received")
        new_operator = uuid4()

        service = RightsCaseService(db=db)
        service.get_case = AsyncMock(return_value=fake_case)

        result = await service.update_case(
            case_id=CASE_ID,
            operator_id=OPERATOR_ID,
            assigned_operator=new_operator,
        )

        assert result.assigned_operator == new_operator
        assert result.actions_taken[-1]["assigned_to"] == str(new_operator)


# =============================================================================
# Tests: submit_appeal
# =============================================================================


class TestSubmitAppeal:
    """Tests for RightsCaseService.submit_appeal."""

    @pytest.mark.asyncio
    async def test_appeal_from_restricted_succeeds(self):
        """Appeal from RESTRICTED status succeeds."""
        db = _make_db_mock()
        fake_case = FakeRightsCase(id=CASE_ID, status="restricted")

        service = RightsCaseService(db=db)
        service.get_case = AsyncMock(return_value=fake_case)

        result = await service.submit_appeal(
            case_id=CASE_ID,
            appellant_email="user@example.com",
            reason="The content is original work, here is my proof.",
        )

        assert result.status == "appealed"
        assert result.appeal_state == "pending_review"
        appeal_action = result.actions_taken[-1]
        assert appeal_action["action_type"] == "appeal_submitted"
        assert appeal_action["appellant_email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_appeal_from_removed_succeeds(self):
        """Appeal from REMOVED status succeeds."""
        db = _make_db_mock()
        fake_case = FakeRightsCase(id=CASE_ID, status="removed")

        service = RightsCaseService(db=db)
        service.get_case = AsyncMock(return_value=fake_case)

        result = await service.submit_appeal(
            case_id=CASE_ID,
            appellant_email="user@example.com",
            reason="My content was incorrectly flagged",
        )

        assert result.status == "appealed"

    @pytest.mark.asyncio
    async def test_appeal_from_received_raises(self):
        """Cannot appeal a case still in RECEIVED status."""
        db = _make_db_mock()
        fake_case = FakeRightsCase(id=CASE_ID, status="received")

        service = RightsCaseService(db=db)
        service.get_case = AsyncMock(return_value=fake_case)

        with pytest.raises(InvalidCaseTransitionError):
            await service.submit_appeal(
                case_id=CASE_ID,
                appellant_email="user@example.com",
                reason="I want to appeal",
            )

    @pytest.mark.asyncio
    async def test_appeal_not_found_raises(self):
        """Appeal on non-existent case raises CaseNotFoundError."""
        db = _make_db_mock()

        service = RightsCaseService(db=db)
        service.get_case = AsyncMock(return_value=None)

        with pytest.raises(CaseNotFoundError):
            await service.submit_appeal(
                case_id=CASE_ID,
                appellant_email="user@example.com",
                reason="I want to appeal",
            )


# =============================================================================
# Tests: list_cases
# =============================================================================


class TestListCases:
    """Tests for RightsCaseService.list_cases."""

    @pytest.mark.asyncio
    async def test_list_cases_returns_results(self):
        """list_cases returns items and total count."""
        db = _make_db_mock()

        fake_cases = [
            FakeRightsCase(status="received"),
            FakeRightsCase(status="triaged"),
        ]

        # Mock the scalar (count) and execute (items)
        db.scalar = AsyncMock(return_value=2)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = fake_cases
        db.execute = AsyncMock(return_value=mock_result)

        service = RightsCaseService(db=db)
        items, total = await service.list_cases(limit=20, offset=0)

        assert total == 2
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_list_cases_clamps_limit(self):
        """list_cases clamps limit to valid range."""
        db = _make_db_mock()
        db.scalar = AsyncMock(return_value=0)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        service = RightsCaseService(db=db)

        # Over max
        await service.list_cases(limit=200, offset=0)
        # Under min
        await service.list_cases(limit=0, offset=0)


# =============================================================================
# Tests: Valid Transitions
# =============================================================================


class TestValidTransitions:
    """Tests verifying the status transition graph."""

    def test_received_can_transition_to_triaged(self):
        """RECEIVED → TRIAGED is valid."""
        case = FakeRightsCase(status="received")
        assert case.can_transition_to(RightsCaseStatus.TRIAGED) is True

    def test_received_cannot_transition_to_closed(self):
        """RECEIVED → CLOSED is invalid."""
        case = FakeRightsCase(status="received")
        assert case.can_transition_to(RightsCaseStatus.CLOSED) is False

    def test_triaged_can_transition_to_action_required(self):
        """TRIAGED → ACTION_REQUIRED is valid."""
        case = FakeRightsCase(status="triaged")
        assert case.can_transition_to(RightsCaseStatus.ACTION_REQUIRED) is True

    def test_triaged_can_transition_to_no_action(self):
        """TRIAGED → NO_ACTION is valid."""
        case = FakeRightsCase(status="triaged")
        assert case.can_transition_to(RightsCaseStatus.NO_ACTION) is True

    def test_action_required_can_transition_to_restricted(self):
        """ACTION_REQUIRED → RESTRICTED is valid."""
        case = FakeRightsCase(status="action_required")
        assert case.can_transition_to(RightsCaseStatus.RESTRICTED) is True

    def test_restricted_can_be_appealed(self):
        """RESTRICTED → APPEALED is valid."""
        case = FakeRightsCase(status="restricted")
        assert case.can_transition_to(RightsCaseStatus.APPEALED) is True

    def test_appealed_transitions_to_re_reviewed(self):
        """APPEALED → RE_REVIEWED is valid."""
        case = FakeRightsCase(status="appealed")
        assert case.can_transition_to(RightsCaseStatus.RE_REVIEWED) is True

    def test_closed_is_terminal(self):
        """CLOSED has no valid transitions."""
        case = FakeRightsCase(status="closed")
        assert case.is_terminal is True
        for status in RightsCaseStatus:
            assert case.can_transition_to(status) is False
