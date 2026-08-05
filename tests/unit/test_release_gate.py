"""Release Promotion Gate Tests (Story 063).

Proves: required failures block promotion, all-pass promotes, override policy,
evidence preservation, and target matrix completeness.

Run with:
    pytest tests/unit/test_release_gate.py -v
"""
from __future__ import annotations

import pytest

from scripts.release_gate import (
    CRITICAL_SMOKE_JOURNEYS,
    DEPLOYMENT_IDENTITY,
    REQUIRED_TARGETS,
    CheckResult,
    CheckStatus,
    PromotionDecision,
    ReleaseGate,
    TargetCategory,
    apply_override,
    evaluate_gate,
    preserve_evidence,
)


# =============================================================================
# Promotion Decision
# =============================================================================


class TestPromotionDecision:

    @pytest.mark.unit
    def test_all_required_pass_promotes(self):
        """All required checks passed → PROMOTE."""
        gate = ReleaseGate(environment="staging", commit_sha="abc123")
        gate.checks = [
            CheckResult("frontend_build", TargetCategory.FRONTEND, CheckStatus.PASSED),
            CheckResult("api_tests", TargetCategory.API, CheckStatus.PASSED),
            CheckResult("security_scan", TargetCategory.SECURITY, CheckStatus.PASSED),
        ]
        result = evaluate_gate(gate)
        assert result.decision == PromotionDecision.PROMOTE
        assert "3 required checks passed" in result.decision_reason

    @pytest.mark.unit
    def test_one_required_failure_blocks(self):
        """Single required failure → BLOCK."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [
            CheckResult("frontend_build", TargetCategory.FRONTEND, CheckStatus.PASSED),
            CheckResult("api_tests", TargetCategory.API, CheckStatus.FAILED, message="2 tests failed"),
            CheckResult("security_scan", TargetCategory.SECURITY, CheckStatus.PASSED),
        ]
        result = evaluate_gate(gate)
        assert result.decision == PromotionDecision.BLOCK
        assert "api_tests" in result.decision_reason

    @pytest.mark.unit
    def test_timeout_counts_as_failure(self):
        """Required check that times out → BLOCK."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [
            CheckResult("api_health", TargetCategory.API, CheckStatus.TIMEOUT),
        ]
        result = evaluate_gate(gate)
        assert result.decision == PromotionDecision.BLOCK

    @pytest.mark.unit
    def test_not_run_counts_as_failure(self):
        """Required check not run → BLOCK (cannot skip required checks)."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [
            CheckResult("smoke_auth", TargetCategory.SMOKE_TEST, CheckStatus.NOT_RUN),
        ]
        result = evaluate_gate(gate)
        assert result.decision == PromotionDecision.BLOCK

    @pytest.mark.unit
    def test_skipped_required_blocks(self):
        """Skipped required check → BLOCK."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [
            CheckResult("worker_build", TargetCategory.WORKER, CheckStatus.SKIPPED),
        ]
        result = evaluate_gate(gate)
        assert result.decision == PromotionDecision.BLOCK

    @pytest.mark.unit
    def test_non_required_failure_does_not_block(self):
        """Non-required (optional) check failure does NOT block."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [
            CheckResult("api_tests", TargetCategory.API, CheckStatus.PASSED, required=True),
            CheckResult("visual_audit", TargetCategory.FRONTEND, CheckStatus.FAILED, required=False),
        ]
        result = evaluate_gate(gate)
        assert result.decision == PromotionDecision.PROMOTE

    @pytest.mark.unit
    def test_empty_gate_blocks(self):
        """Gate with no checks cannot promote."""
        gate = ReleaseGate(environment="staging")
        result = evaluate_gate(gate)
        assert result.decision == PromotionDecision.BLOCK
        assert "empty" in result.decision_reason.lower()


# =============================================================================
# Override Policy
# =============================================================================


class TestOverridePolicy:

    @pytest.mark.unit
    def test_admin_can_override_blocked_gate(self):
        """Admin can override a blocked gate with reason."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [CheckResult("x", TargetCategory.API, CheckStatus.FAILED)]
        evaluate_gate(gate)

        result = apply_override(
            gate, override_by="admin-user", override_reason="Hotfix needed urgently for P0",
            override_role="admin", expires_hours=4,
        )
        assert result.decision == PromotionDecision.OVERRIDE
        assert result.override_by == "admin-user"

    @pytest.mark.unit
    def test_editor_cannot_override(self):
        """Editor role cannot override."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [CheckResult("x", TargetCategory.API, CheckStatus.FAILED)]
        evaluate_gate(gate)

        result = apply_override(
            gate, override_by="editor-user", override_reason="I want to deploy anyway",
            override_role="editor",
        )
        assert result.decision == PromotionDecision.BLOCK  # Not overridden

    @pytest.mark.unit
    def test_override_requires_reason(self):
        """Override without meaningful reason is rejected."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [CheckResult("x", TargetCategory.API, CheckStatus.FAILED)]
        evaluate_gate(gate)

        result = apply_override(
            gate, override_by="admin", override_reason="ok",  # Too short
            override_role="admin",
        )
        assert result.decision == PromotionDecision.BLOCK  # Not overridden

    @pytest.mark.unit
    def test_cannot_override_promoted_gate(self):
        """Cannot override an already-promoted gate."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [CheckResult("x", TargetCategory.API, CheckStatus.PASSED)]
        evaluate_gate(gate)

        result = apply_override(
            gate, override_by="admin", override_reason="Testing override on success",
            override_role="admin",
        )
        assert result.decision == PromotionDecision.PROMOTE  # Unchanged


# =============================================================================
# Evidence Preservation
# =============================================================================


class TestEvidencePreservation:

    @pytest.mark.unit
    def test_evidence_includes_all_checks(self):
        """Evidence record contains all check results."""
        gate = ReleaseGate(environment="staging", commit_sha="abc", version="1.0.0")
        gate.checks = [
            CheckResult("frontend_build", TargetCategory.FRONTEND, CheckStatus.PASSED),
            CheckResult("api_tests", TargetCategory.API, CheckStatus.FAILED, message="err"),
        ]
        evaluate_gate(gate)

        evidence = preserve_evidence(gate)
        assert evidence["commit_sha"] == "abc"
        assert evidence["version"] == "1.0.0"
        assert evidence["total_checks"] == 2
        assert evidence["passed"] == 1
        assert evidence["failed"] == 1
        assert len(evidence["checks"]) == 2

    @pytest.mark.unit
    def test_evidence_includes_decision(self):
        """Evidence records the final decision and reason."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [CheckResult("x", TargetCategory.API, CheckStatus.PASSED)]
        evaluate_gate(gate)

        evidence = preserve_evidence(gate)
        assert evidence["decision"] == "promote"
        assert evidence["decided_at"] is not None

    @pytest.mark.unit
    def test_evidence_includes_override_details(self):
        """Override details are preserved in evidence."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [CheckResult("x", TargetCategory.API, CheckStatus.FAILED)]
        evaluate_gate(gate)
        apply_override(
            gate, override_by="admin", override_reason="Emergency P0 hotfix required immediately",
            override_role="owner",
        )

        evidence = preserve_evidence(gate)
        assert evidence["override"] is not None
        assert evidence["override"]["by"] == "admin"
        assert "hotfix" in evidence["override"]["reason"].lower()


# =============================================================================
# Target Matrix
# =============================================================================


class TestTargetMatrix:

    @pytest.mark.unit
    def test_staging_has_required_targets(self):
        """Staging environment has all critical targets defined."""
        staging = REQUIRED_TARGETS["staging"]
        names = {t["name"] for t in staging}
        assert "frontend_build" in names
        assert "api_tests" in names
        assert "worker_build" in names
        assert "security_scan" in names
        assert "smoke_health" in names
        assert "smoke_auth" in names

    @pytest.mark.unit
    def test_production_requires_staging_first(self):
        """Production requires staging_promoted check."""
        prod = REQUIRED_TARGETS["production"]
        names = {t["name"] for t in prod}
        assert "staging_promoted" in names

    @pytest.mark.unit
    def test_smoke_journeys_defined(self):
        """Critical smoke journeys exist and have steps."""
        assert len(CRITICAL_SMOKE_JOURNEYS) >= 3
        for journey in CRITICAL_SMOKE_JOURNEYS:
            assert journey["name"]
            assert journey["steps"]
            assert journey["expected_outcome"]

    @pytest.mark.unit
    def test_all_categories_covered(self):
        """Staging matrix covers all critical categories."""
        staging = REQUIRED_TARGETS["staging"]
        categories = {t["category"] for t in staging}
        assert "frontend" in categories
        assert "api" in categories
        assert "worker" in categories
        assert "security" in categories
        assert "smoke_test" in categories


# =============================================================================
# Multiple Failure Scenario
# =============================================================================


class TestMultipleFailures:

    @pytest.mark.unit
    def test_multiple_failures_all_reported(self):
        """All failures are listed in the decision reason."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [
            CheckResult("frontend_build", TargetCategory.FRONTEND, CheckStatus.FAILED),
            CheckResult("api_tests", TargetCategory.API, CheckStatus.FAILED),
            CheckResult("security_scan", TargetCategory.SECURITY, CheckStatus.PASSED),
            CheckResult("worker_build", TargetCategory.WORKER, CheckStatus.TIMEOUT),
        ]
        result = evaluate_gate(gate)
        assert result.decision == PromotionDecision.BLOCK
        assert "3 required failure" in result.decision_reason
        assert "frontend_build" in result.decision_reason
        assert "api_tests" in result.decision_reason

    @pytest.mark.unit
    def test_single_success_cannot_override_failures(self):
        """One passing target cannot override another required failure."""
        gate = ReleaseGate(environment="staging")
        gate.checks = [
            CheckResult("frontend_build", TargetCategory.FRONTEND, CheckStatus.PASSED),
            CheckResult("api_health", TargetCategory.API, CheckStatus.FAILED),
        ]
        result = evaluate_gate(gate)
        assert result.decision == PromotionDecision.BLOCK  # Cannot promote with partial success


