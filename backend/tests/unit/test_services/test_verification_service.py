"""Unit tests for IndependentVerificationService.

Tests cover:
    - run_automated_verification records evidence for mapped requirements
    - record_evidence creates evidence record with correct fields
    - get_verification_status aggregates coverage correctly
    - classify_feature returns PRODUCTION only with independent evidence
    - classify_feature returns PARTIAL when only automated tests exist
    - classify_feature returns UNVERIFIED when no evidence exists
    - Developer assertion alone is insufficient for PRODUCTION (R82.1, R82.6)
    - get_evidence_for_requirement returns paginated results

Requirements: R82.1, R82.2, R82.3, R82.4, R82.5, R82.6
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
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

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_async_mock)

_base_mock = MagicMock()
_base_mock.Base = type("Base", (), {"metadata": MagicMock()})
_base_mock.UUIDMixin = type("UUIDMixin", (), {})
_base_mock.TimestampMixin = type("TimestampMixin", (), {})
_base_mock.TenantMixin = type("TenantMixin", (), {})
_base_mock.SoftDeleteMixin = type("SoftDeleteMixin", (), {})
sys.modules.setdefault("app.db.base", _base_mock)
sys.modules.setdefault("app.db", MagicMock())
sys.modules.setdefault("app.db.session", MagicMock())

_logging_mock = MagicMock()
_logging_mock.get_logger = MagicMock(return_value=MagicMock())
sys.modules.setdefault("app.core.logging", _logging_mock)

# Now import the modules under test
from app.schemas.verification import (
    FeatureClassification,
    RequirementCoverageItem,
    VerificationMethod,
)
from app.services.verification_service import (
    INDEPENDENT_METHODS,
    EvidenceNotFoundError,
    IndependentVerificationService,
    InsufficientVerificationError,
    VerificationError,
    _compute_requirement_coverage,
    _get_requirement_test_map,
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
    db.scalar = AsyncMock()
    return db


def _make_mock_evidence(
    requirement_id: str = "R2.1",
    feature_name: str = "tenant_isolation",
    method: str = "automated_test",
    passed: bool = True,
    verifier_identity: str = "test_suite",
) -> MagicMock:
    """Create a mock VerificationEvidence ORM object."""
    evidence = MagicMock()
    evidence.id = uuid4()
    evidence.requirement_id = requirement_id
    evidence.feature_name = feature_name
    evidence.method = method
    evidence.evidence_location = "tests/unit/test_tenant.py"
    evidence.evidence_type = "test_suite"
    evidence.passed = passed
    evidence.verified_at = datetime.now(UTC)
    evidence.verifier_identity = verifier_identity
    evidence.notes = None
    evidence.created_at = datetime.now(UTC)
    return evidence


# =============================================================================
# Tests: Schema and Enum Validation
# =============================================================================


class TestVerificationEnums:
    """Tests for verification enums and constants."""

    def test_independent_methods_excludes_automated(self):
        """INDEPENDENT_METHODS must not include automated_test."""
        assert VerificationMethod.AUTOMATED_TEST.value not in INDEPENDENT_METHODS

    def test_independent_methods_includes_human_review(self):
        """INDEPENDENT_METHODS includes human_review."""
        assert VerificationMethod.HUMAN_REVIEW.value in INDEPENDENT_METHODS

    def test_independent_methods_includes_hermes_inspection(self):
        """INDEPENDENT_METHODS includes hermes_inspection."""
        assert VerificationMethod.HERMES_INSPECTION.value in INDEPENDENT_METHODS

    def test_independent_methods_includes_adversarial_test(self):
        """INDEPENDENT_METHODS includes adversarial_test."""
        assert VerificationMethod.ADVERSARIAL_TEST.value in INDEPENDENT_METHODS

    def test_feature_classification_values(self):
        """FeatureClassification has the expected values."""
        assert FeatureClassification.PRODUCTION.value == "PRODUCTION"
        assert FeatureClassification.PARTIAL.value == "PARTIAL"
        assert FeatureClassification.UNVERIFIED.value == "UNVERIFIED"


# =============================================================================
# Tests: _get_requirement_test_map
# =============================================================================


class TestRequirementTestMap:
    """Tests for the requirement-to-test mapping."""

    def test_returns_full_map_without_filter(self):
        """Without a feature filter, returns all mapped requirements."""
        result = _get_requirement_test_map()
        assert len(result) > 0
        assert "R1.1" in result
        assert "R82.1" in result

    def test_filters_by_feature_name(self):
        """With a feature filter, returns only matching entries."""
        result = _get_requirement_test_map("auth_enforcement")
        assert all(v["feature_name"] == "auth_enforcement" for v in result.values())
        assert "R1.1" in result
        assert "R82.1" not in result

    def test_each_entry_has_required_fields(self):
        """Each map entry has feature_name and test_location."""
        result = _get_requirement_test_map()
        for req_id, info in result.items():
            assert "feature_name" in info, f"{req_id} missing feature_name"
            assert "test_location" in info, f"{req_id} missing test_location"


# =============================================================================
# Tests: _compute_requirement_coverage
# =============================================================================


class TestComputeRequirementCoverage:
    """Tests for coverage computation logic."""

    def test_no_evidence_returns_unverified(self):
        """No evidence yields UNVERIFIED classification."""
        result = _compute_requirement_coverage("R1.1", [])
        assert result.classification == FeatureClassification.UNVERIFIED.value
        assert result.evidence_count == 0
        assert not result.meets_independence_requirement

    def test_only_automated_returns_partial(self):
        """Only automated test evidence yields PARTIAL (R82.6)."""
        evidence = _make_mock_evidence(method="automated_test", passed=True)
        result = _compute_requirement_coverage("R2.1", [evidence])
        assert result.classification == FeatureClassification.PARTIAL.value
        assert result.has_automated_test is True
        assert result.has_human_review is False
        assert not result.meets_independence_requirement

    def test_automated_plus_human_review_returns_production(self):
        """Automated + human review (both passing) yields PRODUCTION."""
        auto = _make_mock_evidence(method="automated_test", passed=True)
        human = _make_mock_evidence(
            method="human_review", passed=True, verifier_identity="admin@studio.ai"
        )
        result = _compute_requirement_coverage("R2.1", [auto, human])
        assert result.classification == FeatureClassification.PRODUCTION.value
        assert result.has_automated_test is True
        assert result.has_human_review is True
        assert result.meets_independence_requirement is True

    def test_automated_plus_hermes_returns_production(self):
        """Automated + Hermes inspection (both passing) yields PRODUCTION."""
        auto = _make_mock_evidence(method="automated_test", passed=True)
        hermes = _make_mock_evidence(
            method="hermes_inspection", passed=True, verifier_identity="hermes"
        )
        result = _compute_requirement_coverage("R2.1", [auto, hermes])
        assert result.classification == FeatureClassification.PRODUCTION.value
        assert result.has_hermes_inspection is True
        assert result.meets_independence_requirement is True

    def test_automated_plus_adversarial_returns_production(self):
        """Automated + adversarial test (both passing) yields PRODUCTION."""
        auto = _make_mock_evidence(method="automated_test", passed=True)
        adversarial = _make_mock_evidence(
            method="adversarial_test", passed=True, verifier_identity="red_team"
        )
        result = _compute_requirement_coverage("R2.1", [auto, adversarial])
        assert result.classification == FeatureClassification.PRODUCTION.value
        assert result.has_adversarial_test is True

    def test_failing_evidence_prevents_production(self):
        """Even with both methods, failures prevent PRODUCTION."""
        auto = _make_mock_evidence(method="automated_test", passed=True)
        human = _make_mock_evidence(method="human_review", passed=False)
        result = _compute_requirement_coverage("R2.1", [auto, human])
        assert result.classification == FeatureClassification.PARTIAL.value
        assert result.all_passed is False

    def test_only_independent_without_automated_is_partial(self):
        """Only independent verification without automated is PARTIAL."""
        human = _make_mock_evidence(
            method="human_review", passed=True, verifier_identity="admin"
        )
        result = _compute_requirement_coverage("R2.1", [human])
        assert result.classification == FeatureClassification.PARTIAL.value
        assert result.has_automated_test is False
        assert result.has_human_review is True


# =============================================================================
# Tests: run_automated_verification
# =============================================================================


class TestRunAutomatedVerification:
    """Tests for IndependentVerificationService.run_automated_verification()."""

    @pytest.mark.asyncio
    async def test_creates_evidence_for_all_mapped_requirements(self):
        """Automated run creates evidence records for all mapped requirements."""
        db = _make_mock_db()
        service = IndependentVerificationService(db)

        mock_evidence_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid4()
        mock_instance.created_at = datetime.now(UTC)
        mock_evidence_cls.return_value = mock_instance

        with patch.dict(
            "sys.modules",
            {"app.models.verification_evidence": MagicMock(VerificationEvidence=mock_evidence_cls)},
        ):
            result = await service.run_automated_verification()

        assert result["status"] == "completed"
        assert result["total_requirements"] > 0
        assert result["evidence_records_created"] == result["total_requirements"]
        assert result["run_id"] is not None
        assert db.add.call_count == result["total_requirements"]
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_filters_by_feature_name(self):
        """Feature filter restricts which requirements are verified."""
        db = _make_mock_db()
        service = IndependentVerificationService(db)

        mock_evidence_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid4()
        mock_instance.created_at = datetime.now(UTC)
        mock_evidence_cls.return_value = mock_instance

        with patch.dict(
            "sys.modules",
            {"app.models.verification_evidence": MagicMock(VerificationEvidence=mock_evidence_cls)},
        ):
            result = await service.run_automated_verification(
                feature_name="auth_enforcement"
            )

        # Should only include auth_enforcement requirements
        assert result["total_requirements"] > 0
        assert result["feature_name"] == "auth_enforcement"

    @pytest.mark.asyncio
    async def test_records_verifier_identity(self):
        """Verifier identity is passed through to evidence records."""
        db = _make_mock_db()
        service = IndependentVerificationService(db)

        mock_evidence_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid4()
        mock_instance.created_at = datetime.now(UTC)
        mock_evidence_cls.return_value = mock_instance

        with patch.dict(
            "sys.modules",
            {"app.models.verification_evidence": MagicMock(VerificationEvidence=mock_evidence_cls)},
        ):
            result = await service.run_automated_verification(
                verifier_identity="ci_system_v2"
            )

        assert result["status"] == "completed"


# =============================================================================
# Tests: record_evidence
# =============================================================================


class TestRecordEvidence:
    """Tests for IndependentVerificationService.record_evidence()."""

    @pytest.mark.asyncio
    async def test_records_human_review_evidence(self):
        """Recording human review evidence creates correct record."""
        db = _make_mock_db()
        service = IndependentVerificationService(db)

        mock_evidence_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid4()
        mock_instance.created_at = datetime.now(UTC)
        mock_evidence_cls.return_value = mock_instance

        with patch.dict(
            "sys.modules",
            {"app.models.verification_evidence": MagicMock(VerificationEvidence=mock_evidence_cls)},
        ):
            result = await service.record_evidence(
                requirement_id="R2.14",
                feature_name="tenant_isolation",
                method=VerificationMethod.HUMAN_REVIEW,
                evidence_location="docs/VERIFICATION_SIGNOFF.md",
                evidence_type="manual_sign_off",
                passed=True,
                verifier_identity="admin@studio.ai",
                notes="Verified cross-tenant isolation manually",
            )

        assert result["requirement_id"] == "R2.14"
        assert result["feature_name"] == "tenant_isolation"
        assert result["method"] == "human_review"
        assert result["passed"] is True
        assert result["verifier_identity"] == "admin@studio.ai"
        assert result["notes"] == "Verified cross-tenant isolation manually"
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_records_hermes_inspection(self):
        """Recording Hermes inspection creates correct record."""
        db = _make_mock_db()
        service = IndependentVerificationService(db)

        mock_evidence_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid4()
        mock_instance.created_at = datetime.now(UTC)
        mock_evidence_cls.return_value = mock_instance

        with patch.dict(
            "sys.modules",
            {"app.models.verification_evidence": MagicMock(VerificationEvidence=mock_evidence_cls)},
        ):
            result = await service.record_evidence(
                requirement_id="R6.1",
                feature_name="rls_audit",
                method=VerificationMethod.HERMES_INSPECTION,
                evidence_location="hermes/inspection/rls_2025-01-15.json",
                evidence_type="hermes_report",
                passed=True,
                verifier_identity="hermes",
            )

        assert result["method"] == "hermes_inspection"
        assert result["verifier_identity"] == "hermes"

    @pytest.mark.asyncio
    async def test_records_adversarial_test(self):
        """Recording adversarial test creates correct record."""
        db = _make_mock_db()
        service = IndependentVerificationService(db)

        mock_evidence_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid4()
        mock_instance.created_at = datetime.now(UTC)
        mock_evidence_cls.return_value = mock_instance

        with patch.dict(
            "sys.modules",
            {"app.models.verification_evidence": MagicMock(VerificationEvidence=mock_evidence_cls)},
        ):
            result = await service.record_evidence(
                requirement_id="R2.13",
                feature_name="tenant_isolation",
                method=VerificationMethod.ADVERSARIAL_TEST,
                evidence_location="docs/UAT_RED_TEAM_REPORT.md",
                evidence_type="red_team_report",
                passed=True,
                verifier_identity="red_team",
            )

        assert result["method"] == "adversarial_test"
        assert result["evidence_type"] == "red_team_report"


# =============================================================================
# Tests: classify_feature
# =============================================================================


class TestClassifyFeature:
    """Tests for IndependentVerificationService.classify_feature().

    Key invariant: developer assertion alone is INSUFFICIENT for PRODUCTION.
    """

    @pytest.mark.asyncio
    async def test_no_evidence_returns_unverified(self):
        """Feature with no evidence is UNVERIFIED."""
        db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        service = IndependentVerificationService(db)

        mock_ve_module = MagicMock()
        mock_ve_module.VerificationEvidence = MagicMock()
        mock_ve_module.VerificationEvidence.feature_name = MagicMock()
        with patch.dict("sys.modules", {"app.models.verification_evidence": mock_ve_module}):
            result = await service.classify_feature("some_feature")

        assert result["classification"] == "UNVERIFIED"
        assert result["has_automated_test"] is False
        assert result["has_independent_verification"] is False

    @pytest.mark.asyncio
    async def test_only_automated_tests_returns_partial(self):
        """Feature with only automated tests is PARTIAL — NOT PRODUCTION (R82.6)."""
        db = _make_mock_db()
        auto_evidence = _make_mock_evidence(method="automated_test", passed=True)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [auto_evidence]
        db.execute.return_value = mock_result

        service = IndependentVerificationService(db)

        mock_ve_module = MagicMock()
        mock_ve_module.VerificationEvidence = MagicMock()
        mock_ve_module.VerificationEvidence.feature_name = MagicMock()
        with patch.dict("sys.modules", {"app.models.verification_evidence": mock_ve_module}):
            result = await service.classify_feature("tenant_isolation")

        assert result["classification"] == "PARTIAL"
        assert result["has_automated_test"] is True
        assert result["has_independent_verification"] is False

    @pytest.mark.asyncio
    async def test_automated_plus_human_review_returns_production(self):
        """Feature with automated + passing human review is PRODUCTION."""
        db = _make_mock_db()
        auto = _make_mock_evidence(method="automated_test", passed=True)
        human = _make_mock_evidence(
            method="human_review", passed=True, verifier_identity="admin@studio.ai"
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [auto, human]
        db.execute.return_value = mock_result

        service = IndependentVerificationService(db)

        mock_ve_module = MagicMock()
        mock_ve_module.VerificationEvidence = MagicMock()
        mock_ve_module.VerificationEvidence.feature_name = MagicMock()
        with patch.dict("sys.modules", {"app.models.verification_evidence": mock_ve_module}):
            result = await service.classify_feature("tenant_isolation")

        assert result["classification"] == "PRODUCTION"
        assert result["has_automated_test"] is True
        assert result["has_independent_verification"] is True
        assert result["all_passing"] is True

    @pytest.mark.asyncio
    async def test_failing_automated_prevents_production(self):
        """Failing automated tests prevent PRODUCTION even with independent."""
        db = _make_mock_db()
        auto = _make_mock_evidence(method="automated_test", passed=False)
        human = _make_mock_evidence(method="human_review", passed=True)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [auto, human]
        db.execute.return_value = mock_result

        service = IndependentVerificationService(db)

        mock_ve_module = MagicMock()
        mock_ve_module.VerificationEvidence = MagicMock()
        mock_ve_module.VerificationEvidence.feature_name = MagicMock()
        with patch.dict("sys.modules", {"app.models.verification_evidence": mock_ve_module}):
            result = await service.classify_feature("tenant_isolation")

        assert result["classification"] == "PARTIAL"
        assert result["all_passing"] is False

    @pytest.mark.asyncio
    async def test_developer_assertion_alone_insufficient(self):
        """Developer assertion (automated_test only) is NEVER enough for PRODUCTION.

        Validates: R82.1, R82.6 — implementation and verification must be separate.
        """
        db = _make_mock_db()
        # Multiple automated tests all passing — still not PRODUCTION
        auto1 = _make_mock_evidence(method="automated_test", passed=True)
        auto2 = _make_mock_evidence(method="automated_test", passed=True)
        auto3 = _make_mock_evidence(method="automated_test", passed=True)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [auto1, auto2, auto3]
        db.execute.return_value = mock_result

        service = IndependentVerificationService(db)

        mock_ve_module = MagicMock()
        mock_ve_module.VerificationEvidence = MagicMock()
        mock_ve_module.VerificationEvidence.feature_name = MagicMock()
        with patch.dict("sys.modules", {"app.models.verification_evidence": mock_ve_module}):
            result = await service.classify_feature("tenant_isolation")

        # Even with many passing automated tests, classification is NOT PRODUCTION
        assert result["classification"] != "PRODUCTION"
        assert result["classification"] == "PARTIAL"
        assert result["has_independent_verification"] is False


# =============================================================================
# Tests: get_evidence_for_requirement
# =============================================================================


class TestGetEvidenceForRequirement:
    """Tests for IndependentVerificationService.get_evidence_for_requirement()."""

    @pytest.mark.asyncio
    async def test_returns_paginated_results(self):
        """Returns evidence records with pagination metadata."""
        db = _make_mock_db()
        evidence1 = _make_mock_evidence(requirement_id="R2.1")
        evidence2 = _make_mock_evidence(requirement_id="R2.1", method="human_review")

        # Mock the count query
        db.scalar = AsyncMock(return_value=2)

        # Mock the list query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [evidence1, evidence2]
        db.execute.return_value = mock_result

        service = IndependentVerificationService(db)

        mock_ve_module = MagicMock()
        mock_ve_module.VerificationEvidence = MagicMock()
        mock_ve_module.VerificationEvidence.requirement_id = MagicMock()
        mock_ve_module.VerificationEvidence.verified_at = MagicMock()
        mock_ve_module.VerificationEvidence.verified_at.desc = MagicMock()

        mock_func = MagicMock()
        mock_func.count = MagicMock(return_value=MagicMock())

        with patch.dict(
            "sys.modules",
            {"app.models.verification_evidence": mock_ve_module},
        ):
            result = await service.get_evidence_for_requirement(
                requirement_id="R2.1",
                limit=20,
                offset=0,
            )

        assert result["total"] == 2
        assert result["limit"] == 20
        assert result["offset"] == 0
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_empty_results_for_unknown_requirement(self):
        """Unknown requirement returns empty list with zero total."""
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=0)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        service = IndependentVerificationService(db)

        mock_ve_module = MagicMock()
        mock_ve_module.VerificationEvidence = MagicMock()
        mock_ve_module.VerificationEvidence.requirement_id = MagicMock()
        mock_ve_module.VerificationEvidence.verified_at = MagicMock()
        mock_ve_module.VerificationEvidence.verified_at.desc = MagicMock()

        with patch.dict(
            "sys.modules",
            {"app.models.verification_evidence": mock_ve_module},
        ):
            result = await service.get_evidence_for_requirement(
                requirement_id="R999.99",
            )

        assert result["total"] == 0
        assert result["items"] == []


# =============================================================================
# Tests: get_verification_status
# =============================================================================


class TestGetVerificationStatus:
    """Tests for IndependentVerificationService.get_verification_status()."""

    @pytest.mark.asyncio
    async def test_returns_status_with_no_evidence(self):
        """With no evidence, all requirements are unverified."""
        db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        service = IndependentVerificationService(db)

        mock_ve_module = MagicMock()
        mock_ve_module.VerificationEvidence = MagicMock()
        mock_ve_module.VerificationEvidence.feature_name = MagicMock()

        with patch.dict(
            "sys.modules",
            {"app.models.verification_evidence": mock_ve_module},
        ):
            result = await service.get_verification_status()

        assert result["total_requirements"] > 0
        assert result["unverified_count"] == result["total_requirements"]
        assert result["production_ready_count"] == 0
        assert result["coverage_percentage"] == 0.0

    @pytest.mark.asyncio
    async def test_returns_status_with_mixed_evidence(self):
        """Mixed evidence produces correct counts."""
        db = _make_mock_db()
        # One requirement with both automated + human (PRODUCTION)
        auto = _make_mock_evidence(
            requirement_id="R1.1", feature_name="auth_enforcement",
            method="automated_test", passed=True
        )
        human = _make_mock_evidence(
            requirement_id="R1.1", feature_name="auth_enforcement",
            method="human_review", passed=True
        )
        # Another with only automated (PARTIAL)
        auto2 = _make_mock_evidence(
            requirement_id="R2.1", feature_name="tenant_isolation",
            method="automated_test", passed=True
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [auto, human, auto2]
        db.execute.return_value = mock_result

        service = IndependentVerificationService(db)

        mock_ve_module = MagicMock()
        mock_ve_module.VerificationEvidence = MagicMock()
        mock_ve_module.VerificationEvidence.feature_name = MagicMock()

        with patch.dict(
            "sys.modules",
            {"app.models.verification_evidence": mock_ve_module},
        ):
            result = await service.get_verification_status()

        assert result["production_ready_count"] >= 1
        assert result["partial_count"] >= 1
        assert result["coverage_percentage"] > 0.0
