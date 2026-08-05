"""Durable Deletion Workflow — Story 070.

Coordinates purge of database records, B2 storage objects, and external provider
resources through one tracked, idempotent, receipt-backed workflow.

Design principles:
    1. Persist all targets BEFORE any side effects begin.
    2. Each cleanup step is idempotent — safe to retry on failure.
    3. Storage/provider deletion verifies outcome (receipt-backed).
    4. Partial failures remain visible and retryable until resolved.
    5. Database state never claims "purged" while storage is unverified.
    6. Audit tombstones and historical lineage are preserved (never deleted).
    7. Cross-tenant access fails without revealing target existence.

Workflow states:
    requested → eligible → targets_persisted → cleaning → reconciling → purged
                                                         ↘ failed (retryable)

Entity types supported:
    - talent (DB + B2 assets + model files)
    - asset (DB + B2 object)
    - job (DB + B2 outputs + GPU provider cleanup)
    - model (DB + B2 model file)
    - campaign (DB only, cascade-protected)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Workflow States
# =============================================================================


class PurgeState(str, Enum):
    """Durable deletion workflow states."""
    REQUESTED = "requested"          # User submitted deletion request
    ELIGIBLE = "eligible"            # Retention/hold checks passed
    TARGETS_PERSISTED = "targets_persisted"  # All cleanup targets recorded
    CLEANING = "cleaning"            # Active cleanup in progress
    RECONCILING = "reconciling"      # Verifying all targets removed
    PURGED = "purged"                # Final: all verified deleted
    FAILED = "failed"                # Retryable failure
    BLOCKED = "blocked"              # Legal hold or dependency prevents purge
    CANCELLED = "cancelled"          # Target restored before purge completed


class TargetType(str, Enum):
    """Types of cleanup targets."""
    DB_ROW = "db_row"               # Database record to tombstone/delete
    B2_OBJECT = "b2_object"         # Backblaze B2 storage object
    PROVIDER_RESOURCE = "provider_resource"  # External provider (Vast.ai instance, etc.)
    AUDIT_TOMBSTONE = "audit_tombstone"  # Preserved — never deleted


class TargetStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DELETED = "deleted"
    VERIFIED = "verified"           # Receipt confirms deletion
    FAILED = "failed"
    SKIPPED = "skipped"             # Preserved (audit) or already missing


class EntityType(str, Enum):
    TALENT = "talent"
    ASSET = "asset"
    JOB = "job"
    MODEL = "model"
    CAMPAIGN = "campaign"


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class CleanupTarget:
    """A single resource to be cleaned up during purge."""
    target_id: str = field(default_factory=lambda: f"tgt-{uuid.uuid4().hex[:10]}")
    target_type: TargetType = TargetType.DB_ROW
    resource_key: str = ""          # DB table+id, B2 key, provider instance
    status: TargetStatus = TargetStatus.PENDING
    receipt: str | None = None      # Provider deletion receipt/confirmation
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    completed_at: float | None = None

    @property
    def is_retryable(self) -> bool:
        return self.status == TargetStatus.FAILED and self.attempts < self.max_attempts

    @property
    def is_terminal(self) -> bool:
        return self.status in (TargetStatus.VERIFIED, TargetStatus.SKIPPED)


@dataclass
class PurgeRequest:
    """Durable deletion workflow instance."""
    purge_id: str = field(default_factory=lambda: f"prg-{uuid.uuid4().hex[:12]}")
    org_id: str = ""                # Tenant scope — mandatory
    actor_id: str = ""              # Who initiated the deletion
    entity_type: EntityType = EntityType.ASSET
    entity_id: str = ""             # Target entity UUID
    state: PurgeState = PurgeState.REQUESTED
    targets: list[CleanupTarget] = field(default_factory=list)

    # Eligibility
    retention_eligible: bool = False
    legal_hold: bool = False
    dependencies_clear: bool = False

    # Tracking
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    error: str | None = None

    # Audit preservation
    tombstone_preserved: bool = False

    @property
    def all_targets_terminal(self) -> bool:
        return all(t.is_terminal for t in self.targets)

    @property
    def has_failed_targets(self) -> bool:
        return any(t.status == TargetStatus.FAILED for t in self.targets)

    @property
    def has_retryable_targets(self) -> bool:
        return any(t.is_retryable for t in self.targets)


# =============================================================================
# In-Memory Store (production: Supabase table)
# =============================================================================

_purge_store: dict[str, PurgeRequest] = {}


# =============================================================================
# Workflow Engine
# =============================================================================


def request_purge(
    org_id: str,
    actor_id: str,
    entity_type: EntityType,
    entity_id: str,
) -> PurgeRequest:
    """Create a new purge request.

    Cross-tenant protection: org_id must match entity ownership.
    """
    if not org_id or not actor_id or not entity_id:
        raise ValueError("org_id, actor_id, and entity_id are required")

    # Check for duplicate (idempotent — return existing if same entity)
    existing = _find_active_purge(org_id, entity_type, entity_id)
    if existing:
        return existing

    request = PurgeRequest(
        org_id=org_id,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    _purge_store[request.purge_id] = request

    logger.info(f"PURGE_REQUESTED: id={request.purge_id} entity={entity_type.value}/{entity_id} org={org_id}")
    return request


def check_eligibility(purge_id: str) -> PurgeRequest:
    """Check retention eligibility and legal holds.

    Returns updated request with eligibility status.
    Blocked if: legal hold active, retention period not expired,
    or dependencies prevent deletion.
    """
    request = _get_request(purge_id)

    # Check legal hold
    if _has_legal_hold(request.org_id, request.entity_type, request.entity_id):
        request.state = PurgeState.BLOCKED
        request.legal_hold = True
        request.error = "Legal hold active — purge blocked"
        request.updated_at = time.time()
        _raise_alert(request, "legal_hold_blocked")
        return request

    # Check retention eligibility
    request.retention_eligible = _check_retention(request)
    if not request.retention_eligible:
        request.state = PurgeState.BLOCKED
        request.error = "Retention period not expired"
        request.updated_at = time.time()
        return request

    # Check dependencies
    request.dependencies_clear = _check_dependencies(request)
    if not request.dependencies_clear:
        request.state = PurgeState.BLOCKED
        request.error = "Active dependencies prevent deletion"
        request.updated_at = time.time()
        return request

    request.state = PurgeState.ELIGIBLE
    request.updated_at = time.time()
    return request


def persist_targets(purge_id: str) -> PurgeRequest:
    """Identify and persist all cleanup targets BEFORE any side effects.

    This is the critical safety step: all targets are recorded durably
    so partial failures can be retried without re-discovery.
    """
    request = _get_request(purge_id)
    if request.state != PurgeState.ELIGIBLE:
        raise InvalidStateError(f"Cannot persist targets in state {request.state.value}")

    targets = _discover_targets(request)
    request.targets = targets
    request.state = PurgeState.TARGETS_PERSISTED
    request.updated_at = time.time()

    logger.info(f"PURGE_TARGETS_PERSISTED: id={purge_id} count={len(targets)}")
    return request


def execute_cleanup(purge_id: str) -> PurgeRequest:
    """Execute cleanup for all persisted targets.

    Each step is idempotent. Already-deleted targets are marked as verified.
    Failures are recorded but don't stop other targets from being processed.
    """
    request = _get_request(purge_id)
    if request.state not in (PurgeState.TARGETS_PERSISTED, PurgeState.CLEANING, PurgeState.FAILED):
        raise InvalidStateError(f"Cannot execute cleanup in state {request.state.value}")

    request.state = PurgeState.CLEANING
    request.updated_at = time.time()

    for target in request.targets:
        if target.is_terminal:
            continue  # Already done

        _execute_target_cleanup(target)

    # Check if all targets are processed (deleted, verified, skipped, or permanently failed)
    all_processed = all(
        t.status in (TargetStatus.DELETED, TargetStatus.VERIFIED, TargetStatus.SKIPPED)
        for t in request.targets
    )
    has_unresolved_failures = any(
        t.status == TargetStatus.FAILED for t in request.targets
    )

    if all_processed and not has_unresolved_failures:
        request.state = PurgeState.RECONCILING
    elif has_unresolved_failures and not request.has_retryable_targets:
        request.state = PurgeState.FAILED
        request.error = "One or more targets failed after max retries"
        _raise_alert(request, "purge_partial_failure")
    elif has_unresolved_failures:
        request.state = PurgeState.FAILED
        request.error = "One or more targets failed — retryable"

    request.updated_at = time.time()
    return request


def reconcile(purge_id: str) -> PurgeRequest:
    """Final reconciliation — verify all targets are actually gone.

    Only transitions to PURGED if every target is verified or skipped.
    """
    request = _get_request(purge_id)
    if request.state != PurgeState.RECONCILING:
        raise InvalidStateError(f"Cannot reconcile in state {request.state.value}")

    all_verified = True
    for target in request.targets:
        if target.target_type == TargetType.AUDIT_TOMBSTONE:
            target.status = TargetStatus.SKIPPED
            continue

        if target.status == TargetStatus.DELETED:
            # Verify the deletion actually happened
            verified = _verify_deletion(target)
            if verified:
                target.status = TargetStatus.VERIFIED
                target.receipt = f"verified-{int(time.time())}"
            else:
                target.status = TargetStatus.FAILED
                target.last_error = "Verification failed — resource still exists"
                all_verified = False

    if all_verified and request.all_targets_terminal:
        request.state = PurgeState.PURGED
        request.completed_at = time.time()
        request.tombstone_preserved = True
        logger.info(f"PURGE_COMPLETE: id={purge_id} entity={request.entity_type.value}/{request.entity_id}")
    else:
        request.state = PurgeState.FAILED
        request.error = "Reconciliation found unverified deletions"
        _raise_alert(request, "reconciliation_failed")

    request.updated_at = time.time()
    return request


def retry_failed(purge_id: str) -> PurgeRequest:
    """Retry failed targets that haven't exceeded max attempts."""
    request = _get_request(purge_id)
    if request.state != PurgeState.FAILED:
        raise InvalidStateError(f"Cannot retry in state {request.state.value}")

    # Reset retryable targets
    for target in request.targets:
        if target.is_retryable:
            target.status = TargetStatus.PENDING

    request.state = PurgeState.CLEANING
    request.error = None
    request.updated_at = time.time()

    return execute_cleanup(purge_id)


