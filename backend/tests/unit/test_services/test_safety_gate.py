"""Unit tests for AdultContentSafetyGate — three-layer policy evaluation.

Tests cover:
    - Safety Kernel (Layer 1): age ambiguity fails closed, NOT_VERIFIED blocked
    - Platform Policy (Layer 2): disabled blocks, rating insufficient blocks
    - Workspace Policy (Layer 3): disabled blocks, rating insufficient blocks
    - FICTIONAL: allowed when workspace permits + VERIFIED_18_PLUS
    - REAL_PERSON_SELF: requires active consent with adult_content scope
    - REAL_PERSON_AUTHORIZED: requires consent + grantor + evidence
    - Policy hierarchy: kernel overrides all, workspace cannot be more permissive

Requirements: R39.1, R39.2, R39.3, R39.4, R39.5, R39.6, R39.7, R10.11, A2-024, A2-025
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

# =============================================================================
# Mock heavy dependencies before app imports
# =============================================================================

# structlog mock
_structlog_mock = MagicMock()
_structlog_mock.get_logger = MagicMock(return_value=MagicMock())
sys.modules.setdefault("structlog", _structlog_mock)

# pydantic-settings mock
_pydantic_settings_mock = MagicMock()
_pydantic_settings_mock.BaseSettings = type("BaseSettings", (), {"model_config": {}})
sys.modules.setdefault("pydantic_settings", _pydantic_settings_mock)

# dotenv mock
sys.modules.setdefault("dotenv", MagicMock())

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
sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", MagicMock())
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", MagicMock())
sys.modules.setdefault("sqlalchemy.exc", MagicMock())

# jose + passlib
sys.modules.setdefault("jose", MagicMock())
sys.modules.setdefault("passlib", MagicMock())
sys.modules.setdefault("passlib.context", MagicMock())

# Mock app.db
_mock_db_mod = ModuleType("app.db")
sys.modules.setdefault("app.db", _mock_db_mod)
_mock_db_session = ModuleType("app.db.session")
_mock_db_session.get_db_session = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.session", _mock_db_session)

# Now import the modules under test
from app.schemas.safety import (
    AdultStatus,
    ConsentContext,
    ContentRating,
    IdentityClassification,
    PlatformPolicy,
    PolicyLayer,
    SafetyDecision,
    TalentSafetyContext,
    WorkspacePolicy,
)
from app.services.safety_gate import AdultContentSafetyGate


# =============================================================================
# Helpers
# =============================================================================

TALENT_ID = uuid4()


def _make_talent(
    identity: IdentityClassification = IdentityClassification.FICTIONAL,
    adult_status: AdultStatus = AdultStatus.VERIFIED_18_PLUS,
) -> TalentSafetyContext:
    """Create a TalentSafetyContext for testing."""
    return TalentSafetyContext(
        talent_id=TALENT_ID,
        identity_classification=identity,
        adult_status=adult_status,
    )


def _make_consent(
    has_scope: bool = True,
    is_active: bool = True,
    grantor_identity: str | None = "John Doe (Manager)",
    evidence_exists: bool = True,
) -> ConsentContext:
    """Create a ConsentContext for testing."""
    return ConsentContext(
        has_adult_content_scope=has_scope,
        grantor_identity=grantor_identity,
        evidence_exists=evidence_exists,
        is_active=is_active,
    )


def _adult_platform_policy() -> PlatformPolicy:
    """Platform policy that allows adult content."""
    return PlatformPolicy(
        allowed_content_rating=ContentRating.ADULT,
        adult_content_enabled=True,
    )


def _adult_workspace_policy() -> WorkspacePolicy:
    """Workspace policy that allows adult content."""
    return WorkspacePolicy(
        allowed_content_rating=ContentRating.ADULT,
        adult_content_enabled=True,
    )


def _gate(
    platform: PlatformPolicy | None = None,
    workspace: WorkspacePolicy | None = None,
) -> AdultContentSafetyGate:
    """Create an AdultContentSafetyGate with default permissive policies."""
    return AdultContentSafetyGate(
        platform_policy=platform or _adult_platform_policy(),
        workspace_policy=workspace or _adult_workspace_policy(),
    )


# =============================================================================
# Tests: Safety Kernel (Layer 1 — MANDATORY, non-disableable)
# =============================================================================


@pytest.mark.unit
class TestSafetyKernel:
    """Layer 1: Safety Kernel tests — these rules cannot be overridden."""

    def test_age_ambiguity_fails_closed(self):
        """A2-024: Age ambiguity blocks adult content regardless of policies."""
        gate = _gate()
        talent = _make_talent(adult_status=AdultStatus.AMBIGUOUS)
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.SAFETY_KERNEL
        assert "ambiguous" in result.reason.lower()
        assert result.details["condition"] == "age_ambiguity_fail_closed"

    def test_not_verified_adult_status_blocked(self):
        """R10.11: NOT_VERIFIED adult status blocks adult content."""
        gate = _gate()
        talent = _make_talent(adult_status=AdultStatus.NOT_VERIFIED)
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.SAFETY_KERNEL
        assert "VERIFIED_18_PLUS" in result.reason
        assert result.details["condition"] == "adult_status_not_verified"

    def test_kernel_blocks_even_with_all_policies_permissive(self):
        """Safety kernel is non-disableable — blocks even with permissive policies."""
        gate = _gate()
        talent = _make_talent(adult_status=AdultStatus.AMBIGUOUS)
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        # Even though platform + workspace both allow adult content,
        # the safety kernel blocks because age is ambiguous
        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.SAFETY_KERNEL

    def test_verified_18_plus_passes_kernel(self):
        """VERIFIED_18_PLUS passes the safety kernel layer."""
        gate = _gate()
        talent = _make_talent(adult_status=AdultStatus.VERIFIED_18_PLUS)
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        # Should NOT be blocked at kernel layer (may be allowed or blocked at workspace)
        assert result.policy_layer != PolicyLayer.SAFETY_KERNEL or result.is_allowed

    def test_talent_id_included_in_result(self):
        """Result includes the talent_id for correlation."""
        gate = _gate()
        talent = _make_talent(adult_status=AdultStatus.AMBIGUOUS)
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        assert result.talent_id == TALENT_ID


# =============================================================================
# Tests: Platform Policy (Layer 2)
# =============================================================================


@pytest.mark.unit
class TestPlatformPolicy:
    """Layer 2: Platform Policy tests — operator-level configuration."""

    def test_platform_adult_content_disabled_blocks(self):
        """Platform with adult_content_enabled=False blocks adult content."""
        platform = PlatformPolicy(
            allowed_content_rating=ContentRating.SFW_ONLY,
            adult_content_enabled=False,
        )
        gate = _gate(platform=platform)
        talent = _make_talent()
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.PLATFORM_POLICY
        assert "platform" in result.reason.lower()
        assert result.details["condition"] == "platform_adult_content_disabled"

    def test_platform_mature_rating_blocks_adult(self):
        """Platform with MATURE rating blocks adult content (not permissive enough)."""
        platform = PlatformPolicy(
            allowed_content_rating=ContentRating.MATURE,
            adult_content_enabled=True,
        )
        gate = _gate(platform=platform)
        talent = _make_talent()
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.PLATFORM_POLICY
        assert result.details["condition"] == "platform_rating_insufficient"

    def test_platform_sfw_only_rating_blocks_adult(self):
        """Platform with SFW_ONLY rating blocks adult content."""
        platform = PlatformPolicy(
            allowed_content_rating=ContentRating.SFW_ONLY,
            adult_content_enabled=True,
        )
        gate = _gate(platform=platform)
        talent = _make_talent()
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.PLATFORM_POLICY

    def test_platform_adult_rating_and_enabled_passes(self):
        """Platform with ADULT rating + enabled passes to workspace layer."""
        platform = _adult_platform_policy()
        workspace = _adult_workspace_policy()
        gate = _gate(platform=platform, workspace=workspace)
        talent = _make_talent()
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        # Should proceed past platform policy (either allowed or blocked at workspace)
        assert result.policy_layer != PolicyLayer.PLATFORM_POLICY


# =============================================================================
# Tests: Workspace Policy (Layer 3)
# =============================================================================


@pytest.mark.unit
class TestWorkspacePolicy:
    """Layer 3: Workspace Policy tests — can only be stricter."""

    def test_workspace_adult_content_disabled_blocks(self):
        """Workspace with adult_content_enabled=False blocks adult content."""
        workspace = WorkspacePolicy(
            allowed_content_rating=ContentRating.SFW_ONLY,
            adult_content_enabled=False,
        )
        gate = _gate(workspace=workspace)
        talent = _make_talent()
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.WORKSPACE_POLICY
        assert "workspace" in result.reason.lower()
        assert result.details["condition"] == "workspace_adult_content_disabled"

    def test_workspace_mature_rating_blocks_adult(self):
        """Workspace with MATURE rating blocks adult content."""
        workspace = WorkspacePolicy(
            allowed_content_rating=ContentRating.MATURE,
            adult_content_enabled=True,
        )
        gate = _gate(workspace=workspace)
        talent = _make_talent()
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.WORKSPACE_POLICY
        assert result.details["condition"] == "workspace_rating_insufficient"


# =============================================================================
# Tests: FICTIONAL identity (R39.6 case a)
# =============================================================================


@pytest.mark.unit
class TestFictionalIdentity:
    """FICTIONAL: workspace allows + adult_status verified → allowed."""

    def test_fictional_verified_allowed(self):
        """Fictional talent with VERIFIED_18_PLUS and permissive policies → allowed."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.FICTIONAL,
            adult_status=AdultStatus.VERIFIED_18_PLUS,
        )
        consent = ConsentContext()  # No consent required for fictional

        result = gate.evaluate(talent, consent)

        assert result.is_allowed
        assert result.policy_layer == PolicyLayer.WORKSPACE_POLICY
        assert result.details["identity_classification"] == "FICTIONAL"

    def test_fictional_no_consent_required(self):
        """Fictional talent does not require consent for adult content."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.FICTIONAL,
            adult_status=AdultStatus.VERIFIED_18_PLUS,
        )
        # Empty consent — no scope, no grantor, no evidence
        consent = ConsentContext(
            has_adult_content_scope=False,
            is_active=False,
        )

        result = gate.evaluate(talent, consent)

        # Still allowed — consent not required for fictional
        assert result.is_allowed

    def test_fictional_not_verified_blocked_at_kernel(self):
        """Fictional talent without VERIFIED_18_PLUS is blocked at kernel."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.FICTIONAL,
            adult_status=AdultStatus.NOT_VERIFIED,
        )
        consent = ConsentContext()

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.SAFETY_KERNEL


