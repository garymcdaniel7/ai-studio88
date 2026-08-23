"""Unit and smoke coverage for local-first AIOS lip-sync and pipeline planning."""

from __future__ import annotations

import pytest

from backend.aios.adapters.lipsync import LipSyncAdapter, LipSyncTier, ShotType
from backend.aios.pipeline import PIPELINE_STAGES, AiosCraftPipeline


class CountingEngine:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, video_url: str, audio_url: str, *, tier: LipSyncTier, profile: dict | None):
        self.calls += 1
        from backend.aios.adapters.lipsync import TimingReport

        return "https://cdn.example.test/output.mp4", TimingReport([0], 0.99, 5.0, tier.value)


@pytest.mark.unit
def test_shot_policy_selects_latentsync_primary_and_musetalk_fast() -> None:
    assert LipSyncAdapter().select_tier(ShotType.CLOSE_UP) == LipSyncTier.LATENTSYNC
    assert LipSyncAdapter(fast_tier=True).select_tier(ShotType.CLOSE_UP) == LipSyncTier.MUSETALK
    assert LipSyncAdapter().select_tier(ShotType.WIDE) == LipSyncTier.LIGHT_PASS
    assert LipSyncAdapter(wide_mode=LipSyncTier.SKIP).select_tier(ShotType.BEHIND) == LipSyncTier.SKIP


@pytest.mark.unit
def test_dry_run_does_not_call_worker() -> None:
    latent = CountingEngine()
    adapter = LipSyncAdapter(latent_sync=latent)
    result = adapter.execute(
        org_id="org-a",
        video_artifact_url="https://cdn.example.test/video.mp4",
        audio_artifact_url="https://cdn.example.test/audio.mp3",
        shot_type=ShotType.CLOSE_UP,
        dry_run=True,
    )
    assert result.status == "planned"
    assert result.dry_run is True
    assert latent.calls == 0


@pytest.mark.unit
@pytest.mark.slow
def test_five_second_fixture_returns_timing_and_artifact_url() -> None:
    result = LipSyncAdapter().execute(
        org_id="org-a",
        video_artifact_url="https://fixtures.example.test/clip-5s.mp4",
        audio_artifact_url="https://fixtures.example.test/dialogue.wav",
        shot_type=ShotType.CLOSE_UP,
    )
    assert result.status == "completed"
    assert result.timing_report.duration_seconds == 5.0
    assert result.timing_report.confidence > 0.9
    assert result.artifact_url.startswith("https://")
    print(f"SMOKE_ARTIFACT_URL={result.artifact_url}")


@pytest.mark.unit
def test_pipeline_plan_has_required_order_and_costs() -> None:
    plan = AiosCraftPipeline().plan(
        org_id="org-a",
        shot_type=ShotType.CLOSE_UP,
        dry_run=True,
        estimated_costs={"wan2.2/klein": 0.12, "lipsync": 0.03},
    )
    assert [stage.name for stage in plan.stages] == list(PIPELINE_STAGES)
    assert plan.dry_run is True
    assert plan.total_estimated_cost_usd == 0.15
    assert plan.stages[4].policy == "latentsync"