def cancel_purge(purge_id: str, reason: str = "target restored") -> PurgeRequest:
    """Cancel a purge (e.g. target was restored before cleanup started)."""
    request = _get_request(purge_id)
    if request.state in (PurgeState.PURGED, PurgeState.CANCELLED):
        return request  # Already terminal

    if request.state == PurgeState.CLEANING:
        raise InvalidStateError("Cannot cancel during active cleanup — wait for completion")

    request.state = PurgeState.CANCELLED
    request.error = reason
    request.updated_at = time.time()

    logger.info(f"PURGE_CANCELLED: id={purge_id} reason={reason}")
    return request


# =============================================================================
# Cross-Tenant Protection
# =============================================================================


def get_purge_request(purge_id: str, org_id: str) -> PurgeRequest | None:
    """Get a purge request with tenant validation.

    Returns None (not 404 details) for cross-tenant attempts.
    """
    request = _purge_store.get(purge_id)
    if not request or request.org_id != org_id:
        return None  # Don't reveal existence
    return request


def list_purge_requests(org_id: str) -> list[PurgeRequest]:
    """List purge requests for an organization."""
    return [r for r in _purge_store.values() if r.org_id == org_id]


# =============================================================================
# Target Discovery
# =============================================================================


def _discover_targets(request: PurgeRequest) -> list[CleanupTarget]:
    """Discover all cleanup targets for an entity.

    This maps entity types to their storage footprint:
    - talent: DB record + all associated assets + model files
    - asset: DB record + B2 object
    - job: DB record + output assets + GPU instance (if active)
    - model: DB record + B2 model file
    - campaign: DB record only (assets preserved)
    """
    targets: list[CleanupTarget] = []

    # Always add DB tombstone (the main record)
    targets.append(CleanupTarget(
        target_type=TargetType.DB_ROW,
        resource_key=f"{request.entity_type.value}/{request.entity_id}",
    ))

    # Add storage targets based on entity type
    if request.entity_type == EntityType.ASSET:
        targets.append(CleanupTarget(
            target_type=TargetType.B2_OBJECT,
            resource_key=f"{request.org_id}/assets/{request.entity_id}",
        ))

    elif request.entity_type == EntityType.MODEL:
        targets.append(CleanupTarget(
            target_type=TargetType.B2_OBJECT,
            resource_key=f"{request.org_id}/models/{request.entity_id}",
        ))

    elif request.entity_type == EntityType.TALENT:
        # Talent has associated assets and models
        targets.append(CleanupTarget(
            target_type=TargetType.B2_OBJECT,
            resource_key=f"{request.org_id}/images/{request.entity_id}/*",
        ))
        targets.append(CleanupTarget(
            target_type=TargetType.B2_OBJECT,
            resource_key=f"{request.org_id}/models/{request.entity_id}/*",
        ))

    elif request.entity_type == EntityType.JOB:
        targets.append(CleanupTarget(
            target_type=TargetType.B2_OBJECT,
            resource_key=f"{request.org_id}/outputs/{request.entity_id}/*",
        ))
        targets.append(CleanupTarget(
            target_type=TargetType.PROVIDER_RESOURCE,
            resource_key=f"gpu-instance/{request.entity_id}",
        ))

    # Always preserve audit tombstone
    targets.append(CleanupTarget(
        target_type=TargetType.AUDIT_TOMBSTONE,
        resource_key=f"audit/{request.entity_type.value}/{request.entity_id}",
        status=TargetStatus.SKIPPED,  # Never deleted
    ))

    return targets


