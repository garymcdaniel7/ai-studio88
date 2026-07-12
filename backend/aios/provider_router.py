"""AIOS Provider Router — intelligent per-request LLM selection.

Replaces static BRAIN_PROVIDER with dynamic routing based on:
- Task complexity (simple chat vs multi-step reasoning)
- Context length (short vs long conversation)
- Privacy (local vs cloud)
- Cost (free local vs paid cloud)
- Availability (provider health)
- User preferences

Routing logic:
1. Score each available provider for the request
2. Pick highest-scoring provider
3. If it fails, try next in chain (auto-fallback)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


@dataclass
class RoutingContext:
    """Context about the request to inform routing decisions."""

    mode: str = "creative"
    message_length: int = 0
    session_message_count: int = 0
    has_talent_context: bool = False
    requires_tool_use: bool = False
    privacy_sensitive: bool = False
    max_latency_ms: int | None = None


@dataclass
class ProviderScore:
    """Score for a provider candidate."""

    name: str
    model: str
    score: float
    reasoning: str


def route_request(
    messages: list[dict],
    ctx: RoutingContext,
) -> tuple[str, str, str]:
    """Route a chat request to the best available provider.

    Returns: (response_text, provider_name, model_name)
    """
    # Score all available providers
    candidates = _score_providers(ctx)

    # Sort by score descending
    candidates.sort(key=lambda c: c.score, reverse=True)

    # Try each in order
    last_error = None
    for candidate in candidates:
        try:
            response = _call_provider(candidate.name, candidate.model, messages)
            logger.info(
                f"AIOS routed to {candidate.name}/{candidate.model} "
                f"(score={candidate.score:.2f}, reason={candidate.reasoning})"
            )
            return response, candidate.name, candidate.model
        except Exception as e:
            last_error = e
            logger.warning(f"Provider {candidate.name} failed: {e}")
            continue

    raise last_error or RuntimeError("No LLM providers available")


def _score_providers(ctx: RoutingContext) -> list[ProviderScore]:
    """Score each available provider for this request."""
    candidates = []

    # Ollama (local)
    if _ollama_available():
        score = 70.0  # Base score for local (free, fast for short)
        reasoning = "Local Ollama (free, private)"

        # Boost for privacy-sensitive
        if ctx.privacy_sensitive:
            score += 20
            reasoning += " +privacy"

        # Penalize for long context (8b model has limited context)
        if ctx.session_message_count > 15:
            score -= 15
            reasoning += " -long_context"

        # Penalize for complex modes that benefit from larger models
        if ctx.mode in ("script_writer", "production_advisor") and ctx.message_length > 500:
            score -= 10
            reasoning += " -complex_task"

        candidates.append(ProviderScore("ollama", OLLAMA_MODEL, score, reasoning))

    # OpenAI
    if OPENAI_API_KEY:
        score = 60.0  # Base (costs money but very capable)
        reasoning = "OpenAI (capable, good tool use)"

        # Boost for complex tasks
        if ctx.mode in ("script_writer", "production_advisor", "prompt_engineer"):
            score += 15
            reasoning += " +complex_mode"

        # Boost for long context
        if ctx.session_message_count > 15:
            score += 10
            reasoning += " +long_context"

        # Boost for tool use
        if ctx.requires_tool_use:
            score += 20
            reasoning += " +tool_use"

        # Penalize if privacy needed
        if ctx.privacy_sensitive:
            score -= 30
            reasoning += " -cloud_privacy"

        candidates.append(ProviderScore("openai", OPENAI_MODEL, score, reasoning))

    # Anthropic
    if ANTHROPIC_API_KEY:
        score = 55.0  # Base
        reasoning = "Anthropic (careful analysis, long context)"

        # Boost for long context (Claude has 200K)
        if ctx.session_message_count > 20:
            score += 20
            reasoning += " +very_long_context"

        # Boost for creative writing
        if ctx.mode in ("script_writer", "story_assistant", "creative"):
            score += 10
            reasoning += " +creative_writing"

        # Penalize if privacy needed
        if ctx.privacy_sensitive:
            score -= 30
            reasoning += " -cloud_privacy"

        candidates.append(ProviderScore("anthropic", ANTHROPIC_MODEL, score, reasoning))

    return candidates


def _call_provider(name: str, model: str, messages: list[dict]) -> str:
    """Call a specific provider and return the response text."""
    from backend.brain.llm_provider import _chat_ollama, _chat_openai, _chat_anthropic

    if name == "ollama":
        return _chat_ollama(messages, model)
    elif name == "openai":
        return _chat_openai(messages, model)
    elif name == "anthropic":
        return _chat_anthropic(messages, model)
    else:
        raise ValueError(f"Unknown provider: {name}")


def _ollama_available() -> bool:
    """Quick check if Ollama is reachable."""
    import httpx

    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        return resp.status_code == 200
    except Exception:
        pass

    # Try GPU worker
    try:
        from backend.infrastructure.worker_orchestrator import get_orchestrator

        o = get_orchestrator()
        if o.session and o.session.ssh_host:
            resp = httpx.get(f"http://{o.session.ssh_host}:11434/api/tags", timeout=3)
            return resp.status_code == 200
    except Exception:
        pass

    return False
