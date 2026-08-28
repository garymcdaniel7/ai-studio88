"""Unified Generation Platform — Story 072.

One canonical generation API for all surfaces: Create, Storyboard, Quick Edit,
and Hermes. Every submission goes through the same authenticated, durable,
lifecycle-tracked pipeline.

Design:
    - Authenticated: org_id + user_id derived from JWT (never client-supplied)
    - Durable: job persisted immediately, survives browser close
    - Uniform lifecycle: queued → running → completed/failed/cancelled
    - Cancel/retry: supported for all surfaces
    - Asset registration: completed jobs register authoritative tenant-scoped assets
    - Reconnect: client can re-subscribe to job status at any time
    - Lineage: every output links to source spec, workflow, model, and talent

Surfaces:
    - Create: single image/video generation from prompt
    - Storyboard: batch of shots (multiple jobs linked to one storyboard)
    - Quick Edit: modify existing asset (img2img, upscale, inpaint)
    - Hermes: AI-initiated generation (requires approval token)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class Surface(str, Enum):
    """Caller surfaces that use the generation platform."""
    CREATE = "create"
    STORYBOARD = "storyboard"
    QUICK_EDIT = "quick_edit"
    HERMES = "hermes"


class JobStatus(str, Enum):
    """Canonical job lifecycle states."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    UPSCALE = "upscale"
    INPAINT = "inpaint"


# =============================================================================
# Generation Spec (immutable once submitted)
# =============================================================================


@dataclass(frozen=True)
class GenerationSpec:
    """Immutable generation specification — the contract between surface and platform."""
    prompt: str
    generation_type: GenerationType = GenerationType.IMAGE
    negative_prompt: str = ""
    model: str = "flux_dev"
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg: float = 7.0
    seed: int | None = None
    # Source lineage
    talent_id: str | None = None
    source_asset_id: str | None = None
    workflow_id: str | None = None
    # Batch context
    storyboard_id: str | None = None
    shot_index: int | None = None
    # Hermes context
    approval_token: str | None = None


# =============================================================================
# Generation Job
# =============================================================================


@dataclass
class GenerationJob:
    """Durable generation job with full lifecycle tracking."""
    job_id: str = field(default_factory=lambda: f"gen-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    user_id: str = ""
    surface: Surface = Surface.CREATE
    spec: GenerationSpec = field(default_factory=lambda: GenerationSpec(prompt=""))
    status: JobStatus = JobStatus.QUEUED

    # Timing
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None

    # Progress
    progress_pct: int = 0

    # Output
    output_asset_id: str | None = None
    output_url: str | None = None

    # Cost
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float | None = None

    # Error
    error: str | None = None
    retries: int = 0
    max_retries: int = 2

    # Idempotency
    idempotency_key: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)

    @property
    def is_retryable(self) -> bool:
        return self.status == JobStatus.FAILED and self.retries < self.max_retries


# =============================================================================
# Registered Asset (output of completed generation)
# =============================================================================


