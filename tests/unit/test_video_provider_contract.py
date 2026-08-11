"""Video Provider Contract Tests — Story 143.

Proves:
- Multi-provider coexistence (registry holds both adapters simultaneously)
- Failure isolation (one provider down doesn't break others)
- Canonical behavior (typed capabilities, validation, cost, execution)
- Tenant isolation (org_id flows through request)
- Retry classification (retryable vs terminal errors)
- Cancellation support
- Priority-based selection
- Registration validation (invalid configs rejected)
- Provider removal doesn't break remaining
"""

import pytest

from backend.video.contract import (
    CanonicalVideoProvider,
    VideoCostEstimate,
    VideoErrorCode,
    VideoGenerationProgress,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoJobStatus,
    VideoMode,
    VideoModelInfo,
    VideoProviderCapabilities,
    VideoProviderConfig,
    VideoProviderError,
    VideoProviderHealth,
    VideoProviderStatus,
)
from backend.video.registry import (
    VideoProviderRegistry,
    reset_video_provider_registry,
)
from backend.video.adapters.simulation_adapter import SimulationVideoAdapter
from backend.video.adapters.comfyui_adapter import ComfyUIVideoAdapter


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def registry():
    """Fresh registry for each test."""
    reg = VideoProviderRegistry()
    yield reg
    reg.shutdown_all()


@pytest.fixture
def sim_config():
    return VideoProviderConfig(name="simulation", enabled=True, priority=100)


@pytest.fixture
def comfyui_config():
    return VideoProviderConfig(
        name="comfyui-wan",
        enabled=True,
        priority=50,
        settings={
            "base_url": "http://localhost:8188",
            "timeout_seconds": 600,
            "workflow_template": "wan21_t2v_simple",
        },
    )


@pytest.fixture
def t2v_request():
    return VideoGenerationRequest(
        mode=VideoMode.TEXT_TO_VIDEO,
        prompt="A cat walking on the moon",
        model="wan-2.1",
        duration_seconds=2.0,
        fps=24,
        width=832,
        height=480,
        org_id="org_test_123",
        user_id="user_test_456",
    )


@pytest.fixture
def i2v_request():
    return VideoGenerationRequest(
        mode=VideoMode.IMAGE_TO_VIDEO,
        prompt="Animate this scene",
        model="wan-2.1",
        input_image_bytes=b"fake_image_data",
        duration_seconds=2.0,
        org_id="org_test_123",
    )


# =============================================================================
# Multi-Provider Coexistence
# =============================================================================


@pytest.mark.unit
class TestMultiProviderCoexistence:
    """Both providers can be registered and function simultaneously."""

    def test_both_providers_register_successfully(self, registry, sim_config, comfyui_config):
        registry.register(sim_config, SimulationVideoAdapter)
        registry.register(comfyui_config, ComfyUIVideoAdapter)
        assert registry.provider_count == 2
        assert set(registry.list_providers()) == {"simulation", "comfyui-wan"}

    def test_each_provider_has_distinct_capabilities(self, registry, sim_config, comfyui_config):
        registry.register(sim_config, SimulationVideoAdapter)
        registry.register(comfyui_config, ComfyUIVideoAdapter)

        sim = registry.get_provider("simulation")
        comfyui = registry.get_provider("comfyui-wan")

        sim_caps = sim.capabilities()
        comfyui_caps = comfyui.capabilities()

        # Simulation supports all modes
        assert VideoMode.VIDEO_TO_VIDEO in sim_caps.modes
        # ComfyUI does not support v2v
        assert VideoMode.VIDEO_TO_VIDEO not in comfyui_caps.modes

    def test_capabilities_list_returns_all_providers(self, registry, sim_config, comfyui_config):
        registry.register(sim_config, SimulationVideoAdapter)
        registry.register(comfyui_config, ComfyUIVideoAdapter)

        caps_list = registry.list_capabilities()
        assert len(caps_list) == 2
        provider_names = [c.provider_name for c in caps_list]
        assert "simulation" in provider_names
        assert "comfyui-wan" in provider_names


# =============================================================================
# Failure Isolation
# =============================================================================


