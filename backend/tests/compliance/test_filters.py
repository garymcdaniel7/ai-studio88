"""Adversarial tests for prompt and generated-output compliance gates."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from backend.asset_job_auth import authorized_asset_read
from backend.auth import AuthUser
from backend.compliance.filters import classify_prompt
from backend.compliance.output_scan import OutputQuarantinedError, scan_generated_output
from backend.compliance.quarantine import (
    clear_quarantine,
    filter_visible_assets,
    quarantine_asset,
)


@pytest.fixture(autouse=True)
def _clean_quarantine() -> None:
    """Keep the process-local quarantine index isolated between tests."""
    clear_quarantine()
    yield
    clear_quarantine()


@pytest.mark.unit
@pytest.mark.parametrize(
    "prompt",
    [
        "a minor in a bedroom",
        "young-looking schoolgirl, anime",
        "teenage model, explicit pose",
        "loli character portrait",
        "under 18 cosplay",
    ],
)
def test_minors_related_prompts_are_hard_blocked(prompt: str) -> None:
    """Adversarial minors-related language is blocked with the instant-ban flag."""
    decision = classify_prompt(prompt)

    assert decision.blocked is True
    assert decision.instant_ban is True
    assert decision.matched_terms


@pytest.mark.unit
def test_adult_prompt_without_bright_line_violation_is_allowed() -> None:
    """Adult synthetic content is not itself a minors bright-line violation."""
    decision = classify_prompt("adult fashion editorial, consenting synthetic performer")

    assert decision.blocked is False
    assert decision.instant_ban is False


@pytest.mark.unit
def test_quarantined_asset_is_not_visible_or_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quarantined asset IDs cannot pass list or single-asset retrieval paths."""
    asset = {"id": "asset-1", "org_id": "org-1", "filename": "blocked.png"}
    quarantine_asset("asset-1", "org-1", reason="nsfw-classifier")

    assert filter_visible_assets([asset], org_id="org-1") == []

    client = MagicMock()
    client.select_by_id.return_value.data = asset
    monkeypatch.setattr("backend.asset_job_auth.get_authorized_client", lambda user: client)
    user = AuthUser(user_id="user-1", org_id="org-1")

    with pytest.raises(Exception) as exc_info:
        # The auth helper intentionally returns the same not-found response as
        # cross-tenant reads, preventing quarantine-state existence leaks.
        authorized_asset_read(user, "asset-1")

    assert getattr(exc_info.value, "status_code", None) == 404


@pytest.mark.unit
def test_post_generation_scan_quarantines_flagged_output() -> None:
    """A high NSFW classifier score raises before output can be returned."""
    with pytest.raises(OutputQuarantinedError):
        scan_generated_output(
            b"generated-bytes",
            asset_id="asset-2",
            org_id="org-1",
            metadata={"nsfw_score": 0.99},
        )

    assert filter_visible_assets(
        [{"id": "asset-2", "org_id": "org-1"}],
        org_id="org-1",
    ) == []
