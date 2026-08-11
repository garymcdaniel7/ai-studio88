"""Unit tests for ProductionGateService — gate checks, approval, and emergency path.

Tests cover:
    - run_gate_checks creates a gate record with all checks for FULL type
    - run_gate_checks uses reduced checks for EMERGENCY type
    - run_gate_checks applies check_overrides to specific checks
    - run_gate_checks sets emergency_verification_due for emergency gates
    - record_passage approves a passing gate with evidence
    - record_passage raises GateNotFoundError for missing gate
    - record_passage raises GateNotApprovableError when checks haven't passed
    - record_passage raises GateNotApprovableError when already approved
    - get_gate_status returns gate details and check counts
    - get_gate_status raises GateNotFoundError for missing gate
    - verify_emergency_gate runs full checks on emergency gate
    - verify_emergency_gate raises error for non-emergency gate
    - EMERGENCY_REQUIRED_CHECKS is a proper subset of FULL_REQUIRED_CHECKS
    - All GateCheckName values have registered implementations

Requirements: R83.1, R83.2, R83.6, R83.7, R83.8, R83.9
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# =============================================================================
# Mock heavy dependencies before importing application modules.
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

_sa_orm_mock = MagicMock()
_sa_orm_mock.Mapped = MagicMock
_sa_orm_mock.mapped_column = MagicMock(return_value=None)
_sa_orm_mock.relationship = MagicMock(return_value=None)
_sa_orm_mock.DeclarativeBase = type("DeclarativeBase", (), {})

_sa_dialects_pg_mock = MagicMock()
_sa_dialects_pg_mock.UUID = MagicMock
_sa_dialects_pg_mock.JSONB = MagicMock
_sa_dialects_pg_mock.ARRAY = MagicMock

_sa_ext_async_mock = MagicMock()
_sa_ext_async_mock.AsyncSession = MagicMock

# Patch before imports
sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_async_mock)

# Mock app.db.base to provide a usable Base
_base_mock = MagicMock()
_base_mock.Base = type("Base", (), {"metadata": MagicMock()})
_base_mock.UUIDMixin = type("UUIDMixin", (), {})
_base_mock.TimestampMixin = type("TimestampMixin", (), {})
_base_mock.TenantMixin = type("TenantMixin", (), {})
_base_mock.SoftDeleteMixin = type("SoftDeleteMixin", (), {})
sys.modules.setdefault("app.db.base", _base_mock)
sys.modules.setdefault("app.db", MagicMock())
sys.modules.setdefault("app.db.session", MagicMock())

# Mock app.core.logging
_logging_mock = MagicMock()
_logging_mock.get_logger = MagicMock(return_value=MagicMock())
sys.modules.setdefault("app.core.logging", _logging_mock)

# Now import the modules under test
from app.schemas.production_gate import (
    EMERGENCY_REQUIRED_CHECKS,
    FULL_REQUIRED_CHECKS,
    GateCheckName,
    GateCheckResult,
    GateType,
)
from app.services.production_gate_service import (
    GATE_CHECK_REGISTRY,
    GateNotApprovableError,
    GateNotFoundError,
    ProductionGateError,
    ProductionGateService,
    ReleaseIdentityNotFoundError,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_mock_db() -> MagicMock:
    """Create a mock AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_mock_gate(
    gate_id: UUID | None = None,
    all_passed: bool = True,
    gate_type: str = "full",
    approved_at: datetime | None = None,
    checks: list | None = None,
) -> MagicMock:
    """Create a mock ProductionGate ORM object."""
    gate = MagicMock()
    gate.id = gate_id or uuid4()
    gate.release_identity_id = uuid4()
    gate.gate_type = gate_type
    gate.checks = checks or []
    gate.all_passed = all_passed
    gate.evidence_links = {}
    gate.approving_actor = None
    gate.approved_at = approved_at
    gate.emergency_verification_due = None
    gate.emergency_verified = False
    gate.failure_summary = None
    gate.created_at = datetime.now(UTC)
    return gate


