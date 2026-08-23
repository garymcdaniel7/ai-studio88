"""Append-oriented quarantine index used by compliance gates and retrieval."""

from __future__ import annotations

import hashlib
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    """Immutable record describing why a prompt or asset was quarantined."""

    id: str
    org_id: str
    reason: str
    asset_id: str | None = None
    source_type: str = "asset"
    matched_terms: tuple[str, ...] = ()
    perceptual_hash: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


_quarantine_log: list[QuarantineRecord] = []
_quarantined_assets: dict[tuple[str, str], QuarantineRecord] = {}
_lock = threading.RLock()


def record_violation(
    *,
    org_id: str,
    reason: str,
    source_type: str,
    asset_id: str | None = None,
    matched_terms: tuple[str, ...] = (),
    perceptual_hash: str | None = None,
) -> QuarantineRecord:
    """Append a compliance violation to the process-local quarantine log."""
    record = QuarantineRecord(
        id=str(uuid.uuid4()),
        org_id=org_id,
        reason=reason,
        source_type=source_type,
        asset_id=asset_id,
        matched_terms=matched_terms,
        perceptual_hash=perceptual_hash,
    )
    with _lock:
        _quarantine_log.append(record)
        if asset_id is not None:
            _quarantined_assets[(org_id, asset_id)] = record
    return record


def quarantine_asset(
    asset_id: str,
    org_id: str,
    *,
    reason: str,
    perceptual_hash: str | None = None,
) -> QuarantineRecord:
    """Mark an asset unavailable to clients while preserving evidence."""
    with _lock:
        existing = _quarantined_assets.get((org_id, asset_id))
        if existing is not None:
            return existing
    return record_violation(
        org_id=org_id,
        reason=reason,
        source_type="asset",
        asset_id=asset_id,
        perceptual_hash=perceptual_hash,
    )


def is_asset_quarantined(asset_id: str, org_id: str | None = None) -> bool:
    """Return whether an asset is quarantined for the requested tenant."""
    with _lock:
        if org_id is not None:
            return (org_id, asset_id) in _quarantined_assets
        return any(key[1] == asset_id for key in _quarantined_assets)


def filter_visible_assets(assets: list[dict[str, Any]], *, org_id: str) -> list[dict[str, Any]]:
    """Remove quarantined records from a tenant-scoped asset result."""
    return [
        asset
        for asset in assets
        if not is_asset_quarantined(str(asset.get("id", "")), org_id)
        and asset.get("compliance_status") != "quarantined"
    ]


def get_quarantine_log() -> list[QuarantineRecord]:
    """Return a stable snapshot of the append-only quarantine log."""
    with _lock:
        return list(_quarantine_log)


def compute_perceptual_hash(content: bytes) -> str:
    """Compute a deterministic pHash-compatible content fingerprint.

    Image-aware average hashing can be added behind this seam; the SHA-256
    fallback keeps arbitrary generated media indexable and deterministic in
    environments without an image decoder.
    """
    return hashlib.sha256(content).hexdigest()[:32]


def clear_quarantine() -> None:
    """Clear the process-local index for isolated tests."""
    with _lock:
        _quarantine_log.clear()
        _quarantined_assets.clear()
