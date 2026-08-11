"""Property tests for compute availability enforcement.

Property 14: Compute Availability Enforcement
    DISABLED state → API returns 403 regardless of request origin.
    For any API request for platform-managed compute when availability state
    is DISABLED, the response SHALL be HTTP 403 with code PLATFORM_COMPUTE_DISABLED
    — regardless of request origin (UI, direct API, forged).

Property 23: Compute Provider Neutrality
    Core contracts contain no provider-specific identifiers.
    For any job submission, governance evaluation, or cost reservation, the core
    contracts (ComputeProvider protocol, dataclasses) SHALL NOT contain RunPod-specific
    (or any provider-specific) identifiers.

Validates: Requirements R86.2, R13.15, R13.1, R13.2
"""

from __future__ import annotations

import ast
import inspect
import sys
from types import ModuleType
from typing import get_type_hints
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# =============================================================================
# Mock sqlalchemy and app.db.session BEFORE importing modules that depend on it.
# Follows the existing pattern from test_provisioning.py.
# =============================================================================

_sa_mock = MagicMock()
_sa_ext_mock = MagicMock()
_sa_ext_asyncio_mock = MagicMock()

_sa_ext_asyncio_mock.AsyncEngine = MagicMock
_sa_ext_asyncio_mock.AsyncSession = MagicMock
_sa_ext_asyncio_mock.async_sessionmaker = MagicMock
_sa_ext_asyncio_mock.create_async_engine = MagicMock

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.ext", _sa_ext_mock)
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.orm", MagicMock())

_mock_db_session = ModuleType("app.db.session")
_mock_db_session.get_db_session = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db", ModuleType("app.db"))
sys.modules.setdefault("app.db.session", _mock_db_session)

# Now safe to import our modules
from app.providers.compute import (
    ComputeMode,
    ComputeProvider,
    ComputeRequirements,
    CostEstimate,
    HealthState,
    HealthStatus,
    InstanceHandle,
    InstanceState,
    InstanceStatus,
    OfferInfo,
)
from app.services.compute_availability_service import (
    ComputeAvailabilityService,
    ComputeAvailabilityState,
    ComputeNotGrantedError,
    PlatformComputeDisabledError,
    WorkloadType,
    WorkspaceRole,
)


# =============================================================================
# Hypothesis Strategies
# =============================================================================

# Strategy for any valid UUID
uuid_strategy = st.builds(uuid4)

# Strategy for any workspace role
role_strategy = st.sampled_from(list(WorkspaceRole))

# Strategy for any workload type
workload_strategy = st.sampled_from(list(WorkloadType))


# =============================================================================
# Property 14: Compute Availability Enforcement
# Feature: production-revamp, Property 14: Compute Availability Enforcement
# =============================================================================


