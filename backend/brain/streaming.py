"""Brain Streaming — SSE streaming for real-time token-by-token Brain responses.

Implements Server-Sent Events (SSE) streaming with:
- Token-by-token delivery from LLM providers
- Keepalive ping every 15 seconds
- Connection close after 120 seconds of inactivity
- Per-request output token budget of 4096 tokens
- Failover to next provider if active provider fails mid-response

Validates: Requirements R25.1, R25.6, R25.9, R25.11, R25.12

Frontend usage:
    const response = await fetch('/api/v1/brain/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: [...], mode: 'creative' })
    });
    const reader = response.body.getReader();
    // Process SSE events: data: {"token": "...", "done": false}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

# Constants
MAX_OUTPUT_TOKENS = 4096
KEEPALIVE_INTERVAL_SECONDS = 15
INACTIVITY_TIMEOUT_SECONDS = 120
STREAM_TIMEOUT_PER_PROVIDER_SECONDS = 90

# Provider config (mirror from llm_provider.py to avoid circular imports)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
BRAIN_PROVIDER = os.getenv("BRAIN_PROVIDER", "ollama")


class StreamingError(Exception):
    """Raised when streaming fails for a provider."""


def _get_streaming_provider_chain() -> list[dict[str, str]]:
    """Build ordered streaming provider chain: primary first, then fallbacks."""
    chain: list[dict[str, str]] = []

    # Primary provider first
    if BRAIN_PROVIDER == "ollama":
        chain.append({"name": "ollama", "model": OLLAMA_MODEL})
    elif BRAIN_PROVIDER == "openai":
        chain.append({"name": "openai", "model": OPENAI_MODEL})
    elif BRAIN_PROVIDER == "anthropic":
        chain.append({"name": "anthropic", "model": ANTHROPIC_MODEL})

    # Fallbacks
    if BRAIN_PROVIDER != "openai" and OPENAI_API_KEY:
        chain.append({"name": "openai", "model": OPENAI_MODEL})
    if BRAIN_PROVIDER != "anthropic" and ANTHROPIC_API_KEY:
        chain.append({"name": "anthropic", "model": ANTHROPIC_MODEL})
    if BRAIN_PROVIDER != "ollama":
        chain.append({"name": "ollama", "model": OLLAMA_MODEL})

    return chain


async def _stream_ollama(
    messages: list[dict[str, str]],
    model: str,
    max_tokens: int,
) -> AsyncGenerator[str, None]:
    """Stream tokens from Ollama /api/chat endpoint."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(
        connect=10.0, read=STREAM_TIMEOUT_PER_PROVIDER_SECONDS, write=10.0, pool=10.0
    )) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": True,
                "options": {"num_predict": max_tokens},
            },
        ) as resp:
            if resp.status_code != 200:
                raise StreamingError(
                    f"Ollama returned {resp.status_code}"
                )
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done", False):
                        return
                except json.JSONDecodeError:
                    continue


async def _stream_openai(
    messages: list[dict[str, str]],
    model: str,
    max_tokens: int,
) -> AsyncGenerator[str, None]:
    """Stream tokens from OpenAI chat completions endpoint."""
    if not OPENAI_API_KEY:
        raise StreamingError("OPENAI_API_KEY not configured")

    async with httpx.AsyncClient(timeout=httpx.Timeout(
        connect=10.0, read=STREAM_TIMEOUT_PER_PROVIDER_SECONDS, write=10.0, pool=10.0
    )) as client:
        async with client.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": True,
            },
        ) as resp:
            if resp.status_code != 200:
                raise StreamingError(
                    f"OpenAI returned {resp.status_code}"
                )
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    return
                try:
                    data = json.loads(payload)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        yield token
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue


async def _stream_anthropic(
    messages: list[dict[str, str]],
    model: str,
    max_tokens: int,
) -> AsyncGenerator[str, None]:
    """Stream tokens from Anthropic messages endpoint."""
    if not ANTHROPIC_API_KEY:
        raise StreamingError("ANTHROPIC_API_KEY not configured")

    # Separate system message for Anthropic format
    system = ""
    chat_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system = msg["content"]
        else:
            chat_messages.append(msg)

    body: dict = {
        "model": model,
        "messages": chat_messages,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if system:
        body["system"] = system

    async with httpx.AsyncClient(timeout=httpx.Timeout(
        connect=10.0, read=STREAM_TIMEOUT_PER_PROVIDER_SECONDS, write=10.0, pool=10.0
    )) as client:
        async with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
        ) as resp:
            if resp.status_code != 200:
                raise StreamingError(
                    f"Anthropic returned {resp.status_code}"
                )
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                try:
                    data = json.loads(payload)
                    event_type = data.get("type", "")
                    if event_type == "content_block_delta":
                        delta = data.get("delta", {})
                        token = delta.get("text", "")
                        if token:
                            yield token
                    elif event_type == "message_stop":
                        return
                except (json.JSONDecodeError, KeyError):
                    continue


# Provider streaming function map
_STREAM_PROVIDERS = {
    "ollama": _stream_ollama,
    "openai": _stream_openai,
    "anthropic": _stream_anthropic,
}


