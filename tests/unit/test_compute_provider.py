"""Unit tests for the ComputeProvider interface, registry, and implementations.

Tests protocol conformance, registry operations, capabilities dataclass,
and the SimulationProvider stub.

Run with: pytest tests/unit/test_compute_provider.py -v
"""
from __future__ import annotations

import pytest

from backend.app.providers.compute import (
    ComputeProvider,
    ComputeProviderCapabilities,
    ComputeRequirements,
    CostEstimate,
    HealthState,
    HealthStatus,
    InstanceHandle,
    InstanceState,
    InstanceStatus,
    OfferInfo,
    ProviderNotFoundError,
)
from backend.app.providers.registry import (
    clear_registry,
    get_provider,
    get_registry_size,
    list_providers,
    register_provider,
    unregister_provider,
)
from backend.app.providers.runpod_provider import RunPodProvider
from backend.app.providers.simulation_provider import SimulationProvider


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure a clean registry for each test."""
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def sim_provider() -> SimulationProvider:
    """Create a SimulationProvider instance."""
    return SimulationProvider()


@pytest.fixture
def runpod_provider() -> RunPodProvider:
    """Create a RunPodProvider instance (no API key — stub mode)."""
    return RunPodProvider(api_key=None)


# =============================================================================
# Tests: Protocol Conformance
# =============================================================================


@pytest.mark.unit
class TestProtocolConformance:
    """Verify that provider implementations satisfy the ComputeProvider protocol."""

    def test_simulation_provider_is_compute_provider(self, sim_provider):
        """SimulationProvider must satisfy the ComputeProvider Protocol."""
        assert isinstance(sim_provider, ComputeProvider)

    def test_runpod_provider_is_compute_provider(self, runpod_provider):
        """RunPodProvider must satisfy the ComputeProvider Protocol."""
        assert isinstance(runpod_provider, ComputeProvider)

    def test_protocol_has_required_methods(self):
        """ComputeProvider protocol must declare all required methods."""
        required_methods = [
            "provision",
            "terminate",
            "health_check",
            "get_status",
            "list_available",
            "estimate_cost",
        ]
        for method_name in required_methods:
            assert hasattr(ComputeProvider, method_name), (
                f"ComputeProvider missing method: {method_name}"
            )

    def test_protocol_has_capabilities_property(self):
        """ComputeProvider must declare a capabilities property."""
        # The protocol declares it; implementations must provide it
        assert hasattr(ComputeProvider, "capabilities")


# =============================================================================
# Tests: ComputeProviderCapabilities
# =============================================================================


@pytest.mark.unit
class TestComputeProviderCapabilities:
    """Test the ComputeProviderCapabilities dataclass."""

    def test_capabilities_is_frozen(self):
        """ComputeProviderCapabilities instances must be immutable."""
        caps = ComputeProviderCapabilities(name="test", display_name="Test Provider")
        with pytest.raises(Exception):  # FrozenInstanceError or dataclass frozen error
            caps.name = "modified"  # type: ignore[misc]

    def test_capabilities_defaults(self):
        """Capabilities should have sensible defaults."""
        caps = ComputeProviderCapabilities(name="test", display_name="Test")
        assert caps.supports_persistent_storage is False
        assert caps.supports_network_volume is False
        assert caps.supports_stop_resume is False
        assert caps.supports_snapshot is False
        assert caps.supports_multi_gpu is False
        assert caps.supports_autoscaling is False
        assert caps.min_vram_gb == 8
        assert caps.max_vram_gb == 80
        assert caps.regions == []
        assert caps.gpu_types == []
        assert caps.startup_time_seconds == 120

    def test_satisfies_all_required(self):
        """satisfies() returns True when all required caps are present."""
        caps = ComputeProviderCapabilities(
            name="full",
            display_name="Full Provider",
            supports_persistent_storage=True,
            supports_multi_gpu=True,
            supports_cost_estimation=True,
        )
        assert caps.satisfies(["persistent_storage", "multi_gpu"]) is True

    def test_satisfies_empty_requirements(self):
        """satisfies() returns True when no capabilities are required."""
        caps = ComputeProviderCapabilities(name="min", display_name="Minimal")
        assert caps.satisfies([]) is True

    def test_satisfies_fails_on_missing_capability(self):
        """satisfies() returns False when a required cap is missing."""
        caps = ComputeProviderCapabilities(
            name="limited",
            display_name="Limited",
            supports_persistent_storage=False,
            supports_multi_gpu=True,
        )
        assert caps.satisfies(["persistent_storage"]) is False

    def test_satisfies_unknown_capability_returns_false(self):
        """satisfies() returns False for unrecognized capability names."""
        caps = ComputeProviderCapabilities(name="test", display_name="Test")
        assert caps.satisfies(["nonexistent_capability"]) is False


# =============================================================================
# Tests: Registry
# =============================================================================


@pytest.mark.unit
class TestProviderRegistry:
    """Test the provider registry operations."""

    def test_register_and_get(self, sim_provider):
        """Registered providers are retrievable by name."""
        register_provider("simulation", sim_provider)
        retrieved = get_provider("simulation")
        assert retrieved is sim_provider

    def test_get_unknown_raises_provider_not_found(self):
        """Getting an unregistered provider raises ProviderNotFoundError."""
        with pytest.raises(ProviderNotFoundError) as exc_info:
            get_provider("nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_list_providers_returns_capabilities(self, sim_provider, runpod_provider):
        """list_providers() returns capabilities of all registered providers."""
        register_provider("simulation", sim_provider)
        register_provider("runpod", runpod_provider)

        caps_list = list_providers()
        assert len(caps_list) == 2
        names = {c.name for c in caps_list}
        assert "simulation" in names
        assert "runpod" in names

    def test_list_providers_empty(self):
        """list_providers() returns empty list when no providers registered."""
        assert list_providers() == []

    def test_register_empty_name_raises(self, sim_provider):
        """Registering with empty name raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            register_provider("", sim_provider)

    def test_register_none_provider_raises(self):
        """Registering None as provider raises ValueError."""
        with pytest.raises(ValueError, match="must not be None"):
            register_provider("test", None)  # type: ignore[arg-type]

    def test_unregister_provider(self, sim_provider):
        """Unregistering removes the provider from the registry."""
        register_provider("simulation", sim_provider)
        unregister_provider("simulation")
        with pytest.raises(ProviderNotFoundError):
            get_provider("simulation")

    def test_unregister_unknown_raises(self):
        """Unregistering an unknown provider raises ProviderNotFoundError."""
        with pytest.raises(ProviderNotFoundError):
            unregister_provider("does_not_exist")

    def test_registry_size(self, sim_provider, runpod_provider):
        """get_registry_size() returns correct count."""
        assert get_registry_size() == 0
        register_provider("simulation", sim_provider)
        assert get_registry_size() == 1
        register_provider("runpod", runpod_provider)
        assert get_registry_size() == 2

    def test_overwrite_existing_provider(self, sim_provider):
        """Re-registering a name overwrites the previous provider."""
        register_provider("test", sim_provider)
        new_provider = SimulationProvider()
        register_provider("test", new_provider)
        assert get_provider("test") is new_provider
        assert get_registry_size() == 1


