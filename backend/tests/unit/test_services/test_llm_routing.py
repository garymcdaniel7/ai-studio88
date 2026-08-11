"""Unit tests for LLM provider routing logic.

Tests the LLMRouter's priority-chain fallback behavior including:
- First healthy provider is selected
- Unhealthy providers are skipped
- Capability mismatches are skipped
- All-providers-exhausted raises error
- Privacy level filtering
- Cost budget filtering
- Routing decision logging

No I/O, no DB — all providers are mocked.

Validates: Requirements R26.1, R26.2, R26.5
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.llm import (
    AllProvidersExhaustedError,
    CostTier,
    LLMProviderError,
    LLMResponse,
    LLMRouter,
    LanguageModelProvider,
    PrivacyLevel,
    ProviderCapabilities,
    RoutingRequirements,
)


# =============================================================================
# Fixtures — mock providers
# =============================================================================


def make_mock_provider(
    name: str = "mock",
    healthy: bool = True,
    privacy_level: PrivacyLevel = PrivacyLevel.CLOUD,
    cost_tier: CostTier = CostTier.MEDIUM,
    supports_streaming: bool = True,
    supports_tool_use: bool = False,
    supports_vision: bool = False,
    response_content: str = "Hello",
    response_cost: float = 0.001,
    response_tokens: int = 50,
    raise_on_complete: Exception | None = None,
) -> LanguageModelProvider:
    """Create a mock LanguageModelProvider for testing."""
    provider = MagicMock()

    # health_check
    provider.health_check = AsyncMock(return_value=healthy)

    # get_capabilities
    provider.get_capabilities = MagicMock(
        return_value=ProviderCapabilities(
            name=name,
            models=["test-model"],
            max_context_tokens=8192,
            supports_streaming=supports_streaming,
            supports_tool_use=supports_tool_use,
            supports_vision=supports_vision,
            privacy_level=privacy_level,
            cost_tier=cost_tier,
        )
    )

    # complete
    if raise_on_complete:
        provider.complete = AsyncMock(side_effect=raise_on_complete)
    else:
        provider.complete = AsyncMock(
            return_value=LLMResponse(
                content=response_content,
                model="test-model",
                provider=name,
                tokens_used=response_tokens,
                latency_ms=100.0,
                cost_usd=response_cost,
            )
        )

    return provider


# =============================================================================
# Tests — Router Initialization
# =============================================================================


@pytest.mark.unit
class TestLLMRouterInit:
    """Tests for LLMRouter initialization."""

    def test_init_with_providers(self) -> None:
        """Router initializes with a list of providers."""
        providers = [make_mock_provider("a"), make_mock_provider("b")]
        router = LLMRouter(providers)
        assert router.provider_count == 2

    def test_init_empty_raises(self) -> None:
        """Router raises ValueError when initialized with no providers."""
        with pytest.raises(ValueError, match="at least one provider"):
            LLMRouter([])

    def test_provider_names(self) -> None:
        """Router reports ordered provider names."""
        providers = [
            make_mock_provider("ollama"),
            make_mock_provider("openai"),
            make_mock_provider("anthropic"),
        ]
        router = LLMRouter(providers)
        assert router.provider_names == ["ollama", "openai", "anthropic"]


# =============================================================================
# Tests — Routing: Happy Path
# =============================================================================


@pytest.mark.unit
class TestLLMRouterHappyPath:
    """Tests for successful routing scenarios."""

    @pytest.mark.asyncio
    async def test_routes_to_first_healthy_provider(self) -> None:
        """Router selects the first healthy provider in the chain."""
        p1 = make_mock_provider("primary", healthy=True, response_content="from primary")
        p2 = make_mock_provider("fallback", healthy=True, response_content="from fallback")
        router = LLMRouter([p1, p2])

        response = await router.route("test prompt")

        assert response.provider == "primary"
        assert response.content == "from primary"
        # Second provider should not be attempted
        p2.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_routes_with_default_requirements(self) -> None:
        """Router works with no explicit requirements."""
        p1 = make_mock_provider("ollama", healthy=True)
        router = LLMRouter([p1])

        response = await router.route("hello")

        assert response.provider == "ollama"
        p1.complete.assert_called_once_with(
            prompt="hello", model=None, max_tokens=2048, temperature=0.7
        )

    @pytest.mark.asyncio
    async def test_routes_with_custom_requirements(self) -> None:
        """Router passes requirements to the provider's complete method."""
        p1 = make_mock_provider("openai", healthy=True)
        router = LLMRouter([p1])
        reqs = RoutingRequirements(model="gpt-4o", max_tokens=1000, temperature=0.3)

        response = await router.route("test", requirements=reqs)

        p1.complete.assert_called_once_with(
            prompt="test", model="gpt-4o", max_tokens=1000, temperature=0.3
        )