# =============================================================================
# Target Cleanup Execution
# =============================================================================


def _execute_target_cleanup(target: CleanupTarget) -> None:
    """Execute cleanup for a single target (idempotent)."""
    target.attempts += 1
    target.status = TargetStatus.IN_PROGRESS

    try:
        if target.target_type == TargetType.AUDIT_TOMBSTONE:
            # Never delete audit records
            target.status = TargetStatus.SKIPPED
            return

        if target.target_type == TargetType.DB_ROW:
            _delete_db_record(target)
        elif target.target_type == TargetType.B2_OBJECT:
            _delete_b2_object(target)
        elif target.target_type == TargetType.PROVIDER_RESOURCE:
            _delete_provider_resource(target)

        target.status = TargetStatus.DELETED
        target.completed_at = time.time()

    except ResourceAlreadyDeletedError:
        # Idempotent: already gone is success
        target.status = TargetStatus.VERIFIED
        target.receipt = "already_deleted"
        target.completed_at = time.time()

    except Exception as e:
        target.status = TargetStatus.FAILED
        target.last_error = str(e)[:200]
        logger.warning(f"TARGET_CLEANUP_FAILED: {target.target_id} attempt={target.attempts} error={e}")


# =============================================================================
# Simulated Backend Operations (production: real B2/DB/provider calls)
# =============================================================================

