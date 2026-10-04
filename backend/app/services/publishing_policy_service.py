"""Publishing policy gates for connected platform destinations.

This module is intentionally independent of HTTP and database code so the
same policy decision can be reused by scheduled publishing, MCP tools, and
provider adapters. A connected account is not sufficient to publish.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.platform_registry import PlatformDefinition, get_platform_definition


class PlatformPolicyDeniedError(Exception):
    """Raised when required content or safety evidence is missing."""

    def __init__(self, platform: str, missing_requirements: list[str]) -> None:
        self.platform = platform
        self.missing_requirements = missing_requirements
        self.code = "PLATFORM_POLICY_DENIED"
        super().__init__(
            f"Publishing to {platform} is blocked by platform policy: "
            + ", ".join(missing_requirements)
        )


class PlatformUnavailableError(Exception):
    """Raised when a provider is unknown, disabled, or not verified."""

    def __init__(self, platform: str, availability: str = "unknown") -> None:
        self.platform = platform
        self.availability = availability
        self.code = "PLATFORM_UNAVAILABLE"
        super().__init__(f"Platform '{platform}' is not enabled ({availability})")


@dataclass(frozen=True)
class PublishPolicyInput:
    """Evidence required before content may be submitted to a platform."""

    ai_generated: bool = True
    ai_label_present: bool = False
    watermark_present: bool = False
    caption_disclosure_present: bool = False
    age_verified: bool = False
    consent_verified: bool = False
    identity_verified: bool = False
    verified_creator: bool = False
    moderation_passed: bool = False
    publish_confirmed: bool = False
    is_nsfw: bool = False


@dataclass(frozen=True)
class PublishPolicyDecision:
    """Stable result returned to callers and audit/event producers."""

    allowed: bool
    platform: str
    missing_requirements: tuple[str, ...]
    capabilities: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe policy decision."""
        return {
            "allowed": self.allowed,
            "platform": self.platform,
            "missing_requirements": list(self.missing_requirements),
            "capabilities": list(self.capabilities),
        }


def evaluate_publish_policy(
    platform: str,
    evidence: PublishPolicyInput,
    definition: PlatformDefinition | None = None,
) -> PublishPolicyDecision:
    """Evaluate all destination policy gates without making a provider call.

    Raises:
        PlatformUnavailable: If the destination is not a verified rollout target.
        PlatformPolicyDenied: If one or more required gates are not satisfied.
    """
    normalized = platform.strip().lower()
    definition = definition or get_platform_definition(normalized)
    if definition is None:
        raise PlatformUnavailableError(normalized)
    if not definition.enabled:
        raise PlatformUnavailableError(normalized, definition.availability.value)

    policy = definition.policy
    missing: list[str] = []
    if evidence.ai_generated and policy.ai_label_required and not evidence.ai_label_present:
        missing.append("ai_label")
    if evidence.ai_generated and policy.watermark_required and not evidence.watermark_present:
        missing.append("watermark")
    if evidence.ai_generated and policy.caption_disclosure_required and not evidence.caption_disclosure_present:
        missing.append("caption_disclosure")
    if evidence.is_nsfw and not policy.nsfw_allowed:
        missing.append("nsfw_not_allowed")
    if policy.age_verification_required and not evidence.age_verified:
        missing.append("age_verification")
    if policy.consent_identity_required and not evidence.consent_verified:
        missing.append("consent")
    if policy.consent_identity_required and not evidence.identity_verified:
        missing.append("identity_verification")
    if policy.verified_creator_required and not evidence.verified_creator:
        missing.append("verified_creator")
    if policy.reasonable_person_moderation_required and not evidence.moderation_passed:
        missing.append("reasonable_person_moderation")
    if policy.explicit_publish_confirmation_required and not evidence.publish_confirmed:
        missing.append("publish_confirmation")

    if missing:
        raise PlatformPolicyDeniedError(normalized, missing)

    return PublishPolicyDecision(
        allowed=True,
        platform=normalized,
        missing_requirements=(),
        capabilities=tuple(definition.capabilities),
    )
