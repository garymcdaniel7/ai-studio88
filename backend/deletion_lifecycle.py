"""Recoverable Deletion Lifecycle — Story 069.

Implements trash/restore states, dependency blocking, audit transitions,
default query filtering, and purge-hold enforcement for all supported entities.

Lifecycle States:
    ACTIVE      → Normal operational state
    ARCHIVED    → Soft-hidden, still queryable with flag
    TRASHED     → Recoverable deletion (default reads exclude)
    HOLD        → Legal/consent/dependency hold blocks purge
    PURGE_PENDING → Approved for permanent deletion (awaiting cleanup)
    PURGED      → Permanently deleted (record retained for audit)

Supported Entities:
    - assets (content_jobs outputs)
    - ai_talent
    - projects
    - lora_models
    - brain_conversations
    - workflows
    - campaigns

Every transition records: actor, reason, timestamp, prior state.
Default queries filter to ACTIVE + ARCHIVED only.
Purge blocked when retention policy is UNVERIFIED or holds exist.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


# =============================================================================
# Lifecycle States
# =============================================================================


class LifecycleState(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    TRASHED = "trashed"
    HOLD = "hold"               # Legal/consent/dependency hold
    PURGE_PENDING = "purge_pending"
    PURGED = "purged"


class HoldType(str, Enum):
    LEGAL = "legal"             # Legal/litigation hold
    CONSENT = "consent"         # Consent withdrawal — must retain proof
    DEPENDENCY = "dependency"   # Active model/job references this
    AUDIT = "audit"             # Required for audit trail
    RETENTION = "retention"     # Retention period not expired
    UNVERIFIED = "unverified"   # Policy not yet defined — blocks purge


class TransitionAction(str, Enum):
    TRASH = "trash"
    RESTORE = "restore"
    ARCHIVE = "archive"
    UNARCHIVE = "unarchive"
    PLACE_HOLD = "place_hold"
    RELEASE_HOLD = "release_hold"
    APPROVE_PURGE = "approve_purge"
    PURGE = "purge"


# =============================================================================
# Valid Transitions
# =============================================================================

# Map: (current_state, action) → target_state
VALID_TRANSITIONS: dict[tuple[LifecycleState, TransitionAction], LifecycleState] = {
    # From ACTIVE
    (LifecycleState.ACTIVE, TransitionAction.TRASH): LifecycleState.TRASHED,
    (LifecycleState.ACTIVE, TransitionAction.ARCHIVE): LifecycleState.ARCHIVED,
    (LifecycleState.ACTIVE, TransitionAction.PLACE_HOLD): LifecycleState.HOLD,
    # From ARCHIVED
    (LifecycleState.ARCHIVED, TransitionAction.TRASH): LifecycleState.TRASHED,
    (LifecycleState.ARCHIVED, TransitionAction.UNARCHIVE): LifecycleState.ACTIVE,
    (LifecycleState.ARCHIVED, TransitionAction.PLACE_HOLD): LifecycleState.HOLD,
    # From TRASHED
    (LifecycleState.TRASHED, TransitionAction.RESTORE): LifecycleState.ACTIVE,
    (LifecycleState.TRASHED, TransitionAction.PLACE_HOLD): LifecycleState.HOLD,
    (LifecycleState.TRASHED, TransitionAction.APPROVE_PURGE): LifecycleState.PURGE_PENDING,
    # From HOLD
    (LifecycleState.HOLD, TransitionAction.RELEASE_HOLD): LifecycleState.TRASHED,
    # From PURGE_PENDING
    (LifecycleState.PURGE_PENDING, TransitionAction.PURGE): LifecycleState.PURGED,
    (LifecycleState.PURGE_PENDING, TransitionAction.PLACE_HOLD): LifecycleState.HOLD,
    (LifecycleState.PURGE_PENDING, TransitionAction.RESTORE): LifecycleState.ACTIVE,
}

# States visible in default queries (no special flags)
DEFAULT_VISIBLE_STATES: set[LifecycleState] = {
    LifecycleState.ACTIVE,
    LifecycleState.ARCHIVED,
}

# States that allow restoration
RESTORABLE_STATES: set[LifecycleState] = {
    LifecycleState.TRASHED,
    LifecycleState.PURGE_PENDING,
}

# Terminal state — no transitions out
TERMINAL_STATES: set[LifecycleState] = {
    LifecycleState.PURGED,
}


# =============================================================================
# Supported Entities
# =============================================================================

SUPPORTED_ENTITIES: dict[str, dict[str, Any]] = {
    "assets": {
        "table": "content_jobs",
        "has_storage": True,
        "retention_policy": "UNVERIFIED",  # DECISION-REQUIRED
        "default_retention_days": None,
    },
    "ai_talent": {
        "table": "ai_talent",
        "has_storage": True,
        "retention_policy": "UNVERIFIED",
        "default_retention_days": None,
    },
    "projects": {
        "table": "projects",
        "has_storage": False,
        "retention_policy": "UNVERIFIED",
        "default_retention_days": None,
    },
    "lora_models": {
        "table": "lora_models",
        "has_storage": True,
        "retention_policy": "UNVERIFIED",
        "default_retention_days": None,
    },
    "brain_conversations": {
        "table": "brain_conversations",
        "has_storage": False,
        "retention_policy": "UNVERIFIED",
        "default_retention_days": None,
    },
    "workflows": {
        "table": "workflows",
        "has_storage": False,
        "retention_policy": "UNVERIFIED",
        "default_retention_days": None,
    },
    "campaigns": {
        "table": "campaigns",
        "has_storage": False,
        "retention_policy": "UNVERIFIED",
        "default_retention_days": None,
    },
}


# =============================================================================
# Transition Record (Audit)
# =============================================================================


@dataclass
class TransitionRecord:
    """Immutable audit record of a lifecycle state change."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: str = ""
    entity_id: str = ""
    org_id: str = ""
    prior_state: LifecycleState = LifecycleState.ACTIVE
    new_state: LifecycleState = LifecycleState.ACTIVE
    action: TransitionAction = TransitionAction.TRASH
    actor_id: str = ""          # Who performed the action
    actor_role: str = ""        # Role at time of action
    reason: str = ""            # Human-readable reason
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    # Hold metadata (when placing hold)
    hold_type: HoldType | None = None
    hold_expires_at: str | None = None
    # Restoration metadata
    restored_name: str | None = None  # If name collision resolved

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "org_id": self.org_id,
            "prior_state": self.prior_state.value,
            "new_state": self.new_state.value,
            "action": self.action.value,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "hold_type": self.hold_type.value if self.hold_type else None,
            "hold_expires_at": self.hold_expires_at,
            "restored_name": self.restored_name,
        }


