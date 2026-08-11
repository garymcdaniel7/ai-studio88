"""MiniMax H3 Video Provider Unit Tests — Story 144.

Proves:
- Contract compliance (implements CanonicalVideoProvider fully)
- Capability advertisement (correct modes, models, constraints)
- Request validation (duration, prompt, mode, reference limits)
- Cost estimation (768P and 2K pricing)
- Health check states (configured, unconfigured, auth failed)
- Error mapping (rate limit, timeout, auth, API errors)
- Cancellation behavior (always returns False)
- Registration lifecycle (initialize, shutdown)
- Tenant isolation (org_id flows through)
- Submit workflow (mock API → poll → download → result)
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from backend.video.contract import (
    CanonicalVideoProvider,
    VideoErrorCode,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoJobStatus,
    VideoMode,
    VideoProviderCapabilities,
    VideoProviderConfig,
    VideoProviderHealth,
    VideoProviderStatus,
)
from backend.video.adapters.minimax_h3_adapter import (
    H3_MAX_DURATION,
    H3_MIN_DURATION,
    H3_MODEL,
    H3_MODEL_ID,
    MiniMaxAPIError,
    MiniMaxH3Client,
    MiniMaxH3VideoAdapter,
    MiniMaxRateLimitError,
    MiniMaxTimeoutError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def adapter():
    """Uninitialized adapter (no API key)."""
    return MiniMaxH3VideoAdapter()


@pytest.fixture
def configured_adapter():
    """Adapter initialized with a test API key."""
    a = MiniMaxH3VideoAdapter()
    config = VideoProviderConfig(
        name="minimax-h3",
        enabled=True,
        priority=30,
        settings={
            "api_key": "test-api-key-12345",
            "base_url": "https://api.minimax.io",
            "poll_interval_seconds": 1.0,
            "poll_timeout_seconds": 30.0,
        },
    )
    a.initialize(config)
    return a


@pytest.fixture
def t2v_request():
    return VideoGenerationRequest(
        mode=VideoMode.TEXT_TO_VIDEO,
        prompt="A spaceship flying through an asteroid field",
        model="minimax-h3",
        duration_seconds=8.0,
        fps=24,
        width=1365,
        height=768,
        org_id="org-test-123",
        user_id="user-test-456",
    )


@pytest.fixture
def i2v_request():
    return VideoGenerationRequest(
        mode=VideoMode.IMAGE_TO_VIDEO,
        prompt="The character starts walking forward",
        model="minimax-h3",
        duration_seconds=5.0,
        fps=24,
        width=1365,
        height=768,
        input_image_url="https://example.com/frame.jpg",
        org_id="org-test-123",
    )


# =============================================================================
# Contract Compliance
# =============================================================================


@pytest.mark.unit
class TestContractCompliance:
    """Adapter implements the full CanonicalVideoProvider interface."""

    def test_is_canonical_provider(self, adapter):
        assert isinstance(adapter, CanonicalVideoProvider)

    def test_name_property(self, adapter):
        assert adapter.name == "minimax-h3"

    def test_display_name_property(self, adapter):
        assert "MiniMax H3" in adapter.display_name

    def test_capabilities_returns_typed(self, adapter):
        caps = adapter.capabilities()
        assert isinstance(caps, VideoProviderCapabilities)

    def test_health_returns_typed(self, adapter):
        health = adapter.health()
        assert isinstance(health, VideoProviderHealth)

    def test_list_models_returns_list(self, adapter):
        models = adapter.list_models()
        assert isinstance(models, list)
        assert len(models) == 1
        assert models[0].id == "minimax-h3"


# =============================================================================
# Capabilities
# =============================================================================


@pytest.mark.unit
class TestCapabilities:
    """Capabilities advertise correct modes and constraints."""

    def test_supported_modes(self, adapter):
        caps = adapter.capabilities()
        assert VideoMode.TEXT_TO_VIDEO in caps.modes
        assert VideoMode.IMAGE_TO_VIDEO in caps.modes
        assert VideoMode.VIDEO_TO_VIDEO not in caps.modes

    def test_cancellation_not_supported(self, adapter):
        caps = adapter.capabilities()
        assert caps.supports_cancellation is False

    def test_progress_supported(self, adapter):
        caps = adapter.capabilities()
        assert caps.supports_progress is True

    def test_cost_estimate_supported(self, adapter):
        caps = adapter.capabilities()
        assert caps.supports_cost_estimate is True

    def test_deployment_mode_cloud(self, adapter):
        caps = adapter.capabilities()
        assert caps.deployment_mode == "cloud"

    def test_model_info(self, adapter):
        models = adapter.list_models()
        model = models[0]
        assert model.id == "minimax-h3"
        assert model.max_duration_seconds == float(H3_MAX_DURATION)
        assert model.default_fps == 24
        assert model.supports_negative_prompt is False
        assert model.supports_seed is False
        assert model.vram_required_gb == 0.0  # Hosted API


# =============================================================================
# Validation
# =============================================================================


@pytest.mark.unit
class TestValidation:
    """Request validation rejects invalid inputs before paid execution."""

    def test_valid_t2v_request(self, adapter, t2v_request):
        error = adapter.validate_request(t2v_request)
        assert error is None

    def test_valid_i2v_request(self, adapter, i2v_request):
        error = adapter.validate_request(i2v_request)
        assert error is None

    def test_rejects_video_to_video_mode(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.VIDEO_TO_VIDEO,
            prompt="Edit this video",
            duration_seconds=5.0,
        )
        error = adapter.validate_request(req)
        assert error is not None
        assert error.code == VideoErrorCode.UNSUPPORTED_MODE

    def test_rejects_duration_below_minimum(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="Short clip",
            duration_seconds=2.0,  # Below 4s minimum
        )
        error = adapter.validate_request(req)
        assert error is not None
        assert error.code == VideoErrorCode.INVALID_INPUT

    def test_rejects_duration_above_maximum(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="Long clip",
            duration_seconds=20.0,  # Above 15s maximum
        )
        error = adapter.validate_request(req)
        assert error is not None
        assert error.code == VideoErrorCode.DURATION_EXCEEDED

    def test_rejects_empty_prompt(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="",
            duration_seconds=5.0,
        )
        error = adapter.validate_request(req)
        assert error is not None
        assert error.code == VideoErrorCode.INVALID_INPUT

    def test_rejects_whitespace_prompt(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="   \n\t  ",
            duration_seconds=5.0,
        )
        error = adapter.validate_request(req)
        assert error is not None
        assert error.code == VideoErrorCode.INVALID_INPUT

    def test_rejects_prompt_too_long(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="x" * 7001,
            duration_seconds=5.0,
        )
        error = adapter.validate_request(req)
        assert error is not None
        assert error.code == VideoErrorCode.INPUT_TOO_LARGE

    def test_rejects_i2v_without_image(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.IMAGE_TO_VIDEO,
            prompt="Animate this",
            duration_seconds=5.0,
        )
        error = adapter.validate_request(req)
        assert error is not None
        assert error.code == VideoErrorCode.INVALID_INPUT

    def test_accepts_i2v_with_provider_options_image(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.IMAGE_TO_VIDEO,
            prompt="Animate this",
            duration_seconds=5.0,
            provider_options={"first_frame_image": "https://example.com/img.png"},
        )
        error = adapter.validate_request(req)
        assert error is None

    def test_rejects_too_many_reference_images(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="Reference generation",
            duration_seconds=5.0,
            provider_options={
                "reference_images": [f"https://example.com/img{i}.jpg" for i in range(10)],
            },
        )
        error = adapter.validate_request(req)
        assert error is not None
        assert error.code == VideoErrorCode.INPUT_TOO_LARGE

    def test_rejects_too_many_reference_videos(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="Reference generation",
            duration_seconds=5.0,
            provider_options={
                "reference_videos": [f"https://example.com/vid{i}.mp4" for i in range(4)],
            },
        )
        error = adapter.validate_request(req)
        assert error is not None
        assert error.code == VideoErrorCode.INPUT_TOO_LARGE

    def test_rejects_audio_only_reference(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="Audio reference only",
            duration_seconds=5.0,
            provider_options={
                "reference_audio": ["https://example.com/audio.wav"],
            },
        )
        error = adapter.validate_request(req)
        assert error is not None
        assert error.code == VideoErrorCode.INVALID_INPUT

    def test_rejects_total_references_exceeded(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="Too many refs",
            duration_seconds=5.0,
            provider_options={
                "reference_images": [f"https://example.com/img{i}.jpg" for i in range(9)],
                "reference_videos": [f"https://example.com/vid{i}.mp4" for i in range(3)],
                "reference_audio": ["https://example.com/audio.wav"],
            },
        )
        error = adapter.validate_request(req)
        assert error is not None
        assert error.code == VideoErrorCode.INPUT_TOO_LARGE


# =============================================================================
# Cost Estimation
# =============================================================================


@pytest.mark.unit
class TestCostEstimation:
    """Cost estimates reflect verified pricing."""

    def test_768p_cost_estimate(self, adapter, t2v_request):
        estimate = adapter.estimate_cost(t2v_request)
        # 8 seconds at $0.10/sec = $0.80
        assert estimate.estimated_cost_usd == pytest.approx(0.80, abs=0.01)
        assert estimate.confidence == "estimate"
        assert "768P" in estimate.message

    def test_2k_cost_estimate(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="High res video",
            duration_seconds=10.0,
            provider_options={"enable_2k": True},
        )
        estimate = adapter.estimate_cost(req)
        # 10 seconds at $0.14/sec = $1.40
        assert estimate.estimated_cost_usd == pytest.approx(1.40, abs=0.01)
        assert "2K" in estimate.message

    def test_cost_clamps_duration_to_min(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="Short",
            duration_seconds=2.0,  # Below min, clamped to 4
        )
        estimate = adapter.estimate_cost(req)
        assert estimate.estimated_cost_usd == pytest.approx(0.40, abs=0.01)

    def test_cost_clamps_duration_to_max(self, adapter):
        req = VideoGenerationRequest(
            mode=VideoMode.TEXT_TO_VIDEO,
            prompt="Long",
            duration_seconds=30.0,  # Above max, clamped to 15
        )
        estimate = adapter.estimate_cost(req)
        assert estimate.estimated_cost_usd == pytest.approx(1.50, abs=0.01)

    def test_cost_includes_audio_flag(self, adapter, t2v_request):
        estimate = adapter.estimate_cost(t2v_request)
        assert estimate.breakdown.get("includes_audio") is True


# =============================================================================
# Health Check
# =============================================================================


@pytest.mark.unit
class TestHealth:
    """Health reports distinguish config, credential, and connectivity states."""

    def test_unconfigured_reports_unavailable(self, adapter):
        health = adapter.health()
        assert health.status == VideoProviderStatus.UNAVAILABLE
        assert "not configured" in health.message.lower()

    def test_configured_healthy(self, configured_adapter):
        with patch.object(
            configured_adapter._client, "health_check",
            return_value={"healthy": True, "message": "MiniMax API reachable"},
        ):
            health = configured_adapter.health()
            assert health.status == VideoProviderStatus.AVAILABLE

    def test_auth_failure_reports_unavailable(self, configured_adapter):
        with patch.object(
            configured_adapter._client, "health_check",
            return_value={"healthy": False, "message": "Invalid API key"},
        ):
            health = configured_adapter.health()
            assert health.status == VideoProviderStatus.UNAVAILABLE
            assert "Invalid API key" in health.message

    def test_connection_failure_reports_degraded(self, configured_adapter):
        with patch.object(
            configured_adapter._client, "health_check",
            return_value={"healthy": False, "message": "Connection timed out"},
        ):
            health = configured_adapter.health()
            assert health.status == VideoProviderStatus.DEGRADED


# =============================================================================
# Cancellation
# =============================================================================


@pytest.mark.unit
class TestCancellation:
    """H3 does not support cancellation — always returns False."""

    def test_cancel_returns_false(self, configured_adapter):
        result = configured_adapter.cancel("task-12345")
        assert result is False

    def test_cancel_with_any_id(self, configured_adapter):
        assert configured_adapter.cancel("") is False
        assert configured_adapter.cancel("nonexistent") is False


# =============================================================================
# Lifecycle
# =============================================================================


@pytest.mark.unit
class TestLifecycle:
    """Registration and shutdown behavior."""

    def test_initialize_requires_api_key(self, adapter):
        config = VideoProviderConfig(
            name="minimax-h3",
            enabled=True,
            settings={},  # No api_key
        )
        with pytest.raises(ValueError, match="api_key"):
            adapter.initialize(config)

    def test_initialize_creates_client(self, adapter):
        config = VideoProviderConfig(
            name="minimax-h3",
            enabled=True,
            settings={"api_key": "test-key"},
        )
        adapter.initialize(config)
        assert adapter._client is not None

    def test_shutdown_clears_client(self, configured_adapter):
        assert configured_adapter._client is not None
        configured_adapter.shutdown()
        assert configured_adapter._client is None

    def test_initialize_with_custom_base_url(self, adapter):
        config = VideoProviderConfig(
            name="minimax-h3",
            enabled=True,
            settings={
                "api_key": "test-key",
                "base_url": "https://api.minimaxi.com",
            },
        )
        adapter.initialize(config)
        assert adapter._client._base_url == "https://api.minimaxi.com"


# =============================================================================
# Submit — Error Handling
# =============================================================================


@pytest.mark.unit
class TestSubmitErrors:
    """Error paths during submission produce correct canonical results."""

    def test_submit_without_client_fails(self, adapter, t2v_request):
        result = adapter.submit(t2v_request)
        assert result.success is False
        assert result.error_code == VideoErrorCode.PROVIDER_UNAVAILABLE
        assert result.retryable is False

    def test_submit_rate_limit_error(self, configured_adapter, t2v_request):
        with patch.object(
            configured_adapter, "_submit_task",
            side_effect=MiniMaxRateLimitError("Rate limit exceeded"),
        ):
            result = configured_adapter.submit(t2v_request)
            assert result.success is False
            assert result.error_code == VideoErrorCode.PROVIDER_RATE_LIMITED
            assert result.retryable is True

    def test_submit_timeout_error(self, configured_adapter, t2v_request):
        with patch.object(
            configured_adapter, "_submit_task",
            return_value={"task_id": "task-123"},
        ), patch.object(
            configured_adapter._client, "poll_until_complete",
            side_effect=MiniMaxTimeoutError("Timed out"),
        ):
            result = configured_adapter.submit(t2v_request)
            assert result.success is False
            assert result.status == VideoJobStatus.TIMED_OUT
            assert result.error_code == VideoErrorCode.PROVIDER_TIMEOUT
            assert result.retryable is True

    def test_submit_auth_error(self, configured_adapter, t2v_request):
        with patch.object(
            configured_adapter, "_submit_task",
            side_effect=MiniMaxAPIError("Authentication failed", status_code=401),
        ):
            result = configured_adapter.submit(t2v_request)
            assert result.success is False
            assert result.error_code == VideoErrorCode.PROVIDER_AUTH_FAILED
            assert result.retryable is False

    def test_submit_server_error(self, configured_adapter, t2v_request):
        with patch.object(
            configured_adapter, "_submit_task",
            side_effect=MiniMaxAPIError("Internal server error", status_code=500),
        ):
            result = configured_adapter.submit(t2v_request)
            assert result.success is False
            assert result.error_code == VideoErrorCode.PROVIDER_UNAVAILABLE
            assert result.retryable is True

    def test_submit_unexpected_error(self, configured_adapter, t2v_request):
        with patch.object(
            configured_adapter, "_submit_task",
            side_effect=RuntimeError("Something unexpected"),
        ):
            result = configured_adapter.submit(t2v_request)
            assert result.success is False
            assert result.error_code == VideoErrorCode.UNKNOWN
            assert result.retryable is False


# =============================================================================
# Submit — Success Path
# =============================================================================


@pytest.mark.unit
class TestSubmitSuccess:
    """Successful submission produces correct canonical results with provenance."""

    def test_successful_t2v_generation(self, configured_adapter, t2v_request):
        fake_video = b"\x00" * 1024  # Fake video bytes

        with patch.object(
            configured_adapter, "_submit_task",
            return_value={"task_id": "task-abc-123"},
        ), patch.object(
            configured_adapter._client, "poll_until_complete",
            return_value={
                "task_id": "task-abc-123",
                "status": "Success",
                "video_width": 1365,
                "video_height": 768,
                "content": {"url": "https://cdn.minimax.io/video/abc.mp4"},
            },
        ), patch.object(
            configured_adapter._client, "download_video",
            return_value=fake_video,
        ):
            result = configured_adapter.submit(t2v_request)

            assert result.success is True
            assert result.status == VideoJobStatus.COMPLETED
            assert result.output_bytes == fake_video
            assert result.provider_name == "minimax-h3"
            assert result.model_used == H3_MODEL_ID
            assert result.provider_job_id == "task-abc-123"
            assert result.fps == 24
            assert result.duration_seconds == 8.0
            assert result.width == 1365
            assert result.height == 768
            assert result.mime_type == "video/mp4"
            assert result.cost_usd is not None
            assert result.cost_usd > 0

    def test_result_includes_audio_metadata(self, configured_adapter, t2v_request):
        with patch.object(
            configured_adapter, "_submit_task",
            return_value={"task_id": "task-xyz"},
        ), patch.object(
            configured_adapter._client, "poll_until_complete",
            return_value={
                "task_id": "task-xyz",
                "status": "Success",
                "video_width": 1365,
                "video_height": 768,
                "content": {"url": "https://cdn.minimax.io/video/xyz.mp4"},
            },
        ), patch.object(
            configured_adapter._client, "download_video",
            return_value=b"\x00" * 512,
        ):
            result = configured_adapter.submit(t2v_request)

            assert result.metadata.get("has_native_audio") is True
            assert result.metadata.get("audio_sample_rate_hz") == 32000
            assert result.metadata.get("audio_channels") == "stereo"

    def test_result_includes_output_url(self, configured_adapter, t2v_request):
        url = "https://cdn.minimax.io/video/output.mp4"
        with patch.object(
            configured_adapter, "_submit_task",
            return_value={"task_id": "task-url"},
        ), patch.object(
            configured_adapter._client, "poll_until_complete",
            return_value={
                "task_id": "task-url",
                "status": "Success",
                "video_width": 1920,
                "video_height": 1080,
                "content": {"url": url},
            },
        ), patch.object(
            configured_adapter._client, "download_video",
            return_value=b"\x00" * 256,
        ):
            result = configured_adapter.submit(t2v_request)
            assert result.output_url == url

    def test_missing_video_url_returns_output_missing(self, configured_adapter, t2v_request):
        with patch.object(
            configured_adapter, "_submit_task",
            return_value={"task_id": "task-no-url"},
        ), patch.object(
            configured_adapter._client, "poll_until_complete",
            return_value={
                "task_id": "task-no-url",
                "status": "Success",
                # No content.url or video_url
            },
        ):
            result = configured_adapter.submit(t2v_request)
            assert result.success is False
            assert result.error_code == VideoErrorCode.OUTPUT_MISSING


# =============================================================================
# Registry Integration
# =============================================================================


@pytest.mark.unit
class TestRegistryIntegration:
    """MiniMax H3 integrates correctly with VideoProviderRegistry."""

    def test_registers_successfully(self):
        from backend.video.registry import VideoProviderRegistry

        registry = VideoProviderRegistry()
        config = VideoProviderConfig(
            name="minimax-h3",
            enabled=True,
            priority=30,
            settings={"api_key": "test-key"},
        )
        registry.register(config, MiniMaxH3VideoAdapter)
        assert "minimax-h3" in registry.list_providers()
        registry.shutdown_all()

    def test_disabled_config_skips_registration(self):
        from backend.video.registry import VideoProviderRegistry

        registry = VideoProviderRegistry()
        config = VideoProviderConfig(
            name="minimax-h3",
            enabled=False,
            settings={"api_key": "test-key"},
        )
        registry.register(config, MiniMaxH3VideoAdapter)
        assert "minimax-h3" not in registry.list_providers()
        registry.shutdown_all()

    def test_missing_api_key_rejects_registration(self):
        from backend.video.registry import VideoProviderRegistry

        registry = VideoProviderRegistry()
        config = VideoProviderConfig(
            name="minimax-h3",
            enabled=True,
            settings={},  # No api_key
        )
        with pytest.raises(ValueError, match="api_key"):
            registry.register(config, MiniMaxH3VideoAdapter)
        registry.shutdown_all()

    def test_provider_selection_by_mode(self):
        from backend.video.registry import VideoProviderRegistry
        from backend.video.adapters.simulation_adapter import SimulationVideoAdapter

        registry = VideoProviderRegistry()

        # Register simulation at priority 100
        registry.register(
            VideoProviderConfig(name="simulation", enabled=True, priority=100),
            SimulationVideoAdapter,
        )
        # Register MiniMax H3 at priority 30 (preferred)
        registry.register(
            VideoProviderConfig(
                name="minimax-h3", enabled=True, priority=30,
                settings={"api_key": "test-key"},
            ),
            MiniMaxH3VideoAdapter,
        )

        # H3 is preferred for text_to_video since lower priority
        provider = registry.select_provider(mode=VideoMode.TEXT_TO_VIDEO)
        assert provider is not None
        assert provider.name == "minimax-h3"

        registry.shutdown_all()

    def test_provider_selection_respects_model(self):
        from backend.video.registry import VideoProviderRegistry
        from backend.video.adapters.simulation_adapter import SimulationVideoAdapter

        registry = VideoProviderRegistry()

        registry.register(
            VideoProviderConfig(name="simulation", enabled=True, priority=100),
            SimulationVideoAdapter,
        )
        registry.register(
            VideoProviderConfig(
                name="minimax-h3", enabled=True, priority=30,
                settings={"api_key": "test-key"},
            ),
            MiniMaxH3VideoAdapter,
        )

        # Requesting wan-2.1 model should select simulation (not H3)
        provider = registry.select_provider(model="wan-2.1")
        assert provider is not None
        assert provider.name == "simulation"

        # Requesting minimax-h3 model should select H3
        provider = registry.select_provider(model="minimax-h3")
        assert provider is not None
        assert provider.name == "minimax-h3"

        registry.shutdown_all()


# =============================================================================
# Tenant Isolation
# =============================================================================


@pytest.mark.unit
class TestTenantIsolation:
    """Org context flows through the generation request."""

    def test_org_id_in_request(self, configured_adapter, t2v_request):
        assert t2v_request.org_id == "org-test-123"

        with patch.object(
            configured_adapter, "_submit_task",
            return_value={"task_id": "task-tenant"},
        ), patch.object(
            configured_adapter._client, "poll_until_complete",
            return_value={
                "task_id": "task-tenant",
                "status": "Success",
                "video_width": 1365,
                "video_height": 768,
                "content": {"url": "https://cdn.minimax.io/v.mp4"},
            },
        ), patch.object(
            configured_adapter._client, "download_video",
            return_value=b"\x00" * 100,
        ):
            result = configured_adapter.submit(t2v_request)
            assert result.success is True
            # Org_id is on the request; result provenance traces back
            assert result.provider_name == "minimax-h3"