# =============================================================================
# Tests: Check Registry Completeness
# =============================================================================


class TestGateCheckRegistry:
    """Tests for gate check registry and check type definitions."""

    def test_all_check_names_have_implementation(self):
        """Every GateCheckName value must have a registered check function."""
        for check_name in GateCheckName:
            assert check_name in GATE_CHECK_REGISTRY, (
                f"GateCheckName.{check_name.name} has no registered implementation"
            )

    def test_emergency_checks_are_subset_of_full(self):
        """Emergency required checks must be a proper subset of full checks."""
        assert EMERGENCY_REQUIRED_CHECKS < FULL_REQUIRED_CHECKS

    def test_full_checks_cover_all_defined_checks(self):
        """Full gate requires all 14 defined check types."""
        assert FULL_REQUIRED_CHECKS == set(GateCheckName)
        assert len(FULL_REQUIRED_CHECKS) == 14

    def test_emergency_checks_include_critical_subset(self):
        """Emergency path must include build, CI, tenant isolation, and security."""
        assert GateCheckName.FRONTEND_BUILD in EMERGENCY_REQUIRED_CHECKS
        assert GateCheckName.BACKEND_BUILD in EMERGENCY_REQUIRED_CHECKS
        assert GateCheckName.CI_GREEN in EMERGENCY_REQUIRED_CHECKS
        assert GateCheckName.TENANT_ISOLATION_TESTS in EMERGENCY_REQUIRED_CHECKS
        assert GateCheckName.SECURITY_EVIDENCE in EMERGENCY_REQUIRED_CHECKS


# =============================================================================
# Tests: run_gate_checks
# =============================================================================