# =============================================================================
# Tests: REAL_PERSON_SELF identity (R39.6 case b)
# =============================================================================


@pytest.mark.unit
class TestRealPersonSelf:
    """REAL_PERSON_SELF: workspace allows + verified + active consent scope."""

    def test_real_person_self_with_active_consent_allowed(self):
        """Real person (self) with all conditions met → allowed."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.REAL_PERSON_SELF,
            adult_status=AdultStatus.VERIFIED_18_PLUS,
        )
        consent = _make_consent(
            has_scope=True,
            is_active=True,
        )

        result = gate.evaluate(talent, consent)

        assert result.is_allowed
        assert result.details["identity_classification"] == "REAL_PERSON_SELF"
        assert result.details["consent_active"] is True

    def test_real_person_self_missing_consent_scope_blocked(self):
        """Real person (self) without adult_content consent scope → blocked."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.REAL_PERSON_SELF,
            adult_status=AdultStatus.VERIFIED_18_PLUS,
        )
        consent = _make_consent(has_scope=False, is_active=True)

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.WORKSPACE_POLICY
        assert result.details["condition"] == "missing_adult_content_consent"

    def test_real_person_self_inactive_consent_blocked(self):
        """Real person (self) with revoked/expired consent → blocked."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.REAL_PERSON_SELF,
            adult_status=AdultStatus.VERIFIED_18_PLUS,
        )
        consent = _make_consent(has_scope=True, is_active=False)

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.WORKSPACE_POLICY
        assert result.details["condition"] == "consent_not_active"

    def test_real_person_self_not_verified_blocked_at_kernel(self):
        """Real person (self) without VERIFIED_18_PLUS → blocked at kernel."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.REAL_PERSON_SELF,
            adult_status=AdultStatus.NOT_VERIFIED,
        )
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.SAFETY_KERNEL


