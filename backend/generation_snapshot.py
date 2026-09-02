"""Immutable Generation Snapshots — Story 086.

Every executed generation references one immutable snapshot that captures
the exact context, prompts, model versions, and provenance used. This
snapshot cannot be changed after creation — mutable source edits do not
retroactively alter historical generation records.

Design:
    - Snapshot is frozen at execution time (dataclass frozen=True for content)
    - Content hash (SHA-256) provides integrity verification
    - Job and asset both reference the same snapshot_id
    - Remix reads from snapshot (not current mutable records)
    - Persistence failure tracked with repair state
    - Legacy assets without snapshots get a "legacy_unknown" marker

Snapshot content:
    - Effective positive/negative prompts
    - All resolved source record IDs and versions
    - Creative DNA version used
    - Model ID + version, LoRA IDs + versions + strengths
    - Workflow, recipe, talent, project references
    - Provider, seed, dimensions, steps, cfg
    - Context package ID + hash
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class SnapshotStatus(str, Enum):
    PERSISTED = "persisted"           # Successfully saved
    FAILED = "failed"                 # Persistence failed (retryable)
    LEGACY_UNKNOWN = "legacy_unknown" # Pre-snapshot asset (no data)


class RemixMode(str, Enum):
    EXACT = "exact"                   # Use snapshot values exactly
    RESET = "reset"                   # Explicit reset — use current sources


# =============================================================================
# Immutable Snapshot Content
# =============================================================================


@dataclass(frozen=True)
class SnapshotContent:
    """Immutable content captured at generation time.

    frozen=True enforces immutability — any attempt to modify raises.
    """
    # Prompts (effective, after all enrichment/resolution)
    effective_prompt: str = ""
    effective_negative_prompt: str = ""
    original_prompt: str = ""  # What user typed before enrichment

    # Model
    model_id: str = ""
    model_version: str = ""

    # LoRA
    lora_ids: tuple[str, ...] = ()
    lora_versions: tuple[str, ...] = ()
    lora_strengths: tuple[float, ...] = ()

    # Generation params (actual values used)
    seed: int = 0
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg: float = 7.0
    guidance: float | None = None

    # Creative DNA
    creative_dna_version_id: str = ""

    # Context package
    context_package_id: str = ""
    context_package_hash: str = ""

    # References (IDs + versions at execution time)
    talent_id: str = ""
    talent_version: str = ""
    workflow_id: str = ""
    recipe_id: str = ""
    project_id: str = ""

    # Provider
    provider: str = ""
    gpu_type: str = ""

    # Source versions snapshot (all sources that contributed)
    source_versions: tuple[tuple[str, str], ...] = ()  # ((source_id, version), ...)

    def compute_hash(self) -> str:
        """Compute deterministic SHA-256 hash of snapshot content."""
        # Serialize deterministically (sorted keys)
        content_dict = asdict(self)
        serialized = json.dumps(content_dict, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()


# =============================================================================
# Snapshot Record
# =============================================================================


@dataclass
class GenerationSnapshot:
    """A generation snapshot linking job, asset, and immutable content."""
    snapshot_id: str = field(default_factory=lambda: f"snap-{uuid.uuid4().hex[:12]}")
    org_id: str = ""

    # Linkage
    job_id: str = ""
    asset_id: str | None = None  # Set when asset is registered

    # Immutable content
    content: SnapshotContent = field(default_factory=SnapshotContent)
    content_hash: str = ""  # SHA-256 of content

    # Status
    status: SnapshotStatus = SnapshotStatus.PERSISTED
    error: str | None = None

    # Remix lineage
    remixed_from_snapshot_id: str | None = None  # If this was a remix
    remix_mode: RemixMode | None = None

    # Timing
    created_at: float = field(default_factory=time.time)

    @property
    def is_valid(self) -> bool:
        """Snapshot is valid if persisted and hash matches."""
        return (
            self.status == SnapshotStatus.PERSISTED
            and self.content_hash == self.content.compute_hash()
        )


# =============================================================================
# Store
# =============================================================================

_snapshots: dict[str, GenerationSnapshot] = {}  # snapshot_id → snapshot
_job_index: dict[str, str] = {}                  # job_id → snapshot_id
_asset_index: dict[str, str] = {}                # asset_id → snapshot_id


# =============================================================================
# Snapshot Creation
# =============================================================================


def create_snapshot(
    org_id: str,
    job_id: str,
    content: SnapshotContent,
    remixed_from: str | None = None,
    remix_mode: RemixMode | None = None,
) -> GenerationSnapshot:
    """Create an immutable snapshot for a generation job.

    Called at execution time — captures the exact state used.
    Content is frozen and cannot be modified after creation.
    """
    if not org_id or not job_id:
        raise ValueError("org_id and job_id are required")

    # Idempotent: if snapshot already exists for this job, return it
    if job_id in _job_index:
        existing = _snapshots.get(_job_index[job_id])
        if existing:
            return existing

    content_hash = content.compute_hash()

    snapshot = GenerationSnapshot(
        org_id=org_id,
        job_id=job_id,
        content=content,
        content_hash=content_hash,
        remixed_from_snapshot_id=remixed_from,
        remix_mode=remix_mode,
    )

    _snapshots[snapshot.snapshot_id] = snapshot
    _job_index[job_id] = snapshot.snapshot_id

    logger.info(
        f"SNAPSHOT_CREATED: id={snapshot.snapshot_id} job={job_id} "
        f"hash={content_hash[:12]} model={content.model_id}"
    )
    return snapshot


def link_asset_to_snapshot(snapshot_id: str, asset_id: str, org_id: str) -> GenerationSnapshot:
    """Link a completed asset to its generation snapshot."""
    snapshot = _snapshots.get(snapshot_id)
    if not snapshot:
        raise SnapshotNotFound(f"Snapshot {snapshot_id} not found")
    if snapshot.org_id != org_id:
        raise SnapshotAccessDenied("Cross-workspace snapshot access denied")

    snapshot.asset_id = asset_id
    _asset_index[asset_id] = snapshot_id
    return snapshot


def mark_snapshot_failed(job_id: str, error: str) -> GenerationSnapshot | None:
    """Mark a snapshot as failed to persist (for repair tracking)."""
    snapshot_id = _job_index.get(job_id)
    if not snapshot_id:
        return None
    snapshot = _snapshots.get(snapshot_id)
    if snapshot:
        snapshot.status = SnapshotStatus.FAILED
        snapshot.error = error[:500]
    return snapshot


# =============================================================================
# Retrieval (reads immutable snapshot, NOT current mutable data)
# =============================================================================


def get_snapshot_by_job(job_id: str, org_id: str) -> GenerationSnapshot | None:
    """Get the snapshot for a job — tenant-isolated."""
    snapshot_id = _job_index.get(job_id)
    if not snapshot_id:
        return None
    snapshot = _snapshots.get(snapshot_id)
    if not snapshot or snapshot.org_id != org_id:
        return None
    return snapshot


def get_snapshot_by_asset(asset_id: str, org_id: str) -> GenerationSnapshot | None:
    """Get the snapshot for an asset — tenant-isolated."""
    snapshot_id = _asset_index.get(asset_id)
    if not snapshot_id:
        return None
    snapshot = _snapshots.get(snapshot_id)
    if not snapshot or snapshot.org_id != org_id:
        return None
    return snapshot


def get_snapshot_by_id(snapshot_id: str, org_id: str) -> GenerationSnapshot | None:
    """Get a snapshot by direct ID — tenant-isolated."""
    snapshot = _snapshots.get(snapshot_id)
    if not snapshot or snapshot.org_id != org_id:
        return None
    return snapshot


# =============================================================================
# Remix Support
# =============================================================================


def prepare_remix(
    source_snapshot_id: str,
    org_id: str,
    mode: RemixMode = RemixMode.EXACT,
) -> dict[str, Any]:
    """Prepare remix parameters from a historical snapshot.

    EXACT mode: returns the exact values from the snapshot
    RESET mode: returns a marker indicating current sources should be used

    The key guarantee: remix reads from the IMMUTABLE snapshot,
    not from current mutable talent/DNA/model records.
    """
    snapshot = get_snapshot_by_id(source_snapshot_id, org_id)
    if not snapshot:
        raise SnapshotNotFound("Source snapshot not found for remix")

    if mode == RemixMode.RESET:
        return {
            "remix_mode": "reset",
            "source_snapshot_id": source_snapshot_id,
            "note": "Using current source values — explicit reset from historical snapshot",
        }

    # EXACT mode — return snapshot values for re-use
    content = snapshot.content
    return {
        "remix_mode": "exact",
        "source_snapshot_id": source_snapshot_id,
        "effective_prompt": content.effective_prompt,
        "effective_negative_prompt": content.effective_negative_prompt,
        "model_id": content.model_id,
        "model_version": content.model_version,
        "lora_ids": list(content.lora_ids),
        "lora_versions": list(content.lora_versions),
        "lora_strengths": list(content.lora_strengths),
        "seed": content.seed,
        "width": content.width,
        "height": content.height,
        "steps": content.steps,
        "cfg": content.cfg,
        "talent_id": content.talent_id,
        "creative_dna_version_id": content.creative_dna_version_id,
        "workflow_id": content.workflow_id,
        "recipe_id": content.recipe_id,
    }


# =============================================================================
# Integrity Verification
# =============================================================================


def verify_snapshot_integrity(snapshot_id: str, org_id: str) -> dict[str, Any]:
    """Verify a snapshot's hash integrity."""
    snapshot = get_snapshot_by_id(snapshot_id, org_id)
    if not snapshot:
        return {"valid": False, "reason": "not_found"}

    computed = snapshot.content.compute_hash()
    matches = computed == snapshot.content_hash

    return {
        "valid": matches,
        "snapshot_id": snapshot_id,
        "stored_hash": snapshot.content_hash,
        "computed_hash": computed,
        "status": snapshot.status.value,
    }


