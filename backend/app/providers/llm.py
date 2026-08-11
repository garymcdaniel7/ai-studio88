"""Provider-agnostic LLM routing interface.

Defines the LanguageModelProvider Protocol, concrete provider implementations
(Ollama, OpenAI, Anthropic, OpenRouter), and the LLMRouter that attempts
providers in priority order with health-check-based fallback.

Validates: Requirements R26.1, R26.2, R26.5
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Protocol, runtime_checkable

import httpx

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class PrivacyLevel(str, Enum):
    """Where data is processed — drives privacy policy enforcement."""

    LOCAL = "local"
    CLOUD = "cloud"


class CostTier(str, Enum):
    """Relative cost classification for routing decisions."""

    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(frozen=True)
class ProviderCapabilities:
    """Capabilities and metadata for an LLM provider.

    Used by the router to match requests to the best provider based on
    model availability, privacy level, cost, and feature support.
    """

    name: str
    models: list[str] = field(default_factory=list)
    max_context_tokens: int = 4096
    supports_streaming: bool = False
    supports_tool_use: bool = False
    supports_vision: bool = False
    privacy_level: PrivacyLevel = PrivacyLevel.CLOUD
    cost_tier: CostTier = CostTier.MEDIUM


@dataclass(frozen=True)
class LLMResponse:
    """Standard response from any LLM provider."""

    content: str
    model: str
    provider: str
    tokens_used: int
    latency_ms: float
    cost_usd: float = 0.0


@dataclass(frozen=True)
class RoutingRequirements:
    """Constraints the router uses to select a provider.

    The router evaluates providers against these requirements and selects
    the first healthy provider in the priority chain that satisfies them.
    """

    model: str | None = None
    max_tokens: int = 2048
    temperature: float = 0.7
    privacy_level: PrivacyLevel | None = None
    max_cost_usd: float | None = None
    max_latency_ms: float | None = None
    require_streaming: bool = False
    require_tool_use: bool = False
    require_vision: bool = False


@dataclass
class RoutingDecision:
    """Record of a routing decision — logged for observability (R26.5)."""

    selected_provider: str
    model: str
    routing_reason: str
    estimated_cost: float
    fallback_chain: list[str]
    latency_ms: float = 0.0


@dataclass(frozen=True)
class WorkspaceFallbackRouteConfig:
    """Workspace-level fallback preferences passed into the router.

    This is a lightweight config object that the router uses to enforce
    fallback mode and privacy policies during routing. It is created
    from the WorkspaceFallbackService's persisted config.

    Attributes:
        fallback_mode: AUTO, ASK, or STRICT behavior on fallback.
        denied_providers: Provider names blocked by privacy policy.
        org_id: The workspace this config belongs to (for logging).
    """

    fallback_mode: str = "auto"  # "auto" | "ask" | "strict"
    denied_providers: list[str] = field(default_factory=list)
    org_id: str = ""


# =============================================================================
# Exceptions
# =============================================================================


class LLMProviderError(Exception):
    """Base exception for LLM provider operations."""

    def __init__(self, message: str, provider: str | None = None) -> None:
        self.message = message
        self.provider = provider
        super().__init__(message)


class ProviderHealthError(LLMProviderError):
    """Provider failed health check — skip to next in chain."""


class ProviderCapabilityError(LLMProviderError):
    """Provider cannot satisfy the request requirements."""


class AllProvidersExhaustedError(LLMProviderError):
    """All providers in the chain failed or were filtered out."""


# =============================================================================
# Protocol
# =============================================================================


@runtime_checkable
class LanguageModelProvider(Protocol):
    """Provider-agnostic LLM interface.

    All LLM providers implement this protocol. The router uses health_check()
    to verify availability (5s timeout) and get_capabilities() to match
    providers against routing requirements.

    Validates: Requirements R26.1, R26.2
    """

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate a completion from the provider."""
        ...

    async def health_check(self) -> bool:
        """Check if the provider is reachable and ready (5s timeout)."""
        ...

    def get_capabilities(self) -> ProviderCapabilities:
        """Return this provider's declared capabilities."""
        ...


# =============================================================================
# Provider Implementations
# =============================================================================

