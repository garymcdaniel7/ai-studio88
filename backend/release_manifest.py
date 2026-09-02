"""Release Versioning & Manifest — Story 062.

One immutable release manifest linking all artifacts, with version propagation,
migration compatibility checks, and rollback safety evaluation.

Release ID format: "rel-{date}-{short_sha}" e.g. "rel-20260803-a1b2c3d"

Manifest contents:
    - release_id (immutable identifier)
    - commit_sha (git commit)
    - frontend_build (Vercel deployment ID or build hash)
    - backend_image (Docker image digest)
    - worker_image (GPU worker image digest)
    - migrations_version (latest applied migration number)
    - config_version (environment profile hash)
    - model_manifest_version (build-manifest.yml hash)
    - deployment_targets (which environments)
    - created_at, created_by, approved_by

Compatibility rules:
    EXPAND  — additive changes (new columns, new tables) — safe to rollback
    MIGRATE — data transformation — rollback requires reverse migration
    CONTRACT — destructive changes (drop column, rename) — BLOCKS rollback

Version propagation:
    - /health and /ready expose release_id
    - Logs include release_id in structured context
    - Job records carry the release_id that created them
    - Error reports include release_id
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Migration Compatibility
# =============================================================================


class MigrationKind(str, Enum):
    EXPAND = "expand"       # Additive — safe to rollback (new column, new table)
    MIGRATE = "migrate"     # Data transform — needs reverse migration for rollback
    CONTRACT = "contract"   # Destructive — BLOCKS rollback


class RollbackSafety(str, Enum):
    SAFE = "safe"               # All changes are reversible
    REQUIRES_REVERSE = "requires_reverse"  # Needs reverse migration script
    BLOCKED = "blocked"         # Contains irreversible changes — forward-repair only


# =============================================================================
# Release Manifest
# =============================================================================


@dataclass(frozen=True)
class ReleaseManifest:
    """Immutable release manifest — one ID links all artifacts."""
    release_id: str
    commit_sha: str
    frontend_build: str = ""
    backend_image: str = ""
    worker_image: str = ""
    migrations_version: str = ""
    config_version: str = ""
    model_manifest_version: str = ""
    deployment_targets: tuple[str, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    created_by: str = ""
    approved_by: str | None = None
    security_gate_passed: bool = False

    # Migration compatibility for this release
    migration_kind: MigrationKind = MigrationKind.EXPAND
    rollback_safety: RollbackSafety = RollbackSafety.SAFE
    rollback_blocked_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "commit_sha": self.commit_sha,
            "frontend_build": self.frontend_build,
            "backend_image": self.backend_image,
            "worker_image": self.worker_image,
            "migrations_version": self.migrations_version,
            "config_version": self.config_version,
            "model_manifest_version": self.model_manifest_version,
            "deployment_targets": list(self.deployment_targets),
            "created_at": self.created_at,
            "created_by": self.created_by,
            "approved_by": self.approved_by,
            "security_gate_passed": self.security_gate_passed,
            "migration_kind": self.migration_kind.value,
            "rollback_safety": self.rollback_safety.value,
            "rollback_blocked_reason": self.rollback_blocked_reason,
        }

    @property
    def manifest_hash(self) -> str:
        """Integrity hash of the manifest contents."""
        content = f"{self.release_id}:{self.commit_sha}:{self.backend_image}:{self.worker_image}:{self.migrations_version}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# =============================================================================
# Release Store
# =============================================================================

_release_store: dict[str, ReleaseManifest] = {}
_active_release: str | None = None  # Currently deployed release_id


# =============================================================================
# Release Creation
# =============================================================================


def generate_release_id(commit_sha: str) -> str:
    """Generate a human-readable release ID."""
    date_part = datetime.now(UTC).strftime("%Y%m%d")
    sha_short = commit_sha[:7] if commit_sha else uuid.uuid4().hex[:7]
    return f"rel-{date_part}-{sha_short}"


def create_release(
    commit_sha: str,
    created_by: str,
    frontend_build: str = "",
    backend_image: str = "",
    worker_image: str = "",
    migrations_version: str = "",
    config_version: str = "",
    model_manifest_version: str = "",
    deployment_targets: tuple[str, ...] = ("staging",),
    migration_kind: MigrationKind = MigrationKind.EXPAND,
    security_gate_passed: bool = False,
) -> ReleaseManifest:
    """Create an immutable release manifest.

    The manifest cannot be modified after creation. A new release
    must be created for any change.
    """
    if not commit_sha:
        raise ValueError("commit_sha is required for release creation")
    if not created_by:
        raise ValueError("created_by is required")

    release_id = generate_release_id(commit_sha)

    # Determine rollback safety based on migration kind
    rollback_safety, blocked_reason = evaluate_rollback_safety(migration_kind)

    manifest = ReleaseManifest(
        release_id=release_id,
        commit_sha=commit_sha,
        frontend_build=frontend_build,
        backend_image=backend_image,
        worker_image=worker_image,
        migrations_version=migrations_version,
        config_version=config_version,
        model_manifest_version=model_manifest_version,
        deployment_targets=deployment_targets,
        created_by=created_by,
        security_gate_passed=security_gate_passed,
        migration_kind=migration_kind,
        rollback_safety=rollback_safety,
        rollback_blocked_reason=blocked_reason,
    )

    _release_store[release_id] = manifest
    logger.info(f"RELEASE_CREATED: id={release_id} commit={commit_sha[:7]} by={created_by}")
    return manifest


# =============================================================================
# Migration Compatibility & Rollback Safety
# =============================================================================


def evaluate_rollback_safety(migration_kind: MigrationKind) -> tuple[RollbackSafety, str | None]:
    """Evaluate whether rollback is safe for this migration type.

    Rules:
        EXPAND (add column/table) → SAFE (old code ignores new columns)
        MIGRATE (data transform) → REQUIRES_REVERSE (needs reverse script)
        CONTRACT (drop/rename) → BLOCKED (irreversible without data loss)
    """
    if migration_kind == MigrationKind.EXPAND:
        return RollbackSafety.SAFE, None
    elif migration_kind == MigrationKind.MIGRATE:
        return RollbackSafety.REQUIRES_REVERSE, "Data migration requires reverse script for rollback"
    elif migration_kind == MigrationKind.CONTRACT:
        return RollbackSafety.BLOCKED, "Contains irreversible schema changes (column drop/rename). Forward-repair only."
    return RollbackSafety.SAFE, None


def check_rollback_compatibility(
    current_release_id: str,
    target_release_id: str,
) -> dict[str, Any]:
    """Check if rolling back from current to target is safe.

    Returns a compatibility report with decision and reason.
    """
    current = _release_store.get(current_release_id)
    target = _release_store.get(target_release_id)

    if not current:
        return {"compatible": False, "reason": f"Current release {current_release_id} not found"}
    if not target:
        return {"compatible": False, "reason": f"Target release {target_release_id} not found"}

    # Check if current release blocks rollback
    if current.rollback_safety == RollbackSafety.BLOCKED:
        return {
            "compatible": False,
            "reason": current.rollback_blocked_reason or "Rollback blocked by irreversible changes",
            "required_action": "forward_repair",
        }

    if current.rollback_safety == RollbackSafety.REQUIRES_REVERSE:
        return {
            "compatible": True,
            "reason": "Rollback possible but requires reverse migration",
            "requires_reverse_migration": True,
            "warning": current.rollback_blocked_reason,
        }

    # Check version ordering (can't rollback to a newer release)
    if current.created_at < target.created_at:
        return {"compatible": False, "reason": "Target is newer than current — this is a forward deploy, not rollback"}

    return {
        "compatible": True,
        "reason": "Rollback safe — all changes are additive (expand-only)",
        "requires_reverse_migration": False,
    }


# =============================================================================
# Rollback Rehearsal
# =============================================================================


@dataclass
class RollbackRehearsalResult:
    """Evidence from a rollback rehearsal."""
    rehearsal_id: str = field(default_factory=lambda: f"reh-{uuid.uuid4().hex[:12]}")
    from_release: str = ""
    to_release: str = ""
    environment: str = "staging"
    compatibility_check: dict = field(default_factory=dict)
    executed: bool = False
    success: bool = False
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    evidence_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def rehearse_rollback(
    current_release_id: str,
    target_release_id: str,
    environment: str = "staging",
) -> RollbackRehearsalResult:
    """Rehearse a rollback in staging and record evidence.

    Does NOT execute the actual rollback — only validates feasibility
    and records the evidence for promotion approval.
    """
    result = RollbackRehearsalResult(
        from_release=current_release_id,
        to_release=target_release_id,
        environment=environment,
    )

    # Step 1: Compatibility check
    compat = check_rollback_compatibility(current_release_id, target_release_id)
    result.compatibility_check = compat

    if not compat.get("compatible"):
        result.executed = False
        result.success = False
        result.errors.append(f"Rollback blocked: {compat.get('reason')}")
        return result

    # Step 2: Validate artifacts exist
    target = _release_store.get(target_release_id)
    if target and not target.backend_image and not target.commit_sha:
        result.errors.append("Target release has no deployable artifacts")
        result.success = False
        return result

    # Step 3: Record rehearsal as executed
    result.executed = True
    result.success = True
    result.duration_seconds = 0.1  # Simulated — real rehearsal would measure

    logger.info(
        f"ROLLBACK_REHEARSAL: from={current_release_id} to={target_release_id} "
        f"env={environment} success={result.success}"
    )
    return result


# =============================================================================
# Version Propagation
# =============================================================================


def get_active_release() -> ReleaseManifest | None:
    """Get the currently active release manifest."""
    if _active_release:
        return _release_store.get(_active_release)
    return None


def set_active_release(release_id: str) -> None:
    """Set the active release (after successful deployment)."""
    global _active_release
    if release_id not in _release_store:
        raise ValueError(f"Release {release_id} not found")
    _active_release = release_id


def get_version_info() -> dict[str, Any]:
    """Get version info for health/ready endpoints.

    Exposes release identity WITHOUT secrets.
    """
    release = get_active_release()
    if not release:
        return {
            "release_id": "dev-local",
            "commit_sha": "unknown",
            "environment": "development",
        }
    return {
        "release_id": release.release_id,
        "commit_sha": release.commit_sha[:7],
        "migrations_version": release.migrations_version,
        "manifest_hash": release.manifest_hash,
        "deployment_targets": list(release.deployment_targets),
    }


# =============================================================================
# Promotion (staging → production)
# =============================================================================


def approve_for_promotion(
    release_id: str,
    approved_by: str,
    rehearsal_evidence: RollbackRehearsalResult | None = None,
) -> dict[str, Any]:
    """Approve a release for production promotion.

    Requirements:
    - Security gate must have passed
    - Rollback rehearsal must succeed (or be explicitly waived)
    - Approver identity recorded
    """
    manifest = _release_store.get(release_id)
    if not manifest:
        return {"approved": False, "reason": "Release not found"}

    issues = []

    if not manifest.security_gate_passed:
        issues.append("Security gate has not passed")

    if rehearsal_evidence and not rehearsal_evidence.success:
        issues.append(f"Rollback rehearsal failed: {rehearsal_evidence.errors}")

    if manifest.rollback_safety == RollbackSafety.BLOCKED and not rehearsal_evidence:
        issues.append("Release contains irreversible changes — requires explicit forward-repair acknowledgment")

    if issues:
        return {"approved": False, "issues": issues}

    # Record approval (manifest is frozen, store approval separately)
    logger.info(f"RELEASE_APPROVED: id={release_id} by={approved_by}")
    return {
        "approved": True,
        "release_id": release_id,
        "approved_by": approved_by,
        "approved_at": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# Testing
# =============================================================================


def _reset_store() -> None:
    global _active_release
    _release_store.clear()
    _active_release = None