# Injection points for testing
_simulate_b2_failure: bool = False
_simulate_provider_timeout: bool = False
_simulate_already_deleted: bool = False
_simulate_legal_hold: bool = False
_simulate_dependency: bool = False


def _delete_db_record(target: CleanupTarget) -> None:
    """Mark DB record as deleted (soft delete → hard delete)."""
    if _simulate_already_deleted:
        raise ResourceAlreadyDeletedError(target.resource_key)
    # In production: UPDATE ... SET deleted_at = now() WHERE id = ...


def _delete_b2_object(target: CleanupTarget) -> None:
    """Delete object from Backblaze B2."""
    if _simulate_already_deleted:
        raise ResourceAlreadyDeletedError(target.resource_key)
    if _simulate_b2_failure:
        raise StorageCleanupError(f"B2 deletion failed for {target.resource_key}")
    # In production: b2_client.delete_file_version(...)
    target.receipt = f"b2-del-{uuid.uuid4().hex[:8]}"


def _delete_provider_resource(target: CleanupTarget) -> None:
    """Terminate/cleanup external provider resource."""
    if _simulate_provider_timeout:
        raise ProviderCleanupError(f"Provider timeout for {target.resource_key}")
    # In production: vast_client.destroy_instance(...)
    target.receipt = f"provider-del-{uuid.uuid4().hex[:8]}"


def _verify_deletion(target: CleanupTarget) -> bool:
    """Verify a target is actually deleted (check storage/provider)."""
    # In production: HEAD request to B2, status check on provider
    return True


# =============================================================================
# Eligibility & Dependency Checks
# =============================================================================


def _has_legal_hold(org_id: str, entity_type: EntityType, entity_id: str) -> bool:
    """Check if entity is under legal hold."""
    return _simulate_legal_hold


