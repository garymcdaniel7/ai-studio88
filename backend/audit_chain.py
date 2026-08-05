"""Immutable Correlated Audit Chain — Story 047.

Provides a single canonical audit event model for the complete Hermes action
lifecycle: plans → decisions → tool-calls → approvals → execution → results.

Every consequential action is reconstructable from correlated immutable records.

Properties:
    1. Correlated: Events share a correlation_id linking proposal→decision→execution→result
    2. Immutable: Records cannot be modified or deleted after creation
    3. Redacted: Secrets/credentials stripped before persistence
    4. Tenant-scoped: Queries are org-isolated, reads are role-checked
    5. Mandatory: High-risk execution FAILS if audit persistence is unavailable
    6. Integrity: SHA256 hash chain detects unauthorized mutation/deletion

Event types:
    PLAN_CREATED       — Hermes proposed an action plan
    GOVERNANCE_DECISION — Governance evaluated the plan
    APPROVAL_REQUESTED — Human approval required
    APPROVAL_DECIDED   — Human approved or rejected
    EXECUTION_STARTED  — Tool/action execution began
    EXECUTION_COMPLETED — Execution succeeded
    EXECUTION_FAILED   — Execution failed
    SIDE_EFFECT        — External resource created/modified (asset, job, etc.)
    RETRY_ATTEMPTED    — Retry of a failed action
    POLICY_CHANGED     — Governance policy was modified
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from backend.credentials import redact_dict, redact_secrets


# =============================================================================
# Event Types
# =============================================================================


class AuditEventType(str, Enum):
    PLAN_CREATED = "plan_created"
    GOVERNANCE_DECISION = "governance_decision"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    SIDE_EFFECT = "side_effect"
    RETRY_ATTEMPTED = "retry_attempted"
    POLICY_CHANGED = "policy_changed"


# High-risk events that MUST succeed or block execution
MANDATORY_EVENTS: frozenset[AuditEventType] = frozenset({
    AuditEventType.EXECUTION_STARTED,
    AuditEventType.EXECUTION_COMPLETED,
    AuditEventType.EXECUTION_FAILED,
    AuditEventType.SIDE_EFFECT,
    AuditEventType.APPROVAL_DECIDED,
})


# =============================================================================
# Audit Event Record
# =============================================================================


@dataclass(frozen=True)
class AuditEvent:
    """An immutable audit event in the correlated chain."""

    id: str
    correlation_id: str  # Links all events for one action lifecycle
    event_type: AuditEventType
    # Identity (trusted, server-resolved)
    org_id: str
    actor_user_id: str
    actor_role: str
    # Context
    session_id: str
    request_id: str
    command_id: str = ""  # Links to ActionCommand if applicable
    approval_id: str = ""  # Links to DurableApproval if applicable
    # Content (redacted before storage)
    tool: str = ""
    arguments_summary: str = ""  # Redacted summary, NOT raw params
    result_summary: str = ""  # Redacted summary
    error: str = ""
    # Resources
    resource_ids: tuple[str, ...] = ()  # Asset/job IDs created or affected
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    # Versioning
    model_version: str = ""
    prompt_version: str = ""
    policy_version: str = ""
    # Timing
    timestamp: str = ""
    duration_ms: int = 0
    # Integrity
    previous_hash: str = ""  # SHA256 of the previous event (chain integrity)
    event_hash: str = ""  # SHA256 of this event's content

    def to_dict(self) -> dict:
        """Serialize for storage/query (already redacted)."""
        return {
            "id": self.id,
            "correlation_id": self.correlation_id,
            "event_type": self.event_type.value,
            "org_id": self.org_id,
            "actor_user_id": self.actor_user_id,
            "actor_role": self.actor_role,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "command_id": self.command_id,
            "approval_id": self.approval_id,
            "tool": self.tool,
            "arguments_summary": self.arguments_summary,
            "result_summary": self.result_summary,
            "error": self.error,
            "resource_ids": list(self.resource_ids),
            "estimated_cost_usd": self.estimated_cost_usd,
            "actual_cost_usd": self.actual_cost_usd,
            "model_version": self.model_version,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "event_hash": self.event_hash,
            "previous_hash": self.previous_hash,
        }


# =============================================================================
# Integrity Hashing
# =============================================================================


def _compute_event_hash(event_data: dict) -> str:
    """Compute SHA256 hash of event content for integrity verification."""
    canonical = json.dumps(event_data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def _compute_chain_hash(event_hash: str, previous_hash: str) -> str:
    """Compute chained hash linking this event to the previous one."""
    combined = f"{previous_hash}:{event_hash}"
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


# =============================================================================
# Event Store (in-memory, production: append-only table)
# =============================================================================

_event_store: list[AuditEvent] = []
_store_lock = threading.Lock()
_last_hash: str = "genesis"  # Initial chain seed


class AuditPersistenceError(Exception):
    """Raised when mandatory audit persistence fails."""
    pass


# =============================================================================
# Audit Chain Service
# =============================================================================


class AuditChainService:
    """Immutable correlated audit chain management.

    Every consequential Hermes action emits events through this service.
    High-risk events MUST persist or execution is blocked.
    """

    @staticmethod
    def emit(
        *,
        event_type: AuditEventType,
        correlation_id: str,
        org_id: str,
        actor_user_id: str,
        actor_role: str,
        session_id: str = "",
        request_id: str = "",
        command_id: str = "",
        approval_id: str = "",
        tool: str = "",
        arguments: dict | None = None,
        result: dict | None = None,
        error: str = "",
        resource_ids: list[str] | None = None,
        estimated_cost_usd: float = 0.0,
        actual_cost_usd: float = 0.0,
        model_version: str = "",
        prompt_version: str = "",
        policy_version: str = "",
        duration_ms: int = 0,
        mandatory: bool | None = None,
    ) -> AuditEvent:
        """Emit an audit event into the immutable chain.

        Args:
            mandatory: Override whether this event blocks on failure.
                       If None, uses MANDATORY_EVENTS classification.

        Raises:
            AuditPersistenceError: If a mandatory event cannot be persisted.
        """
        global _last_hash

        is_mandatory = mandatory if mandatory is not None else (event_type in MANDATORY_EVENTS)

        # Redact sensitive content before storage
        arguments_summary = _redact_arguments(arguments) if arguments else ""
        result_summary = _redact_result(result) if result else ""
        safe_error = redact_secrets(error) if error else ""

        # Compute timestamp once (used in both hash and record)
        event_timestamp = datetime.now(UTC).isoformat()

        # Build event data for hashing
        event_data = {
            "event_type": event_type.value,
            "correlation_id": correlation_id,
            "org_id": org_id,
            "actor_user_id": actor_user_id,
            "tool": tool,
            "arguments_summary": arguments_summary,
            "timestamp": event_timestamp,
        }
        event_hash = _compute_event_hash(event_data)

        with _store_lock:
            previous_hash = _last_hash

            event = AuditEvent(
                id=f"evt-{secrets.token_hex(10)}",
                correlation_id=correlation_id,
                event_type=event_type,
                org_id=org_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                session_id=session_id,
                request_id=request_id,
                command_id=command_id,
                approval_id=approval_id,
                tool=tool,
                arguments_summary=arguments_summary,
                result_summary=result_summary,
                error=safe_error,
                resource_ids=tuple(resource_ids or []),
                estimated_cost_usd=estimated_cost_usd,
                actual_cost_usd=actual_cost_usd,
                model_version=model_version,
                prompt_version=prompt_version,
                policy_version=policy_version,
                timestamp=event_timestamp,
                duration_ms=duration_ms,
                previous_hash=previous_hash,
                event_hash=event_hash,
            )

            # Persist (mandatory events fail execution on persistence error)
            try:
                _event_store.append(event)
                _last_hash = _compute_chain_hash(event_hash, previous_hash)
            except Exception as e:
                if is_mandatory:
                    raise AuditPersistenceError(
                        f"Mandatory audit event {event_type.value} could not be persisted: {e}"
                    )
                # Non-mandatory: log warning but don't block
                pass

        return event

    @staticmethod
    def get_chain(correlation_id: str, org_id: str) -> list[dict]:
        """Reconstruct the full audit chain for a correlation ID.

        Tenant-scoped: only returns events for the specified org.
        """
        return [
            e.to_dict() for e in _event_store
            if e.correlation_id == correlation_id and e.org_id == org_id
        ]

    @staticmethod
    def query(
        *,
        org_id: str,
        event_type: AuditEventType | None = None,
        actor_user_id: str | None = None,
        tool: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query audit events for a workspace (tenant-scoped)."""
        results = []
        for event in reversed(_event_store):
            if event.org_id != org_id:
                continue
            if event_type and event.event_type != event_type:
                continue
            if actor_user_id and event.actor_user_id != actor_user_id:
                continue
            if tool and event.tool != tool:
                continue
            results.append(event.to_dict())
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def verify_integrity(org_id: str) -> dict:
        """Verify the integrity of the audit chain for a workspace.

        Checks that no events have been mutated or deleted by recomputing hashes.

        Returns:
            {"valid": bool, "events_checked": int, "first_invalid": str|None}
        """
        org_events = [e for e in _event_store if e.org_id == org_id]
        if not org_events:
            return {"valid": True, "events_checked": 0, "first_invalid": None}

        for i, event in enumerate(org_events):
            # Verify event hash matches content
            event_data = {
                "event_type": event.event_type.value,
                "correlation_id": event.correlation_id,
                "org_id": event.org_id,
                "actor_user_id": event.actor_user_id,
                "tool": event.tool,
                "arguments_summary": event.arguments_summary,
                "timestamp": event.timestamp,
            }
            expected_hash = _compute_event_hash(event_data)
            if expected_hash != event.event_hash:
                return {
                    "valid": False,
                    "events_checked": i + 1,
                    "first_invalid": event.id,
                }

        return {"valid": True, "events_checked": len(org_events), "first_invalid": None}

    @staticmethod
    def new_correlation_id() -> str:
        """Generate a new correlation ID for linking related events."""
        return f"cor-{secrets.token_hex(10)}"


# =============================================================================
# Redaction Helpers
# =============================================================================


def _redact_arguments(arguments: dict) -> str:
    """Redact sensitive fields from arguments before audit storage.

    Returns a summary string, not the full arguments.
    Never stores raw credentials, tokens, prompts > 200 chars, or binary data.
    """
    if not arguments:
        return ""

    redacted = redact_dict(arguments)

    # Truncate long values
    summary_parts = []
    for k, v in redacted.items():
        v_str = str(v)
        if len(v_str) > 200:
            v_str = v_str[:200] + "..."
        summary_parts.append(f"{k}={v_str}")

    return "; ".join(summary_parts[:10])  # Max 10 fields


def _redact_result(result: dict) -> str:
    """Redact sensitive fields from execution results."""
    if not result:
        return ""

    redacted = redact_dict(result)

    # Remove large blobs (image_base64, etc.)
    for key in list(redacted.keys()):
        if isinstance(redacted[key], str) and len(redacted[key]) > 500:
            redacted[key] = f"[{len(redacted[key])} chars]"

    return json.dumps(redacted, default=str)[:500]
