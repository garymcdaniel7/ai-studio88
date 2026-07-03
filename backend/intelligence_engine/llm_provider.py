"""LLM Provider Interface — vendor-agnostic LLM access.

AI Studio never depends directly on one LLM vendor. All agent logic
goes through this interface. Swap providers by changing env config.

Supported (current + planned):
  - simulation (no LLM, rule-based responses)
  - openai (GPT-4o, GPT-4-turbo)
  - anthropic (Claude 3.5 Sonnet, Opus)
  - gemini (Google Gemini Pro)
  - openrouter (multi-model routing)
  - ollama (local models)
  - lmstudio (local LM Studio)
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMMessage:
    """A single message in a conversation."""
    role: str  # system, user, assistant
    content: str


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str
    model: str = ""
    tokens_used: int = 0
    finish_reason: str = "stop"
    metadata: dict = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Implement this to add a new LLM backend (OpenAI, Claude, local, etc.).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""
        ...

    @abstractmethod
    def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        """Send messages and get a completion.

        Args:
            messages: Conversation history
            **kwargs: Provider-specific options (temperature, max_tokens, etc.)

        Returns:
            LLMResponse with the generated content
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and reachable."""
        ...


# =============================================================================
# Simulation Provider (rule-based, no LLM needed)
# =============================================================================

class SimulationLLMProvider(LLMProvider):
    """Returns pre-built responses without calling any LLM.

    Used for development and testing. Each agent provides its own
    rule-based logic — this provider just wraps it in the LLM interface.
    """

    @property
    def name(self) -> str:
        return "simulation"

    def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        # Simulation doesn't actually call an LLM — agents handle their own logic
        # This is a passthrough that returns the last user message as acknowledgment
        user_msg = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return LLMResponse(
            content=user_msg,
            model="simulation",
            tokens_used=0,
        )

    def is_available(self) -> bool:
        return True  # Always available


# =============================================================================
# OpenAI Provider (placeholder — activate when API key is set)
# =============================================================================

class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider (GPT-4o, GPT-4-turbo, etc.)."""

    def __init__(self):
        self._api_key = os.getenv("OPENAI_API_KEY", "")
        self._model = os.getenv("OPENAI_MODEL", "gpt-4o")

    @property
    def name(self) -> str:
        return "openai"

    def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")

        import requests
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": kwargs.get("model", self._model),
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": kwargs.get("temperature", 0.7),
                "max_tokens": kwargs.get("max_tokens", 1000),
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", self._model),
            tokens_used=data.get("usage", {}).get("total_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
        )

    def is_available(self) -> bool:
        return bool(self._api_key)


# =============================================================================
# Provider Registry
# =============================================================================

LLM_PROVIDERS: dict[str, type[LLMProvider]] = {
    "simulation": SimulationLLMProvider,
    "openai": OpenAIProvider,
    # Future: "anthropic", "gemini", "openrouter", "ollama", "lmstudio"
}


def get_llm_provider() -> LLMProvider:
    """Get the configured LLM provider from environment.

    Set AI_PROVIDER=openai (or simulation, anthropic, etc.) in .env.
    """
    provider_name = os.getenv("AI_PROVIDER", "simulation")
    provider_class = LLM_PROVIDERS.get(provider_name)
    if not provider_class:
        raise ValueError(f"Unknown AI_PROVIDER: {provider_name}. Available: {list(LLM_PROVIDERS.keys())}")
    return provider_class()
