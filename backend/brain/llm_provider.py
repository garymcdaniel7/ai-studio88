"""LLM Provider for AI Brain — connects to Ollama, OpenAI, or Anthropic.

The Brain uses this to power conversations, creative planning,
prompt engineering, and production advice.

Configuration:
    BRAIN_PROVIDER — ollama | openai | anthropic | openrouter
    OLLAMA_BASE_URL — http://localhost:11434 (default)
    OLLAMA_MODEL — llama3.1 (default)
    OPENAI_API_KEY — for OpenAI provider
    ANTHROPIC_API_KEY — for Anthropic provider
"""
from __future__ import annotations

import logging
import os
from typing import AsyncGenerator, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BRAIN_PROVIDER = os.getenv("BRAIN_PROVIDER", "ollama")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

SYSTEM_PROMPT = """You are the AI Brain for AI Studio — a creative production platform.
You help with:
- Creative direction and brainstorming
- Prompt engineering for image/video generation
- Story development and scriptwriting
- Production planning and workflow optimization
- Marketing strategy and content calendars
- Technical advice on models, LoRAs, and workflows

Be creative, specific, and production-ready in your responses.
Format output clearly with bullet points, headers, and structured plans when appropriate."""


class LLMProviderError(Exception):
    """Raised when LLM provider fails."""


def get_brain_health() -> dict:
    """Check if the configured Brain LLM provider is accessible."""
    if BRAIN_PROVIDER == "ollama":
        try:
            resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                return {
                    "provider": "ollama",
                    "connected": True,
                    "model": OLLAMA_MODEL,
                    "available_models": model_names[:5],
                    "url": OLLAMA_BASE_URL,
                }
            return {"provider": "ollama", "connected": False, "error": f"HTTP {resp.status_code}"}
        except httpx.ConnectError:
            return {"provider": "ollama", "connected": False, "error": f"Not reachable at {OLLAMA_BASE_URL}"}
        except Exception as e:
            return {"provider": "ollama", "connected": False, "error": str(e)[:100]}

    elif BRAIN_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            return {"provider": "openai", "connected": False, "error": "OPENAI_API_KEY not set"}
        return {"provider": "openai", "connected": True, "model": OPENAI_MODEL}

    elif BRAIN_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            return {"provider": "anthropic", "connected": False, "error": "ANTHROPIC_API_KEY not set"}
        return {"provider": "anthropic", "connected": True, "model": ANTHROPIC_MODEL}

    return {"provider": BRAIN_PROVIDER, "connected": False, "error": "Unknown provider"}


def chat(messages: list[dict], model: Optional[str] = None) -> str:
    """Send a chat completion request to the configured LLM provider.

    Args:
        messages: List of {"role": "user"|"assistant"|"system", "content": "..."}
        model: Override the default model

    Returns:
        The assistant's response text
    """
    # Prepend system prompt if not already present
    if not messages or messages[0].get("role") != "system":
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    if BRAIN_PROVIDER == "ollama":
        return _chat_ollama(messages, model or OLLAMA_MODEL)
    elif BRAIN_PROVIDER == "openai":
        return _chat_openai(messages, model or OPENAI_MODEL)
    elif BRAIN_PROVIDER == "anthropic":
        return _chat_anthropic(messages, model or ANTHROPIC_MODEL)
    else:
        raise LLMProviderError(f"Unknown provider: {BRAIN_PROVIDER}")


def _chat_ollama(messages: list[dict], model: str) -> str:
    """Chat via Ollama API."""
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
            timeout=120,
        )
        if resp.status_code == 200:
            return resp.json().get("message", {}).get("content", "")
        raise LLMProviderError(f"Ollama returned {resp.status_code}: {resp.text[:200]}")
    except httpx.ConnectError:
        raise LLMProviderError(f"Ollama not reachable at {OLLAMA_BASE_URL}. Is it running?")


def _chat_openai(messages: list[dict], model: str) -> str:
    """Chat via OpenAI API."""
    if not OPENAI_API_KEY:
        raise LLMProviderError("OPENAI_API_KEY not configured")
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": model, "messages": messages},
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        raise LLMProviderError(f"OpenAI returned {resp.status_code}: {resp.text[:200]}")
    except httpx.ConnectError:
        raise LLMProviderError("Cannot reach OpenAI API")


def _chat_anthropic(messages: list[dict], model: str) -> str:
    """Chat via Anthropic API."""
    if not ANTHROPIC_API_KEY:
        raise LLMProviderError("ANTHROPIC_API_KEY not configured")

    # Anthropic uses a different format — system is separate
    system = ""
    chat_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system = msg["content"]
        else:
            chat_messages.append(msg)

    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "system": system,
                "messages": chat_messages,
                "max_tokens": 4096,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            content = resp.json().get("content", [])
            return content[0]["text"] if content else ""
        raise LLMProviderError(f"Anthropic returned {resp.status_code}: {resp.text[:200]}")
    except httpx.ConnectError:
        raise LLMProviderError("Cannot reach Anthropic API")