# =============================================================================
# Entity Lifecycle Record
# =============================================================================


@dataclass
class EntityLifecycle:
    """Tracks the lifecycle state of a single entity instance."""

    entity_type: str
    entity_id: str
    org_id: str
    state: LifecycleState = LifecycleState.ACTIVE
    trashed_at: str | None = None
    trashed_by: str | None = None
    trash_reason: str | None = None
    # Retention
    retention_deadline: str | None = None  # When purge becomes eligible
    retention_policy: str = "UNVERIFIED"
    # Holds
    active_holds: list[dict] = field(default_factory=list)
    # History
    transitions: list[TransitionRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "org_id": self.org_id,
            "state": self.state.value,
            "trashed_at": self.trashed_at,
            "trashed_by": self.trashed_by,
            "trash_reason": self.trash_reason,
            "retention_deadline": self.retention_deadline,
            "retention_policy": self.retention_policy,
            "active_holds_count": len(self.active_holds),
            "transition_count": len(self.transitions),
        }


# =============================================================================
# Dependency Registry
# =============================================================================


@dataclass
class DependencyCheck:
    """Result of checking if an entity has active dependencies."""

    has_dependencies: bool = False
    blocking_dependencies: list[dict] = field(default_factory=list)
    # Each entry: {"type": "lora_model", "id": "...", "reason": "Model in active use"}

    @property
    def blocks_purge(self) -> bool:
        return self.has_dependencies


# Dependency rules: entity_type → list of (dependent_type, relationship_description)
DEPENDENCY_RULES: dict[str, list[dict]] = {
    "ai_talent": [
        {"dependent_type": "lora_models", "relationship": "talent has trained models"},
        {"dependent_type": "assets", "relationship": "talent has generated assets"},
        {"dependent_type": "campaigns", "relationship": "talent is assigned to campaigns"},
    ],
    "projects": [
        {"dependent_type": "assets", "relationship": "project contains assets"},
        {"dependent_type": "campaigns", "relationship": "project has campaigns"},
    ],
    "lora_models": [
        {"dependent_type": "assets", "relationship": "model used in generation history"},
    ],
    "workflows": [
        {"dependent_type": "assets", "relationship": "workflow used in job history"},
    ],
}


