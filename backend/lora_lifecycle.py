"""LoRA Evaluation & Approval Lifecycle — Story 096.

Training completion never activates a model. Evaluation and authorized
approval are mandatory gates before any model can affect production.

Lifecycle:
    trained → evaluating → review_required → approved → deployable → active
                                           → rejected (can re-evaluate)
    active → superseded (when newer version is activated)

Key invariants:
    - Training completion → TRAINED (never directly active)
    - Evaluation requires real test assets and metrics (not simulation)
    - Only authorized workspace actors can approve
    - Only APPROVED versions can become DEPLOYABLE or ACTIVE
    - Every transition is audited and idempotent
    - Stale evaluation (artifact changed) invalidates approval path

DECISION-REQUIRED:
    - Final evaluation metric thresholds (not implemented — policy reference only)
    - Auto-approval criteria for specific quality scores (not implemented)
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


class LoRAStatus(str, Enum):
    TRAINED = "trained"                 # Training complete, not evaluated
    EVALUATING = "evaluating"           # Evaluation in progress
    REVIEW_REQUIRED = "review_required" # Evaluation done, needs human review
    APPROVED = "approved"               # Human approved for deployment
    DEPLOYABLE = "deployable"           # Ready to be assigned (not yet active)
    ACTIVE = "active"                   # Currently used in production
    REJECTED = "rejected"               # Failed evaluation or rejected by reviewer
    SUPERSEDED = "superseded"           # Replaced by newer version


class EvidenceType(str, Enum):
    REAL = "real"                       # Real test generation with actual assets
    SIMULATION = "simulation"           # Simulated (NEVER satisfies approval)


# =============================================================================
# Evaluation Record
# =============================================================================


@dataclass
class EvaluationRecord:
    """Evidence from LoRA evaluation — required before approval."""
    evaluation_id: str = field(default_factory=lambda: f"eval-{uuid.uuid4().hex[:12]}")
    lora_version_id: str = ""
    org_id: str = ""

    # Evidence type — simulation CANNOT satisfy production approval
    evidence_type: EvidenceType = EvidenceType.REAL

    # Test assets (must be real generated images, not placeholders)
    test_asset_ids: list[str] = field(default_factory=list)
    test_asset_count: int = 0

    # Metrics (policy-configurable — no hardcoded thresholds)
    scores: dict[str, float] = field(default_factory=dict)  # e.g. {"identity": 0.92, "quality": 0.85}
    policy_version: str = ""  # Which evaluation policy was used

    # Reviewer
    evaluated_by: str = ""    # User or system that ran evaluation
    evaluated_at: float | None = None

    # Completion
    is_complete: bool = False
    error: str | None = None

    # Artifact integrity — hash of the model file at evaluation time
    model_artifact_hash: str = ""

    @property
    def is_valid_for_approval(self) -> bool:
        """Can this evaluation satisfy the approval gate?"""
        return (
            self.is_complete
            and self.evidence_type == EvidenceType.REAL
            and self.test_asset_count > 0
            and len(self.test_asset_ids) > 0
            and bool(self.model_artifact_hash)
            and self.error is None
        )


# =============================================================================
# Approval Record
# =============================================================================


@dataclass
class ApprovalRecord:
    """Authorized approval decision for a LoRA version."""
    approval_id: str = field(default_factory=lambda: f"apv-{uuid.uuid4().hex[:12]}")
    lora_version_id: str = ""
    org_id: str = ""
    evaluation_id: str = ""  # Which evaluation this approval is based on

    # Approver
    approved_by: str = ""
    approved_at: float | None = None
    decision: str = ""  # "approved" | "rejected"
    reason: str = ""

    # Authorization check
    approver_authorized: bool = False


# =============================================================================
# LoRA Version
# =============================================================================


@dataclass
class LoRAVersion:
    """A versioned LoRA model with lifecycle tracking."""
    version_id: str = field(default_factory=lambda: f"lora-v-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    talent_id: str = ""
    model_name: str = ""
    version_number: int = 1

    # Status
    status: LoRAStatus = LoRAStatus.TRAINED

    # Artifact
    artifact_hash: str = ""  # SHA-256 of the .safetensors file
    storage_key: str = ""
    file_size_bytes: int = 0

    # Evaluation
    evaluation: EvaluationRecord | None = None

    # Approval
    approval: ApprovalRecord | None = None

    # Timing
    trained_at: float = field(default_factory=time.time)
    activated_at: float | None = None
    superseded_at: float | None = None

    # Audit trail
    transitions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_activatable(self) -> bool:
        """Can this version be activated for production?"""
        return self.status in (LoRAStatus.APPROVED, LoRAStatus.DEPLOYABLE)


# =============================================================================
# Store
# =============================================================================

_versions: dict[str, LoRAVersion] = {}
_authorized_approvers: set[str] = {"admin", "owner", "editor"}  # Role-based


# =============================================================================
# Lifecycle Management
# =============================================================================


def register_trained(
    org_id: str,
    talent_id: str,
    model_name: str,
    version_number: int,
    artifact_hash: str,
    storage_key: str,
    file_size_bytes: int = 0,
) -> LoRAVersion:
    """Register a newly trained LoRA version (status=TRAINED, never active)."""
    if not org_id or not talent_id or not artifact_hash:
        raise ValueError("org_id, talent_id, and artifact_hash are required")

    version = LoRAVersion(
        org_id=org_id,
        talent_id=talent_id,
        model_name=model_name,
        version_number=version_number,
        artifact_hash=artifact_hash,
        storage_key=storage_key,
        file_size_bytes=file_size_bytes,
        status=LoRAStatus.TRAINED,
    )

    _versions[version.version_id] = version
    _record_transition(version, LoRAStatus.TRAINED, "training_complete", "system")

    logger.info(f"LORA_REGISTERED: id={version.version_id} talent={talent_id} v{version_number}")
    return version


def start_evaluation(
    version_id: str,
    org_id: str,
    evaluated_by: str,
    policy_version: str = "1.0.0",
) -> LoRAVersion:
    """Start evaluation process for a trained LoRA."""
    version = _get_version(version_id, org_id)

    if version.status not in (LoRAStatus.TRAINED, LoRAStatus.REJECTED):
        raise InvalidTransition(f"Cannot evaluate from state {version.status.value}")

    version.status = LoRAStatus.EVALUATING
    version.evaluation = EvaluationRecord(
        lora_version_id=version_id,
        org_id=org_id,
        evaluated_by=evaluated_by,
        policy_version=policy_version,
        model_artifact_hash=version.artifact_hash,
    )

    _record_transition(version, LoRAStatus.EVALUATING, "evaluation_started", evaluated_by)
    return version


def complete_evaluation(
    version_id: str,
    org_id: str,
    test_asset_ids: list[str],
    scores: dict[str, float],
    evidence_type: EvidenceType = EvidenceType.REAL,
) -> LoRAVersion:
    """Complete evaluation with test results."""
    version = _get_version(version_id, org_id)

    if version.status != LoRAStatus.EVALUATING:
        raise InvalidTransition(f"Cannot complete evaluation from state {version.status.value}")

    if not version.evaluation:
        raise InvalidTransition("No evaluation record exists")

    version.evaluation.test_asset_ids = test_asset_ids
    version.evaluation.test_asset_count = len(test_asset_ids)
    version.evaluation.scores = scores
    version.evaluation.evidence_type = evidence_type
    version.evaluation.evaluated_at = time.time()
    version.evaluation.is_complete = True

    version.status = LoRAStatus.REVIEW_REQUIRED
    _record_transition(version, LoRAStatus.REVIEW_REQUIRED, "evaluation_complete", version.evaluation.evaluated_by)

    logger.info(f"LORA_EVALUATION_COMPLETE: id={version_id} type={evidence_type.value} assets={len(test_asset_ids)}")
    return version


# =============================================================================
# Approval Gate
# =============================================================================


def approve_version(
    version_id: str,
    org_id: str,
    approver_id: str,
    approver_role: str,
    reason: str = "",
) -> LoRAVersion:
    """Approve a LoRA version for production use.

    Gates:
    1. Version must be in REVIEW_REQUIRED state
    2. Evaluation must be complete and valid
    3. Evidence type must be REAL (not simulation)
    4. Test assets must exist
    5. Approver must be authorized
    6. Artifact hash must match evaluation (not stale)
    """
    version = _get_version(version_id, org_id)

    # Gate 1: Correct state
    if version.status != LoRAStatus.REVIEW_REQUIRED:
        if version.status == LoRAStatus.APPROVED:
            return version  # Idempotent
        raise InvalidTransition(f"Cannot approve from state {version.status.value}")

    # Gate 2: Evaluation exists and is complete
    if not version.evaluation or not version.evaluation.is_complete:
        raise ApprovalDenied("Evaluation is not complete")

    # Gate 3: Evidence type must be REAL
    if version.evaluation.evidence_type != EvidenceType.REAL:
        raise ApprovalDenied("Simulation evidence cannot satisfy production approval")

    # Gate 4: Test assets exist
    if not version.evaluation.test_asset_ids:
        raise ApprovalDenied("No test assets in evaluation record")

    # Gate 5: Approver authorized
    if approver_role not in _authorized_approvers:
        raise ApprovalDenied(f"Role '{approver_role}' is not authorized to approve LoRA versions")

    # Gate 6: Artifact integrity (not stale)
    if version.evaluation.model_artifact_hash != version.artifact_hash:
        raise ApprovalDenied("Evaluation is stale — model artifact changed since evaluation")

    # Approve
    version.status = LoRAStatus.APPROVED
    version.approval = ApprovalRecord(
        lora_version_id=version_id,
        org_id=org_id,
        evaluation_id=version.evaluation.evaluation_id,
        approved_by=approver_id,
        approved_at=time.time(),
        decision="approved",
        reason=reason,
        approver_authorized=True,
    )

    _record_transition(version, LoRAStatus.APPROVED, "approved", approver_id)
    logger.info(f"LORA_APPROVED: id={version_id} by={approver_id}")
    return version


def reject_version(
    version_id: str,
    org_id: str,
    rejector_id: str,
    rejector_role: str,
    reason: str,
) -> LoRAVersion:
    """Reject a LoRA version (can be re-evaluated later)."""
    version = _get_version(version_id, org_id)

    if version.status not in (LoRAStatus.REVIEW_REQUIRED, LoRAStatus.EVALUATING):
        if version.status == LoRAStatus.REJECTED:
            return version  # Idempotent
        raise InvalidTransition(f"Cannot reject from state {version.status.value}")

    if rejector_role not in _authorized_approvers:
        raise ApprovalDenied(f"Role '{rejector_role}' is not authorized to reject")

    version.status = LoRAStatus.REJECTED
    version.approval = ApprovalRecord(
        lora_version_id=version_id,
        org_id=org_id,
        evaluation_id=version.evaluation.evaluation_id if version.evaluation else "",
        approved_by=rejector_id,
        approved_at=time.time(),
        decision="rejected",
        reason=reason,
        approver_authorized=True,
    )

    _record_transition(version, LoRAStatus.REJECTED, "rejected", rejector_id)
    logger.info(f"LORA_REJECTED: id={version_id} by={rejector_id} reason={reason[:50]}")
    return version


# =============================================================================
# Activation (only from APPROVED/DEPLOYABLE)
# =============================================================================


def mark_deployable(version_id: str, org_id: str) -> LoRAVersion:
    """Mark an approved version as deployable (ready for assignment)."""
    version = _get_version(version_id, org_id)
    if version.status != LoRAStatus.APPROVED:
        raise InvalidTransition(f"Cannot mark deployable from state {version.status.value}")
    version.status = LoRAStatus.DEPLOYABLE
    _record_transition(version, LoRAStatus.DEPLOYABLE, "marked_deployable", "system")
    return version


def activate_version(version_id: str, org_id: str, activated_by: str) -> LoRAVersion:
    """Activate a version for production use.

    Only APPROVED or DEPLOYABLE versions can be activated.
    """
    version = _get_version(version_id, org_id)

    if not version.is_activatable:
        raise InvalidTransition(
            f"Cannot activate from state {version.status.value}. "
            f"Only approved or deployable versions can be activated."
        )

    version.status = LoRAStatus.ACTIVE
    version.activated_at = time.time()
    _record_transition(version, LoRAStatus.ACTIVE, "activated", activated_by)

    logger.info(f"LORA_ACTIVATED: id={version_id} by={activated_by}")
    return version


def supersede_version(version_id: str, org_id: str, superseded_by: str) -> LoRAVersion:
    """Mark a version as superseded (replaced by newer)."""
    version = _get_version(version_id, org_id)
    if version.status != LoRAStatus.ACTIVE:
        return version  # Only active versions can be superseded
    version.status = LoRAStatus.SUPERSEDED
    version.superseded_at = time.time()
    _record_transition(version, LoRAStatus.SUPERSEDED, "superseded", superseded_by)
    return version


# =============================================================================
# Query
# =============================================================================


def get_version(version_id: str, org_id: str) -> LoRAVersion | None:
    """Get a LoRA version with tenant isolation."""
    v = _versions.get(version_id)
    if not v or v.org_id != org_id:
        return None
    return v


def get_active_version(talent_id: str, org_id: str) -> LoRAVersion | None:
    """Get the currently active LoRA for a talent."""
    for v in _versions.values():
        if v.org_id == org_id and v.talent_id == talent_id and v.status == LoRAStatus.ACTIVE:
            return v
    return None


# =============================================================================
# Helpers
# =============================================================================


def _get_version(version_id: str, org_id: str) -> LoRAVersion:
    v = _versions.get(version_id)
    if not v or v.org_id != org_id:
        raise VersionNotFound(f"LoRA version {version_id} not found")
    return v


def _record_transition(version: LoRAVersion, to_status: LoRAStatus, reason: str, actor: str) -> None:
    version.transitions.append({
        "to": to_status.value,
        "reason": reason,
        "actor": actor,
        "at": time.time(),
    })


# =============================================================================
# Exceptions
# =============================================================================


class LoRALifecycleError(Exception):
    """Base LoRA lifecycle error."""


class VersionNotFound(LoRALifecycleError):
    """Version not found or cross-tenant."""


class InvalidTransition(LoRALifecycleError):
    """Invalid state transition."""


class ApprovalDenied(LoRALifecycleError):
    """Approval gate not satisfied."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _versions.clear()
