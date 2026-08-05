"""Session & Memory Ownership Lifecycle — Story 046.

Enforces verified ownership, retention policy, deletion, and export controls
for agent sessions and memory items.

Rules:
1. New sessions/memories MUST have verified actor + workspace (no placeholders)
2. Zero-tenant (00000000...) and empty org_id are REJECTED
3. Retention class determines lifecycle (from Story 040: persistent/standard/session/ephemeral)
4. Authorized users can delete/export their eligible records
5. Cross-user, cross-workspace, cross-project retrieval is DENIED
6. Deletion cascades to related indexes, embeddings, and derived references

Retention enforcement:
    persistent  — kept until explicit user deletion
    standard    — 90 days after last access, then eligible for cleanup
    session     — deleted when parent session ends
    ephemeral   — deleted after 24 hours

DECISION-REQUIRED markers:
    - Legal hold behavior (no approved policy — enforcement point exists but is no-op)
    - Cross-workspace transfer (no approved policy — blocked by default)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from backend.membership import OrgRole, TenantContext

logger = logging.getLogger(__name__)

# Zero-tenant UUID that must always be rejected
ZERO_TENANT = "00000000-0000-0000-0000-000000000000"


# =============================================================================
# Retention Policy
# =============================================================================


class RetentionClass(str, Enum):
    PERSISTENT = "persistent"   # Until explicit deletion
    STANDARD = "standard"       # 90 days after last access
    SESSION = "session"         # Deleted with parent session
    EPHEMERAL = "ephemeral"     # 24 hours


RETENTION_DAYS: dict[RetentionClass, int | None] = {
    RetentionClass.PERSISTENT: None,  # Never auto-expires
    RetentionClass.STANDARD: 90,
    RetentionClass.SESSION: 0,        # Managed by session lifecycle
    RetentionClass.EPHEMERAL: 1,
}


class ExportEligibility(str, Enum):
    ELIGIBLE = "eligible"           # Can be exported by owner
    INELIGIBLE_AUDIT = "ineligible_audit"  # Audit records cannot be exported/deleted
    INELIGIBLE_HOLD = "ineligible_hold"    # DECISION-REQUIRED: legal hold
    INELIGIBLE_SHARED = "ineligible_shared"  # Shared records need admin


# =============================================================================
# Ownership Validation
# =============================================================================


class OwnershipError(Exception):
    """Raised when ownership validation fails."""
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Ownership validation failed: {reason}")


class LifecycleError(Exception):
    """Raised when a lifecycle operation is denied."""
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Lifecycle operation denied: {reason}")


def validate_ownership_context(
    user_id: str,
    org_id: str,
    purpose: str = "",
) -> None:
    """Validate that session/memory creation has verified ownership.

    Rejects:
    - Empty user_id or org_id
    - Zero-tenant placeholder
    - Placeholder org patterns

    Raises:
        OwnershipError: If ownership context is invalid.
    """
    if not user_id or not user_id.strip():
        raise OwnershipError("user_id is required — anonymous sessions not permitted")

    if not org_id or not org_id.strip():
        raise OwnershipError("org_id is required — unscoped sessions not permitted")

    if org_id == ZERO_TENANT:
        raise OwnershipError("Zero-tenant org_id rejected — use a real workspace")

    if org_id in ("default", "org_development", "placeholder"):
        raise OwnershipError(f"Placeholder org_id '{org_id}' rejected — use a real workspace")


# =============================================================================
# Lifecycle Operations
# =============================================================================


@dataclass
class DeletionResult:
    """Result of a deletion operation."""
    deleted_count: int = 0
    related_cleaned: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.deleted_count > 0 and not self.errors


@dataclass
class ExportResult:
    """Result of an export operation."""
    items: list[dict] = field(default_factory=list)
    total: int = 0
    format: str = "json"
    exported_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def delete_user_sessions(
    ctx: TenantContext,
    session_ids: list[str] | None = None,
) -> DeletionResult:
    """Delete agent sessions owned by the authenticated user.

    Cascades to:
    - Session messages (via FK CASCADE)
    - Related decision records (SET NULL on session_id)
    - Session-scoped memory items
    - Related embeddings (if linked)

    Args:
        ctx: Verified tenant context.
        session_ids: Specific sessions to delete (None = all user's sessions).

    Returns:
        DeletionResult with counts and any errors.
    """
    validate_ownership_context(ctx.user_id, ctx.org_id, "session_deletion")

    result = DeletionResult()

    try:
        from backend.aios.sessions import delete_session

        if session_ids:
            for sid in session_ids:
                if delete_session(sid, org_id=ctx.org_id):
                    result.deleted_count += 1
        else:
            # Delete all user's sessions in this workspace
            from backend.aios.sessions import list_sessions
            sessions = list_sessions(org_id=ctx.org_id)
            for session in sessions:
                if session.get("user_id") == ctx.user_id:
                    if delete_session(session["id"], org_id=ctx.org_id):
                        result.deleted_count += 1

        # Clean up session-scoped memory
        memory_cleaned = _cleanup_session_memory(ctx)
        if memory_cleaned:
            result.related_cleaned["session_memory"] = memory_cleaned

    except Exception as e:
        result.errors.append(f"Deletion error: {str(e)[:200]}")
        logger.error(f"Session deletion failed for {ctx.user_id[:8]}: {e}")

    return result


def delete_user_memories(
    ctx: TenantContext,
    category: str | None = None,
    memory_ids: list[str] | None = None,
) -> DeletionResult:
    """Delete memory items owned by the authenticated user.

    Only deletes memories the user is authorized to manage
    (per namespace rules from Story 040).

    Args:
        ctx: Verified tenant context.
        category: Delete all in this category (optional).
        memory_ids: Specific memory IDs (optional).
    """
    validate_ownership_context(ctx.user_id, ctx.org_id, "memory_deletion")

    result = DeletionResult()

    try:
        from backend.memory_service import forget, recall

        if memory_ids:
            for mid in memory_ids:
                try:
                    forget(ctx, mid)
                    result.deleted_count += 1
                except Exception:
                    pass  # Not found or not authorized — skip
        elif category:
            # Delete all user's memories in this category
            items = recall(ctx, category=category)
            for item in items:
                if item.get("user_id") == ctx.user_id:
                    try:
                        forget(ctx, item["id"])
                        result.deleted_count += 1
                    except Exception:
                        pass

    except Exception as e:
        result.errors.append(f"Memory deletion error: {str(e)[:200]}")
        logger.error(f"Memory deletion failed for {ctx.user_id[:8]}: {e}")

    return result


def export_user_data(
    ctx: TenantContext,
    include_sessions: bool = True,
    include_memories: bool = True,
    include_decisions: bool = False,  # Audit records — DECISION-REQUIRED for export
) -> ExportResult:
    """Export user's eligible data from this workspace.

    Eligibility rules:
    - Sessions owned by user: ELIGIBLE
    - Private memories: ELIGIBLE
    - Workspace-shared memories created by user: ELIGIBLE
    - Audit decisions: INELIGIBLE_AUDIT (unless DECISION-REQUIRED approval)
    - Memories under legal hold: INELIGIBLE_HOLD (DECISION-REQUIRED)

    Returns:
        ExportResult with serialized data.
    """
    validate_ownership_context(ctx.user_id, ctx.org_id, "data_export")

    export = ExportResult()

    if include_sessions:
        try:
            from backend.aios.sessions import list_sessions
            sessions = list_sessions(org_id=ctx.org_id)
            user_sessions = [s for s in sessions if s.get("user_id") == ctx.user_id]
            for session in user_sessions:
                export.items.append({
                    "type": "session",
                    "data": session,
                    "eligibility": ExportEligibility.ELIGIBLE.value,
                })
        except Exception as e:
            logger.warning(f"Session export partial failure: {e}")

    if include_memories:
        try:
            from backend.memory_service import recall, MemoryNamespace
            memories = recall(ctx)
            for mem in memories:
                # Only export user's own or shared memories they created
                if mem.get("user_id") == ctx.user_id:
                    export.items.append({
                        "type": "memory",
                        "data": _sanitize_for_export(mem),
                        "eligibility": ExportEligibility.ELIGIBLE.value,
                    })
        except Exception as e:
            logger.warning(f"Memory export partial failure: {e}")

    if include_decisions:
        # DECISION-REQUIRED: Whether audit records can be exported
        # For now, we include them as read-only copies (no deletion)
        try:
            from backend.aios.decisions import list_decisions
            decisions = list_decisions(org_id=ctx.org_id)
            user_decisions = [d for d in decisions if d.get("user_id") == ctx.user_id]
            for dec in user_decisions[:100]:  # Cap at 100
                export.items.append({
                    "type": "decision",
                    "data": _sanitize_for_export(dec),
                    "eligibility": ExportEligibility.INELIGIBLE_AUDIT.value,
                    "note": "Audit records are exported as read-only copies and cannot be deleted.",
                })
        except Exception as e:
            logger.warning(f"Decision export partial failure: {e}")

    export.total = len(export.items)
    return export


# =============================================================================
# Retention Enforcement
# =============================================================================


def get_retention_expiry(retention_class: RetentionClass, from_time: float | None = None) -> float | None:
    """Calculate expiry timestamp for a retention class.

    Returns None for persistent (never expires).
    """
    days = RETENTION_DAYS.get(retention_class)
    if days is None:
        return None  # Persistent
    base = from_time or time.time()
    return base + (days * 86400)


def is_expired(retention_class: RetentionClass, created_at: float, last_accessed: float | None = None) -> bool:
    """Check if a record has exceeded its retention period."""
    days = RETENTION_DAYS.get(retention_class)
    if days is None:
        return False  # Persistent never expires
    if days == 0:
        return False  # Session-scoped — managed by session lifecycle

    reference_time = last_accessed or created_at
    expiry = reference_time + (days * 86400)
    return time.time() > expiry


def check_legal_hold(record_id: str) -> bool:
    """Check if a record is under legal hold.

    DECISION-REQUIRED: No approved legal hold policy exists.
    This is a configurable enforcement point that always returns False
    until a policy is approved.
    """
    # DECISION-REQUIRED: Legal hold lookup not implemented
    # When implemented, this would check a legal_holds table
    return False


# =============================================================================
# Helpers
# =============================================================================


def _cleanup_session_memory(ctx: TenantContext) -> int:
    """Clean up memory items with session retention class."""
    try:
        from backend.memory_service import recall, forget, RetentionClass as MemRetention
        items = recall(ctx)
        cleaned = 0
        for item in items:
            if item.get("retention_class") == "session":
                try:
                    forget(ctx, item["id"])
                    cleaned += 1
                except Exception:
                    pass
        return cleaned
    except Exception:
        return 0


def _sanitize_for_export(record: dict) -> dict:
    """Remove internal fields before export."""
    excluded = {"_ownership_status", "org_id"}
    return {k: v for k, v in record.items() if k not in excluded}