def check_dependencies(
    entity_type: str,
    entity_id: str,
    active_children: dict[str, list[str]] | None = None,
) -> DependencyCheck:
    """Check if entity has active dependencies that block purge.

    Args:
        entity_type: The type of entity being checked
        entity_id: The ID of the entity
        active_children: Map of dependent_type → list of active IDs
                        (injected by caller from DB query results)
    """
    result = DependencyCheck()

    if active_children is None:
        active_children = {}

    rules = DEPENDENCY_RULES.get(entity_type, [])
    for rule in rules:
        dep_type = rule["dependent_type"]
        if dep_type in active_children and active_children[dep_type]:
            result.has_dependencies = True
            result.blocking_dependencies.append({
                "type": dep_type,
                "count": len(active_children[dep_type]),
                "ids": active_children[dep_type][:5],  # Show first 5
                "reason": rule["relationship"],
            })

    return result


# =============================================================================
# Transition Engine
# =============================================================================


class TransitionError(Exception):
    """Raised when a lifecycle transition is invalid."""

    def __init__(self, message: str, code: str = "INVALID_TRANSITION"):
        self.message = message
        self.code = code
        super().__init__(message)


class PurgeBlockedError(TransitionError):
    """Raised when purge is blocked by holds or missing policy."""

    def __init__(self, message: str, holds: list[dict] | None = None):
        self.holds = holds or []
        super().__init__(message, code="PURGE_BLOCKED")


def validate_transition(
    entity: EntityLifecycle,
    action: TransitionAction,
    *,
    actor_id: str = "",
    actor_role: str = "",
    reason: str = "",
    hold_type: HoldType | None = None,
    active_children: dict[str, list[str]] | None = None,
) -> LifecycleState:
    """Validate and return the target state for a transition.

    Raises TransitionError if the transition is invalid.
    Raises PurgeBlockedError if purge is blocked.
    """
    current = entity.state

    # Terminal state — no transitions allowed
    if current in TERMINAL_STATES:
        raise TransitionError(
            f"Entity {entity.entity_id} is in terminal state '{current.value}' — "
            f"no transitions allowed.",
            code="TERMINAL_STATE",
        )

    # Check valid transition
    key = (current, action)
    if key not in VALID_TRANSITIONS:
        raise TransitionError(
            f"Invalid transition: {current.value} + {action.value}. "
            f"Not a valid state change.",
            code="INVALID_TRANSITION",
        )

    target_state = VALID_TRANSITIONS[key]

    # Special checks for APPROVE_PURGE
    if action == TransitionAction.APPROVE_PURGE:
        _validate_purge_approval(entity, active_children)

    # Special checks for PURGE
    if action == TransitionAction.PURGE:
        _validate_purge_execution(entity)

    # Reason required for trash and hold
    if action in (TransitionAction.TRASH, TransitionAction.PLACE_HOLD) and not reason:
        raise TransitionError(
            f"Reason required for {action.value} action.",
            code="REASON_REQUIRED",
        )

    # Hold type required for PLACE_HOLD
    if action == TransitionAction.PLACE_HOLD and hold_type is None:
        raise TransitionError(
            "Hold type required when placing a hold.",
            code="HOLD_TYPE_REQUIRED",
        )

    return target_state


def _validate_purge_approval(
    entity: EntityLifecycle,
    active_children: dict[str, list[str]] | None,
) -> None:
    """Validate that purge can be approved."""
    # Check retention policy
    if entity.retention_policy == "UNVERIFIED":
        raise PurgeBlockedError(
            f"Cannot approve purge for {entity.entity_id}: "
            f"retention policy is UNVERIFIED. Define policy before purging.",
            holds=[{"type": "unverified", "reason": "Retention policy not defined"}],
        )

    # Check active holds
    if entity.active_holds:
        raise PurgeBlockedError(
            f"Cannot approve purge for {entity.entity_id}: "
            f"{len(entity.active_holds)} active hold(s) exist.",
            holds=entity.active_holds,
        )

    # Check dependencies
    if active_children is not None:
        dep_check = check_dependencies(entity.entity_type, entity.entity_id, active_children)
        if dep_check.blocks_purge:
            raise PurgeBlockedError(
                f"Cannot approve purge for {entity.entity_id}: "
                f"active dependencies exist.",
                holds=[{"type": "dependency", "details": dep_check.blocking_dependencies}],
            )


def _validate_purge_execution(entity: EntityLifecycle) -> None:
    """Validate that purge can be executed (entity is in PURGE_PENDING)."""
    # Double-check holds haven't been added since approval
    if entity.active_holds:
        raise PurgeBlockedError(
            f"Cannot purge {entity.entity_id}: hold added after approval.",
            holds=entity.active_holds,
        )