HEALTH_CHECK_TIMEOUT = 5.0  # seconds — per R26.2


class OllamaProvider:
    """Local Ollama LLM provider — zero cost, local privacy.

    Connects to Ollama running on localhost:11434 (configurable).
    Preferred for privacy-sensitive workloads and interactive tasks.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = model

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate completion via Ollama /api/generate endpoint."""
        use_model = model or self.default_model
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": use_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
        latency = (time.perf_counter() - start) * 1000
        tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)
        return LLMResponse(
            content=data.get("response", ""),
            model=use_model,
            provider="ollama",
            tokens_used=tokens,
            latency_ms=latency,
            cost_usd=0.0,
        )

    async def health_check(self) -> bool:
        """Check if Ollama is reachable via /api/tags (5s timeout)."""
        try:
            async with httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        """Ollama capabilities — local, free, moderate context."""
        return ProviderCapabilities(
            name="ollama",
            models=[self.default_model],
            max_context_tokens=8192,
            supports_streaming=True,
            supports_tool_use=False,
            supports_vision=False,
            privacy_level=PrivacyLevel.LOCAL,
            cost_tier=CostTier.FREE,
        )


class OpenAIProvider:
    """OpenAI API provider — cloud, per-token cost.

    Uses the chat completions endpoint at api.openai.com.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key
        self.default_model = model
        self.base_url = base_url.rstrip("/")

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate completion via OpenAI chat completions."""
        use_model = model or self.default_model
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": use_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        latency = (time.perf_counter() - start) * 1000
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        cost = self._estimate_cost(use_model, usage)
        content = data["choices"][0]["message"]["content"]
        return LLMResponse(
            content=content,
            model=use_model,
            provider="openai",
            tokens_used=tokens,
            latency_ms=latency,
            cost_usd=cost,
        )

    async def health_check(self) -> bool:
        """Check connectivity by listing models (5s timeout)."""
        try:
            async with httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        """OpenAI capabilities — cloud, tool use, vision, large context."""
        return ProviderCapabilities(
            name="openai",
            models=[self.default_model, "gpt-4o-mini", "gpt-4-turbo"],
            max_context_tokens=128_000,
            supports_streaming=True,
            supports_tool_use=True,
            supports_vision=True,
            privacy_level=PrivacyLevel.CLOUD,
            cost_tier=CostTier.HIGH,
        )

    @staticmethod
    def _estimate_cost(model: str, usage: dict) -> float:
        """Estimate cost based on token usage and model pricing."""
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        # Approximate pricing per 1M tokens (simplified)
        rates = {
            "gpt-4o": (2.50, 10.00),
            "gpt-4o-mini": (0.15, 0.60),
            "gpt-4-turbo": (10.00, 30.00),
        }
        input_rate, output_rate = rates.get(model, (5.00, 15.00))
        cost = (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000
        return round(cost, 6)


class AnthropicProvider:
    """Anthropic API provider — cloud, per-token cost.

    Uses the messages endpoint at api.anthropic.com.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self.api_key = api_key
        self.default_model = model

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate completion via Anthropic messages API."""
        use_model = model or self.default_model
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": use_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        latency = (time.perf_counter() - start) * 1000
        usage = data.get("usage", {})
        tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        cost = self._estimate_cost(use_model, usage)
        content_blocks = data.get("content", [])
        content = content_blocks[0]["text"] if content_blocks else ""
        return LLMResponse(
            content=content,
            model=use_model,
            provider="anthropic",
            tokens_used=tokens,
            latency_ms=latency,
            cost_usd=cost,
        )

    async def health_check(self) -> bool:
        """Check Anthropic by verifying API key format and endpoint reachability."""
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT) as client:
                # Anthropic doesn't have a lightweight health endpoint — use a
                # minimal message request with max_tokens=1 to verify connectivity
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.default_model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                )
                # 200 = healthy; 401 = bad key but reachable; 529 = overloaded
                return resp.status_code in (200, 401)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        """Anthropic capabilities — cloud, large context, tool use."""
        return ProviderCapabilities(
            name="anthropic",
            models=[self.default_model, "claude-sonnet-4-20250514", "claude-3-haiku-20240307"],
            max_context_tokens=200_000,
            supports_streaming=True,
            supports_tool_use=True,
            supports_vision=True,
            privacy_level=PrivacyLevel.CLOUD,
            cost_tier=CostTier.HIGH,
        )

    @staticmethod
    def _estimate_cost(model: str, usage: dict) -> float:
        """Estimate cost based on Anthropic token usage."""
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        # Approximate pricing per 1M tokens
        rates = {
            "claude-sonnet-4-20250514": (3.00, 15.00),
            "claude-3-haiku-20240307": (0.25, 1.25),
        }
        input_rate, output_rate = rates.get(model, (3.00, 15.00))
        cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
        return round(cost, 6)


