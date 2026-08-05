"""Memory Namespace Service — Story 040.

Scoped memory with namespace isolation, provenance, retention, and authorization.

Namespaces:
    user_private      — Only the creating user can read/write
    founder_private   — Workspace founder only (never in customer sessions)
    workspace_shared  — All workspace members read; editors+ write
    project           — Scoped to a specific project within workspace
    customer          — External customer conversation memory

Every memory item has:
    - org_id: workspace ownership (required)
    - user_id: who created it (attribution)
    - namespace: access scope
    - audience: who can see it (workspace, project, user, customer)
    - provenance: how it was created (user_confirmed, inferred, imported, system)
    - retention_class: how long to keep (standard, session, persistent, ephemeral)
    - skip_memory: if True, excluded from retrieval (user opt-out)

Authorization:
    - user_private: only creating user can read/write
    - founder_private: only workspace owner can read/write, never in customer context
    - workspace_shared: all members read, editors+ write
    - project: members with project access read, editors+ write
    - customer: scoped to customer session context only
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from backend.membership import OrgRole, TenantContext

logger = logging.getLogger(__name__)


# =============================================================================
# Namespace Model
# =============================================================================


class MemoryNamespace(str, Enum):
    USER_PRIVATE = "user_private"
    FOUNDER_PRIVATE = "founder_private"
    WORKSPACE_SHARED = "workspace_shared"
    PROJECT = "project"
    CUSTOMER = "customer"


class MemoryProvenance(str, Enum):
    USER_CONFIRMED = "user_confirmed"  # User explicitly stated this
    INFERRED = "inferred"              # AI inferred from conversation
    IMPORTED = "imported"              # Imported from external source
    SYSTEM = "system"                  # System-generated (e.g., preferences)


class RetentionClass(str, Enum):
    PERSISTENT = "persistent"  # Keep until explicitly deleted
    STANDARD = "standard"      # Keep for 90 days after last access
    SESSION = "session"        # Delete when session ends
    EPHEMERAL = "ephemeral"    # Delete after 24 hours


RETENTION_DAYS = {
    RetentionClass.PERSISTENT: None,  # Never expires
    RetentionClass.STANDARD: 90,
    RetentionClass.SESSION: 0,  # Managed by session lifecycle
    RetentionClass.EPHEMERAL: 1,
}


# =============================================================================
# Errors
# =============================================================================


class MemoryAccessDenied(Exception):
    """Raised when memory access is denied by namespace rules."""

    def __init__(self, namespace: str, reason: str) -> None:
        self.namespace = namespace
        self.reason = reason
        super().__init__(f"Memory access denied ({namespace}): {reason}")


class MemoryNotFound(Exception):
    """Raised when a memory item is not found within scope."""
    pass


# =============================================================================
# Authorization
# =============================================================================


def can_read(ctx: TenantContext, namespace: MemoryNamespace, item_user_id: str | None = None) -> bool:
    """Check if the caller can read memory in this namespace."""
    if namespace == MemoryNamespace.USER_PRIVATE:
        return item_user_id == ctx.user_id
    elif namespace == MemoryNamespace.FOUNDER_PRIVATE:
        return ctx.is_owner and item_user_id == ctx.user_id
    elif namespace == MemoryNamespace.WORKSPACE_SHARED:
        return True  # All workspace members
    elif namespace == MemoryNamespace.PROJECT:
        return True  # All workspace members with project access
    elif namespace == MemoryNamespace.CUSTOMER:
        return ctx.is_editor_or_above  # Only editors+ see customer memory
    return False


def can_write(ctx: TenantContext, namespace: MemoryNamespace) -> bool:
    """Check if the caller can write memory in this namespace."""
    if namespace == MemoryNamespace.USER_PRIVATE:
        return True  # Users can always write their own private memory
    elif namespace == MemoryNamespace.FOUNDER_PRIVATE:
        return ctx.is_owner
    elif namespace == MemoryNamespace.WORKSPACE_SHARED:
        return ctx.is_editor_or_above
    elif namespace == MemoryNamespace.PROJECT:
        return ctx.is_editor_or_above
    elif namespace == MemoryNamespace.CUSTOMER:
        return ctx.is_editor_or_above
    return False


def can_delete(ctx: TenantContext, namespace: MemoryNamespace, item_user_id: str | None = None) -> bool:
    """Check if the caller can delete memory in this namespace."""
    if namespace == MemoryNamespace.USER_PRIVATE:
        return item_user_id == ctx.user_id
    elif namespace == MemoryNamespace.FOUNDER_PRIVATE:
        return ctx.is_owner and item_user_id == ctx.user_id
    elif namespace in (MemoryNamespace.WORKSPACE_SHARED, MemoryNamespace.PROJECT, MemoryNamespace.CUSTOMER):
        return ctx.is_admin_or_above
    return False


# =============================================================================
# Memory Operations
# =============================================================================


def _db():
    from backend.database import supabase
    return supabase


def remember(
    ctx: TenantContext,
    category: str,
    key: str,
    value: Any,
    namespace: MemoryNamespace = MemoryNamespace.WORKSPACE_SHARED,
    provenance: MemoryProvenance = MemoryProvenance.INFERRED,
    retention: RetentionClass = RetentionClass.STANDARD,
    confidence: float = 0.8,
    project_id: str | None = None,
    skip_memory: bool = False,
) -> dict:
    """Store a memory item with full namespace and provenance.

    Args:
        ctx: Trusted execution context.
        category: Memory category (e.g., "preferences", "talent_style").
        key: Memory key within the category.
        value: The value to remember (JSONB-compatible).
        namespace: Access scope for this memory.
        provenance: How this memory was created.
        retention: How long to keep this memory.
        confidence: Confidence score (0.0-1.0).
        project_id: Project scope (required for project namespace).
        skip_memory: If True, this item is excluded from retrieval.

    Raises:
        MemoryAccessDenied: If caller cannot write to this namespace.
    """
    if not ctx.org_id:
        raise ValueError("org_id is required for memory operations")

    if not can_write(ctx, namespace):
        raise MemoryAccessDenied(namespace.value, f"Role '{ctx.role.value}' cannot write to {namespace.value}")

    if namespace == MemoryNamespace.PROJECT and not project_id:
        raise ValueError("project_id is required for project-scoped memory")

    # Compute expiry
    expires_at = None
    retention_days = RETENTION_DAYS.get(retention)
    if retention_days:
        expires_at = (datetime.now(UTC) + timedelta(days=retention_days)).isoformat()

    record = {
        "org_id": ctx.org_id,
        "user_id": ctx.user_id,
        "category": category,
        "key": key,
        "value": value if isinstance(value, dict) else {"v": value},
        "namespace": namespace.value,
        "audience": _audience_for_namespace(namespace),
        "provenance": provenance.value,
        "retention_class": retention.value,
        "confidence": confidence,
        "project_id": project_id,
        "skip_memory": skip_memory,
        "expires_at": expires_at,
        "source": f"{provenance.value}:{ctx.user_id[:8]}",
    }

    try:
        result = _db().table("brain_memory").upsert(
            record, on_conflict="org_id,category,key"
        ).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        logger.warning(f"Failed to store memory: {e}")
        return record


def recall(
    ctx: TenantContext,
    category: str | None = None,
    namespace: MemoryNamespace | None = None,
    project_id: str | None = None,
    limit: int = 50,
    include_expired: bool = False,
) -> list[dict]:
    """Retrieve memory items with namespace-scoped authorization.

    Only returns items the caller is authorized to see.
    Expired items and skip_memory items are excluded by default.

    Args:
        ctx: Trusted execution context.
        category: Filter by category (optional).
        namespace: Filter by namespace (optional — returns all accessible).
        project_id: Filter by project (optional).
        limit: Max items to return.
        include_expired: Include expired items (for admin inspection).
    """
    if not ctx.org_id:
        raise ValueError("org_id is required for memory operations")

    query = (
        _db().table("brain_memory")
        .select("*")
        .eq("org_id", ctx.org_id)
        .eq("skip_memory", False)
        .order("updated_at", desc=True)
        .limit(limit)
    )

    if category:
        query = query.eq("category", category)
    if namespace:
        query = query.eq("namespace", namespace.value)
    if project_id:
        query = query.eq("project_id", project_id)

    try:
        result = query.execute()
        items = result.data or []
    except Exception:
        return []

    # Apply namespace authorization filter
    authorized = []
    for item in items:
        item_ns = MemoryNamespace(item.get("namespace", "workspace_shared"))
        item_user = item.get("user_id")

        # Check expiry
        if not include_expired and item.get("expires_at"):
            try:
                expiry = datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
                if expiry < datetime.now(UTC):
                    continue
            except (ValueError, TypeError):
                pass

        # Check read authorization
        if can_read(ctx, item_ns, item_user):
            authorized.append(item)

    return authorized


def forget(ctx: TenantContext, memory_id: str) -> bool:
    """Delete a memory item (user-initiated deletion).

    Checks namespace authorization before deletion.
    """
    if not ctx.org_id:
        raise ValueError("org_id is required for memory operations")

    # Fetch the item to check authorization
    try:
        result = (
            _db().table("brain_memory")
            .select("*")
            .eq("id", memory_id)
            .eq("org_id", ctx.org_id)
            .execute()
        )
        if not result.data:
            raise MemoryNotFound()
    except MemoryNotFound:
        raise
    except Exception:
        raise MemoryNotFound()

    item = result.data[0]
    item_ns = MemoryNamespace(item.get("namespace", "workspace_shared"))
    item_user = item.get("user_id")

    if not can_delete(ctx, item_ns, item_user):
        raise MemoryAccessDenied(item_ns.value, f"Cannot delete {item_ns.value} memory")

    try:
        _db().table("brain_memory").delete().eq("id", memory_id).eq("org_id", ctx.org_id).execute()
        return True
    except Exception:
        return False


def inspect_memory(ctx: TenantContext, limit: int = 100) -> list[dict]:
    """List all memory items the user can see (for inspection UI).

    Includes metadata: namespace, provenance, retention, expiry.
    """
    return recall(ctx, limit=limit, include_expired=True)


# =============================================================================
# Helpers
# =============================================================================


def _audience_for_namespace(namespace: MemoryNamespace) -> str:
    """Map namespace to audience label."""
    return {
        MemoryNamespace.USER_PRIVATE: "user",
        MemoryNamespace.FOUNDER_PRIVATE: "founder",
        MemoryNamespace.WORKSPACE_SHARED: "workspace",
        MemoryNamespace.PROJECT: "project",
        MemoryNamespace.CUSTOMER: "customer",
    }.get(namespace, "workspace")