class TestProperty14ComputeAvailabilityEnforcement:
    """Property 14: DISABLED state → rejects ALL requests with 403.

    For any API request for platform-managed compute when availability state
    is DISABLED, the response SHALL be HTTP 403 with code PLATFORM_COMPUTE_DISABLED
    — regardless of request origin (UI, direct API, forged).

    **Validates: Requirements R86.2, R13.15**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        org_id=uuid_strategy,
        role=role_strategy,
        workload_type=workload_strategy,
    )
    def test_disabled_state_always_rejects(
        self,
        org_id: UUID,
        role: WorkspaceRole,
        workload_type: WorkloadType,
    ) -> None:
        """DISABLED state rejects ALL requests regardless of org, role, workload.

        **Validates: Requirements R86.2**

        Property: For ANY combination of org_id, role, and workload_type,
        when the state is DISABLED, check_availability MUST raise
        PlatformComputeDisabledError with status_code=403 and
        code=PLATFORM_COMPUTE_DISABLED.
        """
        service = ComputeAvailabilityService(
            state=ComputeAvailabilityState.DISABLED
        )

        with pytest.raises(PlatformComputeDisabledError) as exc_info:
            service.check_availability(org_id, role, workload_type)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "PLATFORM_COMPUTE_DISABLED"

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        org_id=uuid_strategy,
        role=role_strategy,
        workload_type=workload_strategy,
    )
    def test_disabled_state_not_bypassable_by_selective_grants(
        self,
        org_id: UUID,
        role: WorkspaceRole,
        workload_type: WorkloadType,
    ) -> None:
        """Even if an org was previously granted selective access, DISABLED blocks all.

        **Validates: Requirements R86.2**

        Property: Adding a selective grant and then switching to DISABLED
        must still reject the org's request unconditionally.
        """
        service = ComputeAvailabilityService(
            state=ComputeAvailabilityState.SELECTIVE
        )
        # Grant the org selective access
        service.add_selective_grant(org_id)

        # Switch to DISABLED
        service.set_state(ComputeAvailabilityState.DISABLED)

        with pytest.raises(PlatformComputeDisabledError) as exc_info:
            service.check_availability(org_id, role, workload_type)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "PLATFORM_COMPUTE_DISABLED"

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        org_id=uuid_strategy,
        role=role_strategy,
        workload_type=workload_strategy,
    )
    def test_enabled_state_always_allows(
        self,
        org_id: UUID,
        role: WorkspaceRole,
        workload_type: WorkloadType,
    ) -> None:
        """ENABLED state allows ALL requests regardless of org, role, workload.

        **Validates: Requirements R86.1**

        Property: For ANY combination of org_id, role, and workload_type,
        when the state is ENABLED, check_availability returns without error.
        """
        service = ComputeAvailabilityService(
            state=ComputeAvailabilityState.ENABLED
        )

        # Should not raise
        result = service.check_availability(org_id, role, workload_type)
        assert result is None

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        org_id=uuid_strategy,
        role=role_strategy,
        workload_type=workload_strategy,
    )
    def test_selective_rejects_non_granted_orgs(
        self,
        org_id: UUID,
        role: WorkspaceRole,
        workload_type: WorkloadType,
    ) -> None:
        """SELECTIVE state rejects requests from non-granted workspaces.

        **Validates: Requirements R86.3**

        Property: In SELECTIVE mode with no grants, ALL requests are rejected
        with ComputeNotGrantedError.
        """
        service = ComputeAvailabilityService(
            state=ComputeAvailabilityState.SELECTIVE
        )
        # No grants added — all orgs should be rejected

        with pytest.raises(ComputeNotGrantedError) as exc_info:
            service.check_availability(org_id, role, workload_type)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "COMPUTE_NOT_GRANTED"

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        org_id=uuid_strategy,
        role=role_strategy,
        workload_type=workload_strategy,
    )
    def test_selective_allows_granted_orgs(
        self,
        org_id: UUID,
        role: WorkspaceRole,
        workload_type: WorkloadType,
    ) -> None:
        """SELECTIVE state allows requests from granted workspaces.

        **Validates: Requirements R86.3**

        Property: In SELECTIVE mode, when the org_id IS in the grants set,
        check_availability returns without error for ANY role and workload.
        """
        service = ComputeAvailabilityService(
            state=ComputeAvailabilityState.SELECTIVE
        )
        service.add_selective_grant(org_id)

        # Should not raise
        result = service.check_availability(org_id, role, workload_type)
        assert result is None

    @pytest.mark.unit
    def test_is_platform_compute_available_disabled(self) -> None:
        """is_platform_compute_available returns False when DISABLED."""
        service = ComputeAvailabilityService(
            state=ComputeAvailabilityState.DISABLED
        )
        assert service.is_platform_compute_available() is False

    @pytest.mark.unit
    def test_is_platform_compute_available_enabled(self) -> None:
        """is_platform_compute_available returns True when ENABLED."""
        service = ComputeAvailabilityService(
            state=ComputeAvailabilityState.ENABLED
        )
        assert service.is_platform_compute_available() is True

    @pytest.mark.unit
    def test_is_platform_compute_available_selective(self) -> None:
        """is_platform_compute_available returns True when SELECTIVE."""
        service = ComputeAvailabilityService(
            state=ComputeAvailabilityState.SELECTIVE
        )
        assert service.is_platform_compute_available() is True


# =============================================================================
# Property 23: Compute Provider Neutrality
# Feature: production-revamp, Property 23: Compute Provider Neutrality
# =============================================================================

# Provider-specific identifiers that MUST NOT appear in the protocol file
PROVIDER_SPECIFIC_IDENTIFIERS = [
    # Vast.ai
    "vast",
    "vastai",
    "vast_ai",
    # RunPod
    "runpod",
    "run_pod",
    # FluidStack
    "fluidstack",
    "fluid_stack",
    # Lambda Labs
    "lambda",
    "lambdalabs",
    "lambda_labs",
    # TensorDock
    "tensordock",
    "tensor_dock",
    # Provider-specific field names
    "pod_id",
    "machine_id",
    "vast_id",
    "runpod_id",
]


class TestProperty23ComputeProviderNeutrality:
    """Property 23: Core contracts contain no provider-specific identifiers.

    For any job submission, governance evaluation, or cost reservation, the core
    contracts (ComputeProvider protocol, supporting dataclasses) SHALL NOT contain
    RunPod-specific (or any provider-specific) identifiers.

    **Validates: Requirements R13.1, R13.2**
    """

    @pytest.mark.unit
    def test_protocol_source_has_no_provider_identifiers(self) -> None:
        """ComputeProvider protocol source contains no provider-specific terms.

        **Validates: Requirements R13.1**

        Verifies: The compute.py module source code does not contain any
        provider-specific identifiers (vast, runpod, fluidstack, etc.).
        """
        import app.providers.compute as compute_module

        source = inspect.getsource(compute_module)
        source_lower = source.lower()

        for identifier in PROVIDER_SPECIFIC_IDENTIFIERS:
            assert identifier not in source_lower, (
                f"Provider-specific identifier '{identifier}' found in "
                f"app.providers.compute module source. The protocol must be "
                f"provider-agnostic."
            )

    @pytest.mark.unit
    def test_protocol_has_no_provider_specific_imports(self) -> None:
        """ComputeProvider module does not import from provider-specific packages.

        **Validates: Requirements R13.1**

        Verifies: The compute.py module does not import from any
        provider-specific package (providers/vast/, providers/runpod/, etc.).
        """
        import app.providers.compute as compute_module

        source = inspect.getsource(compute_module)
        tree = ast.parse(source)

        provider_packages = [
            "vast", "runpod", "fluidstack", "lambdalabs", "tensordock",
            "providers.vast", "providers.runpod", "providers.fluidstack",
            "backend.providers.vast", "backend.providers.runpod",
        ]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name_lower = alias.name.lower()
                    for pkg in provider_packages:
                        assert pkg not in name_lower, (
                            f"Provider-specific import '{alias.name}' found "
                            f"in compute protocol module."
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_lower = node.module.lower()
                    for pkg in provider_packages:
                        assert pkg not in module_lower, (
                            f"Provider-specific import from '{node.module}' "
                            f"found in compute protocol module."
                        )

    @pytest.mark.unit
    def test_protocol_methods_use_generic_identifiers(self) -> None:
        """ComputeProvider protocol methods use generic parameter names.

        **Validates: Requirements R13.1, R13.2**

        Verifies: All method signatures on ComputeProvider use generic terms
        (instance_id, requirements, etc.) and not provider-specific names.
        """
        import app.providers.compute as compute_module

        source = inspect.getsource(compute_module)
        tree = ast.parse(source)

        # Find the ComputeProvider class
        provider_class = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ComputeProvider":
                provider_class = node
                break

        assert provider_class is not None, "ComputeProvider class not found"

        # Check all method argument names
        for item in ast.walk(provider_class):
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                for arg in item.args.args:
                    arg_name = arg.arg.lower()
                    for identifier in PROVIDER_SPECIFIC_IDENTIFIERS:
                        assert identifier not in arg_name, (
                            f"Provider-specific parameter name '{arg.arg}' "
                            f"found in method '{item.name}' of ComputeProvider."
                        )

    @pytest.mark.unit
    def test_dataclass_fields_use_generic_identifiers(self) -> None:
        """Supporting dataclasses use generic field names only.

        **Validates: Requirements R13.1, R13.2**

        Verifies: ComputeRequirements, InstanceHandle, HealthStatus,
        InstanceStatus, OfferInfo, CostEstimate have no provider-specific fields.
        """
        dataclasses_to_check = [
            ComputeRequirements,
            InstanceHandle,
            HealthStatus,
            InstanceStatus,
            OfferInfo,
            CostEstimate,
        ]

        for cls in dataclasses_to_check:
            # Get field names from annotations
            annotations = get_type_hints(cls)
            for field_name in annotations:
                field_lower = field_name.lower()
                for identifier in PROVIDER_SPECIFIC_IDENTIFIERS:
                    assert identifier not in field_lower, (
                        f"Provider-specific field '{field_name}' found in "
                        f"dataclass '{cls.__name__}'. Core contracts must be "
                        f"provider-agnostic."
                    )

    @pytest.mark.unit
    def test_compute_mode_enum_is_generic(self) -> None:
        """ComputeMode enum values are provider-agnostic.

        **Validates: Requirements R13.2**

        Verifies: The three compute modes (PLATFORM_MANAGED, CUSTOMER_MANAGED,
        HYBRID) use generic terms without referencing specific providers.
        """
        expected_modes = {"platform_managed", "customer_managed", "hybrid"}
        actual_modes = {mode.value for mode in ComputeMode}
        assert actual_modes == expected_modes

        # Verify no provider-specific identifiers in enum values
        for mode in ComputeMode:
            for identifier in PROVIDER_SPECIFIC_IDENTIFIERS:
                assert identifier not in mode.value.lower(), (
                    f"Provider-specific identifier '{identifier}' found in "
                    f"ComputeMode value '{mode.value}'."
                )

    @pytest.mark.unit
    def test_protocol_defines_required_methods(self) -> None:
        """ComputeProvider protocol defines all required methods per R13.1.

        **Validates: Requirements R13.1**

        Required methods: provision, terminate, health_check, get_status,
        list_available, estimate_cost.
        """
        required_methods = {
            "provision",
            "terminate",
            "health_check",
            "get_status",
            "list_available",
            "estimate_cost",
        }

        # Check using dir() and filtering
        protocol_methods = {
            name for name in dir(ComputeProvider)
            if not name.startswith("_")
            and callable(getattr(ComputeProvider, name, None))
        }

        for method in required_methods:
            assert method in protocol_methods, (
                f"Required method '{method}' not found in ComputeProvider protocol."
            )

    @pytest.mark.unit
    def test_return_types_are_generic_dataclasses(self) -> None:
        """Protocol return types are generic dataclasses, not provider-specific.

        **Validates: Requirements R13.1**

        Verifies: InstanceHandle, HealthStatus, InstanceStatus, OfferInfo,
        CostEstimate are all defined in the compute protocol module (not imported
        from provider-specific packages).
        """
        import app.providers.compute as compute_module

        generic_types = [
            "ComputeRequirements",
            "InstanceHandle",
            "HealthStatus",
            "InstanceStatus",
            "OfferInfo",
            "CostEstimate",
        ]

        for type_name in generic_types:
            assert hasattr(compute_module, type_name), (
                f"Generic type '{type_name}' not found in "
                f"app.providers.compute module."
            )
            cls = getattr(compute_module, type_name)
            assert cls.__module__ == "app.providers.compute", (
                f"Type '{type_name}' should be defined in app.providers.compute, "
                f"but is from {cls.__module__}."
            )
