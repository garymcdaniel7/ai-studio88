"""Simulation Isolation Tests (Story 099).

Proves: production guards reject simulation, catalog excludes simulation,
promotion blocked, assignment blocked, quarantine works, namespace isolation,
and environment controls.

Run with:
    pytest tests/unit/test_simulation_isolation.py -v
"""
from __future__ import annotations

import pytest

from backend.simulation_isolation import (
    DEV_SIMULATION_ENV,
    DEFAULT_SIMULATION_ENV,
    CatalogEntry,
    QuarantineReason,
    SimulationEnvironment,
    SimulationGuardError,
    VersionReference,
    clear_quarantine,
    compute_storage_namespace,
    filter_production_catalog,
    filter_simulation_catalog,
    get_quarantined,
    guard_approval,
    guard_context_reference,
    guard_deployment,
    guard_generation_use,
    guard_promotion,
    guard_talent_assignment,
    is_simulation_path,
    quarantine_record,
    scan_for_violations,
    validate_production_reference,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_quarantine()
    yield
    clear_quarantine()


# =============================================================================
# Lifecycle Guards
# =============================================================================


class TestLifecycleGuards:

    @pytest.mark.unit
    def test_approval_blocked_for_simulation(self):
        """Simulation cannot be approved."""
        with pytest.raises(SimulationGuardError) as exc_info:
            guard_approval(is_simulation=True)
        assert exc_info.value.code == "APPROVAL_DENIED"

    @pytest.mark.unit
    def test_approval_allowed_for_production(self):
        """Production can be approved."""
        guard_approval(is_simulation=False)  # No exception

    @pytest.mark.unit
    def test_promotion_blocked_for_simulation(self):
        """Simulation cannot be promoted."""
        with pytest.raises(SimulationGuardError) as exc_info:
            guard_promotion(is_simulation=True)
        assert exc_info.value.code == "PROMOTION_DENIED"

    @pytest.mark.unit
    def test_promotion_allowed_for_production(self):
        """Production can be promoted."""
        guard_promotion(is_simulation=False)

    @pytest.mark.unit
    def test_deployment_blocked_for_simulation(self):
        """Simulation cannot be deployed."""
        with pytest.raises(SimulationGuardError):
            guard_deployment(is_simulation=True)

    @pytest.mark.unit
    def test_assignment_blocked_for_simulation(self):
        """Simulation cannot be assigned to production talent."""
        with pytest.raises(SimulationGuardError) as exc_info:
            guard_talent_assignment(is_simulation=True)
        assert exc_info.value.code == "ASSIGNMENT_DENIED"

    @pytest.mark.unit
    def test_context_reference_blocked_for_simulation(self):
        """Production context cannot reference simulation."""
        with pytest.raises(SimulationGuardError):
            guard_context_reference(is_simulation=True)

    @pytest.mark.unit
    def test_generation_blocked_for_simulation(self):
        """Production generation cannot use simulation."""
        with pytest.raises(SimulationGuardError) as exc_info:
            guard_generation_use(is_simulation=True)
        assert exc_info.value.code == "GENERATION_DENIED"

    @pytest.mark.unit
    def test_generation_allowed_in_dev_mode(self):
        """Generation with simulation allowed when dev mode explicitly enabled."""
        guard_generation_use(is_simulation=True, allow_dev_mode=True)  # No exception

    @pytest.mark.unit
    def test_all_guards_pass_for_production(self):
        """All guards pass for production artifacts."""
        guard_approval(is_simulation=False)
        guard_promotion(is_simulation=False)
        guard_deployment(is_simulation=False)
        guard_talent_assignment(is_simulation=False)
        guard_context_reference(is_simulation=False)
        guard_generation_use(is_simulation=False)


# =============================================================================
# Catalog Exclusion
# =============================================================================


class TestCatalogExclusion:

    @pytest.mark.unit
    def test_production_catalog_excludes_simulation(self):
        """Production catalog filters out all simulation entries."""
        entries = [
            CatalogEntry(version_id="v-1", name="Model A", is_simulation=False),
            CatalogEntry(version_id="v-2", name="Model B Sim", is_simulation=True),
            CatalogEntry(version_id="v-3", name="Model C", is_simulation=False),
        ]
        result = filter_production_catalog(entries)
        assert len(result) == 2
        assert all(not e.is_simulation for e in result)

    @pytest.mark.unit
    def test_simulation_catalog_shows_only_simulation(self):
        """Dev catalog shows only simulation entries."""
        entries = [
            CatalogEntry(version_id="v-1", name="Prod", is_simulation=False),
            CatalogEntry(version_id="v-2", name="Sim", is_simulation=True),
        ]
        result = filter_simulation_catalog(entries)
        assert len(result) == 1
        assert result[0].is_simulation is True

    @pytest.mark.unit
    def test_empty_catalog_returns_empty(self):
        """Empty catalog returns empty list."""
        assert filter_production_catalog([]) == []

    @pytest.mark.unit
    def test_all_simulation_catalog_returns_empty_production(self):
        """Catalog with only simulation entries returns empty for production."""
        entries = [
            CatalogEntry(version_id="v-1", name="Sim A", is_simulation=True),
            CatalogEntry(version_id="v-2", name="Sim B", is_simulation=True),
        ]
        assert filter_production_catalog(entries) == []


# =============================================================================
# Direct API Reference Protection
# =============================================================================


class TestDirectAPIProtection:

    @pytest.mark.unit
    def test_production_reference_passes(self):
        """Production version reference passes validation."""
        ref = VersionReference(version_id="v-prod", is_simulation=False)
        validate_production_reference(ref)  # No exception

    @pytest.mark.unit
    def test_simulation_reference_rejected(self):
        """Simulation version reference rejected even when explicitly supplied."""
        ref = VersionReference(version_id="v-sim-123", is_simulation=True)
        with pytest.raises(SimulationGuardError) as exc_info:
            validate_production_reference(ref)
        assert exc_info.value.code == "REFERENCE_DENIED"
        assert "v-sim-123" in exc_info.value.message


# =============================================================================
# Storage Namespace
# =============================================================================


class TestStorageNamespace:

    @pytest.mark.unit
    def test_simulation_uses_simulation_prefix(self):
        """Simulation storage uses /_simulation/ prefix."""
        path = compute_storage_namespace(
            "org-1", "talent-1", "lineage-1", 3, is_simulation=True,
        )
        assert path.startswith("/_simulation/")
        assert "v3.safetensors" in path

    @pytest.mark.unit
    def test_production_uses_standard_prefix(self):
        """Production storage uses standard / prefix."""
        path = compute_storage_namespace(
            "org-1", "talent-1", "lineage-1", 2, is_simulation=False,
        )
        assert not path.startswith("/_simulation/")
        assert path.startswith("/org-1/")
        assert "v2.safetensors" in path

    @pytest.mark.unit
    def test_is_simulation_path_detection(self):
        """is_simulation_path correctly identifies namespace."""
        assert is_simulation_path("/_simulation/org-1/models/t-1/l-1/v1.safetensors") is True
        assert is_simulation_path("/org-1/models/t-1/l-1/v1.safetensors") is False

    @pytest.mark.unit
    def test_namespaces_never_overlap(self):
        """Production and simulation paths for same version never overlap."""
        prod = compute_storage_namespace("org-1", "t-1", "l-1", 1, is_simulation=False)
        sim = compute_storage_namespace("org-1", "t-1", "l-1", 1, is_simulation=True)
        assert prod != sim


# =============================================================================
# Quarantine
# =============================================================================


class TestQuarantine:

    @pytest.mark.unit
    def test_quarantine_creates_record(self):
        """Quarantining creates an audit record."""
        record = quarantine_record(
            version_id="v-bad",
            org_id="org-1",
            talent_id="talent-1",
            prior_lifecycle="active",
            reason=QuarantineReason.SIMULATION_IN_ACTIVE,
            notes="Found during migration scan",
        )
        assert record.version_id == "v-bad"
        assert record.prior_lifecycle == "active"
        assert record.reason == QuarantineReason.SIMULATION_IN_ACTIVE

    @pytest.mark.unit
    def test_scan_detects_simulation_in_active(self):
        """Scan identifies simulation records in active state."""
        versions = [
            {"version_id": "v-1", "is_simulation": False, "lifecycle": "active", "org_id": "org-1"},
            {"version_id": "v-2", "is_simulation": True, "lifecycle": "active", "org_id": "org-1"},
            {"version_id": "v-3", "is_simulation": True, "lifecycle": "superseded", "org_id": "org-1"},
        ]
        quarantined = scan_for_violations(versions)
        assert len(quarantined) == 1
        assert quarantined[0].version_id == "v-2"

    @pytest.mark.unit
    def test_scan_detects_simulation_in_approved(self):
        """Scan catches simulation in approved state."""
        versions = [
            {"version_id": "v-1", "is_simulation": True, "lifecycle": "approved", "org_id": "org-1"},
        ]
        quarantined = scan_for_violations(versions)
        assert len(quarantined) == 1
        assert quarantined[0].reason == QuarantineReason.SIMULATION_IN_APPROVED

    @pytest.mark.unit
    def test_scan_ignores_production_active(self):
        """Scan does not quarantine legitimate production active records."""
        versions = [
            {"version_id": "v-1", "is_simulation": False, "lifecycle": "active", "org_id": "org-1"},
        ]
        quarantined = scan_for_violations(versions)
        assert len(quarantined) == 0

    @pytest.mark.unit
    def test_scan_ignores_simulation_in_safe_state(self):
        """Simulation in superseded/retired is not quarantined (already safe)."""
        versions = [
            {"version_id": "v-1", "is_simulation": True, "lifecycle": "superseded", "org_id": "org-1"},
            {"version_id": "v-2", "is_simulation": True, "lifecycle": "retired", "org_id": "org-1"},
            {"version_id": "v-3", "is_simulation": True, "lifecycle": "created", "org_id": "org-1"},
        ]
        quarantined = scan_for_violations(versions)
        assert len(quarantined) == 0

    @pytest.mark.unit
    def test_get_quarantined_by_org(self):
        """Quarantine retrieval is tenant-scoped."""
        quarantine_record(
            version_id="v-1", org_id="org-1", prior_lifecycle="active",
            reason=QuarantineReason.SIMULATION_IN_ACTIVE,
        )
        quarantine_record(
            version_id="v-2", org_id="org-2", prior_lifecycle="active",
            reason=QuarantineReason.SIMULATION_IN_ACTIVE,
        )
        org1 = get_quarantined("org-1")
        assert len(org1) == 1
        assert org1[0].version_id == "v-1"

    @pytest.mark.unit
    def test_quarantine_serializable(self):
        """QuarantineRecord.to_dict() is JSON-serializable."""
        import json
        record = quarantine_record(
            version_id="v-1", org_id="org-1", prior_lifecycle="active",
            reason=QuarantineReason.SIMULATION_IN_ACTIVE,
        )
        json.dumps(record.to_dict())


# =============================================================================
# Environment Controls
# =============================================================================


class TestEnvironmentControls:

    @pytest.mark.unit
    def test_default_env_simulation_disabled(self):
        """Default production environment has simulation disabled."""
        assert DEFAULT_SIMULATION_ENV.enabled is False
        assert DEFAULT_SIMULATION_ENV.is_accessible(auth_dev_mode=False) is False

    @pytest.mark.unit
    def test_dev_env_requires_dev_mode(self):
        """Dev environment requires AUTH_DEV_MODE=true."""
        assert DEV_SIMULATION_ENV.enabled is True
        assert DEV_SIMULATION_ENV.is_accessible(auth_dev_mode=False) is False
        assert DEV_SIMULATION_ENV.is_accessible(auth_dev_mode=True) is True

    @pytest.mark.unit
    def test_custom_env_no_dev_mode_requirement(self):
        """Custom environment can waive dev mode requirement."""
        env = SimulationEnvironment(enabled=True, requires_dev_mode=False)
        assert env.is_accessible(auth_dev_mode=False) is True

    @pytest.mark.unit
    def test_disabled_env_never_accessible(self):
        """Disabled environment is never accessible regardless of flags."""
        env = SimulationEnvironment(enabled=False, requires_dev_mode=False)
        assert env.is_accessible(auth_dev_mode=True) is False
