"""Capability Selector Tests — Story 145.

Proves: requirement matching, compatibility classification, ranking,
server enforcement, edge cases (no providers, budget, privacy, stale state).

Run with:
    pytest tests/unit/test_capability_selector.py -v
"""

from __future__ import annotations

import pytest

from backend.video.capability_selector import (
    Compatibility,
    CompatibilityReason,
    DeploymentPreference,
    GenerationRequirement,
    IncompatibleProviderError,
    PrivacyLevel,
    RANKING_RULE_VERSION,
    SelectionResult,
    enforce_compatibility,
    match_requirement_to_model,
    select_providers,
    _classify_overall,
    _parse_resolution,
)
from backend.video.contract import (
    CanonicalVideoProvider,
    VideoCostEstimate,
    VideoGenerationProgress,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoMode,
    VideoModelInfo,
    VideoProviderCapabilities,
    VideoProviderConfig,
    VideoProviderHealth,
    VideoProviderStatus,
)
from backend.video.registry import VideoProviderRegistry, reset_video_provider_registry


# =============================================================================
# Test Fixtures — Mock provider for isolated testing
# =============================================================================

TEST_MODEL_A = VideoModelInfo(
    id="test-model-a",
    name="Test Model A",
    provider="test-provider",
    modes=[VideoMode.TEXT_TO_VIDEO, VideoMode.IMAGE_TO_VIDEO],
    max_duration_seconds=10.0,
    max_resolution="1280x720",
    default_resolution="832x480",
    default_fps=24,
    max_fps=24,
    vram_required_gb=12.0,
    supports_negative_prompt=True,
    supports_camera_motion=False,
    supports_seed=True,
)

TEST_MODEL_B = VideoModelInfo(
    id="test-model-b",
    name="Test Model B (Premium)",
    provider="test-premium",
    modes=[VideoMode.TEXT_TO_VIDEO, VideoMode.IMAGE_TO_VIDEO, VideoMode.VIDEO_TO_VIDEO],
    max_duration_seconds=30.0,
    max_resolution="1920x1080",
    default_resolution="1280x720",
    default_fps=30,
    max_fps=60,
    vram_required_gb=80.0,
    supports_negative_prompt=True,
    supports_camera_motion=True,
    supports_seed=True,
)


class MockProvider(CanonicalVideoProvider):
    """Test provider with configurable capabilities."""

    def __init__(self, name: str = "test-provider", models: list | None = None,
                 status: VideoProviderStatus = VideoProviderStatus.AVAILABLE,
                 deployment: str = "cloud", cost: float = 0.05):
        self._name = name
        self._models = models or [TEST_MODEL_A]
        self._status = status
        self._deployment = deployment
        self._cost = cost
        self._config: VideoProviderConfig | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def display_name(self) -> str:
        return f"Mock {self._name}"

    def initialize(self, config: VideoProviderConfig) -> None:
        self._config = config

    def capabilities(self) -> VideoProviderCapabilities:
        all_modes = set()
        for m in self._models:
            all_modes.update(m.modes)
        return VideoProviderCapabilities(
            provider_name=self._name,
            modes=list(all_modes),
            models=self._models,
            deployment_mode=self._deployment,
        )

    def health(self) -> VideoProviderHealth:
        return VideoProviderHealth(
            provider_name=self._name,
            status=self._status,
            estimated_wait_seconds=5.0,
        )

    def list_models(self) -> list[VideoModelInfo]:
        return self._models

    def validate_request(self, request: VideoGenerationRequest):
        return None

    def estimate_cost(self, request: VideoGenerationRequest) -> VideoCostEstimate:
        return VideoCostEstimate(
            estimated_cost_usd=self._cost,
            confidence="estimate",
        )

    def submit(self, request, on_progress=None) -> VideoGenerationResult:
        return VideoGenerationResult(status="completed")

    def cancel(self, job_id: str) -> bool:
        return True

    def shutdown(self) -> None:
        pass


def _make_registry(*providers: MockProvider) -> VideoProviderRegistry:
    """Create a test registry with mock providers."""
    registry = VideoProviderRegistry()
    for p in providers:
        config = VideoProviderConfig(name=p.name, enabled=True, priority=50)
        registry.register(config, lambda _p=p: _p)  # type: ignore
    return registry