# =============================================================================
# Tests — Routing: Fallback Behavior
# =============================================================================


@pytest.mark.unit
class TestLLMRouterFallback:
    """Tests for fallback when primary providers fail."""

    @pytest.mark.asyncio
    async def test_skips_unhealthy_provider(self) -> None:
        """Router skips an unhealthy provider and tries the next."""
        p1 = make_mock_provider("primary", healthy=False)
        p2 = make_mock_provider("fallback", healthy=True, response_content="fallback works")
        router = LLMRouter([p1, p2])

        response = await router.route("test")

        assert response.provider == "fallback"
        assert response.content == "fallback works"
        p1.complete.assert_not_called()  # Never attempted completion

    @pytest.mark.asyncio
    async def test_skips_provider_with_exception_on_health(self) -> None:
        """Router skips provider that raises exception during health check."""
        p1 = make_mock_provider("flaky", healthy=True)
        p1.health_check = AsyncMock(side_effect=Exception("connection refused"))
        p2 = make_mock_provider("stable", healthy=True, response_content="stable ok")
        router = LLMRouter([p1, p2])

        response = await router.route("test")

        assert response.provider == "stable"

    @pytest.mark.asyncio
    async def test_skips_provider_with_completion_error(self) -> None:
        """Router falls back when a provider's complete() raises."""
        import httpx

        p1 = make_mock_provider(
            "broken",
            healthy=True,
            raise_on_complete=httpx.ConnectError("timeout"),
        )
        p2 = make_mock_provider("backup", healthy=True, response_content="backup ok")
        router = LLMRouter([p1, p2])

        response = await router.route("test")

        assert response.provider == "backup"
        assert response.content == "backup ok"

    @pytest.mark.asyncio
    async def test_all_providers_exhausted_raises(self) -> None:
        """Router raises AllProvidersExhaustedError when all fail."""
        p1 = make_mock_provider("a", healthy=False)
        p2 = make_mock_provider("b", healthy=False)
        router = LLMRouter([p1, p2])

        with pytest.raises(AllProvidersExhaustedError, match="All providers exhausted"):
            await router.route("test")

    @pytest.mark.asyncio
    async def test_single_provider_unhealthy_raises(self) -> None:
        """Router raises when the only provider is unhealthy."""
        p1 = make_mock_provider("lone", healthy=False)
        router = LLMRouter([p1])

        with pytest.raises(AllProvidersExhaustedError):
            await router.route("test")


# =============================================================================
# Tests — Capability Filtering
# =============================================================================


