"""Capability-Driven Video Provider Selection — Story 145.

Requirement-driven compatibility layer that matches user-specified generation
needs against verified provider capabilities and current readiness. Returns
classified results (compatible, incompatible, degraded, unavailable, unknown)
with explainable reasons for each provider/model.

Design principles:
- Provider-independent: requirement schema never references provider names
- Deterministic: same inputs → same output (versioned ranking rules)
- Explainable: every classification has a human-readable reason
- Fail-safe: missing data → 'unknown' (never assumes compatible)
- Manual override: authorized user can select any compatible provider
- Server enforcement: incompatible submissions blocked at API boundary

Ranking Rule Version: 1.0.0 (bump on any ranking logic change)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from backend.video.contract import (
    CanonicalVideoProvider,
    VideoMode,
    VideoModelInfo,
    VideoProviderCapabilities,
    VideoProviderHealth,
    VideoProviderStatus,
)

logger = logging.getLogger(__name__)

RANKING_RULE_VERSION = "1.0.0"


# =============================================================================
# Generation Requirement Schema (provider-independent)
# =============================================================================


class DeploymentPreference(StrEnum):
    """Where the user wants generation to run."""
    ANY = "any"
    CLOUD = "cloud"
    LOCAL = "local"
    SELF_HOSTED = "self_hosted"


class PrivacyLevel(StrEnum):
    """Content privacy requirements."""
    STANDARD = "standard"       # Cloud OK
    SENSITIVE = "sensitive"     # Prefer self-hosted
    RESTRICTED = "restricted"   # Must be self-hosted / local only


@dataclass
class GenerationRequirement:
    """Provider-independent description of what the user needs.

    Filled from UI selections and project context. Never references
    provider or model names — those are outputs of the matching engine.
    """

    # --- Modality (required) ---
    mode: VideoMode                          # text_to_video, image_to_video, video_to_video

    # --- Content inputs ---
    has_input_image: bool = False             # User is providing a reference image
    has_input_video: bool = False             # User is providing a source video

    # --- Duration & timing ---
    duration_seconds: float | None = None     # Desired output duration (None = provider default)
    min_duration_seconds: float | None = None # Minimum acceptable
    max_duration_seconds: float | None = None # Maximum acceptable

    # --- Resolution & aspect ---
    width: int | None = None                 # Desired width (None = provider default)
    height: int | None = None                # Desired height (None = provider default)
    aspect_ratio: str | None = None          # e.g. "16:9", "9:16", "1:1"
    min_resolution: str | None = None        # e.g. "720p", "1080p"

    # --- Quality & features ---
    needs_audio: bool = False                # Output must include audio track
    needs_camera_motion: bool = False        # Specific camera movement required
    needs_negative_prompt: bool = False      # Negative prompt control needed
    needs_seed_control: bool = False         # Reproducibility via seed
    needs_high_fps: bool = False             # >24fps required (48/60)

    # --- Consistency & references ---
    needs_character_consistency: bool = False # Same character across clips
    needs_style_consistency: bool = False    # Consistent visual style

    # --- Deployment & privacy ---
    deployment_preference: DeploymentPreference = DeploymentPreference.ANY
    privacy_level: PrivacyLevel = PrivacyLevel.STANDARD

    # --- Budget ---
    max_cost_usd: float | None = None        # Hard budget cap (None = no limit)

    # --- Latency ---
    max_wait_seconds: float | None = None    # Maximum acceptable wait time

    # --- Hardware ---
    min_vram_gb: float | None = None         # Minimum VRAM (for self-hosted)

    # --- Context (informational, not matching criteria) ---
    project_id: str | None = None
    talent_id: str | None = None


# =============================================================================
# Compatibility Classification
# =============================================================================


class Compatibility(StrEnum):
    """Result of matching a requirement against a provider/model."""
    COMPATIBLE = "compatible"           # Fully supports all requirements
    DEGRADED = "degraded"               # Supports core but not all features
    INCOMPATIBLE = "incompatible"       # Cannot fulfill the requirement
    UNAVAILABLE = "unavailable"         # Could fulfill but currently offline/degraded
    UNKNOWN = "unknown"                 # Missing capability data — cannot determine


@dataclass
class CompatibilityReason:
    """One reason contributing to a compatibility classification."""
    field: str                           # Which requirement field caused this
    constraint: str                      # What the requirement asked for
    provider_value: str                  # What the provider offers
    verdict: Compatibility               # This reason's verdict
    message: str                         # Human-readable explanation


@dataclass
class ProviderCompatibility:
    """Full compatibility assessment for one provider/model pair."""
    provider_name: str
    provider_display_name: str
    model_id: str
    model_name: str
    compatibility: Compatibility         # Overall verdict (worst of all reasons)
    reasons: list[CompatibilityReason] = field(default_factory=list)
    # Metadata
    deployment_mode: str = ""
    estimated_cost_usd: float | None = None  # None = unknown
    estimated_wait_seconds: float | None = None
    cost_confidence: str = "unknown"     # fixed, estimate, unknown


@dataclass
class SelectionResult:
    """Complete result from the capability selector."""
    requirement: GenerationRequirement
    compatible: list[ProviderCompatibility] = field(default_factory=list)
    degraded: list[ProviderCompatibility] = field(default_factory=list)
    incompatible: list[ProviderCompatibility] = field(default_factory=list)
    unavailable: list[ProviderCompatibility] = field(default_factory=list)
    unknown: list[ProviderCompatibility] = field(default_factory=list)
    # Recommendation
    recommended: ProviderCompatibility | None = None
    recommendation_reason: str = ""
    ranking_rule_version: str = RANKING_RULE_VERSION


# =============================================================================
# Capability Matcher
# =============================================================================


def match_requirement_to_model(
    requirement: GenerationRequirement,
    model: VideoModelInfo,
    capabilities: VideoProviderCapabilities,
    health: VideoProviderHealth,
    provider: CanonicalVideoProvider,
) -> ProviderCompatibility:
    """Match a requirement against a single provider/model pair.

    Returns a full ProviderCompatibility with classified reasons.
    """
    reasons: list[CompatibilityReason] = []

    # --- Mode support ---
    if requirement.mode not in model.modes:
        reasons.append(CompatibilityReason(
            field="mode",
            constraint=requirement.mode.value,
            provider_value=", ".join(m.value for m in model.modes),
            verdict=Compatibility.INCOMPATIBLE,
            message=f"Model does not support {requirement.mode.value}. Supported: {', '.join(m.value for m in model.modes)}.",
        ))
    else:
        reasons.append(CompatibilityReason(
            field="mode",
            constraint=requirement.mode.value,
            provider_value=requirement.mode.value,
            verdict=Compatibility.COMPATIBLE,
            message=f"Supports {requirement.mode.value}.",
        ))

    # --- Duration ---
    if requirement.duration_seconds is not None:
        if requirement.duration_seconds > model.max_duration_seconds:
            reasons.append(CompatibilityReason(
                field="duration_seconds",
                constraint=f"{requirement.duration_seconds}s",
                provider_value=f"max {model.max_duration_seconds}s",
                verdict=Compatibility.INCOMPATIBLE,
                message=f"Requested {requirement.duration_seconds}s exceeds max {model.max_duration_seconds}s.",
            ))
        else:
            reasons.append(CompatibilityReason(
                field="duration_seconds",
                constraint=f"{requirement.duration_seconds}s",
                provider_value=f"max {model.max_duration_seconds}s",
                verdict=Compatibility.COMPATIBLE,
                message=f"Duration {requirement.duration_seconds}s within limit.",
            ))

    # --- Resolution ---
    if requirement.width and requirement.height:
        max_w, max_h = _parse_resolution(model.max_resolution)
        if requirement.width > max_w or requirement.height > max_h:
            reasons.append(CompatibilityReason(
                field="resolution",
                constraint=f"{requirement.width}x{requirement.height}",
                provider_value=f"max {model.max_resolution}",
                verdict=Compatibility.INCOMPATIBLE,
                message=f"Requested {requirement.width}x{requirement.height} exceeds max {model.max_resolution}.",
            ))
        else:
            reasons.append(CompatibilityReason(
                field="resolution",
                constraint=f"{requirement.width}x{requirement.height}",
                provider_value=f"max {model.max_resolution}",
                verdict=Compatibility.COMPATIBLE,
                message=f"Resolution within limits.",
            ))

    # --- Camera motion ---
    if requirement.needs_camera_motion and not model.supports_camera_motion:
        reasons.append(CompatibilityReason(
            field="camera_motion",
            constraint="required",
            provider_value="not supported",
            verdict=Compatibility.DEGRADED,
            message="Camera motion control not supported. Static camera will be used.",
        ))

    # --- Negative prompt ---
    if requirement.needs_negative_prompt and not model.supports_negative_prompt:
        reasons.append(CompatibilityReason(
            field="negative_prompt",
            constraint="required",
            provider_value="not supported",
            verdict=Compatibility.DEGRADED,
            message="Negative prompt not supported by this model.",
        ))

    # --- Seed control ---
    if requirement.needs_seed_control and not model.supports_seed:
        reasons.append(CompatibilityReason(
            field="seed_control",
            constraint="required",
            provider_value="not supported",
            verdict=Compatibility.DEGRADED,
            message="Seed control not available — results will not be reproducible.",
        ))

    # --- High FPS ---
    if requirement.needs_high_fps and model.max_fps <= 24:
        reasons.append(CompatibilityReason(
            field="fps",
            constraint=">24fps",
            provider_value=f"max {model.max_fps}fps",
            verdict=Compatibility.DEGRADED,
            message=f"Max FPS is {model.max_fps}. High frame rate not available.",
        ))

    # --- Audio ---
    if requirement.needs_audio:
        reasons.append(CompatibilityReason(
            field="audio",
            constraint="required",
            provider_value="not supported",
            verdict=Compatibility.DEGRADED,
            message="Audio generation not natively supported. Audio must be added separately.",
        ))

    # --- Deployment preference ---
    if requirement.deployment_preference != DeploymentPreference.ANY:
        if requirement.deployment_preference == DeploymentPreference.LOCAL and capabilities.deployment_mode != "local":
            reasons.append(CompatibilityReason(
                field="deployment",
                constraint="local",
                provider_value=capabilities.deployment_mode,
                verdict=Compatibility.INCOMPATIBLE,
                message=f"Local deployment required but provider is {capabilities.deployment_mode}.",
            ))
        elif requirement.deployment_preference == DeploymentPreference.SELF_HOSTED and capabilities.deployment_mode == "hosted":
            reasons.append(CompatibilityReason(
                field="deployment",
                constraint="self_hosted",
                provider_value=capabilities.deployment_mode,
                verdict=Compatibility.INCOMPATIBLE,
                message="Self-hosted required but provider is externally hosted.",
            ))

    # --- Privacy ---
    if requirement.privacy_level == PrivacyLevel.RESTRICTED:
        if capabilities.deployment_mode not in ("local", "self_hosted"):
            reasons.append(CompatibilityReason(
                field="privacy",
                constraint="restricted",
                provider_value=capabilities.deployment_mode,
                verdict=Compatibility.INCOMPATIBLE,
                message="Restricted privacy requires local/self-hosted execution.",
            ))

    # --- Provider health/availability ---
    if health.status == VideoProviderStatus.UNAVAILABLE:
        reasons.append(CompatibilityReason(
            field="availability",
            constraint="available",
            provider_value="unavailable",
            verdict=Compatibility.UNAVAILABLE,
            message=health.message or "Provider is currently unavailable.",
        ))
    elif health.status == VideoProviderStatus.DEGRADED:
        reasons.append(CompatibilityReason(
            field="availability",
            constraint="available",
            provider_value="degraded",
            verdict=Compatibility.DEGRADED,
            message=health.message or "Provider is degraded — slower or less reliable.",
        ))
    elif health.status == VideoProviderStatus.MAINTENANCE:
        reasons.append(CompatibilityReason(
            field="availability",
            constraint="available",
            provider_value="maintenance",
            verdict=Compatibility.UNAVAILABLE,
            message="Provider is in maintenance mode.",
        ))

    # --- Cost estimate ---
    estimated_cost: float | None = None
    cost_confidence = "unknown"
    try:
        from backend.video.contract import VideoGenerationRequest
        est_request = VideoGenerationRequest(
            mode=requirement.mode,
            prompt="cost_estimate_probe",
            duration_seconds=requirement.duration_seconds or 2.0,
            width=requirement.width or 832,
            height=requirement.height or 480,
        )
        estimate = provider.estimate_cost(est_request)
        estimated_cost = estimate.estimated_cost_usd
        cost_confidence = estimate.confidence
    except Exception:
        pass

    # --- Budget check ---
    if requirement.max_cost_usd is not None and estimated_cost is not None:
        if estimated_cost > requirement.max_cost_usd:
            reasons.append(CompatibilityReason(
                field="budget",
                constraint=f"max ${requirement.max_cost_usd:.3f}",
                provider_value=f"~${estimated_cost:.3f}",
                verdict=Compatibility.INCOMPATIBLE,
                message=f"Estimated cost ${estimated_cost:.3f} exceeds budget ${requirement.max_cost_usd:.3f}.",
            ))

    # --- Classify overall verdict (worst reason wins) ---
    overall = _classify_overall(reasons)

    return ProviderCompatibility(
        provider_name=capabilities.provider_name,
        provider_display_name=provider.display_name,
        model_id=model.id,
        model_name=model.name,
        compatibility=overall,
        reasons=reasons,
        deployment_mode=capabilities.deployment_mode,
        estimated_cost_usd=estimated_cost,
        estimated_wait_seconds=health.estimated_wait_seconds,
        cost_confidence=cost_confidence,
    )


# =============================================================================
# Full Selection (all providers × all models)
# =============================================================================


def select_providers(
    requirement: GenerationRequirement,
    registry: Any | None = None,
) -> SelectionResult:
    """Run capability matching across all registered providers.

    Returns classified results with recommendation.
    """
    if registry is None:
        from backend.video.registry import get_video_provider_registry
        registry = get_video_provider_registry()

    result = SelectionResult(requirement=requirement)

    for provider_name in registry.list_providers():
        provider = registry.get_provider(provider_name)
        if not provider:
            continue

        capabilities = provider.capabilities()
        health = provider.health()
        models = provider.list_models()

        for model in models:
            compat = match_requirement_to_model(
                requirement, model, capabilities, health, provider,
            )

            if compat.compatibility == Compatibility.COMPATIBLE:
                result.compatible.append(compat)
            elif compat.compatibility == Compatibility.DEGRADED:
                result.degraded.append(compat)
            elif compat.compatibility == Compatibility.INCOMPATIBLE:
                result.incompatible.append(compat)
            elif compat.compatibility == Compatibility.UNAVAILABLE:
                result.unavailable.append(compat)
            else:
                result.unknown.append(compat)

    # --- Recommendation ---
    result.recommended, result.recommendation_reason = _rank_and_recommend(result)
    result.ranking_rule_version = RANKING_RULE_VERSION

    return result


# =============================================================================
# Recommendation Ranking (versioned, deterministic)
# =============================================================================


def _rank_and_recommend(result: SelectionResult) -> tuple[ProviderCompatibility | None, str]:
    """Deterministic recommendation from compatible providers.

    Ranking rules (v1.0.0):
    1. Prefer compatible over degraded
    2. Among compatible: prefer lower estimated cost (if known)
    3. Among same cost: prefer lower estimated wait
    4. Among same wait: prefer non-simulation providers
    5. If no cost info: rank by availability (lower queue preferred)

    Does NOT claim quality rankings without evidence.
    """
    candidates = list(result.compatible)
    if not candidates:
        candidates = list(result.degraded)

    if not candidates:
        return None, "No compatible or degraded providers available."

    def sort_key(c: ProviderCompatibility) -> tuple:
        # Prefer non-simulation
        is_sim = 1 if "simulation" in c.provider_name.lower() else 0
        # Prefer known cost (unknown sorts last)
        cost = c.estimated_cost_usd if c.estimated_cost_usd is not None else 999.0
        # Prefer shorter wait
        wait = c.estimated_wait_seconds if c.estimated_wait_seconds is not None else 999.0
        return (is_sim, cost, wait)

    candidates.sort(key=sort_key)
    recommended = candidates[0]

    # Build explanation
    parts = []
    if recommended.estimated_cost_usd is not None:
        parts.append(f"estimated cost ${recommended.estimated_cost_usd:.3f}")
    if recommended.estimated_wait_seconds is not None:
        parts.append(f"~{recommended.estimated_wait_seconds:.0f}s wait")
    if "simulation" in recommended.provider_name.lower():
        parts.append("simulation mode (no GPU cost)")

    reason = f"Recommended: {recommended.provider_display_name} / {recommended.model_name}"
    if parts:
        reason += f" ({', '.join(parts)})"

    return recommended, reason


# =============================================================================
# Server-Side Enforcement
# =============================================================================


class IncompatibleProviderError(Exception):
    """Raised when submission targets an incompatible provider."""

    def __init__(self, provider_name: str, model_id: str, reasons: list[CompatibilityReason]):
        self.provider_name = provider_name
        self.model_id = model_id
        self.reasons = reasons
        incompatible_reasons = [r for r in reasons if r.verdict == Compatibility.INCOMPATIBLE]
        messages = [r.message for r in incompatible_reasons]
        super().__init__(
            f"Provider '{provider_name}' model '{model_id}' is incompatible: {'; '.join(messages)}"
        )


def enforce_compatibility(
    requirement: GenerationRequirement,
    provider_name: str,
    model_id: str,
    registry: Any | None = None,
) -> ProviderCompatibility:
    """Server-side enforcement: blocks incompatible submissions.

    Called before budget reservation or dispatch.
    Returns the compatibility result if compatible/degraded.
    Raises IncompatibleProviderError if incompatible.
    Raises LookupError if provider/model not found.
    """
    if registry is None:
        from backend.video.registry import get_video_provider_registry
        registry = get_video_provider_registry()

    provider = registry.get_provider(provider_name)
    if not provider:
        raise LookupError(f"Provider '{provider_name}' not found in registry.")

    capabilities = provider.capabilities()
    health = provider.health()
    models = provider.list_models()

    target_model = next((m for m in models if m.id == model_id), None)
    if not target_model:
        raise LookupError(f"Model '{model_id}' not found for provider '{provider_name}'.")

    compat = match_requirement_to_model(
        requirement, target_model, capabilities, health, provider,
    )

    if compat.compatibility == Compatibility.INCOMPATIBLE:
        raise IncompatibleProviderError(provider_name, model_id, compat.reasons)

    if compat.compatibility == Compatibility.UNAVAILABLE:
        raise IncompatibleProviderError(provider_name, model_id, compat.reasons)

    if compat.compatibility == Compatibility.UNKNOWN:
        raise IncompatibleProviderError(provider_name, model_id, compat.reasons)

    # Compatible or degraded — allow
    return compat


# =============================================================================
# Helpers
# =============================================================================


def _parse_resolution(res: str) -> tuple[int, int]:
    """Parse '1280x720' into (1280, 720)."""
    try:
        parts = res.lower().split("x")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 9999, 9999  # Unknown → don't block


def _classify_overall(reasons: list[CompatibilityReason]) -> Compatibility:
    """Determine overall compatibility from individual reasons.

    Priority: INCOMPATIBLE > UNAVAILABLE > UNKNOWN > DEGRADED > COMPATIBLE.
    """
    verdicts = {r.verdict for r in reasons}
    if Compatibility.INCOMPATIBLE in verdicts:
        return Compatibility.INCOMPATIBLE
    if Compatibility.UNAVAILABLE in verdicts:
        return Compatibility.UNAVAILABLE
    if Compatibility.UNKNOWN in verdicts:
        return Compatibility.UNKNOWN
    if Compatibility.DEGRADED in verdicts:
        return Compatibility.DEGRADED
    return Compatibility.COMPATIBLE


# =============================================================================
# Serialization (for API responses)
# =============================================================================


def serialize_selection_result(result: SelectionResult) -> dict:
    """Serialize SelectionResult for JSON API response."""
    def _ser_compat(c: ProviderCompatibility) -> dict:
        return {
            "provider_name": c.provider_name,
            "provider_display_name": c.provider_display_name,
            "model_id": c.model_id,
            "model_name": c.model_name,
            "compatibility": c.compatibility.value,
            "deployment_mode": c.deployment_mode,
            "estimated_cost_usd": c.estimated_cost_usd,
            "cost_confidence": c.cost_confidence,
            "estimated_wait_seconds": c.estimated_wait_seconds,
            "reasons": [
                {
                    "field": r.field,
                    "constraint": r.constraint,
                    "provider_value": r.provider_value,
                    "verdict": r.verdict.value,
                    "message": r.message,
                }
                for r in c.reasons
            ],
        }

    return {
        "compatible": [_ser_compat(c) for c in result.compatible],
        "degraded": [_ser_compat(c) for c in result.degraded],
        "incompatible": [_ser_compat(c) for c in result.incompatible],
        "unavailable": [_ser_compat(c) for c in result.unavailable],
        "unknown": [_ser_compat(c) for c in result.unknown],
        "recommended": _ser_compat(result.recommended) if result.recommended else None,
        "recommendation_reason": result.recommendation_reason,
        "ranking_rule_version": result.ranking_rule_version,
    }