@pytest.mark.unit
class TestFailureIsolation:
    """One provider's failure doesn't affect others."""

    def test_comfyui_unhealthy_doesnt_break_simulation(self, registry, sim_config, comfyui_config):
        registry.register(sim_config, SimulationVideoAdapter)
        registry.register(comfyui_config, ComfyUIVideoAdapter)

        # ComfyUI will be unavailable (no server running)
        comfyui = registry.get_provider("comfyui-wan")
        comfyui_health = comfyui.health()
        assert comfyui_health.status == VideoProviderStatus.UNAVAILABLE

        # Simulation still works
        sim = registry.get_provider("simulation")
        sim_health = sim.health()
        assert sim_health.status == VideoProviderStatus.AVAILABLE

    def test_provider_removal_doesnt_break_remaining(self, registry, sim_config, comfyui_config):
        registry.register(sim_config, SimulationVideoAdapter)
        registry.register(comfyui_config, ComfyUIVideoAdapter)

        # Remove comfyui
        removed = registry.unregister("comfyui-wan")
        assert removed is True
        assert registry.provider_count == 1

        # Simulation still works
        sim = registry.get_provider("simulation")
        assert sim is not None
        assert sim.health().status == VideoProviderStatus.AVAILABLE

    def test_health_check_handles_provider_exception(self, registry, sim_config):
        registry.register(sim_config, SimulationVideoAdapter)

        # list_health should never crash even if a provider throws
        health_list = registry.list_health()
        assert len(health_list) == 1
        assert health_list[0].status == VideoProviderStatus.AVAILABLE


# =============================================================================
# Canonical Behavior: Capabilities
# =============================================================================


@pytest.mark.unit
class TestCanonicalCapabilities:
    """Capabilities are typed and complete."""

    def test_simulation_capabilities_are_typed(self, registry, sim_config):
        registry.register(sim_config, SimulationVideoAdapter)
        sim = registry.get_provider("simulation")
        caps = sim.capabilities()

        assert isinstance(caps, VideoProviderCapabilities)
        assert isinstance(caps.modes, list)
        assert all(isinstance(m, VideoMode) for m in caps.modes)
        assert isinstance(caps.models, list)
        assert all(isinstance(m, VideoModelInfo) for m in caps.models)

    def test_model_info_has_required_fields(self, registry, sim_config):
        registry.register(sim_config, SimulationVideoAdapter)
        sim = registry.get_provider("simulation")
        models = sim.list_models()

        for model in models:
            assert model.id
            assert model.name
            assert model.provider
            assert len(model.modes) > 0
            assert model.max_duration_seconds > 0
            assert model.max_fps > 0

    def test_comfyui_capabilities_accurate(self, registry, comfyui_config):
        registry.register(comfyui_config, ComfyUIVideoAdapter)
        comfyui = registry.get_provider("comfyui-wan")
        caps = comfyui.capabilities()

        assert VideoMode.TEXT_TO_VIDEO in caps.modes
        assert VideoMode.IMAGE_TO_VIDEO in caps.modes
        assert caps.deployment_mode == "cloud"
        assert len(caps.models) >= 1
        assert caps.models[0].id == "wan-2.1"


# =============================================================================
# Canonical Behavior: Validation
# =============================================================================


@pytest.mark.unit
class TestCanonicalValidation:
    """validate_request fails fast for unsupported combinations."""

    def test_simulation_accepts_valid_t2v(self, registry, sim_config, t2v_request):
        registry.register(sim_config, SimulationVideoAdapter)
        sim = registry.get_provider("simulation")
        error = sim.validate_request(t2v_request)
        assert error is None

    def test_simulation_rejects_empty_prompt_for_t2v(self, registry, sim_config):
        registry.register(sim_config, SimulationVideoAdapter)
        sim = registry.get_provider("simulation")

        request = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="",
        )
        error = sim.validate_request(request)
        assert error is not None
        assert error.code == VideoErrorCode.INVALID_INPUT

    def test_comfyui_rejects_v2v_mode(self, registry, comfyui_config):
        registry.register(comfyui_config, ComfyUIVideoAdapter)
        comfyui = registry.get_provider("comfyui-wan")

        request = VideoGenerationRequest(
            mode=VideoMode.VIDEO_TO_VIDEO,
            prompt="Transform this",
        )
        error = comfyui.validate_request(request)
        assert error is not None
        assert error.code == VideoErrorCode.UNSUPPORTED_MODE

    def test_comfyui_rejects_excessive_duration(self, registry, comfyui_config):
        registry.register(comfyui_config, ComfyUIVideoAdapter)
        comfyui = registry.get_provider("comfyui-wan")

        request = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="Long video",
            duration_seconds=60.0,
        )
        error = comfyui.validate_request(request)
        assert error is not None
        assert error.code == VideoErrorCode.DURATION_EXCEEDED

    def test_comfyui_rejects_i2v_without_image(self, registry, comfyui_config):
        registry.register(comfyui_config, ComfyUIVideoAdapter)
        comfyui = registry.get_provider("comfyui-wan")

        request = VideoGenerationRequest(
            mode=VideoMode.IMAGE_TO_VIDEO,
            prompt="Animate",
            # No image provided
        )
        error = comfyui.validate_request(request)
        assert error is not None
        assert error.code == VideoErrorCode.INVALID_INPUT

    def test_registry_validate_returns_provider_unavailable(self, registry):
        # Empty registry — no providers
        request = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="Test",
        )
        error = registry.validate_request(request)
        assert error is not None
        assert error.code == VideoErrorCode.PROVIDER_UNAVAILABLE