# =============================================================================
# Apply Transition
# =============================================================================


def apply_transition(
    entity: EntityLifecycle,
    action: TransitionAction,
    *,
    actor_id: str,
    actor_role: str = "owner",
    reason: str = "",
    hold_type: HoldType | None = None,
    hold_expires_at: str | None = None,
    active_children: dict[str, list[str]] | None = None,
) -> TransitionRecord:
    """Apply a lifecycle transition to an entity.

    Returns the audit TransitionRecord.
    Raises TransitionError or PurgeBlockedError on invalid transitions.
    """
    target_state = validate_transition(
        entity, action,
        actor_id=actor_id,
        actor_role=actor_role,
        reason=reason,
        hold_type=hold_type,
        active_children=active_children,
    )

    prior_state = entity.state

    # Create audit record
    record = TransitionRecord(
        entity_type=entity.entity_type,
        entity_id=entity.entity_id,
        org_id=entity.org_id,
        prior_state=prior_state,
        new_state=target_state,
        action=action,
        actor_id=actor_id,
        actor_role=actor_role,
        reason=reason,
        hold_type=hold_type,
        hold_expires_at=hold_expires_at,
    )

    # Apply state change
    entity.state = target_state

    # Side effects
    if action == TransitionAction.TRASH:
        entity.trashed_at = datetime.now(UTC).isoformat()
        entity.trashed_by = actor_id
        entity.trash_reason = reason

    elif action == TransitionAction.RESTORE:
        entity.trashed_at = None
        entity.trashed_by = None
        entity.trash_reason = None

    elif action == TransitionAction.PLACE_HOLD:
        entity.active_holds.append({
            "hold_type": hold_type.value if hold_type else "unknown",
            "placed_by": actor_id,
            "placed_at": datetime.now(UTC).isoformat(),
            "reason": reason,
            "expires_at": hold_expires_at,
        })

    elif action == TransitionAction.RELEASE_HOLD:
        # Remove the most recent hold (in production: remove by hold_id)
        if entity.active_holds:
            entity.active_holds.pop()

    elif action == TransitionAction.PURGE:
        # Clear sensitive data references (storage cleanup is Story 070)
        pass

    # Record transition
    entity.transitions.append(record)

    return record


# =============================================================================
# Default Query Filter
# =============================================================================


def default_query_filter() -> set[str]:
    """Return the set of state values that default queries should include.

    Default reads EXCLUDE trashed, held, purge-pending, and purged records.
    """
    return {s.value for s in DEFAULT_VISIBLE_STATES}


def trash_query_filter() -> set[str]:
    """Return state values for authorized trash view."""
    return {LifecycleState.TRASHED.value}


def all_states_filter() -> set[str]:
    """Return all non-terminal states (admin view)."""
    return {s.value for s in LifecycleState if s != LifecycleState.PURGED}


# =============================================================================
# Idempotent Delete/Restore
# =============================================================================


def idempotent_trash(
    entity: EntityLifecycle,
    *,
    actor_id: str,
    reason: str,
) -> TransitionRecord | None:
    """Trash an entity idempotently — returns None if already trashed."""
    if entity.state == LifecycleState.TRASHED:
        return None  # Already trashed — idempotent
    if entity.state in TERMINAL_STATES:
        return None  # Already purged — cannot trash again

    return apply_transition(
        entity,
        TransitionAction.TRASH,
        actor_id=actor_id,
        reason=reason,
    )


def idempotent_restore(
    entity: EntityLifecycle,
    *,
    actor_id: str,
    reason: str = "User requested restoration",
) -> TransitionRecord | None:
    """Restore an entity idempotently — returns None if already active."""
    if entity.state == LifecycleState.ACTIVE:
        return None  # Already active

    if entity.state not in RESTORABLE_STATES:
        raise TransitionError(
            f"Cannot restore entity in state '{entity.state.value}'. "
            f"Restorable states: {[s.value for s in RESTORABLE_STATES]}",
            code="NOT_RESTORABLE",
        )

    return apply_transition(
        entity,
        TransitionAction.RESTORE,
        actor_id=actor_id,
        reason=reason,
    )


# =============================================================================
# Tenant Isolation Check
# =============================================================================


def verify_tenant_access(
    entity: EntityLifecycle,
    requesting_org_id: str,
) -> bool:
    """Verify the requesting org owns this entity.

    Returns True if access is allowed, False otherwise.
    NEVER allows cross-tenant access regardless of state.
    """
    return entity.org_id == requesting_org_id
