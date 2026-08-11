"""Unit tests for CapabilityRegistryService.

Tests the capability registry including:
- Classification enum values (7 states)
- get_all_capabilities() returns all registered capabilities
- get_capability() single lookup + not found error
- is_available() checks DISABLED/MISSING exclusion
- update_classification() transitions with audit logging
- get_transitions() audit log retrieval
- check_available() raises appropriate errors for MISSING/DISABLED
- Default capabilities sourced from CAPABILITY_MAP.md

No I/O, no DB — pure unit tests mocking nothing (service is in-memory).

Validates: Requirements R19.1, R19.2, R19.3, R19.6, R19.7, R19.8, R19.9
"""

from __future__ import annotations

import pytest

from app.services.capability_registry import (
    Capability,
    CapabilityClassification,
    CapabilityDisabledRegistryError,
    CapabilityNotFoundError,
    CapabilityNotImplementedError,
    CapabilityRegistryService,
    ClassificationTransition,
    HealthStatus,
)


# =============================================================================
# Fixtures
# =============================================================================


def make_test_capabilities() -> list[Capability]:
    """Create a minimal set of test capabilities covering all classifications."""
    return [
        Capability(
            name="talent_crud",
            classification=CapabilityClassification.PRODUCTION,
            required_providers=["supabase"],
            health_status=HealthStatus.HEALTHY,
            description="Talent CRUD operations",
        ),
        Capability(
            name="image_generation",
            classification=CapabilityClassification.PARTIAL,
            required_providers=["comfyui", "gpu_worker"],
            health_status=HealthStatus.DEGRADED,
            description="Image generation (needs GPU worker)",
        ),
        Capability(
            name="video_generation",
            classification=CapabilityClassification.SIMULATED,
            required_providers=["comfyui"],
            health_status=HealthStatus.UNAVAILABLE,
            description="Video generation (simulated)",
        ),
        Capability(
            name="batch_generation",
            classification=CapabilityClassification.MISSING,
            required_providers=["comfyui"],
            health_status=HealthStatus.NOT_APPLICABLE,
            description="Batch generation (not implemented)",
        ),
        Capability(
            name="legacy_feedback",
            classification=CapabilityClassification.DEPRECATED,
            required_providers=[],
            health_status=HealthStatus.NOT_APPLICABLE,
            description="Legacy feedback system",
        ),
        Capability(
            name="platform_compute",
            classification=CapabilityClassification.DISABLED,
            required_providers=["runpod"],
            health_status=HealthStatus.NOT_APPLICABLE,
            description="Platform-managed compute (disabled)",
        ),
        Capability(
            name="new_feature",
            classification=CapabilityClassification.UNVERIFIED,
            required_providers=["supabase"],
            health_status=HealthStatus.HEALTHY,
            description="New feature (unverified)",
        ),
    ]


@pytest.fixture
def registry() -> CapabilityRegistryService:
    """Create a registry with test capabilities."""
    return CapabilityRegistryService(capabilities=make_test_capabilities())


@pytest.fixture
def empty_registry() -> CapabilityRegistryService:
    """Create an empty registry."""
    return CapabilityRegistryService(capabilities=[])


# =============================================================================
# Tests: CapabilityClassification enum
# =============================================================================


class TestCapabilityClassificationEnum:
    """Test that all 7 classification values exist."""

    @pytest.mark.unit
    def test_has_seven_values(self) -> None:
        """The enum contains exactly 7 classification states (R19.1)."""
        assert len(CapabilityClassification) == 7

    @pytest.mark.unit
    def test_production_value(self) -> None:
        """PRODUCTION classification exists."""
        assert CapabilityClassification.PRODUCTION == "production"

    @pytest.mark.unit
    def test_partial_value(self) -> None:
        """PARTIAL classification exists."""
        assert CapabilityClassification.PARTIAL == "partial"

    @pytest.mark.unit
    def test_simulated_value(self) -> None:
        """SIMULATED classification exists."""
        assert CapabilityClassification.SIMULATED == "simulated"

    @pytest.mark.unit
    def test_missing_value(self) -> None:
        """MISSING classification exists."""
        assert CapabilityClassification.MISSING == "missing"

    @pytest.mark.unit
    def test_deprecated_value(self) -> None:
        """DEPRECATED classification exists."""
        assert CapabilityClassification.DEPRECATED == "deprecated"

    @pytest.mark.unit
    def test_disabled_value(self) -> None:
        """DISABLED classification exists."""
        assert CapabilityClassification.DISABLED == "disabled"

    @pytest.mark.unit
    def test_unverified_value(self) -> None:
        """UNVERIFIED classification exists."""
        assert CapabilityClassification.UNVERIFIED == "unverified"


# =============================================================================
# Tests: get_all_capabilities
# =============================================================================