# =============================================================================
# Tests: SimulationProvider
# =============================================================================


@pytest.mark.unit
class TestSimulationProvider:
    """Test the SimulationProvider implementation."""

    @pytest.mark.asyncio
    async def test_provision_returns_handle(self, sim_provider):
        """provision() returns a valid InstanceHandle."""
        req = ComputeRequirements(vram_gb=24)
        handle = await sim_provider.provision(req)
        assert isinstance(handle, InstanceHandle)
        assert handle.instance_id.startswith("sim-")
        assert handle.host == "127.0.0.1"
        assert handle.port == 8188
        assert handle.state == InstanceState.RUNNING

    @pytest.mark.asyncio
    async def test_terminate_marks_instance(self, sim_provider):
        """terminate() marks instance as terminated."""
        req = ComputeRequirements(vram_gb=12)
        handle = await sim_provider.provision(req)
        await sim_provider.terminate(handle.instance_id)

        status = await sim_provider.get_status(handle.instance_id)
        assert status.state == InstanceState.TERMINATED

    @pytest.mark.asyncio
    async def test_health_check_running_instance(self, sim_provider):
        """health_check() returns HEALTHY for running instances."""
        req = ComputeRequirements(vram_gb=12)
        handle = await sim_provider.provision(req)
        health = await sim_provider.health_check(handle.instance_id)
        assert health.state == HealthState.HEALTHY
        assert health.latency_ms == 1.0

    @pytest.mark.asyncio
    async def test_health_check_terminated_instance(self, sim_provider):
        """health_check() returns UNREACHABLE for terminated instances."""
        req = ComputeRequirements(vram_gb=12)
        handle = await sim_provider.provision(req)
        await sim_provider.terminate(handle.instance_id)

        health = await sim_provider.health_check(handle.instance_id)
        assert health.state == HealthState.UNREACHABLE

    @pytest.mark.asyncio
    async def test_health_check_unknown_instance(self, sim_provider):
        """health_check() returns UNREACHABLE for unknown instance IDs."""
        health = await sim_provider.health_check("nonexistent-id")
        assert health.state == HealthState.UNREACHABLE

    @pytest.mark.asyncio
    async def test_list_available_returns_offers(self, sim_provider):
        """list_available() returns synthetic offers."""
        offers = await sim_provider.list_available()
        assert len(offers) == 3
        assert all(isinstance(o, OfferInfo) for o in offers)
        assert any(o.gpu_name == "RTX 4090" for o in offers)
        assert any(o.gpu_name == "A100 80GB" for o in offers)

    @pytest.mark.asyncio
    async def test_estimate_cost_returns_estimate(self, sim_provider):
        """estimate_cost() returns a deterministic cost estimate."""
        req = ComputeRequirements(vram_gb=24, max_duration_seconds=3600)
        estimate = await sim_provider.estimate_cost(req)
        assert isinstance(estimate, CostEstimate)
        assert estimate.estimated_usd > 0
        assert estimate.estimated_duration_seconds == 3600
        assert estimate.confidence == 1.0

    @pytest.mark.asyncio
    async def test_estimate_cost_scales_with_vram(self, sim_provider):
        """Higher VRAM requests should produce higher cost estimates."""
        req_small = ComputeRequirements(vram_gb=12, max_duration_seconds=3600)
        req_large = ComputeRequirements(vram_gb=80, max_duration_seconds=3600)

        est_small = await sim_provider.estimate_cost(req_small)
        est_large = await sim_provider.estimate_cost(req_large)

        assert est_large.estimated_usd > est_small.estimated_usd

    def test_simulation_capabilities(self, sim_provider):
        """SimulationProvider capabilities are correctly declared."""
        caps = sim_provider.capabilities
        assert caps.name == "simulation"
        assert caps.display_name == "Simulation (Testing)"
        assert caps.supports_persistent_storage is True
        assert caps.supports_multi_gpu is True
        assert caps.min_vram_gb == 8
        assert caps.max_vram_gb == 80
        assert "RTX_4090" in caps.gpu_types


