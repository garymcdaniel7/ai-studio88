"""AIOS studio craft pipeline planning and dry-run execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.aios.adapters.lipsync import LipSyncAdapter, ShotType
from backend.tenant_context import validate_org_id

PIPELINE_STAGES = ("script", "cast", "tts", "wan2.2/klein", "lipsync", "mux", "compliance", "deliver")


@dataclass(frozen=True)
class PipelineStage:
    """One ordered production stage and its policy status."""

    name: str
    status: str = "planned"
    estimated_cost_usd: float = 0.0
    policy: str = "approved"

    def to_dict(self) -> dict[str, Any]:
        """Serialize one stage."""
        return self.__dict__.copy()


@dataclass(frozen=True)
class PipelinePlan:
    """Ordered plan returned before any side effect."""

    org_id: str
    stages: tuple[PipelineStage, ...]
    dry_run: bool
    total_estimated_cost_usd: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize a complete plan."""
        return {
            "org_id": self.org_id,
            "stages": [stage.to_dict() for stage in self.stages],
            "dry_run": self.dry_run,
            "total_estimated_cost_usd": self.total_estimated_cost_usd,
        }


class AiosCraftPipeline:
    """Decision flow for script through compliant delivery."""

    def __init__(self, lipsync: LipSyncAdapter | None = None) -> None:
        self.lipsync = lipsync or LipSyncAdapter()

    def plan(
        self,
        *,
        org_id: str,
        shot_type: ShotType,
        dry_run: bool = True,
        estimated_costs: dict[str, float] | None = None,
    ) -> PipelinePlan:
        """Return the complete ordered flow without executing providers."""
        org_id = validate_org_id(org_id)
        costs = estimated_costs or {}
        lip_policy = self.lipsync.select_tier(shot_type).value
        stages = tuple(
            PipelineStage(
                name=name,
                status="planned" if dry_run else "ready",
                estimated_cost_usd=float(costs.get(name, 0.0)),
                policy=lip_policy if name == "lipsync" else "approved",
            )
            for name in PIPELINE_STAGES
        )
        return PipelinePlan(org_id, stages, dry_run, sum(stage.estimated_cost_usd for stage in stages))

    def execute_lipsync(
        self,
        *,
        org_id: str,
        video_artifact_url: str,
        audio_artifact_url: str,
        shot_type: ShotType,
        voice_profile_id: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute only the lipsync stage after an explicit pipeline plan."""
        return self.lipsync.execute(
            org_id=org_id,
            video_artifact_url=video_artifact_url,
            audio_artifact_url=audio_artifact_url,
            shot_type=shot_type,
            voice_profile_id=voice_profile_id,
            dry_run=dry_run,
        ).to_dict()