def _make_registry_proper(*providers: tuple[MockProvider, int]) -> VideoProviderRegistry:
    """Create registry using class registration pattern."""
    registry = VideoProviderRegistry()
    for provider, priority in providers:
        # Use a factory that returns existing instance
        class _Factory(CanonicalVideoProvider):
            pass

        # Direct injection for testing
        config = VideoProviderConfig(name=provider.name, enabled=True, priority=priority)
        registry._providers[provider.name] = provider
        registry._configs[provider.name] = config
    return registry


# =============================================================================
# Requirement Schema Tests
# =============================================================================


class TestRequirementSchema:

    @pytest.mark.unit
    def test_minimal_requirement(self):
        """Minimal requirement only needs mode."""
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO)
        assert req.mode == VideoMode.TEXT_TO_VIDEO
        assert req.duration_seconds is None
        assert req.max_cost_usd is None

    @pytest.mark.unit
    def test_full_requirement(self):
        """Full requirement with all fields populated."""
        req = GenerationRequirement(
            mode=VideoMode.IMAGE_TO_VIDEO,
            has_input_image=True,
            duration_seconds=5.0,
            width=1280,
            height=720,
            needs_camera_motion=True,
            needs_audio=True,
            deployment_preference=DeploymentPreference.SELF_HOSTED,
            privacy_level=PrivacyLevel.RESTRICTED,
            max_cost_usd=0.50,
        )
        assert req.needs_camera_motion is True
        assert req.privacy_level == PrivacyLevel.RESTRICTED


# =============================================================================
# Compatibility Matching Tests
# =============================================================================


class TestCompatibilityMatching:

    @pytest.mark.unit
    def test_basic_compatible_match(self):
        """Basic t2v request against a t2v provider → compatible."""
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO)
        provider = MockProvider()
        caps = provider.capabilities()
        health = provider.health()

        result = match_requirement_to_model(req, TEST_MODEL_A, caps, health, provider)
        assert result.compatibility == Compatibility.COMPATIBLE

    @pytest.mark.unit
    def test_mode_incompatible(self):
        """Requesting video_to_video on a t2v-only model → incompatible."""
        req = GenerationRequirement(mode=VideoMode.VIDEO_TO_VIDEO)
        provider = MockProvider()
        caps = provider.capabilities()
        health = provider.health()

        result = match_requirement_to_model(req, TEST_MODEL_A, caps, health, provider)
        assert result.compatibility == Compatibility.INCOMPATIBLE
        assert any(r.field == "mode" and r.verdict == Compatibility.INCOMPATIBLE for r in result.reasons)

    @pytest.mark.unit
    def test_duration_exceeded(self):
        """Duration beyond model max → incompatible."""
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO, duration_seconds=15.0)
        provider = MockProvider()
        caps = provider.capabilities()
        health = provider.health()

        result = match_requirement_to_model(req, TEST_MODEL_A, caps, health, provider)
        assert result.compatibility == Compatibility.INCOMPATIBLE
        assert any(r.field == "duration_seconds" for r in result.reasons)

    @pytest.mark.unit
    def test_resolution_exceeded(self):
        """Resolution beyond model max → incompatible."""
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO, width=3840, height=2160)
        provider = MockProvider()
        caps = provider.capabilities()
        health = provider.health()

        result = match_requirement_to_model(req, TEST_MODEL_A, caps, health, provider)
        assert result.compatibility == Compatibility.INCOMPATIBLE

    @pytest.mark.unit
    def test_camera_motion_degraded(self):
        """Camera motion needed but not supported → degraded."""
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO, needs_camera_motion=True)
        provider = MockProvider()
        caps = provider.capabilities()
        health = provider.health()

        result = match_requirement_to_model(req, TEST_MODEL_A, caps, health, provider)
        assert result.compatibility == Compatibility.DEGRADED

    @pytest.mark.unit
    def test_provider_unavailable(self):
        """Provider offline → unavailable classification."""
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO)
        provider = MockProvider(status=VideoProviderStatus.UNAVAILABLE)
        caps = provider.capabilities()
        health = provider.health()

        result = match_requirement_to_model(req, TEST_MODEL_A, caps, health, provider)
        assert result.compatibility == Compatibility.UNAVAILABLE

    @pytest.mark.unit
    def test_budget_exceeded(self):
        """Cost above budget → incompatible."""
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO, max_cost_usd=0.01)
        provider = MockProvider(cost=0.05)
        caps = provider.capabilities()
        health = provider.health()

        result = match_requirement_to_model(req, TEST_MODEL_A, caps, health, provider)
        assert result.compatibility == Compatibility.INCOMPATIBLE
        assert any(r.field == "budget" for r in result.reasons)

    @pytest.mark.unit
    def test_privacy_restricted_blocks_cloud(self):
        """Restricted privacy + cloud deployment → incompatible."""
        req = GenerationRequirement(
            mode=VideoMode.TEXT_TO_VIDEO,
            privacy_level=PrivacyLevel.RESTRICTED,
        )
        provider = MockProvider(deployment="cloud")
        caps = provider.capabilities()
        health = provider.health()

        result = match_requirement_to_model(req, TEST_MODEL_A, caps, health, provider)
        assert result.compatibility == Compatibility.INCOMPATIBLE
        assert any(r.field == "privacy" for r in result.reasons)

    @pytest.mark.unit
    def test_local_deployment_preference(self):
        """Local preference + cloud provider → incompatible."""
        req = GenerationRequirement(
            mode=VideoMode.TEXT_TO_VIDEO,
            deployment_preference=DeploymentPreference.LOCAL,
        )
        provider = MockProvider(deployment="cloud")
        caps = provider.capabilities()
        health = provider.health()

        result = match_requirement_to_model(req, TEST_MODEL_A, caps, health, provider)
        assert result.compatibility == Compatibility.INCOMPATIBLE

    @pytest.mark.unit
    def test_reasons_are_explainable(self):
        """Every reason has a human-readable message."""
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO, duration_seconds=15.0)
        provider = MockProvider()
        caps = provider.capabilities()
        health = provider.health()

        result = match_requirement_to_model(req, TEST_MODEL_A, caps, health, provider)
        for reason in result.reasons:
            assert reason.message  # Non-empty
            assert reason.field    # Non-empty


