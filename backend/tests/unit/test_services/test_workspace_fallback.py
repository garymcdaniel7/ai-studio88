"""Unit tests for workspace fallback preferences service and router integration.

Tests:
- WorkspaceFallbackService: config get/set, privacy filtering, validation
- LLMRouter: privacy policy denial, STRICT mode blocking, ASK mode, AUTO mode
- Privacy override: AUTO → STRICT when all fallback targets are denied
- Routing decision logging with full context

No I/O, no DB — all tested in-memory.

Validates: Requirements R26.3, R26.4, R26.9, R102.1, R102.2, R102.3
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.providers.llm import (
    AllProvidersExhaustedError,
    CostTier,
    LLMResponse,
    LLMRouter,
    LanguageModelProvider,
    PrivacyLevel,
    ProviderCapabilities,
    RoutingRequirements,
    WorkspaceFallbackRouteConfig,
)
from app.services.workspace_fallback_service import (
    FallbackAskRequiredError,
    FallbackMode,
    FallbackStrictDeniedError,
    PrivacyPolicyViolationError,
    RoutingDecisionLog,
    WorkspaceFallbackConfig,
    WorkspaceFallbackService,
)


# =============================================================================
# Helpers
# =============================================================================

ORG_ID = uuid4()
USER_ID = uuid4()


def make_mock_provider(
    name: str = "mock",
    healthy: bool = True,
    privacy_level: PrivacyLevel = PrivacyLevel.CLOUD,
    response_content: str = "Hello",
    response_cost: float = 0.001,
) -> LanguageModelProvider:
    """Create a mock LanguageModelProvider for testing."""
    provider = MagicMock()
    provider.health_check = AsyncMock(return_value=healthy)
    provider.get_capabilities = MagicMock(
        return_value=ProviderCapabilities(
            name=name,
            models=["test-model"],
            max_context_tokens=8192,
            supports_streaming=True,
            supports_tool_use=False,
            supports_vision=False,
            privacy_level=privacy_level,
            cost_tier=CostTier.MEDIUM,
        )
    )
    provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=response_content,
            model="test-model",
            provider=name,
            tokens_used=50,
            latency_ms=100.0,
            cost_usd=response_cost,
        )
    )
    return provider


# =============================================================================
# Tests — WorkspaceFallbackService: In-Memory Config
# =============================================================================


@pytest.mark.unit
class TestWorkspaceFallbackServiceConfig:
    """Tests for WorkspaceFallbackService config management (in-memory mode)."""

    @pytest.mark.asyncio
    async def test_get_config_returns_defaults_when_no_config(self) -> None:
        """Service returns AUTO with no denied providers by default."""
        service = WorkspaceFallbackService()
        config = await service.get_config(org_id=ORG_ID)

        assert config.org_id == ORG_ID
        assert config.fallback_mode == FallbackMode.AUTO
        assert config.denied_providers == []

    @pytest.mark.asyncio
    async def test_get_config_returns_in_memory_config(self) -> None:
        """Service returns the in-memory config when provided."""
        custom_config = WorkspaceFallbackConfig(
            org_id=ORG_ID,
            fallback_mode=FallbackMode.STRICT,
            denied_providers=["openai", "anthropic"],
        )
        service = WorkspaceFallbackService(config=custom_config)
        config = await service.get_config(org_id=ORG_ID)

        assert config.fallback_mode == FallbackMode.STRICT
        assert config.denied_providers == ["openai", "anthropic"]

    @pytest.mark.asyncio
    async def test_set_config_updates_in_memory(self) -> None:
        """Service updates in-memory config correctly."""
        initial = WorkspaceFallbackConfig(org_id=ORG_ID)
        service = WorkspaceFallbackService(config=initial)

        result = await service.set_config(
            org_id=ORG_ID,
            fallback_mode=FallbackMode.ASK,
            denied_providers=["openrouter"],
            updated_by=USER_ID,
        )

        assert result.fallback_mode == FallbackMode.ASK
        assert result.denied_providers == ["openrouter"]

        # Verify persistence
        config = await service.get_config(org_id=ORG_ID)
        assert config.fallback_mode == FallbackMode.ASK


# =============================================================================
# Tests — WorkspaceFallbackService: Privacy Filtering
# =============================================================================


@pytest.mark.unit
class TestWorkspaceFallbackServicePrivacy:
    """Tests for privacy policy enforcement in the service."""

    def test_is_provider_denied_matches_case_insensitive(self) -> None:
        """Privacy check is case-insensitive."""
        config = WorkspaceFallbackConfig(
            org_id=ORG_ID,
            denied_providers=["OpenAI", "Anthropic"],
        )
        service = WorkspaceFallbackService(config=config)

        assert service.is_provider_denied("openai", config) is True
        assert service.is_provider_denied("OPENAI", config) is True
        assert service.is_provider_denied("Anthropic", config) is True
        assert service.is_provider_denied("ollama", config) is False

    def test_filter_allowed_providers(self) -> None:
        """Filter removes denied providers and keeps allowed ones."""
        config = WorkspaceFallbackConfig(
            org_id=ORG_ID,
            denied_providers=["openai", "anthropic"],
        )
        service = WorkspaceFallbackService(config=config)

        result = service.filter_allowed_providers(
            ["ollama", "openai", "anthropic", "openrouter"],
            config,
        )

        assert result == ["ollama", "openrouter"]

    def test_filter_allowed_providers_empty_denied(self) -> None:
        """With no denied providers, all are allowed."""
        config = WorkspaceFallbackConfig(org_id=ORG_ID, denied_providers=[])
        service = WorkspaceFallbackService(config=config)

        result = service.filter_allowed_providers(
            ["ollama", "openai"],
            config,
        )

        assert result == ["ollama", "openai"]


# =============================================================================
# Tests — WorkspaceFallbackService: Routing Decision Validation
# =============================================================================


@pytest.mark.unit
class TestWorkspaceFallbackServiceValidation:
    """Tests for validate_routing_decision enforcement."""

    def test_validate_allows_non_denied_provider(self) -> None:
        """Non-denied provider passes validation."""
        config = WorkspaceFallbackConfig(
            org_id=ORG_ID,
            denied_providers=["openai"],
        )
        service = WorkspaceFallbackService(config=config)

        # Should not raise
        service.validate_routing_decision(
            selected_provider="ollama",
            all_providers=["ollama", "openai"],
            config=config,
            is_fallback=False,
        )

    def test_validate_blocks_denied_provider(self) -> None:
        """Denied provider raises PrivacyPolicyViolationError."""
        config = WorkspaceFallbackConfig(
            org_id=ORG_ID,
            denied_providers=["openai"],
        )
        service = WorkspaceFallbackService(config=config)

        with pytest.raises(PrivacyPolicyViolationError) as exc_info:
            service.validate_routing_decision(
                selected_provider="openai",
                all_providers=["ollama", "openai"],
                config=config,
                is_fallback=False,
            )

        assert exc_info.value.denied_provider == "openai"

    def test_validate_strict_mode_blocks_fallback(self) -> None:
        """STRICT mode raises FallbackStrictDeniedError on fallback."""
        config = WorkspaceFallbackConfig(
            org_id=ORG_ID,
            fallback_mode=FallbackMode.STRICT,
            denied_providers=[],
        )
        service = WorkspaceFallbackService(config=config)

        with pytest.raises(FallbackStrictDeniedError) as exc_info:
            service.validate_routing_decision(
                selected_provider="openai",
                all_providers=["ollama", "openai"],
                config=config,
                is_fallback=True,
            )

        assert exc_info.value.preferred_provider == "ollama"

    def test_validate_ask_mode_raises_confirmation(self) -> None:
        """ASK mode raises FallbackAskRequiredError on fallback."""
        config = WorkspaceFallbackConfig(
            org_id=ORG_ID,
            fallback_mode=FallbackMode.ASK,
            denied_providers=[],
        )
        service = WorkspaceFallbackService(config=config)

        with pytest.raises(FallbackAskRequiredError) as exc_info:
            service.validate_routing_decision(
                selected_provider="openai",
                all_providers=["ollama", "openai"],
                config=config,
                is_fallback=True,
            )

        assert exc_info.value.preferred_provider == "ollama"
        assert "openai" in exc_info.value.alternative_providers

    def test_validate_auto_mode_allows_fallback(self) -> None:
        """AUTO mode allows fallback without raising."""
        config = WorkspaceFallbackConfig(
            org_id=ORG_ID,
            fallback_mode=FallbackMode.AUTO,
            denied_providers=[],
        )
        service = WorkspaceFallbackService(config=config)

        # Should not raise
        service.validate_routing_decision(
            selected_provider="openai",
            all_providers=["ollama", "openai"],
            config=config,
            is_fallback=True,
        )


# =============================================================================
# Tests — WorkspaceFallbackService: Privacy Override (AUTO → STRICT)
# =============================================================================


@pytest.mark.unit
class TestWorkspaceFallbackPrivacyOverride:
    """Tests for privacy policy overriding AUTO → STRICT."""

    def test_resolve_effective_mode_auto_stays_auto_when_allowed_exist(self) -> None:
        """AUTO remains AUTO when there are allowed providers available."""
        config = WorkspaceFallbackConfig(
            org_id=ORG_ID,
            fallback_mode=FallbackMode.AUTO,
            denied_providers=["openai"],
        )
        service = WorkspaceFallbackService(config=config)

        result = service.resolve_effective_mode(
            config,
            candidate_providers=["ollama", "openrouter"],
        )

        assert result == FallbackMode.AUTO

    def test_resolve_effective_mode_auto_becomes_strict_when_all_denied(self) -> None:
        """AUTO becomes STRICT when all candidate providers are denied (R26.9)."""
        config = WorkspaceFallbackConfig(
            org_id=ORG_ID,
            fallback_mode=FallbackMode.AUTO,
            denied_providers=["openai", "anthropic", "openrouter"],
        )
        service = WorkspaceFallbackService(config=config)

        result = service.resolve_effective_mode(
            config,
            candidate_providers=["openai", "anthropic", "openrouter"],
        )

        assert result == FallbackMode.STRICT

    def test_resolve_effective_mode_strict_stays_strict(self) -> None:
        """STRICT mode is preserved regardless of providers."""
        config = WorkspaceFallbackConfig(
            org_id=ORG_ID,
            fallback_mode=FallbackMode.STRICT,
            denied_providers=[],
        )
        service = WorkspaceFallbackService(config=config)

        result = service.resolve_effective_mode(
            config,
            candidate_providers=["ollama", "openai"],
        )

        assert result == FallbackMode.STRICT


# =============================================================================
# Tests — WorkspaceFallbackService: Routing Decision Logging
# =============================================================================


@pytest.mark.unit
class TestWorkspaceFallbackLogging:
    """Tests for routing decision logging."""

    def test_log_routing_decision_returns_record(self) -> None:
        """Logging returns a structured RoutingDecisionLog record."""
        service = WorkspaceFallbackService()

        decision = service.log_routing_decision(
            org_id=ORG_ID,
            provider="ollama",
            model="llama3.1:8b",
            routing_reason="first_healthy_capable",
            estimated_cost=0.0,
            fallback_chain=[],
            fallback_mode=FallbackMode.AUTO,
            privacy_override_applied=False,
        )

        assert isinstance(decision, RoutingDecisionLog)
        assert decision.org_id == ORG_ID
        assert decision.provider == "ollama"
        assert decision.model == "llama3.1:8b"
        assert decision.routing_reason == "first_healthy_capable"
        assert decision.fallback_mode == FallbackMode.AUTO
        assert decision.privacy_override_applied is False

    def test_log_routing_decision_with_privacy_override(self) -> None:
        """Logging captures privacy override flag."""
        service = WorkspaceFallbackService()

        decision = service.log_routing_decision(
            org_id=ORG_ID,
            provider="ollama",
            model="llama3.1:8b",
            routing_reason="privacy_override_strict",
            estimated_cost=0.0,
            fallback_chain=["openai:privacy_denied"],
            fallback_mode=FallbackMode.AUTO,
            privacy_override_applied=True,
        )

        assert decision.privacy_override_applied is True
        assert decision.fallback_chain == ["openai:privacy_denied"]


# =============================================================================
# Tests — LLMRouter with WorkspaceFallbackRouteConfig
# =============================================================================


@pytest.mark.unit
class TestLLMRouterWithFallbackConfig:
    """Tests for LLMRouter integration with workspace fallback preferences."""

    @pytest.mark.asyncio
    async def test_router_skips_denied_providers(self) -> None:
        """Router skips providers in the denied_providers list."""
        p1 = make_mock_provider("openai", healthy=True, response_content="openai response")
        p2 = make_mock_provider("ollama", healthy=True, response_content="ollama response")
        router = LLMRouter([p1, p2])

        fallback_cfg = WorkspaceFallbackRouteConfig(
            fallback_mode="auto",
            denied_providers=["openai"],
            org_id=str(ORG_ID),
        )

        response = await router.route("test", fallback_config=fallback_cfg)

        assert response.provider == "ollama"
        assert response.content == "ollama response"
        p1.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_router_all_denied_raises_exhausted(self) -> None:
        """Router raises AllProvidersExhaustedError when all providers denied."""
        p1 = make_mock_provider("openai", healthy=True)
        p2 = make_mock_provider("anthropic", healthy=True)
        router = LLMRouter([p1, p2])

        fallback_cfg = WorkspaceFallbackRouteConfig(
            fallback_mode="auto",
            denied_providers=["openai", "anthropic"],
            org_id=str(ORG_ID),
        )

        with pytest.raises(AllProvidersExhaustedError):
            await router.route("test", fallback_config=fallback_cfg)

    @pytest.mark.asyncio
    async def test_router_strict_mode_blocks_fallback(self) -> None:
        """STRICT mode raises AllProvidersExhaustedError when primary fails."""
        p1 = make_mock_provider("ollama", healthy=False)
        p2 = make_mock_provider("openai", healthy=True, response_content="fallback")
        router = LLMRouter([p1, p2])

        fallback_cfg = WorkspaceFallbackRouteConfig(
            fallback_mode="strict",
            denied_providers=[],
            org_id=str(ORG_ID),
        )

        with pytest.raises(AllProvidersExhaustedError, match="STRICT mode"):
            await router.route("test", fallback_config=fallback_cfg)

    @pytest.mark.asyncio
    async def test_router_auto_mode_allows_fallback(self) -> None:
        """AUTO mode allows fallback to next provider when primary fails."""
        p1 = make_mock_provider("ollama", healthy=False)
        p2 = make_mock_provider("openai", healthy=True, response_content="fallback ok")
        router = LLMRouter([p1, p2])

        fallback_cfg = WorkspaceFallbackRouteConfig(
            fallback_mode="auto",
            denied_providers=[],
            org_id=str(ORG_ID),
        )

        response = await router.route("test", fallback_config=fallback_cfg)

        assert response.provider == "openai"
        assert response.content == "fallback ok"

    @pytest.mark.asyncio
    async def test_router_auto_with_denied_fallback_treated_as_strict(self) -> None:
        """AUTO mode + denied fallback providers → privacy override to STRICT.

        When the primary is unhealthy and the only fallback targets are in
        the denied list, AUTO effectively becomes STRICT (R26.9).
        """
        p1 = make_mock_provider("ollama", healthy=False)
        p2 = make_mock_provider("openai", healthy=True, response_content="fallback")
        router = LLMRouter([p1, p2])

        fallback_cfg = WorkspaceFallbackRouteConfig(
            fallback_mode="auto",
            denied_providers=["openai"],
            org_id=str(ORG_ID),
        )

        # openai is the only fallback but it's denied → all exhausted
        with pytest.raises(AllProvidersExhaustedError):
            await router.route("test", fallback_config=fallback_cfg)

    @pytest.mark.asyncio
    async def test_router_without_fallback_config_works_normally(self) -> None:
        """Router works without fallback_config (backward compatible)."""
        p1 = make_mock_provider("ollama", healthy=True, response_content="normal")
        router = LLMRouter([p1])

        response = await router.route("test")

        assert response.provider == "ollama"
        assert response.content == "normal"

    @pytest.mark.asyncio
    async def test_router_privacy_denial_is_case_insensitive(self) -> None:
        """Privacy denied list comparison is case-insensitive."""
        p1 = make_mock_provider("OpenAI", healthy=True)
        p2 = make_mock_provider("ollama", healthy=True, response_content="local")
        router = LLMRouter([p1, p2])

        fallback_cfg = WorkspaceFallbackRouteConfig(
            fallback_mode="auto",
            denied_providers=["openai"],  # lowercase
            org_id=str(ORG_ID),
        )

        response = await router.route("test", fallback_config=fallback_cfg)

        assert response.provider == "ollama"
        p1.complete.assert_not_called()
