"""Durable quarantine gates used by compliance and tenant asset retrieval."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.compliance.repository import (
    ComplianceRepository,
    get_compliance_repository,
)
from backend.compliance.repository import set_compliance_repository as _set_compliance_repository


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


def set_compliance_repository(repository: ComplianceRepository | None) -> None:
    """Inject a repository adapter, primarily for isolated tests."""
    _set_compliance_repository(repository)


def _record_from_row(row: dict[str, Any]) -> QuarantineRecord:
    """Hydrate the public record shape from a repository row."""
    created_at = row.get("created_at", datetime.now(UTC).isoformat())
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return QuarantineRecord(
        id=str(row["id"]),
        org_id=str(row["org_id"]),
        reason=str(row.get("reason") or "unspecified"),
        asset_id=str(row["asset_id"]) if row.get("asset_id") is not None else None,
        source_type=str(row.get("source_type") or "asset"),
        matched_terms=tuple(row.get("matched_terms") or ()),
        perceptual_hash=row.get("phash") or row.get("perceptual_hash"),
        created_at=str(created_at),
    )


def record_violation(
    *,
    org_id: str,
    reason: str,
    source_type: str,
    asset_id: str | None = None,
    matched_terms: tuple[str, ...] = (),
    perceptual_hash: str | None = None,
    repository: ComplianceRepository | None = None,
) -> QuarantineRecord:
    """Persist a compliance violation through the durable repository."""
    store = repository or get_compliance_repository()
    row = store.record_quarantine(
        org_id=org_id,
        asset_id=asset_id,
        reason=reason,
        source_type=source_type,
        matched_terms=matched_terms,
        phash=perceptual_hash,
    )
    return _record_from_row(row)


def quarantine_asset(
    asset_id: str,
    org_id: str,
    *,
    reason: str,
    perceptual_hash: str | None = None,
    repository: ComplianceRepository | None = None,
) -> QuarantineRecord:
    """Mark an asset unavailable to clients while preserving evidence durably."""
    store = repository or get_compliance_repository()
    existing = store.get_quarantine(asset_id, org_id)
    if existing is not None:
        return _record_from_row(existing)
    return record_violation(
        org_id=org_id,
        reason=reason,
        source_type="asset",
        asset_id=asset_id,
        perceptual_hash=perceptual_hash,
        repository=store,
    )


def is_asset_quarantined(asset_id: str, org_id: str | None = None) -> bool:
    """Return quarantine state only for an explicitly supplied tenant."""
    if org_id is None:
        return False
    return get_compliance_repository().get_quarantine(asset_id, org_id) is not None


def filter_visible_assets(assets: list[dict[str, Any]], *, org_id: str) -> list[dict[str, Any]]:
    """Remove quarantined records from an already tenant-scoped result."""
    return [
        asset
        for asset in assets
        if not is_asset_quarantined(str(asset.get("id", "")), org_id)
        and asset.get("compliance_status") != "quarantined"
    ]


def get_quarantine_log() -> list[QuarantineRecord]:
    """Return a stable snapshot of persisted quarantine evidence."""
    return [_record_from_row(row) for row in get_compliance_repository().list_quarantines()]


def compute_perceptual_hash(content: bytes) -> str:
    """Compute a deterministic pHash-compatible content fingerprint."""
    return hashlib.sha256(content).hexdigest()[:32]


def clear_quarantine() -> None:
    """Reset only an injected test repository; production state is never deleted here."""
    repository = get_compliance_repository()
    clear_for_tests = getattr(repository, "clear_for_tests", None)
    if clear_for_tests is not None:
        clear_for_tests()