# =============================================================================
# Tests: REAL_PERSON_AUTHORIZED identity (R39.6 case c)
# =============================================================================


@pytest.mark.unit
class TestRealPersonAuthorized:
    """REAL_PERSON_AUTHORIZED: consent + grantor + evidence required."""

    def test_authorized_with_full_consent_allowed(self):
        """Real person (authorized) with all requirements met → allowed."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.REAL_PERSON_AUTHORIZED,
            adult_status=AdultStatus.VERIFIED_18_PLUS,
        )
        consent = _make_consent(
            has_scope=True,
            is_active=True,
            grantor_identity="Jane Agent, Legal Representative",
            evidence_exists=True,
        )

        result = gate.evaluate(talent, consent)

        assert result.is_allowed
        assert result.details["identity_classification"] == "REAL_PERSON_AUTHORIZED"
        assert result.details["has_grantor_identity"] is True
        assert result.details["has_evidence"] is True

    def test_authorized_missing_consent_scope_blocked(self):
        """Real person (authorized) without consent scope → blocked."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.REAL_PERSON_AUTHORIZED,
            adult_status=AdultStatus.VERIFIED_18_PLUS,
        )
        consent = _make_consent(has_scope=False)

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.details["condition"] == "missing_adult_content_consent"

    def test_authorized_inactive_consent_blocked(self):
        """Real person (authorized) with inactive consent → blocked."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.REAL_PERSON_AUTHORIZED,
            adult_status=AdultStatus.VERIFIED_18_PLUS,
        )
        consent = _make_consent(has_scope=True, is_active=False)

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.details["condition"] == "consent_not_active"

    def test_authorized_missing_grantor_identity_blocked(self):
        """Real person (authorized) without grantor identity → blocked."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.REAL_PERSON_AUTHORIZED,
            adult_status=AdultStatus.VERIFIED_18_PLUS,
        )
        consent = _make_consent(
            has_scope=True,
            is_active=True,
            grantor_identity=None,  # Missing!
            evidence_exists=True,
        )

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.details["condition"] == "missing_grantor_identity"

    def test_authorized_missing_evidence_blocked(self):
        """Real person (authorized) without evidence → blocked."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.REAL_PERSON_AUTHORIZED,
            adult_status=AdultStatus.VERIFIED_18_PLUS,
        )
        consent = _make_consent(
            has_scope=True,
            is_active=True,
            grantor_identity="Valid Grantor",
            evidence_exists=False,  # Missing!
        )

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.details["condition"] == "missing_evidence"

    def test_authorized_empty_grantor_string_blocked(self):
        """Real person (authorized) with empty string grantor → blocked."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.REAL_PERSON_AUTHORIZED,
            adult_status=AdultStatus.VERIFIED_18_PLUS,
        )
        consent = _make_consent(
            has_scope=True,
            is_active=True,
            grantor_identity="",  # Empty string is falsy
            evidence_exists=True,
        )

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.details["condition"] == "missing_grantor_identity"


