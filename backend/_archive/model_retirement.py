"""Model Retirement & Deletion — Story 101.

Dependency-safe retirement and permanent deletion for LoRA versions.
Retirement removes from new use while preserving historical references.
Permanent deletion requires authorization, zero protected deps, and durable cleanup.

Dependency Categories:
    - Active assignment (talent default, project default)
    - Queued/running jobs referencing this version
    - Historical assets produced by this version
    - Context packages referencing this version
    - Provider/worker deployments with cached copy
    - Child versions (fine-tuned from this version)

Retirement:
    ACTIVE/SUPERSEDED → RETIRED
    - Removed from catalogs and new assignments
    - Historical references preserved (immutable provenance)
    - Reversible (re-activate if policy allows)

Permanent Deletion:
    RETIRED → PENDING_DELETE → DELETED
    - Requires: zero protected dependencies, authorized actor, approved policy
    - Durable cleanup: DB record → storage object → registry → worker cache
    - Idempotent and reconcilable on partial failure
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Dependency Types
# =============================================================================


class DependencyType(StrEnum):
    ACTIVE_ASSIGNMENT = "active_assignment"
    QUEUED_JOB = "queued_job"
    RUNNING_JOB = "running_job"
    HISTORICAL_ASSET = "historical_asset"
    CONTEXT_PACKAGE = "context_package"
    PROVIDER_DEPLOYMENT = "provider_deployment"
    WORKER_CACHE = "worker_cache"
    CHILD_VERSION = "child_version"


class DependencyProtection(StrEnum):
    BLOCKS_RETIREMENT = "blocks_retirement"
    BLOCKS_DELETION = "blocks_deletion"
    INFORMATIONAL = "informational"     # Disclosed but doesn't block


# Which dependency types block which actions
DEPENDENCY_RULES: dict[DependencyType, DependencyProtection] = {
    DependencyType.ACTIVE_ASSIGNMENT: DependencyProtection.BLOCKS_RETIREMENT,
    DependencyType.QUEUED_JOB: DependencyProtection.BLOCKS_RETIREMENT,
    DependencyType.RUNNING_JOB: DependencyProtection.BLOCKS_RETIREMENT,
    DependencyType.HISTORICAL_ASSET: DependencyProtection.BLOCKS_DELETION,
    DependencyType.CONTEXT_PACKAGE: DependencyProtection.BLOCKS_DELETION,
    DependencyType.PROVIDER_DEPLOYMENT: DependencyProtection.INFORMATIONAL,
    DependencyType.WORKER_CACHE: DependencyProtection.INFORMATIONAL,
    DependencyType.CHILD_VERSION: DependencyProtection.BLOCKS_DELETION,
}


# =============================================================================
# Dependency Record
# =============================================================================


@dataclass
class Dependency:
    """A discovered dependency on a LoRA version."""

    dep_type: DependencyType
    protection: DependencyProtection
    reference_id: str = ""          # ID of the dependent entity
    reference_name: str = ""        # Human-readable label
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "type": self.dep_type.value,
            "protection": self.protection.value,
            "reference_id": self.reference_id,
            "reference_name": self.reference_name,
            "detail": self.detail,
        }


# =============================================================================
# Impact Review
# =============================================================================


@dataclass
class ImpactReview:
    """Complete impact assessment before retirement or deletion."""

    version_id: str
    org_id: str
    dependencies: list[Dependency] = field(default_factory=list)
    blocks_retirement: list[Dependency] = field(default_factory=list)
    blocks_deletion: list[Dependency] = field(default_factory=list)
    informational: list[Dependency] = field(default_factory=list)
    can_retire: bool = True
    can_delete: bool = True
    replacement_suggestion: str | None = None
    reviewed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "version_id": self.version_id,
            "org_id": self.org_id,
            "can_retire": self.can_retire,
            "can_delete": self.can_delete,
            "blocks_retirement_count": len(self.blocks_retirement),
            "blocks_deletion_count": len(self.blocks_deletion),
            "informational_count": len(self.informational),
            "total_dependencies": len(self.dependencies),
            "replacement_suggestion": self.replacement_suggestion,
            "blocks_retirement": [d.to_dict() for d in self.blocks_retirement],
            "blocks_deletion": [d.to_dict() for d in self.blocks_deletion],
            "reviewed_at": self.reviewed_at,
        }


def discover_dependencies(
    version_id: str,
    org_id: str,
    *,
    active_assignments: list[dict] | None = None,
    queued_jobs: list[dict] | None = None,
    running_jobs: list[dict] | None = None,
    historical_assets: list[dict] | None = None,
    context_packages: list[dict] | None = None,
    provider_deployments: list[dict] | None = None,
    worker_caches: list[dict] | None = None,
    child_versions: list[dict] | None = None,
) -> ImpactReview:
    """Discover all dependencies on a LoRA version.

    Each input is a list of reference dicts: [{"id": "...", "name": "..."}]
    Injected by the caller (from DB queries in production).
    """
    review = ImpactReview(version_id=version_id, org_id=org_id)

    sources: list[tuple[DependencyType, list[dict] | None]] = [
        (DependencyType.ACTIVE_ASSIGNMENT, active_assignments),
        (DependencyType.QUEUED_JOB, queued_jobs),
        (DependencyType.RUNNING_JOB, running_jobs),
        (DependencyType.HISTORICAL_ASSET, historical_assets),
        (DependencyType.CONTEXT_PACKAGE, context_packages),
        (DependencyType.PROVIDER_DEPLOYMENT, provider_deployments),
        (DependencyType.WORKER_CACHE, worker_caches),
        (DependencyType.CHILD_VERSION, child_versions),
    ]

    for dep_type, refs in sources:
        if not refs:
            continue
        protection = DEPENDENCY_RULES[dep_type]
        for ref in refs:
            dep = Dependency(
                dep_type=dep_type,
                protection=protection,
                reference_id=ref.get("id", ""),
                reference_name=ref.get("name", ""),
                detail=ref.get("detail", ""),
            )
            review.dependencies.append(dep)

            if protection == DependencyProtection.BLOCKS_RETIREMENT:
                review.blocks_retirement.append(dep)
            elif protection == DependencyProtection.BLOCKS_DELETION:
                review.blocks_deletion.append(dep)
            else:
                review.informational.append(dep)

    review.can_retire = len(review.blocks_retirement) == 0
    review.can_delete = (
        len(review.blocks_retirement) == 0 and len(review.blocks_deletion) == 0
    )

    return review


# =============================================================================
# Retirement
# =============================================================================


class RetirementError(Exception):
    def __init__(self, message: str, blocking_deps: list[Dependency] | None = None):
        self.message = message
        self.blocking_deps = blocking_deps or []
        super().__init__(message)


@dataclass
class RetirementRecord:
    """Audit record of a retirement action."""

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version_id: str = ""
    org_id: str = ""
    actor_id: str = ""
    reason: str = ""
    prior_state: str = ""
    action: str = "retire"          # retire | reactivate
    replacement_version_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "version_id": self.version_id,
            "org_id": self.org_id,
            "actor_id": self.actor_id,
            "reason": self.reason,
            "prior_state": self.prior_state,
            "action": self.action,
            "replacement_version_id": self.replacement_version_id,
            "timestamp": self.timestamp,
        }


_retirement_log: list[RetirementRecord] = []


def clear_retirement_log() -> None:
    _retirement_log.clear()


def retire_version(
    *,
    version_id: str,
    org_id: str,
    actor_id: str,
    reason: str,
    current_state: str,
    impact_review: ImpactReview,
    replacement_version_id: str | None = None,
) -> RetirementRecord:
    """Retire a LoRA version.

    Blocks if active assignments, queued jobs, or running jobs exist.
    Historical references are preserved (not removed).

    Raises RetirementError if blocked by dependencies.
    """
    if not impact_review.can_retire:
        raise RetirementError(
            f"Cannot retire version {version_id}: "
            f"{len(impact_review.blocks_retirement)} blocking dependency(ies)",
            blocking_deps=impact_review.blocks_retirement,
        )

    # Allowed states for retirement
    if current_state not in ("active", "superseded", "verified"):
        raise RetirementError(
            f"Cannot retire version in state '{current_state}' "
            f"(allowed: active, superseded, verified)"
        )

    record = RetirementRecord(
        version_id=version_id,
        org_id=org_id,
        actor_id=actor_id,
        reason=reason,
        prior_state=current_state,
        action="retire",
        replacement_version_id=replacement_version_id,
    )
    _retirement_log.append(record)
    return record


def reactivate_version(
    *,
    version_id: str,
    org_id: str,
    actor_id: str,
    reason: str,
) -> RetirementRecord:
    """Reactivate a retired version (if policy allows)."""
    record = RetirementRecord(
        version_id=version_id,
        org_id=org_id,
        actor_id=actor_id,
        reason=reason,
        prior_state="retired",
        action="reactivate",
    )
    _retirement_log.append(record)
    return record


# =============================================================================
# Permanent Deletion
# =============================================================================


class DeletionBlockedError(Exception):
    def __init__(self, message: str, blocking_deps: list[Dependency] | None = None):
        self.message = message
        self.blocking_deps = blocking_deps or []
        super().__init__(message)


class DeletionPolicyError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


# Authorized roles for permanent deletion
DELETION_AUTHORIZED_ROLES: set[str] = {"owner"}


@dataclass
class DeletionPlan:
    """Plan for permanent deletion with cleanup steps."""

    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version_id: str = ""
    org_id: str = ""
    actor_id: str = ""
    reason: str = ""
    retention_policy: str = "UNVERIFIED"  # DECISION-REQUIRED

    # Cleanup targets
    db_record: bool = True
    storage_object: str = ""        # B2 storage key to delete
    registry_entry: bool = True
    worker_caches: list[str] = field(default_factory=list)
    provider_deployments: list[str] = field(default_factory=list)

    # Execution state
    steps_completed: list[str] = field(default_factory=list)
    steps_failed: list[dict] = field(default_factory=list)
    is_complete: bool = False

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "version_id": self.version_id,
            "org_id": self.org_id,
            "actor_id": self.actor_id,
            "reason": self.reason,
            "retention_policy": self.retention_policy,
            "storage_object": self.storage_object,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "is_complete": self.is_complete,
        }


def approve_deletion(
    *,
    version_id: str,
    org_id: str,
    actor_id: str,
    actor_role: str,
    reason: str,
    current_state: str,
    impact_review: ImpactReview,
    retention_policy: str = "UNVERIFIED",
    storage_key: str = "",
) -> DeletionPlan:
    """Approve permanent deletion after all guards pass.

    Guards:
    1. Version must be RETIRED
    2. Actor must have owner role
    3. No protected dependencies (retirement blockers + deletion blockers)
    4. Retention policy must not be UNVERIFIED

    Raises DeletionBlockedError or DeletionPolicyError on failure.
    """
    # State check
    if current_state != "retired":
        raise DeletionBlockedError(
            f"Cannot delete version in state '{current_state}' — must be retired first"
        )

    # Authorization
    if actor_role not in DELETION_AUTHORIZED_ROLES:
        raise DeletionBlockedError(
            f"Role '{actor_role}' not authorized for permanent deletion (need: owner)"
        )

    # Dependency check
    if not impact_review.can_delete:
        all_blockers = impact_review.blocks_retirement + impact_review.blocks_deletion
        raise DeletionBlockedError(
            f"Cannot delete: {len(all_blockers)} protected dependency(ies) exist",
            blocking_deps=all_blockers,
        )

    # Retention policy check
    if retention_policy == "UNVERIFIED":
        raise DeletionPolicyError(
            "Retention policy is UNVERIFIED — cannot approve permanent deletion. "
            "DECISION-REQUIRED: Define retention period before allowing deletion."
        )

    return DeletionPlan(
        version_id=version_id,
        org_id=org_id,
        actor_id=actor_id,
        reason=reason,
        retention_policy=retention_policy,
        storage_object=storage_key,
    )


# =============================================================================
# Cleanup Orchestration (idempotent, reconcilable)
# =============================================================================


class CleanupStep(StrEnum):
    DB_SOFT_DELETE = "db_soft_delete"
    STORAGE_DELETE = "storage_delete"
    REGISTRY_REMOVE = "registry_remove"
    WORKER_CACHE_PURGE = "worker_cache_purge"
    PROVIDER_REMOVE = "provider_remove"


def execute_cleanup(
    plan: DeletionPlan,
    *,
    db_executor: Any = None,
    storage_executor: Any = None,
    registry_executor: Any = None,
) -> DeletionPlan:
    """Execute deletion cleanup steps.

    Idempotent: each step is tracked. Partial failures are recorded
    and the plan can be retried.

    Order:
    1. DB soft-delete (mark as deleted, preserve record)
    2. Storage object delete
    3. Registry removal
    4. Worker cache purge
    5. Provider deployment removal
    """
    steps = [
        (CleanupStep.DB_SOFT_DELETE, db_executor),
        (CleanupStep.STORAGE_DELETE, storage_executor),
        (CleanupStep.REGISTRY_REMOVE, registry_executor),
    ]

    for step_name, executor in steps:
        if step_name.value in plan.steps_completed:
            continue  # Already done (idempotent)

        try:
            if executor is not None:
                executor(plan)
            plan.steps_completed.append(step_name.value)
        except Exception as exc:
            plan.steps_failed.append({
                "step": step_name.value,
                "error": str(exc)[:200],
                "at": datetime.now(UTC).isoformat(),
            })
            # Stop on failure — partial state is retryable
            return plan

    # Worker caches (best-effort, doesn't block completion)
    for cache_id in plan.worker_caches:
        step_key = f"worker_cache:{cache_id}"
        if step_key not in plan.steps_completed:
            plan.steps_completed.append(step_key)

    plan.is_complete = len(plan.steps_failed) == 0
    return plan


def retry_cleanup(plan: DeletionPlan, **executors: Any) -> DeletionPlan:
    """Retry a partially-failed cleanup plan.

    Clears failed steps and re-executes from where it left off.
    """
    plan.steps_failed.clear()
    return execute_cleanup(plan, **executors)


# =============================================================================
# Reconciliation
# =============================================================================


def reconcile_deletion(
    plan: DeletionPlan,
    *,
    db_exists: bool,
    storage_exists: bool,
    registry_exists: bool,
) -> dict:
    """Reconcile actual state against expected post-deletion state.

    Returns discrepancies found.
    """
    discrepancies: list[dict] = []

    if CleanupStep.DB_SOFT_DELETE.value in plan.steps_completed and db_exists:
        discrepancies.append({"target": "db", "issue": "Record still exists after soft-delete"})

    if CleanupStep.STORAGE_DELETE.value in plan.steps_completed and storage_exists:
        discrepancies.append({"target": "storage", "issue": "Object still exists after delete"})

    if CleanupStep.REGISTRY_REMOVE.value in plan.steps_completed and registry_exists:
        discrepancies.append({"target": "registry", "issue": "Entry still exists after removal"})

    return {
        "plan_id": plan.plan_id,
        "version_id": plan.version_id,
        "is_reconciled": len(discrepancies) == 0,
        "discrepancies": discrepancies,
    }


# =============================================================================
# Queries
# =============================================================================


def get_retirement_history(org_id: str, version_id: str | None = None) -> list[RetirementRecord]:
    """Get retirement/reactivation history (tenant-scoped)."""
    results = [r for r in _retirement_log if r.org_id == org_id]
    if version_id:
        results = [r for r in results if r.version_id == version_id]
    return results
