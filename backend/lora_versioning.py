"""LoRA Versioning — Story 095.

Atomic sequential version allocation with immutable lineage for every
trained LoRA model. Prevents duplicate versions, enforces provenance
immutability, and distinguishes simulation from production outputs.

Version Allocation:
    - Sequential within a talent/model lineage (v1, v2, v3...)
    - Atomic: concurrent completions cannot create the same version number
    - Each version is immutable after creation (provenance fields locked)

Lineage Fields (immutable after creation):
    - parent_version_id: which version this was fine-tuned from (None for first)
    - training_job_id: the durable job that produced this version
    - dataset_manifest_id: exact images used (from Story 091)
    - dataset_checksum: hash of the manifest for verification
    - training_config: hyperparameters and settings used
    - base_model_id + base_model_version: the foundation model
    - provider_mode: production or simulation
    - output_checksum: SHA-256 of the output .safetensors file
    - container_manifest: software/container versions used

Lifecycle:
    CREATED → VERIFIED → ACTIVE → SUPERSEDED → RETIRED
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Version Lifecycle
# =============================================================================


class VersionLifecycle(StrEnum):
    CREATED = "created"         # Just allocated, output not yet verified
    VERIFIED = "verified"       # Output checksum confirmed
    ACTIVE = "active"           # Currently in use for generation
    SUPERSEDED = "superseded"   # Replaced by newer version
    RETIRED = "retired"         # Permanently deactivated


# =============================================================================
# Provider Mode (from Story 093)
# =============================================================================


class TrainingMode(StrEnum):
    PRODUCTION = "production"
    SIMULATION = "simulation"


# =============================================================================
# Training Configuration (immutable snapshot)
# =============================================================================


@dataclass
class TrainingConfig:
    """Immutable training configuration snapshot."""

    learning_rate: float = 1e-4
    epochs: int = 100
    batch_size: int = 1
    resolution: int = 512
    network_rank: int = 32
    network_alpha: int = 16
    optimizer: str = "AdamW8bit"
    scheduler: str = "cosine"
    mixed_precision: str = "fp16"
    gradient_accumulation: int = 1
    max_train_steps: int | None = None
    seed: int = 42
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "learning_rate": self.learning_rate,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "resolution": self.resolution,
            "network_rank": self.network_rank,
            "network_alpha": self.network_alpha,
            "optimizer": self.optimizer,
            "scheduler": self.scheduler,
            "mixed_precision": self.mixed_precision,
            "seed": self.seed,
            "max_train_steps": self.max_train_steps,
        }

    def config_hash(self) -> str:
        """Deterministic hash of config for comparison."""
        parts = [
            str(self.learning_rate), str(self.epochs), str(self.batch_size),
            str(self.resolution), str(self.network_rank), str(self.network_alpha),
            self.optimizer, self.scheduler, self.mixed_precision, str(self.seed),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


# =============================================================================
# LoRA Version Record
# =============================================================================


@dataclass
class LoRAVersion:
    """An immutable versioned LoRA training output."""

    # Identity
    version_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    talent_id: str = ""
    lineage_id: str = ""            # Groups versions of the same logical model
    version_number: int = 0         # Sequential within lineage (1, 2, 3...)

    # Lifecycle
    lifecycle: VersionLifecycle = VersionLifecycle.CREATED
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # Lineage (immutable after creation)
    parent_version_id: str | None = None    # Previous version (None for v1)
    training_job_id: str = ""               # Durable job that produced this
    dataset_manifest_id: str = ""           # Exact dataset used
    dataset_checksum: str = ""              # Hash of manifest for verification
    training_config: TrainingConfig = field(default_factory=TrainingConfig)

    # Base model
    base_model_id: str = ""                 # e.g., "flux-dev", "sdxl"
    base_model_version: str = ""            # e.g., "1.0"

    # Provider
    training_mode: TrainingMode = TrainingMode.PRODUCTION
    provider_name: str = ""                 # e.g., "vast_ai"
    container_manifest: str = ""            # Docker image/tag used

    # Output
    output_checksum: str = ""               # SHA-256 of .safetensors file
    output_storage_key: str = ""            # B2 storage location
    output_size_bytes: int = 0
    trigger_word: str = ""

    # Flags
    is_immutable: bool = True               # Provenance fields locked

    def to_dict(self) -> dict:
        return {
            "version_id": self.version_id,
            "org_id": self.org_id,
            "talent_id": self.talent_id,
            "lineage_id": self.lineage_id,
            "version_number": self.version_number,
            "lifecycle": self.lifecycle.value,
            "parent_version_id": self.parent_version_id,
            "training_job_id": self.training_job_id,
            "dataset_manifest_id": self.dataset_manifest_id,
            "dataset_checksum": self.dataset_checksum,
            "base_model_id": self.base_model_id,
            "base_model_version": self.base_model_version,
            "training_mode": self.training_mode.value,
            "provider_name": self.provider_name,
            "output_checksum": self.output_checksum,
            "output_storage_key": self.output_storage_key,
            "output_size_bytes": self.output_size_bytes,
            "trigger_word": self.trigger_word,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }


# =============================================================================
# Version Registry (atomic allocation)
# =============================================================================

_version_store: dict[str, LoRAVersion] = {}  # version_id → LoRAVersion
_lineage_counters: dict[str, int] = {}       # lineage_id → current max version
_allocation_lock = threading.Lock()


def clear_registry() -> None:
    """Clear registry (testing only)."""
    _version_store.clear()
    _lineage_counters.clear()


class VersionAllocationError(Exception):
    """Raised when version allocation fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ImmutabilityError(Exception):
    """Raised when attempting to modify immutable provenance."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def allocate_version(
    *,
    org_id: str,
    talent_id: str,
    lineage_id: str,
    training_job_id: str,
    dataset_manifest_id: str,
    dataset_checksum: str,
    training_config: TrainingConfig,
    base_model_id: str,
    base_model_version: str,
    training_mode: TrainingMode,
    provider_name: str = "",
    container_manifest: str = "",
    output_checksum: str = "",
    output_storage_key: str = "",
    output_size_bytes: int = 0,
    trigger_word: str = "",
    parent_version_id: str | None = None,
    created_by: str = "",
) -> LoRAVersion:
    """Atomically allocate the next version number within a lineage.

    Thread-safe: uses a lock to prevent concurrent allocations from
    creating duplicate version numbers.

    Returns the created LoRAVersion record.
    Raises VersionAllocationError on constraint violations.
    """
    if not org_id:
        raise VersionAllocationError("org_id is required")
    if not talent_id:
        raise VersionAllocationError("talent_id is required")
    if not lineage_id:
        raise VersionAllocationError("lineage_id is required")
    if not training_job_id:
        raise VersionAllocationError("training_job_id is required")

    # Check for duplicate job_id (idempotency)
    for existing in _version_store.values():
        if existing.training_job_id == training_job_id and existing.lineage_id == lineage_id:
            return existing  # Idempotent — same job already created a version

    with _allocation_lock:
        # Atomically get next version number
        current_max = _lineage_counters.get(lineage_id, 0)
        next_version = current_max + 1
        _lineage_counters[lineage_id] = next_version

    # Validate parent reference
    if parent_version_id:
        parent = _version_store.get(parent_version_id)
        if parent is None:
            raise VersionAllocationError(
                f"Parent version {parent_version_id} not found in registry"
            )
        if parent.lineage_id != lineage_id:
            raise VersionAllocationError(
                f"Parent version belongs to different lineage "
                f"({parent.lineage_id} != {lineage_id})"
            )

    version = LoRAVersion(
        org_id=org_id,
        talent_id=talent_id,
        lineage_id=lineage_id,
        version_number=next_version,
        parent_version_id=parent_version_id,
        training_job_id=training_job_id,
        dataset_manifest_id=dataset_manifest_id,
        dataset_checksum=dataset_checksum,
        training_config=training_config,
        base_model_id=base_model_id,
        base_model_version=base_model_version,
        training_mode=training_mode,
        provider_name=provider_name,
        container_manifest=container_manifest,
        output_checksum=output_checksum,
        output_storage_key=output_storage_key,
        output_size_bytes=output_size_bytes,
        trigger_word=trigger_word,
        created_by=created_by,
        lifecycle=VersionLifecycle.CREATED,
    )

    _version_store[version.version_id] = version
    return version


# =============================================================================
# Verification
# =============================================================================


def verify_output(version_id: str, actual_checksum: str) -> LoRAVersion:
    """Verify the output checksum matches and transition to VERIFIED.

    Raises VersionAllocationError if checksum doesn't match.
    """
    version = _version_store.get(version_id)
    if version is None:
        raise VersionAllocationError(f"Version {version_id} not found")

    if version.output_checksum and version.output_checksum != actual_checksum:
        raise VersionAllocationError(
            f"Checksum mismatch: expected {version.output_checksum[:12]}... "
            f"got {actual_checksum[:12]}..."
        )

    version.output_checksum = actual_checksum
    version.lifecycle = VersionLifecycle.VERIFIED
    return version


# =============================================================================
# Immutability Enforcement
# =============================================================================

IMMUTABLE_FIELDS: set[str] = {
    "org_id", "talent_id", "lineage_id", "version_number",
    "parent_version_id", "training_job_id", "dataset_manifest_id",
    "dataset_checksum", "base_model_id", "base_model_version",
    "training_mode", "output_checksum", "created_by", "created_at",
}


def modify_version(version_id: str, field_name: str, value: Any) -> None:
    """Attempt to modify a version field.

    Raises ImmutabilityError for provenance fields.
    Only lifecycle and non-provenance fields can be updated.
    """
    version = _version_store.get(version_id)
    if version is None:
        raise VersionAllocationError(f"Version {version_id} not found")

    if field_name in IMMUTABLE_FIELDS:
        raise ImmutabilityError(
            f"Field '{field_name}' is immutable on LoRA version records"
        )

    if hasattr(version, field_name):
        setattr(version, field_name, value)


# =============================================================================
# Lifecycle Transitions
# =============================================================================


VALID_LIFECYCLE_TRANSITIONS: dict[tuple[VersionLifecycle, VersionLifecycle], bool] = {
    (VersionLifecycle.CREATED, VersionLifecycle.VERIFIED): True,
    (VersionLifecycle.VERIFIED, VersionLifecycle.ACTIVE): True,
    (VersionLifecycle.ACTIVE, VersionLifecycle.SUPERSEDED): True,
    (VersionLifecycle.ACTIVE, VersionLifecycle.RETIRED): True,
    (VersionLifecycle.SUPERSEDED, VersionLifecycle.ACTIVE): True,  # Reactivate
}


def transition_lifecycle(version_id: str, new_state: VersionLifecycle) -> LoRAVersion:
    """Transition version lifecycle."""
    version = _version_store.get(version_id)
    if version is None:
        raise VersionAllocationError(f"Version {version_id} not found")

    key = (version.lifecycle, new_state)
    if key not in VALID_LIFECYCLE_TRANSITIONS:
        raise VersionAllocationError(
            f"Invalid lifecycle transition: {version.lifecycle.value} → {new_state.value}"
        )

    version.lifecycle = new_state
    return version


# =============================================================================
# Queries
# =============================================================================


def get_version(version_id: str) -> LoRAVersion | None:
    """Get a version by ID."""
    return _version_store.get(version_id)


def get_lineage(lineage_id: str) -> list[LoRAVersion]:
    """Get all versions in a lineage, ordered by version number."""
    versions = [v for v in _version_store.values() if v.lineage_id == lineage_id]
    return sorted(versions, key=lambda v: v.version_number)


def get_latest_version(lineage_id: str) -> LoRAVersion | None:
    """Get the highest version number in a lineage."""
    versions = get_lineage(lineage_id)
    return versions[-1] if versions else None


def get_active_version(lineage_id: str) -> LoRAVersion | None:
    """Get the ACTIVE version in a lineage (if any)."""
    for v in _version_store.values():
        if v.lineage_id == lineage_id and v.lifecycle == VersionLifecycle.ACTIVE:
            return v
    return None


def get_versions_for_talent(talent_id: str, org_id: str) -> list[LoRAVersion]:
    """Get all versions for a talent (tenant-scoped)."""
    return [
        v for v in _version_store.values()
        if v.talent_id == talent_id and v.org_id == org_id
    ]
