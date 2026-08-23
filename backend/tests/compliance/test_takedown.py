"""Staging-clock and pHash copy-sweep tests for NCII takedowns."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from backend.compliance.quarantine import clear_quarantine, is_asset_quarantined
from backend.compliance.takedown import (
    TAKEDOWN_ESCALATION_HOURS,
    TAKEDOWN_SLA_HOURS,
    TakedownService,
)


@pytest.fixture(autouse=True)
def _clean_quarantine() -> None:
    """Isolate the shared quarantine index between clock tests."""
    clear_quarantine()
    yield
    clear_quarantine()


@pytest.mark.unit
def test_takedown_copy_sweep_completes_before_48_hour_sla() -> None:
    """A simulated request removes identical copies inside the statutory window."""
    service = TakedownService()
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
    completed = service.process(
        case.id,
        now=received_at + timedelta(hours=1),
    )

    assert TAKEDOWN_SLA_HOURS == 48
    assert completed.status == "removed"
    assert completed.sla_breached is False
    assert completed.removed_at is not None
    assert set(completed.affected_asset_ids) == {"asset-1", "asset-2"}
    assert is_asset_quarantined("asset-1", "org-1")
    assert is_asset_quarantined("asset-2", "org-2")


@pytest.mark.unit
def test_unprocessed_case_escalates_at_24_hours() -> None:
    """The SLA monitor marks an open case escalated at the 24-hour clock."""
    service = TakedownService()
    received_at = datetime(2026, 8, 21, 12, tzinfo=UTC)
    case = service.submit(
        asset_id="asset-1",
        claimant_email="claimant@example.com",
        reason="privacy violation",
        org_id="org-1",
        actor_user_id="user-1",
        now=received_at,
    )

    escalated = service.run_sla_monitor(
        now=received_at + timedelta(hours=TAKEDOWN_ESCALATION_HOURS),
    )

    assert escalated == [case]
    assert case.status == "escalated"
    assert case.escalated_at == received_at + timedelta(hours=24)
