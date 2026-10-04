"""Platform capability and rollout registry for authenticated publishing.

The registry is deliberately provider-neutral: it describes what a platform
supports and what a publish operation must prove. Connection existence never
implies that a platform is enabled or that a publish is policy-approved.

Fanvue is the first verified rollout target. Other providers are represented
for truthful capability discovery, but remain disabled until their adapter,
configuration, and verification evidence are supplied.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class PlatformAvailability(StrEnum):
    """Rollout state exposed to authenticated clients."""

    ENABLED = "enabled"
    COMING_SOON = "coming_soon"
    DISABLED = "disabled"


@dataclass(frozen=True)
class PlatformPolicy:
    """Destination policy requirements for a publish operation."""

    ai_label_required: bool = False
    watermark_required: bool = False
    caption_disclosure_required: bool = False
    nsfw_allowed: bool = False
    age_verification_required: bool = False
    consent_identity_required: bool = False
    verified_creator_required: bool = False
    reasonable_person_moderation_required: bool = False
    explicit_publish_confirmation_required: bool = True

    def as_dict(self) -> dict[str, bool]:
        """Return a JSON-safe policy representation."""
        return asdict(self)


@dataclass(frozen=True)
class PlatformDefinition:
    """Static metadata for one publishing destination."""

    platform: str
    display_name: str
    lane: str
    availability: PlatformAvailability
    verified: bool
    oauth_supported: bool
    capabilities: tuple[str, ...]
    policy: PlatformPolicy
    allowed_roles: tuple[str, ...] = ("owner", "admin", "editor")

    @property
    def enabled(self) -> bool:
        """Whether new connections may be initiated for this platform."""
        return self.availability == PlatformAvailability.ENABLED and self.verified

    def as_dict(self) -> dict[str, object]:
        """Return client-safe capability metadata with no provider secrets."""
        return {
            "platform": self.platform,
            "display_name": self.display_name,
            "lane": self.lane,
            "availability": self.availability.value,
            "enabled": self.enabled,
            "verified": self.verified,
            "oauth_supported": self.oauth_supported,
            "capabilities": list(self.capabilities),
            "policy": self.policy.as_dict(),
            "allowed_roles": list(self.allowed_roles),
        }


_FANVUE_POLICY = PlatformPolicy(
    ai_label_required=True,
    watermark_required=True,
    caption_disclosure_required=True,
    nsfw_allowed=True,
    age_verification_required=True,
    consent_identity_required=True,
    verified_creator_required=False,
    reasonable_person_moderation_required=True,
    explicit_publish_confirmation_required=True,
)

_SFW_POLICY = PlatformPolicy(
    ai_label_required=True,
    caption_disclosure_required=True,
    nsfw_allowed=False,
    explicit_publish_confirmation_required=True,
)

_NSFW_COMING_SOON_POLICY = PlatformPolicy(
    ai_label_required=True,
    caption_disclosure_required=True,
    nsfw_allowed=True,
    age_verification_required=True,
    consent_identity_required=True,
    verified_creator_required=True,
    reasonable_person_moderation_required=True,
    explicit_publish_confirmation_required=True,
)


PLATFORM_REGISTRY: dict[str, PlatformDefinition] = {
    "fanvue": PlatformDefinition(
        platform="fanvue",
        display_name="Fanvue",
        lane="nsfw_sfw",
        availability=PlatformAvailability.ENABLED,
        verified=True,
        oauth_supported=True,
        capabilities=(
            "read_profile",
            "read_media",
            "publish_media",
            "publish_explicit_media",
            "schedule_posts",
            "health_check",
        ),
        policy=_FANVUE_POLICY,
    ),
    "onlyfans": PlatformDefinition(
        platform="onlyfans",
        display_name="OnlyFans",
        lane="nsfw_sfw",
        availability=PlatformAvailability.COMING_SOON,
        verified=False,
        oauth_supported=False,
        capabilities=("publish_media", "schedule_posts"),
        policy=_NSFW_COMING_SOON_POLICY,
    ),
    "loyalfans": PlatformDefinition(
        platform="loyalfans",
        display_name="LoyalFans",
        lane="nsfw_sfw",
        availability=PlatformAvailability.COMING_SOON,
        verified=False,
        oauth_supported=False,
        capabilities=("publish_media", "schedule_posts"),
        policy=_NSFW_COMING_SOON_POLICY,
    ),
}

for _platform, _display_name in (
    ("instagram", "Instagram"),
    ("x", "X/Twitter"),
    ("youtube", "YouTube"),
    ("facebook", "Facebook"),
    ("tiktok", "TikTok"),
    ("threads", "Threads"),
    ("snapchat", "Snapchat"),
):
    PLATFORM_REGISTRY[_platform] = PlatformDefinition(
        platform=_platform,
        display_name=_display_name,
        lane="sfw",
        availability=PlatformAvailability.COMING_SOON,
        verified=False,
        oauth_supported=False,
        capabilities=("publish_media", "schedule_posts"),
        policy=_SFW_POLICY,
    )


def get_platform_definition(platform: str) -> PlatformDefinition | None:
    """Return metadata for a platform identifier, if it is registered."""
    return PLATFORM_REGISTRY.get(platform.strip().lower())


def list_platform_definitions() -> list[dict[str, object]]:
    """Return deterministic, client-safe platform capability metadata."""
    return [PLATFORM_REGISTRY[name].as_dict() for name in sorted(PLATFORM_REGISTRY)]


LEGACY_COMPATIBLE_PLATFORMS = frozenset({"instagram", "youtube", "tiktok", "x", "github"})


def connection_allowed(platform: str) -> bool:
    """Return whether connection compatibility permits a platform.

    Existing configured SFW OAuth providers retain their historical connection
    behavior; unverified Phase 2 rollout targets never do.
    """
    definition = get_platform_definition(platform)
    return definition is None or definition.enabled or platform in LEGACY_COMPATIBLE_PLATFORMS


def discovered_capabilities(platform: str) -> list[str]:
    """Return the verified baseline capabilities for a connected platform."""
    definition = get_platform_definition(platform)
    return list(definition.capabilities) if definition else []
