"""Endpoint-level contract tests for canonical Brain chat wiring."""

from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import brain_chat


@pytest.mark.asyncio
async def test_complete_brain_chat_persists_user_and_brain_messages(monkeypatch):
    conversation_id = uuid4()
    conversation = SimpleNamespace(id=conversation_id, message_count=0)
    service = SimpleNamespace(
        create_conversation=AsyncMock(return_value=conversation),
        get_recent_messages=AsyncMock(return_value=[]),
        add_message=AsyncMock(),
    )
    memory = SimpleNamespace(get_active_memory_for_context=AsyncMock(return_value=[]))
    monkeypatch.setattr(brain_chat, "BrainConversationService", lambda db: service)
    monkeypatch.setattr(brain_chat, "BrainMemoryService", lambda db: memory)
    monkeypatch.setattr(
        "backend.brain.llm_provider.chat", lambda messages, mode="creative": "locked reply"
    )

    tenant = SimpleNamespace(
        org_id=uuid4(), user_id=uuid4(), role=SimpleNamespace(value="owner")
    )
    result = await brain_chat.complete_brain_chat(
        {"message": "Keep the identity bible consistent", "mode": "creative"},
        tenant,
        AsyncMock(),
    )

    assert result["conversation_id"] == str(conversation_id)
    assert result["response"] == "locked reply"
    assert [call.kwargs["actor"] for call in service.add_message.await_args_list] == [
        "user",
        "brain",
    ]
    assert service.add_message.await_args_list[0].kwargs["content"] == "Keep the identity bible consistent"
