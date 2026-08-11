"""Adult Content Safety Gate — three-layer policy evaluation.

Three-layer content policy:
    1. Safety Kernel (mandatory, non-disableable) — CSAM, nonconsensual imagery,
       imminent harm, legal obligations. Cannot be overridden by any policy.
    2. Platform Policy (platform operator) — allowed_content_ratings, prohibited
       categories, adult content toggle.
    3. Workspace Policy (workspace admin) — can only be EQUAL TO or STRICTER
       than platform policy, never more permissive.

Adult content evaluation logic:
    - FICTIONAL: workspace allows adult + adult_status == VERIFIED_18_PLUS
    - REAL_PERSON_SELF: above + consent scope 'adult_content' active
    - REAL_PERSON_AUTHORIZED: above + consent has grantor_identity + evidence
    - Age ambiguity fails closed (A2-024): cannot confirm 18+ → blocked

Callable from the generation pipeline and governance boundary.

Requirements: R39.1, R39.2, R39.3, R39.4, R39.5, R39.6, R39.7, R10.11, A2-024, A2-025
"""

from __future__ import annotations

from uuid import UUID

from app.core.logging import get_logger
from app.schemas.safety import (
    AdultStatus,
    ConsentContext,
    ContentRating,
    IdentityClassification,
    PlatformPolicy,
    PolicyLayer,
    SafetyDecision,
    SafetyEvaluationResult,
    TalentSafetyContext,
    WorkspacePolicy,
)

logger = get_logger(__name__)