@pytest.mark.unit
class TestLLMRouterCapabilityFiltering:
    """Tests for capability-based provider filtering."""

    @pytest.mark.asyncio
    async def test_filters_by_privacy_level_local(self) -> None:
        """Router skips cloud providers when local privacy is required."""
        cloud = make_mock_provider("openai", healthy=True, privacy_level=PrivacyLevel.CLOUD)
        local = make_mock_provider("ollama", healthy=True, privacy_level=PrivacyLevel.LOCAL)
        router = LLMRouter([cloud, local])
        reqs = RoutingRequirements(privacy_level=PrivacyLevel.LOCAL)

        response = await router.route("sensitive data", requirements=reqs)

        assert response.provider == "ollama"
        cloud.complete.assert_not_called()
        cloud.health_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_filters_by_streaming_requirement(self) -> None:
        """Router skips providers that don't support streaming."""
        no_stream = make_mock_provider("no-stream", healthy=True, supports_streaming=False)
        with_stream = make_mock_provider("streamer", healthy=True, supports_streaming=True)
        router = LLMRouter([no_stream, with_stream])
        reqs = RoutingRequirements(require_streaming=True)

        response = await router.route("test", requirements=reqs)

        assert response.provider == "streamer"

    @pytest.mark.asyncio
    async def test_filters_by_tool_use_requirement(self) -> None:
        """Router skips providers that don't support tool use."""
        no_tools = make_mock_provider("basic", healthy=True, supports_tool_use=False)
        with_tools = make_mock_provider("advanced", healthy=True, supports_tool_use=True)
        router = LLMRouter([no_tools, with_tools])
        reqs = RoutingRequirements(require_tool_use=True)

        response = await router.route("test", requirements=reqs)

        assert response.provider == "advanced"

    @pytest.mark.asyncio
    async def test_filters_by_vision_requirement(self) -> None:
        """Router skips providers without vision when vision is required."""
        no_vision = make_mock_provider("text-only", healthy=True, supports_vision=False)
        with_vision = make_mock_provider("multimodal", healthy=True, supports_vision=True)
        router = LLMRouter([no_vision, with_vision])
        reqs = RoutingRequirements(require_vision=True)

        response = await router.route("describe image", requirements=reqs)

        assert response.provider == "multimodal"

    @pytest.mark.asyncio
    async def test_all_filtered_by_capability_raises(self) -> None:
        """Router raises when no provider satisfies capabilities."""
        cloud_only = make_mock_provider("cloud", healthy=True, privacy_level=PrivacyLevel.CLOUD)
        router = LLMRouter([cloud_only])
        reqs = RoutingRequirements(privacy_level=PrivacyLevel.LOCAL)

        with pytest.raises(AllProvidersExhaustedError):
            await router.route("test", requirements=reqs)


# =============================================================================
# Tests — Cost Filtering
# =============================================================================


@pytest.mark.unit
class TestLLMRouterCostFiltering:
    """Tests for cost-budget-based provider selection."""

    @pytest.mark.asyncio
    async def test_skips_provider_exceeding_cost_budget(self) -> None:
        """Router skips provider whose response cost exceeds budget."""
        expensive = make_mock_provider("expensive", healthy=True, response_cost=0.50)
        cheap = make_mock_provider("cheap", healthy=True, response_cost=0.001)
        router = LLMRouter([expensive, cheap])
        reqs = RoutingRequirements(max_cost_usd=0.01)

        response = await router.route("test", requirements=reqs)

        assert response.provider == "cheap"
        assert response.cost_usd <= 0.01

    @pytest.mark.asyncio
    async def test_all_exceed_cost_budget_raises(self) -> None:
        """Router raises when all providers exceed the cost budget."""
        expensive = make_mock_provider("a", healthy=True, response_cost=1.0)
        also_expensive = make_mock_provider("b", healthy=True, response_cost=0.50)
        router = LLMRouter([expensive, also_expensive])
        reqs = RoutingRequirements(max_cost_usd=0.001)

        with pytest.raises(AllProvidersExhaustedError):
            await router.route("test", requirements=reqs)


# =============================================================================
# Tests — Dataclass Behavior
# =============================================================================