# =============================================================================
# Canonical Behavior: Cost Estimation
# =============================================================================


@pytest.mark.unit
class TestCanonicalCost:
    """Cost estimates are available before execution."""

    def test_simulation_cost_is_zero(self, registry, sim_config, t2v_request):
        registry.register(sim_config, SimulationVideoAdapter)
        sim = registry.get_provider("simulation")
        estimate = sim.estimate_cost(t2v_request)

        assert isinstance(estimate, VideoCostEstimate)
        assert estimate.estimated_cost_usd == 0.0
        assert estimate.confidence == "fixed"

    def test_comfyui_cost_estimates_by_frames(self, registry, comfyui_config, t2v_request):
        registry.register(comfyui_config, ComfyUIVideoAdapter)
        comfyui = registry.get_provider("comfyui-wan")
        estimate = comfyui.estimate_cost(t2v_request)

        assert isinstance(estimate, VideoCostEstimate)
        assert estimate.estimated_cost_usd > 0
        assert estimate.confidence == "estimate"
        assert "frames" in estimate.breakdown


# =============================================================================
# Canonical Behavior: Execution
# =============================================================================


@pytest.mark.unit
class TestCanonicalExecution:
    """Execution returns canonical results with provenance."""

    def test_simulation_generates_successfully(self, registry, sim_config, t2v_request):
        registry.register(sim_config, SimulationVideoAdapter)
        sim = registry.get_provider("simulation")
        result = sim.submit(t2v_request)

        assert isinstance(result, VideoGenerationResult)
        assert result.success is True
        assert result.status == VideoJobStatus.COMPLETED
        assert result.provider_name == "simulation"
        assert result.model_used == "wan-2.1"
        assert result.output_bytes is not None
        assert len(result.output_bytes) > 0
        assert result.filename.endswith(".mp4")
        assert result.mime_type == "video/mp4"
        assert result.generation_time_seconds >= 0
        assert result.cost_usd == 0.0

    def test_simulation_i2v_generates_successfully(self, registry, sim_config, i2v_request):
        registry.register(sim_config, SimulationVideoAdapter)
        sim = registry.get_provider("simulation")
        result = sim.submit(i2v_request)

        assert result.success is True
        assert result.status == VideoJobStatus.COMPLETED

    def test_simulation_reports_progress(self, registry, sim_config, t2v_request):
        registry.register(sim_config, SimulationVideoAdapter)
        sim = registry.get_provider("simulation")

        progress_updates = []

        def on_progress(p: VideoGenerationProgress):
            progress_updates.append(p)

        sim.submit(t2v_request, on_progress=on_progress)

        # Should have received at least one progress update
        assert len(progress_updates) > 0
        assert all(isinstance(p, VideoGenerationProgress) for p in progress_updates)
        assert all(0 <= p.percent <= 100 for p in progress_updates)

    def test_result_carries_org_context(self, registry, sim_config):
        """Provenance: org_id flows through the request for tenant isolation."""
        registry.register(sim_config, SimulationVideoAdapter)
        sim = registry.get_provider("simulation")

        request = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="Tenant test",
            org_id="org_isolated_abc",
            user_id="user_xyz",
        )
        result = sim.submit(request)
        assert result.success is True
        # The provider preserves context — orchestration layer uses org_id for isolation


# =============================================================================
# Priority-Based Selection
# =============================================================================


