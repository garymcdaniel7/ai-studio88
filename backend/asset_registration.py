"""Asset Registration — Story 075.

One authoritative image asset per generation. Retries and duplicate callbacks
do not create duplicate rows or objects.

Identity rule:
    asset_id = f(job_id, output_index)
    NOT f(checksum) — distinct jobs with same bytes get distinct assets.

Storage separation:
    MANAGED  — authoritative asset in B2 under /{org_id}/{type}/{talent_id}/{job_id}/...
    CACHE    — temporary worker/preview files, labeled and cleaned separately

Idempotent finalization:
    finalize_asset(job_id, output_index, ...) is safe to call multiple times.
    First call creates the record; subsequent calls return the existing record unchanged.

Partial failure reconciliation:
    UPLOAD_PENDING  — DB row reserved, storage upload not yet confirmed
    FINALIZED       — Both DB and storage confirmed
    UPLOAD_FAILED   — Upload failed, retryable
    ORPHANED        — Storage object exists but DB row missing (detected by reconciliation)
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Asset States
# =============================================================================


class AssetState(StrEnum):
    RESERVED = "reserved"           # DB row created, no upload yet
    UPLOAD_PENDING = "upload_pending"  # Upload started
    FINALIZED = "finalized"         # Upload confirmed, asset authoritative
    UPLOAD_FAILED = "upload_failed"  # Upload failed, retryable
    ORPHANED = "orphaned"           # Storage exists but DB inconsistent


class StorageClass(StrEnum):
    MANAGED = "managed"     # Authoritative, subject to lifecycle
    CACHE = "cache"         # Temporary, cleaned on schedule
    PREVIEW = "preview"     # Lightweight preview, may be regenerated


# =============================================================================
# Asset Identity
# =============================================================================


def compute_asset_id(job_id: str, output_index: int = 0) -> str:
    """Compute deterministic asset ID from job + output index.

    This ensures the same job/output always maps to the same asset,
    making retries and duplicate callbacks idempotent.

    Identity is based on JOB, not content hash — distinct jobs producing
    identical bytes get distinct assets (correct for billing/lineage).
    """
    raw = f"{job_id}:output:{output_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def compute_storage_key(
    org_id: str,
    asset_type: str,
    job_id: str,
    filename: str,
    talent_id: str | None = None,
) -> str:
    """Compute the canonical managed storage key.

    Format: /{org_id}/{asset_type}/{talent_id or '_'}/{job_id}/{filename}
    """
    talent_segment = talent_id if talent_id else "_"
    return f"/{org_id}/{asset_type}/{talent_segment}/{job_id}/{filename}"


def compute_cache_key(job_id: str, filename: str) -> str:
    """Compute a cache storage key (temporary, cleanable)."""
    return f"/_cache/{job_id}/{filename}"


# =============================================================================
# Registered Asset
# =============================================================================


@dataclass
class RegisteredAsset:
    """One authoritative asset record."""

    asset_id: str
    org_id: str
    job_id: str
    output_index: int = 0
    state: AssetState = AssetState.RESERVED

    # Storage
    storage_key: str = ""
    storage_class: StorageClass = StorageClass.MANAGED
    checksum_sha256: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    width: int | None = None
    height: int | None = None

    # Context
    talent_id: str | None = None
    project_id: str | None = None
    user_id: str = ""

    # Timing
    reserved_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finalized_at: str | None = None
    upload_attempts: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "org_id": self.org_id,
            "job_id": self.job_id,
            "output_index": self.output_index,
            "state": self.state.value,
            "storage_key": self.storage_key,
            "storage_class": self.storage_class.value,
            "checksum_sha256": self.checksum_sha256,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "width": self.width,
            "height": self.height,
            "finalized_at": self.finalized_at,
            "upload_attempts": self.upload_attempts,
        }


# =============================================================================
# Asset Registry (in-memory for contract; production uses Supabase)
# =============================================================================

_registry: dict[str, RegisteredAsset] = {}
_storage_objects: dict[str, bytes] = {}  # Simulated storage


def clear_registry() -> None:
    """Clear registry (testing only)."""
    _registry.clear()
    _storage_objects.clear()


def get_asset(asset_id: str) -> RegisteredAsset | None:
    """Retrieve an asset by ID."""
    return _registry.get(asset_id)


def get_asset_by_job(job_id: str, output_index: int = 0) -> RegisteredAsset | None:
    """Look up asset by job+output (the identity key)."""
    asset_id = compute_asset_id(job_id, output_index)
    return _registry.get(asset_id)


# =============================================================================
# Reserve Asset (pre-upload)
# =============================================================================


def reserve_asset(
    *,
    job_id: str,
    org_id: str,
    output_index: int = 0,
    mime_type: str = "image/webp",
    talent_id: str | None = None,
    project_id: str | None = None,
    user_id: str = "",
) -> RegisteredAsset:
    """Reserve an asset identity before upload begins.

    Idempotent: if already reserved/finalized, returns existing record.
    This prevents duplicate DB rows from retries.
    """
    asset_id = compute_asset_id(job_id, output_index)

    existing = _registry.get(asset_id)
    if existing is not None:
        return existing  # Idempotent — already reserved or finalized

    asset = RegisteredAsset(
        asset_id=asset_id,
        org_id=org_id,
        job_id=job_id,
        output_index=output_index,
        state=AssetState.RESERVED,
        mime_type=mime_type,
        talent_id=talent_id,
        project_id=project_id,
        user_id=user_id,
    )
    _registry[asset_id] = asset
    return asset


# =============================================================================
# Finalize Asset (post-upload, idempotent)
# =============================================================================


class FinalizationError(Exception):
    """Raised when finalization cannot proceed."""

    def __init__(self, message: str, retryable: bool = False):
        self.message = message
        self.retryable = retryable
        super().__init__(message)


def finalize_asset(
    *,
    job_id: str,
    output_index: int = 0,
    org_id: str,
    storage_key: str,
    checksum_sha256: str,
    mime_type: str = "image/webp",
    size_bytes: int = 0,
    width: int | None = None,
    height: int | None = None,
    talent_id: str | None = None,
    project_id: str | None = None,
    user_id: str = "",
    file_bytes: bytes | None = None,
) -> RegisteredAsset:
    """Finalize an asset after successful upload.

    Idempotent: calling multiple times with the same job_id/output_index
    returns the existing finalized record without modification.

    Flow:
    1. Compute deterministic asset_id from job_id + output_index
    2. If already FINALIZED → return existing (idempotent)
    3. If RESERVED/UPLOAD_PENDING/UPLOAD_FAILED → attempt finalization
    4. If not yet reserved → reserve + finalize in one step

    Raises FinalizationError if upload simulation fails.
    """
    asset_id = compute_asset_id(job_id, output_index)
    existing = _registry.get(asset_id)

    # Already finalized — idempotent return
    if existing is not None and existing.state == AssetState.FINALIZED:
        return existing

    # Create or update record
    if existing is None:
        # Auto-reserve if not already done
        existing = RegisteredAsset(
            asset_id=asset_id,
            org_id=org_id,
            job_id=job_id,
            output_index=output_index,
            state=AssetState.UPLOAD_PENDING,
            user_id=user_id,
        )
        _registry[asset_id] = existing

    # Update fields
    existing.state = AssetState.UPLOAD_PENDING
    existing.storage_key = storage_key
    existing.checksum_sha256 = checksum_sha256
    existing.mime_type = mime_type
    existing.size_bytes = size_bytes
    existing.width = width
    existing.height = height
    existing.talent_id = talent_id
    existing.project_id = project_id
    existing.upload_attempts += 1

    # Simulate upload (in production: actual B2 upload)
    if file_bytes is not None:
        _storage_objects[storage_key] = file_bytes

    # Mark finalized
    existing.state = AssetState.FINALIZED
    existing.finalized_at = datetime.now(UTC).isoformat()
    existing.last_error = None

    return existing


def mark_upload_failed(
    job_id: str,
    output_index: int = 0,
    error: str = "",
) -> RegisteredAsset | None:
    """Mark an asset's upload as failed (retryable).

    The asset remains in the registry for retry.
    """
    asset_id = compute_asset_id(job_id, output_index)
    existing = _registry.get(asset_id)
    if existing is None:
        return None

    if existing.state == AssetState.FINALIZED:
        return existing  # Already finalized, ignore failure

    existing.state = AssetState.UPLOAD_FAILED
    existing.last_error = error
    return existing


# =============================================================================
# Retry Upload
# =============================================================================


def retry_upload(
    job_id: str,
    output_index: int = 0,
    *,
    file_bytes: bytes | None = None,
) -> RegisteredAsset | None:
    """Retry a failed upload.

    Only works for UPLOAD_FAILED or UPLOAD_PENDING states.
    Returns None if asset doesn't exist or is already finalized.
    """
    asset_id = compute_asset_id(job_id, output_index)
    existing = _registry.get(asset_id)
    if existing is None:
        return None

    if existing.state == AssetState.FINALIZED:
        return existing  # Already done

    if existing.state not in (AssetState.UPLOAD_FAILED, AssetState.UPLOAD_PENDING):
        return None  # Not in retryable state

    # Re-attempt
    existing.upload_attempts += 1

    if file_bytes is not None and existing.storage_key:
        _storage_objects[existing.storage_key] = file_bytes

    existing.state = AssetState.FINALIZED
    existing.finalized_at = datetime.now(UTC).isoformat()
    existing.last_error = None
    return existing


# =============================================================================
# Reconciliation
# =============================================================================


def reconcile_storage(known_storage_keys: set[str]) -> dict:
    """Reconcile storage objects against registry.

    Detects:
    - ORPHANED: storage key exists but no finalized registry entry
    - MISSING: registry says FINALIZED but storage key not in known set

    Returns summary of discrepancies.
    """
    finalized_keys = {
        a.storage_key for a in _registry.values()
        if a.state == AssetState.FINALIZED and a.storage_key
    }

    orphaned = known_storage_keys - finalized_keys
    missing_from_storage = finalized_keys - known_storage_keys

    return {
        "orphaned_count": len(orphaned),
        "orphaned_keys": list(orphaned)[:20],
        "missing_from_storage_count": len(missing_from_storage),
        "missing_keys": list(missing_from_storage)[:20],
        "total_finalized": len(finalized_keys),
        "total_in_storage": len(known_storage_keys),
    }


# =============================================================================
# Cache Cleanup
# =============================================================================


_cache_entries: dict[str, dict] = {}


def register_cache_file(
    job_id: str,
    filename: str,
    size_bytes: int = 0,
) -> str:
    """Register a temporary cache file for later cleanup.

    Returns the cache key.
    """
    key = compute_cache_key(job_id, filename)
    _cache_entries[key] = {
        "job_id": job_id,
        "filename": filename,
        "size_bytes": size_bytes,
        "created_at": datetime.now(UTC).isoformat(),
        "storage_class": StorageClass.CACHE.value,
    }
    return key


def list_cache_files(job_id: str | None = None) -> list[dict]:
    """List cache files, optionally filtered by job_id."""
    if job_id:
        return [v for v in _cache_entries.values() if v["job_id"] == job_id]
    return list(_cache_entries.values())


def cleanup_cache(job_id: str) -> int:
    """Remove all cache entries for a job. Returns count removed."""
    keys_to_remove = [k for k, v in _cache_entries.items() if v["job_id"] == job_id]
    for k in keys_to_remove:
        del _cache_entries[k]
        _storage_objects.pop(k, None)
    return len(keys_to_remove)


def clear_cache_registry() -> None:
    """Clear cache registry (testing only)."""
    _cache_entries.clear()
