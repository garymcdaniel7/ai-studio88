"""Local-first AIOS lip-sync execution with policy-selected engines."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import urlparse

from backend.tenant_context import validate_org_id


class ShotType(StrEnum):
    """Shot categories used by the lip-sync policy."""

    CLOSE_UP = "close_up"
    MEDIUM = "medium"
    WIDE = "wide"
    BEHIND = "behind"


class LipSyncTier(StrEnum):
    """Execution tiers selected from shot type and speed policy."""

    LATENTSYNC = "latentsync"
    MUSETALK = "musetalk"
    LIGHT_PASS = "light_pass"
    SKIP = "skip"


@dataclass(frozen=True)
class TimingReport:
    """Frame alignment evidence returned with a lip-synced artifact."""

    frame_offsets: list[int]
    confidence: float
    duration_seconds: float
    engine: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the timing evidence."""
        return {
            "frame_offsets": self.frame_offsets,
            "confidence": self.confidence,
            "duration_seconds": self.duration_seconds,
            "engine": self.engine,
        }


@dataclass(frozen=True)
class LipSyncResult:
    """Result of planning or executing one lip-sync operation."""

    status: str
    tier: LipSyncTier
    artifact_url: str
    timing_report: TimingReport
    elapsed_seconds: float
    dry_run: bool = False
    voice_profile_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result for pipeline and API callers."""
        return {
            "status": self.status,
            "tier": self.tier.value,
            "artifact_url": self.artifact_url,
            "timing_report": self.timing_report.to_dict(),
            "elapsed_seconds": self.elapsed_seconds,
            "dry_run": self.dry_run,
            "voice_profile_id": self.voice_profile_id,
            "metadata": self.metadata,
        }


class LipSyncEngine(Protocol):
    """Protocol for a local LatentSync or MuseTalk worker."""

    def run(self, video_url: str, audio_url: str, *, tier: LipSyncTier, profile: dict | None) -> tuple[str, TimingReport]:
        """Produce an output artifact URL and timing evidence."""


class SimulatedLipSyncEngine:
    """Deterministic local engine used for tests and founder dry-run play."""

    def run(self, video_url: str, audio_url: str, *, tier: LipSyncTier, profile: dict | None) -> tuple[str, TimingReport]:
        """Return a CDN-shaped artifact URL without external provider calls."""
        digest = hashlib.sha256(f"{video_url}|{audio_url}|{tier.value}".encode()).hexdigest()[:16]
        report = TimingReport(
            frame_offsets=[0, 0, 1, 0],
            confidence=0.97 if tier == LipSyncTier.LATENTSYNC else 0.91,
            duration_seconds=5.0,
            engine=tier.value,
        )
        return f"https://cdn.ai-studio.invalid/lipsync/{digest}.mp4", report


class VoiceProfileStore:
    """Read tenant-scoped voice profile references without exposing raw secrets."""

    def __init__(self, db_client: Any | None = None) -> None:
        self._db_client = db_client

    def _db(self) -> Any:
        if self._db_client is not None:
            return self._db_client
        from backend.database import supabase

        return supabase

    def get(self, org_id: str, profile_id: str) -> dict | None:
        """Fetch a profile only when both profile and organization match."""
        org_id = validate_org_id(org_id)
        result = (
            self._db()
            .table("voice_profiles")
            .select("id,org_id,character,tts_ref,sample_ref")
            .eq("id", profile_id)
            .eq("org_id", org_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None


class LipSyncAdapter:
    """Select LatentSync/MuseTalk or a light-pass policy for each shot."""

    def __init__(
        self,
        *,
        latent_sync: LipSyncEngine | None = None,
        muse_talk: LipSyncEngine | None = None,
        profile_store: VoiceProfileStore | None = None,
        fast_tier: bool = False,
        wide_mode: LipSyncTier = LipSyncTier.LIGHT_PASS,
    ) -> None:
        self.latent_sync = latent_sync or SimulatedLipSyncEngine()
        self.muse_talk = muse_talk or SimulatedLipSyncEngine()
        self.profile_store = profile_store or VoiceProfileStore()
        self.fast_tier = fast_tier
        self.wide_mode = wide_mode

    def select_tier(self, shot_type: ShotType) -> LipSyncTier:
        """Apply the bright-line shot policy."""
        if shot_type == ShotType.CLOSE_UP:
            return LipSyncTier.MUSETALK if self.fast_tier else LipSyncTier.LATENTSYNC
        if shot_type == ShotType.MEDIUM:
            return LipSyncTier.MUSETALK if self.fast_tier else LipSyncTier.LATENTSYNC
        if shot_type in (ShotType.WIDE, ShotType.BEHIND):
            return self.wide_mode
        raise ValueError(f"unsupported shot type: {shot_type}")

    def execute(
        self,
        *,
        org_id: str,
        video_artifact_url: str,
        audio_artifact_url: str,
        shot_type: ShotType,
        voice_profile_id: str | None = None,
        dry_run: bool = False,
    ) -> LipSyncResult:
        """Plan or execute local lip-sync without third-party API calls."""
        validate_org_id(org_id)
        for label, value in (("video_artifact_url", video_artifact_url), ("audio_artifact_url", audio_artifact_url)):
            parsed = urlparse(value)
            if parsed.scheme not in {"https", "file"} or not parsed.netloc and parsed.scheme == "https":
                raise ValueError(f"{label} must be an HTTPS or local fixture artifact URL")
        tier = self.select_tier(shot_type)
        started = time.monotonic()
        if tier == LipSyncTier.SKIP:
            report = TimingReport([], 1.0, 5.0, "skipped")
            return LipSyncResult("skipped", tier, video_artifact_url, report, time.monotonic() - started, dry_run, voice_profile_id)
        if tier == LipSyncTier.LIGHT_PASS:
            report = TimingReport([0], 0.6, 5.0, "light_pass")
            return LipSyncResult("light_pass", tier, video_artifact_url, report, time.monotonic() - started, dry_run, voice_profile_id)
        if dry_run:
            report = TimingReport([], 0.0, 5.0, tier.value)
            return LipSyncResult("planned", tier, video_artifact_url, report, 0.0, True, voice_profile_id)
        profile = self.profile_store.get(org_id, voice_profile_id) if voice_profile_id else None
        engine = self.latent_sync if tier == LipSyncTier.LATENTSYNC else self.muse_talk
        output_url, report = engine.run(video_artifact_url, audio_artifact_url, tier=tier, profile=profile)
        if urlparse(output_url).scheme != "https":
            raise ValueError("lip-sync output must be a signed or CDN HTTPS URL")
        return LipSyncResult("completed", tier, output_url, report, time.monotonic() - started, False, voice_profile_id, {"profile_loaded": profile is not None})