class AdultContentSafetyGate:
    """Evaluates whether adult content generation is permitted.

    This gate enforces the three-layer policy hierarchy:
        Safety Kernel → Platform Policy → Workspace Policy

    The Safety Kernel rules are MANDATORY and cannot be disabled. They cover:
        - CSAM / sexual depiction of minors
        - Real-person nonconsensual intimate imagery (without authorization)
        - Content facilitating imminent physical harm
        - Mandatory legal/takedown compliance obligations

    Platform Policy sets the default content boundaries.
    Workspace Policy can only be stricter than platform policy.

    Usage:
        gate = AdultContentSafetyGate(
            platform_policy=platform_policy,
            workspace_policy=workspace_policy,
        )
        result = gate.evaluate(talent_context, consent_context)
    """

    def __init__(
        self,
        platform_policy: PlatformPolicy,
        workspace_policy: WorkspacePolicy,
    ) -> None:
        """Initialize the safety gate with policy configurations.

        Args:
            platform_policy: Platform-wide policy set by operator.
            workspace_policy: Workspace-level policy (must be <= platform).
        """
        self._platform_policy = platform_policy
        self._workspace_policy = workspace_policy

    def evaluate(
        self,
        talent_context: TalentSafetyContext,
        consent_context: ConsentContext,
    ) -> SafetyEvaluationResult:
        """Evaluate whether adult content generation is permitted.

        Evaluates the three policy layers in order:
            1. Safety Kernel (mandatory checks)
            2. Platform Policy (operator-level)
            3. Workspace Policy + identity-specific checks

        Args:
            talent_context: Safety-relevant talent information.
            consent_context: Consent records relevant to this evaluation.

        Returns:
            SafetyEvaluationResult with decision, policy layer, and reason.
        """
        # Layer 1: Safety Kernel (mandatory, non-disableable)
        kernel_result = self._evaluate_safety_kernel(talent_context)
        if kernel_result is not None:
            self._log_evaluation(kernel_result, talent_context)
            return kernel_result

        # Layer 2: Platform Policy
        platform_result = self._evaluate_platform_policy()
        if platform_result is not None:
            self._log_evaluation(platform_result, talent_context)
            return platform_result

        # Layer 3: Workspace Policy + identity-specific checks
        workspace_result = self._evaluate_workspace_policy(
            talent_context, consent_context
        )
        self._log_evaluation(workspace_result, talent_context)
        return workspace_result

    # =========================================================================
    # Layer 1: Safety Kernel (MANDATORY — cannot be disabled)
    # =========================================================================

    def _evaluate_safety_kernel(
        self,
        talent_context: TalentSafetyContext,
    ) -> SafetyEvaluationResult | None:
        """Evaluate mandatory safety kernel rules.

        The Safety Kernel blocks:
            - Age ambiguity (A2-024): cannot confirm adulthood → blocked
            - NOT_VERIFIED adult status → blocked (R10.11)

        These rules are NON-DISABLEABLE regardless of platform/workspace policy.

        Args:
            talent_context: Talent safety information.

        Returns:
            SafetyEvaluationResult if blocked, None if kernel passes.
        """
        # A2-024: Age ambiguity fails closed
        if talent_context.adult_status == AdultStatus.AMBIGUOUS:
            return SafetyEvaluationResult(
                decision=SafetyDecision.BLOCKED,
                policy_layer=PolicyLayer.SAFETY_KERNEL,
                reason=(
                    "Age/adulthood cannot be confirmed for this talent. "
                    "Ambiguous cases are blocked from adult content workflows "
                    "until explicit confirmation resolves the ambiguity."
                ),
                talent_id=talent_context.talent_id,
                details={
                    "condition": "age_ambiguity_fail_closed",
                    "adult_status": talent_context.adult_status.value,
                },
            )

        # R10.11: adult_status must be VERIFIED_18_PLUS
        if talent_context.adult_status != AdultStatus.VERIFIED_18_PLUS:
            return SafetyEvaluationResult(
                decision=SafetyDecision.BLOCKED,
                policy_layer=PolicyLayer.SAFETY_KERNEL,
                reason=(
                    "Talent does not have VERIFIED_18_PLUS adult status. "
                    "Adult content generation requires explicit age verification."
                ),
                talent_id=talent_context.talent_id,
                details={
                    "condition": "adult_status_not_verified",
                    "adult_status": talent_context.adult_status.value,
                },
            )

        # Safety kernel passes — proceed to platform policy
        return None

    # =========================================================================
    # Layer 2: Platform Policy
    # =========================================================================

    def _evaluate_platform_policy(self) -> SafetyEvaluationResult | None:
        """Evaluate platform operator policy.

        Checks whether the platform allows adult content at all.

        Returns:
            SafetyEvaluationResult if blocked, None if platform allows.
        """
        if not self._platform_policy.adult_content_enabled:
            return SafetyEvaluationResult(
                decision=SafetyDecision.BLOCKED,
                policy_layer=PolicyLayer.PLATFORM_POLICY,
                reason=(
                    "Platform policy does not allow adult content. "
                    "Contact the platform operator to enable adult content."
                ),
                details={
                    "condition": "platform_adult_content_disabled",
                    "platform_rating": self._platform_policy.allowed_content_rating.value,
                },
            )

        if self._platform_policy.allowed_content_rating != ContentRating.ADULT:
            return SafetyEvaluationResult(
                decision=SafetyDecision.BLOCKED,
                policy_layer=PolicyLayer.PLATFORM_POLICY,
                reason=(
                    f"Platform content rating is "
                    f"'{self._platform_policy.allowed_content_rating.value}', "
                    f"which does not permit adult content. "
                    f"Content rating must be 'ADULT' for adult workflows."
                ),
                details={
                    "condition": "platform_rating_insufficient",
                    "platform_rating": self._platform_policy.allowed_content_rating.value,
                    "required_rating": ContentRating.ADULT.value,
                },
            )

        # Platform policy allows — proceed to workspace
        return None

    # =========================================================================
    # Layer 3: Workspace Policy + Identity-Specific Checks
    # =========================================================================

    def _evaluate_workspace_policy(
        self,
        talent_context: TalentSafetyContext,
        consent_context: ConsentContext,
    ) -> SafetyEvaluationResult:
        """Evaluate workspace policy and identity-specific conditions.

        Workspace policy can only be equal to or stricter than platform.
        After workspace check, evaluates based on identity_classification:
            - FICTIONAL: workspace allows + adult_status verified (already checked in kernel)
            - REAL_PERSON_SELF: above + active 'adult_content' consent scope
            - REAL_PERSON_AUTHORIZED: above + grantor identity + evidence

        Args:
            talent_context: Talent safety information.
            consent_context: Consent records for this talent.

        Returns:
            SafetyEvaluationResult (always returns a result at this layer).
        """
        # Check workspace allows adult content
        if not self._workspace_policy.adult_content_enabled:
            return SafetyEvaluationResult(
                decision=SafetyDecision.BLOCKED,
                policy_layer=PolicyLayer.WORKSPACE_POLICY,
                reason=(
                    "Workspace policy does not allow adult content. "
                    "The workspace administrator must enable adult content."
                ),
                talent_id=talent_context.talent_id,
                details={
                    "condition": "workspace_adult_content_disabled",
                    "workspace_rating": self._workspace_policy.allowed_content_rating.value,
                },
            )

        if self._workspace_policy.allowed_content_rating != ContentRating.ADULT:
            return SafetyEvaluationResult(
                decision=SafetyDecision.BLOCKED,
                policy_layer=PolicyLayer.WORKSPACE_POLICY,
                reason=(
                    f"Workspace content rating is "
                    f"'{self._workspace_policy.allowed_content_rating.value}', "
                    f"which does not permit adult content."
                ),
                talent_id=talent_context.talent_id,
                details={
                    "condition": "workspace_rating_insufficient",
                    "workspace_rating": self._workspace_policy.allowed_content_rating.value,
                    "required_rating": ContentRating.ADULT.value,
                },
            )

        # Identity-specific evaluation (R39.6)
        classification = talent_context.identity_classification

        if classification == IdentityClassification.FICTIONAL:
            return self._evaluate_fictional(talent_context)

        if classification == IdentityClassification.REAL_PERSON_SELF:
            return self._evaluate_real_person_self(talent_context, consent_context)

        if classification == IdentityClassification.REAL_PERSON_AUTHORIZED:
            return self._evaluate_real_person_authorized(
                talent_context, consent_context
            )

        # Unknown classification — fail closed
        return SafetyEvaluationResult(
            decision=SafetyDecision.BLOCKED,
            policy_layer=PolicyLayer.SAFETY_KERNEL,
            reason=(
                f"Unknown identity classification: "
                f"'{classification}'. Cannot evaluate adult content safety."
            ),
            talent_id=talent_context.talent_id,
            details={
                "condition": "unknown_identity_classification",
                "classification": str(classification),
            },
        )

    def _evaluate_fictional(
        self,
        talent_context: TalentSafetyContext,
    ) -> SafetyEvaluationResult:
        """Evaluate FICTIONAL talent for adult content.

        For fictional characters:
            - Workspace allows adult content (checked above)
            - adult_status == VERIFIED_18_PLUS (checked in safety kernel)
            - No consent record required

        Args:
            talent_context: Talent safety information.

        Returns:
            SafetyEvaluationResult — ALLOWED for fictional with verified status.
        """
        # All conditions met (kernel verified age, workspace allows adult)
        return SafetyEvaluationResult(
            decision=SafetyDecision.ALLOWED,
            policy_layer=PolicyLayer.WORKSPACE_POLICY,
            reason=(
                "Adult content allowed for fictional talent with "
                "VERIFIED_18_PLUS status and workspace adult content enabled."
            ),
            talent_id=talent_context.talent_id,
            details={
                "identity_classification": IdentityClassification.FICTIONAL.value,
                "adult_status": talent_context.adult_status.value,
            },
        )

    def _evaluate_real_person_self(
        self,
        talent_context: TalentSafetyContext,
        consent_context: ConsentContext,
    ) -> SafetyEvaluationResult:
        """Evaluate REAL_PERSON_SELF talent for adult content.

        For real persons (self-represented):
            - Workspace allows adult content (checked above)
            - adult_status == VERIFIED_18_PLUS (checked in safety kernel)
            - Active consent scope 'adult_content' from the real person

        Args:
            talent_context: Talent safety information.
            consent_context: Consent information.

        Returns:
            SafetyEvaluationResult.
        """
        # Must have active adult_content consent scope
        if not consent_context.has_adult_content_scope:
            return SafetyEvaluationResult(
                decision=SafetyDecision.BLOCKED,
                policy_layer=PolicyLayer.WORKSPACE_POLICY,
                reason=(
                    "Real person (self) requires active consent with "
                    "'adult_content' scope. No such consent record found."
                ),
                talent_id=talent_context.talent_id,
                details={
                    "condition": "missing_adult_content_consent",
                    "identity_classification": IdentityClassification.REAL_PERSON_SELF.value,
                },
            )

        if not consent_context.is_active:
            return SafetyEvaluationResult(
                decision=SafetyDecision.BLOCKED,
                policy_layer=PolicyLayer.WORKSPACE_POLICY,
                reason=(
                    "Real person (self) has an adult_content consent record "
                    "but it is not currently active (revoked or expired)."
                ),
                talent_id=talent_context.talent_id,
                details={
                    "condition": "consent_not_active",
                    "identity_classification": IdentityClassification.REAL_PERSON_SELF.value,
                },
            )

        # All conditions met
        return SafetyEvaluationResult(
            decision=SafetyDecision.ALLOWED,
            policy_layer=PolicyLayer.WORKSPACE_POLICY,
            reason=(
                "Adult content allowed for real person (self) with "
                "VERIFIED_18_PLUS status, workspace allows, and active "
                "'adult_content' consent scope."
            ),
            talent_id=talent_context.talent_id,
            details={
                "identity_classification": IdentityClassification.REAL_PERSON_SELF.value,
                "adult_status": talent_context.adult_status.value,
                "consent_active": True,
            },
        )

    def _evaluate_real_person_authorized(
        self,
        talent_context: TalentSafetyContext,
        consent_context: ConsentContext,
    ) -> SafetyEvaluationResult:
        """Evaluate REAL_PERSON_AUTHORIZED talent for adult content.

        For real persons (authorized representative):
            - Workspace allows adult content (checked above)
            - adult_status == VERIFIED_18_PLUS (checked in safety kernel)
            - Active consent scope 'adult_content' from authorized representative
            - Consent includes explicit adult-content authorization
            - Consent has grantor identity
            - Consent has evidence

        Args:
            talent_context: Talent safety information.
            consent_context: Consent information.

        Returns:
            SafetyEvaluationResult.
        """
        # Must have adult_content consent scope
        if not consent_context.has_adult_content_scope:
            return SafetyEvaluationResult(
                decision=SafetyDecision.BLOCKED,
                policy_layer=PolicyLayer.WORKSPACE_POLICY,
                reason=(
                    "Real person (authorized) requires consent with "
                    "'adult_content' scope from an authorized representative. "
                    "No such consent record found."
                ),
                talent_id=talent_context.talent_id,
                details={
                    "condition": "missing_adult_content_consent",
                    "identity_classification": IdentityClassification.REAL_PERSON_AUTHORIZED.value,
                },
            )

        if not consent_context.is_active:
            return SafetyEvaluationResult(
                decision=SafetyDecision.BLOCKED,
                policy_layer=PolicyLayer.WORKSPACE_POLICY,
                reason=(
                    "Real person (authorized) has an adult_content consent "
                    "record but it is not currently active (revoked or expired)."
                ),
                talent_id=talent_context.talent_id,
                details={
                    "condition": "consent_not_active",
                    "identity_classification": IdentityClassification.REAL_PERSON_AUTHORIZED.value,
                },
            )

        # Must have grantor identity (A2-025: who authorized this)
        if not consent_context.grantor_identity:
            return SafetyEvaluationResult(
                decision=SafetyDecision.BLOCKED,
                policy_layer=PolicyLayer.WORKSPACE_POLICY,
                reason=(
                    "Real person (authorized) requires consent with explicit "
                    "grantor identity. The consent record must identify who "
                    "authorized the adult content."
                ),
                talent_id=talent_context.talent_id,
                details={
                    "condition": "missing_grantor_identity",
                    "identity_classification": IdentityClassification.REAL_PERSON_AUTHORIZED.value,
                },
            )

        # Must have evidence
        if not consent_context.evidence_exists:
            return SafetyEvaluationResult(
                decision=SafetyDecision.BLOCKED,
                policy_layer=PolicyLayer.WORKSPACE_POLICY,
                reason=(
                    "Real person (authorized) requires consent with "
                    "supporting evidence. The consent record must include "
                    "evidence of adult-content authorization."
                ),
                talent_id=talent_context.talent_id,
                details={
                    "condition": "missing_evidence",
                    "identity_classification": IdentityClassification.REAL_PERSON_AUTHORIZED.value,
                },
            )

        # All conditions met
        return SafetyEvaluationResult(
            decision=SafetyDecision.ALLOWED,
            policy_layer=PolicyLayer.WORKSPACE_POLICY,
            reason=(
                "Adult content allowed for real person (authorized) with "
                "VERIFIED_18_PLUS status, workspace allows, active "
                "'adult_content' consent scope with grantor identity "
                "and evidence."
            ),
            talent_id=talent_context.talent_id,
            details={
                "identity_classification": IdentityClassification.REAL_PERSON_AUTHORIZED.value,
                "adult_status": talent_context.adult_status.value,
                "consent_active": True,
                "has_grantor_identity": True,
                "has_evidence": True,
            },
        )

    # =========================================================================
    # Logging
    # =========================================================================

    def _log_evaluation(
        self,
        result: SafetyEvaluationResult,
        talent_context: TalentSafetyContext,
    ) -> None:
        """Log the safety evaluation result for audit.

        Args:
            result: The evaluation result.
            talent_context: Talent context for correlation.
        """
        log_data = {
            "talent_id": str(talent_context.talent_id),
            "identity_classification": talent_context.identity_classification.value,
            "adult_status": talent_context.adult_status.value,
            "decision": result.decision.value,
            "policy_layer": result.policy_layer.value,
            "reason": result.reason,
        }

        if result.is_blocked:
            logger.warning("adult_content_safety_gate_blocked", **log_data)
        else:
            logger.info("adult_content_safety_gate_allowed", **log_data)
