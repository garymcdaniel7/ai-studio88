"""Context Disclosure Gate Tests (Story 085).

Proves: required failures block, optional disclosed, overrides recorded,
cross-tenant isolation, audit persistence, and warning generation.

Run with:
    pytest tests/unit/test_context_disclosure.py -v
"""
from __future__ import annotations

import pytest

from backend.context_disclosure import (
    OVERRIDE_ALLOWED_ROLES,
    DisclosureGateResult,
    GateDecision,
    GenerationAuditEntry,
    OverrideRecord,
    SourceDisclosure,
    SourceInput,
    SourceRequirement,
    SourceStatus,
    clear_audit_store,
    evaluate_gate,
    get_audit_for_job,
    get_audits_for_org,
    persist_audit,
    validate_override,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_audit_store()
    yield
    clear_audit_store()


def _loaded_source(name: str, requirement: SourceRequirement = SourceRequirement.REQUIRED) -> SourceInput:
    return SourceInput(
        source_name=name, status=SourceStatus.LOADED,
        requirement=requirement, record_count=1, versions=[1],
    )


def _failed_source(name: str, requirement: SourceRequirement = SourceRequirement.REQUIRED) -> SourceInput:
    return SourceInput(
        source_name=name, status=SourceStatus.ERROR,
        requirement=requirement, error="Database timeout",
    )


def _absent_source(name: str, requirement: SourceRequirement = SourceRequirement.OPTIONAL) -> SourceInput:
    return SourceInput(
        source_name=name, status=SourceStatus.ABSENT,
        requirement=requirement,
    )


def _stale_source(name: str, requirement: SourceRequirement = SourceRequirement.RECOMMENDED) -> SourceInput:
    return SourceInput(
        source_name=name, status=SourceStatus.STALE,
        requirement=requirement, record_count=2,
    )


def _valid_override(**overrides) -> OverrideRecord:
    defaults = {
        "actor_id": "admin-1",
        "actor_role": "admin",
        "reason": "Emergency hotfix needed for campaign deadline",
        "policy": "manual_override",
        "affected_sources": ["talent_profile"],
        "org_id": "org-123",
    }
    defaults.update(overrides)
    return OverrideRecord(**defaults)


# =============================================================================
# Required Failures Block
# =============================================================================


class TestRequiredFailuresBlock:

    @pytest.mark.unit
    def test_all_required_loaded_proceeds(self):
        """All required sources loaded → PROCEED."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _loaded_source("talent_profile", SourceRequirement.REQUIRED),
                _loaded_source("creative_preferences", SourceRequirement.RECOMMENDED),
                _loaded_source("wardrobe_items", SourceRequirement.OPTIONAL),
            ],
        )
        assert result.decision == GateDecision.PROCEED
        assert result.blocking_count == 0

    @pytest.mark.unit
    def test_required_error_blocks(self):
        """Required source with ERROR → BLOCKED."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _failed_source("talent_profile", SourceRequirement.REQUIRED),
                _loaded_source("wardrobe_items", SourceRequirement.OPTIONAL),
            ],
        )
        assert result.decision == GateDecision.BLOCKED
        assert result.blocking_count == 1
        assert "talent_profile" in result.decision_reason

    @pytest.mark.unit
    def test_required_absent_blocks(self):
        """Required source ABSENT → BLOCKED."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                SourceInput(
                    source_name="talent_profile",
                    status=SourceStatus.ABSENT,
                    requirement=SourceRequirement.REQUIRED,
                ),
            ],
        )
        assert result.decision == GateDecision.BLOCKED

    @pytest.mark.unit
    def test_required_unauthorized_blocks(self):
        """Required source UNAUTHORIZED → BLOCKED."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                SourceInput(
                    source_name="talent_profile",
                    status=SourceStatus.UNAUTHORIZED,
                    requirement=SourceRequirement.REQUIRED,
                ),
            ],
        )
        assert result.decision == GateDecision.BLOCKED

    @pytest.mark.unit
    def test_multiple_required_failures_all_reported(self):
        """Multiple required failures all listed in reason."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _failed_source("talent_profile", SourceRequirement.REQUIRED),
                _failed_source("continuity_rules", SourceRequirement.REQUIRED),
                _loaded_source("wardrobe_items", SourceRequirement.OPTIONAL),
            ],
        )
        assert result.decision == GateDecision.BLOCKED
        assert result.blocking_count == 2
        assert "talent_profile" in result.decision_reason
        assert "continuity_rules" in result.decision_reason


# =============================================================================
# Optional Failures Disclosed
# =============================================================================


class TestOptionalDisclosed:

    @pytest.mark.unit
    def test_optional_absent_does_not_block(self):
        """Optional source absent → PROCEED (not blocked)."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _loaded_source("talent_profile", SourceRequirement.REQUIRED),
                _absent_source("wardrobe_items", SourceRequirement.OPTIONAL),
            ],
        )
        assert result.decision == GateDecision.PROCEED
        assert result.blocking_count == 0

    @pytest.mark.unit
    def test_optional_failure_generates_warning(self):
        """Optional failure produces user-visible warning."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _loaded_source("talent_profile", SourceRequirement.REQUIRED),
                _absent_source("wardrobe_items", SourceRequirement.OPTIONAL),
            ],
        )
        assert len(result.user_warnings) >= 1
        assert any("wardrobe" in w.lower() for w in result.user_warnings)

    @pytest.mark.unit
    def test_recommended_failure_produces_warning(self):
        """Recommended source failure produces warning but doesn't block."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _loaded_source("talent_profile", SourceRequirement.REQUIRED),
                _failed_source("creative_preferences", SourceRequirement.RECOMMENDED),
            ],
        )
        assert result.decision == GateDecision.PROCEED
        assert result.warning_count >= 1

    @pytest.mark.unit
    def test_stale_produces_warning(self):
        """Stale source produces warning."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _loaded_source("talent_profile", SourceRequirement.REQUIRED),
                _stale_source("relationships", SourceRequirement.OPTIONAL),
            ],
        )
        assert result.decision == GateDecision.PROCEED
        assert any("outdated" in w.lower() for w in result.user_warnings)


# =============================================================================
# Overrides Recorded
# =============================================================================


class TestOverrides:

    @pytest.mark.unit
    def test_valid_override_allows_proceed(self):
        """Valid override on blocked gate → OVERRIDE decision."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _failed_source("talent_profile", SourceRequirement.REQUIRED),
            ],
            override=_valid_override(),
        )
        assert result.decision == GateDecision.OVERRIDE
        assert result.override is not None
        assert result.override.actor_id == "admin-1"

    @pytest.mark.unit
    def test_override_with_wrong_role_rejected(self):
        """Override with non-admin role → still BLOCKED."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _failed_source("talent_profile", SourceRequirement.REQUIRED),
            ],
            override=_valid_override(actor_role="editor"),
        )
        assert result.decision == GateDecision.BLOCKED
        assert "role" in result.decision_reason.lower()

    @pytest.mark.unit
    def test_override_with_short_reason_rejected(self):
        """Override with too-short reason → still BLOCKED."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _failed_source("talent_profile", SourceRequirement.REQUIRED),
            ],
            override=_valid_override(reason="ok"),
        )
        assert result.decision == GateDecision.BLOCKED

    @pytest.mark.unit
    def test_override_without_actor_rejected(self):
        """Override without actor_id → rejected."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _failed_source("talent_profile", SourceRequirement.REQUIRED),
            ],
            override=_valid_override(actor_id=""),
        )
        assert result.decision == GateDecision.BLOCKED

    @pytest.mark.unit
    def test_override_on_non_blocked_gate_not_needed(self):
        """Override on already-proceeding gate has no effect."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _loaded_source("talent_profile", SourceRequirement.REQUIRED),
            ],
            override=_valid_override(),
        )
        assert result.decision == GateDecision.PROCEED
        assert result.override is None

    @pytest.mark.unit
    def test_owner_role_can_override(self):
        """Owner role is permitted to override."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _failed_source("talent_profile", SourceRequirement.REQUIRED),
            ],
            override=_valid_override(actor_role="owner"),
        )
        assert result.decision == GateDecision.OVERRIDE


# =============================================================================
# Audit Persistence
# =============================================================================


class TestAuditPersistence:

    @pytest.mark.unit
    def test_audit_persisted_on_proceed(self):
        """Audit entry persisted even on successful proceed."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[_loaded_source("talent_profile")],
        )
        entry = persist_audit(result, job_id="gen-123")
        assert entry.job_id == "gen-123"
        assert entry.decision == GateDecision.PROCEED

    @pytest.mark.unit
    def test_audit_records_omissions(self):
        """Audit captures all omitted sources."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _loaded_source("talent_profile"),
                _absent_source("wardrobe_items"),
                _failed_source("relationships", SourceRequirement.OPTIONAL),
            ],
        )
        entry = persist_audit(result, job_id="gen-456")
        assert len(entry.omitted_sources) == 2
        names = {o["source"] for o in entry.omitted_sources}
        assert "wardrobe_items" in names
        assert "relationships" in names

    @pytest.mark.unit
    def test_audit_records_override_evidence(self):
        """Audit captures override details."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[_failed_source("talent_profile")],
            override=_valid_override(),
        )
        entry = persist_audit(result, job_id="gen-789")
        assert entry.override_evidence is not None
        assert entry.override_evidence["actor_id"] == "admin-1"

    @pytest.mark.unit
    def test_retrieve_audit_by_job(self):
        """Can retrieve audit by job_id."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[_loaded_source("talent_profile")],
        )
        persist_audit(result, job_id="gen-abc")
        found = get_audit_for_job("gen-abc")
        assert found is not None
        assert found.org_id == "org-1"

    @pytest.mark.unit
    def test_retrieve_audits_by_org(self):
        """Audit retrieval is tenant-scoped."""
        r1 = evaluate_gate(org_id="org-1", user_id="u-1", sources=[_loaded_source("x")])
        r2 = evaluate_gate(org_id="org-2", user_id="u-2", sources=[_loaded_source("x")])
        persist_audit(r1, job_id="j-1")
        persist_audit(r2, job_id="j-2")

        org1_audits = get_audits_for_org("org-1")
        assert len(org1_audits) == 1
        assert org1_audits[0].job_id == "j-1"


# =============================================================================
# Cross-Tenant Isolation
# =============================================================================


class TestTenantIsolation:

    @pytest.mark.unit
    def test_audit_scoped_to_org(self):
        """Cannot retrieve another org's audit entries."""
        result = evaluate_gate(
            org_id="org-secret", user_id="u-1",
            sources=[_loaded_source("talent_profile")],
        )
        persist_audit(result, job_id="j-secret")

        other_audits = get_audits_for_org("org-attacker")
        assert len(other_audits) == 0

    @pytest.mark.unit
    def test_user_warnings_no_cross_tenant_data(self):
        """User warnings never expose cross-tenant information."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                SourceInput(
                    source_name="talent_profile",
                    status=SourceStatus.UNAUTHORIZED,
                    requirement=SourceRequirement.REQUIRED,
                    error="Belongs to org-other",
                ),
            ],
        )
        # Warning should say "access denied" not reveal the other org
        for warning in result.user_warnings:
            assert "org-other" not in warning


# =============================================================================
# Warning Generation
# =============================================================================


class TestWarnings:

    @pytest.mark.unit
    def test_loaded_sources_no_warning(self):
        """Loaded sources produce no warnings."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[_loaded_source("talent_profile")],
        )
        assert result.user_warnings == []

    @pytest.mark.unit
    def test_each_non_loaded_produces_warning(self):
        """Each non-loaded source produces exactly one warning."""
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _loaded_source("talent_profile"),
                _absent_source("wardrobe"),
                _stale_source("rules"),
            ],
        )
        assert len(result.user_warnings) == 2

    @pytest.mark.unit
    def test_disclosure_serializable(self):
        """DisclosureGateResult.to_dict() is JSON-serializable."""
        import json
        result = evaluate_gate(
            org_id="org-1", user_id="u-1",
            sources=[
                _loaded_source("talent_profile"),
                _failed_source("prefs", SourceRequirement.RECOMMENDED),
            ],
            override=_valid_override(),
        )
        json.dumps(result.to_dict())
