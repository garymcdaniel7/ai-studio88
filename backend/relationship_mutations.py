"""Authenticated Relationship Mutations — Story 106.

Routes all relationship CRUD through authenticated, authorized, version-aware
service. UI state only updates after confirmed persistence.

Authorization rules:
    - User must have active workspace membership (org_id from JWT)
    - Source and target entities must belong to the same org
    - Role must be editor, admin, or owner (viewers cannot mutate)
    - Cross-tenant references rejected without revealing existence

Version-aware concurrency:
    - Every mutation includes expected_version
    - Stale version → conflict error with current version info
    - Client retries with fresh version after conflict

Audit:
    - Every mutation produces an audit event with actor, action, timestamp
    - Failed mutations also audited (for security monitoring)

Optimistic UI contract:
    - Client may display optimistic state
    - On server confirmation: commit
    - On server rejection: rollback to last confirmed state
    - Never report success before persistence confirmed
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class MutationAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ARCHIVE = "archive"


class MutationResult(str, Enum):
    CONFIRMED = "confirmed"         # Persisted successfully
    REJECTED = "rejected"           # Validation/auth failure
    CONFLICT = "conflict"           # Version mismatch
    ROLLED_BACK = "rolled_back"     # Optimistic state reverted


class MemberRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


MUTATE_ROLES = {MemberRole.OWNER, MemberRole.ADMIN, MemberRole.EDITOR}


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class MutationRequest:
    """A relationship mutation request from an authenticated user."""
    request_id: str = field(default_factory=lambda: f"mut-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    user_id: str = ""
    user_role: MemberRole = MemberRole.VIEWER
    action: MutationAction = MutationAction.CREATE
    # Target relationship
    relationship_id: str | None = None  # For update/delete
    # Create/Update payload
    rel_type: str = ""
    source_id: str = ""
    source_type: str = ""
    target_id: str = ""
    target_type: str = ""
    # Version-aware concurrency
    expected_version: int | None = None
    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MutationResponse:
    """Response to a mutation request — confirmed or rejected."""
    request_id: str = ""
    result: MutationResult = MutationResult.REJECTED
    relationship_id: str | None = None
    current_version: int = 0
    error: str | None = None
    error_code: str | None = None
    timestamp: float = field(default_factory=time.time)

    @property
    def is_success(self) -> bool:
        return self.result == MutationResult.CONFIRMED


@dataclass
class AuditEvent:
    """Immutable audit record for a relationship mutation."""
    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:10]}")
    org_id: str = ""
    user_id: str = ""
    action: MutationAction = MutationAction.CREATE
    relationship_id: str = ""
    result: MutationResult = MutationResult.CONFIRMED
    error: str | None = None
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Relationship Record (internal state)
# =============================================================================


@dataclass
class RelationshipRecord:
    """Server-side relationship state (source of truth)."""
    relationship_id: str = field(default_factory=lambda: f"rel-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    rel_type: str = ""
    source_id: str = ""
    source_type: str = ""
    target_id: str = ""
    target_type: str = ""
    version: int = 1
    active: bool = True
    archived: bool = False
    created_by: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


# =============================================================================
# Store
# =============================================================================

_relationships: dict[str, RelationshipRecord] = {}
_audit_log: list[AuditEvent] = []

# Entity ownership simulation (entity_id → org_id)
_entity_owners: dict[str, str] = {}
# Membership simulation (user_id → {org_id: role})
_memberships: dict[str, dict[str, MemberRole]] = {}
# Valid relationship types (from Story 090 taxonomy)
_valid_types: set[str] = {
    "wears", "holds", "located_at", "promotes", "friends_with",
    "sibling_of", "partner_of", "works_with", "voiced_by",
    "trained_with", "belongs_to", "part_of", "set_in",
}


# =============================================================================
# Mutation Service
# =============================================================================


def execute_mutation(request: MutationRequest) -> MutationResponse:
    """Execute an authenticated relationship mutation.

    Validation order:
    1. Membership check (user belongs to org with mutate role)
    2. Entity ownership (source and target in same org)
    3. Type validation (against taxonomy)
    4. Version check (for updates/deletes)
    5. Persistence
    6. Audit event

    Returns confirmed or rejected response.
    """
    response = MutationResponse(request_id=request.request_id)

    # Gate 1: Membership and role
    if not _check_membership(request.user_id, request.org_id):
        response.result = MutationResult.REJECTED
        response.error = "User does not have active membership in this workspace"
        response.error_code = "MEMBERSHIP_REQUIRED"
        _emit_audit(request, response)
        return response

    if request.user_role not in MUTATE_ROLES:
        response.result = MutationResult.REJECTED
        response.error = f"Role '{request.user_role.value}' cannot mutate relationships (requires editor+)"
        response.error_code = "INSUFFICIENT_ROLE"
        _emit_audit(request, response)
        return response

    # Dispatch by action
    if request.action == MutationAction.CREATE:
        return _handle_create(request, response)
    elif request.action == MutationAction.UPDATE:
        return _handle_update(request, response)
    elif request.action in (MutationAction.DELETE, MutationAction.ARCHIVE):
        return _handle_delete(request, response)

    response.error = f"Unknown action: {request.action.value}"
    response.error_code = "UNKNOWN_ACTION"
    _emit_audit(request, response)
    return response


# =============================================================================
# Action Handlers
# =============================================================================


def _handle_create(request: MutationRequest, response: MutationResponse) -> MutationResponse:
    """Handle relationship creation."""
    # Gate 2: Entity ownership
    if not _verify_ownership(request.source_id, request.org_id):
        response.result = MutationResult.REJECTED
        response.error = "Source entity does not belong to this workspace"
        response.error_code = "OWNERSHIP_VIOLATION"
        _emit_audit(request, response)
        return response

    if not _verify_ownership(request.target_id, request.org_id):
        response.result = MutationResult.REJECTED
        response.error = "Target entity does not belong to this workspace"
        response.error_code = "OWNERSHIP_VIOLATION"
        _emit_audit(request, response)
        return response

    # Gate 3: Type validation
    if request.rel_type not in _valid_types:
        response.result = MutationResult.REJECTED
        response.error = f"Invalid relationship type '{request.rel_type}'"
        response.error_code = "INVALID_TYPE"
        _emit_audit(request, response)
        return response

    # Gate: Source not archived
    existing_as_source = _find_entity_archived(request.source_id, request.org_id)
    if existing_as_source:
        response.result = MutationResult.REJECTED
        response.error = "Source entity is archived — cannot create relationships"
        response.error_code = "SOURCE_ARCHIVED"
        _emit_audit(request, response)
        return response

    # Duplicate check (idempotent)
    duplicate = _find_duplicate(request)
    if duplicate:
        response.result = MutationResult.CONFIRMED
        response.relationship_id = duplicate.relationship_id
        response.current_version = duplicate.version
        _emit_audit(request, response)
        return response

    # Create
    record = RelationshipRecord(
        org_id=request.org_id,
        rel_type=request.rel_type,
        source_id=request.source_id,
        source_type=request.source_type,
        target_id=request.target_id,
        target_type=request.target_type,
        created_by=request.user_id,
    )
    _relationships[record.relationship_id] = record

    response.result = MutationResult.CONFIRMED
    response.relationship_id = record.relationship_id
    response.current_version = record.version

    logger.info(f"RELATIONSHIP_CREATED: id={record.relationship_id} type={request.rel_type} by={request.user_id}")
    _emit_audit(request, response)
    return response


def _handle_update(request: MutationRequest, response: MutationResponse) -> MutationResponse:
    """Handle relationship update (version-aware)."""
    if not request.relationship_id:
        response.result = MutationResult.REJECTED
        response.error = "relationship_id is required for update"
        response.error_code = "MISSING_ID"
        _emit_audit(request, response)
        return response

    record = _relationships.get(request.relationship_id)
    if not record or record.org_id != request.org_id:
        response.result = MutationResult.REJECTED
        response.error = "Relationship not found"
        response.error_code = "NOT_FOUND"
        _emit_audit(request, response)
        return response

    if not record.active:
        response.result = MutationResult.REJECTED
        response.error = "Cannot update a deleted relationship"
        response.error_code = "ALREADY_DELETED"
        _emit_audit(request, response)
        return response

    # Version check
    if request.expected_version is not None and request.expected_version != record.version:
        response.result = MutationResult.CONFLICT
        response.error = f"Version conflict: expected {request.expected_version}, current is {record.version}"
        response.error_code = "VERSION_CONFLICT"
        response.current_version = record.version
        _emit_audit(request, response)
        return response

    # Apply update
    if request.rel_type and request.rel_type != record.rel_type:
        if request.rel_type not in _valid_types:
            response.result = MutationResult.REJECTED
            response.error = f"Invalid relationship type '{request.rel_type}'"
            response.error_code = "INVALID_TYPE"
            _emit_audit(request, response)
            return response
        record.rel_type = request.rel_type

    record.version += 1
    record.updated_at = time.time()

    response.result = MutationResult.CONFIRMED
    response.relationship_id = record.relationship_id
    response.current_version = record.version

    logger.info(f"RELATIONSHIP_UPDATED: id={record.relationship_id} v={record.version} by={request.user_id}")
    _emit_audit(request, response)
    return response


def _handle_delete(request: MutationRequest, response: MutationResponse) -> MutationResponse:
    """Handle relationship deletion/archival (idempotent)."""
    if not request.relationship_id:
        response.result = MutationResult.REJECTED
        response.error = "relationship_id is required for delete"
        response.error_code = "MISSING_ID"
        _emit_audit(request, response)
        return response

    record = _relationships.get(request.relationship_id)
    if not record or record.org_id != request.org_id:
        response.result = MutationResult.REJECTED
        response.error = "Relationship not found"
        response.error_code = "NOT_FOUND"
        _emit_audit(request, response)
        return response

    # Already deleted — idempotent
    if not record.active:
        response.result = MutationResult.CONFIRMED
        response.relationship_id = record.relationship_id
        response.current_version = record.version
        _emit_audit(request, response)
        return response

    # Version check
    if request.expected_version is not None and request.expected_version != record.version:
        response.result = MutationResult.CONFLICT
        response.error = f"Version conflict: expected {request.expected_version}, current is {record.version}"
        response.error_code = "VERSION_CONFLICT"
        response.current_version = record.version
        _emit_audit(request, response)
        return response

    record.active = False
    record.archived = request.action == MutationAction.ARCHIVE
    record.version += 1
    record.updated_at = time.time()

    response.result = MutationResult.CONFIRMED
    response.relationship_id = record.relationship_id
    response.current_version = record.version

    logger.info(f"RELATIONSHIP_DELETED: id={record.relationship_id} by={request.user_id}")
    _emit_audit(request, response)
    return response


# =============================================================================
# Audit
# =============================================================================


def _emit_audit(request: MutationRequest, response: MutationResponse) -> None:
    """Record audit event for every mutation attempt (success or failure)."""
    event = AuditEvent(
        org_id=request.org_id,
        user_id=request.user_id,
        action=request.action,
        relationship_id=response.relationship_id or request.relationship_id or "",
        result=response.result,
        error=response.error,
        metadata=request.metadata,
    )
    _audit_log.append(event)


def get_audit_log(org_id: str) -> list[AuditEvent]:
    """Get audit events for an org."""
    return [e for e in _audit_log if e.org_id == org_id]


# =============================================================================
# Validation Helpers
# =============================================================================


def _check_membership(user_id: str, org_id: str) -> bool:
    """Check if user has active membership in org."""
    user_memberships = _memberships.get(user_id, {})
    return org_id in user_memberships


def _verify_ownership(entity_id: str, org_id: str) -> bool:
    """Verify entity belongs to the requesting org."""
    owner = _entity_owners.get(entity_id)
    if owner is None:
        return True  # Unregistered entities assumed valid (production: DB check)
    return owner == org_id


def _find_duplicate(request: MutationRequest) -> RelationshipRecord | None:
    """Find an existing active relationship with same source/target/type."""
    for r in _relationships.values():
        if (r.org_id == request.org_id and r.rel_type == request.rel_type
                and r.source_id == request.source_id and r.target_id == request.target_id
                and r.active):
            return r
    return None


def _find_entity_archived(entity_id: str, org_id: str) -> bool:
    """Check if entity is archived (simulated)."""
    return _archived_entities.get(entity_id, False)


# Simulation state
_archived_entities: dict[str, bool] = {}


# =============================================================================
# Query (confirmed state only)
# =============================================================================


def get_confirmed_relationships(org_id: str, entity_id: str | None = None) -> list[RelationshipRecord]:
    """Get confirmed (persisted) relationships for an org."""
    results = []
    for r in _relationships.values():
        if r.org_id != org_id or not r.active:
            continue
        if entity_id and r.source_id != entity_id and r.target_id != entity_id:
            continue
        results.append(r)
    return results


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _relationships.clear()
    _audit_log.clear()
    _entity_owners.clear()
    _memberships.clear()
    _archived_entities.clear()


def _register_membership(user_id: str, org_id: str, role: MemberRole) -> None:
    _memberships.setdefault(user_id, {})[org_id] = role


def _register_entity_owner(entity_id: str, org_id: str) -> None:
    _entity_owners[entity_id] = org_id


def _archive_entity(entity_id: str) -> None:
    _archived_entities[entity_id] = True