class TestGetAllCapabilities:
    """Test get_all_capabilities() returns all registered capabilities."""

    @pytest.mark.unit
    def test_returns_all_capabilities(self, registry: CapabilityRegistryService) -> None:
        """Returns all 7 test capabilities."""
        capabilities = registry.get_all_capabilities()
        assert len(capabilities) == 7

    @pytest.mark.unit
    def test_returns_empty_for_empty_registry(
        self, empty_registry: CapabilityRegistryService
    ) -> None:
        """Returns empty list when no capabilities registered."""
        capabilities = empty_registry.get_all_capabilities()
        assert capabilities == []

    @pytest.mark.unit
    def test_contains_production_capability(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Contains a PRODUCTION capability."""
        capabilities = registry.get_all_capabilities()
        names = [c.name for c in capabilities]
        assert "talent_crud" in names

    @pytest.mark.unit
    def test_capability_has_required_fields(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Each capability has name, classification, providers, health, description."""
        capabilities = registry.get_all_capabilities()
        for cap in capabilities:
            assert cap.name
            assert isinstance(cap.classification, CapabilityClassification)
            assert isinstance(cap.required_providers, list)
            assert isinstance(cap.health_status, HealthStatus)
            assert isinstance(cap.description, str)


# =============================================================================
# Tests: get_capability
# =============================================================================


class TestGetCapability:
    """Test get_capability() single lookup."""

    @pytest.mark.unit
    def test_returns_existing_capability(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Returns the correct capability for a valid name."""
        cap = registry.get_capability("talent_crud")
        assert cap.name == "talent_crud"
        assert cap.classification == CapabilityClassification.PRODUCTION
        assert "supabase" in cap.required_providers

    @pytest.mark.unit
    def test_raises_not_found_for_unknown_name(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Raises CapabilityNotFoundError for unknown capability name."""
        with pytest.raises(CapabilityNotFoundError) as exc_info:
            registry.get_capability("nonexistent_feature")
        assert "nonexistent_feature" in str(exc_info.value)

    @pytest.mark.unit
    def test_returns_disabled_capability(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Can look up a DISABLED capability (it exists in registry)."""
        cap = registry.get_capability("platform_compute")
        assert cap.classification == CapabilityClassification.DISABLED

    @pytest.mark.unit
    def test_returns_missing_capability(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Can look up a MISSING capability (it exists in registry)."""
        cap = registry.get_capability("batch_generation")
        assert cap.classification == CapabilityClassification.MISSING


# =============================================================================
# Tests: is_available
# =============================================================================


class TestIsAvailable:
    """Test is_available() check for usable capabilities."""

    @pytest.mark.unit
    def test_production_is_available(
        self, registry: CapabilityRegistryService
    ) -> None:
        """PRODUCTION capabilities are available."""
        assert registry.is_available("talent_crud") is True

    @pytest.mark.unit
    def test_partial_is_available(
        self, registry: CapabilityRegistryService
    ) -> None:
        """PARTIAL capabilities are available."""
        assert registry.is_available("image_generation") is True

    @pytest.mark.unit
    def test_simulated_is_available(
        self, registry: CapabilityRegistryService
    ) -> None:
        """SIMULATED capabilities are available (with simulation badge)."""
        assert registry.is_available("video_generation") is True

    @pytest.mark.unit
    def test_deprecated_is_available(
        self, registry: CapabilityRegistryService
    ) -> None:
        """DEPRECATED capabilities are still available (but discouraged)."""
        assert registry.is_available("legacy_feedback") is True

    @pytest.mark.unit
    def test_unverified_is_available(
        self, registry: CapabilityRegistryService
    ) -> None:
        """UNVERIFIED capabilities are available."""
        assert registry.is_available("new_feature") is True

    @pytest.mark.unit
    def test_disabled_is_not_available(
        self, registry: CapabilityRegistryService
    ) -> None:
        """DISABLED capabilities are NOT available (R19.9)."""
        assert registry.is_available("platform_compute") is False

    @pytest.mark.unit
    def test_missing_is_not_available(
        self, registry: CapabilityRegistryService
    ) -> None:
        """MISSING capabilities are NOT available (R19.8)."""
        assert registry.is_available("batch_generation") is False

    @pytest.mark.unit
    def test_raises_not_found_for_unknown(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Raises CapabilityNotFoundError for unknown capability."""
        with pytest.raises(CapabilityNotFoundError):
            registry.is_available("does_not_exist")


# =============================================================================
# Tests: update_classification
# =============================================================================


class TestUpdateClassification:
    """Test update_classification() transitions with logging (R19.6)."""

    @pytest.mark.unit
    def test_transitions_classification(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Updates the capability's classification to the new value."""
        registry.update_classification(
            name="video_generation",
            new_classification=CapabilityClassification.PARTIAL,
            actor="platform_operator_1",
            reason="GPU worker now available, promoting from simulated",
        )
        cap = registry.get_capability("video_generation")
        assert cap.classification == CapabilityClassification.PARTIAL

    @pytest.mark.unit
    def test_returns_transition_record(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Returns a ClassificationTransition with correct fields."""
        transition = registry.update_classification(
            name="video_generation",
            new_classification=CapabilityClassification.PRODUCTION,
            actor="admin_user",
            reason="Full production validation passed",
        )
        assert isinstance(transition, ClassificationTransition)
        assert transition.capability_name == "video_generation"
        assert transition.previous_classification == CapabilityClassification.SIMULATED
        assert transition.new_classification == CapabilityClassification.PRODUCTION
        assert transition.actor == "admin_user"
        assert transition.reason == "Full production validation passed"
        assert transition.timestamp is not None

    @pytest.mark.unit
    def test_logs_transition_timestamp(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Transition record includes a timestamp (R19.6)."""
        transition = registry.update_classification(
            name="talent_crud",
            new_classification=CapabilityClassification.DEPRECATED,
            actor="system",
            reason="Being replaced by new talent service",
        )
        assert transition.timestamp is not None

    @pytest.mark.unit
    def test_raises_not_found_for_unknown(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Raises CapabilityNotFoundError for unknown capability."""
        with pytest.raises(CapabilityNotFoundError):
            registry.update_classification(
                name="nonexistent",
                new_classification=CapabilityClassification.DISABLED,
                actor="test",
                reason="test",
            )

    @pytest.mark.unit
    def test_can_disable_a_capability(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Can transition any capability to DISABLED."""
        registry.update_classification(
            name="image_generation",
            new_classification=CapabilityClassification.DISABLED,
            actor="founder",
            reason="Temporarily disabled for maintenance",
        )
        assert registry.is_available("image_generation") is False

    @pytest.mark.unit
    def test_can_re_enable_disabled_capability(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Can transition a DISABLED capability back to PRODUCTION."""
        registry.update_classification(
            name="platform_compute",
            new_classification=CapabilityClassification.PRODUCTION,
            actor="founder",
            reason="Compute now available globally",
        )
        assert registry.is_available("platform_compute") is True


# =============================================================================
# Tests: get_transitions (audit log)
# =============================================================================


class TestGetTransitions:
    """Test get_transitions() audit log retrieval."""

    @pytest.mark.unit
    def test_empty_transitions_initially(
        self, registry: CapabilityRegistryService
    ) -> None:
        """No transitions logged initially."""
        transitions = registry.get_transitions()
        assert transitions == []

    @pytest.mark.unit
    def test_returns_transitions_for_capability(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Returns transitions filtered by capability name."""
        registry.update_classification(
            "talent_crud", CapabilityClassification.DEPRECATED, "actor1", "reason1"
        )
        registry.update_classification(
            "image_generation", CapabilityClassification.PRODUCTION, "actor2", "reason2"
        )

        talent_transitions = registry.get_transitions("talent_crud")
        assert len(talent_transitions) == 1
        assert talent_transitions[0].actor == "actor1"

    @pytest.mark.unit
    def test_returns_all_transitions_when_no_filter(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Returns all transitions when name is None."""
        registry.update_classification(
            "talent_crud", CapabilityClassification.DEPRECATED, "a1", "r1"
        )
        registry.update_classification(
            "image_generation", CapabilityClassification.PRODUCTION, "a2", "r2"
        )

        all_transitions = registry.get_transitions()
        assert len(all_transitions) == 2

    @pytest.mark.unit
    def test_multiple_transitions_for_same_capability(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Records multiple transitions for the same capability."""
        registry.update_classification(
            "video_generation", CapabilityClassification.PARTIAL, "a1", "first change"
        )
        registry.update_classification(
            "video_generation", CapabilityClassification.PRODUCTION, "a2", "second change"
        )

        transitions = registry.get_transitions("video_generation")
        assert len(transitions) == 2
        assert transitions[0].new_classification == CapabilityClassification.PARTIAL
        assert transitions[1].new_classification == CapabilityClassification.PRODUCTION


# =============================================================================
# Tests: check_available (enforcement)
# =============================================================================


class TestCheckAvailable:
    """Test check_available() raises correct errors for unavailable capabilities."""

    @pytest.mark.unit
    def test_production_does_not_raise(
        self, registry: CapabilityRegistryService
    ) -> None:
        """PRODUCTION capability does not raise."""
        # Should not raise
        registry.check_available("talent_crud")

    @pytest.mark.unit
    def test_partial_does_not_raise(
        self, registry: CapabilityRegistryService
    ) -> None:
        """PARTIAL capability does not raise."""
        registry.check_available("image_generation")

    @pytest.mark.unit
    def test_simulated_does_not_raise(
        self, registry: CapabilityRegistryService
    ) -> None:
        """SIMULATED capability does not raise."""
        registry.check_available("video_generation")

    @pytest.mark.unit
    def test_missing_raises_not_implemented(
        self, registry: CapabilityRegistryService
    ) -> None:
        """MISSING capability raises CapabilityNotImplementedError (R19.8)."""
        with pytest.raises(CapabilityNotImplementedError) as exc_info:
            registry.check_available("batch_generation")
        assert exc_info.value.status_code == 501
        assert exc_info.value.code == "CAPABILITY_NOT_IMPLEMENTED"
        assert exc_info.value.capability_name == "batch_generation"

    @pytest.mark.unit
    def test_disabled_raises_disabled_error(
        self, registry: CapabilityRegistryService
    ) -> None:
        """DISABLED capability raises CapabilityDisabledRegistryError (R19.9)."""
        with pytest.raises(CapabilityDisabledRegistryError) as exc_info:
            registry.check_available("platform_compute")
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "CAPABILITY_DISABLED"
        assert exc_info.value.capability_name == "platform_compute"

    @pytest.mark.unit
    def test_not_found_raises(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Unknown capability raises CapabilityNotFoundError."""
        with pytest.raises(CapabilityNotFoundError):
            registry.check_available("does_not_exist")


# =============================================================================
# Tests: register_capability
# =============================================================================


class TestRegisterCapability:
    """Test register_capability() for adding new capabilities."""

    @pytest.mark.unit
    def test_register_new_capability(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Can register a brand new capability."""
        new_cap = Capability(
            name="custom_workflow",
            classification=CapabilityClassification.UNVERIFIED,
            required_providers=["comfyui"],
            health_status=HealthStatus.HEALTHY,
            description="Custom workflow execution",
        )
        registry.register_capability(new_cap)

        cap = registry.get_capability("custom_workflow")
        assert cap.classification == CapabilityClassification.UNVERIFIED

    @pytest.mark.unit
    def test_register_replaces_existing(
        self, registry: CapabilityRegistryService
    ) -> None:
        """Registering an existing name replaces the capability."""
        updated = Capability(
            name="talent_crud",
            classification=CapabilityClassification.DEPRECATED,
            required_providers=["supabase"],
            health_status=HealthStatus.DEGRADED,
            description="Updated description",
        )
        registry.register_capability(updated)

        cap = registry.get_capability("talent_crud")
        assert cap.classification == CapabilityClassification.DEPRECATED
        assert cap.description == "Updated description"


# =============================================================================
# Tests: Default capabilities (CAPABILITY_MAP.md source)
# =============================================================================


class TestDefaultCapabilities:
    """Test that the default registry is populated from CAPABILITY_MAP.md."""

    @pytest.mark.unit
    def test_default_registry_has_capabilities(self) -> None:
        """Default registry (no args) is populated with known capabilities."""
        registry = CapabilityRegistryService()
        capabilities = registry.get_all_capabilities()
        assert len(capabilities) > 0

    @pytest.mark.unit
    def test_default_registry_contains_core_capabilities(self) -> None:
        """Default registry contains known core platform capabilities."""
        registry = CapabilityRegistryService()
        names = [c.name for c in registry.get_all_capabilities()]
        assert "talent_crud" in names
        assert "brain_chat" in names
        assert "image_generation" in names

    @pytest.mark.unit
    def test_default_registry_has_disabled_capability(self) -> None:
        """Default registry includes platform_compute as DISABLED."""
        registry = CapabilityRegistryService()
        cap = registry.get_capability("platform_compute")
        assert cap.classification == CapabilityClassification.DISABLED

    @pytest.mark.unit
    def test_default_registry_has_missing_capability(self) -> None:
        """Default registry includes batch_generation as MISSING."""
        registry = CapabilityRegistryService()
        cap = registry.get_capability("batch_generation")
        assert cap.classification == CapabilityClassification.MISSING

    @pytest.mark.unit
    def test_default_registry_has_all_classification_types(self) -> None:
        """Default registry covers all 7 classification types."""
        registry = CapabilityRegistryService()
        classifications = {
            c.classification for c in registry.get_all_capabilities()
        }
        assert CapabilityClassification.PRODUCTION in classifications
        assert CapabilityClassification.PARTIAL in classifications
        assert CapabilityClassification.SIMULATED in classifications
        assert CapabilityClassification.MISSING in classifications
        assert CapabilityClassification.DEPRECATED in classifications
        assert CapabilityClassification.DISABLED in classifications
        # UNVERIFIED may not be in defaults but that's ok
