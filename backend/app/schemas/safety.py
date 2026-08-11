"""Pydantic v2 schemas for the Adult Content Safety Gate.

Three-layer content policy evaluation:
    1. Safety Kernel (mandatory, non-disableable)
    2. Platform Policy (platform operator configurable)
    3. Workspace Policy (can only be stricter than platform)

Validates: Requirements R39.1, R39.2, R39.3, R39.4, R39.5, R39.6, R39.7, R10.11, A2-024, A2-025
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from uuid import UUID


# =============================================================================
# Enums
# =============================================================================


class ContentRating(str, enum.Enum):
    """Platform/workspace content rating levels.

    SFW_ONLY: No adult content permitted.
    MATURE: Suggestive content permitted, explicit not.
    ADULT: Explicit adult content permitted (subject to identity checks).
    """

    SFW_ONLY = "SFW_ONLY"
    MATURE = "MATURE"
    ADULT = "ADULT"


class AdultStatus(str, enum.Enum):
    """Adult verification status for a talent entity.

    VERIFIED_18_PLUS: Creator has attested that the character/person is 18+.
    NOT_VERIFIED: Age/adulthood has not been confirmed.
    AMBIGUOUS: Age cannot be determined — fails closed per A2-024.
    """

    VERIFIED_18_PLUS = "VERIFIED_18_PLUS"
    NOT_VERIFIED = "NOT_VERIFIED"
    AMBIGUOUS = "AMBIGUOUS"


class IdentityClassification(str, enum.Enum):
    """Identity classification for talent entities."""

    FICTIONAL = "FICTIONAL"
    REAL_PERSON_SELF = "REAL_PERSON_SELF"
    REAL_PERSON_AUTHORIZED = "REAL_PERSON_AUTHORIZED"


class PolicyLayer(str, enum.Enum):
    """Which policy layer issued a decision."""

    SAFETY_KERNEL = "safety_kernel"
    PLATFORM_POLICY = "platform_policy"
    WORKSPACE_POLICY = "workspace_policy"


class SafetyDecision(str, enum.Enum):
    """Result of a safety evaluation."""

    ALLOWED = "allowed"
    BLOCKED = "blocked"


# =============================================================================
# Data Classes (used internally by the safety gate service)
# =============================================================================


@dataclass(frozen=True)
class PlatformPolicy:
    """Platform-wide content policy set by the platform operator.

    Attributes:
        allowed_content_rating: Maximum rating permitted platform-wide.
        prohibited_categories: Content categories that are never permitted.
        adult_content_enabled: Whether adult content is allowed at all.
    """

    allowed_content_rating: ContentRating = ContentRating.SFW_ONLY
    prohibited_categories: list[str] = field(default_factory=list)
    adult_content_enabled: bool = False


@dataclass(frozen=True)
class WorkspacePolicy:
    """Workspace-level content policy (can only be stricter than platform).

    Attributes:
        allowed_content_rating: Maximum rating for this workspace.
        adult_content_enabled: Whether adult content is allowed in this workspace.
    """

    allowed_content_rating: ContentRating = ContentRating.SFW_ONLY
    adult_content_enabled: bool = False


@dataclass(frozen=True)
class TalentSafetyContext:
    """Safety-relevant information about the talent being evaluated.

    Attributes:
        talent_id: UUID of the talent entity.
        identity_classification: FICTIONAL, REAL_PERSON_SELF, REAL_PERSON_AUTHORIZED.
        adult_status: Verification status of age/adulthood.
    """

    talent_id: UUID
    identity_classification: IdentityClassification
    adult_status: AdultStatus


@dataclass(frozen=True)
class ConsentContext:
    """Consent information relevant to adult content evaluation.

    Attributes:
        has_adult_content_scope: Whether an active consent record with
            'adult_content' scope exists for this talent.
        grantor_identity: Who granted the consent (for REAL_PERSON_AUTHORIZED).
        evidence_exists: Whether evidence is attached to the consent record.
        is_active: Whether the consent record is currently active (not revoked/expired).
    """

    has_adult_content_scope: bool = False
    grantor_identity: str | None = None
    evidence_exists: bool = False
    is_active: bool = False


@dataclass(frozen=True)
class SafetyEvaluationResult:
    """Result of the adult content safety gate evaluation.

    Attributes:
        decision: ALLOWED or BLOCKED.
        policy_layer: Which layer issued the decision.
        reason: Human-readable explanation of the decision.
        talent_id: The talent entity that was evaluated.
        details: Additional structured details about the evaluation.
    """

    decision: SafetyDecision
    policy_layer: PolicyLayer
    reason: str
    talent_id: UUID | None = None
    details: dict = field(default_factory=dict)

    @property
    def is_allowed(self) -> bool:
        """Convenience property for checking if content is allowed."""
        return self.decision == SafetyDecision.ALLOWED

    @property
    def is_blocked(self) -> bool:
        """Convenience property for checking if content is blocked."""
        return self.decision == SafetyDecision.BLOCKED