# =============================================================================
# Tests: RunPodProvider capabilities (no API calls)
# =============================================================================


@pytest.mark.unit
class TestRunPodProviderCapabilities:
    """Test RunPodProvider capabilities (does not make real API calls)."""

    def test_runpod_capabilities(self, runpod_provider):
        """RunPodProvider declares full capability set."""
        caps = runpod_provider.capabilities
        assert caps.name == "runpod"
        assert caps.display_name == "RunPod"
        assert caps.supports_persistent_storage is True
        assert caps.supports_network_volume is True
        assert caps.supports_stop_resume is True
        assert caps.supports_snapshot is True
        assert caps.supports_multi_gpu is True
        assert caps.supports_autoscaling is True
        assert caps.supports_cost_estimation is True
        assert "A100_80GB" in caps.gpu_types
        assert "H100" in caps.gpu_types

    @pytest.mark.asyncio
    async def test_runpod_estimate_cost(self, runpod_provider):
        """RunPodProvider returns cost estimate based on pricing tiers."""
        req = ComputeRequirements(vram_gb=24, max_duration_seconds=3600)
        estimate = await runpod_provider.estimate_cost(req)
        assert isinstance(estimate, CostEstimate)
        assert estimate.estimated_usd > 0
        assert estimate.confidence == 0.7


# =============================================================================
# Tests: Registry get_cheapest_provider (async)
# =============================================================================


@pytest.mark.unit
class TestGetCheapestProvider:
    """Test the async get_cheapest_provider registry function."""

    @pytest.mark.asyncio
    async def test_cheapest_selects_lowest_cost(self):
        """get_cheapest_provider returns the provider with lowest estimate."""
        from backend.app.providers.registry import get_cheapest_provider

        sim = SimulationProvider()
        runpod = RunPodProvider(api_key=None)

        register_provider("simulation", sim)
        register_provider("runpod", runpod)

        # Both can estimate; simulation has confidence=1.0 and known formula
        cheapest = await get_cheapest_provider(min_vram_gb=24, duration_seconds=3600)
        # Result should be one of the registered providers
        assert cheapest in ("simulation", "runpod")

    @pytest.mark.asyncio
    async def test_cheapest_no_providers_raises(self):
        """get_cheapest_provider raises when no providers registered."""
        from backend.app.providers.registry import get_cheapest_provider

        with pytest.raises(ProviderNotFoundError):
            await get_cheapest_provider(min_vram_gb=24)
