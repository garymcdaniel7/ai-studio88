"""Model Retirement & Deletion Tests (Story 101).

Proves: dependency blocking, retirement behavior, delete guards,
partial failure handling, historical preservation, and reconciliation.

Run with:
    pytest tests/unit/test_model_retirement.py -v
"""
from __future__ import annotations

import pytest

from backend.model_retirement import (
    DELETION_AUTHORIZED_ROLES,
    CleanupStep,
    DeletionBlockedError,
    DeletionPlan,
    DeletionPolicyError,
    DependencyProtection,
    DependencyType,
    ImpactReview,
    RetirementError,
    approve_deletion,
    clear_retirement_log,
    discover_dependencies,
    execute_cleanup,
    get_retirement_history,
    reactivate_version,
    reconcile_deletion,
    retire_version,
    retry_cleanup,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_retirement_log()
    yield
    clear_retirement_log()


def _empty_review(version_id: str = "v-1", org_id: str = "org-1") -> ImpactReview:
    """Impact review with no dependencies (all clear)."""
    return discover_dependencies(version_id, org_id)


def _review_with_assignment(version_id: str = "v-1") -> ImpactReview:
    """Impact review with active assignment blocking retirement."""
    return discover_dependencies(
        version_id, "org-1",
        active_assignments=[{"id": "assign-1", "name": "Talent: Melissa primary"}],
    )


def _review_with_history(version_id: str = "v-1") -> ImpactReview:
    """Impact review with historical assets blocking deletion only."""
    return discover_dependencies(
        version_id, "org-1",
        historical_assets=[{"id": "asset-1", "name": "Generated portrait"}],
    )


# =============================================================================
# Dependency Discovery
# =============================================================================


class TestDependencyDiscovery:

    @pytest.mark.unit
    def test_no_deps_allows_all(self):
        """No dependencies → can retire AND can delete."""
        review = _empty_review()
        assert review.can_retire is True
        assert review.can_delete is True
        assert len(review.dependencies) == 0

    @pytest.mark.unit
    def test_active_assignment_blocks_retirement(self):
        """Active assignment blocks retirement."""
        review = _review_with_assignment()
        assert review.can_retire is False
        assert len(review.blocks_retirement) == 1
        assert review.blocks_retirement[0].dep_type == DependencyType.ACTIVE_ASSIGNMENT

    @pytest.mark.unit
    def test_queued_job_blocks_retirement(self):
        """Queued job blocks retirement."""
        review = discover_dependencies(
            "v-1", "org-1",
            queued_jobs=[{"id": "job-1", "name": "Pending generation"}],
        )
        assert review.can_retire is False

    @pytest.mark.unit
    def test_running_job_blocks_retirement(self):
        """Running job blocks retirement."""
        review = discover_dependencies(
            "v-1", "org-1",
            running_jobs=[{"id": "job-2", "name": "In-progress training"}],
        )
        assert review.can_retire is False

    @pytest.mark.unit
    def test_historical_asset_blocks_deletion_not_retirement(self):
        """Historical asset blocks deletion but allows retirement."""
        review = _review_with_history()
        assert review.can_retire is True  # Retirement OK
        assert review.can_delete is False  # Deletion blocked
        assert len(review.blocks_deletion) == 1

    @pytest.mark.unit
    def test_child_version_blocks_deletion(self):
        """Child version (fine-tuned from) blocks deletion."""
        review = discover_dependencies(
            "v-1", "org-1",
            child_versions=[{"id": "v-2", "name": "Fine-tuned v2"}],
        )
        assert review.can_delete is False

    @pytest.mark.unit
    def test_provider_deployment_is_informational(self):
        """Provider deployment is informational (doesn't block)."""
        review = discover_dependencies(
            "v-1", "org-1",
            provider_deployments=[{"id": "deploy-1", "name": "Worker GPU-A"}],
        )
        assert review.can_retire is True
        assert review.can_delete is True
        assert len(review.informational) == 1

    @pytest.mark.unit
    def test_multiple_deps_accumulated(self):
        """Multiple dependency types are all reported."""
        review = discover_dependencies(
            "v-1", "org-1",
            active_assignments=[{"id": "a-1", "name": "Primary"}],
            historical_assets=[{"id": "h-1", "name": "Asset"}, {"id": "h-2", "name": "Asset 2"}],
            worker_caches=[{"id": "w-1", "name": "Cache"}],
        )
        assert len(review.dependencies) == 4
        assert len(review.blocks_retirement) == 1
        assert len(review.blocks_deletion) == 2
        assert len(review.informational) == 1

    @pytest.mark.unit
    def test_review_serializable(self):
        """ImpactReview.to_dict() is JSON-serializable."""
        import json
        review = _review_with_assignment()
        json.dumps(review.to_dict())


# =============================================================================
# Retirement Behavior
# =============================================================================


class TestRetirement:

    @pytest.mark.unit
    def test_retire_with_no_blockers(self):
        """Can retire when no blocking dependencies."""
        review = _empty_review()
        record = retire_version(
            version_id="v-1", org_id="org-1", actor_id="admin-1",
            reason="No longer needed", current_state="active",
            impact_review=review,
        )
        assert record.action == "retire"
        assert record.prior_state == "active"

    @pytest.mark.unit
    def test_retire_blocked_by_assignment(self):
        """Cannot retire with active assignment."""
        review = _review_with_assignment()
        with pytest.raises(RetirementError) as exc_info:
            retire_version(
                version_id="v-1", org_id="org-1", actor_id="admin-1",
                reason="Cleanup", current_state="active", impact_review=review,
            )
        assert "blocking" in exc_info.value.message
        assert len(exc_info.value.blocking_deps) == 1

    @pytest.mark.unit
    def test_retire_from_superseded(self):
        """Can retire from superseded state."""
        review = _empty_review()
        record = retire_version(
            version_id="v-1", org_id="org-1", actor_id="admin-1",
            reason="Old version", current_state="superseded", impact_review=review,
        )
        assert record.prior_state == "superseded"

    @pytest.mark.unit
    def test_cannot_retire_from_retired(self):
        """Cannot retire an already-retired version."""
        review = _empty_review()
        with pytest.raises(RetirementError):
            retire_version(
                version_id="v-1", org_id="org-1", actor_id="admin-1",
                reason="Double retire", current_state="retired", impact_review=review,
            )

    @pytest.mark.unit
    def test_retirement_with_replacement(self):
        """Retirement can suggest a replacement version."""
        review = _empty_review()
        record = retire_version(
            version_id="v-1", org_id="org-1", actor_id="admin-1",
            reason="Upgrade", current_state="superseded", impact_review=review,
            replacement_version_id="v-2",
        )
        assert record.replacement_version_id == "v-2"

    @pytest.mark.unit
    def test_reactivate_retired(self):
        """Can reactivate a retired version."""
        record = reactivate_version(
            version_id="v-1", org_id="org-1", actor_id="admin-1",
            reason="Needed again",
        )
        assert record.action == "reactivate"
        assert record.prior_state == "retired"

    @pytest.mark.unit
    def test_retirement_history_recorded(self):
        """Retirement actions are recorded in audit log."""
        review = _empty_review()
        retire_version(
            version_id="v-1", org_id="org-1", actor_id="admin-1",
            reason="Cleanup", current_state="active", impact_review=review,
        )
        history = get_retirement_history("org-1", "v-1")
        assert len(history) == 1
        assert history[0].actor_id == "admin-1"


# =============================================================================
# Delete Guards
# =============================================================================


class TestDeleteGuards:

    @pytest.mark.unit
    def test_delete_approved_when_clear(self):
        """Deletion approved when all guards pass."""
        review = _empty_review()
        plan = approve_deletion(
            version_id="v-1", org_id="org-1", actor_id="owner-1",
            actor_role="owner", reason="Storage cleanup",
            current_state="retired", impact_review=review,
            retention_policy="30_days", storage_key="/org-1/models/v1.safetensors",
        )
        assert plan.version_id == "v-1"
        assert plan.storage_object == "/org-1/models/v1.safetensors"

    @pytest.mark.unit
    def test_delete_blocked_not_retired(self):
        """Cannot delete version that isn't retired first."""
        review = _empty_review()
        with pytest.raises(DeletionBlockedError) as exc_info:
            approve_deletion(
                version_id="v-1", org_id="org-1", actor_id="owner-1",
                actor_role="owner", reason="Delete",
                current_state="active", impact_review=review,
                retention_policy="30_days",
            )
        assert "retired" in exc_info.value.message

    @pytest.mark.unit
    def test_delete_blocked_wrong_role(self):
        """Non-owner cannot approve deletion."""
        review = _empty_review()
        with pytest.raises(DeletionBlockedError) as exc_info:
            approve_deletion(
                version_id="v-1", org_id="org-1", actor_id="admin-1",
                actor_role="admin", reason="Delete",
                current_state="retired", impact_review=review,
                retention_policy="30_days",
            )
        assert "owner" in exc_info.value.message

    @pytest.mark.unit
    def test_delete_blocked_by_dependencies(self):
        """Cannot delete with protected dependencies."""
        review = _review_with_history()
        with pytest.raises(DeletionBlockedError) as exc_info:
            approve_deletion(
                version_id="v-1", org_id="org-1", actor_id="owner-1",
                actor_role="owner", reason="Delete",
                current_state="retired", impact_review=review,
                retention_policy="30_days",
            )
        assert "protected" in exc_info.value.message

    @pytest.mark.unit
    def test_delete_blocked_unverified_policy(self):
        """Cannot delete with UNVERIFIED retention policy."""
        review = _empty_review()
        with pytest.raises(DeletionPolicyError) as exc_info:
            approve_deletion(
                version_id="v-1", org_id="org-1", actor_id="owner-1",
                actor_role="owner", reason="Delete",
                current_state="retired", impact_review=review,
                retention_policy="UNVERIFIED",
            )
        assert "DECISION-REQUIRED" in exc_info.value.message


# =============================================================================
# Partial Failure & Cleanup
# =============================================================================


class TestCleanup:

    @pytest.mark.unit
    def test_successful_cleanup(self):
        """All steps succeed → plan complete."""
        plan = DeletionPlan(version_id="v-1", org_id="org-1")
        result = execute_cleanup(
            plan,
            db_executor=lambda p: None,
            storage_executor=lambda p: None,
            registry_executor=lambda p: None,
        )
        assert result.is_complete is True
        assert len(result.steps_completed) >= 3

    @pytest.mark.unit
    def test_partial_failure_stops(self):
        """Failure at step 2 stops execution, records error."""
        plan = DeletionPlan(version_id="v-1", org_id="org-1")

        call_count = [0]
        def failing_storage(p):
            call_count[0] += 1
            raise RuntimeError("B2 connection refused")

        result = execute_cleanup(
            plan,
            db_executor=lambda p: None,
            storage_executor=failing_storage,
            registry_executor=lambda p: None,
        )
        assert result.is_complete is False
        assert len(result.steps_failed) == 1
        assert "B2 connection" in result.steps_failed[0]["error"]
        assert CleanupStep.DB_SOFT_DELETE.value in result.steps_completed
        assert CleanupStep.REGISTRY_REMOVE.value not in result.steps_completed

    @pytest.mark.unit
    def test_idempotent_cleanup(self):
        """Re-running cleanup skips completed steps."""
        plan = DeletionPlan(version_id="v-1", org_id="org-1")
        plan.steps_completed = [CleanupStep.DB_SOFT_DELETE.value]

        call_count = [0]
        def counting_db(p):
            call_count[0] += 1

        execute_cleanup(
            plan,
            db_executor=counting_db,
            storage_executor=lambda p: None,
            registry_executor=lambda p: None,
        )
        # DB step was NOT re-executed (already completed)
        assert call_count[0] == 0

    @pytest.mark.unit
    def test_retry_after_failure(self):
        """retry_cleanup clears failures and re-executes."""
        plan = DeletionPlan(version_id="v-1", org_id="org-1")
        plan.steps_completed = [CleanupStep.DB_SOFT_DELETE.value]
        plan.steps_failed = [{"step": "storage_delete", "error": "timeout"}]

        result = retry_cleanup(
            plan,
            storage_executor=lambda p: None,
            registry_executor=lambda p: None,
        )
        assert result.is_complete is True
        assert len(result.steps_failed) == 0

    @pytest.mark.unit
    def test_plan_serializable(self):
        """DeletionPlan.to_dict() is JSON-serializable."""
        import json
        plan = DeletionPlan(
            version_id="v-1", org_id="org-1", actor_id="owner-1",
            storage_object="/path/to/model.safetensors",
        )
        json.dumps(plan.to_dict())


# =============================================================================
# Reconciliation
# =============================================================================


class TestReconciliation:

    @pytest.mark.unit
    def test_clean_reconciliation(self):
        """No discrepancies when all targets cleaned."""
        plan = DeletionPlan(version_id="v-1", org_id="org-1")
        plan.steps_completed = [
            CleanupStep.DB_SOFT_DELETE.value,
            CleanupStep.STORAGE_DELETE.value,
            CleanupStep.REGISTRY_REMOVE.value,
        ]
        result = reconcile_deletion(
            plan, db_exists=False, storage_exists=False, registry_exists=False,
        )
        assert result["is_reconciled"] is True
        assert result["discrepancies"] == []

    @pytest.mark.unit
    def test_storage_still_exists(self):
        """Discrepancy when storage object persists after delete step."""
        plan = DeletionPlan(version_id="v-1", org_id="org-1")
        plan.steps_completed = [
            CleanupStep.DB_SOFT_DELETE.value,
            CleanupStep.STORAGE_DELETE.value,
        ]
        result = reconcile_deletion(
            plan, db_exists=False, storage_exists=True, registry_exists=False,
        )
        assert result["is_reconciled"] is False
        assert len(result["discrepancies"]) == 1
        assert result["discrepancies"][0]["target"] == "storage"

    @pytest.mark.unit
    def test_db_still_exists(self):
        """Discrepancy when DB record persists."""
        plan = DeletionPlan(version_id="v-1", org_id="org-1")
        plan.steps_completed = [CleanupStep.DB_SOFT_DELETE.value]
        result = reconcile_deletion(
            plan, db_exists=True, storage_exists=False, registry_exists=False,
        )
        assert result["is_reconciled"] is False


# =============================================================================
# Historical Preservation
# =============================================================================


class TestHistoricalPreservation:

    @pytest.mark.unit
    def test_historical_assets_block_delete_not_retire(self):
        """Historical assets prevent deletion but allow retirement."""
        review = _review_with_history()
        # Retirement allowed
        record = retire_version(
            version_id="v-1", org_id="org-1", actor_id="admin-1",
            reason="Old", current_state="active", impact_review=review,
        )
        assert record.action == "retire"

        # Deletion blocked
        with pytest.raises(DeletionBlockedError):
            approve_deletion(
                version_id="v-1", org_id="org-1", actor_id="owner-1",
                actor_role="owner", reason="Delete",
                current_state="retired", impact_review=review,
                retention_policy="90_days",
            )

    @pytest.mark.unit
    def test_context_packages_block_delete(self):
        """Context packages referencing version block deletion."""
        review = discover_dependencies(
            "v-1", "org-1",
            context_packages=[{"id": "ctx-1", "name": "Context from last week"}],
        )
        assert review.can_retire is True
        assert review.can_delete is False

    @pytest.mark.unit
    def test_retirement_record_serializable(self):
        """RetirementRecord.to_dict() is JSON-serializable."""
        import json
        review = _empty_review()
        record = retire_version(
            version_id="v-1", org_id="org-1", actor_id="admin-1",
            reason="Test", current_state="active", impact_review=review,
        )
        json.dumps(record.to_dict())