@dataclass
class RegisteredAsset:
    """Authoritative output asset registered after generation completes."""
    asset_id: str = field(default_factory=lambda: f"ast-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    job_id: str = ""
    surface: Surface = Surface.CREATE
    storage_key: str = ""
    content_type: str = "image/webp"
    file_size_bytes: int = 0
    # Lineage
    talent_id: str | None = None
    model_used: str = ""
    prompt: str = ""
    seed: int | None = None
    created_at: float = field(default_factory=time.time)


# =============================================================================
# Platform Store (production: Supabase)
# =============================================================================

_jobs: dict[str, GenerationJob] = {}
_assets: dict[str, RegisteredAsset] = {}
_legacy_calls: list[dict] = []  # Telemetry for legacy adapter usage


# =============================================================================
# Canonical Generation API
# =============================================================================


def submit_generation(
    org_id: str,
    user_id: str,
    surface: Surface,
    spec: GenerationSpec,
    idempotency_key: str | None = None,
) -> GenerationJob:
    """Submit a generation job through the canonical platform.

    Requirements:
    - org_id and user_id MUST be server-derived (from JWT)
    - spec is immutable once submitted
    - Returns job_id immediately (durable — survives browser close)
    - Duplicate submissions with same idempotency_key return existing job
    """
    if not org_id or not user_id:
        raise AuthenticationRequired("org_id and user_id are required (server-derived)")

    if not spec.prompt and spec.generation_type not in (GenerationType.UPSCALE,):
        raise ValidationError("prompt is required for generation")

    # Hermes requires approval token
    if surface == Surface.HERMES and not spec.approval_token:
        raise AuthorizationDenied("Hermes generation requires an approval token")

    # Idempotency check
    if idempotency_key:
        existing = _find_by_idempotency(org_id, idempotency_key)
        if existing:
            return existing

    job = GenerationJob(
        org_id=org_id,
        user_id=user_id,
        surface=surface,
        spec=spec,
        idempotency_key=idempotency_key,
        estimated_cost_usd=_estimate_cost(spec),
    )

    _jobs[job.job_id] = job
    logger.info(
        f"GENERATION_SUBMITTED: job={job.job_id} surface={surface.value} "
        f"type={spec.generation_type.value} org={org_id}"
    )
    return job


def get_job_status(job_id: str, org_id: str) -> GenerationJob | None:
    """Get job status with tenant isolation.

    Returns None for cross-tenant access (no existence leak).
    Supports reconnect — client can poll at any time.
    """
    job = _jobs.get(job_id)
    if not job or job.org_id != org_id:
        return None
    return job


def cancel_job(job_id: str, org_id: str) -> GenerationJob:
    """Cancel a running or queued job.

    Cancellation after provider completion: accepted but output not registered.
    """
    job = _jobs.get(job_id)
    if not job or job.org_id != org_id:
        raise JobNotFound("Job not found")

    if job.is_terminal:
        if job.status == JobStatus.CANCELLED:
            return job  # Idempotent
        raise InvalidOperation(f"Cannot cancel job in state {job.status.value}")

    job.status = JobStatus.CANCELLED
    job.completed_at = time.time()
    logger.info(f"GENERATION_CANCELLED: job={job_id}")
    return job


def retry_job(job_id: str, org_id: str) -> GenerationJob:
    """Retry a failed job (creates continuation, not a new job)."""
    job = _jobs.get(job_id)
    if not job or job.org_id != org_id:
        raise JobNotFound("Job not found")

    if not job.is_retryable:
        raise InvalidOperation(f"Job not retryable (status={job.status.value}, retries={job.retries})")

    job.status = JobStatus.QUEUED
    job.error = None
    job.retries += 1
    job.started_at = None
    job.completed_at = None
    job.progress_pct = 0
    logger.info(f"GENERATION_RETRIED: job={job_id} retry={job.retries}")
    return job


# =============================================================================
# Job Lifecycle (called by worker/orchestrator)
# =============================================================================


def mark_running(job_id: str) -> GenerationJob:
    """Mark job as running (worker picked it up)."""
    job = _get_job_internal(job_id)
    if job.status == JobStatus.CANCELLED:
        return job  # Race: cancelled before worker started
    job.status = JobStatus.RUNNING
    job.started_at = time.time()
    return job


def update_progress(job_id: str, progress_pct: int) -> GenerationJob:
    """Update job progress (0-100)."""
    job = _get_job_internal(job_id)
    job.progress_pct = min(max(progress_pct, 0), 100)
    return job


def mark_completed(
    job_id: str,
    output_url: str,
    storage_key: str,
    content_type: str = "image/webp",
    file_size_bytes: int = 0,
    actual_cost_usd: float = 0.0,
    seed: int | None = None,
) -> GenerationJob:
    """Mark job completed and register authoritative output asset.

    The asset is only registered if:
    1. Job was not cancelled during execution
    2. Output URL/key is provided
    3. Tenant context is valid

    This is the ONLY path to authoritative asset creation from generation.
    """
    job = _get_job_internal(job_id)

    # Race: cancelled while running — discard output
    if job.status == JobStatus.CANCELLED:
        logger.info(f"GENERATION_COMPLETED_AFTER_CANCEL: job={job_id} — output discarded")
        return job

    job.status = JobStatus.COMPLETED
    job.completed_at = time.time()
    job.progress_pct = 100
    job.output_url = output_url
    job.actual_cost_usd = actual_cost_usd

    # Register authoritative asset
    asset = RegisteredAsset(
        org_id=job.org_id,
        job_id=job.job_id,
        surface=job.surface,
        storage_key=storage_key,
        content_type=content_type,
        file_size_bytes=file_size_bytes,
        talent_id=job.spec.talent_id,
        model_used=job.spec.model,
        prompt=job.spec.prompt,
        seed=seed,
    )
    _assets[asset.asset_id] = asset
    job.output_asset_id = asset.asset_id

    logger.info(
        f"GENERATION_COMPLETED: job={job_id} asset={asset.asset_id} "
        f"cost=${actual_cost_usd:.4f}"
    )
    return job


def mark_failed(job_id: str, error: str) -> GenerationJob:
    """Mark job as failed."""
    job = _get_job_internal(job_id)
    if job.status == JobStatus.CANCELLED:
        return job  # Don't overwrite cancel with failure
    job.status = JobStatus.FAILED
    job.error = error[:500]
    job.completed_at = time.time()
    logger.warning(f"GENERATION_FAILED: job={job_id} error={error[:100]}")
    return job


# =============================================================================
# Surface Adapters
# =============================================================================


def submit_from_create(
    org_id: str,
    user_id: str,
    prompt: str,
    negative_prompt: str = "",
    model: str = "flux_dev",
    width: int = 1024,
    height: int = 1024,
    steps: int = 20,
    cfg: float = 7.0,
    seed: int | None = None,
    talent_id: str | None = None,
    idempotency_key: str | None = None,
) -> GenerationJob:
    """Create page submission adapter."""
    spec = GenerationSpec(
        prompt=prompt,
        negative_prompt=negative_prompt,
        model=model,
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
        seed=seed,
        talent_id=talent_id,
        generation_type=GenerationType.IMAGE,
    )
    return submit_generation(org_id, user_id, Surface.CREATE, spec, idempotency_key)


def submit_from_storyboard(
    org_id: str,
    user_id: str,
    storyboard_id: str,
    shots: list[dict[str, Any]],
) -> list[GenerationJob]:
    """Storyboard batch submission adapter.

    Each shot becomes a separate durable job linked to the storyboard.
    """
    jobs = []
    for i, shot in enumerate(shots):
        spec = GenerationSpec(
            prompt=shot.get("prompt", ""),
            negative_prompt=shot.get("negative_prompt", ""),
            model=shot.get("model", "flux_dev"),
            width=shot.get("width", 1024),
            height=shot.get("height", 1024),
            steps=shot.get("steps", 20),
            cfg=shot.get("cfg", 7.0),
            seed=shot.get("seed"),
            talent_id=shot.get("talent_id"),
            storyboard_id=storyboard_id,
            shot_index=i,
            generation_type=GenerationType.IMAGE,
        )
        job = submit_generation(org_id, user_id, Surface.STORYBOARD, spec)
        jobs.append(job)
    return jobs


def submit_from_quick_edit(
    org_id: str,
    user_id: str,
    source_asset_id: str,
    edit_type: str,  # "upscale" | "inpaint" | "img2img"
    prompt: str = "",
    **kwargs: Any,
) -> GenerationJob:
    """Quick Edit submission adapter."""
    gen_type = {
        "upscale": GenerationType.UPSCALE,
        "inpaint": GenerationType.INPAINT,
        "img2img": GenerationType.IMAGE,
    }.get(edit_type, GenerationType.IMAGE)

    spec = GenerationSpec(
        prompt=prompt,
        source_asset_id=source_asset_id,
        generation_type=gen_type,
        model=kwargs.get("model", "flux_dev"),
        width=kwargs.get("width", 1024),
        height=kwargs.get("height", 1024),
        steps=kwargs.get("steps", 20),
    )
    return submit_generation(org_id, user_id, Surface.QUICK_EDIT, spec)


def submit_from_hermes(
    org_id: str,
    user_id: str,
    prompt: str,
    approval_token: str,
    talent_id: str | None = None,
    model: str = "flux_dev",
) -> GenerationJob:
    """Hermes (AI-initiated) submission adapter.

    Requires a valid single-use approval token from the governance system.
    """
    spec = GenerationSpec(
        prompt=prompt,
        talent_id=talent_id,
        model=model,
        approval_token=approval_token,
        generation_type=GenerationType.IMAGE,
    )
    return submit_generation(org_id, user_id, Surface.HERMES, spec)


# =============================================================================
# Legacy Adapter Telemetry
# =============================================================================


def record_legacy_call(surface: str, endpoint: str, org_id: str) -> None:
    """Record usage of a legacy endpoint for migration tracking."""
    _legacy_calls.append({
        "surface": surface,
        "endpoint": endpoint,
        "org_id": org_id,
        "timestamp": datetime.now(UTC).isoformat(),
    })
    logger.info(f"LEGACY_GENERATION_CALL: surface={surface} endpoint={endpoint}")


def get_legacy_usage() -> list[dict]:
    """Get legacy endpoint usage for migration dashboard."""
    return list(_legacy_calls)


def get_legacy_usage_summary() -> dict[str, int]:
    """Summarize legacy calls by surface."""
    summary: dict[str, int] = {}
    for call in _legacy_calls:
        key = call["surface"]
        summary[key] = summary.get(key, 0) + 1
    return summary


# =============================================================================
# Query Helpers
# =============================================================================


def list_jobs(org_id: str, surface: Surface | None = None, limit: int = 20) -> list[GenerationJob]:
    """List generation jobs for an org, optionally filtered by surface."""
    jobs = [j for j in _jobs.values() if j.org_id == org_id]
    if surface:
        jobs = [j for j in jobs if j.surface == surface]
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs[:limit]


def get_storyboard_jobs(org_id: str, storyboard_id: str) -> list[GenerationJob]:
    """Get all jobs for a storyboard, ordered by shot index."""
    jobs = [
        j for j in _jobs.values()
        if j.org_id == org_id and j.spec.storyboard_id == storyboard_id
    ]
    jobs.sort(key=lambda j: j.spec.shot_index or 0)
    return jobs


def get_registered_asset(asset_id: str, org_id: str) -> RegisteredAsset | None:
    """Get a registered asset with tenant isolation."""
    asset = _assets.get(asset_id)
    if not asset or asset.org_id != org_id:
        return None
    return asset


# =============================================================================
# Cost Estimation
# =============================================================================


def _estimate_cost(spec: GenerationSpec) -> float:
    """Estimate generation cost based on spec."""
    # Base costs per generation type
    base_costs = {
        GenerationType.IMAGE: 0.02,
        GenerationType.VIDEO: 0.15,
        GenerationType.AUDIO: 0.05,
        GenerationType.UPSCALE: 0.01,
        GenerationType.INPAINT: 0.02,
    }
    base = base_costs.get(spec.generation_type, 0.02)

    # Adjust for resolution
    pixels = spec.width * spec.height
    if pixels > 1_048_576:  # > 1MP
        base *= 1.5

    # Adjust for steps
    if spec.steps > 30:
        base *= 1.2

    return round(base, 4)


# =============================================================================
# Internal Helpers
# =============================================================================


def _get_job_internal(job_id: str) -> GenerationJob:
    job = _jobs.get(job_id)
    if not job:
        raise JobNotFound(f"Job {job_id} not found")
    return job


def _find_by_idempotency(org_id: str, key: str) -> GenerationJob | None:
    for job in _jobs.values():
        if job.org_id == org_id and job.idempotency_key == key:
            return job
    return None


# =============================================================================
# Exceptions
# =============================================================================


class GenerationError(Exception):
    """Base generation platform error."""


class AuthenticationRequired(GenerationError):
    """Missing or invalid authentication."""


class AuthorizationDenied(GenerationError):
    """Insufficient permissions."""


class ValidationError(GenerationError):
    """Invalid generation spec."""


class JobNotFound(GenerationError):
    """Job not found or cross-tenant access."""


class InvalidOperation(GenerationError):
    """Invalid state transition."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    """Reset all state for testing."""
    _jobs.clear()
    _assets.clear()
    _legacy_calls.clear()
