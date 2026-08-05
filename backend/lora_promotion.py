"""LoRA Promotion & Rollback — Story 097.

Exactly one active production LoRA version per (workspace, talent, role).
Promotion and rollback are atomic, authorized, auditable, and idempotent.

Constraints:
    - ONE active version per (org_id, talent_id, role)
    - Only VERIFIED/APPROVED versions can be promoted
    - Prior active becomes SUPERSEDED (never deleted)
    - Rollback reactivates a previously-approved compatible version
    - Concurrent promotions serialize via lock (DB: SELECT FOR UPDATE)
    - Every transition is audited with actor, reason, and version IDs

Lifecycle Integration (Story 095):
    VERIFIED → (promote) → ACTIVE
    ACTIVE   → (superseded by promotion/rollback) → SUPERSEDED
    SUPERSEDED → (rollback) → ACTIVE
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# LoRA Role
# =============================================================================


class LoRARole(StrEnum):
    PRIMARY = "primary"         # Main identity model
    STYLE = "style"             # Style-specific LoRA
    CLOTHING = "clothing"       # Wardrobe/outfit LoRA
    ENVIRONMENT = "environment" # Location/setting LoRA


# =============================================================================
# Version State (subset relevant to promotion)
# =============================================================================


class VersionState(StrEnum):
    VERIFIED = "verified"       # Passed checks, eligible for promotion
    ACTIVE = "active"           # Currently in production use
    SUPERSEDED = "superseded"   # Replaced by newer active version
    RETIRED = "retired"         # Permanently deactivated


# States eligible for promotion
PROMOTABLE_STATES: set[VersionState] = {VersionState.VERIFIED, VersionState.SUPERSEDED}

# States eligible for rollback target
ROLLBACK_ELIGIBLE_STATES: set[VersionState] = {VersionState.SUPERSEDED, VersionState.VERIFIED}


# =============================================================================
# Version Record (simplified for promotion context)
# =============================================================================


@dataclass
class PromotableVersion:
    """A LoRA version record in the promotion context."""

    version_id: str
    org_id: str
    talent_id: str
    role: LoRARole = LoRARole.PRIMARY
    state: VersionState = VersionState.VERIFIED
    version_number: int = 1
    output_checksum: str = ""
    base_model_id: str = ""
    base_model_version: str = ""
    is_simulation: bool = False
    lineage_id: str = ""


# =============================================================================
# Promotion Audit Record
# =============================================================================


@dataclass
class PromotionAudit:
    """Immutable audit record of a promotion or rollback event."""

    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    talent_id: str = ""
    role: LoRARole = LoRARole.PRIMARY
    action: str = "promote"         # "promote" or "rollback"
    actor_id: str = ""
    reason: str = ""
    # Version details
    new_active_version_id: str = ""
    new_active_version_number: int = 0
    prior_active_version_id: str | None = None
    prior_active_version_number: int | None = None
    # Result
    success: bool = True
    error: str | None = None
    # Timing
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "audit_id": self.audit_id,
            "org_id": self.org_id,
            "talent_id": self.talent_id,
            "role": self.role.value,
            "action": self.action,
            "actor_id": self.actor_id,
            "reason": self.reason,
            "new_active_version_id": self.new_active_version_id,
            "new_active_version_number": self.new_active_version_number,
            "prior_active_version_id": self.prior_active_version_id,
            "prior_active_version_number": self.prior_active_version_number,
            "success": self.success,
            "error": self.error,
            "timestamp": self.timestamp,
        }


# =============================================================================
# Errors
# =============================================================================


class PromotionError(Exception):
    def __init__(self, message: str, code: str = "PROMOTION_FAILED"):
        self.message = message
        self.code = code
        super().__init__(message)


class RollbackError(Exception):
    def __init__(self, message: str, code: str = "ROLLBACK_FAILED"):
        self.message = message
        self.code = code
        super().__init__(message)


class AuthorizationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


# =============================================================================
# Promotion Registry (simulates DB with one-active constraint)
# =============================================================================

# Key: (org_id, talent_id, role) → active version_id
_active_versions: dict[tuple[str, str, str], str] = {}
_version_store: dict[str, PromotableVersion] = {}
_audit_log: list[PromotionAudit] = []
_promotion_lock = threading.Lock()

# Authorized roles
PROMOTION_ROLES: set[str] = {"owner", "admin"}


def clear_registry() -> None:
    """Clear all state (testing only)."""
    _active_versions.clear()
    _version_store.clear()
    _audit_log.clear()


def register_version(version: PromotableVersion) -> None:
    """Register a version in the store (setup helper)."""
    _version_store[version.version_id] = version


def get_active_version_id(org_id: str, talent_id: str, role: LoRARole) -> str | None:
    """Get the currently active version ID for a talent/role."""
    return _active_versions.get((org_id, talent_id, role.value))


def get_active_version(org_id: str, talent_id: str, role: LoRARole) -> PromotableVersion | None:
    """Get the currently active version record."""
    vid = get_active_version_id(org_id, talent_id, role)
    if vid:
        return _version_store.get(vid)
    return None


# =============================================================================
# Pre-Promotion Validation
# =============================================================================


def validate_promotion(
    version: PromotableVersion,
    *,
    actor_role: str,
) -> list[str]:
    """Validate that a version can be promoted.

    Returns list of violation messages. Empty = valid.
    """
    violations: list[str] = []

    # Authorization
    if actor_role not in PROMOTION_ROLES:
        violations.append(f"Role '{actor_role}' not authorized for promotion (need: {PROMOTION_ROLES})")

    # State check
    if version.state not in PROMOTABLE_STATES:
        violations.append(f"Version state '{version.state.value}' not promotable (need: {[s.value for s in PROMOTABLE_STATES]})")

    # Simulation check
    if version.is_simulation:
        violations.append("Simulation versions cannot be promoted to production")

    # Artifact integrity
    if not version.output_checksum:
        violations.append("Version has no output checksum (artifact not verified)")

    return violations


# =============================================================================
# Promote
# =============================================================================


def promote(
    *,
    version_id: str,
    actor_id: str,
    actor_role: str,
    reason: str = "",
) -> PromotionAudit:
    """Promote a LoRA version to active.

    Atomic: under lock, deactivates prior active and activates the new one.
    Idempotent: promoting the already-active version is a no-op success.

    Raises PromotionError or AuthorizationError on failure.
    """
    version = _version_store.get(version_id)
    if version is None:
        raise PromotionError(f"Version {version_id} not found", code="NOT_FOUND")

    key = (version.org_id, version.talent_id, version.role.value)

    # Idempotent: already active
    current_active_id = _active_versions.get(key)
    if current_active_id == version_id:
        return PromotionAudit(
            org_id=version.org_id,
            talent_id=version.talent_id,
            role=version.role,
            action="promote",
            actor_id=actor_id,
            reason=reason or "Already active (idempotent)",
            new_active_version_id=version_id,
            new_active_version_number=version.version_number,
            prior_active_version_id=version_id,
            success=True,
        )

    # Validate
    violations = validate_promotion(version, actor_role=actor_role)
    if violations:
        audit = PromotionAudit(
            org_id=version.org_id,
            talent_id=version.talent_id,
            role=version.role,
            action="promote",
            actor_id=actor_id,
            reason=reason,
            new_active_version_id=version_id,
            new_active_version_number=version.version_number,
            success=False,
            error="; ".join(violations),
        )
        _audit_log.append(audit)

        if any("not authorized" in v for v in violations):
            raise AuthorizationError(violations[0])
        raise PromotionError("; ".join(violations))

    # Atomic transition
    with _promotion_lock:
        prior_active_id = _active_versions.get(key)
        prior_version = _version_store.get(prior_active_id) if prior_active_id else None

        # Supersede prior
        if prior_version and prior_version.version_id != version_id:
            prior_version.state = VersionState.SUPERSEDED

        # Activate new
        version.state = VersionState.ACTIVE
        _active_versions[key] = version_id

    # Audit
    audit = PromotionAudit(
        org_id=version.org_id,
        talent_id=version.talent_id,
        role=version.role,
        action="promote",
        actor_id=actor_id,
        reason=reason,
        new_active_version_id=version_id,
        new_active_version_number=version.version_number,
        prior_active_version_id=prior_active_id,
        prior_active_version_number=prior_version.version_number if prior_version else None,
        success=True,
    )
    _audit_log.append(audit)
    return audit


# =============================================================================
# Rollback
# =============================================================================


def rollback(
    *,
    org_id: str,
    talent_id: str,
    role: LoRARole,
    target_version_id: str,
    actor_id: str,
    actor_role: str,
    reason: str = "",
) -> PromotionAudit:
    """Rollback to a previously-approved version.

    Atomic: deactivates current, reactivates target.
    The target must be SUPERSEDED or VERIFIED and compatible.

    Raises RollbackError or AuthorizationError on failure.
    """
    # Authorization
    if actor_role not in PROMOTION_ROLES:
        raise AuthorizationError(f"Role '{actor_role}' not authorized for rollback")

    target = _version_store.get(target_version_id)
    if target is None:
        raise RollbackError(f"Target version {target_version_id} not found")

    # Ownership check
    if target.org_id != org_id or target.talent_id != talent_id:
        raise RollbackError("Target version belongs to different workspace/talent")

    if target.role != role:
        raise RollbackError(f"Target version role '{target.role.value}' != requested '{role.value}'")

    key = (org_id, talent_id, role.value)

    # Idempotent: target already active
    if _active_versions.get(key) == target_version_id:
        return PromotionAudit(
            org_id=org_id, talent_id=talent_id, role=role,
            action="rollback", actor_id=actor_id,
            reason=reason or "Already active (idempotent)",
            new_active_version_id=target_version_id,
            new_active_version_number=target.version_number,
            success=True,
        )

    # Eligibility check
    if target.state not in ROLLBACK_ELIGIBLE_STATES:
        raise RollbackError(
            f"Target version state '{target.state.value}' not eligible for rollback "
            f"(need: {[s.value for s in ROLLBACK_ELIGIBLE_STATES]})"
        )

    # Simulation check
    if target.is_simulation:
        raise RollbackError("Cannot rollback to a simulation version")

    # Artifact check
    if not target.output_checksum:
        raise RollbackError("Target version has no verified artifact")

    # Atomic transition
    with _promotion_lock:
        prior_active_id = _active_versions.get(key)
        prior_version = _version_store.get(prior_active_id) if prior_active_id else None

        # Supersede current
        if prior_version and prior_version.version_id != target_version_id:
            prior_version.state = VersionState.SUPERSEDED

        # Reactivate target
        target.state = VersionState.ACTIVE
        _active_versions[key] = target_version_id

    # Audit
    audit = PromotionAudit(
        org_id=org_id, talent_id=talent_id, role=role,
        action="rollback", actor_id=actor_id, reason=reason,
        new_active_version_id=target_version_id,
        new_active_version_number=target.version_number,
        prior_active_version_id=prior_active_id,
        prior_active_version_number=prior_version.version_number if prior_version else None,
        success=True,
    )
    _audit_log.append(audit)
    return audit


# =============================================================================
# Audit Queries
# =============================================================================


def get_promotion_history(
    org_id: str,
    talent_id: str,
    role: LoRARole | None = None,
) -> list[PromotionAudit]:
    """Get promotion/rollback history for a talent (tenant-scoped)."""
    results = [
        a for a in _audit_log
        if a.org_id == org_id and a.talent_id == talent_id
    ]
    if role:
        results = [a for a in results if a.role == role]
    return results


def get_all_active_versions(org_id: str) -> dict[str, str]:
    """Get all active version assignments for an org.

    Returns dict of "(talent_id, role)" → version_id.
    """
    return {
        f"{k[1]}:{k[2]}": vid
        for k, vid in _active_versions.items()
        if k[0] == org_id
    }
