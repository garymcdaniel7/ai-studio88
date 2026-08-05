"""Durable Lineage Capture — Story 078.

Context-package and prompt-history persistence are explicit, durable job steps
with independent status from the media output. A generation may succeed while
lineage capture fails — both states are visible and actionable.

Design:
    - Media output and lineage capture have INDEPENDENT statuses
    - Lineage capture failures are NEVER silently ignored
    - Retry is idempotent and preserves original immutable generation values
    - Repair is authorized, audited, and produces evidence
    - Alerts fire on persistent lineage failure

Lineage capture steps:
    1. context_package — full generation context (model, params, LoRA, recipe)
    2. prompt_history — original + enriched prompts, negative, talent DNA
    3. provenance_link — bidirectional link between asset and job

Each step is tracked independently: pending → captured → failed → repaired.
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


class CaptureStep(str, Enum):
    """Lineage capture steps that must persist independently."""
    CONTEXT_PACKAGE = "context_package"
    PROMPT_HISTORY = "prompt_history"
    PROVENANCE_LINK = "provenance_link"


class CaptureStatus(str, Enum):
    """Status of a single lineage capture step."""
    PENDING = "pending"
    CAPTURED = "captured"        # Successfully persisted
    FAILED = "failed"            # Persistence failed (retryable)
    PERMANENTLY_FAILED = "permanently_failed"  # Exhausted retries
    REPAIRED = "repaired"        # Manually repaired by authorized user


class LineageStatus(str, Enum):
    """Overall lineage status for an asset."""
    COMPLETE = "complete"        # All steps captured
    INCOMPLETE = "incomplete"    # Some steps pending or failed
    FAILED = "failed"            # One or more steps permanently failed
    REPAIRING = "repairing"     # Manual repair in progress


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class CaptureStepRecord:
    """A single lineage capture step with its own lifecycle."""
    step: CaptureStep
    status: CaptureStatus = CaptureStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    captured_at: float | None = None
    failed_at: float | None = None
    repaired_at: float | None = None
    repaired_by: str | None = None

    @property
    def is_retryable(self) -> bool:
        return self.status == CaptureStatus.FAILED and self.attempts < self.max_attempts

    @property
    def is_terminal(self) -> bool:
        return self.status in (CaptureStatus.CAPTURED, CaptureStatus.PERMANENTLY_FAILED, CaptureStatus.REPAIRED)


@dataclass
class ImmutableGenerationValues:
    """The original generation truth — NEVER reconstructed from mutable state.

    These values are captured at generation time and preserved across retries.
    """
    job_id: str = ""
    effective_prompt: str = ""
    effective_negative_prompt: str = ""
    original_prompt: str = ""
    model_id: str = ""
    model_version: str = ""
    actual_seed: int = 0
    actual_width: int = 0
    actual_height: int = 0
    actual_steps: int = 0
    actual_cfg: float = 0.0
    lora_ids: list[str] = field(default_factory=list)
    lora_versions: list[str] = field(default_factory=list)
    talent_id: str | None = None
    recipe_id: str | None = None
    workflow_id: str | None = None
    provider: str = ""
    actual_cost_usd: float = 0.0


@dataclass
class LineageCaptureRecord:
    """Durable record tracking lineage capture for one generation/asset."""
    capture_id: str = field(default_factory=lambda: f"lc-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    asset_id: str = ""
    job_id: str = ""

    # Immutable generation values (frozen at capture time)
    generation_values: ImmutableGenerationValues = field(
        default_factory=ImmutableGenerationValues
    )

    # Individual step statuses
    steps: dict[CaptureStep, CaptureStepRecord] = field(default_factory=dict)

    # Overall
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    @property
    def lineage_status(self) -> LineageStatus:
        if not self.steps:
            return LineageStatus.INCOMPLETE
        if all(s.status in (CaptureStatus.CAPTURED, CaptureStatus.REPAIRED) for s in self.steps.values()):
            return LineageStatus.COMPLETE
        if any(s.status == CaptureStatus.PERMANENTLY_FAILED for s in self.steps.values()):
            return LineageStatus.FAILED
        return LineageStatus.INCOMPLETE

    @property
    def is_complete(self) -> bool:
        return self.lineage_status == LineageStatus.COMPLETE

    @property
    def incomplete_steps(self) -> list[CaptureStep]:
        return [
            step for step, record in self.steps.items()
            if record.status not in (CaptureStatus.CAPTURED, CaptureStatus.REPAIRED)
        ]


# =============================================================================
# Store
# =============================================================================

_captures: dict[str, LineageCaptureRecord] = {}  # capture_id → record
_asset_index: dict[str, str] = {}  # asset_id → capture_id
_alerts: list[dict] = []


# =============================================================================
# Failure Injection (testing)
# =============================================================================

_inject_step_failures: dict[CaptureStep, bool] = {}
_inject_permanent_failure: bool = False


# =============================================================================
# Lineage Capture API
# =============================================================================


def initiate_capture(
    org_id: str,
    asset_id: str,
    job_id: str,
    generation_values: ImmutableGenerationValues,
) -> LineageCaptureRecord:
    """Initiate lineage capture for a completed generation.

    Called after media output is confirmed. Creates durable tracking
    for each capture step.

    Idempotent: if capture already exists for this asset, returns existing.
    """
    if not org_id or not asset_id or not job_id:
        raise ValueError("org_id, asset_id, and job_id are required")

    # Idempotency
    if asset_id in _asset_index:
        existing = _captures.get(_asset_index[asset_id])
        if existing:
            return existing

    record = LineageCaptureRecord(
        org_id=org_id,
        asset_id=asset_id,
        job_id=job_id,
        generation_values=generation_values,
        steps={
            CaptureStep.CONTEXT_PACKAGE: CaptureStepRecord(step=CaptureStep.CONTEXT_PACKAGE),
            CaptureStep.PROMPT_HISTORY: CaptureStepRecord(step=CaptureStep.PROMPT_HISTORY),
            CaptureStep.PROVENANCE_LINK: CaptureStepRecord(step=CaptureStep.PROVENANCE_LINK),
        },
    )

    _captures[record.capture_id] = record
    _asset_index[asset_id] = record.capture_id

    logger.info(f"LINEAGE_CAPTURE_INITIATED: capture={record.capture_id} asset={asset_id} job={job_id}")
    return record


def execute_capture(capture_id: str) -> LineageCaptureRecord:
    """Execute all pending capture steps.

    Each step is attempted independently — one failure doesn't block others.
    Failed steps remain visible and retryable.
    """
    record = _get_record(capture_id)

    for step, step_record in record.steps.items():
        if step_record.is_terminal:
            continue
        _execute_step(record, step, step_record)

    # Check if all complete
    if record.is_complete:
        record.completed_at = time.time()
        logger.info(f"LINEAGE_CAPTURE_COMPLETE: capture={capture_id}")

    return record


def retry_capture(capture_id: str) -> LineageCaptureRecord:
    """Retry failed (non-permanent) capture steps.

    Preserves original immutable generation values — never reconstructs
    from current mutable state.
    """
    record = _get_record(capture_id)

    retried_any = False
    for step, step_record in record.steps.items():
        if step_record.is_retryable:
            step_record.status = CaptureStatus.PENDING
            retried_any = True

    if not retried_any:
        raise NoRetryableSteps("No retryable steps found")

    # Re-execute
    return execute_capture(capture_id)


def repair_step(
    capture_id: str,
    step: CaptureStep,
    org_id: str,
    repaired_by: str,
) -> LineageCaptureRecord:
    """Manually repair a permanently failed capture step.

    Requires authorization and produces audit evidence.
    Uses the original immutable generation values (not current state).
    """
    record = _get_record(capture_id)

    # Tenant isolation
    if record.org_id != org_id:
        raise PermissionDenied("Cross-tenant repair denied")

    if not repaired_by:
        raise PermissionDenied("repaired_by (actor) is required for audit")

    step_record = record.steps.get(step)
    if not step_record:
        raise StepNotFound(f"Step {step.value} not found")

    if step_record.status in (CaptureStatus.CAPTURED, CaptureStatus.REPAIRED):
        return record  # Already good — idempotent

    # Mark repaired
    step_record.status = CaptureStatus.REPAIRED
    step_record.repaired_at = time.time()
    step_record.repaired_by = repaired_by

    # Check overall completion
    if record.is_complete:
        record.completed_at = time.time()

    logger.info(
        f"LINEAGE_STEP_REPAIRED: capture={capture_id} step={step.value} "
        f"by={repaired_by}"
    )
    return record


# =============================================================================
# Query API
# =============================================================================


def get_lineage_status(asset_id: str, org_id: str) -> dict[str, Any] | None:
    """Get lineage capture status for an asset.

    Returns None for cross-tenant access (no existence leak).
    """
    capture_id = _asset_index.get(asset_id)
    if not capture_id:
        return None

    record = _captures.get(capture_id)
    if not record or record.org_id != org_id:
        return None

    return {
        "capture_id": record.capture_id,
        "asset_id": record.asset_id,
        "job_id": record.job_id,
        "lineage_status": record.lineage_status.value,
        "is_complete": record.is_complete,
        "incomplete_steps": [s.value for s in record.incomplete_steps],
        "steps": {
            step.value: {
                "status": sr.status.value,
                "attempts": sr.attempts,
                "last_error": sr.last_error,
                "repaired_by": sr.repaired_by,
            }
            for step, sr in record.steps.items()
        },
    }


def list_incomplete_lineages(org_id: str) -> list[dict[str, Any]]:
    """List all assets with incomplete lineage for an org.

    Used by ops dashboard and alerting.
    """
    results = []
    for record in _captures.values():
        if record.org_id == org_id and not record.is_complete:
            results.append({
                "capture_id": record.capture_id,
                "asset_id": record.asset_id,
                "job_id": record.job_id,
                "lineage_status": record.lineage_status.value,
                "incomplete_steps": [s.value for s in record.incomplete_steps],
            })
    return results


def get_active_alerts(org_id: str | None = None) -> list[dict]:
    """Get unresolved lineage alerts."""
    alerts = [a for a in _alerts if not a.get("resolved")]
    if org_id:
        alerts = [a for a in alerts if a.get("org_id") == org_id]
    return alerts


# =============================================================================
# Step Execution
# =============================================================================


def _execute_step(
    record: LineageCaptureRecord,
    step: CaptureStep,
    step_record: CaptureStepRecord,
) -> None:
    """Execute a single capture step."""
    step_record.attempts += 1
    step_record.status = CaptureStatus.PENDING

    try:
        # Check for injected failures (testing)
        if _inject_step_failures.get(step, False):
            raise PersistenceError(f"Simulated failure for {step.value}")

        if _inject_permanent_failure:
            raise PersistenceError(f"Permanent failure for {step.value}")

        # In production: actual DB/storage write using record.generation_values
        # The key point: we use the IMMUTABLE generation_values, not current state
        _persist_step(record, step)

        step_record.status = CaptureStatus.CAPTURED
        step_record.captured_at = time.time()

    except PersistenceError as e:
        step_record.last_error = str(e)[:200]

        if step_record.attempts >= step_record.max_attempts:
            step_record.status = CaptureStatus.PERMANENTLY_FAILED
            step_record.failed_at = time.time()
            _raise_alert(record, step, str(e))
            logger.error(
                f"LINEAGE_STEP_PERMANENTLY_FAILED: capture={record.capture_id} "
                f"step={step.value} attempts={step_record.attempts}"
            )
        else:
            step_record.status = CaptureStatus.FAILED
            logger.warning(
                f"LINEAGE_STEP_FAILED: capture={record.capture_id} "
                f"step={step.value} attempt={step_record.attempts} error={e}"
            )


def _persist_step(record: LineageCaptureRecord, step: CaptureStep) -> None:
    """Persist a lineage step using immutable generation values.

    In production this writes to Supabase tables:
    - context_package → generation_context table
    - prompt_history → prompt_history table
    - provenance_link → asset_provenance table
    """
    gv = record.generation_values
    # Simulated persistence — in production: actual DB insert
    # The critical invariant: we use gv (immutable), never current domain state


def _raise_alert(record: LineageCaptureRecord, step: CaptureStep, error: str) -> None:
    """Raise alert for permanent lineage failure."""
    alert = {
        "id": f"lineage-alert-{uuid.uuid4().hex[:8]}",
        "type": "lineage_capture_failed",
        "capture_id": record.capture_id,
        "asset_id": record.asset_id,
        "step": step.value,
        "error": error[:200],
        "org_id": record.org_id,
        "raised_at": datetime.now(UTC).isoformat(),
        "resolved": False,
    }
    _alerts.append(alert)


# =============================================================================
# Internal
# =============================================================================


def _get_record(capture_id: str) -> LineageCaptureRecord:
    record = _captures.get(capture_id)
    if not record:
        raise CaptureNotFound(f"Capture record {capture_id} not found")
    return record


# =============================================================================
# Exceptions
# =============================================================================


class LineageError(Exception):
    """Base lineage capture error."""


class CaptureNotFound(LineageError):
    """Capture record not found."""


class NoRetryableSteps(LineageError):
    """No steps available for retry."""


class PersistenceError(LineageError):
    """Failed to persist lineage data."""


class PermissionDenied(LineageError):
    """Authorization check failed."""


class StepNotFound(LineageError):
    """Capture step not found."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    """Reset all state for testing."""
    _captures.clear()
    _asset_index.clear()
    _alerts.clear()
    _inject_step_failures.clear()
    global _inject_permanent_failure
    _inject_permanent_failure = False


def _set_step_failure(step: CaptureStep, enabled: bool = True) -> None:
    """Inject failure for a specific step."""
    _inject_step_failures[step] = enabled


def _set_permanent_failure(enabled: bool = True) -> None:
    """Inject permanent failure for all steps."""
    global _inject_permanent_failure
    _inject_permanent_failure = enabled