@pytest.mark.unit
class TestLLMDataclasses:
    """Tests for LLM provider dataclass behavior."""

    def test_llm_response_immutable(self) -> None:
        """LLMResponse is frozen — cannot mutate after creation."""
        response = LLMResponse(
            content="hi",
            model="test",
            provider="mock",
            tokens_used=10,
            latency_ms=50.0,
            cost_usd=0.0,
        )
        with pytest.raises(AttributeError):
            response.content = "mutated"  # type: ignore[misc]

    def test_provider_capabilities_immutable(self) -> None:
        """ProviderCapabilities is frozen."""
        caps = ProviderCapabilities(name="test")
        with pytest.raises(AttributeError):
            caps.name = "changed"  # type: ignore[misc]

    def test_routing_requirements_defaults(self) -> None:
        """RoutingRequirements has sensible defaults."""
        reqs = RoutingRequirements()
        assert reqs.model is None
        assert reqs.max_tokens == 2048
        assert reqs.temperature == 0.7
        assert reqs.privacy_level is None
        assert reqs.max_cost_usd is None
        assert reqs.require_streaming is False


# =============================================================================
# Tests — Provider Capabilities
# =============================================================================


@pytest.mark.unit
class TestProviderCapabilities:
    """Tests for individual provider capability declarations."""

    def test_ollama_capabilities(self) -> None:
        """OllamaProvider declares local privacy and free cost."""
        from app.providers.llm import OllamaProvider

        provider = OllamaProvider()
        caps = provider.get_capabilities()
        assert caps.name == "ollama"
        assert caps.privacy_level == PrivacyLevel.LOCAL
        assert caps.cost_tier == CostTier.FREE

    def test_openai_capabilities(self) -> None:
        """OpenAIProvider declares cloud privacy and high cost."""
        from app.providers.llm import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        caps = provider.get_capabilities()
        assert caps.name == "openai"
        assert caps.privacy_level == PrivacyLevel.CLOUD
        assert caps.cost_tier == CostTier.HIGH
        assert caps.supports_tool_use is True
        assert caps.supports_vision is True

    def test_anthropic_capabilities(self) -> None:
        """AnthropicProvider declares cloud privacy and high cost."""
        from app.providers.llm import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        caps = provider.get_capabilities()
        assert caps.name == "anthropic"
        assert caps.privacy_level == PrivacyLevel.CLOUD
        assert caps.cost_tier == CostTier.HIGH
        assert caps.supports_tool_use is True

    def test_openrouter_capabilities(self) -> None:
        """OpenRouterProvider declares cloud privacy and medium cost."""
        from app.providers.llm import OpenRouterProvider

        provider = OpenRouterProvider(api_key="test-key")
        caps = provider.get_capabilities()
        assert caps.name == "openrouter"
        assert caps.privacy_level == PrivacyLevel.CLOUD
        assert caps.cost_tier == CostTier.MEDIUM


# =============================================================================
# Tests — Protocol Compliance
# =============================================================================


@pytest.mark.unit
class TestProtocolCompliance:
    """Tests that concrete providers satisfy the LanguageModelProvider protocol."""

    def test_ollama_is_language_model_provider(self) -> None:
        """OllamaProvider satisfies LanguageModelProvider protocol."""
        from app.providers.llm import OllamaProvider

        provider = OllamaProvider()
        assert isinstance(provider, LanguageModelProvider)

    def test_openai_is_language_model_provider(self) -> None:
        """OpenAIProvider satisfies LanguageModelProvider protocol."""
        from app.providers.llm import OpenAIProvider

        provider = OpenAIProvider(api_key="test")
        assert isinstance(provider, LanguageModelProvider)

    def test_anthropic_is_language_model_provider(self) -> None:
        """AnthropicProvider satisfies LanguageModelProvider protocol."""
        from app.providers.llm import AnthropicProvider

        provider = AnthropicProvider(api_key="test")
        assert isinstance(provider, LanguageModelProvider)

    def test_openrouter_is_language_model_provider(self) -> None:
        """OpenRouterProvider satisfies LanguageModelProvider protocol."""
        from app.providers.llm import OpenRouterProvider

        provider = OpenRouterProvider(api_key="test")
        assert isinstance(provider, LanguageModelProvider)
