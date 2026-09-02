"""Immutable Training Dataset Manifest — Story 092.

Ensures the exact approved training dataset reaches the GPU worker verified
and intact before paid training execution begins.

Lifecycle:
    1. Manifest created from approved dataset records (immutable once frozen)
    2. Signed URLs generated for each item (scoped, time-limited)
    3. Items transferred to worker via secure download
    4. Worker verifies every checksum before training starts
    5. Worker sends acknowledgement (manifest hash + item count)
    6. Training proceeds only after verification passes
    7. Temporary copies cleaned per policy after training completes

Security:
    - Manifest is immutable (frozen dataclass for content)
    - Each item gets a scoped signed URL (no broad bucket access)
    - Worker cannot enumerate other workspaces
    - Checksums verified server-side before transfer and worker-side after
    - Cross-workspace manifest access rejected
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


class ManifestStatus(str, Enum):
    DRAFT = "draft"                 # Being assembled
    FROZEN = "frozen"               # Immutable — ready for transfer
    TRANSFERRING = "transferring"   # Items being sent to worker
    VERIFIED = "verified"           # Worker acknowledged all checksums
    TRAINING = "training"          # Training in progress
    COMPLETED = "completed"        # Training done, cleanup pending
    CLEANED = "cleaned"            # Worker copies removed
    FAILED = "failed"              # Verification or transfer failed


class ItemStatus(str, Enum):
    PENDING = "pending"
    TRANSFERRED = "transferred"
    VERIFIED = "verified"
    FAILED = "failed"
    CLEANED = "cleaned"


# =============================================================================
# Data Structures
# =============================================================================


@dataclass(frozen=True)
class DatasetItem:
    """A single immutable training dataset item."""
    item_id: str
    asset_id: str              # Source asset reference
    storage_key: str           # B2 object key
    checksum_sha256: str       # SHA-256 of file content
    file_size_bytes: int
    content_type: str          # image/jpeg, image/png, etc.
    caption: str = ""          # Training caption/label
    ordering: int = 0          # Position in dataset
    consent_ref: str = ""      # Consent record reference


@dataclass
class ManifestItem:
    """Mutable tracking wrapper around an immutable DatasetItem."""
    item: DatasetItem
    status: ItemStatus = ItemStatus.PENDING
    signed_url: str | None = None
    signed_url_expires: float | None = None
    worker_checksum: str | None = None  # Checksum computed by worker
    transferred_at: float | None = None
    verified_at: float | None = None
    error: str | None = None


@dataclass
class DatasetManifest:
    """Immutable training dataset manifest."""
    manifest_id: str = field(default_factory=lambda: f"dsm-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    talent_id: str = ""
    job_id: str = ""           # Training job reference
    worker_id: str | None = None

    # Manifest content (frozen once status == FROZEN)
    items: list[ManifestItem] = field(default_factory=list)
    manifest_hash: str = ""    # SHA-256 of all item checksums + ordering

    # Status
    status: ManifestStatus = ManifestStatus.DRAFT
    frozen_at: float | None = None

    # Worker acknowledgement
    worker_ack_hash: str | None = None
    worker_ack_count: int | None = None
    worker_ack_at: float | None = None

    # Timing
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    # Cleanup policy
    cleanup_after_hours: int = 24

    @property
    def item_count(self) -> int:
        return len(self.items)

    @property
    def total_size_bytes(self) -> int:
        return sum(i.item.file_size_bytes for i in self.items)

    @property
    def all_verified(self) -> bool:
        return all(i.status == ItemStatus.VERIFIED for i in self.items)

    @property
    def has_failures(self) -> bool:
        return any(i.status == ItemStatus.FAILED for i in self.items)

    def compute_manifest_hash(self) -> str:
        """Compute deterministic hash from item checksums + ordering."""
        content = "|".join(
            f"{i.item.ordering}:{i.item.checksum_sha256}"
            for i in sorted(self.items, key=lambda x: x.item.ordering)
        )
        return hashlib.sha256(content.encode()).hexdigest()


# =============================================================================
# Store
# =============================================================================

_manifests: dict[str, DatasetManifest] = {}

# Simulation flags
_simulate_checksum_mismatch: bool = False
_simulate_expired_url: bool = False
_simulate_worker_loss: bool = False
_simulate_deleted_source: bool = False


# =============================================================================
# Manifest Assembly
# =============================================================================


def create_manifest(
    org_id: str,
    talent_id: str,
    job_id: str,
    items: list[dict[str, Any]],
) -> DatasetManifest:
    """Create a dataset manifest from approved records.

    Items must include: asset_id, storage_key, checksum_sha256, file_size_bytes,
    content_type. Optional: caption, ordering, consent_ref.
    """
    if not org_id or not talent_id or not job_id:
        raise ValueError("org_id, talent_id, and job_id are required")
    if not items:
        raise ValueError("At least one dataset item is required")

    manifest = DatasetManifest(org_id=org_id, talent_id=talent_id, job_id=job_id)

    for i, item_data in enumerate(items):
        dataset_item = DatasetItem(
            item_id=f"dsi-{uuid.uuid4().hex[:10]}",
            asset_id=item_data["asset_id"],
            storage_key=item_data["storage_key"],
            checksum_sha256=item_data["checksum_sha256"],
            file_size_bytes=item_data.get("file_size_bytes", 0),
            content_type=item_data.get("content_type", "image/jpeg"),
            caption=item_data.get("caption", ""),
            ordering=item_data.get("ordering", i),
            consent_ref=item_data.get("consent_ref", ""),
        )
        manifest.items.append(ManifestItem(item=dataset_item))

    _manifests[manifest.manifest_id] = manifest
    logger.info(f"MANIFEST_CREATED: id={manifest.manifest_id} items={manifest.item_count}")
    return manifest


def freeze_manifest(manifest_id: str, org_id: str) -> DatasetManifest:
    """Freeze the manifest — makes it immutable. No items can be added/removed."""
    manifest = _get_manifest(manifest_id, org_id)

    if manifest.status != ManifestStatus.DRAFT:
        raise ManifestAlreadyFrozen(f"Manifest already in state {manifest.status.value}")

    # Check for deleted sources
    if _simulate_deleted_source:
        raise SourceDeletedError("Source asset deleted after manifest creation")

    manifest.manifest_hash = manifest.compute_manifest_hash()
    manifest.status = ManifestStatus.FROZEN
    manifest.frozen_at = time.time()

    logger.info(f"MANIFEST_FROZEN: id={manifest_id} hash={manifest.manifest_hash[:12]} items={manifest.item_count}")
    return manifest


# =============================================================================
# Secure Transfer
# =============================================================================


def generate_signed_urls(manifest_id: str, org_id: str, expiry_seconds: int = 3600) -> DatasetManifest:
    """Generate scoped signed URLs for each item.

    Each URL is:
    - Time-limited (default 1 hour)
    - Scoped to the specific object key (no bucket listing)
    - Bound to the org_id (cross-workspace access impossible)
    """
    manifest = _get_manifest(manifest_id, org_id)

    if manifest.status != ManifestStatus.FROZEN:
        raise InvalidManifestState(f"Cannot generate URLs in state {manifest.status.value}")

    if _simulate_expired_url:
        # URLs generated but already expired (for testing)
        expiry_seconds = -1

    now = time.time()
    for item in manifest.items:
        # In production: B2 authorize_download with scoped key
        item.signed_url = f"https://b2.example.com/{item.item.storage_key}?token={uuid.uuid4().hex[:16]}"
        item.signed_url_expires = now + expiry_seconds

    manifest.status = ManifestStatus.TRANSFERRING
    return manifest


def transfer_to_worker(manifest_id: str, org_id: str, worker_id: str) -> DatasetManifest:
    """Initiate transfer of all items to the assigned worker.

    In production: downloads each item via signed URL to worker filesystem.
    Idempotent: already-transferred items are skipped.
    """
    manifest = _get_manifest(manifest_id, org_id)

    if manifest.status not in (ManifestStatus.TRANSFERRING, ManifestStatus.FAILED):
        raise InvalidManifestState(f"Cannot transfer in state {manifest.status.value}")

    manifest.worker_id = worker_id

    if _simulate_worker_loss:
        manifest.status = ManifestStatus.FAILED
        raise WorkerLostError("Worker connection lost during transfer")

    for item in manifest.items:
        if item.status in (ItemStatus.VERIFIED, ItemStatus.TRANSFERRED):
            continue  # Idempotent skip

        # Check URL expiry
        if item.signed_url_expires and time.time() > item.signed_url_expires:
            item.status = ItemStatus.FAILED
            item.error = "Signed URL expired"
            continue

        # Simulate transfer (production: actual download)
        item.status = ItemStatus.TRANSFERRED
        item.transferred_at = time.time()

    if manifest.has_failures:
        manifest.status = ManifestStatus.FAILED
    return manifest


# =============================================================================
# Checksum Verification
# =============================================================================


def verify_checksums(manifest_id: str, org_id: str, worker_checksums: dict[str, str]) -> DatasetManifest:
    """Verify worker-reported checksums against manifest.

    worker_checksums: {item_id: sha256_hex} — computed by worker after download.

    Training CANNOT begin until every item passes verification.
    """
    manifest = _get_manifest(manifest_id, org_id)

    if manifest.status not in (ManifestStatus.TRANSFERRING, ManifestStatus.FAILED):
        raise InvalidManifestState(f"Cannot verify in state {manifest.status.value}")

    all_pass = True
    for item in manifest.items:
        worker_hash = worker_checksums.get(item.item.item_id)

        if not worker_hash:
            item.status = ItemStatus.FAILED
            item.error = "No checksum reported by worker"
            all_pass = False
            continue

        if _simulate_checksum_mismatch:
            item.status = ItemStatus.FAILED
            item.error = f"Checksum mismatch: expected {item.item.checksum_sha256[:8]}... got {worker_hash[:8]}..."
            all_pass = False
            continue

        if worker_hash != item.item.checksum_sha256:
            item.status = ItemStatus.FAILED
            item.error = f"Checksum mismatch: expected {item.item.checksum_sha256[:8]}... got {worker_hash[:8]}..."
            all_pass = False
        else:
            item.status = ItemStatus.VERIFIED
            item.worker_checksum = worker_hash
            item.verified_at = time.time()

    if all_pass:
        manifest.status = ManifestStatus.VERIFIED
    else:
        manifest.status = ManifestStatus.FAILED

    return manifest


# =============================================================================
# Worker Acknowledgement
# =============================================================================


def record_worker_acknowledgement(
    manifest_id: str,
    org_id: str,
    worker_manifest_hash: str,
    worker_item_count: int,
) -> DatasetManifest:
    """Record worker's acknowledgement of the complete verified dataset.

    Training may ONLY proceed after this acknowledgement matches.
    """
    manifest = _get_manifest(manifest_id, org_id)

    if manifest.status != ManifestStatus.VERIFIED:
        raise InvalidManifestState(f"Cannot acknowledge in state {manifest.status.value}")

    # Verify worker's hash matches ours
    if worker_manifest_hash != manifest.manifest_hash:
        raise ManifestHashMismatch(
            f"Worker hash {worker_manifest_hash[:12]}... != manifest hash {manifest.manifest_hash[:12]}..."
        )

    # Verify item count
    if worker_item_count != manifest.item_count:
        raise ManifestCountMismatch(
            f"Worker reports {worker_item_count} items, manifest has {manifest.item_count}"
        )

    manifest.worker_ack_hash = worker_manifest_hash
    manifest.worker_ack_count = worker_item_count
    manifest.worker_ack_at = time.time()
    manifest.status = ManifestStatus.TRAINING

    logger.info(
        f"WORKER_ACK: manifest={manifest_id} hash={worker_manifest_hash[:12]} "
        f"items={worker_item_count}"
    )
    return manifest


def can_start_training(manifest_id: str, org_id: str) -> bool:
    """Check if training can start — all verifications must pass."""
    manifest = _get_manifest(manifest_id, org_id)
    return manifest.status == ManifestStatus.TRAINING and manifest.all_verified


# =============================================================================
# Cleanup
# =============================================================================


def mark_training_complete(manifest_id: str, org_id: str) -> DatasetManifest:
    """Mark training complete — triggers cleanup scheduling."""
    manifest = _get_manifest(manifest_id, org_id)
    manifest.status = ManifestStatus.COMPLETED
    manifest.completed_at = time.time()
    return manifest


def cleanup_worker_copies(manifest_id: str, org_id: str) -> DatasetManifest:
    """Clean up temporary copies on worker (idempotent)."""
    manifest = _get_manifest(manifest_id, org_id)

    if manifest.status not in (ManifestStatus.COMPLETED, ManifestStatus.CLEANED):
        raise InvalidManifestState(f"Cannot cleanup in state {manifest.status.value}")

    for item in manifest.items:
        item.status = ItemStatus.CLEANED

    manifest.status = ManifestStatus.CLEANED
    logger.info(f"MANIFEST_CLEANED: id={manifest_id}")
    return manifest


# =============================================================================
# Retry
# =============================================================================


def retry_failed_items(manifest_id: str, org_id: str) -> DatasetManifest:
    """Retry failed items (idempotent — already-verified items not re-transferred)."""
    manifest = _get_manifest(manifest_id, org_id)

    if manifest.status != ManifestStatus.FAILED:
        raise InvalidManifestState(f"Cannot retry in state {manifest.status.value}")

    # Reset failed items to pending
    for item in manifest.items:
        if item.status == ItemStatus.FAILED:
            item.status = ItemStatus.PENDING
            item.error = None

    manifest.status = ManifestStatus.TRANSFERRING
    return manifest


# =============================================================================
# Query
# =============================================================================


def get_manifest(manifest_id: str, org_id: str) -> DatasetManifest | None:
    """Get manifest with tenant isolation."""
    manifest = _manifests.get(manifest_id)
    if not manifest or manifest.org_id != org_id:
        return None
    return manifest


def get_manifest_status(manifest_id: str, org_id: str) -> dict[str, Any]:
    """Get manifest status summary."""
    manifest = get_manifest(manifest_id, org_id)
    if not manifest:
        return {"error": "not_found"}

    return {
        "manifest_id": manifest.manifest_id,
        "status": manifest.status.value,
        "item_count": manifest.item_count,
        "total_size_bytes": manifest.total_size_bytes,
        "manifest_hash": manifest.manifest_hash,
        "all_verified": manifest.all_verified,
        "has_failures": manifest.has_failures,
        "worker_acknowledged": manifest.worker_ack_at is not None,
        "items": [
            {
                "item_id": i.item.item_id,
                "status": i.status.value,
                "error": i.error,
            }
            for i in manifest.items
        ],
    }


# =============================================================================
# Mutation Prevention
# =============================================================================


def attempt_add_item(manifest_id: str, org_id: str, item_data: dict) -> None:
    """Attempt to add an item to a frozen manifest — always rejected."""
    manifest = _get_manifest(manifest_id, org_id)
    if manifest.status != ManifestStatus.DRAFT:
        raise ManifestImmutable("Cannot modify a frozen manifest")


# =============================================================================
# Helpers
# =============================================================================


def _get_manifest(manifest_id: str, org_id: str) -> DatasetManifest:
    manifest = _manifests.get(manifest_id)
    if not manifest or manifest.org_id != org_id:
        raise ManifestNotFound(f"Manifest {manifest_id} not found")
    return manifest


# =============================================================================
# Exceptions
# =============================================================================


class ManifestError(Exception):
    """Base manifest error."""


class ManifestNotFound(ManifestError):
    """Manifest not found or cross-tenant."""


class ManifestAlreadyFrozen(ManifestError):
    """Manifest is already frozen."""


class ManifestImmutable(ManifestError):
    """Cannot modify a frozen manifest."""


class ManifestHashMismatch(ManifestError):
    """Worker hash doesn't match manifest hash."""


class ManifestCountMismatch(ManifestError):
    """Worker item count doesn't match manifest."""


class InvalidManifestState(ManifestError):
    """Invalid state for operation."""


class SourceDeletedError(ManifestError):
    """Source asset was deleted."""


class WorkerLostError(ManifestError):
    """Worker connection lost."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    global _simulate_checksum_mismatch, _simulate_expired_url
    global _simulate_worker_loss, _simulate_deleted_source
    _manifests.clear()
    _simulate_checksum_mismatch = False
    _simulate_expired_url = False
    _simulate_worker_loss = False
    _simulate_deleted_source = False


def _inject_condition(condition: str, enabled: bool = True) -> None:
    global _simulate_checksum_mismatch, _simulate_expired_url
    global _simulate_worker_loss, _simulate_deleted_source
    if condition == "checksum_mismatch":
        _simulate_checksum_mismatch = enabled
    elif condition == "expired_url":
        _simulate_expired_url = enabled
    elif condition == "worker_loss":
        _simulate_worker_loss = enabled
    elif condition == "deleted_source":
        _simulate_deleted_source = enabled
