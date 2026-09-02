"""Unified Plan-to-Execution Lifecycle — Story 088.

One governed contract from creative planning through context assembly to
canonical generation. Planning proposes; approval locks; execution references
the approved immutable package.

Lifecycle:
    plan_draft → plan_approved → context_assembled → job_submitted → completed
                      ↓
              plan_revised (requires new approval)

Rules:
    1. Execution MUST reference an approved plan version
    2. Plan edits after approval require a new version + re-approval
    3. Direct caller-supplied prompts cannot bypass the lifecycle
    4. All surfaces (Create, Storyboard, Quick Edit, Hermes) use adapters
    5. Audit links: plan → context_package → job → asset → snapshot

Surfaces:
    - Create: plan is implicit (single-shot, auto-approved)
    - Storyboard: plan is the storyboard definition (multi-shot)
    - Quick Edit: plan references source asset + edit intent
    - Hermes: plan from AI requires governance approval
    - Full Production: plan is the production brief
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


class PlanStatus(str, Enum):
    DRAFT = "draft"                 # Being edited
    PENDING_APPROVAL = "pending_approval"  # Submitted for approval
    APPROVED = "approved"           # Locked for execution
    REVISED = "revised"             # Edited after approval (needs re-approval)
    CANCELLED = "cancelled"         # Abandoned
    EXECUTED = "executed"           # Job submitted (terminal)


class ApprovalType(str, Enum):
    AUTO = "auto"                   # Auto-approved (Create, Quick Edit)
    USER = "user"                   # User explicitly approved
    GOVERNANCE = "governance"       # Hermes/AI — requires governance approval


class Surface(str, Enum):
    CREATE = "create"
    STORYBOARD = "storyboard"
    QUICK_EDIT = "quick_edit"
    HERMES = "hermes"
    FULL_PRODUCTION = "full_production"
    BATCH = "batch"


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class PlanVersion:
    """A versioned snapshot of plan content."""
    version: int = 1
    content: dict[str, Any] = field(default_factory=dict)
    author_id: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class CreativePlan:
    """A creative plan that governs generation execution."""
    plan_id: str = field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    user_id: str = ""
    surface: Surface = Surface.CREATE
    status: PlanStatus = PlanStatus.DRAFT

    # Versioned content
    versions: list[PlanVersion] = field(default_factory=list)
    current_version: int = 0

    # Approval
    approval_type: ApprovalType = ApprovalType.AUTO
    approved_by: str | None = None
    approved_at: float | None = None
    approved_version: int | None = None  # Which version was approved

    # Context linkage
    context_package_id: str | None = None

    # Execution linkage
    job_ids: list[str] = field(default_factory=list)

    # Timing
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def effective_content(self) -> dict[str, Any]:
        if not self.versions:
            return {}
        return self.versions[-1].content

    @property
    def is_executable(self) -> bool:
        """Plan is executable only when approved and not stale."""
        return (
            self.status == PlanStatus.APPROVED
            and self.approved_version == self.current_version
        )


@dataclass
class ExecutionRequest:
    """A request to execute through the lifecycle."""
    plan_id: str
    org_id: str
    user_id: str
    context_package_id: str | None = None


@dataclass
class LifecycleAudit:
    """Audit trail linking plan → context → job → asset."""
    plan_id: str = ""
    plan_version: int = 0
    context_package_id: str = ""
    job_id: str = ""
    asset_id: str | None = None
    snapshot_id: str | None = None
    surface: str = ""
    org_id: str = ""
    created_at: float = field(default_factory=time.time)


# =============================================================================
# Store
# =============================================================================

_plans: dict[str, CreativePlan] = {}
_audit_trail: list[LifecycleAudit] = []


# =============================================================================
# Plan Management
# =============================================================================


def create_plan(
    org_id: str,
    user_id: str,
    surface: Surface,
    content: dict[str, Any],
    auto_approve: bool = False,
) -> CreativePlan:
    """Create a creative plan.

    For simple surfaces (Create, Quick Edit), auto_approve=True makes
    the plan immediately executable without an explicit approval step.
    """
    if not org_id or not user_id:
        raise ValueError("org_id and user_id are required")

    plan = CreativePlan(
        org_id=org_id,
        user_id=user_id,
        surface=surface,
        approval_type=_approval_type_for_surface(surface),
    )

    version = PlanVersion(version=1, content=content, author_id=user_id)
    plan.versions.append(version)
    plan.current_version = 1

    if auto_approve:
        plan.status = PlanStatus.APPROVED
        plan.approved_by = user_id
        plan.approved_at = time.time()
        plan.approved_version = 1
    else:
        plan.status = PlanStatus.DRAFT

    _plans[plan.plan_id] = plan
    logger.info(f"PLAN_CREATED: id={plan.plan_id} surface={surface.value} auto_approve={auto_approve}")
    return plan


def revise_plan(
    plan_id: str,
    org_id: str,
    user_id: str,
    content: dict[str, Any],
) -> CreativePlan:
    """Revise a plan — creates a new version and invalidates approval."""
    plan = _get_plan(plan_id, org_id)

    if plan.status == PlanStatus.EXECUTED:
        raise PlanExecuted("Cannot revise an executed plan")
    if plan.status == PlanStatus.CANCELLED:
        raise PlanCancelled("Cannot revise a cancelled plan")

    new_version = PlanVersion(
        version=plan.current_version + 1,
        content=content,
        author_id=user_id,
    )
    plan.versions.append(new_version)
    plan.current_version = new_version.version
    plan.status = PlanStatus.REVISED  # Needs re-approval
    plan.updated_at = time.time()

    logger.info(f"PLAN_REVISED: id={plan_id} version={new_version.version}")
    return plan


def approve_plan(
    plan_id: str,
    org_id: str,
    approver_id: str,
) -> CreativePlan:
    """Approve a plan for execution — locks the current version."""
    plan = _get_plan(plan_id, org_id)

    if plan.status == PlanStatus.EXECUTED:
        raise PlanExecuted("Cannot approve an already-executed plan")

    plan.status = PlanStatus.APPROVED
    plan.approved_by = approver_id
    plan.approved_at = time.time()
    plan.approved_version = plan.current_version
    plan.updated_at = time.time()

    logger.info(f"PLAN_APPROVED: id={plan_id} version={plan.current_version} by={approver_id}")
    return plan


def cancel_plan(plan_id: str, org_id: str) -> CreativePlan:
    """Cancel a plan."""
    plan = _get_plan(plan_id, org_id)
    if plan.status == PlanStatus.EXECUTED:
        return plan  # Already terminal
    plan.status = PlanStatus.CANCELLED
    plan.updated_at = time.time()
    return plan


# =============================================================================
# Execution Gate
# =============================================================================


def submit_for_execution(
    plan_id: str,
    org_id: str,
    user_id: str,
    context_package_id: str,
    job_id: str,
) -> LifecycleAudit:
    """Submit a plan for execution through the canonical lifecycle.

    Validates:
    1. Plan exists and belongs to org
    2. Plan is approved (not draft, revised, or cancelled)
    3. Approved version matches current version (not stale)
    4. Context package is linked

    Returns an audit record linking everything together.
    """
    plan = _get_plan(plan_id, org_id)

    # Gate: plan must be approved
    if plan.status != PlanStatus.APPROVED:
        raise ExecutionDenied(
            f"Plan not approved (status={plan.status.value}). "
            f"{'Revised after approval — re-approval required.' if plan.status == PlanStatus.REVISED else ''}"
        )

    # Gate: approved version must match current (detect stale approval)
    if plan.approved_version != plan.current_version:
        raise ExecutionDenied(
            f"Plan was revised after approval (approved v{plan.approved_version}, "
            f"current v{plan.current_version}). Re-approval required."
        )

    # Gate: context package required
    if not context_package_id:
        raise ExecutionDenied("context_package_id is required for execution")

    # Mark executed
    plan.status = PlanStatus.EXECUTED
    plan.context_package_id = context_package_id
    plan.job_ids.append(job_id)
    plan.updated_at = time.time()

    # Create audit record
    audit = LifecycleAudit(
        plan_id=plan_id,
        plan_version=plan.current_version,
        context_package_id=context_package_id,
        job_id=job_id,
        surface=plan.surface.value,
        org_id=org_id,
    )
    _audit_trail.append(audit)

    logger.info(
        f"PLAN_EXECUTED: plan={plan_id} version={plan.current_version} "
        f"package={context_package_id} job={job_id}"
    )
    return audit


# =============================================================================
# Surface Adapters
# =============================================================================


def submit_from_create_surface(
    org_id: str,
    user_id: str,
    content: dict[str, Any],
    context_package_id: str,
    job_id: str,
) -> LifecycleAudit:
    """Create surface: auto-approve and execute in one step."""
    plan = create_plan(org_id, user_id, Surface.CREATE, content, auto_approve=True)
    return submit_for_execution(plan.plan_id, org_id, user_id, context_package_id, job_id)


def submit_from_storyboard_surface(
    org_id: str,
    user_id: str,
    storyboard_content: dict[str, Any],
    context_package_id: str,
    job_ids: list[str],
) -> list[LifecycleAudit]:
    """Storyboard surface: one plan, multiple jobs (one per shot)."""
    plan = create_plan(org_id, user_id, Surface.STORYBOARD, storyboard_content, auto_approve=True)
    audits = []
    for job_id in job_ids:
        # Reset status for each job in batch (plan can have multiple executions)
        plan.status = PlanStatus.APPROVED
        audit = submit_for_execution(plan.plan_id, org_id, user_id, context_package_id, job_id)
        audits.append(audit)
    return audits


def submit_from_hermes_surface(
    org_id: str,
    user_id: str,
    content: dict[str, Any],
    approval_token: str,
    context_package_id: str,
    job_id: str,
) -> LifecycleAudit:
    """Hermes surface: AI-initiated, requires governance approval.

    The approval_token proves governance has approved this action.
    """
    if not approval_token:
        raise ExecutionDenied("Hermes execution requires governance approval token")

    plan = create_plan(org_id, user_id, Surface.HERMES, content, auto_approve=False)
    # Governance approval via token
    approve_plan(plan.plan_id, org_id, f"governance:{approval_token}")
    return submit_for_execution(plan.plan_id, org_id, user_id, context_package_id, job_id)


def submit_from_quick_edit_surface(
    org_id: str,
    user_id: str,
    content: dict[str, Any],
    context_package_id: str,
    job_id: str,
) -> LifecycleAudit:
    """Quick Edit surface: auto-approve and execute."""
    plan = create_plan(org_id, user_id, Surface.QUICK_EDIT, content, auto_approve=True)
    return submit_for_execution(plan.plan_id, org_id, user_id, context_package_id, job_id)


# =============================================================================
# Bypass Rejection
# =============================================================================


def reject_direct_submission(
    org_id: str,
    user_id: str,
    raw_params: dict[str, Any],
) -> dict[str, str]:
    """Reject a direct caller submission that bypasses the lifecycle.

    Returns error information explaining why and how to fix.
    """
    logger.warning(f"BYPASS_REJECTED: org={org_id} user={user_id}")
    return {
        "error": "direct_submission_rejected",
        "message": "Direct generation submission is not allowed. Use the plan-to-execution lifecycle.",
        "fix": "Create a plan, get approval, assemble context package, then submit for execution.",
    }


# =============================================================================
# Query
# =============================================================================


def get_plan(plan_id: str, org_id: str) -> CreativePlan | None:
    """Get a plan with tenant isolation."""
    plan = _plans.get(plan_id)
    if not plan or plan.org_id != org_id:
        return None
    return plan


def get_audit_trail(org_id: str, plan_id: str | None = None) -> list[LifecycleAudit]:
    """Get audit trail, optionally filtered by plan."""
    trail = [a for a in _audit_trail if a.org_id == org_id]
    if plan_id:
        trail = [a for a in trail if a.plan_id == plan_id]
    return trail


def link_asset_to_audit(job_id: str, asset_id: str, snapshot_id: str | None = None) -> None:
    """Link a completed asset back to the audit trail."""
    for audit in _audit_trail:
        if audit.job_id == job_id:
            audit.asset_id = asset_id
            audit.snapshot_id = snapshot_id
            break


# =============================================================================
# Helpers
# =============================================================================


def _get_plan(plan_id: str, org_id: str) -> CreativePlan:
    plan = _plans.get(plan_id)
    if not plan or plan.org_id != org_id:
        raise PlanNotFound(f"Plan {plan_id} not found")
    return plan


def _approval_type_for_surface(surface: Surface) -> ApprovalType:
    if surface in (Surface.CREATE, Surface.QUICK_EDIT):
        return ApprovalType.AUTO
    elif surface == Surface.HERMES:
        return ApprovalType.GOVERNANCE
    return ApprovalType.USER


# =============================================================================
# Exceptions
# =============================================================================


class LifecycleError(Exception):
    """Base lifecycle error."""


class PlanNotFound(LifecycleError):
    """Plan not found or cross-tenant."""


class PlanExecuted(LifecycleError):
    """Plan already executed (terminal)."""


class PlanCancelled(LifecycleError):
    """Plan was cancelled."""


class ExecutionDenied(LifecycleError):
    """Execution requirements not met."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _plans.clear()
    _audit_trail.clear()
