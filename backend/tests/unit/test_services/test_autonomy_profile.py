"""Unit tests for workspace autonomy profile service.

Tests:
- AutonomyProfileService: profile get/set, default behavior
- Action evaluation: ADVISORY, ASSISTED, AUTONOMOUS_WITHIN_LIMITS
- Mandatory controls: always enforced regardless of profile
- Destructive actions: always require approval

No I/O, no DB — all tested in-memory.

Validates: Requirements R98.1, R98.2, R30.12, R30.13
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.autonomy_profile_service import (
    ActionEvaluation,
    ActionRisk,
    AutonomyLevel,
    AutonomyProfile,
    AutonomyProfileService,
    MANDATORY_APPROVAL_ACTIONS,
    MANDATORY_CONTROLS,
)


# =============================================================================
# Helpers
# =============================================================================

ORG_ID = uuid4()
USER_ID = uuid4()


# =============================================================================
# Tests — AutonomyProfileService: Profile Get/Set
# =============================================================================


@pytest.mark.unit
class TestAutonomyProfileServiceConfig:
    """Tests for AutonomyProfileService profile management (in-memory mode)."""

    @pytest.mark.asyncio
    async def test_get_profile_returns_advisory_default(self) -> None:
        """Service returns ADVISORY with mandatory controls by default."""
        service = AutonomyProfileService()
        profile = await service.get_profile(org_id=ORG_ID)

        assert profile.org_id == ORG_ID
        assert profile.autonomy_level == AutonomyLevel.ADVISORY
        assert profile.mandatory_controls == MANDATORY_CONTROLS

    @pytest.mark.asyncio
    async def test_get_profile_returns_in_memory_profile(self) -> None:
        """Service returns the in-memory profile when provided."""
        custom_profile = AutonomyProfile(
            org_id=ORG_ID,
            autonomy_level=AutonomyLevel.ASSISTED,
        )
        service = AutonomyProfileService(profile=custom_profile)
        profile = await service.get_profile(org_id=ORG_ID)

        assert profile.autonomy_level == AutonomyLevel.ASSISTED

    @pytest.mark.asyncio
    async def test_set_profile_updates_in_memory(self) -> None:
        """Service updates in-memory profile correctly."""
        initial = AutonomyProfile(org_id=ORG_ID)
        service = AutonomyProfileService(profile=initial)

        result = await service.set_profile(
            org_id=ORG_ID,
            autonomy_level=AutonomyLevel.AUTONOMOUS_WITHIN_LIMITS,
            updated_by=USER_ID,
        )

        assert result.autonomy_level == AutonomyLevel.AUTONOMOUS_WITHIN_LIMITS
        # Mandatory controls preserved
        assert result.mandatory_controls == MANDATORY_CONTROLS

        # Verify persistence
        profile = await service.get_profile(org_id=ORG_ID)
        assert profile.autonomy_level == AutonomyLevel.AUTONOMOUS_WITHIN_LIMITS

    @pytest.mark.asyncio
    async def test_set_profile_preserves_mandatory_controls(self) -> None:
        """Mandatory controls cannot be overridden by set_profile."""
        service = AutonomyProfileService(profile=AutonomyProfile(org_id=ORG_ID))

        result = await service.set_profile(
            org_id=ORG_ID,
            autonomy_level=AutonomyLevel.AUTONOMOUS_WITHIN_LIMITS,
            updated_by=USER_ID,
        )

        assert result.mandatory_controls["safety_kernel"] is True
        assert result.mandatory_controls["security_sensitive"] is True
        assert result.mandatory_controls["consent_verification"] is True
        assert result.mandatory_controls["budget_exceeding"] is True
        assert result.mandatory_controls["destructive_operations"] is True


# =============================================================================
# Tests — Action Evaluation: ADVISORY Mode
# =============================================================================


@pytest.mark.unit
class TestAdvisoryModeEvaluation:
    """Tests for action evaluation in ADVISORY mode (recommend only)."""

    def setup_method(self) -> None:
        self.profile = AutonomyProfile(
            org_id=ORG_ID,
            autonomy_level=AutonomyLevel.ADVISORY,
        )
        self.service = AutonomyProfileService(profile=self.profile)

    def test_advisory_allows_read_operations(self) -> None:
        """ADVISORY mode allows read operations without approval."""
        result = self.service.evaluate_action(
            self.profile,
            action="get_talent_list",
            risk=ActionRisk.READ,
        )

        assert result.allowed is True
        assert result.requires_approval is False

    def test_advisory_blocks_low_risk_mutations(self) -> None:
        """ADVISORY mode blocks even low-risk mutations."""
        result = self.service.evaluate_action(
            self.profile,
            action="update_preference",
            risk=ActionRisk.LOW_RISK_MUTATE,
        )

        assert result.allowed is False
        assert result.requires_approval is True
        assert "ADVISORY" in result.reason

    def test_advisory_blocks_high_risk_mutations(self) -> None:
        """ADVISORY mode blocks high-risk mutations."""
        result = self.service.evaluate_action(
            self.profile,
            action="generate_image",
            risk=ActionRisk.HIGH_RISK_MUTATE,
        )

        assert result.allowed is False
        assert result.requires_approval is True


# =============================================================================
# Tests — Action Evaluation: ASSISTED Mode
# =============================================================================


@pytest.mark.unit
class TestAssistedModeEvaluation:
    """Tests for action evaluation in ASSISTED mode (low-risk auto-execute)."""

    def setup_method(self) -> None:
        self.profile = AutonomyProfile(
            org_id=ORG_ID,
            autonomy_level=AutonomyLevel.ASSISTED,
        )
        self.service = AutonomyProfileService(profile=self.profile)

    def test_assisted_allows_read_operations(self) -> None:
        """ASSISTED mode allows read operations."""
        result = self.service.evaluate_action(
            self.profile,
            action="search_knowledge",
            risk=ActionRisk.READ,
        )

        assert result.allowed is True
        assert result.requires_approval is False

    def test_assisted_allows_low_risk_mutations(self) -> None:
        """ASSISTED mode auto-executes low-risk mutations."""
        result = self.service.evaluate_action(
            self.profile,
            action="update_preference",
            risk=ActionRisk.LOW_RISK_MUTATE,
        )

        assert result.allowed is True
        assert result.requires_approval is False

    def test_assisted_blocks_high_risk_mutations(self) -> None:
        """ASSISTED mode requires confirmation for high-risk mutations."""
        result = self.service.evaluate_action(
            self.profile,
            action="generate_image",
            risk=ActionRisk.HIGH_RISK_MUTATE,
        )

        assert result.allowed is False
        assert result.requires_approval is True
        assert "ASSISTED" in result.reason


# =============================================================================
# Tests — Action Evaluation: AUTONOMOUS_WITHIN_LIMITS Mode
# =============================================================================


@pytest.mark.unit
class TestAutonomousWithinLimitsEvaluation:
    """Tests for AUTONOMOUS_WITHIN_LIMITS mode (delegated within limits)."""

    def setup_method(self) -> None:
        self.profile = AutonomyProfile(
            org_id=ORG_ID,
            autonomy_level=AutonomyLevel.AUTONOMOUS_WITHIN_LIMITS,
        )
        self.service = AutonomyProfileService(profile=self.profile)

    def test_autonomous_allows_read_operations(self) -> None:
        """AUTONOMOUS mode allows read operations."""
        result = self.service.evaluate_action(
            self.profile,
            action="get_talent_list",
            risk=ActionRisk.READ,
        )

        assert result.allowed is True

    def test_autonomous_allows_low_risk_mutations(self) -> None:
        """AUTONOMOUS mode auto-executes low-risk mutations."""
        result = self.service.evaluate_action(
            self.profile,
            action="update_preference",
            risk=ActionRisk.LOW_RISK_MUTATE,
        )

        assert result.allowed is True

    def test_autonomous_allows_high_risk_mutations(self) -> None:
        """AUTONOMOUS mode auto-executes high-risk mutations within limits."""
        result = self.service.evaluate_action(
            self.profile,
            action="generate_image",
            risk=ActionRisk.HIGH_RISK_MUTATE,
        )

        assert result.allowed is True
        assert "AUTONOMOUS_WITHIN_LIMITS" in result.reason


# =============================================================================
# Tests — Mandatory Controls (always enforced regardless of profile)
# =============================================================================


@pytest.mark.unit
class TestMandatoryControlEnforcement:
    """Tests for mandatory controls that override all autonomy levels.

    Safety/security/consent/budget/destructive controls are enforced
    regardless of whether the profile is ADVISORY, ASSISTED, or
    AUTONOMOUS_WITHIN_LIMITS.

    Validates: R30.13
    """

    def setup_method(self) -> None:
        # Use the most permissive profile to prove mandatory controls override it
        self.profile = AutonomyProfile(
            org_id=ORG_ID,
            autonomy_level=AutonomyLevel.AUTONOMOUS_WITHIN_LIMITS,
        )
        self.service = AutonomyProfileService(profile=self.profile)

    def test_destructive_actions_always_require_approval(self) -> None:
        """Destructive risk actions always require approval."""
        result = self.service.evaluate_action(
            self.profile,
            action="any_action",
            risk=ActionRisk.DESTRUCTIVE,
        )

        assert result.allowed is False
        assert result.requires_approval is True
        assert result.mandatory_control_triggered == "destructive_operations"

    def test_delete_permanent_always_blocked(self) -> None:
        """delete_permanent is always blocked by mandatory controls."""
        result = self.service.evaluate_action(
            self.profile,
            action="delete_permanent",
            risk=ActionRisk.LOW_RISK_MUTATE,
        )

        assert result.allowed is False
        assert result.requires_approval is True
        assert result.mandatory_control_triggered == "mandatory_approval_action"

    def test_publish_to_social_always_blocked(self) -> None:
        """publish_to_social always requires approval."""
        result = self.service.evaluate_action(
            self.profile,
            action="publish_to_social",
            risk=ActionRisk.LOW_RISK_MUTATE,
        )

        assert result.allowed is False
        assert result.requires_approval is True

    def test_clone_voice_always_blocked(self) -> None:
        """clone_voice always requires approval."""
        result = self.service.evaluate_action(
            self.profile,
            action="clone_voice",
            risk=ActionRisk.LOW_RISK_MUTATE,
        )

        assert result.allowed is False
        assert result.requires_approval is True

    def test_spend_above_threshold_always_blocked(self) -> None:
        """spend_above_threshold always requires approval."""
        result = self.service.evaluate_action(
            self.profile,
            action="spend_above_threshold",
            risk=ActionRisk.LOW_RISK_MUTATE,
        )

        assert result.allowed is False
        assert result.requires_approval is True

    def test_force_delete_always_blocked(self) -> None:
        """force_delete always requires approval."""
        result = self.service.evaluate_action(
            self.profile,
            action="force_delete",
            risk=ActionRisk.LOW_RISK_MUTATE,
        )

        assert result.allowed is False
        assert result.requires_approval is True

    def test_modify_safety_policy_always_blocked(self) -> None:
        """modify_safety_policy always requires approval."""
        result = self.service.evaluate_action(
            self.profile,
            action="modify_safety_policy",
            risk=ActionRisk.LOW_RISK_MUTATE,
        )

        assert result.allowed is False
        assert result.requires_approval is True

    def test_all_mandatory_actions_are_blocked_in_autonomous_mode(self) -> None:
        """Every action in MANDATORY_APPROVAL_ACTIONS is blocked even in AUTONOMOUS mode."""
        for action in MANDATORY_APPROVAL_ACTIONS:
            result = self.service.evaluate_action(
                self.profile,
                action=action,
                risk=ActionRisk.LOW_RISK_MUTATE,
            )
            assert result.allowed is False, f"Action '{action}' should be blocked"
            assert result.requires_approval is True, f"Action '{action}' should require approval"


# =============================================================================
# Tests — Default Behavior
# =============================================================================


@pytest.mark.unit
class TestDefaultBehavior:
    """Tests for default autonomy profile behavior."""

    def test_default_profile_is_advisory(self) -> None:
        """New workspaces default to ADVISORY mode."""
        profile = AutonomyProfile(org_id=ORG_ID)

        assert profile.autonomy_level == AutonomyLevel.ADVISORY

    def test_mandatory_controls_default_all_true(self) -> None:
        """All mandatory controls are enabled by default."""
        profile = AutonomyProfile(org_id=ORG_ID)

        for control_name, enabled in profile.mandatory_controls.items():
            assert enabled is True, f"Control '{control_name}' should be True"

    def test_enum_values_are_correct(self) -> None:
        """AutonomyLevel enum values match expected strings."""
        assert AutonomyLevel.ADVISORY.value == "advisory"
        assert AutonomyLevel.ASSISTED.value == "assisted"
        assert AutonomyLevel.AUTONOMOUS_WITHIN_LIMITS.value == "autonomous_within_limits"

    def test_action_risk_enum_values(self) -> None:
        """ActionRisk enum values match expected strings."""
        assert ActionRisk.READ.value == "read"
        assert ActionRisk.LOW_RISK_MUTATE.value == "low_risk_mutate"
        assert ActionRisk.HIGH_RISK_MUTATE.value == "high_risk_mutate"
        assert ActionRisk.DESTRUCTIVE.value == "destructive"
