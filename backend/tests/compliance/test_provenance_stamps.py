"""Tests for export-time C2PA-style provenance disclosure metadata."""

from __future__ import annotations

import pytest
from backend.asset_provenance import AssetMediaType, AssetProvenance, stamp_export_metadata


@pytest.mark.unit
def test_exported_asset_carries_provenance_stamp() -> None:
    """Exports include model, timestamp, tenant, and talent attribution."""
    provenance = AssetProvenance(
        asset_id="asset-1",
        org_id="org-1",
        user_id="user-1",
        job_id="job-1",
        media_type=AssetMediaType.IMAGE,
        model_id="flux-dev",
        model_version="1.0",
        talent_id="talent-1",
        created_at="2026-08-21T12:00:00+00:00",
    )

    exported = stamp_export_metadata(provenance, {"mime_type": "image/png"})
    stamp = exported["c2pa"]

    assert exported["mime_type"] == "image/png"
    assert stamp["claim_generator"] == "AI Studio"
    assert stamp["assertions"] == {
        "ai_generated": True,
        "model": "flux-dev",
        "timestamp": "2026-08-21T12:00:00+00:00",
        "org_id": "org-1",
        "talent_id": "talent-1",
    }


@pytest.mark.unit
def test_provenance_to_dict_includes_export_stamp() -> None:
    """The canonical serialized provenance representation is export-ready."""
    provenance = AssetProvenance(
        org_id="org-1",
        user_id="user-1",
        job_id="job-1",
        model_id="sdxl",
        media_type=AssetMediaType.IMAGE,
        width=512,
        height=512,
        storage_key="org-1/images/asset.png",
        checksum_sha256="abc",
        mime_type="image/png",
        size_bytes=3,
    )

    serialized = provenance.to_dict()

    assert serialized["c2pa"]["assertions"]["org_id"] == "org-1"
    assert serialized["c2pa"]["assertions"]["model"] == "sdxl"
