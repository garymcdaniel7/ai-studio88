"""Brain Memory — conversation history and production preferences.

Stores session conversations, remembers user preferences, and maintains
context across interactions. Influences future planning.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """A single message in a brain conversation."""
    id: str = ""
    role: str = "user"  # user, brain, system
    content: str = ""
    plan_id: str | None = None
    metadata: dict = field(default_factory=dict)
    timestamp: float = 0.0


@dataclass
class Session:
    """A brain conversation session."""
    id: str = ""
    messages: list[Message] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    created_at: float = 0.0


# =============================================================================
# In-memory stores (future: Supabase-backed)
# =============================================================================

_sessions: dict[str, Session] = {}
_production_memory: dict[str, Any] = {
    "favorite_prompts": [],
    "favorite_workflows": [],
    "favorite_models": ["flux-dev"],
    "favorite_loras": [],
    "favorite_voices": [],
    "favorite_camera_moves": ["dolly_in", "slow_pan"],
    "favorite_lighting": ["golden_hour", "warm_cinematic"],
    "favorite_editing_style": "cinematic",
    "favorite_platforms": ["instagram", "tiktok"],
    "favorite_posting_times": ["7pm EST"],
}


def create_session() -> Session:
    """Create a new brain session."""
    session = Session(
        id=uuid.uuid4().hex[:12],
        created_at=time.time(),
    )
    _sessions[session.id] = session
    return session


def get_session(session_id: str) -> Session | None:
    return _sessions.get(session_id)


def add_message(session_id: str, role: str, content: str, plan_id: str | None = None) -> Message:
    """Add a message to a session."""
    session = _sessions.get(session_id)
    if not session:
        session = create_session()
        _sessions[session.id] = session
        session_id = session.id

    msg = Message(
        id=uuid.uuid4().hex[:8],
        role=role,
        content=content,
        plan_id=plan_id,
        timestamp=time.time(),
    )
    session.messages.append(msg)
    return msg


def get_conversation_history(session_id: str, limit: int = 20) -> list[dict]:
    """Get recent conversation history."""
    session = _sessions.get(session_id)
    if not session:
        return []
    return [
        {"role": m.role, "content": m.content, "plan_id": m.plan_id, "timestamp": m.timestamp}
        for m in session.messages[-limit:]
    ]


def get_production_memory() -> dict:
    """Get accumulated production preferences."""
    return _production_memory.copy()


def update_production_memory(key: str, value: Any) -> None:
    """Update a production memory entry."""
    _production_memory[key] = value


def list_sessions() -> list[dict]:
    """List all sessions."""
    return [
        {"id": s.id, "messages": len(s.messages), "created_at": s.created_at}
        for s in _sessions.values()
    ]
