"""AIOS Session Management — tenant-scoped, persistent sessions.

All operations require org_id and user_id from TenantContext.
Sessions survive server restarts and are accessible across instances.

Tables used:
- aios_sessions: session metadata (id, org_id, user_id, mode, created_at)
- aios_messages: individual messages (session_id, org_id, role, content)

Ownership:
- Sessions are DIRECT-owned (org_id column).
- Messages are DENORMALIZED (org_id on each row for efficient queries)
  AND inherit via session_id FK.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def _db():
    from backend.database import supabase
    return supabase


def create_session(
    org_id: str,
    user_id: str,
    mode: str = "creative",
    talent_id: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Create a new AIOS session scoped to a tenant.

    Args:
        org_id: Required. Workspace that owns this session.
        user_id: Required. User who initiated the session.
        mode: Session mode (creative, prompt_engineer, etc.)
    """
    if not org_id:
        raise ValueError("org_id is required for session creation")
    if not user_id:
        raise ValueError("user_id is required for session creation")

    session_id = uuid.uuid4().hex[:16]
    record = {
        "id": session_id,
        "org_id": org_id,
        "user_id": user_id,
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
        return {**record, "messages": [], "_in_memory": True}


def get_session(session_id: str, org_id: str) -> dict | None:
    """Get a session with its messages, scoped to tenant.

    Returns None if session doesn't exist or belongs to another org
    (no existence leak).
    """
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")

    try:
        result = (
            _db().table("aios_sessions")
            .select("*")
            .eq("id", session_id)
            .eq("org_id", org_id)
            .execute()
        )
        if not result.data:
            return None
        session = result.data[0]

        # Get messages (also scoped by org_id for defense-in-depth)
        messages = (
            _db().table("aios_messages")
            .select("*")
            .eq("session_id", session_id)
            .eq("org_id", org_id)
            .order("created_at")
            .execute().data or []
        )
        session["messages"] = messages
        return session
    except Exception as e:
        logger.warning(f"Failed to fetch session {session_id}: {e}")
        return None


def add_message(session_id: str, org_id: str, role: str, content: str) -> dict:
    """Add a message to a session, scoped to tenant.

    org_id is denormalized onto the message for efficient tenant queries.
    """
    if not org_id:
        raise ValueError("org_id is required for message creation")

    record = {
        "session_id": session_id,
        "org_id": org_id,
        "role": role,
        "content": content,
    }
    try:
        result = _db().table("aios_messages").insert(record).execute()
        # Update message count
        _db().table("aios_sessions").update({
            "message_count": _db().table("aios_messages").select("id", count="exact").eq("session_id", session_id).eq("org_id", org_id).execute().count or 0,
            "updated_at": "now()",
        }).eq("id", session_id).eq("org_id", org_id).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        logger.warning(f"Failed to persist message: {e}")
        return record


def list_sessions(org_id: str, limit: int = 20) -> list[dict]:
    """List recent sessions for a tenant."""
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped queries")

    try:
        result = (
            _db().table("aios_sessions")
            .select("*")
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception:
        return []


def delete_session(session_id: str, org_id: str) -> bool:
    """Delete a session and its messages, scoped to tenant.

    Only deletes if the session belongs to the specified org.
    """
    if not org_id:
        raise ValueError("org_id is required for tenant-scoped deletes")

    try:
        # Delete messages first (FK cascade may handle this, but be explicit)
        _db().table("aios_messages").delete().eq("session_id", session_id).eq("org_id", org_id).execute()
        # Delete session (only if owned by this org)
        result = _db().table("aios_sessions").delete().eq("id", session_id).eq("org_id", org_id).execute()
        return bool(result.data)
    except Exception:
        return False