class TestRunGateChecks:
    """Tests for ProductionGateService.run_gate_checks()."""

    @pytest.mark.asyncio
    async def test_full_gate_runs_all_14_checks(self):
        """Full gate type executes all 14 check types."""
        db = _make_mock_db()
        service = ProductionGateService(db)

        # Mock the ProductionGate model at the import location
        mock_gate_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid4()
        mock_instance.created_at = datetime.now(UTC)
        mock_gate_cls.return_value = mock_instance

        with patch.dict(
            "sys.modules",
            {"app.models.production_gate": MagicMock(ProductionGate=mock_gate_cls)},
        ):
            result = await service.run_gate_checks(
                release_identity_id=uuid4(),
                gate_type=GateType.FULL,
            )

        assert len(result["checks"]) == 14
        assert result["gate_type"] == "full"
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_emergency_gate_runs_reduced_checks(self):
        """Emergency gate type only runs the critical subset."""
        db = _make_mock_db()
        service = ProductionGateService(db)

        mock_gate_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid4()
        mock_instance.created_at = datetime.now(UTC)
        mock_gate_cls.return_value = mock_instance

        with patch.dict(
            "sys.modules",
            {"app.models.production_gate": MagicMock(ProductionGate=mock_gate_cls)},
        ):
            result = await service.run_gate_checks(
                release_identity_id=uuid4(),
                gate_type=GateType.EMERGENCY,
            )

        assert len(result["checks"]) == len(EMERGENCY_REQUIRED_CHECKS)
        assert result["gate_type"] == "emergency"
        assert result["emergency_verification_due"] is not None

    @pytest.mark.asyncio
    async def test_all_checks_pass_sets_all_passed_true(self):
        """When all checks pass, all_passed should be True."""
        db = _make_mock_db()
        service = ProductionGateService(db)

        mock_gate_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid4()
        mock_instance.created_at = datetime.now(UTC)
        mock_gate_cls.return_value = mock_instance

        # Mock all gate check functions to return passing results so we can
        # verify the all_passed aggregation logic in isolation.
        async def _always_pass_check(name: str):
            return GateCheckResult(
                check_name=name,
                passed=True,
                evidence_url=None,
                message="Mocked pass",
                checked_at=datetime.now(UTC),
            )

        mock_registry = {}
        for check_name in GateCheckName:
            cn = check_name

            async def _mock_fn(_cn=cn):
                return GateCheckResult(
                    check_name=_cn.value,
                    passed=True,
                    evidence_url=None,
                    message="Mocked pass",
                    checked_at=datetime.now(UTC),
                )

            mock_registry[cn] = _mock_fn

        with patch.dict(
            "sys.modules",
            {"app.models.production_gate": MagicMock(ProductionGate=mock_gate_cls)},
        ), patch(
            "app.services.production_gate_service.GATE_CHECK_REGISTRY",
            mock_registry,
        ):
            result = await service.run_gate_checks(
                release_identity_id=uuid4(),
                gate_type=GateType.FULL,
            )

        assert result["all_passed"] is True
        assert result["failure_summary"] is None

    @pytest.mark.asyncio
    async def test_override_failed_check_sets_all_passed_false(self):
        """Manual override to False should cause all_passed=False."""
        db = _make_mock_db()
        service = ProductionGateService(db)

        mock_gate_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid4()
        mock_instance.created_at = datetime.now(UTC)
        mock_gate_cls.return_value = mock_instance

        with patch.dict(
            "sys.modules",
            {"app.models.production_gate": MagicMock(ProductionGate=mock_gate_cls)},
        ):
            result = await service.run_gate_checks(
                release_identity_id=uuid4(),
                gate_type=GateType.FULL,
                check_overrides={"frontend_build": False},
            )

        assert result["all_passed"] is False
        assert result["failure_summary"] is not None
        assert "frontend_build" in result["failure_summary"]

    @pytest.mark.asyncio
    async def test_emergency_gate_has_24h_verification_due(self):
        """Emergency gates set a 24h verification deadline."""
        db = _make_mock_db()
        service = ProductionGateService(db)

        mock_gate_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid4()
        mock_instance.created_at = datetime.now(UTC)
        mock_gate_cls.return_value = mock_instance

        with patch.dict(
            "sys.modules",
            {"app.models.production_gate": MagicMock(ProductionGate=mock_gate_cls)},
        ):
            result = await service.run_gate_checks(
                release_identity_id=uuid4(),
                gate_type=GateType.EMERGENCY,
            )

        # Parse the ISO timestamp and verify it's ~24h from now
        due = datetime.fromisoformat(result["emergency_verification_due"])
        expected_min = datetime.now(UTC) + timedelta(hours=23, minutes=55)
        expected_max = datetime.now(UTC) + timedelta(hours=24, minutes=5)
        assert expected_min <= due <= expected_max


# =============================================================================
# Tests: record_passage
# =============================================================================