def _check_retention(request: PurgeRequest) -> bool:
    """Check if entity has passed its retention period."""
    # In production: compare deleted_at + retention_days vs now()
    # For now, all soft-deleted items are eligible
    return True


def _check_dependencies(request: PurgeRequest) -> bool:
    """Check if entity has active dependencies preventing deletion."""
    if _simulate_dependency:
        return False
    # In production: check FK references, active jobs, shared assets
    return True


# =============================================================================
# Alerting
# =============================================================================

_alerts: list[dict] = []


def _raise_alert(request: PurgeRequest, alert_type: str) -> None:
    """Raise operational alert for purge issues."""
    alert = {
        "id": f"del-alert-{uuid.uuid4().hex[:8]}",
        "type": alert_type,
        "purge_id": request.purge_id,
        "entity": f"{request.entity_type.value}/{request.entity_id}",
        "org_id": request.org_id,
        "raised_at": datetime.now(UTC).isoformat(),
        "resolved": False,
    }
    _alerts.append(alert)
    logger.warning(f"DELETION_ALERT: {alert_type} purge={request.purge_id}")


def get_deletion_alerts(org_id: str | None = None) -> list[dict]:
    """Get active deletion alerts, optionally filtered by org."""
    alerts = [a for a in _alerts if not a["resolved"]]
    if org_id:
        alerts = [a for a in alerts if a["org_id"] == org_id]
    return alerts


# =============================================================================
# Helpers
# =============================================================================


def _get_request(purge_id: str) -> PurgeRequest:
    request = _purge_store.get(purge_id)
    if not request:
        raise PurgeNotFoundError(f"Purge request {purge_id} not found")
    return request


def _find_active_purge(org_id: str, entity_type: EntityType, entity_id: str) -> PurgeRequest | None:
    """Find an active (non-terminal) purge for the same entity."""
    terminal = {PurgeState.PURGED, PurgeState.CANCELLED}
    for r in _purge_store.values():
        if (r.org_id == org_id and r.entity_type == entity_type
                and r.entity_id == entity_id and r.state not in terminal):
            return r
    return None


# =============================================================================
# Full Workflow (convenience)
# =============================================================================


def execute_full_purge(
    org_id: str,
    actor_id: str,
    entity_type: EntityType,
    entity_id: str,
) -> PurgeRequest:
    """Execute the complete purge workflow in one call.

    Steps: request → eligibility → persist targets → cleanup → reconcile.
    """
    request = request_purge(org_id, actor_id, entity_type, entity_id)
    request = check_eligibility(request.purge_id)

    if request.state == PurgeState.BLOCKED:
        return request

    request = persist_targets(request.purge_id)
    request = execute_cleanup(request.purge_id)

    if request.state == PurgeState.RECONCILING:
        request = reconcile(request.purge_id)

    return request


# =============================================================================
# Exceptions
# =============================================================================


class PurgeError(Exception):
    """Base deletion workflow error."""


class PurgeNotFoundError(PurgeError):
    """Purge request not found."""


class InvalidStateError(PurgeError):
    """Invalid state transition."""


class StorageCleanupError(PurgeError):
    """B2 storage cleanup failed."""


class ProviderCleanupError(PurgeError):
    """External provider cleanup failed."""


class ResourceAlreadyDeletedError(PurgeError):
    """Resource was already deleted (idempotent success)."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    """Reset all state for testing."""
    global _simulate_b2_failure, _simulate_provider_timeout
    global _simulate_already_deleted, _simulate_legal_hold, _simulate_dependency
    _purge_store.clear()
    _alerts.clear()
    _simulate_b2_failure = False
    _simulate_provider_timeout = False
    _simulate_already_deleted = False
    _simulate_legal_hold = False
    _simulate_dependency = False


def _inject_failure(failure_type: str, enabled: bool = True) -> None:
    """Inject failures for testing."""
    global _simulate_b2_failure, _simulate_provider_timeout
    global _simulate_already_deleted, _simulate_legal_hold, _simulate_dependency

    if failure_type == "b2":
        _simulate_b2_failure = enabled
    elif failure_type == "provider":
        _simulate_provider_timeout = enabled
    elif failure_type == "already_deleted":
        _simulate_already_deleted = enabled
    elif failure_type == "legal_hold":
        _simulate_legal_hold = enabled
    elif failure_type == "dependency":
        _simulate_dependency = enabled