# =============================================================================
# Legacy Backfill
# =============================================================================


def create_legacy_marker(asset_id: str, org_id: str) -> GenerationSnapshot:
    """Create a legacy_unknown marker for pre-snapshot assets.

    These assets were created before the snapshot system existed.
    The marker makes their status explicit rather than ambiguous.
    """
    snapshot = GenerationSnapshot(
        org_id=org_id,
        job_id=f"legacy-{asset_id}",
        asset_id=asset_id,
        content=SnapshotContent(),  # Empty — no data available
        content_hash="legacy_unknown",
        status=SnapshotStatus.LEGACY_UNKNOWN,
    )

    _snapshots[snapshot.snapshot_id] = snapshot
    _asset_index[asset_id] = snapshot.snapshot_id

    return snapshot


# =============================================================================
# Listing / Query
# =============================================================================


def list_failed_snapshots(org_id: str) -> list[GenerationSnapshot]:
    """List snapshots with failed persistence — for ops repair dashboard."""
    return [
        s for s in _snapshots.values()
        if s.org_id == org_id and s.status == SnapshotStatus.FAILED
    ]


# =============================================================================
# Exceptions
# =============================================================================


class SnapshotError(Exception):
    """Base snapshot error."""


class SnapshotNotFound(SnapshotError):
    """Snapshot not found."""


class SnapshotAccessDenied(SnapshotError):
    """Cross-workspace access denied."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _snapshots.clear()
    _job_index.clear()
    _asset_index.clear()
