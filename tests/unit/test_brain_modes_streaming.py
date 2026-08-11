"""Unit tests for Brain modes and SSE streaming (task 19.2).

Tests:
- BrainMode enum coverage (all 7 modes)
- System prompt retrieval per mode
- Mode listing for frontend display
- SSE event formatting
- Streaming with keepalive and timeout logic
- Token budget enforcement
- Provider failover during streaming

Validates: Requirements R25.1, R25.6, R25.9, R25.11, R25.12
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# =============================================================================
# Brain Modes Tests
# =============================================================================


class TestBrainModeEnum:
    """Test that BrainMode enum contains all 7 required modes."""

    def test_all_modes_present(self):
        from backend.brain.modes import BrainMode

        expected = {
            "creative",
            "prompt_engineer",
            "story_assistant",
            "production_advisor",
            "research",
            "image_analyzer",
            "business_strategy",
        }
        actual = {m.value for m in BrainMode}
        assert actual == expected

    def test_mode_count(self):
        from backend.brain.modes import BrainMode

        assert len(BrainMode) == 7

    def test_mode_is_string_enum(self):
        from backend.brain.modes import BrainMode

        assert BrainMode.CREATIVE == "creative"
        assert BrainMode.BUSINESS_STRATEGY == "business_strategy"


class TestBrainModeSystemPrompts:
    """Test system prompt retrieval for each mode."""

    def test_get_prompt_for_each_mode(self):
        from backend.brain.modes import BrainMode, get_mode_system_prompt

        for mode in BrainMode:
            prompt = get_mode_system_prompt(mode)
            assert isinstance(prompt, str)
            assert len(prompt) > 50, f"Mode {mode.value} prompt too short"

    def test_get_prompt_by_string(self):
        from backend.brain.modes import get_mode_system_prompt

        prompt = get_mode_system_prompt("creative")
        assert "Creative Director" in prompt

    def test_get_prompt_unknown_mode_returns_default(self):
        from backend.brain.modes import DEFAULT_SYSTEM_PROMPT, get_mode_system_prompt

        prompt = get_mode_system_prompt("nonexistent_mode")
        assert prompt == DEFAULT_SYSTEM_PROMPT

    def test_business_strategy_prompt_content(self):
        from backend.brain.modes import get_mode_system_prompt

        prompt = get_mode_system_prompt("business_strategy")
        assert "Business Strategy" in prompt
        assert "monetization" in prompt.lower() or "Monetization" in prompt

    def test_prompt_engineer_has_technical_terms(self):
        from backend.brain.modes import get_mode_system_prompt

        prompt = get_mode_system_prompt("prompt_engineer")
        assert "SDXL" in prompt
        assert "Flux" in prompt
        assert "negative prompt" in prompt.lower()

    def test_production_advisor_mentions_costs(self):
        from backend.brain.modes import get_mode_system_prompt

        prompt = get_mode_system_prompt("production_advisor")
        assert "cost" in prompt.lower()
        assert "GPU" in prompt


class TestListAvailableModes:
    """Test the mode listing function for frontend display."""

    def test_returns_all_modes(self):
        from backend.brain.modes import list_available_modes

        modes = list_available_modes()
        assert len(modes) == 7

    def test_mode_structure(self):
        from backend.brain.modes import list_available_modes

        modes = list_available_modes()
        for mode in modes:
            assert "mode" in mode
            assert "label" in mode
            assert "description" in mode
            assert "icon" in mode

    def test_business_strategy_in_list(self):
        from backend.brain.modes import list_available_modes

        modes = list_available_modes()
        mode_values = [m["mode"] for m in modes]
        assert "business_strategy" in mode_values


# =============================================================================
# SSE Event Formatting Tests
# =============================================================================


class TestSSEEventFormatting:
    """Test SSE event string formatting."""

    def test_sse_event_format(self):
        from backend.brain.streaming import _sse_event

        event = _sse_event({"type": "token", "content": "hello"})
        assert event.startswith("data: ")
        assert event.endswith("\n\n")
        payload = json.loads(event[6:-2])
        assert payload == {"type": "token", "content": "hello"}

    def test_sse_event_keepalive(self):
        from backend.brain.streaming import _sse_event

        event = _sse_event({"type": "keepalive"})
        payload = json.loads(event[6:-2])
        assert payload["type"] == "keepalive"

    def test_sse_event_done(self):
        from backend.brain.streaming import _sse_event

        event = _sse_event({"type": "done", "provider": "ollama", "tokens": 100})
        payload = json.loads(event[6:-2])
        assert payload["type"] == "done"
        assert payload["provider"] == "ollama"
        assert payload["tokens"] == 100


# =============================================================================
# Provider Chain Tests
# =============================================================================


class TestProviderChain:
    """Test streaming provider chain construction."""

    def test_default_chain_has_ollama_first(self):
        from backend.brain.streaming import _get_streaming_provider_chain

        with patch.dict("os.environ", {"BRAIN_PROVIDER": "ollama"}, clear=False):
            # Need to re-import or patch the module-level constants
            import backend.brain.streaming as st

            original_provider = st.BRAIN_PROVIDER
            st.BRAIN_PROVIDER = "ollama"
            try:
                chain = _get_streaming_provider_chain()
                assert len(chain) >= 1
                assert chain[0]["name"] == "ollama"
            finally:
                st.BRAIN_PROVIDER = original_provider

    def test_openai_primary_puts_openai_first(self):
        import backend.brain.streaming as st

        original_provider = st.BRAIN_PROVIDER
        original_key = st.OPENAI_API_KEY
        st.BRAIN_PROVIDER = "openai"
        st.OPENAI_API_KEY = "sk-test"
        try:
            chain = st._get_streaming_provider_chain()
            assert chain[0]["name"] == "openai"
        finally:
            st.BRAIN_PROVIDER = original_provider
            st.OPENAI_API_KEY = original_key


# =============================================================================
# Streaming Logic Tests
# =============================================================================


class TestStreamingKeepaliveAndTimeout:
    """Test the keepalive and timeout wrapper."""

    @pytest.mark.asyncio
    async def test_keepalive_emitted_on_slow_stream(self):
        """If tokens are slow, keepalive (None) should be yielded."""
        from backend.brain.streaming import _stream_with_keepalive_and_timeout

        async def slow_stream():
            await asyncio.sleep(0.05)
            yield "token1"
            # Long pause triggers keepalive
            await asyncio.sleep(20)
            yield "token2"

        # Patch KEEPALIVE_INTERVAL_SECONDS to a very short value for testing
        import backend.brain.streaming as st

        original_keepalive = st.KEEPALIVE_INTERVAL_SECONDS
        original_timeout = st.INACTIVITY_TIMEOUT_SECONDS
        st.KEEPALIVE_INTERVAL_SECONDS = 0.1
        st.INACTIVITY_TIMEOUT_SECONDS = 5

        try:
            results = []
            async for item in _stream_with_keepalive_and_timeout(
                slow_stream(), time.monotonic()
            ):
                results.append(item)
                if len(results) >= 3:
                    break

            # Should have token1, then a keepalive (None)
            assert "token1" in results
            assert None in results
        finally:
            st.KEEPALIVE_INTERVAL_SECONDS = original_keepalive
            st.INACTIVITY_TIMEOUT_SECONDS = original_timeout

    @pytest.mark.asyncio
    async def test_timeout_after_inactivity(self):
        """Stream should yield __TIMEOUT__ after inactivity period."""
        from backend.brain.streaming import _stream_with_keepalive_and_timeout

        import backend.brain.streaming as st

        original_keepalive = st.KEEPALIVE_INTERVAL_SECONDS
        original_timeout = st.INACTIVITY_TIMEOUT_SECONDS
        st.KEEPALIVE_INTERVAL_SECONDS = 0.03
        st.INACTIVITY_TIMEOUT_SECONDS = 0.1

        try:
            # Use an async queue-based approach to simulate stalled stream
            queue: asyncio.Queue[str | None] = asyncio.Queue()

            async def stalled_stream():
                # Yield one token then stall forever
                yield "first"
                # This await will never complete — simulates provider hang
                await queue.get()
                yield "never"  # pragma: no cover

            results = []
            async for item in _stream_with_keepalive_and_timeout(
                stalled_stream(), time.monotonic()
            ):
                results.append(item)
                if item == "__TIMEOUT__":
                    break

            # Should have: "first", then some keepalives (None), then __TIMEOUT__
            assert "first" in results
            assert "__TIMEOUT__" in results
        finally:
            st.KEEPALIVE_INTERVAL_SECONDS = original_keepalive
            st.INACTIVITY_TIMEOUT_SECONDS = original_timeout

    @pytest.mark.asyncio
    async def test_normal_stream_completes(self):
        """A fast stream should complete without keepalive or timeout."""
        from backend.brain.streaming import _stream_with_keepalive_and_timeout

        import backend.brain.streaming as st

        original_keepalive = st.KEEPALIVE_INTERVAL_SECONDS
        st.KEEPALIVE_INTERVAL_SECONDS = 10  # Long keepalive so it won't trigger

        try:

            async def fast_stream():
                yield "hello"
                yield " "
                yield "world"

            results = []
            async for item in _stream_with_keepalive_and_timeout(
                fast_stream(), time.monotonic()
            ):
                results.append(item)

            assert results == ["hello", " ", "world"]
        finally:
            st.KEEPALIVE_INTERVAL_SECONDS = original_keepalive


class TestStreamBrainChat:
    """Test the main stream_brain_chat generator."""

    @pytest.mark.asyncio
    async def test_token_budget_enforcement(self):
        """Stream should stop after max_tokens tokens."""
        import backend.brain.streaming as st

        async def infinite_tokens(messages, model, max_tokens):
            for i in range(10000):
                yield f"token{i}"

        with patch.dict(st._STREAM_PROVIDERS, {"ollama": lambda m, mo, mt: infinite_tokens(m, mo, mt)}):
            original_provider = st.BRAIN_PROVIDER
            st.BRAIN_PROVIDER = "ollama"
            original_keepalive = st.KEEPALIVE_INTERVAL_SECONDS
            st.KEEPALIVE_INTERVAL_SECONDS = 999  # Don't trigger keepalive

            try:
                events = []
                async for event in st.stream_brain_chat(
                    messages=[{"role": "user", "content": "test"}],
                    mode="creative",
                    max_tokens=5,
                ):
                    events.append(event)

                # Parse events
                parsed = [json.loads(e[6:-2]) for e in events]
                tokens = [p for p in parsed if p["type"] == "token"]
                done_events = [p for p in parsed if p["type"] == "done"]

                assert len(tokens) == 5
                assert len(done_events) == 1
                assert done_events[0]["reason"] == "token_budget_reached"
                assert done_events[0]["tokens"] == 5
            finally:
                st.BRAIN_PROVIDER = original_provider
                st.KEEPALIVE_INTERVAL_SECONDS = original_keepalive

    @pytest.mark.asyncio
    async def test_failover_on_provider_error(self):
        """If first provider fails, should failover to next."""
        import backend.brain.streaming as st

        call_count = {"value": 0}

        async def failing_provider(messages, model, max_tokens):
            raise st.StreamingError("Connection refused")
            yield ""  # Make it a generator  # pragma: no cover

        async def working_provider(messages, model, max_tokens):
            yield "success"

        original_chain_fn = st._get_streaming_provider_chain
        st._get_streaming_provider_chain = lambda: [
            {"name": "ollama", "model": "llama3.1:8b"},
            {"name": "openai", "model": "gpt-4o"},
        ]

        providers_map = {
            "ollama": lambda m, mo, mt: failing_provider(m, mo, mt),
            "openai": lambda m, mo, mt: working_provider(m, mo, mt),
        }
        original_providers = st._STREAM_PROVIDERS.copy()
        st._STREAM_PROVIDERS.update(providers_map)

        original_keepalive = st.KEEPALIVE_INTERVAL_SECONDS
        st.KEEPALIVE_INTERVAL_SECONDS = 999

        try:
            events = []
            async for event in st.stream_brain_chat(
                messages=[{"role": "user", "content": "test"}],
                mode="creative",
            ):
                events.append(event)

            parsed = [json.loads(e[6:-2]) for e in events]
            types = [p["type"] for p in parsed]

            # Should have error (recoverable), failover, token, done
            assert "error" in types or "failover" in types
            assert "token" in types
            assert "done" in types
        finally:
            st._get_streaming_provider_chain = original_chain_fn
            st._STREAM_PROVIDERS.clear()
            st._STREAM_PROVIDERS.update(original_providers)
            st.KEEPALIVE_INTERVAL_SECONDS = original_keepalive

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        """If all providers fail, should emit error event."""
        import backend.brain.streaming as st

        async def failing_provider(messages, model, max_tokens):
            raise st.StreamingError("Failed")
            yield ""  # pragma: no cover

        st._get_streaming_provider_chain = lambda: [
            {"name": "ollama", "model": "llama3.1:8b"},
        ]

        original_providers = st._STREAM_PROVIDERS.copy()
        st._STREAM_PROVIDERS["ollama"] = lambda m, mo, mt: failing_provider(m, mo, mt)

        try:
            events = []
            async for event in st.stream_brain_chat(
                messages=[{"role": "user", "content": "test"}],
                mode="creative",
            ):
                events.append(event)

            parsed = [json.loads(e[6:-2]) for e in events]
            error_events = [p for p in parsed if p["type"] == "error"]
            assert len(error_events) >= 1
            assert error_events[-1]["recoverable"] is False
        finally:
            st._STREAM_PROVIDERS.clear()
            st._STREAM_PROVIDERS.update(original_providers)

    @pytest.mark.asyncio
    async def test_system_prompt_injected_by_mode(self):
        """Stream should inject correct system prompt based on mode."""
        import backend.brain.streaming as st

        captured_messages = []

        async def capture_provider(messages, model, max_tokens):
            captured_messages.extend(messages)
            yield "ok"

        original_chain_fn = st._get_streaming_provider_chain
        st._get_streaming_provider_chain = lambda: [
            {"name": "ollama", "model": "llama3.1:8b"},
        ]

        original_providers = st._STREAM_PROVIDERS.copy()
        st._STREAM_PROVIDERS["ollama"] = lambda m, mo, mt: capture_provider(m, mo, mt)

        original_keepalive = st.KEEPALIVE_INTERVAL_SECONDS
        st.KEEPALIVE_INTERVAL_SECONDS = 999

        try:
            events = []
            async for event in st.stream_brain_chat(
                messages=[{"role": "user", "content": "hello"}],
                mode="business_strategy",
            ):
                events.append(event)

            # The captured messages should have a system prompt as first message
            assert len(captured_messages) >= 2
            assert captured_messages[0]["role"] == "system"
            assert "Business Strategy" in captured_messages[0]["content"]
        finally:
            st._get_streaming_provider_chain = original_chain_fn
            st._STREAM_PROVIDERS.clear()
            st._STREAM_PROVIDERS.update(original_providers)
            st.KEEPALIVE_INTERVAL_SECONDS = original_keepalive

    @pytest.mark.asyncio
    async def test_max_tokens_capped_at_4096(self):
        """Even if user requests more, max_tokens should be capped at 4096."""
        import backend.brain.streaming as st

        captured_max_tokens = []

        async def capture_provider(messages, model, max_tokens):
            captured_max_tokens.append(max_tokens)
            yield "ok"

        original_chain_fn = st._get_streaming_provider_chain
        st._get_streaming_provider_chain = lambda: [
            {"name": "ollama", "model": "llama3.1:8b"},
        ]

        original_providers = st._STREAM_PROVIDERS.copy()
        st._STREAM_PROVIDERS["ollama"] = lambda m, mo, mt: capture_provider(m, mo, mt)

        original_keepalive = st.KEEPALIVE_INTERVAL_SECONDS
        st.KEEPALIVE_INTERVAL_SECONDS = 999

        try:
            events = []
            async for event in st.stream_brain_chat(
                messages=[{"role": "user", "content": "hello"}],
                mode="creative",
                max_tokens=10000,  # Exceeds budget
            ):
                events.append(event)

            # Provider should receive capped value
            assert captured_max_tokens[0] == 4096
        finally:
            st._get_streaming_provider_chain = original_chain_fn
            st._STREAM_PROVIDERS.clear()
            st._STREAM_PROVIDERS.update(original_providers)
            st.KEEPALIVE_INTERVAL_SECONDS = original_keepalive


# =============================================================================
# Router Endpoint Tests
# =============================================================================


class TestBrainStreamEndpoint:
    """Test the /api/v1/brain/chat/stream endpoint via TestClient."""

    def test_stream_endpoint_requires_messages(self, api_client):
        """POST without messages should return 400."""
        resp = api_client.post("/api/v1/brain/chat/stream", json={})
        assert resp.status_code == 400
        assert "'messages' or 'message' required" in resp.json()["detail"]

    def test_stream_endpoint_accepts_single_message(self, api_client):
        """POST with single 'message' string should work (returns SSE stream)."""
        with patch("backend.brain.streaming.stream_brain_chat") as mock_stream:

            async def mock_gen(*args, **kwargs):
                yield 'data: {"type": "done", "provider": "mock", "tokens": 0}\n\n'

            mock_stream.return_value = mock_gen()
            resp = api_client.post(
                "/api/v1/brain/chat/stream",
                json={"message": "hello"},
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")


class TestBrainModesEndpoint:
    """Test the /api/v1/brain/modes endpoint."""

    def test_modes_endpoint_returns_all_modes(self, api_client):
        """GET /modes should return all 7 modes."""
        resp = api_client.get("/api/v1/brain/modes")
        assert resp.status_code == 200
        modes = resp.json()
        assert len(modes) == 7
        mode_values = [m["mode"] for m in modes]
        assert "business_strategy" in mode_values
        assert "creative" in mode_values
        assert "prompt_engineer" in mode_values