async def stream_brain_chat(
    messages: list[dict[str, str]],
    mode: str = "creative",
    model: str | None = None,
    max_tokens: int = MAX_OUTPUT_TOKENS,
) -> AsyncGenerator[str, None]:
    """Stream Brain chat response as SSE events with failover.

    Yields SSE-formatted strings ready for StreamingResponse.

    Event types:
        - data: {"type": "token", "content": "..."} — individual token
        - data: {"type": "keepalive"} — heartbeat every 15s
        - data: {"type": "error", "message": "..."} — provider error
        - data: {"type": "failover", "from": "...", "to": "..."} — provider switch
        - data: {"type": "done", "provider": "...", "tokens": N} — completion
        - data: {"type": "timeout"} — inactivity timeout

    Args:
        messages: Chat messages (system prompt is auto-injected based on mode).
        mode: Brain mode name.
        model: Override model (uses provider default if None).
        max_tokens: Maximum output tokens (default 4096).
    """
    from backend.brain.modes import get_mode_system_prompt

    # Inject system prompt based on mode if not present
    system_prompt = get_mode_system_prompt(mode)
    if not messages or messages[0].get("role") != "system":
        messages = [{"role": "system", "content": system_prompt}] + messages

    # Enforce token budget cap
    max_tokens = min(max_tokens, MAX_OUTPUT_TOKENS)

    # Build provider chain
    provider_chain = _get_streaming_provider_chain()
    if not provider_chain:
        yield _sse_event({"type": "error", "message": "No LLM providers configured"})
        return

    token_count = 0
    last_activity = time.monotonic()
    active_provider: str | None = None
    success = False

    for i, provider_info in enumerate(provider_chain):
        provider_name = provider_info["name"]
        provider_model = model or provider_info["model"]
        stream_fn = _STREAM_PROVIDERS.get(provider_name)

        if not stream_fn:
            continue

        # If failover occurred, notify client
        if active_provider is not None and active_provider != provider_name:
            yield _sse_event({
                "type": "failover",
                "from": active_provider,
                "to": provider_name,
            })
            logger.warning(
                "brain_stream_failover",
                extra={
                    "from_provider": active_provider,
                    "to_provider": provider_name,
                    "tokens_before_failover": token_count,
                },
            )

        active_provider = provider_name

        try:
            token_stream = stream_fn(messages, provider_model, max_tokens - token_count)
            keepalive_task: asyncio.Task | None = None

            async for token in _stream_with_keepalive_and_timeout(
                token_stream, last_activity
            ):
                if token is None:
                    # Keepalive signal
                    yield _sse_event({"type": "keepalive"})
                    continue

                if token == "__TIMEOUT__":
                    yield _sse_event({"type": "timeout"})
                    return

                token_count += 1
                last_activity = time.monotonic()
                yield _sse_event({"type": "token", "content": token})

                # Check token budget
                if token_count >= max_tokens:
                    yield _sse_event({
                        "type": "done",
                        "provider": provider_name,
                        "tokens": token_count,
                        "reason": "token_budget_reached",
                    })
                    return

            # Stream completed successfully
            success = True
            yield _sse_event({
                "type": "done",
                "provider": provider_name,
                "tokens": token_count,
                "reason": "complete",
            })
            return

        except (StreamingError, httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning(
                "brain_stream_provider_failed",
                extra={
                    "provider": provider_name,
                    "error": str(exc)[:200],
                    "tokens_generated": token_count,
                },
            )
            # Try next provider in chain
            if i < len(provider_chain) - 1:
                yield _sse_event({
                    "type": "error",
                    "message": f"Provider '{provider_name}' failed, switching...",
                    "recoverable": True,
                })
            continue
        except Exception as exc:
            logger.error(
                "brain_stream_unexpected_error",
                extra={"provider": provider_name, "error": str(exc)[:200]},
            )
            if i < len(provider_chain) - 1:
                continue
            yield _sse_event({
                "type": "error",
                "message": f"Unexpected error: {str(exc)[:100]}",
                "recoverable": False,
            })
            return

    # All providers exhausted
    if not success:
        yield _sse_event({
            "type": "error",
            "message": "All LLM providers failed",
            "recoverable": False,
        })


async def _stream_with_keepalive_and_timeout(
    token_stream: AsyncGenerator[str, None],
    last_activity_start: float,
) -> AsyncGenerator[str | None, None]:
    """Wrap a token stream with keepalive pings and inactivity timeout.

    Yields:
        str — actual token from provider
        None — keepalive signal (emit keepalive event)
        "__TIMEOUT__" — inactivity timeout reached
    """
    last_activity = last_activity_start

    # Use an asyncio.Queue to safely bridge the async generator
    # This avoids the issue of asyncio.wait_for cancelling __anext__
    token_queue: asyncio.Queue[str | object] = asyncio.Queue()
    _SENTINEL = object()

    async def _drain_tokens():
        """Read all tokens from the stream into the queue."""
        try:
            async for token in token_stream:
                await token_queue.put(token)
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            await token_queue.put(_SENTINEL)

    drain_task = asyncio.create_task(_drain_tokens())

    try:
        while True:
            try:
                item = await asyncio.wait_for(
                    token_queue.get(),
                    timeout=KEEPALIVE_INTERVAL_SECONDS,
                )
                if item is _SENTINEL:
                    # Stream finished normally
                    return
                last_activity = time.monotonic()
                yield item  # type: ignore[misc]
            except asyncio.TimeoutError:
                # No token received within keepalive interval
                elapsed_since_activity = time.monotonic() - last_activity
                if elapsed_since_activity >= INACTIVITY_TIMEOUT_SECONDS:
                    yield "__TIMEOUT__"
                    return
                # Send keepalive
                yield None
    finally:
        drain_task.cancel()
        try:
            await drain_task
        except asyncio.CancelledError:
            pass


def _sse_event(data: dict) -> str:
    """Format a dict as an SSE event string."""
    return f"data: {json.dumps(data)}\n\n"