# =============================================================================
# Deployment Identity (Story 065)
# =============================================================================


class TestDeploymentIdentity:

    @pytest.mark.unit
    def test_canonical_repository_defined(self):
        """Deployment identity references canonical GitHub repo."""
        assert DEPLOYMENT_IDENTITY["source"]["repository"] == "garymcdaniel7/ai-studio88"
        assert DEPLOYMENT_IDENTITY["source"]["branch_production"] == "main"

    @pytest.mark.unit
    def test_frontend_target_mapped(self):
        """Frontend target maps Vercel project with correct root."""
        frontend = DEPLOYMENT_IDENTITY["targets"]["frontend"]
        assert frontend["platform"] == "vercel"
        assert frontend["project_name"] == "ai-studio99"
        assert frontend["root_directory"] == "frontend/"
        assert frontend["framework"] == "nextjs"

    @pytest.mark.unit
    def test_worker_target_mapped(self):
        """Worker target maps to container registry with correct Dockerfile."""
        worker = DEPLOYMENT_IDENTITY["targets"]["worker"]
        assert worker["platform"] == "ghcr"
        assert "garymcdaniel7" in worker["registry"]
        assert "Dockerfile.hardened" in worker["dockerfile"]

    @pytest.mark.unit
    def test_database_target_mapped(self):
        """Database target references Supabase project."""
        db = DEPLOYMENT_IDENTITY["targets"]["database"]
        assert db["platform"] == "supabase"
        assert db["project_ref"] == "vipmjgglascthwoqqqji"

    @pytest.mark.unit
    def test_storage_target_mapped(self):
        """Storage target references B2 bucket."""
        storage = DEPLOYMENT_IDENTITY["targets"]["storage"]
        assert storage["platform"] == "backblaze_b2"
        assert storage["bucket"] == "ai-studio88"

    @pytest.mark.unit
    def test_evidence_includes_deployment_identity(self):
        """Evidence record embeds full deployment identity for traceability."""
        gate = ReleaseGate(environment="staging", commit_sha="face123")
        gate.checks = [CheckResult("x", TargetCategory.API, CheckStatus.PASSED)]
        evaluate_gate(gate)

        evidence = preserve_evidence(gate)
        assert "deployment_identity" in evidence
        assert evidence["deployment_identity"]["source"]["repository"] == "garymcdaniel7/ai-studio88"
        assert evidence["deployment_identity"]["targets"]["frontend"]["project_name"] == "ai-studio99"

    @pytest.mark.unit
    def test_historical_name_divergence_documented(self):
        """Historical note explains repo vs deployment name divergence."""
        note = DEPLOYMENT_IDENTITY["historical_note"]
        assert "ai-studio88" in note
        assert "ai-studio99" in note
