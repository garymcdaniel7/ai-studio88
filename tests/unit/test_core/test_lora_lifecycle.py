"""LoRA evaluation & approval lifecycle tests — Story 096.

Tests prove:
  - Training creates TRAINED status (never active)
  - Simulation evidence cannot satisfy approval
  - Missing evaluation blocks approval
  - Stale evaluation (artifact changed) blocks approval
  - Unauthorized approver rejected
  - Duplicate approval is idempotent
  - Rejection allows re-evaluation
  - Cross-workspace approval denied
  - Only approved/deployable can activate
  - Transitions are audited
  - Missing test assets block approval
"""

import pytest

from backend.lora_lifecycle import (
    ApprovalDenied,
    EvidenceType,
    InvalidTransition,
    LoRAStatus,
    VersionNotFound,
    _reset_store,
    activate_version,
    approve_version,
    complete_evaluation,
    get_active_version,
    get_version,
    mark_deployable,
    register_trained,
    reject_version,
    start_evaluation,
    supersede_version,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
TALENT = "talent-001"


def _trained_version(**overrides) -> str:
    """Create a trained version and return its ID."""
    defaults = dict(
        org_id=ORG,
        talent_id=TALENT,
        model_name="talent_lora",
        version_number=1,
        artifact_hash="abc123def456",
        storage_key=f"{ORG}/models/{TALENT}/v1.safetensors",
    )
    defaults.update(overrides)
    v = register_trained(**defaults)
    return v.version_id


def _evaluated_version(evidence_type=EvidenceType.REAL, test_assets=None) -> str:
    """Create and evaluate a version."""
    vid = _trained_version()
    start_evaluation(vid, ORG, "evaluator-001")
    complete_evaluation(
        vid, ORG,
        test_asset_ids=test_assets or ["ast-test-1", "ast-test-2", "ast-test-3"],
        scores={"identity": 0.92, "quality": 0.85},
        evidence_type=evidence_type,
    )
    return vid


# =============================================================================
# Training Creates TRAINED (Never Active)
# =============================================================================


@pytest.mark.unit
class TestTrainingState:

    def test_register_creates_trained_status(self):
        vid = _trained_version()
        v = get_version(vid, ORG)
        assert v.status == LoRAStatus.TRAINED
        assert v.status != LoRAStatus.ACTIVE

    def test_trained_cannot_activate(self):
        vid = _trained_version()
        with pytest.raises(InvalidTransition, match="Only approved"):
            activate_version(vid, ORG, "user-001")


# =============================================================================
# Simulation Evidence Rejected
# =============================================================================


@pytest.mark.unit
class TestSimulationRejected:

    def test_simulation_cannot_satisfy_approval(self):
        vid = _evaluated_version(evidence_type=EvidenceType.SIMULATION)
        with pytest.raises(ApprovalDenied, match="Simulation"):
            approve_version(vid, ORG, "admin-001", "admin")


# =============================================================================
# Missing Evaluation
# =============================================================================


@pytest.mark.unit
class TestMissingEvaluation:

    def test_approve_without_evaluation_fails(self):
        vid = _trained_version()
        # Try to approve directly from TRAINED
        with pytest.raises(InvalidTransition):
            approve_version(vid, ORG, "admin-001", "admin")

    def test_incomplete_evaluation_blocks_approval(self):
        vid = _trained_version()
        start_evaluation(vid, ORG, "eval-001")
        # Don't complete evaluation — try approval
        with pytest.raises(InvalidTransition):
            approve_version(vid, ORG, "admin-001", "admin")

    def test_no_test_assets_blocks_approval(self):
        vid = _evaluated_version(test_assets=[])
        # Evaluation complete but no test assets
        v = get_version(vid, ORG)
        v.evaluation.test_asset_ids = []
        v.evaluation.test_asset_count = 0
        with pytest.raises(ApprovalDenied, match="test assets"):
            approve_version(vid, ORG, "admin-001", "admin")


# =============================================================================
# Stale Evidence
# =============================================================================


@pytest.mark.unit
class TestStaleEvidence:

    def test_artifact_change_invalidates_evaluation(self):
        vid = _evaluated_version()
        # Simulate: artifact hash changed after evaluation
        v = get_version(vid, ORG)
        v.artifact_hash = "new_hash_after_retrain"
        # Evaluation's model_artifact_hash no longer matches
        with pytest.raises(ApprovalDenied, match="stale"):
            approve_version(vid, ORG, "admin-001", "admin")


# =============================================================================
# Unauthorized Approver
# =============================================================================


@pytest.mark.unit
class TestUnauthorizedApprover:

    def test_viewer_cannot_approve(self):
        vid = _evaluated_version()
        with pytest.raises(ApprovalDenied, match="not authorized"):
            approve_version(vid, ORG, "viewer-001", "viewer")

    def test_admin_can_approve(self):
        vid = _evaluated_version()
        v = approve_version(vid, ORG, "admin-001", "admin")
        assert v.status == LoRAStatus.APPROVED

    def test_editor_can_approve(self):
        vid = _evaluated_version()
        v = approve_version(vid, ORG, "editor-001", "editor")
        assert v.status == LoRAStatus.APPROVED

    def test_viewer_cannot_reject(self):
        vid = _evaluated_version()
        with pytest.raises(ApprovalDenied, match="not authorized"):
            reject_version(vid, ORG, "viewer-001", "viewer", "bad quality")


# =============================================================================
# Duplicate Approval (Idempotent)
# =============================================================================


@pytest.mark.unit
class TestDuplicateApproval:

    def test_approve_already_approved_is_idempotent(self):
        vid = _evaluated_version()
        approve_version(vid, ORG, "admin-001", "admin")
        # Second approval — no error
        v = approve_version(vid, ORG, "admin-002", "admin")
        assert v.status == LoRAStatus.APPROVED

    def test_reject_already_rejected_is_idempotent(self):
        vid = _evaluated_version()
        reject_version(vid, ORG, "admin-001", "admin", "bad")
        v = reject_version(vid, ORG, "admin-001", "admin", "bad again")
        assert v.status == LoRAStatus.REJECTED


# =============================================================================
# Rejection & Re-evaluation
# =============================================================================


@pytest.mark.unit
class TestRejectionReevaluation:

    def test_rejected_can_be_reevaluated(self):
        vid = _evaluated_version()
        reject_version(vid, ORG, "admin-001", "admin", "needs work")
        # Start fresh evaluation
        start_evaluation(vid, ORG, "eval-002")
        complete_evaluation(vid, ORG, ["new-ast-1", "new-ast-2"], {"identity": 0.95})
        # Now can approve
        v = approve_version(vid, ORG, "admin-001", "admin")
        assert v.status == LoRAStatus.APPROVED


# =============================================================================
# Cross-Workspace
# =============================================================================


@pytest.mark.unit
class TestCrossWorkspace:

    def test_cross_workspace_get_returns_none(self):
        vid = _trained_version()
        assert get_version(vid, OTHER_ORG) is None

    def test_cross_workspace_approve_raises(self):
        vid = _evaluated_version()
        with pytest.raises(VersionNotFound):
            approve_version(vid, OTHER_ORG, "hacker", "admin")

    def test_cross_workspace_activate_raises(self):
        vid = _evaluated_version()
        approve_version(vid, ORG, "admin-001", "admin")
        with pytest.raises(VersionNotFound):
            activate_version(vid, OTHER_ORG, "hacker")


# =============================================================================
# Activation Gate
# =============================================================================


@pytest.mark.unit
class TestActivationGate:

    def test_only_approved_can_activate(self):
        vid = _evaluated_version()
        approve_version(vid, ORG, "admin-001", "admin")
        v = activate_version(vid, ORG, "user-001")
        assert v.status == LoRAStatus.ACTIVE
        assert v.activated_at is not None

    def test_deployable_can_activate(self):
        vid = _evaluated_version()
        approve_version(vid, ORG, "admin-001", "admin")
        mark_deployable(vid, ORG)
        v = activate_version(vid, ORG, "user-001")
        assert v.status == LoRAStatus.ACTIVE

    def test_review_required_cannot_activate(self):
        vid = _evaluated_version()
        with pytest.raises(InvalidTransition):
            activate_version(vid, ORG, "user-001")

    def test_rejected_cannot_activate(self):
        vid = _evaluated_version()
        reject_version(vid, ORG, "admin-001", "admin", "bad")
        with pytest.raises(InvalidTransition):
            activate_version(vid, ORG, "user-001")

    def test_supersede_active_version(self):
        vid = _evaluated_version()
        approve_version(vid, ORG, "admin-001", "admin")
        activate_version(vid, ORG, "user-001")
        supersede_version(vid, ORG, "new-version-id")
        v = get_version(vid, ORG)
        assert v.status == LoRAStatus.SUPERSEDED


# =============================================================================
# Audit Trail
# =============================================================================


@pytest.mark.unit
class TestAuditTrail:

    def test_transitions_recorded(self):
        vid = _evaluated_version()
        approve_version(vid, ORG, "admin-001", "admin")
        activate_version(vid, ORG, "user-001")

        v = get_version(vid, ORG)
        # trained → evaluating → review_required → approved → active
        assert len(v.transitions) >= 5
        states = [t["to"] for t in v.transitions]
        assert "trained" in states
        assert "evaluating" in states
        assert "review_required" in states
        assert "approved" in states
        assert "active" in states
