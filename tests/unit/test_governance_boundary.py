"""Unit tests for the canonical Governance Boundary — Task 14.1.

Verifies the GovernanceBoundary.evaluate() decision logic:
- DENY when identity/trust_domain/tenant_context missing for high-impact
- ALLOW (degraded) for read-only when optional data missing
- REQUIRE_APPROVAL for high cost or required approvals
- DENY for safety violations, revoked consent, budget exceeded
- ALLOW when all checks pass

Validates: Requirements R59.1, R59.2, R59.3, R59.4, R59.5
"""

from __future__ import annotations

import pytest

from backend.aios.governance_boundary import (
    AutonomyProfile,
    Decision,
    GovernanceBoundary,
    GovernanceRequest,
    GovernanceResult,
    RiskClassification,
    SafetyPolicyResult,
    TenantContext,
    clear_evaluation_audit,
    get_evaluation_audit,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_audit():
    """Clear audit trail before/after each test."""
    clear_evaluation_audit()
    yield
    clear_evaluation_audit()


@pytest.fixture
def boundary() -> GovernanceBoundary:
    """Default governance boundary instance."""
    return GovernanceBoundary()


@pytest.fixture
def valid_tenant() -> TenantContext:
    """A valid tenant context."""
    return TenantContext(org_id="org-test-1234", role="editor")


@pytest.fixture
def full_request(valid_tenant: TenantContext) -> GovernanceRequest:
    """A fully populated governance request that should pass all checks."""
    return GovernanceRequest(
        action_type="generate_image",
        identity="usr-test-001",
        trust_domain="customer",
        tenant_context=valid_tenant,
        role="editor",
        risk_classification=RiskClassification.MEDIUM_IMPACT,
        estimated_cost_usd=2.0,
        budget_available=50.0,
        resource_ownership=True,
        provider_capability=True,
        compute_availability_state="enabled",
        feature_rollout_status=True,
        environment="production",
    )


# =============================================================================
# Test: Identity missing → DENY for high-impact, degrade for read-only
# =============================================================================


@pytest.mark.unit
class TestIdentityRequired:
    """R59.3: High-impact fails closed when identity missing."""

    def test_high_impact_denies_without_identity(self, boundary: GovernanceBoundary):
        request = GovernanceRequest(
            action_type="delete_asset",
            identity=None,
            trust_domain="customer",
            tenant_context=TenantContext(org_id="org-1", role="editor"),
            risk_classification=RiskClassification.HIGH_IMPACT,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert result.allowed is False
        assert "identity" in result.failed_checks

    def test_destructive_denies_without_identity(self, boundary: GovernanceBoundary):
        request = GovernanceRequest(
            action_type="delete_model",
            identity=None,
            trust_domain="customer",
            tenant_context=TenantContext(org_id="org-1", role="owner"),
            risk_classification=RiskClassification.DESTRUCTIVE,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "identity" in result.failed_checks

    def test_read_only_degrades_without_identity(self, boundary: GovernanceBoundary):
        request = GovernanceRequest(
            action_type="list_assets",
            identity=None,
            trust_domain="customer",
            tenant_context=TenantContext(org_id="org-1", role="viewer"),
            risk_classification=RiskClassification.READ_ONLY,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.ALLOW
        assert result.is_degraded is True
        assert "identity" in result.failed_checks


# =============================================================================
# Test: Trust domain missing → DENY for high-impact, degrade for read-only
# =============================================================================


@pytest.mark.unit
class TestTrustDomainRequired:
    """R59.3: High-impact fails closed when trust_domain missing."""

    def test_high_impact_denies_without_trust_domain(self, boundary: GovernanceBoundary):
        request = GovernanceRequest(
            action_type="train_lora",
            identity="usr-1",
            trust_domain=None,
            tenant_context=TenantContext(org_id="org-1", role="editor"),
            risk_classification=RiskClassification.HIGH_IMPACT,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "trust_domain" in result.failed_checks

    def test_read_only_degrades_without_trust_domain(self, boundary: GovernanceBoundary):
        request = GovernanceRequest(
            action_type="chat",
            identity="usr-1",
            trust_domain=None,
            tenant_context=TenantContext(org_id="org-1", role="viewer"),
            risk_classification=RiskClassification.READ_ONLY,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.ALLOW
        assert result.is_degraded is True


# =============================================================================
# Test: Tenant context missing → DENY for high-impact, degrade for read-only
# =============================================================================


@pytest.mark.unit
class TestTenantContextRequired:
    """R59.3: High-impact fails closed when tenant_context missing."""

    def test_high_impact_denies_without_tenant_context(self, boundary: GovernanceBoundary):
        request = GovernanceRequest(
            action_type="generate_video",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=None,
            risk_classification=RiskClassification.HIGH_IMPACT,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "tenant_context" in result.failed_checks

    def test_low_impact_degrades_without_tenant_context(self, boundary: GovernanceBoundary):
        request = GovernanceRequest(
            action_type="update_settings",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=None,
            risk_classification=RiskClassification.LOW_IMPACT,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.ALLOW
        assert result.is_degraded is True


# =============================================================================
# Test: Safety policy violations → always DENY
# =============================================================================


@pytest.mark.unit
class TestSafetyPolicy:
    """R59.2: Safety policy violations always deny."""

    def test_safety_violation_denies(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="generate_image",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            safety_policy=SafetyPolicyResult(
                passed=False,
                violations=["csam_detected"],
                reason="Content violates safety restrictions",
            ),
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "safety_policy" in result.failed_checks

    def test_safety_passed_allows_continuation(
        self, boundary: GovernanceBoundary, full_request: GovernanceRequest
    ):
        full_request.safety_policy = SafetyPolicyResult(passed=True)
        result = boundary.evaluate(full_request)
        assert result.decision == Decision.ALLOW


# =============================================================================
# Test: Consent revoked → DENY
# =============================================================================


@pytest.mark.unit
class TestConsentCheck:
    """R59.2: Revoked consent always denies."""

    def test_revoked_consent_denies(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="generate_image",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            consent_status="revoked",
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "consent" in result.failed_checks

    def test_required_consent_denies_high_impact(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="train_lora",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.HIGH_IMPACT,
            consent_status="required",
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "consent" in result.failed_checks


# =============================================================================
# Test: Budget checks
# =============================================================================


@pytest.mark.unit
class TestBudgetCheck:
    """R59.2: Budget availability evaluated."""

    def test_budget_exceeded_denies(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="generate_video",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            estimated_cost_usd=25.0,
            budget_available=10.0,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "budget" in result.failed_checks

    def test_budget_unknown_fails_closed_for_high_impact(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="train_lora",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.HIGH_IMPACT,
            estimated_cost_usd=10.0,
            budget_available=None,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "budget" in result.failed_checks

    def test_budget_sufficient_allows(
        self, boundary: GovernanceBoundary, full_request: GovernanceRequest
    ):
        full_request.estimated_cost_usd = 2.0
        full_request.budget_available = 100.0
        result = boundary.evaluate(full_request)
        assert result.decision == Decision.ALLOW


# =============================================================================
# Test: Cost threshold → REQUIRE_APPROVAL
# =============================================================================


@pytest.mark.unit
class TestCostThreshold:
    """R59.2: High cost triggers approval requirement."""

    def test_cost_above_threshold_requires_approval(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="train_lora",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            estimated_cost_usd=10.0,
            budget_available=100.0,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.REQUIRE_APPROVAL
        assert result.required_approval_type == "cost_threshold"

    def test_cost_below_threshold_allows(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="generate_image",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            estimated_cost_usd=3.0,
            budget_available=100.0,
            provider_capability=True,
            compute_availability_state="enabled",
            feature_rollout_status=True,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.ALLOW

    def test_custom_threshold(self, valid_tenant: TenantContext):
        boundary = GovernanceBoundary(cost_approval_threshold_usd=20.0)
        request = GovernanceRequest(
            action_type="train_lora",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            estimated_cost_usd=15.0,
            budget_available=100.0,
            provider_capability=True,
            compute_availability_state="enabled",
            feature_rollout_status=True,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.ALLOW


# =============================================================================
# Test: Required approvals → REQUIRE_APPROVAL
# =============================================================================


@pytest.mark.unit
class TestRequiredApprovals:
    """R59.2: Explicit approval requirements honored."""

    def test_required_approvals_triggers(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="delete_asset",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            estimated_cost_usd=0.0,
            required_approvals=["destructive_action"],
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.REQUIRE_APPROVAL
        assert result.required_approval_type == "destructive_action"


# =============================================================================
# Test: Resource ownership check
# =============================================================================


@pytest.mark.unit
class TestResourceOwnership:
    """R59.2: Resource ownership evaluated for high-impact."""

    def test_non_owner_denied_for_destructive(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="delete_model",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.DESTRUCTIVE,
            resource_ownership=False,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "resource_ownership" in result.failed_checks

    def test_owner_allowed_for_destructive(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="delete_model",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.DESTRUCTIVE,
            resource_ownership=True,
            provider_capability=True,
            compute_availability_state="enabled",
            feature_rollout_status=True,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.ALLOW


# =============================================================================
# Test: Provider capability check
# =============================================================================


@pytest.mark.unit
class TestProviderCapability:
    """R59.2: Provider capability evaluated."""

    def test_incapable_provider_denies(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="generate_video",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            provider_capability=False,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "provider_capability" in result.failed_checks


# =============================================================================
# Test: Compute availability state
# =============================================================================


@pytest.mark.unit
class TestComputeAvailability:
    """R59.2: Compute availability state checked."""

    def test_compute_disabled_denies(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="launch_gpu",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            compute_availability_state="disabled",
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "compute_availability_state" in result.failed_checks

    def test_compute_enabled_allows(
        self, boundary: GovernanceBoundary, full_request: GovernanceRequest
    ):
        full_request.compute_availability_state = "enabled"
        result = boundary.evaluate(full_request)
        assert result.decision == Decision.ALLOW


# =============================================================================
# Test: Feature rollout status
# =============================================================================


@pytest.mark.unit
class TestFeatureRollout:
    """R59.2: Feature rollout status evaluated."""

    def test_feature_not_rolled_out_denies(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="use_new_feature",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            feature_rollout_status=False,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "feature_rollout_status" in result.failed_checks


# =============================================================================
# Test: Autonomy profile enforcement
# =============================================================================


@pytest.mark.unit
class TestAutonomyProfile:
    """R59.2: Autonomy profile evaluated for agent actions."""

    def test_advisory_requires_approval_for_mutations(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="generate_image",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            autonomy_profile=AutonomyProfile.ADVISORY,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.REQUIRE_APPROVAL
        assert result.required_approval_type == "autonomy_advisory"

    def test_autonomous_allows_mutations(
        self, boundary: GovernanceBoundary, full_request: GovernanceRequest
    ):
        full_request.autonomy_profile = AutonomyProfile.AUTONOMOUS_WITHIN_LIMITS
        result = boundary.evaluate(full_request)
        assert result.decision == Decision.ALLOW


# =============================================================================
# Test: Environment restrictions
# =============================================================================


@pytest.mark.unit
class TestEnvironmentRestrictions:
    """R59.2: Environment restrictions evaluated."""

    def test_destructive_in_production_requires_approval(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="delete_all",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.DESTRUCTIVE,
            resource_ownership=True,
            environment="production",
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.REQUIRE_APPROVAL
        assert result.required_approval_type == "production_destructive"


# =============================================================================
# Test: Privacy restrictions
# =============================================================================


@pytest.mark.unit
class TestPrivacyRestrictions:
    """R59.2: Privacy restrictions evaluated."""

    def test_blocking_privacy_restriction_denies(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="export_data",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            privacy_restrictions=["block:data_export_restricted"],
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "privacy_restrictions" in result.failed_checks

    def test_non_blocking_restriction_allows(
        self, boundary: GovernanceBoundary, full_request: GovernanceRequest
    ):
        full_request.privacy_restrictions = ["log:data_access_tracked"]
        result = boundary.evaluate(full_request)
        assert result.decision == Decision.ALLOW


# =============================================================================
# Test: Entitlement exceeded → DENY
# =============================================================================


@pytest.mark.unit
class TestEntitlement:
    """R59.2: Entitlement limits enforced."""

    def test_exceeded_entitlement_denies(
        self, boundary: GovernanceBoundary, valid_tenant: TenantContext
    ):
        request = GovernanceRequest(
            action_type="generate_image",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=valid_tenant,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            entitlement="exceeded",
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.DENY
        assert "entitlement" in result.failed_checks


# =============================================================================
# Test: All checks pass → ALLOW
# =============================================================================


@pytest.mark.unit
class TestAllChecksPassed:
    """R59.2: All checks pass → action allowed."""

    def test_fully_valid_request_allows(
        self, boundary: GovernanceBoundary, full_request: GovernanceRequest
    ):
        result = boundary.evaluate(full_request)
        assert result.decision == Decision.ALLOW
        assert result.allowed is True
        assert result.is_degraded is False
        assert result.failed_checks == []

    def test_read_only_with_minimal_context_allows(
        self, boundary: GovernanceBoundary
    ):
        request = GovernanceRequest(
            action_type="list_models",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=TenantContext(org_id="org-1", role="viewer"),
            risk_classification=RiskClassification.READ_ONLY,
        )
        result = boundary.evaluate(request)
        assert result.decision == Decision.ALLOW
        assert result.is_degraded is False


# =============================================================================
# Test: Audit trail populated
# =============================================================================


@pytest.mark.unit
class TestAuditTrail:
    """R59.5: Every evaluation produces auditable record."""

    def test_evaluation_creates_audit_entry(
        self, boundary: GovernanceBoundary, full_request: GovernanceRequest
    ):
        boundary.evaluate(full_request)
        audit = get_evaluation_audit()
        assert len(audit) == 1
        entry = audit[0]
        assert entry["action_type"] == "generate_image"
        assert entry["identity"] == "usr-test-001"
        assert entry["decision"] == "allow"
        assert entry["evaluation_id"] is not None

    def test_denial_creates_audit_entry(
        self, boundary: GovernanceBoundary
    ):
        request = GovernanceRequest(
            action_type="delete_asset",
            identity=None,
            risk_classification=RiskClassification.HIGH_IMPACT,
        )
        boundary.evaluate(request)
        audit = get_evaluation_audit()
        assert len(audit) == 1
        entry = audit[0]
        assert entry["decision"] == "deny"
        assert entry["denial_reason"] is not None

    def test_multiple_evaluations_accumulate(
        self, boundary: GovernanceBoundary, full_request: GovernanceRequest
    ):
        for _ in range(5):
            boundary.evaluate(full_request)
        audit = get_evaluation_audit()
        assert len(audit) == 5


# =============================================================================
# Test: GovernanceResult properties
# =============================================================================


@pytest.mark.unit
class TestGovernanceResult:
    """GovernanceResult dataclass correctness."""

    def test_allow_result_properties(self):
        result = GovernanceResult(
            decision=Decision.ALLOW,
            risk_classification=RiskClassification.MEDIUM_IMPACT,
        )
        assert result.allowed is True
        assert result.is_degraded is False
        assert result.denial_reason is None

    def test_deny_result_properties(self):
        result = GovernanceResult(
            decision=Decision.DENY,
            denial_reason="test denial",
            risk_classification=RiskClassification.HIGH_IMPACT,
        )
        assert result.allowed is False
        assert result.denial_reason == "test denial"

    def test_require_approval_properties(self):
        result = GovernanceResult(
            decision=Decision.REQUIRE_APPROVAL,
            required_approval_type="cost_threshold",
            risk_classification=RiskClassification.MEDIUM_IMPACT,
        )
        assert result.allowed is False
        assert result.required_approval_type == "cost_threshold"

    def test_to_dict_serialization(self):
        result = GovernanceResult(
            decision=Decision.ALLOW,
            risk_classification=RiskClassification.READ_ONLY,
        )
        d = result.to_dict()
        assert d["decision"] == "allow"
        assert d["allowed"] is True
        assert d["risk_classification"] == "read_only"
        assert "evaluation_id" in d
        assert "timestamp" in d


# =============================================================================
# Test: Risk classification properties
# =============================================================================


@pytest.mark.unit
class TestRiskClassification:
    """RiskClassification enum correctness."""

    def test_read_only_allows_degraded(self):
        assert RiskClassification.READ_ONLY.allows_degraded is True
        assert RiskClassification.READ_ONLY.requires_fail_closed is False

    def test_low_impact_allows_degraded(self):
        assert RiskClassification.LOW_IMPACT.allows_degraded is True
        assert RiskClassification.LOW_IMPACT.requires_fail_closed is False

    def test_medium_impact_requires_fail_closed(self):
        assert RiskClassification.MEDIUM_IMPACT.requires_fail_closed is True
        assert RiskClassification.MEDIUM_IMPACT.allows_degraded is False

    def test_high_impact_requires_fail_closed(self):
        assert RiskClassification.HIGH_IMPACT.requires_fail_closed is True
        assert RiskClassification.HIGH_IMPACT.allows_degraded is False

    def test_destructive_requires_fail_closed(self):
        assert RiskClassification.DESTRUCTIVE.requires_fail_closed is True
        assert RiskClassification.DESTRUCTIVE.allows_degraded is False


# =============================================================================
# Test: Single enforcement point — stateless, no side effects
# =============================================================================


@pytest.mark.unit
class TestSingleEnforcementPoint:
    """R59.5: evaluate() is a single, auditable code path."""

    def test_boundary_is_stateless(self, boundary: GovernanceBoundary):
        """Successive calls don't carry state between evaluations."""
        request1 = GovernanceRequest(
            action_type="generate_image",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=TenantContext(org_id="org-1", role="editor"),
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            estimated_cost_usd=2.0,
            budget_available=100.0,
            provider_capability=True,
            compute_availability_state="enabled",
            feature_rollout_status=True,
        )
        request2 = GovernanceRequest(
            action_type="delete_asset",
            identity=None,
            risk_classification=RiskClassification.DESTRUCTIVE,
        )

        result1 = boundary.evaluate(request1)
        result2 = boundary.evaluate(request2)

        assert result1.decision == Decision.ALLOW
        assert result2.decision == Decision.DENY

    def test_multiple_instances_same_behavior(self):
        """Different instances produce identical decisions for same input."""
        b1 = GovernanceBoundary()
        b2 = GovernanceBoundary()

        request = GovernanceRequest(
            action_type="chat",
            identity="usr-1",
            trust_domain="customer",
            tenant_context=TenantContext(org_id="org-1", role="viewer"),
            risk_classification=RiskClassification.READ_ONLY,
        )

        r1 = b1.evaluate(request)
        r2 = b2.evaluate(request)

        assert r1.decision == r2.decision
        assert r1.is_degraded == r2.is_degraded