# =============================================================================
# Tests: Policy Hierarchy and Precedence
# =============================================================================


@pytest.mark.unit
class TestPolicyHierarchy:
    """Verify the three-layer hierarchy behaves correctly."""

    def test_kernel_takes_priority_over_platform_and_workspace(self):
        """Safety kernel blocks even when platform + workspace both allow."""
        gate = _gate()
        talent = _make_talent(adult_status=AdultStatus.AMBIGUOUS)
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.SAFETY_KERNEL

    def test_platform_blocks_before_workspace_evaluated(self):
        """Platform policy blocks before workspace layer runs."""
        platform = PlatformPolicy(
            allowed_content_rating=ContentRating.SFW_ONLY,
            adult_content_enabled=False,
        )
        workspace = _adult_workspace_policy()  # Would allow
        gate = _gate(platform=platform, workspace=workspace)
        talent = _make_talent()
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.PLATFORM_POLICY

    def test_workspace_stricter_than_platform_blocks(self):
        """Workspace is stricter than platform → blocks at workspace layer."""
        platform = _adult_platform_policy()  # Platform allows
        workspace = WorkspacePolicy(
            allowed_content_rating=ContentRating.SFW_ONLY,
            adult_content_enabled=False,
        )
        gate = _gate(platform=platform, workspace=workspace)
        talent = _make_talent()
        consent = _make_consent()

        result = gate.evaluate(talent, consent)

        assert result.is_blocked
        assert result.policy_layer == PolicyLayer.WORKSPACE_POLICY

    def test_all_layers_pass_for_valid_fictional(self):
        """All three layers pass for a valid fictional talent."""
        gate = _gate()
        talent = _make_talent(
            identity=IdentityClassification.FICTIONAL,
            adult_status=AdultStatus.VERIFIED_18_PLUS,
        )
        consent = ConsentContext()

        result = gate.evaluate(talent, consent)

        assert result.is_allowed