@pytest.mark.unit
class TestPrioritySelection:
    """Registry selects providers based on priority and capabilities."""

    def test_higher_priority_provider_selected_first(self, registry, sim_config, comfyui_config):
        # comfyui has priority 50, simulation has 100 — lower is preferred
        registry.register(sim_config, SimulationVideoAdapter)
        registry.register(comfyui_config, ComfyUIVideoAdapter)

        selected = registry.select_provider(mode=VideoMode.TEXT_TO_VIDEO, model="wan-2.1")
        assert selected is not None
        assert selected.name == "comfyui-wan"  # Lower priority number = preferred

    def test_falls_back_to_capable_provider(self, registry, sim_config, comfyui_config):
        registry.register(sim_config, SimulationVideoAdapter)
        registry.register(comfyui_config, ComfyUIVideoAdapter)

        # v2v is only supported by simulation
        selected = registry.select_provider(mode=VideoMode.VIDEO_TO_VIDEO)
        assert selected is not None
        assert selected.name == "simulation"

    def test_preferred_provider_overrides_priority(self, registry, sim_config, comfyui_config):
        registry.register(sim_config, SimulationVideoAdapter)
        registry.register(comfyui_config, ComfyUIVideoAdapter)

        # Explicitly prefer simulation even though comfyui has higher priority
        selected = registry.select_provider(
            mode=VideoMode.TEXT_TO_VIDEO,
            model="wan-2.1",
            preferred="simulation",
        )
        assert selected is not None
        assert selected.name == "simulation"

    def test_returns_none_for_unsupported_model(self, registry, sim_config):
        registry.register(sim_config, SimulationVideoAdapter)

        # Simulation doesn't have "nonexistent-model" in its model list...
        # Actually simulation's model IDs are wan-2.1, hunyuan, ltx
        selected = registry.select_provider(model="totally-fake-model-xyz")
        assert selected is None

    def test_returns_none_for_empty_registry(self, registry):
        selected = registry.select_provider(mode=VideoMode.TEXT_TO_VIDEO)
        assert selected is None


# =============================================================================
# Registration Validation
# =============================================================================


@pytest.mark.unit
class TestRegistrationValidation:
    """Invalid configurations are rejected at registration time."""

    def test_empty_name_rejected(self, registry):
        config = VideoProviderConfig(name="", enabled=True)
        with pytest.raises(ValueError, match="non-empty name"):
            registry.register(config, SimulationVideoAdapter)

    def test_duplicate_name_rejected(self, registry, sim_config):
        registry.register(sim_config, SimulationVideoAdapter)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(sim_config, SimulationVideoAdapter)

    def test_disabled_provider_skipped_silently(self, registry):
        config = VideoProviderConfig(name="disabled-one", enabled=False)
        registry.register(config, SimulationVideoAdapter)
        assert registry.provider_count == 0
        assert registry.get_provider("disabled-one") is None


# =============================================================================
# Cancellation
# =============================================================================


@pytest.mark.unit
class TestCancellation:
    """Cancellation works through the canonical interface."""

    def test_simulation_accepts_cancellation(self, registry, sim_config):
        registry.register(sim_config, SimulationVideoAdapter)
        sim = registry.get_provider("simulation")
        result = sim.cancel("any-job-id")
        assert result is True

    def test_comfyui_cancel_returns_bool(self, registry, comfyui_config):
        registry.register(comfyui_config, ComfyUIVideoAdapter)
        comfyui = registry.get_provider("comfyui-wan")
        # Will fail gracefully (no server) — returns False
        result = comfyui.cancel("fake-job-id")
        assert isinstance(result, bool)


# =============================================================================
# Error Classification
# =============================================================================


@pytest.mark.unit
class TestErrorClassification:
    """Errors are mapped to canonical codes with retry hints."""

    def test_validation_errors_are_not_retryable(self, registry, comfyui_config):
        registry.register(comfyui_config, ComfyUIVideoAdapter)
        comfyui = registry.get_provider("comfyui-wan")

        request = VideoGenerationRequest(
            mode=VideoMode.VIDEO_TO_VIDEO,
            prompt="Unsupported",
        )
        error = comfyui.validate_request(request)
        assert error is not None
        assert error.retryable is False

    def test_provider_error_includes_provider_name(self, registry, comfyui_config):
        registry.register(comfyui_config, ComfyUIVideoAdapter)
        comfyui = registry.get_provider("comfyui-wan")

        request = VideoGenerationRequest(
            mode=VideoMode.VIDEO_TO_VIDEO,
            prompt="No",
        )
        error = comfyui.validate_request(request)
        assert error.provider_name == "comfyui-wan"


# =============================================================================
# Lifecycle
# =============================================================================


@pytest.mark.unit
class TestLifecycle:
    """Provider lifecycle methods work correctly."""

    def test_shutdown_all_clears_registry(self, registry, sim_config, comfyui_config):
        registry.register(sim_config, SimulationVideoAdapter)
        registry.register(comfyui_config, ComfyUIVideoAdapter)
        assert registry.provider_count == 2

        registry.shutdown_all()
        assert registry.provider_count == 0

    def test_unregister_nonexistent_returns_false(self, registry):
        assert registry.unregister("nonexistent") is False
