"""Plan-to-execution lifecycle tests — Story 088.

Tests prove:
  - Execution requires approved plan
  - Edited plan after approval requires re-approval
  - Direct legacy bypass is rejected
  - Hermes requires governance approval token
  - Batch (storyboard) creates linked audit records
  - Cancelled plan cannot execute
  - Stale plan version detected
  - Concurrent changes invalidate approval
  - Audit trail links plan → context → job → asset
  - Cross-tenant access denied
  - Auto-approve works for Create/Quick Edit
"""

import pytest

from backend.plan_execution_lifecycle import (
    ExecutionDenied,
    PlanCancelled,
    PlanExecuted,
    PlanNotFound,
    PlanStatus,
    Surface,
    _reset_store,
    approve_plan,
    cancel_plan,
    create_plan,
    get_audit_trail,
    get_plan,
    link_asset_to_audit,
    reject_direct_submission,
    revise_plan,
    submit_for_execution,
    submit_from_create_surface,
    submit_from_hermes_surface,
    submit_from_quick_edit_surface,
    submit_from_storyboard_surface,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
USER = "user-test-001"


# =============================================================================
# Execution Requires Approval
# =============================================================================


@pytest.mark.unit
class TestExecutionRequiresApproval:

    def test_approved_plan_executes(self):
        plan = create_plan(ORG, USER, Surface.CREATE, {"prompt": "test"}, auto_approve=True)
        audit = submit_for_execution(plan.plan_id, ORG, USER, "pkg-001", "job-001")
        assert audit.plan_id == plan.plan_id
        assert audit.job_id == "job-001"

    def test_draft_plan_rejected(self):
        plan = create_plan(ORG, USER, Surface.STORYBOARD, {"shots": []}, auto_approve=False)
        with pytest.raises(ExecutionDenied, match="not approved"):
            submit_for_execution(plan.plan_id, ORG, USER, "pkg-001", "job-001")

    def test_missing_context_package_rejected(self):
        plan = create_plan(ORG, USER, Surface.CREATE, {"prompt": "test"}, auto_approve=True)
        with pytest.raises(ExecutionDenied, match="context_package_id"):
            submit_for_execution(plan.plan_id, ORG, USER, "", "job-001")


# =============================================================================
# Edited Plan After Approval
# =============================================================================


@pytest.mark.unit
class TestEditedAfterApproval:

    def test_revision_invalidates_approval(self):
        plan = create_plan(ORG, USER, Surface.STORYBOARD, {"v": 1}, auto_approve=False)
        approve_plan(plan.plan_id, ORG, USER)
        assert plan.is_executable

        revise_plan(plan.plan_id, ORG, USER, {"v": 2})
        assert plan.status == PlanStatus.REVISED
        assert not plan.is_executable

    def test_revised_plan_rejected_for_execution(self):
        plan = create_plan(ORG, USER, Surface.STORYBOARD, {"v": 1}, auto_approve=False)
        approve_plan(plan.plan_id, ORG, USER)
        revise_plan(plan.plan_id, ORG, USER, {"v": 2})

        with pytest.raises(ExecutionDenied, match="not approved"):
            submit_for_execution(plan.plan_id, ORG, USER, "pkg", "job")

    def test_re_approval_after_revision_allows_execution(self):
        plan = create_plan(ORG, USER, Surface.STORYBOARD, {"v": 1}, auto_approve=False)
        approve_plan(plan.plan_id, ORG, USER)
        revise_plan(plan.plan_id, ORG, USER, {"v": 2})
        approve_plan(plan.plan_id, ORG, USER)

        audit = submit_for_execution(plan.plan_id, ORG, USER, "pkg", "job")
        assert audit.plan_version == 2


# =============================================================================
# Legacy Bypass Rejection
# =============================================================================


@pytest.mark.unit
class TestLegacyBypass:

    def test_direct_submission_rejected(self):
        result = reject_direct_submission(ORG, USER, {"prompt": "bypass attempt"})
        assert result["error"] == "direct_submission_rejected"
        assert "not allowed" in result["message"]

    def test_plan_not_found_for_other_org(self):
        plan = create_plan(ORG, USER, Surface.CREATE, {"prompt": "x"}, auto_approve=True)
        with pytest.raises(PlanNotFound):
            submit_for_execution(plan.plan_id, OTHER_ORG, "hacker", "pkg", "job")


# =============================================================================
# Hermes Submission
# =============================================================================


@pytest.mark.unit
class TestHermesSubmission:

    def test_hermes_with_token_executes(self):
        audit = submit_from_hermes_surface(
            ORG, USER,
            content={"prompt": "AI generated"},
            approval_token="gov-token-001",
            context_package_id="pkg-001",
            job_id="job-hermes-001",
        )
        assert audit.surface == "hermes"
        assert audit.job_id == "job-hermes-001"

    def test_hermes_without_token_rejected(self):
        with pytest.raises(ExecutionDenied, match="approval token"):
            submit_from_hermes_surface(
                ORG, USER,
                content={"prompt": "sneaky"},
                approval_token="",
                context_package_id="pkg",
                job_id="job",
            )


# =============================================================================
# Batch (Storyboard)
# =============================================================================


@pytest.mark.unit
class TestBatch:

    def test_storyboard_creates_multiple_audits(self):
        audits = submit_from_storyboard_surface(
            ORG, USER,
            storyboard_content={"shots": ["s1", "s2", "s3"]},
            context_package_id="pkg-sb",
            job_ids=["j1", "j2", "j3"],
        )
        assert len(audits) == 3
        assert all(a.surface == "storyboard" for a in audits)
        assert [a.job_id for a in audits] == ["j1", "j2", "j3"]


# =============================================================================
# Cancelled Plan
# =============================================================================


@pytest.mark.unit
class TestCancelledPlan:

    def test_cancelled_plan_cannot_execute(self):
        plan = create_plan(ORG, USER, Surface.CREATE, {"prompt": "x"}, auto_approve=True)
        cancel_plan(plan.plan_id, ORG)
        with pytest.raises(ExecutionDenied):
            submit_for_execution(plan.plan_id, ORG, USER, "pkg", "job")

    def test_cancelled_plan_cannot_be_revised(self):
        plan = create_plan(ORG, USER, Surface.CREATE, {"prompt": "x"})
        cancel_plan(plan.plan_id, ORG)
        with pytest.raises(PlanCancelled):
            revise_plan(plan.plan_id, ORG, USER, {"prompt": "new"})


# =============================================================================
# Stale Plan Version
# =============================================================================


@pytest.mark.unit
class TestStalePlan:

    def test_stale_approved_version_detected(self):
        """Approved version 1 but current is version 2 — execution blocked."""
        plan = create_plan(ORG, USER, Surface.FULL_PRODUCTION, {"v": 1}, auto_approve=False)
        approve_plan(plan.plan_id, ORG, USER)  # Approves v1

        # Directly bump version without going through revise_plan
        # (simulates concurrent change)
        from backend.plan_execution_lifecycle import _plans
        p = _plans[plan.plan_id]
        p.current_version = 2
        p.status = PlanStatus.APPROVED  # Status says approved but version mismatch

        with pytest.raises(ExecutionDenied, match="revised after approval"):
            submit_for_execution(plan.plan_id, ORG, USER, "pkg", "job")


# =============================================================================
# Audit Trail Linkage
# =============================================================================


@pytest.mark.unit
class TestAuditTrail:

    def test_audit_links_plan_to_job(self):
        audit = submit_from_create_surface(ORG, USER, {"prompt": "x"}, "pkg-1", "job-1")
        assert audit.plan_id
        assert audit.context_package_id == "pkg-1"
        assert audit.job_id == "job-1"

    def test_audit_links_asset_after_completion(self):
        audit = submit_from_create_surface(ORG, USER, {"prompt": "x"}, "pkg-1", "job-1")
        link_asset_to_audit("job-1", "ast-001", "snap-001")

        trail = get_audit_trail(ORG)
        assert trail[0].asset_id == "ast-001"
        assert trail[0].snapshot_id == "snap-001"

    def test_audit_trail_scoped_to_org(self):
        submit_from_create_surface(ORG, USER, {"prompt": "mine"}, "pkg", "j1")
        submit_from_create_surface(OTHER_ORG, "other", {"prompt": "theirs"}, "pkg2", "j2")

        trail = get_audit_trail(ORG)
        assert len(trail) == 1
        assert trail[0].org_id == ORG

    def test_audit_trail_filtered_by_plan(self):
        a1 = submit_from_create_surface(ORG, USER, {"p": "1"}, "pkg1", "j1")
        a2 = submit_from_create_surface(ORG, USER, {"p": "2"}, "pkg2", "j2")

        trail = get_audit_trail(ORG, plan_id=a1.plan_id)
        assert len(trail) == 1
        assert trail[0].job_id == "j1"


# =============================================================================
# Cross-Tenant
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_get_plan_cross_tenant_returns_none(self):
        plan = create_plan(ORG, USER, Surface.CREATE, {"p": "x"})
        assert get_plan(plan.plan_id, OTHER_ORG) is None

    def test_approve_cross_tenant_raises(self):
        plan = create_plan(ORG, USER, Surface.STORYBOARD, {"p": "x"})
        with pytest.raises(PlanNotFound):
            approve_plan(plan.plan_id, OTHER_ORG, "hacker")

    def test_execute_cross_tenant_raises(self):
        plan = create_plan(ORG, USER, Surface.CREATE, {"p": "x"}, auto_approve=True)
        with pytest.raises(PlanNotFound):
            submit_for_execution(plan.plan_id, OTHER_ORG, "hacker", "pkg", "job")