# =============================================================================
# Selection & Ranking Tests
# =============================================================================


class TestProviderSelection:

    @pytest.mark.unit
    def test_select_with_one_compatible(self):
        """Single compatible provider → recommended."""
        registry = _make_registry_proper((MockProvider(), 50))
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO)
        result = select_providers(req, registry=registry)

        assert len(result.compatible) == 1
        assert result.recommended is not None
        assert result.recommended.provider_name == "test-provider"

    @pytest.mark.unit
    def test_select_no_compatible(self):
        """No provider supports the mode → no recommendation."""
        provider = MockProvider(models=[TEST_MODEL_A])  # Only t2v/i2v
        registry = _make_registry_proper((provider, 50))
        req = GenerationRequirement(mode=VideoMode.VIDEO_TO_VIDEO)
        result = select_providers(req, registry=registry)

        assert len(result.compatible) == 0
        assert result.recommended is None

    @pytest.mark.unit
    def test_ranking_prefers_lower_cost(self):
        """Between two compatible providers, cheaper one is recommended."""
        cheap = MockProvider(name="cheap-provider", cost=0.02)
        expensive = MockProvider(name="expensive-provider", cost=0.10)
        registry = _make_registry_proper((cheap, 50), (expensive, 50))

        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO)
        result = select_providers(req, registry=registry)

        assert result.recommended is not None
        assert result.recommended.provider_name == "cheap-provider"

    @pytest.mark.unit
    def test_ranking_prefers_non_simulation(self):
        """Non-simulation providers preferred over simulation."""
        sim = MockProvider(name="simulation", cost=0.0)
        real = MockProvider(name="real-provider", cost=0.05)
        registry = _make_registry_proper((sim, 100), (real, 50))

        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO)
        result = select_providers(req, registry=registry)

        assert result.recommended is not None
        assert result.recommended.provider_name == "real-provider"

    @pytest.mark.unit
    def test_ranking_version_is_set(self):
        """Selection result includes ranking rule version."""
        registry = _make_registry_proper((MockProvider(), 50))
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO)
        result = select_providers(req, registry=registry)

        assert result.ranking_rule_version == RANKING_RULE_VERSION
        assert result.ranking_rule_version == "1.0.0"

    @pytest.mark.unit
    def test_multi_model_provider(self):
        """Provider with multiple models → each evaluated separately."""
        provider = MockProvider(name="multi", models=[TEST_MODEL_A, TEST_MODEL_B])
        registry = _make_registry_proper((provider, 50))

        req = GenerationRequirement(mode=VideoMode.VIDEO_TO_VIDEO)
        result = select_providers(req, registry=registry)

        # Model A doesn't support v2v, Model B does
        assert len(result.incompatible) == 1  # Model A
        assert len(result.compatible) == 1    # Model B
        assert result.incompatible[0].model_id == "test-model-a"
        assert result.compatible[0].model_id == "test-model-b"