class OpenRouterProvider:
    """OpenRouter API provider — cloud, variable cost, many models.

    Routes through OpenRouter to access multiple model providers via a
    single API key.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "meta-llama/llama-3.1-8b-instruct",
    ) -> None:
        self.api_key = api_key
        self.default_model = model
        self.base_url = "https://openrouter.ai/api/v1"

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate completion via OpenRouter (OpenAI-compatible)."""
        use_model = model or self.default_model
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://ai-studio88.com",
                    "X-Title": "AI Studio",
                },
                json={
                    "model": use_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        latency = (time.perf_counter() - start) * 1000
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        cost = usage.get("cost", 0.0) or 0.0
        content = data["choices"][0]["message"]["content"]
        return LLMResponse(
            content=content,
            model=use_model,
            provider="openrouter",
            tokens_used=tokens,
            latency_ms=latency,
            cost_usd=cost,
        )

    async def health_check(self) -> bool:
        """Check OpenRouter by listing models (5s timeout)."""
        try:
            async with httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        """OpenRouter capabilities — cloud, variable cost, many models."""
        return ProviderCapabilities(
            name="openrouter",
            models=[self.default_model],
            max_context_tokens=128_000,
            supports_streaming=True,
            supports_tool_use=True,
            supports_vision=True,
            privacy_level=PrivacyLevel.CLOUD,
            cost_tier=CostTier.MEDIUM,
        )


# =============================================================================
# Router
# =============================================================================


class LLMRouter:
    """Routes LLM requests through a priority chain of providers.

    Attempts providers in order, selecting the first that is:
    1. Healthy (health check passes within 5s timeout)
    2. Capable of satisfying the routing requirements
    3. Allowed by workspace fallback preferences (privacy policy)

    Logs every routing decision for observability (R26.5, R26.9).

    Validates: Requirements R26.1, R26.2, R26.5, R26.9, R102.1, R102.2, R102.3
    """

    def __init__(self, providers: list[LanguageModelProvider]) -> None:
        """Initialize with an ordered priority chain of providers.

        Args:
            providers: Ordered list — first provider is highest priority.
        """
        if not providers:
            raise ValueError("LLMRouter requires at least one provider")
        self._providers = providers

    @property
    def provider_count(self) -> int:
        """Number of providers in the chain."""
        return len(self._providers)

    @property
    def provider_names(self) -> list[str]:
        """Ordered list of provider names in the chain."""
        return [p.get_capabilities().name for p in self._providers]

    async def route(
        self,
        prompt: str,
        requirements: RoutingRequirements | None = None,
        fallback_config: "WorkspaceFallbackRouteConfig | None" = None,
    ) -> LLMResponse:
        """Route a completion request through the priority chain.

        Tries each provider in order:
        1. Check privacy policy (skip denied providers per fallback_config)
        2. Check capabilities against requirements (skip if unsatisfied)
        3. Run health check (5s timeout — skip if unhealthy)
        4. Enforce fallback mode (STRICT/ASK/AUTO) when first choice fails
        5. Execute completion

        Logs every routing decision with provider, model, routing_reason,
        estimated_cost, and fallback_chain (R26.9).

        Args:
            prompt: The prompt to complete.
            requirements: Optional constraints for provider selection.
            fallback_config: Optional workspace fallback preferences.

        Returns:
            LLMResponse from the first successful provider.

        Raises:
            AllProvidersExhaustedError: If no provider could serve the request.
        """
        reqs = requirements or RoutingRequirements()
        fallback_chain: list[str] = []
        last_error: Exception | None = None
        is_fallback = False
        denied_set: set[str] = set()
        fallback_mode = "auto"
        org_id = ""

        if fallback_config:
            denied_set = {p.lower() for p in fallback_config.denied_providers}
            fallback_mode = fallback_config.fallback_mode
            org_id = fallback_config.org_id

        for provider in self._providers:
            caps = provider.get_capabilities()
            provider_name = caps.name

            # Privacy policy enforcement: skip denied providers (R26.9)
            if provider_name.lower() in denied_set:
                fallback_chain.append(f"{provider_name}:privacy_denied")
                logger.info(
                    "llm_routing_skip",
                    provider=provider_name,
                    reason="privacy_policy_denied",
                    org_id=org_id,
                )
                continue

            # Check capability match
            if not self._satisfies_requirements(caps, reqs):
                fallback_chain.append(f"{provider_name}:capability_mismatch")
                logger.info(
                    "llm_routing_skip",
                    provider=provider_name,
                    reason="capability_mismatch",
                )
                if not is_fallback:
                    is_fallback = True
                continue

            # Health check (5s timeout enforced by provider)
            try:
                healthy = await provider.health_check()
            except Exception:
                healthy = False

            if not healthy:
                fallback_chain.append(f"{provider_name}:unhealthy")
                logger.info(
                    "llm_routing_skip",
                    provider=provider_name,
                    reason="health_check_failed",
                )
                if not is_fallback:
                    is_fallback = True
                continue

            # Fallback mode enforcement (R102.1, R102.2, R102.3)
            if is_fallback and fallback_config:
                # Resolve effective mode: if AUTO but only denied providers
                # remain, treat as STRICT (privacy override)
                effective_mode = self._resolve_effective_mode(
                    fallback_mode, fallback_chain, denied_set
                )

                if effective_mode == "strict":
                    logger.info(
                        "llm_routing_strict_denied",
                        org_id=org_id,
                        provider=provider_name,
                        fallback_chain=fallback_chain,
                        fallback_mode=fallback_mode,
                        effective_mode="strict",
                    )
                    raise AllProvidersExhaustedError(
                        f"STRICT mode: preferred provider unavailable. "
                        f"Fallback denied. Chain: {fallback_chain}",
                        provider=None,
                    )

                if effective_mode == "ask":
                    # For ASK mode, we still complete but log the decision
                    # with a special reason so the API layer can present
                    # confirmation UI. The actual "ask" UX is handled by
                    # the endpoint layer, not the router.
                    logger.info(
                        "llm_routing_ask_fallback",
                        org_id=org_id,
                        provider=provider_name,
                        fallback_chain=fallback_chain,
                    )

            # Attempt completion
            try:
                start = time.perf_counter()
                response = await provider.complete(
                    prompt=prompt,
                    model=reqs.model,
                    max_tokens=reqs.max_tokens,
                    temperature=reqs.temperature,
                )
                total_latency = (time.perf_counter() - start) * 1000

                # Check latency constraint post-hoc
                if reqs.max_latency_ms and total_latency > reqs.max_latency_ms:
                    logger.warning(
                        "llm_routing_latency_exceeded",
                        provider=provider_name,
                        latency_ms=total_latency,
                        max_latency_ms=reqs.max_latency_ms,
                    )
                    # Still return — latency is advisory, not a hard filter

                # Check cost constraint post-hoc
                if reqs.max_cost_usd and response.cost_usd > reqs.max_cost_usd:
                    fallback_chain.append(f"{provider_name}:cost_exceeded")
                    logger.info(
                        "llm_routing_skip",
                        provider=provider_name,
                        reason="cost_exceeded",
                        cost=response.cost_usd,
                        max_cost=reqs.max_cost_usd,
                    )
                    last_error = ProviderCapabilityError(
                        f"Cost {response.cost_usd} exceeds max {reqs.max_cost_usd}",
                        provider=provider_name,
                    )
                    if not is_fallback:
                        is_fallback = True
                    continue

                # Determine routing reason
                routing_reason = (
                    "fallback_auto" if is_fallback else "first_healthy_capable"
                )

                # Log successful routing decision (R26.9)
                decision = RoutingDecision(
                    selected_provider=provider_name,
                    model=response.model,
                    routing_reason=routing_reason,
                    estimated_cost=response.cost_usd,
                    fallback_chain=fallback_chain,
                    latency_ms=response.latency_ms,
                )
                logger.info(
                    "llm_routing_decision",
                    org_id=org_id,
                    selected_provider=decision.selected_provider,
                    model=decision.model,
                    routing_reason=decision.routing_reason,
                    estimated_cost=decision.estimated_cost,
                    fallback_chain=decision.fallback_chain,
                    fallback_mode=fallback_mode,
                )
                return response

            except httpx.HTTPStatusError as exc:
                fallback_chain.append(f"{provider_name}:http_error_{exc.response.status_code}")
                last_error = LLMProviderError(
                    f"HTTP {exc.response.status_code}", provider=provider_name
                )
                logger.warning(
                    "llm_routing_provider_error",
                    provider=provider_name,
                    status_code=exc.response.status_code,
                )
                if not is_fallback:
                    is_fallback = True
                continue
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                fallback_chain.append(f"{provider_name}:connection_error")
                last_error = LLMProviderError(str(exc), provider=provider_name)
                logger.warning(
                    "llm_routing_provider_error",
                    provider=provider_name,
                    error=str(exc)[:100],
                )
                if not is_fallback:
                    is_fallback = True
                continue
            except Exception as exc:
                fallback_chain.append(f"{provider_name}:unexpected_error")
                last_error = LLMProviderError(str(exc), provider=provider_name)
                logger.error(
                    "llm_routing_unexpected_error",
                    provider=provider_name,
                    error=str(exc)[:200],
                )
                if not is_fallback:
                    is_fallback = True
                continue

        # All providers exhausted
        logger.error(
            "llm_routing_all_exhausted",
            org_id=org_id,
            fallback_chain=fallback_chain,
            fallback_mode=fallback_mode,
            last_error=str(last_error) if last_error else None,
        )
        raise AllProvidersExhaustedError(
            f"All providers exhausted. Chain: {fallback_chain}",
            provider=None,
        )

    @staticmethod
    def _resolve_effective_mode(
        fallback_mode: str,
        fallback_chain: list[str],
        denied_set: set[str],
    ) -> str:
        """Resolve the effective fallback mode considering privacy overrides.

        If AUTO mode is active but all remaining skipped providers were
        privacy-denied, this indicates a privacy override → treat as STRICT.

        Args:
            fallback_mode: The configured workspace fallback mode.
            fallback_chain: Current chain of skipped providers with reasons.
            denied_set: Set of denied provider names (lowercased).

        Returns:
            The effective mode after considering privacy overrides.
        """
        if fallback_mode != "auto":
            return fallback_mode

        # Check if privacy-denied providers dominate the fallback chain
        privacy_denied_count = sum(
            1 for entry in fallback_chain if ":privacy_denied" in entry
        )
        if privacy_denied_count > 0 and denied_set:
            # AUTO would violate privacy → treat as STRICT (R26.9)
            return "strict"

        return "auto"

    @staticmethod
    def _satisfies_requirements(
        caps: ProviderCapabilities, reqs: RoutingRequirements
    ) -> bool:
        """Check if a provider's capabilities satisfy the routing requirements."""
        if reqs.privacy_level and caps.privacy_level != reqs.privacy_level:
            return False
        if reqs.require_streaming and not caps.supports_streaming:
            return False
        if reqs.require_tool_use and not caps.supports_tool_use:
            return False
        if reqs.require_vision and not caps.supports_vision:
            return False
        return True


# =============================================================================
# Workspace Privacy-Aware Routing (R103, R26.9)
# =============================================================================


class FallbackPreference(str, Enum):
    """Workspace fallback behavior when preferred provider is unavailable."""

    AUTO = "auto"
    ASK = "ask"
    STRICT = "strict"


@dataclass(frozen=True)
class WorkspaceLLMConfig:
    """Per-workspace LLM routing configuration including privacy restrictions.

    Encapsulates the workspace's fallback preference and denied_providers list.
    The PrivacyAwareLLMRouter uses this to filter out disallowed providers
    before any routing decision.

    Validates: Requirements R26.9, R103.2
    """

    fallback_preference: FallbackPreference = FallbackPreference.AUTO
    denied_providers: list[str] = field(default_factory=list)


class PrivacyPolicyViolationError(LLMProviderError):
    """Raised when all eligible providers are blocked by privacy restrictions."""

    def __init__(self, denied: list[str], available: list[str]) -> None:
        self.denied = denied
        self.available = available
        super().__init__(
            f"Privacy policy blocks all available providers. "
            f"Denied: {denied}, Available: {available}",
            provider=None,
        )


class PrivacyAwareLLMRouter:
    """Routes LLM requests while enforcing workspace privacy restrictions.

    Wraps the base LLMRouter and ensures:
    1. Providers in the workspace's denied_providers list are NEVER selected.
    2. If AUTO fallback would route to a denied provider, the request is
       treated as STRICT (fail rather than violate privacy policy).
    3. When all available providers are denied, raises PrivacyPolicyViolationError.

    Property 17: Privacy Restriction Enforcement
    *For any* LLM routing or job dispatch for a workspace with privacy restriction R,
    the selected provider SHALL NOT be in the workspace's denied_providers list.

    Validates: Requirements R26.9, R103.2
    """

    def __init__(self, providers: list[LanguageModelProvider]) -> None:
        """Initialize with an ordered priority chain of providers.

        Args:
            providers: Ordered list — first provider is highest priority.
        """
        if not providers:
            raise ValueError("PrivacyAwareLLMRouter requires at least one provider")
        self._providers = providers

    @property
    def provider_names(self) -> list[str]:
        """Ordered list of provider names in the chain."""
        return [p.get_capabilities().name for p in self._providers]

    def _filter_providers(
        self, workspace_config: WorkspaceLLMConfig
    ) -> list[LanguageModelProvider]:
        """Filter out providers blocked by workspace privacy restrictions.

        Returns only providers whose name is NOT in denied_providers.
        """
        denied = set(workspace_config.denied_providers)
        if not denied:
            return list(self._providers)
        return [
            p for p in self._providers
            if p.get_capabilities().name not in denied
        ]

    async def route(
        self,
        prompt: str,
        workspace_config: WorkspaceLLMConfig,
        requirements: RoutingRequirements | None = None,
    ) -> LLMResponse:
        """Route a completion request respecting workspace privacy restrictions.

        Privacy enforcement:
        - Providers in denied_providers are excluded before any routing attempt.
        - If fallback is AUTO and would route to a denied provider, it is skipped.
        - If all remaining providers are exhausted, raises PrivacyPolicyViolationError
          (not AllProvidersExhaustedError) to distinguish privacy blocks from
          general availability failures.

        Args:
            prompt: The prompt to complete.
            workspace_config: Workspace-level privacy and fallback configuration.
            requirements: Optional routing requirements (model, privacy level, etc.).

        Returns:
            LLMResponse from the first successful, non-denied provider.

        Raises:
            PrivacyPolicyViolationError: All available providers are blocked by privacy.
            AllProvidersExhaustedError: Non-denied providers exist but all failed.
        """
        eligible_providers = self._filter_providers(workspace_config)

        if not eligible_providers:
            raise PrivacyPolicyViolationError(
                denied=workspace_config.denied_providers,
                available=[p.get_capabilities().name for p in self._providers],
            )

        # For STRICT mode with denied providers and no eligible providers
        # we already raised above. For ASK mode, we'd return a confirmation
        # request but that's handled at the API layer — here we just enforce
        # that denied providers are never selected.

        # Create a sub-router with only eligible providers
        inner_router = LLMRouter(eligible_providers)
        try:
            return await inner_router.route(prompt, requirements)
        except AllProvidersExhaustedError:
            # Re-classify: if all providers exhausted AND some were denied,
            # report as privacy violation to help the user understand why.
            denied = set(workspace_config.denied_providers)
            all_names = [p.get_capabilities().name for p in self._providers]
            denied_in_chain = [n for n in all_names if n in denied]
            if denied_in_chain:
                raise PrivacyPolicyViolationError(
                    denied=workspace_config.denied_providers,
                    available=all_names,
                )
            raise
