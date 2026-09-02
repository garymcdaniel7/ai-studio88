"""Full Production Pipeline — Story 112.

Multi-stage orchestration from planning through verified export. Each stage
has explicit prerequisites, approval gates, cost tracking, and retry behavior.

Stage graph (default):
    PLANNING → STORYBOARD → IMAGE_GEN → VOICE → MUSIC → ASSEMBLY → EXPORT

Each stage:
    - Has prerequisites (prior stages must be complete/approved)
    - May require approval before execution (DECISION-REQUIRED: which stages)
    - Tracks cost independently
    - Can be retried without erasing verified prior outputs
    - Can be cancelled (doesn't erase completed siblings)

Final completion:
    - Requires verified persisted export asset with full lineage
    - All prior stages must be complete or explicitly skipped

DECISION-REQUIRED:
    - Which stages require mandatory approval vs auto-advance
    - Whether skipped stages affect final quality designation
    - Budget enforcement behavior (hard block vs warning)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class StageType(str, Enum):
    PLANNING = "planning"
    STORYBOARD = "storyboard"
    IMAGE_GEN = "image_gen"
    VOICE = "voice"
    MUSIC = "music"
    ASSEMBLY = "assembly"
    EXPORT = "export"


class StageStatus(str, Enum):
    PENDING = "pending"               # Waiting for prerequisites
    READY = "ready"                   # Prerequisites met, can execute
    AWAITING_APPROVAL = "awaiting_approval"  # Needs approval to proceed
    APPROVED = "approved"             # Approved, executing
    RUNNING = "running"               # Active execution
    COMPLETED = "completed"           # Successfully done
    FAILED = "failed"                 # Failed (retryable)
    SKIPPED = "skipped"               # Explicitly skipped
    CANCELLED = "cancelled"           # Cancelled by user


class ProductionStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    PARTIAL = "partial"               # Some stages skipped/failed
    CANCELLED = "cancelled"
    BUDGET_EXCEEDED = "budget_exceeded"


# =============================================================================
# Stage Definition
# =============================================================================


@dataclass
class StageDefinition:
    """Definition of a production stage in the dependency graph."""
    stage_type: StageType
    prerequisites: list[StageType] = field(default_factory=list)
    requires_approval: bool = False   # DECISION-REQUIRED: configurable
    optional: bool = False            # Can be skipped
    estimated_cost_usd: float = 0.0


# Default stage graph
DEFAULT_STAGES: list[StageDefinition] = [
    StageDefinition(StageType.PLANNING, prerequisites=[], requires_approval=False),
    StageDefinition(StageType.STORYBOARD, prerequisites=[StageType.PLANNING], requires_approval=True),
    StageDefinition(StageType.IMAGE_GEN, prerequisites=[StageType.STORYBOARD], requires_approval=False),
    StageDefinition(StageType.VOICE, prerequisites=[StageType.STORYBOARD], requires_approval=False, optional=True),
    StageDefinition(StageType.MUSIC, prerequisites=[StageType.STORYBOARD], requires_approval=False, optional=True),
    StageDefinition(StageType.ASSEMBLY, prerequisites=[StageType.IMAGE_GEN], requires_approval=True),
    StageDefinition(StageType.EXPORT, prerequisites=[StageType.ASSEMBLY], requires_approval=False),
]


# =============================================================================
# Stage Instance
# =============================================================================


@dataclass
class ProductionStage:
    """A stage instance within a production."""
    stage_id: str = field(default_factory=lambda: f"stg-{uuid.uuid4().hex[:10]}")
    stage_type: StageType = StageType.PLANNING
    status: StageStatus = StageStatus.PENDING
    prerequisites: list[StageType] = field(default_factory=list)
    requires_approval: bool = False
    optional: bool = False

    # Approval
    approved_by: str | None = None
    approved_at: float | None = None

    # Execution
    job_id: str | None = None
    output_asset_ids: list[str] = field(default_factory=list)

    # Cost
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0

    # Retry
    attempts: int = 0
    max_attempts: int = 3
    error: str | None = None

    # Timing
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (StageStatus.COMPLETED, StageStatus.SKIPPED, StageStatus.CANCELLED)

    @property
    def is_retryable(self) -> bool:
        return self.status == StageStatus.FAILED and self.attempts < self.max_attempts

    @property
    def is_blocking(self) -> bool:
        """Is this stage blocking downstream progress?"""
        return self.status in (StageStatus.AWAITING_APPROVAL, StageStatus.FAILED)


# =============================================================================
# Full Production
# =============================================================================


@dataclass
class FullProduction:
    """A complete multi-stage production with dependency tracking."""
    production_id: str = field(default_factory=lambda: f"fp-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    user_id: str = ""
    project_id: str = ""
    storyboard_id: str = ""
    context_package_id: str = ""
    plan_version: int = 1

    # Status
    status: ProductionStatus = ProductionStatus.DRAFT

    # Stages (ordered)
    stages: dict[StageType, ProductionStage] = field(default_factory=dict)

    # Budget
    budget_usd: float = 0.0
    total_cost_usd: float = 0.0

    # Export
    export_asset_id: str | None = None
    export_verified: bool = False

    # Timing
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    # Idempotency
    idempotency_key: str | None = None

    @property
    def progress_pct(self) -> int:
        if not self.stages:
            return 0
        completed = sum(1 for s in self.stages.values() if s.is_terminal)
        return int((completed / len(self.stages)) * 100)

    @property
    def all_required_complete(self) -> bool:
        """All non-optional stages are complete."""
        for stage in self.stages.values():
            if not stage.optional and stage.status != StageStatus.COMPLETED:
                return False
        return True


# =============================================================================
# Store
# =============================================================================

_productions: dict[str, FullProduction] = {}


# =============================================================================
# Production API
# =============================================================================


def create_full_production(
    org_id: str,
    user_id: str,
    project_id: str,
    storyboard_id: str,
    context_package_id: str,
    budget_usd: float = 0.0,
    stage_overrides: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> FullProduction:
    """Create a full production with default stage graph."""
    if not org_id or not user_id:
        raise ValueError("org_id and user_id are required")

    if idempotency_key:
        existing = _find_by_idempotency(org_id, idempotency_key)
        if existing:
            return existing

    prod = FullProduction(
        org_id=org_id,
        user_id=user_id,
        project_id=project_id,
        storyboard_id=storyboard_id,
        context_package_id=context_package_id,
        budget_usd=budget_usd,
        idempotency_key=idempotency_key,
    )

    # Build stages from default graph
    for defn in DEFAULT_STAGES:
        stage = ProductionStage(
            stage_type=defn.stage_type,
            prerequisites=list(defn.prerequisites),
            requires_approval=defn.requires_approval,
            optional=defn.optional,
            estimated_cost_usd=defn.estimated_cost_usd,
        )
        prod.stages[defn.stage_type] = stage

    # First stage with no prerequisites is immediately READY
    _update_ready_stages(prod)

    _productions[prod.production_id] = prod
    logger.info(f"FULL_PRODUCTION_CREATED: id={prod.production_id} stages={len(prod.stages)}")
    return prod


def start_production(production_id: str, org_id: str) -> FullProduction:
    """Activate a draft production."""
    prod = _get_production(production_id, org_id)
    if prod.status != ProductionStatus.DRAFT:
        return prod  # Idempotent
    prod.status = ProductionStatus.ACTIVE
    return prod


# =============================================================================
# Stage Lifecycle
# =============================================================================


def approve_stage(production_id: str, stage_type: StageType, org_id: str, approver_id: str) -> ProductionStage:
    """Approve a stage that requires approval before execution."""
    prod = _get_production(production_id, org_id)
    stage = _get_stage(prod, stage_type)

    if stage.status != StageStatus.AWAITING_APPROVAL:
        if stage.status == StageStatus.APPROVED:
            return stage  # Idempotent
        raise InvalidStageState(f"Stage {stage_type.value} not awaiting approval (status={stage.status.value})")

    stage.status = StageStatus.APPROVED
    stage.approved_by = approver_id
    stage.approved_at = time.time()

    logger.info(f"STAGE_APPROVED: prod={production_id} stage={stage_type.value} by={approver_id}")
    return stage


def start_stage(production_id: str, stage_type: StageType, org_id: str, job_id: str = "") -> ProductionStage:
    """Start executing a stage."""
    prod = _get_production(production_id, org_id)
    stage = _get_stage(prod, stage_type)

    if stage.status not in (StageStatus.READY, StageStatus.APPROVED):
        raise InvalidStageState(f"Stage {stage_type.value} not ready (status={stage.status.value})")

    # Budget check
    if prod.budget_usd > 0 and prod.total_cost_usd >= prod.budget_usd:
        prod.status = ProductionStatus.BUDGET_EXCEEDED
        raise BudgetExceeded(f"Budget ${prod.budget_usd:.2f} exceeded (spent ${prod.total_cost_usd:.2f})")

    stage.status = StageStatus.RUNNING
    stage.job_id = job_id
    stage.started_at = time.time()
    stage.attempts += 1

    if prod.status == ProductionStatus.DRAFT:
        prod.status = ProductionStatus.ACTIVE

    return stage


def complete_stage(
    production_id: str,
    stage_type: StageType,
    org_id: str,
    output_asset_ids: list[str] | None = None,
    cost_usd: float = 0.0,
) -> ProductionStage:
    """Mark a stage as completed with outputs."""
    prod = _get_production(production_id, org_id)
    stage = _get_stage(prod, stage_type)

    if stage.status == StageStatus.CANCELLED:
        return stage  # Don't overwrite cancel

    stage.status = StageStatus.COMPLETED
    stage.output_asset_ids = output_asset_ids or []
    stage.actual_cost_usd = cost_usd
    stage.completed_at = time.time()

    # Update total cost
    prod.total_cost_usd = round(sum(s.actual_cost_usd for s in prod.stages.values()), 4)

    # Advance downstream stages
    _update_ready_stages(prod)

    # Check overall completion
    _check_production_completion(prod)

    logger.info(f"STAGE_COMPLETED: prod={production_id} stage={stage_type.value} cost=${cost_usd:.4f}")
    return stage


def fail_stage(production_id: str, stage_type: StageType, org_id: str, error: str) -> ProductionStage:
    """Mark a stage as failed."""
    prod = _get_production(production_id, org_id)
    stage = _get_stage(prod, stage_type)

    if stage.status == StageStatus.CANCELLED:
        return stage

    stage.status = StageStatus.FAILED
    stage.error = error[:500]
    stage.completed_at = time.time()

    return stage


def retry_stage(production_id: str, stage_type: StageType, org_id: str) -> ProductionStage:
    """Retry a failed stage without erasing prior verified outputs."""
    prod = _get_production(production_id, org_id)
    stage = _get_stage(prod, stage_type)

    if not stage.is_retryable:
        raise StageNotRetryable(f"Stage {stage_type.value} not retryable")

    stage.status = StageStatus.READY
    stage.error = None
    stage.started_at = None
    stage.completed_at = None

    # Restore production to active
    if prod.status in (ProductionStatus.PARTIAL, ProductionStatus.BUDGET_EXCEEDED):
        prod.status = ProductionStatus.ACTIVE

    return stage


def skip_stage(production_id: str, stage_type: StageType, org_id: str) -> ProductionStage:
    """Skip an optional stage."""
    prod = _get_production(production_id, org_id)
    stage = _get_stage(prod, stage_type)

    if not stage.optional:
        raise InvalidStageState(f"Stage {stage_type.value} is not optional — cannot skip")

    stage.status = StageStatus.SKIPPED
    stage.completed_at = time.time()

    _update_ready_stages(prod)
    _check_production_completion(prod)
    return stage


def cancel_stage(production_id: str, stage_type: StageType, org_id: str) -> ProductionStage:
    """Cancel a stage."""
    prod = _get_production(production_id, org_id)
    stage = _get_stage(prod, stage_type)

    if stage.is_terminal:
        return stage  # Idempotent

    stage.status = StageStatus.CANCELLED
    stage.completed_at = time.time()
    return stage


# =============================================================================
# Export Verification
# =============================================================================


def verify_export(
    production_id: str,
    org_id: str,
    export_asset_id: str,
    storage_verified: bool = True,
) -> FullProduction:
    """Verify the final export asset — required for production completion.

    Export must:
    1. Have a registered asset ID
    2. Be storage-verified (B2 HEAD check passed)
    3. All required stages must be complete
    """
    prod = _get_production(production_id, org_id)

    if not export_asset_id:
        raise ExportVerificationFailed("export_asset_id is required")
    if not storage_verified:
        raise ExportVerificationFailed("Export asset storage verification failed")

    prod.export_asset_id = export_asset_id
    prod.export_verified = True

    _check_production_completion(prod)
    return prod


# =============================================================================
# Cancel Production
# =============================================================================


def cancel_production(production_id: str, org_id: str) -> FullProduction:
    """Cancel entire production — cancels all non-terminal stages."""
    prod = _get_production(production_id, org_id)

    if prod.status == ProductionStatus.CANCELLED:
        return prod  # Idempotent

    for stage in prod.stages.values():
        if not stage.is_terminal:
            stage.status = StageStatus.CANCELLED
            stage.completed_at = time.time()

    prod.status = ProductionStatus.CANCELLED
    prod.completed_at = time.time()

    logger.info(f"PRODUCTION_CANCELLED: id={production_id}")
    return prod


# =============================================================================
# Progress / Recovery
# =============================================================================


def get_production_state(production_id: str, org_id: str) -> dict[str, Any] | None:
    """Get full production state for UI recovery/reconnect."""
    prod = _productions.get(production_id)
    if not prod or prod.org_id != org_id:
        return None

    return {
        "production_id": prod.production_id,
        "status": prod.status.value,
        "progress_pct": prod.progress_pct,
        "budget_usd": prod.budget_usd,
        "total_cost_usd": prod.total_cost_usd,
        "export_asset_id": prod.export_asset_id,
        "export_verified": prod.export_verified,
        "stages": {
            st.value: {
                "status": stage.status.value,
                "requires_approval": stage.requires_approval,
                "optional": stage.optional,
                "output_asset_ids": stage.output_asset_ids,
                "actual_cost_usd": stage.actual_cost_usd,
                "attempts": stage.attempts,
                "error": stage.error,
                "is_retryable": stage.is_retryable,
                "approved_by": stage.approved_by,
            }
            for st, stage in prod.stages.items()
        },
    }


# =============================================================================
# Internal
# =============================================================================


def _update_ready_stages(prod: FullProduction) -> None:
    """Update stage statuses based on prerequisite completion."""
    for stage in prod.stages.values():
        if stage.status != StageStatus.PENDING:
            continue

        # Check all prerequisites are complete (or skipped)
        prereqs_met = all(
            prod.stages[prereq].status in (StageStatus.COMPLETED, StageStatus.SKIPPED)
            for prereq in stage.prerequisites
            if prereq in prod.stages
        )

        if prereqs_met:
            if stage.requires_approval:
                stage.status = StageStatus.AWAITING_APPROVAL
            else:
                stage.status = StageStatus.READY


def _check_production_completion(prod: FullProduction) -> None:
    """Check if production is complete."""
    if prod.all_required_complete and prod.export_verified:
        prod.status = ProductionStatus.COMPLETED
        prod.completed_at = time.time()
        logger.info(f"PRODUCTION_COMPLETED: id={prod.production_id}")
    elif all(s.is_terminal for s in prod.stages.values()):
        # All terminal but not all completed — partial
        if prod.status != ProductionStatus.CANCELLED:
            prod.status = ProductionStatus.PARTIAL


def _get_production(production_id: str, org_id: str) -> FullProduction:
    prod = _productions.get(production_id)
    if not prod or prod.org_id != org_id:
        raise ProductionNotFound(f"Production {production_id} not found")
    return prod


def _get_stage(prod: FullProduction, stage_type: StageType) -> ProductionStage:
    stage = prod.stages.get(stage_type)
    if not stage:
        raise StageNotFound(f"Stage {stage_type.value} not found")
    return stage


def _find_by_idempotency(org_id: str, key: str) -> FullProduction | None:
    for prod in _productions.values():
        if prod.org_id == org_id and prod.idempotency_key == key:
            return prod
    return None


# =============================================================================
# Exceptions
# =============================================================================


class ProductionError(Exception):
    """Base production error."""


class ProductionNotFound(ProductionError):
    """Not found or cross-tenant."""


class StageNotFound(ProductionError):
    """Stage type not in graph."""


class InvalidStageState(ProductionError):
    """Invalid state for operation."""


class StageNotRetryable(ProductionError):
    """Stage cannot be retried."""


class BudgetExceeded(ProductionError):
    """Production budget exceeded."""


class ExportVerificationFailed(ProductionError):
    """Export verification failed."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _productions.clear()
