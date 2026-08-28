"""Simulation Isolation — Story 099.

Strict enforcement preventing simulation artifacts from affecting production.
Simulation outputs are test-only: they cannot be approved, promoted, activated,
deployed, assigned to production talent, or referenced by production context.

Isolation Rules:
1. Simulation artifacts use distinct storage namespace (/_simulation/)
2. Simulation versions have immutable is_simulation=True flag
3. Production lifecycle gates DENY simulation versions
4. Production catalog EXCLUDES simulation artifacts
5. Context assembly REJECTS simulation version IDs
6. Production APIs REJECT simulation references even when supplied directly
7. Legacy simulated-active records are QUARANTINED (not deleted)

Storage Namespace:
    Production: /{org_id}/models/{talent_id}/{lineage_id}/v{N}.safetensors
    Simulation: /_simulation/{org_id}/models/{talent_id}/{lineage_id}/v{N}.safetensors

Quarantine:
    Legacy simulation records found in active/approved state are moved to
    QUARANTINED lifecycle with audit evidence preserved.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Simulation Classification
# =============================================================================


class ArtifactMode(StrEnum):
    PRODUCTION = "production"
    SIMULATION = "simulation"


class QuarantineReason(StrEnum):
    SIMULATION_IN_ACTIVE = "simulation_in_active"
    SIMULATION_IN_APPROVED = "simulation_in_approved"
    SIMULATION_ASSIGNED = "simulation_assigned_to_production"
    MODE_MISMATCH = "mode_mismatch"


# =============================================================================
# Storage Namespace
# =============================================================================

SIMULATION_NAMESPACE_PREFIX = "/_simulation"
PRODUCTION_NAMESPACE_PREFIX = "/"


def compute_storage_namespace(
    org_id: str,
    talent_id: str,
    lineage_id: str,
    version_number: int,
    *,
    is_simulation: bool,
) -> str:
    """Compute the storage path with correct namespace isolation."""
    filename = f"v{version_number}.safetensors"
    if is_simulation:
        return f"{SIMULATION_NAMESPACE_PREFIX}/{org_id}/models/{talent_id}/{lineage_id}/{filename}"
    return f"/{org_id}/models/{talent_id}/{lineage_id}/{filename}"


def is_simulation_path(storage_key: str) -> bool:
    """Check if a storage key belongs to the simulation namespace."""
    return storage_key.startswith(SIMULATION_NAMESPACE_PREFIX + "/")


# =============================================================================
# Lifecycle Guards
# =============================================================================


class SimulationGuardError(Exception):
    """Raised when simulation isolation is violated."""

    def __init__(self, message: str, code: str = "SIMULATION_BLOCKED"):
        self.message = message
        self.code = code
        super().__init__(message)


def guard_approval(is_simulation: bool) -> None:
    """Block: simulation cannot be approved."""
    if is_simulation:
        raise SimulationGuardError(
            "Simulation artifacts cannot be approved for production",
            code="APPROVAL_DENIED",
        )


def guard_promotion(is_simulation: bool) -> None:
    """Block: simulation cannot be promoted to active."""
    if is_simulation:
        raise SimulationGuardError(
            "Simulation versions cannot be promoted to production active state",
            code="PROMOTION_DENIED",
        )


def guard_deployment(is_simulation: bool) -> None:
    """Block: simulation cannot be deployed to production workers."""
    if is_simulation:
        raise SimulationGuardError(
            "Simulation artifacts cannot be deployed to production workers",
            code="DEPLOYMENT_DENIED",
        )


def guard_talent_assignment(is_simulation: bool) -> None:
    """Block: simulation cannot be assigned as production talent LoRA."""
    if is_simulation:
        raise SimulationGuardError(
            "Simulation versions cannot be assigned to production talent",
            code="ASSIGNMENT_DENIED",
        )


def guard_context_reference(is_simulation: bool) -> None:
    """Block: production context packages cannot reference simulation versions."""
    if is_simulation:
        raise SimulationGuardError(
            "Production context cannot reference simulation artifacts",
            code="CONTEXT_DENIED",
        )


def guard_generation_use(is_simulation: bool, *, allow_dev_mode: bool = False) -> None:
    """Block: production generation cannot use simulation artifacts.

    Exception: if dev mode is explicitly enabled (AUTH_DEV_MODE=true).
    """
    if is_simulation and not allow_dev_mode:
        raise SimulationGuardError(
            "Production generation cannot use simulation LoRA versions",
            code="GENERATION_DENIED",
        )


# =============================================================================
# Catalog Exclusion
# =============================================================================


@dataclass
class CatalogEntry:
    """A model/version in the catalog."""

    version_id: str
    name: str
    is_simulation: bool = False
    lifecycle: str = "active"
    # ... other fields


def filter_production_catalog(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    """Filter catalog to exclude all simulation entries.

    Production catalog NEVER shows simulation artifacts.
    """
    return [e for e in entries if not e.is_simulation]


def filter_simulation_catalog(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    """Filter catalog to show ONLY simulation entries (dev view)."""
    return [e for e in entries if e.is_simulation]


# =============================================================================
# Version Validation (direct API protection)
# =============================================================================


@dataclass
class VersionReference:
    """A reference to a LoRA version used in an API call."""

    version_id: str
    is_simulation: bool = False


def validate_production_reference(ref: VersionReference) -> None:
    """Validate that a direct API version reference is not simulation.

    Even if a caller explicitly provides a simulation version_id,
    production APIs must reject it.
    """
    if ref.is_simulation:
        raise SimulationGuardError(
            f"Version {ref.version_id} is a simulation artifact and cannot be "
            f"used in production context",
            code="REFERENCE_DENIED",
        )


# =============================================================================
# Quarantine
# =============================================================================


@dataclass
class QuarantineRecord:
    """Record of a quarantined simulation artifact."""

    quarantine_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version_id: str = ""
    org_id: str = ""
    talent_id: str = ""
    prior_lifecycle: str = ""       # What state it was in before quarantine
    reason: QuarantineReason = QuarantineReason.SIMULATION_IN_ACTIVE
    quarantined_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    quarantined_by: str = "system"  # Usually system/migration
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "quarantine_id": self.quarantine_id,
            "version_id": self.version_id,
            "org_id": self.org_id,
            "talent_id": self.talent_id,
            "prior_lifecycle": self.prior_lifecycle,
            "reason": self.reason.value,
            "quarantined_at": self.quarantined_at,
            "quarantined_by": self.quarantined_by,
            "notes": self.notes,
        }


# In-memory quarantine store
_quarantine_store: list[QuarantineRecord] = []


def clear_quarantine() -> None:
    """Clear store (testing only)."""
    _quarantine_store.clear()


def quarantine_record(
    *,
    version_id: str,
    org_id: str,
    talent_id: str = "",
    prior_lifecycle: str,
    reason: QuarantineReason,
    notes: str = "",
) -> QuarantineRecord:
    """Quarantine a simulation record found in production state.

    Does NOT delete the record — preserves evidence with quarantine metadata.
    """
    record = QuarantineRecord(
        version_id=version_id,
        org_id=org_id,
        talent_id=talent_id,
        prior_lifecycle=prior_lifecycle,
        reason=reason,
        notes=notes,
    )
    _quarantine_store.append(record)
    return record


def scan_for_violations(
    versions: list[dict],
) -> list[QuarantineRecord]:
    """Scan version records and quarantine any simulation artifacts in production states.

    Input: list of dicts with keys: version_id, org_id, talent_id, is_simulation, lifecycle
    Returns: list of quarantine records created.
    """
    production_states = {"active", "approved", "deployed"}
    quarantined: list[QuarantineRecord] = []

    for v in versions:
        if v.get("is_simulation") and v.get("lifecycle") in production_states:
            reason = QuarantineReason.SIMULATION_IN_ACTIVE
            if v["lifecycle"] == "approved":
                reason = QuarantineReason.SIMULATION_IN_APPROVED

            record = quarantine_record(
                version_id=v["version_id"],
                org_id=v.get("org_id", ""),
                talent_id=v.get("talent_id", ""),
                prior_lifecycle=v["lifecycle"],
                reason=reason,
                notes=f"Legacy simulation found in '{v['lifecycle']}' state during scan",
            )
            quarantined.append(record)

    return quarantined


def get_quarantined(org_id: str | None = None) -> list[QuarantineRecord]:
    """Get quarantined records, optionally filtered by org."""
    if org_id:
        return [r for r in _quarantine_store if r.org_id == org_id]
    return list(_quarantine_store)


# =============================================================================
# Environment Controls
# =============================================================================


@dataclass
class SimulationEnvironment:
    """Configuration for simulation mode access."""

    enabled: bool = False           # Must be explicitly True
    visible_label: str = "SIMULATION MODE"
    requires_dev_mode: bool = True  # Only available when AUTH_DEV_MODE=true
    storage_isolated: bool = True   # Uses /_simulation/ namespace

    def is_accessible(self, *, auth_dev_mode: bool = False) -> bool:
        """Check if simulation features are accessible."""
        if not self.enabled:
            return False
        if self.requires_dev_mode and not auth_dev_mode:
            return False
        return True


# Default: simulation is NOT enabled in production
DEFAULT_SIMULATION_ENV = SimulationEnvironment(enabled=False)
DEV_SIMULATION_ENV = SimulationEnvironment(enabled=True, requires_dev_mode=True)
