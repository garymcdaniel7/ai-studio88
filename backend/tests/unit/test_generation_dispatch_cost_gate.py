"""Focused tests for the shared legacy/worker generation cost boundary."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend import cost_ledger
from backend.engine.generation_engine import GenerationEngine, get_gpu_status
from backend.engine.models import GenerationOutput, GenerationRequest, GenerationType
from backend.generation_cost_gate import execute_with_cost_gate

pytestmark = pytest.mark.unit

ORG_A = "12345678-1234-5678-1234-567812345678"
ORG_B = "87654321-4321-8765-4321-876543218765"
JOB_ID = "legacy-job-16-3"
SECRET = "b2-application-secret"


@pytest.fixture(autouse=True)
def reset_cost_state() -> None:
    """Keep the in-memory cost ledger isolated per focused test."""
    cost_ledger._reset_store()
    yield
    cost_ledger._reset_store()


def _run_direct_gate(
    org_id: str = ORG_A,
    job_id: str = JOB_ID,
    events: list[str] | None = None,
) -> dict[str, float]:
    """Run a small provider double through the shared direct-dispatch gate."""
    observed = events if events is not None else []

    def provider() -> dict[str, float]:
        observed.append("provider")
        return {"actual_cost_usd": 0.007}

    return execute_with_cost_gate(
        org_id=org_id,
        job_id=job_id,
        operation="generation:image_generation",
        provider="comfyui",
        estimated_cost_usd=0.01,
        execute=provider,
        actual_cost=lambda result, _fallback: result["actual_cost_usd"],
    )


def test_legacy_reservation_happens_before_provider_execution() -> None:
    """The direct path cannot invoke a provider before reserving tenant budget."""
    events: list[str] = []
    real_reserve = cost_ledger.reserve_cost

    def reserve(*args, **kwargs):
        events.append("reserve")
        return real_reserve(*args, **kwargs)

    with patch.object(cost_ledger, "reserve_cost", side_effect=reserve):
        _run_direct_gate(events=events)

    assert events == ["reserve", "provider"]
    assert cost_ledger.get_spend_summary(ORG_A)["daily_spend_usd"] == 0.007
    assert cost_ledger.get_spend_summary(ORG_A)["active_reservations_usd"] == 0.0


def test_legacy_hard_limit_rejects_before_provider_execution() -> None:
    """A tenant hard limit blocks direct dispatch before the provider is called."""
    cost_ledger.set_workspace_limits(
        ORG_A,
        cost_ledger.BudgetLimits(daily_hard_usd=0.001, daily_soft_usd=0.001),
    )
    events: list[str] = []

    with pytest.raises(cost_ledger.BudgetExceededError):
        _run_direct_gate(events=events)

    assert events == []
    assert cost_ledger.get_spend_summary(ORG_A)["active_reservations_usd"] == 0.0


def test_legacy_success_finalizes_actual_cost() -> None:
    """Successful direct dispatch records provider actual cost and clears the hold."""
    result = _run_direct_gate()

    assert result == {"actual_cost_usd": 0.007}
    summary = cost_ledger.get_spend_summary(ORG_A)
    assert summary["daily_spend_usd"] == 0.007
    assert summary["active_reservations_usd"] == 0.0


def test_legacy_provider_failure_releases_reservation() -> None:
    """Provider failure releases the direct path reservation in finally."""

    def provider_failure() -> None:
        raise TimeoutError("provider timed out")

    with pytest.raises(TimeoutError):
        execute_with_cost_gate(
            org_id=ORG_A,
            job_id=JOB_ID,
            operation="generation:image_generation",
            provider="comfyui",
            estimated_cost_usd=0.01,
            execute=provider_failure,
        )

    summary = cost_ledger.get_spend_summary(ORG_A)
    assert summary["daily_spend_usd"] == 0.0
    assert summary["active_reservations_usd"] == 0.0


def test_legacy_cost_gate_is_tenant_isolated() -> None:
    """Tenant A's rejected budget cannot block tenant B's direct generation."""
    cost_ledger.set_workspace_limits(
        ORG_A,
        cost_ledger.BudgetLimits(daily_hard_usd=0.001, daily_soft_usd=0.001),
    )
    cost_ledger.set_workspace_limits(
        ORG_B,
        cost_ledger.BudgetLimits(daily_hard_usd=1.0, daily_soft_usd=0.8),
    )

    with pytest.raises(cost_ledger.BudgetExceededError):
        _run_direct_gate(org_id=ORG_A, job_id="org-a-job")
    _run_direct_gate(org_id=ORG_B, job_id="org-b-job")

    assert cost_ledger.get_spend_summary(ORG_A)["daily_spend_usd"] == 0.0
    assert cost_ledger.get_spend_summary(ORG_B)["daily_spend_usd"] == 0.007


class _ProviderDouble:
    """Provider double returning a safe CDN URL-shaped asset result."""

    def submit(self, request, on_progress=None):
        del request, on_progress
        return GenerationOutput(
            file_bytes=b"image-bytes",
            filename="output.png",
            mime_type="image/png",
            metadata={"provider_job_id": "provider-job"},
        )


def test_legacy_engine_bridge_retains_provenance_and_safe_url() -> None:
    """The bridged engine scopes storage/metadata to trusted org and job context."""
    engine = GenerationEngine(provider_name="simulation")
    engine._provider = _ProviderDouble()
    request = GenerationRequest(
        type=GenerationType.IMAGE,
        prompt="a portrait",
        model="sdxl",
        steps=10,
        workflow_id="workflow-a",
        org_id=ORG_B,
    )
    asset_result = SimpleNamespace(data=[])

    with (
        patch("backend.database.create_asset", return_value=asset_result),
        patch("backend.storage.upload_file", return_value="https://cdn.example/signed/output.png"),
        patch("backend.compliance.output_scan.scan_generated_output"),
    ):
        asset = engine.generate_and_register(
            request,
            ORG_A,
            job_id=JOB_ID,
            estimated_cost_usd=0.01,
        )

    assert asset["metadata"]["org_id"] == ORG_A
    assert asset["metadata"]["job_id"] == JOB_ID
    assert asset["metadata"]["workflow_id"] == "workflow-a"
    assert asset["metadata"]["model_id"] == "sdxl"
    assert asset["storage_key"].startswith(f"{ORG_A}/image/")
    assert asset["public_url"].startswith("https://cdn.example/")
    assert SECRET not in str(asset)
    assert "backblaze" not in asset["public_url"].lower()
    assert cost_ledger.get_spend_summary(ORG_A)["active_reservations_usd"] == 0.0


def test_legacy_engine_failure_resets_gpu_and_releases_cost() -> None:
    """Provider timeout keeps GPU cleanup and cost release guarantees intact."""
    engine = GenerationEngine(provider_name="simulation")

    class FailingProvider(_ProviderDouble):
        def submit(self, request, on_progress=None):
            del request, on_progress
            raise TimeoutError("provider timed out")

    engine._provider = FailingProvider()
    request = GenerationRequest(type=GenerationType.IMAGE, prompt="a portrait")

    with pytest.raises(TimeoutError):
        engine.generate_and_register(request, ORG_A, job_id=JOB_ID, estimated_cost_usd=0.01)

    assert cost_ledger.get_spend_summary(ORG_A)["active_reservations_usd"] == 0.0
    assert get_gpu_status().status == "idle"