class TestRecordPassage:
    """Tests for ProductionGateService.record_passage()."""

    @pytest.mark.asyncio
    async def test_approve_passing_gate(self):
        """Approving a gate that has all_passed=True succeeds."""
        db = _make_mock_db()
        gate = _make_mock_gate(all_passed=True)

        # Mock the DB query to return our gate
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = gate
        db.execute.return_value = mock_result

        service = ProductionGateService(db)
        approving_actor = uuid4()
        evidence = {"frontend_build": "https://ci.example.com/run/123"}

        # The service does a local import of `select` and `ProductionGate`
        mock_pg_module = MagicMock()
        mock_pg_module.ProductionGate = MagicMock()
        mock_pg_module.ProductionGate.id = MagicMock()
        with patch.dict("sys.modules", {"app.models.production_gate": mock_pg_module}):
            result = await service.record_passage(
                gate_id=gate.id,
                approving_actor=approving_actor,
                evidence_links=evidence,
            )

        assert result["approving_actor"] == approving_actor
        assert result["approved_at"] is not None
        assert gate.evidence_links == evidence
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approve_missing_gate_raises_not_found(self):
        """Approving a non-existent gate raises GateNotFoundError."""
        db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        service = ProductionGateService(db)

        mock_pg_module = MagicMock()
        mock_pg_module.ProductionGate = MagicMock()
        mock_pg_module.ProductionGate.id = MagicMock()
        with patch.dict("sys.modules", {"app.models.production_gate": mock_pg_module}):
            with pytest.raises(GateNotFoundError):
                await service.record_passage(
                    gate_id=uuid4(),
                    approving_actor=uuid4(),
                )

    @pytest.mark.asyncio
    async def test_approve_failing_gate_raises_not_approvable(self):
        """Approving a gate where all_passed=False raises GateNotApprovableError."""
        db = _make_mock_db()
        gate = _make_mock_gate(all_passed=False)
        gate.failure_summary = "1 check(s) failed — frontend_build"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = gate
        db.execute.return_value = mock_result

        service = ProductionGateService(db)

        mock_pg_module = MagicMock()
        mock_pg_module.ProductionGate = MagicMock()
        mock_pg_module.ProductionGate.id = MagicMock()
        with patch.dict("sys.modules", {"app.models.production_gate": mock_pg_module}):
            with pytest.raises(GateNotApprovableError):
                await service.record_passage(
                    gate_id=gate.id,
                    approving_actor=uuid4(),
                )

    @pytest.mark.asyncio
    async def test_approve_already_approved_raises_not_approvable(self):
        """Re-approving an already-approved gate raises GateNotApprovableError."""
        db = _make_mock_db()
        gate = _make_mock_gate(all_passed=True, approved_at=datetime.now(UTC))

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = gate
        db.execute.return_value = mock_result

        service = ProductionGateService(db)

        mock_pg_module = MagicMock()
        mock_pg_module.ProductionGate = MagicMock()
        mock_pg_module.ProductionGate.id = MagicMock()
        with patch.dict("sys.modules", {"app.models.production_gate": mock_pg_module}):
            with pytest.raises(GateNotApprovableError) as exc_info:
                await service.record_passage(
                    gate_id=gate.id,
                    approving_actor=uuid4(),
                )
            assert "already been approved" in exc_info.value.message


# =============================================================================
# Tests: get_gate_status
# =============================================================================


class TestGetGateStatus:
    """Tests for ProductionGateService.get_gate_status()."""

    @pytest.mark.asyncio
    async def test_returns_gate_with_check_counts(self):
        """Returns gate details with total/passed/failed check counts."""
        db = _make_mock_db()
        gate = _make_mock_gate(all_passed=False)
        gate.checks = [
            {"check_name": "frontend_build", "passed": True},
            {"check_name": "backend_build", "passed": True},
            {"check_name": "ci_green", "passed": False},
        ]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = gate
        db.execute.return_value = mock_result

        service = ProductionGateService(db)

        mock_pg_module = MagicMock()
        mock_pg_module.ProductionGate = MagicMock()
        mock_pg_module.ProductionGate.id = MagicMock()
        with patch.dict("sys.modules", {"app.models.production_gate": mock_pg_module}):
            result = await service.get_gate_status(gate.id)

        assert result["total_checks"] == 3
        assert result["passed_checks"] == 2
        assert result["failed_checks"] == 1

    @pytest.mark.asyncio
    async def test_missing_gate_raises_not_found(self):
        """Querying a non-existent gate raises GateNotFoundError."""
        db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        service = ProductionGateService(db)

        mock_pg_module = MagicMock()
        mock_pg_module.ProductionGate = MagicMock()
        mock_pg_module.ProductionGate.id = MagicMock()
        with patch.dict("sys.modules", {"app.models.production_gate": mock_pg_module}):
            with pytest.raises(GateNotFoundError):
                await service.get_gate_status(uuid4())


# =============================================================================
# Tests: verify_emergency_gate
# =============================================================================


