"""Property tests for Privacy Restriction Enforcement (Property 17).

Property 17: Privacy Restriction Enforcement
    *For any* LLM routing or job dispatch for a workspace with privacy restriction R,
    the selected provider SHALL NOT be in the workspace's denied_providers list.

    Additional invariants tested:
    - Privacy restrictions override AUTO fallback mode (R26.9)
    - When all providers are denied, the system fails gracefully (R103.3)
    - Single denied provider, multiple denied, and all denied scenarios
    - Denied providers are never contacted (no health check, no completion call)

**Validates: Requirements R103.2, R26.9**

No I/O, no DB — all providers are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.providers.llm import (
    AllProvidersExhaustedError,
    CostTier,
    FallbackPreference,
    LLMResponse,
    LLMRouter,
    LanguageModelProvider,
    PrivacyAwareLLMRouter,
    PrivacyLevel,
    PrivacyPolicyViolationError,
    ProviderCapabilities,
    RoutingRequirements,
    WorkspaceLLMConfig,
)


# =============================================================================
# Test Fixtures — Mock Providers
# =============================================================================

# Canonical provider names used across the platform
ALL_PROVIDER_NAMES = ["ollama", "openai", "anthropic", "openrouter", "lmstudio"]


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
) -> LanguageModelProvider:
    """Create a mock LanguageModelProvider for testing."""
    provider = MagicMock()

    provider.health_check = AsyncMock(return_value=healthy)

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
# Hypothesis Strategies
# =============================================================================

# Strategy for provider names (1 to 5 unique providers from a realistic set)
provider_name_strategy = st.sampled_from(ALL_PROVIDER_NAMES)

# Strategy for a list of unique provider names (at least 1, up to all 5)
provider_list_strategy = st.lists(
    provider_name_strategy,
    min_size=1,
    max_size=5,
    unique=True,
)

# Strategy for a non-empty subset of providers to deny
denied_providers_strategy = st.lists(
    provider_name_strategy,
    min_size=1,
    max_size=5,
    unique=True,
)

# Strategy for fallback preference
fallback_preference_strategy = st.sampled_from(list(FallbackPreference))


# =============================================================================
# Property 17: Privacy Restriction Enforcement
# Feature: production-revamp, Property 17
# =============================================================================


class TestProperty17PrivacyRestrictionEnforcement:
    """Property 17: Selected provider NEVER in workspace's denied_providers list.

    For any LLM routing decision when a workspace has privacy restrictions
    (denied_providers list), the system must NEVER select or contact a denied
    provider. Privacy restrictions override AUTO fallback mode.

    **Validates: Requirements R103.2, R26.9**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        available_providers=provider_list_strategy,
        denied_subset=provider_list_strategy,
        fallback_pref=fallback_preference_strategy,
    )
    async def test_selected_provider_never_in_denied_list(
        self,
        available_providers: list[str],
        denied_subset: list[str],
        fallback_pref: FallbackPreference,
    ) -> None:
        """The selected provider is NEVER in the denied_providers list.

        **Validates: Requirements R103.2**

        Property: For ANY combination of available providers and denied providers,
        when routing succeeds, the returned response.provider is NOT in
        the workspace's denied_providers list.
        """
        # At least one provider must NOT be denied for routing to succeed
        non_denied = [p for p in available_providers if p not in denied_subset]
        assume(len(non_denied) > 0)

        providers = [make_mock_provider(name=n) for n in available_providers]
        router = PrivacyAwareLLMRouter(providers)
        config = WorkspaceLLMConfig(
            fallback_preference=fallback_pref,
            denied_providers=denied_subset,
        )

        response = await router.route("test prompt", workspace_config=config)

        # INVARIANT: selected provider is NOT in the denied list
        assert response.provider not in denied_subset

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        available_providers=provider_list_strategy,
        fallback_pref=fallback_preference_strategy,
    )
    async def test_all_providers_denied_fails_gracefully(
        self,
        available_providers: list[str],
        fallback_pref: FallbackPreference,
    ) -> None:
        """When ALL providers are denied, the system raises PrivacyPolicyViolationError.

        **Validates: Requirements R103.3**

        Property: For ANY set of available providers, when ALL are in the
        denied_providers list, routing raises PrivacyPolicyViolationError.
        """
        # Deny ALL available providers
        denied_all = list(available_providers)

        providers = [make_mock_provider(name=n) for n in available_providers]
        router = PrivacyAwareLLMRouter(providers)
        config = WorkspaceLLMConfig(
            fallback_preference=fallback_pref,
            denied_providers=denied_all,
        )

        with pytest.raises(PrivacyPolicyViolationError):
            await router.route("test prompt", workspace_config=config)

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        available_providers=provider_list_strategy,
        denied_subset=provider_list_strategy,
    )
    async def test_denied_providers_never_contacted(
        self,
        available_providers: list[str],
        denied_subset: list[str],
    ) -> None:
        """Denied providers are never contacted — no health check, no completion.

        **Validates: Requirements R103.2, R26.9**

        Property: For ANY combination of providers and denied list,
        providers in the denied list have zero calls to health_check()
        and complete().
        """
        non_denied = [p for p in available_providers if p not in denied_subset]
        assume(len(non_denied) > 0)

        providers = [make_mock_provider(name=n) for n in available_providers]
        router = PrivacyAwareLLMRouter(providers)
        config = WorkspaceLLMConfig(
            fallback_preference=FallbackPreference.AUTO,
            denied_providers=denied_subset,
        )

        await router.route("test prompt", workspace_config=config)

        # Verify denied providers were NEVER contacted
        denied_set = set(denied_subset)
        for provider in providers:
            name = provider.get_capabilities().name
            if name in denied_set:
                provider.health_check.assert_not_called()
                provider.complete.assert_not_called()

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        available_providers=provider_list_strategy,
        denied_subset=provider_list_strategy,
    )
    async def test_privacy_overrides_auto_fallback(
        self,
        available_providers: list[str],
        denied_subset: list[str],
    ) -> None:
        """Privacy restrictions override AUTO fallback (R26.9).

        **Validates: Requirements R26.9**

        Property: Even with fallback_preference=AUTO, denied providers are
        never selected. If AUTO would have fallen back to a denied provider,
        the system treats it as STRICT (fails rather than violates privacy).
        """
        non_denied = [p for p in available_providers if p not in denied_subset]

        # Make all non-denied providers unhealthy so AUTO would want to
        # fall back to denied ones
        providers = []
        for name in available_providers:
            if name in denied_subset:
                # Denied but healthy — should still not be selected
                providers.append(make_mock_provider(name=name, healthy=True))
            else:
                # Non-denied but unhealthy
                providers.append(make_mock_provider(name=name, healthy=False))

        router = PrivacyAwareLLMRouter(providers)
        config = WorkspaceLLMConfig(
            fallback_preference=FallbackPreference.AUTO,
            denied_providers=denied_subset,
        )

        if non_denied:
            # All non-denied are unhealthy, so routing should fail
            # but it must NOT fall back to a denied provider
            with pytest.raises((AllProvidersExhaustedError, PrivacyPolicyViolationError)):
                await router.route("test prompt", workspace_config=config)
        else:
            # All providers are denied
            with pytest.raises(PrivacyPolicyViolationError):
                await router.route("test prompt", workspace_config=config)

    @pytest.mark.unit
    @settings(max_examples=50)
    @given(
        available_providers=provider_list_strategy,
        denied_subset=provider_list_strategy,
    )
    async def test_single_denied_provider_skipped_correctly(
        self,
        available_providers: list[str],
        denied_subset: list[str],
    ) -> None:
        """Even a single denied provider is never selected regardless of priority.

        **Validates: Requirements R103.2**

        Property: If the highest-priority provider is denied, routing falls
        through to the next eligible provider rather than selecting the denied one.
        """
        # Pick at most one provider to deny
        assume(len(denied_subset) >= 1)
        single_denied = denied_subset[:1]

        non_denied = [p for p in available_providers if p not in single_denied]
        assume(len(non_denied) > 0)

        providers = [make_mock_provider(name=n) for n in available_providers]
        router = PrivacyAwareLLMRouter(providers)
        config = WorkspaceLLMConfig(
            fallback_preference=FallbackPreference.AUTO,
            denied_providers=single_denied,
        )

        response = await router.route("test prompt", workspace_config=config)

        # INVARIANT: response is not from the denied provider
        assert response.provider not in single_denied
        assert response.provider in non_denied