# =============================================================================
# Server Enforcement Tests
# =============================================================================


class TestServerEnforcement:

    @pytest.mark.unit
    def test_enforce_compatible_passes(self):
        """Compatible provider/model passes enforcement."""
        registry = _make_registry_proper((MockProvider(), 50))
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO)

        compat = enforce_compatibility(req, "test-provider", "test-model-a", registry=registry)
        assert compat.compatibility == Compatibility.COMPATIBLE

    @pytest.mark.unit
    def test_enforce_incompatible_raises(self):
        """Incompatible request raises IncompatibleProviderError."""
        registry = _make_registry_proper((MockProvider(), 50))
        req = GenerationRequirement(mode=VideoMode.VIDEO_TO_VIDEO)

        with pytest.raises(IncompatibleProviderError) as exc_info:
            enforce_compatibility(req, "test-provider", "test-model-a", registry=registry)
        assert "test-provider" in str(exc_info.value)

    @pytest.mark.unit
    def test_enforce_unknown_provider_raises(self):
        """Non-existent provider raises LookupError."""
        registry = _make_registry_proper((MockProvider(), 50))
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO)

        with pytest.raises(LookupError):
            enforce_compatibility(req, "nonexistent", "any-model", registry=registry)

    @pytest.mark.unit
    def test_enforce_unknown_model_raises(self):
        """Non-existent model raises LookupError."""
        registry = _make_registry_proper((MockProvider(), 50))
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO)

        with pytest.raises(LookupError):
            enforce_compatibility(req, "test-provider", "nonexistent-model", registry=registry)

    @pytest.mark.unit
    def test_enforce_unavailable_raises(self):
        """Unavailable provider raises IncompatibleProviderError."""
        provider = MockProvider(status=VideoProviderStatus.UNAVAILABLE)
        registry = _make_registry_proper((provider, 50))
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO)

        with pytest.raises(IncompatibleProviderError):
            enforce_compatibility(req, "test-provider", "test-model-a", registry=registry)

    @pytest.mark.unit
    def test_enforce_degraded_passes(self):
        """Degraded compatibility still passes (with warning)."""
        registry = _make_registry_proper((MockProvider(), 50))
        req = GenerationRequirement(mode=VideoMode.TEXT_TO_VIDEO, needs_camera_motion=True)

        compat = enforce_compatibility(req, "test-provider", "test-model-a", registry=registry)
        assert compat.compatibility == Compatibility.DEGRADED


# =============================================================================
# Helper Tests
# =============================================================================


class TestHelpers:

    @pytest.mark.unit
    def test_parse_resolution(self):
        assert _parse_resolution("1280x720") == (1280, 720)
        assert _parse_resolution("1920x1080") == (1920, 1080)

    @pytest.mark.unit
    def test_parse_resolution_invalid(self):
        """Invalid resolution doesn't block (returns large default)."""
        assert _parse_resolution("unknown") == (9999, 9999)

    @pytest.mark.unit
    def test_classify_overall_priority(self):
        """INCOMPATIBLE trumps DEGRADED in overall classification."""
        reasons = [
            CompatibilityReason("a", "", "", Compatibility.COMPATIBLE, "ok"),
            CompatibilityReason("b", "", "", Compatibility.DEGRADED, "warn"),
            CompatibilityReason("c", "", "", Compatibility.INCOMPATIBLE, "fail"),
        ]
        assert _classify_overall(reasons) == Compatibility.INCOMPATIBLE

    @pytest.mark.unit
    def test_classify_overall_degraded(self):
        """Only DEGRADED + COMPATIBLE → DEGRADED."""
        reasons = [
            CompatibilityReason("a", "", "", Compatibility.COMPATIBLE, "ok"),
            CompatibilityReason("b", "", "", Compatibility.DEGRADED, "warn"),
        ]
        assert _classify_overall(reasons) == Compatibility.DEGRADED

    @pytest.mark.unit
    def test_classify_overall_compatible(self):
        """All COMPATIBLE → COMPATIBLE."""
        reasons = [
            CompatibilityReason("a", "", "", Compatibility.COMPATIBLE, "ok"),
            CompatibilityReason("b", "", "", Compatibility.COMPATIBLE, "ok"),
        ]
        assert _classify_overall(reasons) == Compatibility.COMPATIBLE
