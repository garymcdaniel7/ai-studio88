"""Creator OS Durable Persistence — Story 121.

Tenant-scoped, version-aware records for campaigns, content items, calendar
entries, brands, teams, and notifications. Replaces process-local collections
with durable records that survive restarts.

Every record has:
    - org_id (mandatory tenant scope)
    - created_by / updated_by (actor attribution)
    - version (optimistic concurrency control)
    - lifecycle_state (active/archived/trashed per Story 069)
    - created_at / updated_at (audit timestamps)

Mutations:
    - Version-aware: stale writes rejected with VersionConflictError
    - Recoverable deletion: trashed (not hard-deleted)
    - Pagination: limit/offset with total count
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Record Types
# =============================================================================


class RecordType(StrEnum):
    CAMPAIGN = "campaign"
    CONTENT_ITEM = "content_item"
    CALENDAR_ENTRY = "calendar_entry"
    BRAND = "brand"
    TEAM_MEMBER = "team_member"
    NOTIFICATION = "notification"


class LifecycleState(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    TRASHED = "trashed"


# =============================================================================
# Base Record
# =============================================================================


@dataclass
class CreatorOSRecord:
    """Base record with mandatory tenant scope, versioning, and lifecycle."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    record_type: RecordType = RecordType.CAMPAIGN
    org_id: str = ""
    created_by: str = ""
    updated_by: str = ""
    version: int = 1
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    # Flexible data payload
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "record_type": self.record_type.value,
            "org_id": self.org_id,
            "version": self.version,
            "lifecycle_state": self.lifecycle_state.value,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "data": self.data,
        }


# =============================================================================
# Errors
# =============================================================================


class VersionConflictError(Exception):
    """Raised when a stale write is attempted (optimistic concurrency)."""

    def __init__(self, record_id: str, expected: int, actual: int):
        self.record_id = record_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Version conflict on {record_id}: expected {expected}, actual {actual}"
        )


class TenantAccessError(Exception):
    """Raised on cross-tenant access attempt."""

    def __init__(self, message: str = "Cross-tenant access denied"):
        self.message = message
        super().__init__(message)


class RecordNotFoundError(Exception):
    def __init__(self, record_id: str):
        super().__init__(f"Record {record_id} not found")


# =============================================================================
# Store (in-memory for contract; production uses Supabase)
# =============================================================================

_store: dict[str, CreatorOSRecord] = {}


def clear_store() -> None:
    _store.clear()


# =============================================================================
# CRUD Operations (all tenant-scoped)
# =============================================================================


def create_record(
    *,
    record_type: RecordType,
    org_id: str,
    created_by: str,
    data: dict,
) -> CreatorOSRecord:
    """Create a new tenant-scoped record."""
    if not org_id:
        raise TenantAccessError("org_id is required")
    if not created_by:
        raise TenantAccessError("created_by (actor) is required")

    record = CreatorOSRecord(
        record_type=record_type,
        org_id=org_id,
        created_by=created_by,
        updated_by=created_by,
        data=data,
    )
    _store[record.id] = record
    return record


def get_record(record_id: str, *, org_id: str) -> CreatorOSRecord:
    """Get a record by ID (tenant-scoped).

    Raises RecordNotFoundError or TenantAccessError.
    """
    record = _store.get(record_id)
    if record is None:
        raise RecordNotFoundError(record_id)
    if record.org_id != org_id:
        raise TenantAccessError()
    return record


def update_record(
    record_id: str,
    *,
    org_id: str,
    updated_by: str,
    expected_version: int,
    data: dict,
) -> CreatorOSRecord:
    """Update a record with optimistic concurrency control.

    Raises VersionConflictError if expected_version doesn't match.
    Raises TenantAccessError if org doesn't match.
    """
    record = get_record(record_id, org_id=org_id)

    if record.version != expected_version:
        raise VersionConflictError(record_id, expected_version, record.version)

    if record.lifecycle_state == LifecycleState.TRASHED:
        raise RecordNotFoundError(record_id)  # Cannot update trashed records

    record.data = data
    record.updated_by = updated_by
    record.version += 1
    record.updated_at = datetime.now(UTC).isoformat()
    return record


