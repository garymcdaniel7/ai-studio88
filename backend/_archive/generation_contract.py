"""Canonical Media-Generation Contract — Story 071.

ONE supported contract governs all media generation in AI Studio.
Every caller surface (Create page, AIOS/Hermes, video pipeline, voice, batch)
must submit through this contract or use an explicit adapter.

This module defines:
- CanonicalGenerationRequest — the typed request
- GenerationSpec — immutable generation specification (deterministic)
- GenerationJobContract — the job lifecycle (extends Story 053 GenerationJob)
- AssetResult — the mandatory output shape
- GenerationError — structured error
- CostEstimate — pre-execution cost gate
- RouteClassification — status of every generation path

Invariants:
1. Every generation creates a durable job BEFORE execution starts
2. Simulation provider cannot satisfy production completion
3. Idempotency key prevents duplicate execution
4. Tenant context (org_id) is mandatory and immutable on the job
5. Provenance chain: request → spec → job → asset is traceable
6. Cost estimate must exist before GPU dispatch
7. Cancel and retry follow explicit state machine rules
8. Final asset has storage_key, checksum, and lineage metadata
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any


# =============================================================================
# Media Types
# =============================================================================


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO_VOICE = "audio_voice"
    AUDIO_MUSIC = "audio_music"
    MODEL_TRAINING = "model_training"


class GenerationModel(StrEnum):
    FLUX_DEV = "flux-dev"
    SDXL = "sdxl"
    SD15 = "sd15"
    WAN_21 = "wan-2.1"
    LTX_VIDEO = "ltx-video"
    ELEVENLABS = "elevenlabs"
    MOSS_TTS = "moss-tts"
    SUNO = "suno"
    CUSTOM = "custom"


class JobState(StrEnum):
    """Canonical job states (superset of Story 053 GenerationState)."""
    SUBMITTED = "submitted"       # Request validated, job created
    COST_APPROVED = "cost_approved"  # Cost estimate accepted
    QUEUED = "queued"             # In provider queue
    PROVISIONING = "provisioning" # GPU instance being acquired
    EXECUTING = "executing"       # Generation in progress
    UPLOADING = "uploading"       # Output being stored
    COMPLETED = "completed"       # Success — asset created
    FAILED = "failed"             # Terminal failure
    CANCELLED = "cancelled"       # User-initiated cancel
    TIMEOUT = "timeout"           # Exceeded max duration

    @property
    def is_terminal(self) -> bool:
        return self in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED, JobState.TIMEOUT)

    @property
    def is_active(self) -> bool:
        return self in (
            JobState.SUBMITTED, JobState.COST_APPROVED, JobState.QUEUED,
            JobState.PROVISIONING, JobState.EXECUTING, JobState.UPLOADING,
        )

    @property
    def is_retryable(self) -> bool:
        return self in (JobState.FAILED, JobState.TIMEOUT)

    @property
    def is_cancellable(self) -> bool:
        return self in (
            JobState.SUBMITTED, JobState.COST_APPROVED, JobState.QUEUED, JobState.PROVISIONING,
        )


class ProviderType(StrEnum):
    COMFYUI = "comfyui"
    ELEVENLABS = "elevenlabs"
    SUNO = "suno"
    SIMULATION = "simulation"


# =============================================================================
# Canonical Generation Request
# =============================================================================


@dataclass
class CanonicalGenerationRequest:
    """The ONE typed request shape for all media generation.

    Every caller surface must produce this or use an adapter.
    """
    # Identity (mandatory)
    org_id: str                     # Tenant — extracted from JWT, never user-supplied
    user_id: str                    # Actor
    media_type: MediaType           # What kind of media

    # Content specification
    prompt: str                     # Primary generation prompt
    negative_prompt: str = ""       # What to avoid
    model: str = "flux-dev"         # Target model ID

    # Dimensions (image/video)
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg_scale: float = 7.0
    seed: int = -1                  # -1 = random

    # Optional context links
    talent_id: str | None = None
    project_id: str | None = None
    workflow_id: str | None = None
    campaign_id: str | None = None
    session_id: str | None = None   # Creative/AIOS session

    # LoRA
    lora_model_id: str | None = None
    lora_strength: float = 0.7

    # Provider preferences
    preferred_provider: ProviderType | None = None
    max_cost_usd: float | None = None  # Budget cap

    # Idempotency
    idempotency_key: str | None = None  # Prevents duplicate execution

    # Provider-specific extras (passthrough, not guaranteed)
    extras: dict = field(default_factory=dict)

    def compute_spec_hash(self) -> str:
        """Compute deterministic hash of the generation specification.

        Two requests with the same spec hash produce the same output
        (given same seed and model weights).
        """
        spec_str = (
            f"{self.media_type}|{self.prompt}|{self.negative_prompt}|"
            f"{self.model}|{self.width}x{self.height}|{self.steps}|"
            f"{self.cfg_scale}|{self.seed}|{self.lora_model_id}|{self.lora_strength}"
        )
        return hashlib.sha256(spec_str.encode()).hexdigest()[:16]


# =============================================================================
# Immutable Generation Specification
# =============================================================================


@dataclass
class GenerationSpec:
    """Frozen specification — created from request, never modified after job start.

    This is the "recipe" that produced the output, preserved for reproducibility.
    """
    spec_hash: str
    media_type: MediaType
    prompt: str
    negative_prompt: str
    model: str
    width: int
    height: int
    steps: int
    cfg_scale: float
    seed: int
    lora_model_id: str | None
    lora_strength: float
    extras: dict = field(default_factory=dict)

    @staticmethod
    def from_request(req: CanonicalGenerationRequest) -> "GenerationSpec":
        return GenerationSpec(
            spec_hash=req.compute_spec_hash(),
            media_type=req.media_type,
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            model=req.model,
            width=req.width,
            height=req.height,
            steps=req.steps,
            cfg_scale=req.cfg_scale,
            seed=req.seed,
            lora_model_id=req.lora_model_id,
            lora_strength=req.lora_strength,
            extras=req.extras.copy(),
        )

    def to_dict(self) -> dict:
        return {
            "spec_hash": self.spec_hash,
            "media_type": self.media_type.value,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "model": self.model,
            "resolution": f"{self.width}x{self.height}",
            "steps": self.steps,
            "cfg_scale": self.cfg_scale,
            "seed": self.seed,
            "lora_model_id": self.lora_model_id,
            "lora_strength": self.lora_strength,
        }


# =============================================================================
# Cost Estimate
# =============================================================================


@dataclass
class CostEstimate:
    """Pre-execution cost estimate — must exist before GPU dispatch."""

    estimated_usd: float = 0.0
    provider: ProviderType = ProviderType.SIMULATION
    gpu_type: str = ""
    estimated_seconds: int = 0
    within_budget: bool = True
    budget_remaining_usd: float | None = None

    def to_dict(self) -> dict:
        return {
            "estimated_usd": self.estimated_usd,
            "provider": self.provider.value,
            "gpu_type": self.gpu_type,
            "estimated_seconds": self.estimated_seconds,
            "within_budget": self.within_budget,
        }


# =============================================================================
# Job Contract
# =============================================================================


@dataclass
class GenerationJobContract:
    """The canonical job lifecycle record.

    Extends Story 053 GenerationJob with mandatory fields for contract compliance.
    """
    # Identity
    job_id: str = field(default_factory=lambda: f"gen-{uuid.uuid4().hex[:12]}")
    org_id: str = ""                # Immutable tenant context
    user_id: str = ""               # Requesting actor
    idempotency_key: str | None = None

    # Specification (immutable after creation)
    spec: GenerationSpec | None = None

    # State
    state: JobState = JobState.SUBMITTED
    state_history: list[dict] = field(default_factory=list)

    # Cost
    cost_estimate: CostEstimate | None = None
    actual_cost_usd: float | None = None

    # Provider
    provider: ProviderType = ProviderType.SIMULATION
    worker_id: str | None = None
    provider_job_id: str | None = None  # External provider's job ID

    # Progress
    progress_pct: float = 0.0

    # Result
    asset_id: str | None = None     # Created asset on completion
    output_url: str | None = None   # Signed URL or CDN URL
    error_message: str | None = None

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None

    # Retry
    attempt: int = 1
    max_attempts: int = 3

    def transition(self, new_state: JobState, reason: str = "") -> None:
        """Record a state transition with timestamp."""
        self.state_history.append({
            "from": self.state.value,
            "to": new_state.value,
            "at": datetime.now(UTC).isoformat(),
            "reason": reason,
        })
        self.state = new_state
        if new_state == JobState.EXECUTING:
            self.started_at = datetime.now(UTC).isoformat()
        elif new_state.is_terminal:
            self.completed_at = datetime.now(UTC).isoformat()

    def to_status(self) -> dict:
        """Public status representation."""
        return {
            "job_id": self.job_id,
            "org_id": self.org_id,
            "state": self.state.value,
            "media_type": self.spec.media_type.value if self.spec else None,
            "model": self.spec.model if self.spec else None,
            "progress_pct": self.progress_pct,
            "cost_estimate_usd": self.cost_estimate.estimated_usd if self.cost_estimate else None,
            "actual_cost_usd": self.actual_cost_usd,
            "asset_id": self.asset_id,
            "error_message": self.error_message,
            "attempt": self.attempt,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# =============================================================================
# Asset Result
# =============================================================================


@dataclass
class AssetResult:
    """Mandatory output shape when generation completes."""

    asset_id: str
    storage_key: str                # Immutable B2 path
    checksum_sha256: str            # Content integrity
    mime_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None  # For video/audio
    seed_used: int | None = None
    # Lineage
    job_id: str = ""
    spec_hash: str = ""
    model: str = ""
    provider: str = ""

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "storage_key": self.storage_key,
            "checksum_sha256": self.checksum_sha256,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "width": self.width,
            "height": self.height,
            "duration_seconds": self.duration_seconds,
            "seed_used": self.seed_used,
            "job_id": self.job_id,
            "spec_hash": self.spec_hash,
            "model": self.model,
            "provider": self.provider,
        }


# =============================================================================
# Generation Error
# =============================================================================


class ErrorCategory(StrEnum):
    VALIDATION = "validation"           # Bad input
    COST_EXCEEDED = "cost_exceeded"     # Over budget
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_ERROR = "provider_error"   # Provider returned error
    TIMEOUT = "timeout"                 # Exceeded max duration
    CANCELLED = "cancelled"             # User cancelled
    INTERNAL = "internal"               # Bug/unexpected


@dataclass
class GenerationError:
    """Structured error for generation failures."""

    category: ErrorCategory
    message: str
    code: str = ""              # Machine-readable code
    retryable: bool = False     # Whether retry might help
    provider_detail: str = ""   # Raw provider error (not exposed to client)
    job_id: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "message": self.message,
            "code": self.code,
            "retryable": self.retryable,
            "job_id": self.job_id,
        }


# =============================================================================
# Route Classification
# =============================================================================


class RouteStatus(StrEnum):
    CANONICAL = "canonical"                 # The supported contract path
    ADAPTER = "adapter"                     # Wraps canonical for specific surface
    COMPATIBILITY = "compatibility_only"    # Legacy, will be migrated
    SIMULATION_ONLY = "simulation_only"     # Dev/test only, not production
    DEPRECATED = "deprecated"              # Scheduled for removal
    REMOVE = "remove"                      # Should be deleted


@dataclass
class RouteClassification:
    """Classification of a generation route/endpoint."""

    path: str
    method: str
    status: RouteStatus
    canonical_replacement: str | None = None  # What replaces it
    removal_condition: str = ""              # When it can be removed
    notes: str = ""


# Complete classification of all generation routes
ROUTE_CLASSIFICATIONS: list[RouteClassification] = [
    RouteClassification(
        path="/api/v1/generation/run",
        method="POST",
        status=RouteStatus.COMPATIBILITY,
        canonical_replacement="POST /api/v1/jobs/generate",
        removal_condition="All callers migrated to canonical job submission",
        notes="Sync execution without durable job. Must migrate to async job.",
    ),
    RouteClassification(
        path="/api/v1/generation/health",
        method="GET",
        status=RouteStatus.CANONICAL,
        notes="Provider health check — no change needed.",
    ),
    RouteClassification(
        path="/api/v1/generation/providers",
        method="GET",
        status=RouteStatus.CANONICAL,
        notes="Provider listing — no change needed.",
    ),
    RouteClassification(
        path="/api/v1/generation/models",
        method="GET",
        status=RouteStatus.CANONICAL,
        notes="Model registry — no change needed.",
    ),
    RouteClassification(
        path="/api/v1/generation/available-models",
        method="GET",
        status=RouteStatus.CANONICAL,
        notes="Model availability with B2 cache status.",
    ),
    RouteClassification(
        path="/api/v1/assets/save-generation",
        method="POST",
        status=RouteStatus.DEPRECATED,
        canonical_replacement="Automatic asset creation on job completion",
        removal_condition="Frontend no longer manually saves generation results",
        notes="Browser-orchestrated save. Canonical contract creates asset automatically.",
    ),
    RouteClassification(
        path="/api/v1/videos/{id}/generate",
        method="POST",
        status=RouteStatus.ADAPTER,
        canonical_replacement="POST /api/v1/jobs/generate with media_type=video",
        removal_condition="Video pipeline uses canonical contract internally",
        notes="Domain-specific surface. Should wrap canonical contract.",
    ),
    RouteClassification(
        path="/api/v1/voices/moss/generate-speech",
        method="POST",
        status=RouteStatus.ADAPTER,
        canonical_replacement="POST /api/v1/jobs/generate with media_type=audio_voice",
        removal_condition="Voice pipeline uses canonical contract internally",
        notes="Domain-specific surface for TTS.",
    ),
    RouteClassification(
        path="/api/v1/songs/{id}/generate",
        method="POST",
        status=RouteStatus.ADAPTER,
        canonical_replacement="POST /api/v1/jobs/generate with media_type=audio_music",
        removal_condition="Music pipeline uses canonical contract internally",
        notes="Domain-specific surface for music generation.",
    ),
    RouteClassification(
        path="/api/v1/product-commercials/generate",
        method="POST",
        status=RouteStatus.ADAPTER,
        canonical_replacement="POST /api/v1/jobs/generate with extras",
        removal_condition="Object intelligence uses canonical contract",
        notes="High-level orchestration that produces multiple generation jobs.",
    ),
]


# =============================================================================
# Contract Validation
# =============================================================================


def validate_request(req: CanonicalGenerationRequest) -> list[str]:
    """Validate a generation request against contract rules.

    Returns list of violation messages. Empty = valid.
    """
    violations: list[str] = []

    # Mandatory tenant context
    if not req.org_id:
        violations.append("org_id is mandatory (extracted from JWT)")
    if not req.user_id:
        violations.append("user_id is mandatory")

    # Prompt required for all except training
    if req.media_type != MediaType.MODEL_TRAINING and not req.prompt:
        violations.append("prompt is mandatory for generation")

    # Dimension constraints
    if req.width < 64 or req.width > 4096:
        violations.append(f"width must be 64-4096, got {req.width}")
    if req.height < 64 or req.height > 4096:
        violations.append(f"height must be 64-4096, got {req.height}")

    # Steps constraint
    if req.steps < 1 or req.steps > 150:
        violations.append(f"steps must be 1-150, got {req.steps}")

    # CFG constraint
    if req.cfg_scale < 0 or req.cfg_scale > 30:
        violations.append(f"cfg_scale must be 0-30, got {req.cfg_scale}")

    # LoRA strength
    if req.lora_model_id and (req.lora_strength < 0 or req.lora_strength > 2.0):
        violations.append(f"lora_strength must be 0-2.0, got {req.lora_strength}")

    return violations


def validate_completion(job: GenerationJobContract) -> list[str]:
    """Validate that a completed job meets contract requirements.

    Returns list of violation messages. Empty = compliant.
    """
    violations: list[str] = []

    if job.state != JobState.COMPLETED:
        violations.append(f"Job not completed, state={job.state.value}")
        return violations

    if not job.asset_id:
        violations.append("Completed job must have asset_id")

    if not job.spec:
        violations.append("Completed job must have immutable spec")

    if job.provider == ProviderType.SIMULATION:
        violations.append("Simulation provider cannot satisfy production completion")

    if job.cost_estimate is None:
        violations.append("Completed job must have cost_estimate")

    if job.actual_cost_usd is None:
        violations.append("Completed job must record actual_cost_usd")

    if not job.completed_at:
        violations.append("Completed job must have completed_at timestamp")

    return violations


def validate_simulation_completion(job: GenerationJobContract) -> list[str]:
    """Validate simulation completion (relaxed rules for dev/test).

    Simulation CAN complete but is explicitly marked as non-production.
    """
    violations: list[str] = []

    if job.state != JobState.COMPLETED:
        violations.append(f"Job not completed, state={job.state.value}")

    if not job.spec:
        violations.append("Completed job must have immutable spec")

    # Simulation does NOT require: asset_id, cost, actual_cost
    return violations