# =============================================================================
# Tests: SafetyEvaluationResult properties
# =============================================================================


@pytest.mark.unit
class TestSafetyEvaluationResult:
    """Test the result dataclass convenience properties."""

    def test_is_allowed_property(self):
        """is_allowed returns True for ALLOWED decision."""
        from app.schemas.safety import SafetyEvaluationResult

        result = SafetyEvaluationResult(
            decision=SafetyDecision.ALLOWED,
            policy_layer=PolicyLayer.WORKSPACE_POLICY,
            reason="Test",
        )
        assert result.is_allowed is True
        assert result.is_blocked is False

    def test_is_blocked_property(self):
        """is_blocked returns True for BLOCKED decision."""
        from app.schemas.safety import SafetyEvaluationResult

        result = SafetyEvaluationResult(
            decision=SafetyDecision.BLOCKED,
            policy_layer=PolicyLayer.SAFETY_KERNEL,
            reason="Test block",
        )
        assert result.is_blocked is True
        assert result.is_allowed is False

    def test_default_details_empty_dict(self):
        """Default details is an empty dict."""
        from app.schemas.safety import SafetyEvaluationResult

        result = SafetyEvaluationResult(
            decision=SafetyDecision.ALLOWED,
            policy_layer=PolicyLayer.WORKSPACE_POLICY,
            reason="Test",
        )
        assert result.details == {}

    def test_default_talent_id_none(self):
        """Default talent_id is None."""
        from app.schemas.safety import SafetyEvaluationResult

        result = SafetyEvaluationResult(
            decision=SafetyDecision.ALLOWED,
            policy_layer=PolicyLayer.WORKSPACE_POLICY,
            reason="Test",
        )
        assert result.talent_id is None


# =============================================================================
# Tests: Edge cases
# =============================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_consent_context_defaults(self):
        """ConsentContext defaults are all falsy/None."""
        consent = ConsentContext()
        assert consent.has_adult_content_scope is False
        assert consent.grantor_identity is None
        assert consent.evidence_exists is False
        assert consent.is_active is False

    def test_platform_policy_defaults(self):
        """PlatformPolicy defaults to SFW_ONLY and disabled."""
        policy = PlatformPolicy()
        assert policy.allowed_content_rating == ContentRating.SFW_ONLY
        assert policy.adult_content_enabled is False
        assert policy.prohibited_categories == []

    def test_workspace_policy_defaults(self):
        """WorkspacePolicy defaults to SFW_ONLY and disabled."""
        policy = WorkspacePolicy()
        assert policy.allowed_content_rating == ContentRating.SFW_ONLY
        assert policy.adult_content_enabled is False

    def test_all_identity_classifications_evaluated(self):
        """All three identity classifications produce a result without error."""
        gate = _gate()
        consent = _make_consent()

        for classification in IdentityClassification:
            talent = _make_talent(
                identity=classification,
                adult_status=AdultStatus.VERIFIED_18_PLUS,
            )
            result = gate.evaluate(talent, consent)
            assert result.decision in (SafetyDecision.ALLOWED, SafetyDecision.BLOCKED)

    def test_all_adult_statuses_evaluated(self):
        """All adult status values produce a result without error."""
        gate = _gate()
        consent = _make_consent()

        for status in AdultStatus:
            talent = _make_talent(
                identity=IdentityClassification.FICTIONAL,
                adult_status=status,
            )
            result = gate.evaluate(talent, consent)
            assert result.decision in (SafetyDecision.ALLOWED, SafetyDecision.BLOCKED)

    def test_only_verified_18_plus_allowed_through_kernel(self):
        """Only VERIFIED_18_PLUS passes the safety kernel; others are blocked."""
        gate = _gate()
        consent = _make_consent()

        blocked_statuses = [AdultStatus.NOT_VERIFIED, AdultStatus.AMBIGUOUS]
        for status in blocked_statuses:
            talent = _make_talent(adult_status=status)
            result = gate.evaluate(talent, consent)
            assert result.is_blocked
            assert result.policy_layer == PolicyLayer.SAFETY_KERNEL
