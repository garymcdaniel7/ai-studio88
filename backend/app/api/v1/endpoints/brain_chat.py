"""Canonical SQL-backed Brain chat completion endpoint."""

from __future__ import annotations

import asyncio
import hashlib
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.services.brain_conversation_service import BrainConversationService
from app.services.brain_memory_service import BrainMemoryService

router = APIRouter(prefix="/brain", tags=["brain"])


@router.post("/chat")
async def complete_brain_chat(body: dict, tenant: TenantContextDep, db: DBSessionDep) -> dict:
    """Complete a turn using canonical conversation and memory persistence."""
    message = str(body.get("message", "")).strip()
    if not message:
        raise HTTPException(status_code=400, detail="'message' required")
    mode = str(body.get("mode", "creative"))
    conversations = BrainConversationService(db=db)
    raw_id = body.get("conversation_id")
    if raw_id:
        try:
            conversation_id = UUID(str(raw_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid conversation_id") from exc
        conversation = await conversations.get_conversation(
            conversation_id=conversation_id, org_id=tenant.org_id, user_id=tenant.user_id
        )
    else:
        conversation = await conversations.create_conversation(
            org_id=tenant.org_id, user_id=tenant.user_id, mode=mode,
            title=message[:80], role=tenant.role.value,
        )
        conversation_id = conversation.id

    recent = await conversations.get_recent_messages(
        conversation_id=conversation_id, org_id=tenant.org_id, user_id=tenant.user_id
    )
    memory = await BrainMemoryService(db=db).get_active_memory_for_context(
        tenant.org_id, tenant.user_id, limit=20
    )
    from backend.aios.persona import inject_persona
    from backend.brain.llm_provider import chat, get_system_prompt

    system = inject_persona(get_system_prompt(mode))
    if memory:
        system += "\n\n[AUTHORIZED USER MEMORY]\n" + "\n".join(
            f"- [{item.provenance}] {item.content}" for item in memory
        )
    messages = [{"role": "system", "content": system}]
    messages.extend({
        "role": "assistant" if item.actor == "brain" else item.actor,
        "content": item.content,
    } for item in recent)
    messages.append({"role": "user", "content": message})

    if conversation.message_count >= 198:
        summary = "\n".join(f"{item.actor}: {item.content}" for item in recent)
        await BrainMemoryService(db=db).create_memory(
            org_id=tenant.org_id, user_id=tenant.user_id,
            memory_type="conversation_summary", content={"summary": summary[-12000:]},
            provenance="INFERRED", confidence=0.8, source_conversation_id=conversation_id,
        )
        await conversations.compact_conversation(
            conversation_id=conversation_id, org_id=tenant.org_id, user_id=tenant.user_id
        )

    await conversations.add_message(
        conversation_id=conversation_id, org_id=tenant.org_id, user_id=tenant.user_id,
        actor="user", content=message,
    )
    response_text = await asyncio.to_thread(
        chat,
        messages,
        mode=mode,
        org_id=str(tenant.org_id),
        actor=str(tenant.user_id),
        idempotency_key=(
            f"brain:{conversation_id}:{conversation.message_count}:"
            f"{hashlib.sha256(message.encode()).hexdigest()}"
        ),
    )
    await conversations.add_message(
        conversation_id=conversation_id, org_id=tenant.org_id, user_id=tenant.user_id,
        actor="brain", content=response_text,
    )
    return {
        "conversation_id": str(conversation_id), "session_id": str(conversation_id),
        "response": response_text, "provider": "configured", "mode": mode,
    }
