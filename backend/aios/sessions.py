"""AIOS Session Management — persistent sessions in Supabase.

Replaces the in-memory brain session store with database-backed sessions.
Sessions survive server restarts and are accessible across Vercel instances.

Tables used:
- aios_sessions: session metadata (id, mode, talent_id, created_at)
- aios_messages: individual messages (session_id, role, content, timestamp)
"""

from __future__ import annotations

import logging
import time
import uuid

logger = logging.getLogger(__name__)


def _db():
    from backend.database import supabase
    return supabase


def create_session(
    mode: str = "creative",
    talent_id: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Create a new AIOS session."""
    session_id = uuid.uuid4().hex[:16]
    record = {
        "id": session_id,
        "mode": mode,
        "talent_id": talent_id,
        "project_id": project_id,
        "message_count": 0,
        "status": "active",
    }
    try:
        result = _db().table("aios_sessions").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        logger.warning(f"Failed to persist session: {e}")
        # Return in-memory fallback
        return {**record, "messages": [], "_in_memory": True}


def get_session(session_id: str) -> dict | None:
    """Get a session with its messages."""
    try:
        # Get session
        session = _db().table("aios_sessions").select("*").eq("id", session_id).single().execute().data
        if not session:
            return None

        # Get messages
        messages = (
            _db().table("aios_messages")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at")
            .execute().data or []
        )
        session["messages"] = messages
        return session
    except Exception as e:
        logger.warning(f"Failed to fetch session {session_id}: {e}")
        return None


def add_message(session_id: str, role: str, content: str) -> dict:
    """Add a message to a session."""
    record = {
        "session_id": session_id,
        "role": role,
        "content": content,
    }
    try:
        result = _db().table("aios_messages").insert(record).execute()
        # Update message count
        _db().table("aios_sessions").update({
            "message_count": _db().table("aios_messages").select("id", count="exact").eq("session_id", session_id).execute().count or 0,
            "updated_at": "now()",
        }).eq("id", session_id).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        logger.warning(f"Failed to persist message: {e}")
        return record


def list_sessions(limit: int = 20) -> list[dict]:
    """List recent sessions."""
    try:
        result = (
            _db().table("aios_sessions")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception:
        return []


def delete_session(session_id: str) -> bool:
    """Delete a session and its messages."""
    try:
        _db().table("aios_messages").delete().eq("session_id", session_id).execute()
        _db().table("aios_sessions").delete().eq("id", session_id).execute()
        return True
    except Exception:
        return False
