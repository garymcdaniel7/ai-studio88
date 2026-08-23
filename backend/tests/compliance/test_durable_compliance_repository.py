"""Tests for durable compliance repository seams and tenant isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from backend.compliance.fake_repository import InMemoryComplianceRepository
from backend.compliance.output_scan import scan_generated_output
from backend.compliance.quarantine import (
    clear_quarantine,
    is_asset_quarantined,
    quarantine_asset,
    set_compliance_repository,
)
from backend.compliance.takedown import TakedownService


@pytest.fixture
def repository() -> InMemoryComplianceRepository:
    """Inject an isolated fake repository for unit tests."""
    fake = InMemoryComplianceRepository()
    set_compliance_repository(fake)
    yield fake
    clear_quarantine()
    set_compliance_repository(None)


@pytest.mark.unit
def test_quarantine_lookup_is_durable_and_tenant_scoped(
    repository: InMemoryComplianceRepository,
) -> None:
    """A stored quarantine survives service boundaries without crossing tenants."""
    quarantine_asset("asset-1", "org-1", reason="policy", repository=repository)

    assert is_asset_quarantined("asset-1", "org-1") is True
    assert is_asset_quarantined("asset-1", "org-2") is False
    assert len(repository.list_quarantines()) == 1


@pytest.mark.unit
def test_takedown_persists_case_and_sweeps_durable_hash_index(
    repository: InMemoryComplianceRepository,
) -> None:
    """A takedown stores its SLA state and sweeps identical cross-tenant copies."""
    service = TakedownService(repository=repository)
    received_at = datetime(2026, 8, 21, 12, tzinfo=UTC)
    service.register_asset("asset-1", "org-1", b"same-content")
    service.register_asset("asset-2", "org-2", b"same-content")

    case = service.submit(
        asset_id="asset-1",
        claimant_email="claimant@example.com",
        reason="non-consensual intimate image",
        org_id="org-1",
        actor_user_id="user-1",
        now=received_at,
    )
    completed = service.process(case.id, now=received_at + timedelta(hours=1))
    persisted = repository.get_case(case.id)

    assert persisted is not None
    assert persisted["sla_started_at"] == received_at
    assert completed.status == "removed"
    assert set(completed.affected_asset_ids) == {"asset-1", "asset-2"}
    assert repository.get_quarantine("asset-2", "org-2") is not None


@pytest.mark.unit
def test_safe_output_with_asset_id_registers_its_hash(
    repository: InMemoryComplianceRepository,
) -> None:
    """Known safe assets become discoverable by later compliance copy sweeps."""
    result = scan_generated_output(
        b"safe-content",
        asset_id="asset-3",
        org_id="org-3",
        metadata={"nsfw_score": 0.01},
    )

    indexed = repository.get_asset_index("asset-3", "org-3")
    assert indexed is not None
    assert indexed["phash"] == result.perceptual_hash
    assert indexed["is_quarantined"] is False