class TestVerifyEmergencyGate:
    """Tests for ProductionGateService.verify_emergency_gate()."""

    @pytest.mark.asyncio
    async def test_verify_emergency_gate_succeeds(self):
        """Full verification of emergency gate marks emergency_verified=True."""
        db = _make_mock_db()
        gate = _make_mock_gate(gate_type="emergency", all_passed=True)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = gate
        db.execute.return_value = mock_result

        service = ProductionGateService(db)

        # Mock all gate check functions to return passing results
        mock_registry = {}
        for check_name in GateCheckName:
            cn = check_name

            async def _mock_fn(_cn=cn):
                return GateCheckResult(
                    check_name=_cn.value,
                    passed=True,
                    evidence_url=None,
                    message="Mocked pass",
                    checked_at=datetime.now(UTC),
                )

            mock_registry[cn] = _mock_fn

        mock_pg_module = MagicMock()
        mock_pg_module.ProductionGate = MagicMock()
        mock_pg_module.ProductionGate.id = MagicMock()
        with patch.dict("sys.modules", {"app.models.production_gate": mock_pg_module}), \
             patch(
                 "app.services.production_gate_service.GATE_CHECK_REGISTRY",
                 mock_registry,
             ):
            result = await service.verify_emergency_gate(gate.id)

        assert gate.emergency_verified is True
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_verify_non_emergency_gate_raises_error(self):
        """Calling verify on a full gate raises ProductionGateError."""
        db = _make_mock_db()
        gate = _make_mock_gate(gate_type="full")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = gate
        db.execute.return_value = mock_result

        service = ProductionGateService(db)

        mock_pg_module = MagicMock()
        mock_pg_module.ProductionGate = MagicMock()
        mock_pg_module.ProductionGate.id = MagicMock()
        with patch.dict("sys.modules", {"app.models.production_gate": mock_pg_module}):
            with pytest.raises(ProductionGateError) as exc_info:
                await service.verify_emergency_gate(gate.id)
            assert "NOT_EMERGENCY_GATE" == exc_info.value.code

    @pytest.mark.asyncio
    async def test_verify_missing_gate_raises_not_found(self):
        """Verifying a non-existent gate raises GateNotFoundError."""
        db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        service = ProductionGateService(db)

        mock_pg_module = MagicMock()
        mock_pg_module.ProductionGate = MagicMock()
        mock_pg_module.ProductionGate.id = MagicMock()
        with patch.dict("sys.modules", {"app.models.production_gate": mock_pg_module}):
            with pytest.raises(GateNotFoundError):
                await service.verify_emergency_gate(uuid4())


# =============================================================================
# Tests: GateCheckResult schema validation
# =============================================================================


class TestGateCheckResultSchema:
    """Tests for the GateCheckResult Pydantic schema."""

    def test_valid_check_result(self):
        """A properly formed check result passes validation."""
        result = GateCheckResult(
            check_name="frontend_build",
            passed=True,
            evidence_url="https://ci.example.com/run/123",
            message="Build succeeded with 0 errors",
            checked_at=datetime.now(UTC),
        )
        assert result.check_name == "frontend_build"
        assert result.passed is True

    def test_check_result_without_evidence_url(self):
        """evidence_url is optional and defaults to None."""
        result = GateCheckResult(
            check_name="backend_build",
            passed=False,
            message="Build failed: 3 type errors",
            checked_at=datetime.now(UTC),
        )
        assert result.evidence_url is None
        assert result.passed is False

    def test_check_name_min_length(self):
        """Empty check_name should fail validation."""
        with pytest.raises(Exception):
            GateCheckResult(
                check_name="",
                passed=True,
                message="test",
                checked_at=datetime.now(UTC),
            )

    def test_message_min_length(self):
        """Empty message should fail validation."""
        with pytest.raises(Exception):
            GateCheckResult(
                check_name="test",
                passed=True,
                message="",
                checked_at=datetime.now(UTC),
            )
