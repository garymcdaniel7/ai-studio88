"""Authoritative Asset Metadata — Story 074.

Asset metadata is derived EXCLUSIVELY from the immutable backend generation
record. UI-supplied metadata cannot overwrite effective execution values.

The principle: "backend truth wins." After generation completes, the actual
parameters used (including provider-selected seeds, enriched prompts, recipe
overrides, normalized dimensions, and exact model versions) become the
authoritative source for asset metadata.

Key behaviors:
    - Metadata is populated from the completed GenerationJob record
    - UI-supplied values are rejected if they conflict with execution record
    - Randomized seeds are captured as the actual value used
    - Provider-normalized dimensions are recorded (not UI request)
    - Recipe/enrichment overrides are preserved
    - Save is idempotent (same job → same asset metadata)
    - Retry attempts get distinct metadata (new seed, new attempt)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Authoritative Metadata Record
# =============================================================================


@dataclass
class AssetMetadata:
    """Immutable metadata derived from the generation execution record.

    Every field is sourced from the backend — never from the client.
    """
    metadata_id: str = field(default_factory=lambda: f"meta-{uuid.uuid4().hex[:12]}")

    # Identity
    asset_id: str = ""
    org_id: str = ""
    job_id: str = ""

    # Effective prompt (after enrichment/recipe)
    effective_prompt: str = ""
    effective_negative_prompt: str = ""
    original_prompt: str = ""  # What the user typed (before enrichment)
    enrichment_applied: bool = False

    # Model & LoRA (exact versions used)
    model_id: str = ""
    model_version: str = ""
    lora_ids: list[str] = field(default_factory=list)
    lora_versions: list[str] = field(default_factory=list)
    lora_strengths: list[float] = field(default_factory=list)

    # Generation parameters (actual values used, not requested)
    actual_seed: int = 0           # The ACTUAL seed (even if user said "random")
    actual_width: int = 0          # Provider may normalize dimensions
    actual_height: int = 0
    actual_steps: int = 0
    actual_cfg: float = 0.0
    actual_guidance: float | None = None

    # Context
    talent_id: str | None = None
    project_id: str | None = None
    workflow_id: str | None = None
    recipe_id: str | None = None
    controlnet_id: str | None = None
    storyboard_id: str | None = None
    shot_index: int | None = None

    # Provider & cost
    provider: str = ""             # vast.ai, runpod, local
    gpu_type: str = ""
    generation_time_seconds: float = 0.0
    actual_cost_usd: float = 0.0

    # Lineage
    source_asset_id: str | None = None  # For img2img/upscale
    attempt_number: int = 1        # Which retry attempt produced this

    # Timestamp
    created_at: float = field(default_factory=time.time)

    @property
    def is_remix_ready(self) -> bool:
        """Whether this metadata has enough info for accurate remix."""
        return bool(self.effective_prompt and self.model_id and self.actual_seed)


# =============================================================================
# Execution Record (what the backend actually did)
# =============================================================================


@dataclass
class ExecutionRecord:
    """The authoritative record of what actually happened during generation.

    This is populated by the worker/orchestrator after execution completes.
    It is IMMUTABLE once written.
    """
    job_id: str = ""
    org_id: str = ""

    # What was actually executed
    effective_prompt: str = ""
    effective_negative_prompt: str = ""
    original_prompt: str = ""
    enrichment_applied: bool = False
    recipe_id: str | None = None

    # Actual model/LoRA used
    model_id: str = ""
    model_version: str = ""
    lora_ids: list[str] = field(default_factory=list)
    lora_versions: list[str] = field(default_factory=list)
    lora_strengths: list[float] = field(default_factory=list)

    # Actual parameters (post-normalization)
    actual_seed: int = 0
    actual_width: int = 1024
    actual_height: int = 1024
    actual_steps: int = 20
    actual_cfg: float = 7.0
    actual_guidance: float | None = None

    # Context
    talent_id: str | None = None
    project_id: str | None = None
    workflow_id: str | None = None
    controlnet_id: str | None = None
    storyboard_id: str | None = None
    shot_index: int | None = None
    source_asset_id: str | None = None

    # Provider details
    provider: str = ""
    gpu_type: str = ""
    generation_time_seconds: float = 0.0
    actual_cost_usd: float = 0.0

    # Retry tracking
    attempt_number: int = 1


# =============================================================================
# Store
# =============================================================================

_metadata_store: dict[str, AssetMetadata] = {}  # asset_id → metadata
_execution_store: dict[str, ExecutionRecord] = {}  # job_id → execution record
_save_receipts: dict[str, str] = {}  # job_id → asset_id (idempotency)


# =============================================================================
# Registration API
# =============================================================================


def register_execution_record(record: ExecutionRecord) -> None:
    """Register the authoritative execution record after generation completes.

    Called by the worker/orchestrator — never by the client.
    """
    if not record.job_id:
        raise ValueError("ExecutionRecord requires job_id")
    if not record.org_id:
        raise ValueError("ExecutionRecord requires org_id")

    _execution_store[record.job_id] = record
    logger.info(f"EXECUTION_RECORD_REGISTERED: job={record.job_id} model={record.model_id} seed={record.actual_seed}")


def save_asset_metadata(
    job_id: str,
    asset_id: str,
    org_id: str,
    caller_metadata: dict[str, Any] | None = None,
) -> AssetMetadata:
    """Save asset metadata derived from the authoritative execution record.

    This is the ONLY path to creating asset metadata for generated content.

    Rules:
    1. Metadata is derived from ExecutionRecord (backend truth)
    2. caller_metadata is IGNORED for execution-derived fields
    3. caller_metadata may provide display-only fields (title, tags, notes)
    4. Save is idempotent: same job_id → same metadata returned
    5. Cross-tenant attempts raise ValueError

    Args:
        job_id: The generation job that produced this asset
        asset_id: The asset ID being saved
        org_id: The org requesting the save (must match job org)
        caller_metadata: Optional UI-supplied display metadata (non-authoritative)

    Returns:
        AssetMetadata with all execution fields from backend record
    """
    # Idempotency: if already saved for this job, return existing
    if job_id in _save_receipts:
        existing_asset_id = _save_receipts[job_id]
        existing = _metadata_store.get(existing_asset_id)
        if existing:
            return existing

    # Get authoritative execution record
    record = _execution_store.get(job_id)
    if not record:
        raise ExecutionRecordNotFound(f"No execution record for job {job_id}")

    # Cross-tenant protection
    if record.org_id != org_id:
        raise ValueError("Org mismatch — cross-tenant save denied")

    # Build metadata from execution record (NOT from caller)
    metadata = AssetMetadata(
        asset_id=asset_id,
        org_id=record.org_id,
        job_id=record.job_id,
        effective_prompt=record.effective_prompt,
        effective_negative_prompt=record.effective_negative_prompt,
        original_prompt=record.original_prompt,
        enrichment_applied=record.enrichment_applied,
        model_id=record.model_id,
        model_version=record.model_version,
        lora_ids=list(record.lora_ids),
        lora_versions=list(record.lora_versions),
        lora_strengths=list(record.lora_strengths),
        actual_seed=record.actual_seed,
        actual_width=record.actual_width,
        actual_height=record.actual_height,
        actual_steps=record.actual_steps,
        actual_cfg=record.actual_cfg,
        actual_guidance=record.actual_guidance,
        talent_id=record.talent_id,
        project_id=record.project_id,
        workflow_id=record.workflow_id,
        recipe_id=record.recipe_id,
        controlnet_id=record.controlnet_id,
        storyboard_id=record.storyboard_id,
        shot_index=record.shot_index,
        source_asset_id=record.source_asset_id,
        provider=record.provider,
        gpu_type=record.gpu_type,
        generation_time_seconds=record.generation_time_seconds,
        actual_cost_usd=record.actual_cost_usd,
        attempt_number=record.attempt_number,
    )

    # Log if caller tried to override execution fields
    if caller_metadata:
        _log_rejected_overrides(caller_metadata, record)

    _metadata_store[asset_id] = metadata
    _save_receipts[job_id] = asset_id

    logger.info(
        f"ASSET_METADATA_SAVED: asset={asset_id} job={job_id} "
        f"model={metadata.model_id} seed={metadata.actual_seed} "
        f"enriched={metadata.enrichment_applied}"
    )
    return metadata


def get_asset_metadata(asset_id: str, org_id: str) -> AssetMetadata | None:
    """Get asset metadata with tenant isolation."""
    metadata = _metadata_store.get(asset_id)
    if not metadata or metadata.org_id != org_id:
        return None
    return metadata


# =============================================================================
# Conflict Detection
# =============================================================================

# Fields that are ALWAYS derived from backend (never from caller)
AUTHORITATIVE_FIELDS = frozenset({
    "prompt", "negative_prompt", "effective_prompt", "effective_negative_prompt",
    "seed", "actual_seed", "width", "actual_width", "height", "actual_height",
    "steps", "actual_steps", "cfg", "actual_cfg", "guidance", "actual_guidance",
    "model", "model_id", "model_version",
    "lora_ids", "lora_versions", "lora_strengths",
    "provider", "gpu_type", "cost", "actual_cost_usd",
    "generation_time_seconds", "attempt_number",
    "talent_id", "project_id", "workflow_id", "recipe_id",
    "controlnet_id", "source_asset_id",
})


def validate_caller_metadata(caller_metadata: dict[str, Any]) -> dict[str, Any]:
    """Separate caller metadata into accepted (display) and rejected (authoritative).

    Returns only the accepted (non-authoritative) fields.
    Rejected fields are logged as attempted overrides.
    """
    accepted: dict[str, Any] = {}
    rejected: dict[str, Any] = {}

    for key, value in caller_metadata.items():
        if key in AUTHORITATIVE_FIELDS:
            rejected[key] = value
        else:
            accepted[key] = value

    if rejected:
        logger.warning(
            f"METADATA_OVERRIDE_REJECTED: fields={list(rejected.keys())} "
            f"— these are derived from execution record"
        )

    return accepted


def _log_rejected_overrides(caller_metadata: dict[str, Any], record: ExecutionRecord) -> None:
    """Log when caller tries to supply values that conflict with execution record."""
    conflicts = []

    # Check for seed mismatch (most common: UI sends "random" while backend has actual)
    if "seed" in caller_metadata and caller_metadata["seed"] != record.actual_seed:
        conflicts.append(f"seed: caller={caller_metadata['seed']} actual={record.actual_seed}")

    # Check for prompt mismatch (UI may have pre-enrichment version)
    if "prompt" in caller_metadata and caller_metadata["prompt"] != record.effective_prompt:
        conflicts.append("prompt: caller differs from effective (enrichment applied)")

    # Check dimensions
    if "width" in caller_metadata and caller_metadata["width"] != record.actual_width:
        conflicts.append(f"width: caller={caller_metadata['width']} actual={record.actual_width}")
    if "height" in caller_metadata and caller_metadata["height"] != record.actual_height:
        conflicts.append(f"height: caller={caller_metadata['height']} actual={record.actual_height}")

    if conflicts:
        logger.info(f"METADATA_CONFLICTS_DETECTED: job={record.job_id} conflicts={conflicts}")


# =============================================================================
# Exceptions
# =============================================================================


class ExecutionRecordNotFound(Exception):
    """No execution record exists for the given job."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    """Reset all state for testing."""
    _metadata_store.clear()
    _execution_store.clear()
    _save_receipts.clear()
