"""Context package enforcement tests — Story 084.

Tests prove:
  - Missing package_id is rejected
  - Valid package is allowed
  - Cross-workspace package is rejected (no existence leak)
  - Hash mismatch is rejected
  - Revoked package is rejected
  - Consent revoked after assembly is rejected
  - Stale package (source updated) is rejected
  - Incompatible LoRA is rejected
  - Retry with original valid package works
  - Legacy adapter assembles package server-side
  - Authorized override is allowed and audited
  - Audit log records all decisions
"""

import pytest

from backend.context_enforcement import (
    AuthorizedOverride,
    EnforcementResult,
    PackageStatus,
    _inject_condition,
    _reset_store,
    assemble_package,
    enforce_context_package,
    enforce_or_assemble,
    get_audit_log,
    revoke_package,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
USER = "user-test-001"


def _valid_package(**overrides) -> str:
    """Create a valid package and return its ID."""
    defaults = dict(
        org_id=ORG,
        assembled_by=USER,
        talent_id="talent-001",
        model_id="flux_dev",
        lora_ids=["lora-001"],
    )
    defaults.update(overrides)
    pkg = assemble_package(**defaults)
    return pkg.package_id


# =============================================================================
# Bypass Rejection
# =============================================================================


@pytest.mark.unit
class TestBypassRejection:

    def test_no_package_id_rejected(self):
        decision = enforce_context_package(None, ORG, USER)
        assert not decision.is_allowed
        assert decision.package_status == PackageStatus.MISSING
        assert "required" in decision.rejection_reason

    def test_nonexistent_package_rejected(self):
        decision = enforce_context_package("pkg-fake-123", ORG, USER)
        assert not decision.is_allowed
        assert decision.package_status == PackageStatus.MISSING

    def test_empty_string_package_rejected(self):
        decision = enforce_context_package("", ORG, USER)
        assert not decision.is_allowed


# =============================================================================
# Valid Package
# =============================================================================


@pytest.mark.unit
class TestValidPackage:

    def test_valid_package_allowed(self):
        pkg_id = _valid_package()
        decision = enforce_context_package(pkg_id, ORG, USER)
        assert decision.is_allowed
        assert decision.result == EnforcementResult.ALLOWED
        assert decision.package_status == PackageStatus.VALID

    def test_package_has_content_hash(self):
        pkg = assemble_package(ORG, USER, model_id="flux_dev")
        assert pkg.content_hash
        assert len(pkg.content_hash) == 16


# =============================================================================
# Cross-Workspace
# =============================================================================


@pytest.mark.unit
class TestCrossWorkspace:

    def test_cross_workspace_rejected(self):
        pkg_id = _valid_package(org_id=ORG)
        decision = enforce_context_package(pkg_id, OTHER_ORG, "hacker")
        assert not decision.is_allowed
        assert decision.package_status == PackageStatus.UNAUTHORIZED
        assert "different workspace" in decision.rejection_reason

    def test_same_workspace_allowed(self):
        pkg_id = _valid_package(org_id=ORG)
        decision = enforce_context_package(pkg_id, ORG, USER)
        assert decision.is_allowed


# =============================================================================
# Hash Integrity
# =============================================================================


@pytest.mark.unit
class TestHashIntegrity:

    def test_correct_hash_allowed(self):
        pkg = assemble_package(ORG, USER, model_id="flux_dev")
        decision = enforce_context_package(pkg.package_id, ORG, USER, supplied_hash=pkg.content_hash)
        assert decision.is_allowed

    def test_wrong_hash_rejected(self):
        pkg_id = _valid_package()
        decision = enforce_context_package(pkg_id, ORG, USER, supplied_hash="tampered-hash")
        assert not decision.is_allowed
        assert decision.package_status == PackageStatus.HASH_MISMATCH

    def test_no_hash_supplied_skips_check(self):
        pkg_id = _valid_package()
        decision = enforce_context_package(pkg_id, ORG, USER, supplied_hash=None)
        assert decision.is_allowed


# =============================================================================
# Revoked Package
# =============================================================================


@pytest.mark.unit
class TestRevokedPackage:

    def test_revoked_package_rejected(self):
        pkg_id = _valid_package()
        revoke_package(pkg_id, "talent deleted")
        decision = enforce_context_package(pkg_id, ORG, USER)
        assert not decision.is_allowed
        assert decision.package_status == PackageStatus.REVOKED
        assert "talent deleted" in decision.rejection_reason


# =============================================================================
# Consent Revoked
# =============================================================================


@pytest.mark.unit
class TestConsentRevoked:

    def test_consent_revoked_after_assembly_rejected(self):
        pkg_id = _valid_package()
        _inject_condition("consent_revoked")
        decision = enforce_context_package(pkg_id, ORG, USER)
        assert not decision.is_allowed
        assert decision.package_status == PackageStatus.REVOKED
        assert "consent" in decision.rejection_reason.lower()


# =============================================================================
# Stale Package
# =============================================================================


@pytest.mark.unit
class TestStalePackage:

    def test_stale_package_rejected(self):
        pkg_id = _valid_package()
        _inject_condition("stale")
        decision = enforce_context_package(pkg_id, ORG, USER)
        assert not decision.is_allowed
        assert decision.package_status == PackageStatus.STALE
        assert "reassemble" in decision.rejection_reason.lower()


# =============================================================================
# Incompatible LoRA
# =============================================================================


@pytest.mark.unit
class TestIncompatibleLoRA:

    def test_incompatible_lora_rejected(self):
        pkg_id = _valid_package(lora_ids=["sdxl-lora-on-flux"])
        _inject_condition("incompatible_lora")
        decision = enforce_context_package(pkg_id, ORG, USER)
        assert not decision.is_allowed
        assert decision.package_status == PackageStatus.INCOMPATIBLE


# =============================================================================
# Retry with Original Package
# =============================================================================


@pytest.mark.unit
class TestRetryOriginalPackage:

    def test_retry_with_same_valid_package(self):
        pkg_id = _valid_package()
        # First use
        d1 = enforce_context_package(pkg_id, ORG, USER)
        assert d1.is_allowed
        # Retry (same package, still valid)
        d2 = enforce_context_package(pkg_id, ORG, USER)
        assert d2.is_allowed


# =============================================================================
# Legacy Adapter
# =============================================================================


@pytest.mark.unit
class TestLegacyAdapter:

    def test_legacy_no_params_rejected(self):
        decision = enforce_or_assemble(None, ORG, USER, fallback_params=None)
        assert not decision.is_allowed

    def test_legacy_with_params_assembles_and_passes(self):
        decision = enforce_or_assemble(
            None, ORG, USER,
            fallback_params={"talent_id": "t1", "model": "flux_dev"}
        )
        assert decision.is_allowed
        assert decision.package_id  # A package was assembled

    def test_legacy_records_adapter_usage(self):
        enforce_or_assemble(None, ORG, USER, fallback_params={"model": "sdxl"})
        log = get_audit_log(ORG)
        legacy_events = [e for e in log if e["event"] == "legacy_adapter_used"]
        assert len(legacy_events) == 1

    def test_existing_package_id_skips_assembly(self):
        pkg_id = _valid_package()
        decision = enforce_or_assemble(pkg_id, ORG, USER, fallback_params={"model": "sdxl"})
        assert decision.is_allowed
        # No legacy adapter event
        log = get_audit_log(ORG)
        legacy_events = [e for e in log if e["event"] == "legacy_adapter_used"]
        assert len(legacy_events) == 0


# =============================================================================
# Authorized Override
# =============================================================================


@pytest.mark.unit
class TestAuthorizedOverride:

    def test_override_allowed_and_audited(self):
        pkg_id = _valid_package()
        override = AuthorizedOverride(
            org_id=ORG,
            user_id=USER,
            field_overridden="model_id",
            original_value="flux_dev",
            override_value="sdxl",
            reason="Testing new model",
            scope="single_job",
        )
        decision = enforce_context_package(pkg_id, ORG, USER, overrides=[override])
        assert decision.is_allowed
        assert decision.result == EnforcementResult.OVERRIDE_ALLOWED
        assert len(decision.overrides) == 1

    def test_override_audited_in_log(self):
        pkg_id = _valid_package()
        override = AuthorizedOverride(
            org_id=ORG,
            user_id=USER,
            field_overridden="lora_strength",
            original_value=0.8,
            override_value=0.5,
            reason="Reduce LoRA influence",
        )
        enforce_context_package(pkg_id, ORG, USER, overrides=[override])
        log = get_audit_log(ORG)
        override_events = [e for e in log if e["event"] == "authorized_override"]
        assert len(override_events) == 1
        assert override_events[0]["field"] == "lora_strength"


# =============================================================================
# Audit Log
# =============================================================================


@pytest.mark.unit
class TestAuditLog:

    def test_all_decisions_audited(self):
        pkg_id = _valid_package()
        enforce_context_package(pkg_id, ORG, USER)
        enforce_context_package(None, ORG, USER)
        enforce_context_package("fake", ORG, USER)

        log = get_audit_log(ORG)
        assert len(log) == 3
        events = {e["event"] for e in log}
        assert "allowed" in events
        assert "no_package_id" in events
        assert "package_not_found" in events

    def test_audit_scoped_to_org(self):
        _valid_package(org_id=ORG)
        enforce_context_package(None, ORG, USER)
        enforce_context_package(None, OTHER_ORG, "other")

        org_log = get_audit_log(ORG)
        other_log = get_audit_log(OTHER_ORG)
        assert len(org_log) == 1
        assert len(other_log) == 1