# =============================================================================
# Deterministic Edge Case Tests (complement to property tests)
# =============================================================================


class TestPrivacyRestrictionEdgeCases:
    """Deterministic edge cases for privacy restriction enforcement."""

    @pytest.mark.unit
    async def test_empty_denied_list_allows_all(self) -> None:
        """An empty denied_providers list does not filter any providers."""
        providers = [
            make_mock_provider("ollama"),
            make_mock_provider("openai"),
        ]
        router = PrivacyAwareLLMRouter(providers)
        config = WorkspaceLLMConfig(
            fallback_preference=FallbackPreference.AUTO,
            denied_providers=[],
        )

        response = await router.route("test", workspace_config=config)

        # First healthy provider is selected (normal priority routing)
        assert response.provider == "ollama"

    @pytest.mark.unit
    async def test_denied_primary_selects_secondary(self) -> None:
        """Denying the primary provider routes to the secondary."""
        providers = [
            make_mock_provider("openai"),
            make_mock_provider("ollama"),
        ]
        router = PrivacyAwareLLMRouter(providers)
        config = WorkspaceLLMConfig(
            fallback_preference=FallbackPreference.AUTO,
            denied_providers=["openai"],
        )

        response = await router.route("test", workspace_config=config)

        assert response.provider == "ollama"

    @pytest.mark.unit
    async def test_strict_mode_with_denied_primary_uses_secondary(self) -> None:
        """STRICT mode with denied primary still uses non-denied alternatives."""
        providers = [
            make_mock_provider("anthropic"),
            make_mock_provider("ollama"),
        ]
        router = PrivacyAwareLLMRouter(providers)
        config = WorkspaceLLMConfig(
            fallback_preference=FallbackPreference.STRICT,
            denied_providers=["anthropic"],
        )

        response = await router.route("test", workspace_config=config)

        assert response.provider == "ollama"

    @pytest.mark.unit
    async def test_multiple_denied_all_skipped(self) -> None:
        """Multiple denied providers are all skipped."""
        providers = [
            make_mock_provider("openai"),
            make_mock_provider("anthropic"),
            make_mock_provider("ollama"),
        ]
        router = PrivacyAwareLLMRouter(providers)
        config = WorkspaceLLMConfig(
            fallback_preference=FallbackPreference.AUTO,
            denied_providers=["openai", "anthropic"],
        )

        response = await router.route("test", workspace_config=config)

        assert response.provider == "ollama"

    @pytest.mark.unit
    async def test_denied_provider_not_health_checked(self) -> None:
        """A denied provider is never health-checked."""
        denied_provider = make_mock_provider("openai")
        ok_provider = make_mock_provider("ollama")
        router = PrivacyAwareLLMRouter([denied_provider, ok_provider])
        config = WorkspaceLLMConfig(
            fallback_preference=FallbackPreference.AUTO,
            denied_providers=["openai"],
        )

        await router.route("test", workspace_config=config)

        denied_provider.health_check.assert_not_called()
        denied_provider.complete.assert_not_called()

    @pytest.mark.unit
    async def test_privacy_violation_error_includes_context(self) -> None:
        """PrivacyPolicyViolationError includes denied and available info."""
        providers = [
            make_mock_provider("openai"),
            make_mock_provider("anthropic"),
        ]
        router = PrivacyAwareLLMRouter(providers)
        config = WorkspaceLLMConfig(
            fallback_preference=FallbackPreference.AUTO,
            denied_providers=["openai", "anthropic"],
        )

        with pytest.raises(PrivacyPolicyViolationError) as exc_info:
            await router.route("test", workspace_config=config)

        assert "openai" in exc_info.value.denied
        assert "anthropic" in exc_info.value.denied
        assert "openai" in exc_info.value.available
        assert "anthropic" in exc_info.value.available

    @pytest.mark.unit
    async def test_requirements_combined_with_privacy(self) -> None:
        """Privacy restrictions work together with routing requirements."""
        cloud_provider = make_mock_provider(
            "openai", privacy_level=PrivacyLevel.CLOUD
        )
        local_provider = make_mock_provider(
            "ollama", privacy_level=PrivacyLevel.LOCAL
        )
        router = PrivacyAwareLLMRouter([cloud_provider, local_provider])

        # Deny the local provider + require local privacy → should fail
        config = WorkspaceLLMConfig(
            fallback_preference=FallbackPreference.AUTO,
            denied_providers=["ollama"],
        )
        reqs = RoutingRequirements(privacy_level=PrivacyLevel.LOCAL)

        # openai is not denied but doesn't satisfy LOCAL requirement
        # ollama satisfies LOCAL but is denied
        with pytest.raises((AllProvidersExhaustedError, PrivacyPolicyViolationError)):
            await router.route("test", workspace_config=config, requirements=reqs)