def trash_record(record_id: str, *, org_id: str, actor: str) -> CreatorOSRecord:
    """Move a record to trashed state (recoverable deletion).

    Idempotent: trashing already-trashed record returns it unchanged.
    """
    record = get_record(record_id, org_id=org_id)

    if record.lifecycle_state == LifecycleState.TRASHED:
        return record  # Idempotent

    record.lifecycle_state = LifecycleState.TRASHED
    record.updated_by = actor
    record.version += 1
    record.updated_at = datetime.now(UTC).isoformat()
    return record


def restore_record(record_id: str, *, org_id: str, actor: str) -> CreatorOSRecord:
    """Restore a trashed record to active state."""
    record = get_record(record_id, org_id=org_id)

    if record.lifecycle_state != LifecycleState.TRASHED:
        return record  # Already active/archived

    record.lifecycle_state = LifecycleState.ACTIVE
    record.updated_by = actor
    record.version += 1
    record.updated_at = datetime.now(UTC).isoformat()
    return record


def archive_record(record_id: str, *, org_id: str, actor: str) -> CreatorOSRecord:
    """Archive a record (soft-hide, still queryable)."""
    record = get_record(record_id, org_id=org_id)

    if record.lifecycle_state == LifecycleState.TRASHED:
        raise RecordNotFoundError(record_id)

    record.lifecycle_state = LifecycleState.ARCHIVED
    record.updated_by = actor
    record.version += 1
    record.updated_at = datetime.now(UTC).isoformat()
    return record


# =============================================================================
# List / Pagination (tenant-scoped)
# =============================================================================


@dataclass
class PaginatedResult:
    """Paginated query result."""

    items: list[CreatorOSRecord]
    total: int
    limit: int
    offset: int

    def to_dict(self) -> dict:
        return {
            "items": [r.to_dict() for r in self.items],
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
        }


def list_records(
    *,
    org_id: str,
    record_type: RecordType | None = None,
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE,
    limit: int = 20,
    offset: int = 0,
) -> PaginatedResult:
    """List records with tenant scoping and pagination.

    Default: only ACTIVE records returned (trashed excluded).
    """
    if not org_id:
        raise TenantAccessError("org_id required for listing")

    # Filter
    filtered = [
        r for r in _store.values()
        if r.org_id == org_id
        and r.lifecycle_state == lifecycle_state
        and (record_type is None or r.record_type == record_type)
    ]

    # Sort by created_at descending
    filtered.sort(key=lambda r: r.created_at, reverse=True)

    total = len(filtered)
    page = filtered[offset:offset + limit]

    return PaginatedResult(items=page, total=total, limit=limit, offset=offset)


def count_records(
    *,
    org_id: str,
    record_type: RecordType | None = None,
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE,
) -> int:
    """Count records (tenant-scoped)."""
    return len([
        r for r in _store.values()
        if r.org_id == org_id
        and r.lifecycle_state == lifecycle_state
        and (record_type is None or r.record_type == record_type)
    ])


# =============================================================================
# Search
# =============================================================================


def search_records(
    *,
    org_id: str,
    query: str,
    record_type: RecordType | None = None,
    limit: int = 20,
) -> list[CreatorOSRecord]:
    """Simple text search across record data (tenant-scoped).

    Searches data values for the query string.
    """
    if not org_id:
        raise TenantAccessError("org_id required for search")

    query_lower = query.lower()
    results: list[CreatorOSRecord] = []

    for record in _store.values():
        if record.org_id != org_id:
            continue
        if record.lifecycle_state == LifecycleState.TRASHED:
            continue
        if record_type and record.record_type != record_type:
            continue

        # Search in data values
        data_str = " ".join(str(v) for v in record.data.values()).lower()
        if query_lower in data_str:
            results.append(record)

        if len(results) >= limit:
            break

    return results
