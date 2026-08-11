"""Property tests for Disabled Feature Universality — Task 24.3.

Property 22: Disabled Feature Universality
    For any capability with classification DISABLED (via Capability Registry
    or feature rollout), the capability SHALL NOT be invocable through ANY
    surface: UI, API, Brain/Hermes, MCP, direct execution path, or forged request.

This test file proves:
    22.1 — Globally DISABLED rejects ALL surface/org/user/role combinations
    22.2 — Workspace-scoped disable rejects ONLY the target workspace
    22.3 — Disabling one capability does NOT affect others (isolation)
    22.4 — Error response includes correct status code (403) and code
    22.5 — Re-enabling a capability restores access
    22.6 — Compute availability DISABLED composes with feature rollout

Validates: Requirements R19.9, R86.2, R106.3

Run with:
    pytest backend/tests/unit/test_property_disabled_feature_universality.py -v
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# =============================================================================
# Mock sqlalchemy and app.db.session BEFORE importing modules that depend on it.
# Follows the existing pattern from test_compute_availability.py.
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
from app.services.feature_rollout_service import (
    CapabilityDisabledError,
    FeatureRolloutService,
    RolloutScope,
    Surface,
)
from app.services.compute_availability_service import (
    ComputeAvailabilityService,
    ComputeAvailabilityState,
    PlatformComputeDisabledError,
    WorkloadType,
    WorkspaceRole,
)


# =============================================================================
# Hypothesis Strategies
# =============================================================================

# Strategy for any valid UUID
uuid_strategy = st.builds(uuid4)

# Strategy for capability names (realistic but varied)
capability_name_strategy = st.sampled_from([
    "image_generation",
    "video_generation",
    "lora_training",
    "voice_synthesis",
    "music_generation",
    "lip_sync",
    "brain_chat",
    "quick_edit",
    "publishing",
    "batch_generation",
    "scene_composer",
    "style_transfer",
])

# Strategy for any surface
surface_strategy = st.sampled_from(list(Surface))

# Strategy for plan names
plan_strategy = st.sampled_from(["free", "starter", "pro", "enterprise"])

# Strategy for cohort identifiers
cohort_strategy = st.sampled_from(["beta_testers", "early_access", "public", "internal"])

# Strategy for workload types
workload_strategy = st.sampled_from([
    "image_generation", "video_generation", "training",
    "voice_audio", "batch_generation", "interactive_language",
])

# Strategy for provider names
provider_strategy = st.sampled_from([
    "vast_ai", "runpod", "local", "customer_managed", "fluidstack",
])

# Strategy for workspace roles (used in compute availability composition)
role_strategy = st.sampled_from(list(WorkspaceRole))

# Strategy for compute workload types
compute_workload_strategy = st.sampled_from(list(WorkloadType))


# =============================================================================
# Property 22.1: Global DISABLED Rejects ALL Requests
# Feature: production-revamp, Property 22.1
# =============================================================================


class TestProperty22_1_GlobalDisabledRejectsAll:
    """Property 22.1: Globally DISABLED capability rejects ALL requests.

    For ANY combination of capability name, surface, org_id, user_id,
    plan, cohort, workload, and provider — when a capability is globally
    DISABLED, check_capability MUST raise CapabilityDisabledError.

    This ensures R19.9: DISABLED capabilities SHALL be inaccessible through
    ALL surfaces: UI (not shown), API (rejected), Brain/Hermes (not
    recommended or invokable), MCP (not available), and direct execution paths.

    **Validates: Requirements R19.9, R106.3**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        capability=capability_name_strategy,
        surface=surface_strategy,
        org_id=uuid_strategy,
        user_id=uuid_strategy,
        plan=plan_strategy,
        cohort=cohort_strategy,
        workload=workload_strategy,
        provider=provider_strategy,
    )
    def test_globally_disabled_rejects_all_surfaces_and_contexts(
        self,
        capability: str,
        surface: Surface,
        org_id: UUID,
        user_id: UUID,
        plan: str,
        cohort: str,
        workload: str,
        provider: str,
    ) -> None:
        """Globally DISABLED capability rejects from ANY surface and context.

        **Validates: Requirements R19.9, R106.3**

        Property: For ANY combination of surface, org, user, plan, cohort,
        workload, and provider, a globally disabled capability MUST raise
        CapabilityDisabledError with status_code=403.
        """
        service = FeatureRolloutService()
        service.disable_capability(capability, RolloutScope.GLOBAL)

        with pytest.raises(CapabilityDisabledError) as exc_info:
            service.check_capability(
                capability,
                surface,
                org_id=org_id,
                user_id=user_id,
                plan=plan,
                cohort=cohort,
                workload=workload,
                provider=provider,
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "CAPABILITY_DISABLED"
        assert exc_info.value.scope == RolloutScope.GLOBAL

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        capability=capability_name_strategy,
        surface=surface_strategy,
        org_id=uuid_strategy,
    )
    def test_globally_disabled_not_bypassable_via_different_surfaces(
        self,
        capability: str,
        surface: Surface,
        org_id: UUID,
    ) -> None:
        """Cannot bypass global disable by switching surfaces (forged request).

        **Validates: Requirements R19.9**

        Property: The surface parameter does NOT influence the enforcement
        decision. A DISABLED capability is ALWAYS rejected regardless of
        whether the request claims to come from UI, API, Brain, MCP, or direct.
        """
        service = FeatureRolloutService()
        service.disable_capability(capability, RolloutScope.GLOBAL)

        # Try every single surface — all must fail
        for test_surface in Surface:
            with pytest.raises(CapabilityDisabledError):
                service.check_capability(
                    capability,
                    test_surface,
                    org_id=org_id,
                )


# =============================================================================
# Property 22.2: Workspace-Scoped Disable is Targeted
# Feature: production-revamp, Property 22.2
# =============================================================================


class TestProperty22_2_WorkspaceScopedDisable:
    """Property 22.2: Workspace-scoped disable rejects ONLY the target workspace.

    A capability disabled for workspace A must still be accessible for
    workspace B. This proves the disable is correctly scoped and does not
    over-block.

    **Validates: Requirements R106.3**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        capability=capability_name_strategy,
        surface=surface_strategy,
        target_org=uuid_strategy,
        other_org=uuid_strategy,
    )
    def test_workspace_disable_rejects_target_workspace(
        self,
        capability: str,
        surface: Surface,
        target_org: UUID,
        other_org: UUID,
    ) -> None:
        """Workspace-scoped disable rejects requests from the target org.

        **Validates: Requirements R106.3**

        Property: When a capability is disabled for a specific workspace,
        requests from that workspace are rejected from ANY surface.
        """
        assume(target_org != other_org)

        service = FeatureRolloutService()
        service.disable_capability(
            capability, RolloutScope.WORKSPACE, target=target_org
        )

        # Target workspace should be rejected
        with pytest.raises(CapabilityDisabledError) as exc_info:
            service.check_capability(capability, surface, org_id=target_org)

        assert exc_info.value.status_code == 403
        assert exc_info.value.scope == RolloutScope.WORKSPACE

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        capability=capability_name_strategy,
        surface=surface_strategy,
        target_org=uuid_strategy,
        other_org=uuid_strategy,
    )
    def test_workspace_disable_does_not_affect_other_workspaces(
        self,
        capability: str,
        surface: Surface,
        target_org: UUID,
        other_org: UUID,
    ) -> None:
        """Workspace-scoped disable does NOT affect other workspaces.

        **Validates: Requirements R106.3**

        Property: A different workspace that is NOT disabled should still
        be able to access the capability.
        """
        assume(target_org != other_org)

        service = FeatureRolloutService()
        service.disable_capability(
            capability, RolloutScope.WORKSPACE, target=target_org
        )

        # Other workspace should NOT be rejected (no exception)
        service.check_capability(capability, surface, org_id=other_org)


# =============================================================================
# Property 22.3: Capability Isolation
# Feature: production-revamp, Property 22.3
# =============================================================================


class TestProperty22_3_CapabilityIsolation:
    """Property 22.3: Disabling one capability does NOT affect others.

    Disabling capability A must not prevent access to capability B.
    This proves the enforcement is per-capability and does not leak.

    **Validates: Requirements R19.9, R106.3**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        disabled_cap=capability_name_strategy,
        other_cap=capability_name_strategy,
        surface=surface_strategy,
        org_id=uuid_strategy,
        user_id=uuid_strategy,
    )
    def test_disabling_one_capability_does_not_block_others(
        self,
        disabled_cap: str,
        other_cap: str,
        surface: Surface,
        org_id: UUID,
        user_id: UUID,
    ) -> None:
        """Disabled capability A does not block access to capability B.

        **Validates: Requirements R19.9**

        Property: For any two distinct capabilities, disabling one leaves
        the other accessible.
        """
        assume(disabled_cap != other_cap)

        service = FeatureRolloutService()
        service.disable_capability(disabled_cap, RolloutScope.GLOBAL)

        # Disabled capability should raise
        with pytest.raises(CapabilityDisabledError):
            service.check_capability(
                disabled_cap, surface, org_id=org_id, user_id=user_id
            )

        # Other capability should NOT raise
        service.check_capability(
            other_cap, surface, org_id=org_id, user_id=user_id
        )

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        disabled_cap=capability_name_strategy,
        other_cap=capability_name_strategy,
        org_id=uuid_strategy,
    )
    def test_workspace_scoped_disable_isolates_capabilities(
        self,
        disabled_cap: str,
        other_cap: str,
        org_id: UUID,
    ) -> None:
        """Workspace-scoped disable of one capability isolates from others.

        **Validates: Requirements R106.3**

        Property: Disabling capability A for workspace X does not disable
        capability B for workspace X.
        """
        assume(disabled_cap != other_cap)

        service = FeatureRolloutService()
        service.disable_capability(
            disabled_cap, RolloutScope.WORKSPACE, target=org_id
        )

        # Disabled capability should raise
        with pytest.raises(CapabilityDisabledError):
            service.check_capability(
                disabled_cap, Surface.API, org_id=org_id
            )

        # Other capability should NOT raise
        service.check_capability(other_cap, Surface.API, org_id=org_id)


# =============================================================================
# Property 22.4: Correct Error Response
# Feature: production-revamp, Property 22.4
# =============================================================================


class TestProperty22_4_CorrectErrorResponse:
    """Property 22.4: Error includes correct status code and error code.

    CapabilityDisabledError always has status_code=403 and
    code=CAPABILITY_DISABLED regardless of how it was triggered.

    **Validates: Requirements R19.9, R86.2, R106.3**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        capability=capability_name_strategy,
        surface=surface_strategy,
        org_id=uuid_strategy,
        scope=st.sampled_from(list(RolloutScope)),
    )
    def test_error_always_has_403_and_capability_disabled_code(
        self,
        capability: str,
        surface: Surface,
        org_id: UUID,
        scope: RolloutScope,
    ) -> None:
        """CapabilityDisabledError always returns 403 + CAPABILITY_DISABLED.

        **Validates: Requirements R19.9, R106.3**

        Property: For ANY scope and surface, the error response has
        status_code=403 and code='CAPABILITY_DISABLED'.
        """
        service = FeatureRolloutService()

        # Disable at the given scope with appropriate target
        if scope == RolloutScope.GLOBAL:
            service.disable_capability(capability, scope)
        elif scope == RolloutScope.WORKSPACE:
            service.disable_capability(capability, scope, target=org_id)
        elif scope == RolloutScope.USER:
            service.disable_capability(capability, scope, target=org_id)
        elif scope == RolloutScope.PLAN:
            service.disable_capability(capability, scope, target="pro")
        elif scope == RolloutScope.COHORT:
            service.disable_capability(capability, scope, target="beta_testers")
        elif scope == RolloutScope.WORKLOAD:
            service.disable_capability(
                capability, scope, target="image_generation"
            )
        elif scope == RolloutScope.PROVIDER:
            service.disable_capability(capability, scope, target="vast_ai")

        # Build check kwargs that match the scope target
        kwargs: dict = {"org_id": org_id}
        if scope == RolloutScope.USER:
            kwargs["user_id"] = org_id  # reuse UUID for user_id
        elif scope == RolloutScope.PLAN:
            kwargs["plan"] = "pro"
        elif scope == RolloutScope.COHORT:
            kwargs["cohort"] = "beta_testers"
        elif scope == RolloutScope.WORKLOAD:
            kwargs["workload"] = "image_generation"
        elif scope == RolloutScope.PROVIDER:
            kwargs["provider"] = "vast_ai"

        with pytest.raises(CapabilityDisabledError) as exc_info:
            service.check_capability(capability, surface, **kwargs)

        # Invariant: always 403
        assert exc_info.value.status_code == 403
        # Invariant: always CAPABILITY_DISABLED
        assert exc_info.value.code == "CAPABILITY_DISABLED"
        # Invariant: scope is correctly reported
        assert exc_info.value.scope == scope
        # Invariant: capability name is preserved
        assert exc_info.value.capability_name == capability


# =============================================================================
# Property 22.5: Re-enabling Restores Access
# Feature: production-revamp, Property 22.5
# =============================================================================


class TestProperty22_5_ReEnablingRestoresAccess:
    """Property 22.5: Re-enabling a capability makes it accessible again.

    After disable → enable cycle, the capability must be accessible.
    This proves state transitions are correct and no ghost blocks remain.

    **Validates: Requirements R106.3**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        capability=capability_name_strategy,
        surface=surface_strategy,
        org_id=uuid_strategy,
        user_id=uuid_strategy,
    )
    def test_global_disable_then_enable_restores_access(
        self,
        capability: str,
        surface: Surface,
        org_id: UUID,
        user_id: UUID,
    ) -> None:
        """Global disable → enable cycle restores full access.

        **Validates: Requirements R106.3**

        Property: After disabling then re-enabling a capability globally,
        it becomes accessible again from all surfaces.
        """
        service = FeatureRolloutService()

        # Disable globally
        service.disable_capability(capability, RolloutScope.GLOBAL)

        # Confirm it's blocked
        with pytest.raises(CapabilityDisabledError):
            service.check_capability(
                capability, surface, org_id=org_id, user_id=user_id
            )

        # Re-enable
        service.enable_capability(capability, RolloutScope.GLOBAL)

        # Should now be accessible (no exception)
        service.check_capability(
            capability, surface, org_id=org_id, user_id=user_id
        )

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        capability=capability_name_strategy,
        surface=surface_strategy,
        org_id=uuid_strategy,
    )
    def test_workspace_disable_then_enable_restores_access(
        self,
        capability: str,
        surface: Surface,
        org_id: UUID,
    ) -> None:
        """Workspace-scoped disable → enable cycle restores workspace access.

        **Validates: Requirements R106.3**

        Property: After disabling then re-enabling a capability for a
        workspace, that workspace can access it again.
        """
        service = FeatureRolloutService()

        # Disable for workspace
        service.disable_capability(
            capability, RolloutScope.WORKSPACE, target=org_id
        )

        # Confirm it's blocked
        with pytest.raises(CapabilityDisabledError):
            service.check_capability(capability, surface, org_id=org_id)

        # Re-enable
        service.enable_capability(
            capability, RolloutScope.WORKSPACE, target=org_id
        )

        # Should now be accessible
        service.check_capability(capability, surface, org_id=org_id)

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        capability=capability_name_strategy,
        surface=surface_strategy,
        org_id=uuid_strategy,
    )
    def test_is_capability_enabled_reflects_state_changes(
        self,
        capability: str,
        surface: Surface,
        org_id: UUID,
    ) -> None:
        """is_capability_enabled correctly reflects disable/enable transitions.

        **Validates: Requirements R106.3**
        """
        service = FeatureRolloutService()

        # Initially enabled
        assert service.is_capability_enabled(capability, org_id=org_id) is True

        # Disable
        service.disable_capability(capability, RolloutScope.GLOBAL)
        assert service.is_capability_enabled(capability, org_id=org_id) is False

        # Re-enable
        service.enable_capability(capability, RolloutScope.GLOBAL)
        assert service.is_capability_enabled(capability, org_id=org_id) is True


# =============================================================================
# Property 22.6: Compute Availability DISABLED Composes with Feature Rollout
# Feature: production-revamp, Property 22.6
# =============================================================================


class TestProperty22_6_ComputeAvailabilityComposition:
    """Property 22.6: Compute DISABLED overrides feature rollout ENABLED.

    Even if a capability is enabled via feature rollout, if the underlying
    compute availability is DISABLED, the request MUST still be rejected.
    The two controls compose: both must pass for access to be granted.

    **Validates: Requirements R86.2, R106.3**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        capability=capability_name_strategy,
        surface=surface_strategy,
        org_id=uuid_strategy,
        role=role_strategy,
        workload_type=compute_workload_strategy,
    )
    def test_compute_disabled_overrides_feature_enabled(
        self,
        capability: str,
        surface: Surface,
        org_id: UUID,
        role: WorkspaceRole,
        workload_type: WorkloadType,
    ) -> None:
        """Compute DISABLED blocks even when feature rollout allows.

        **Validates: Requirements R86.2**

        Property: When ComputeAvailabilityService state is DISABLED,
        attempting platform-managed compute ALWAYS raises
        PlatformComputeDisabledError even if the feature rollout service
        would allow the capability.
        """
        # Feature rollout allows the capability (not disabled)
        rollout_service = FeatureRolloutService()
        # No disable — capability is allowed by rollout

        # But compute is DISABLED at platform level
        compute_service = ComputeAvailabilityService(
            state=ComputeAvailabilityState.DISABLED
        )

        # Feature rollout passes (no exception)
        rollout_service.check_capability(capability, surface, org_id=org_id)

        # But compute check blocks
        with pytest.raises(PlatformComputeDisabledError) as exc_info:
            compute_service.check_availability(org_id, role, workload_type)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "PLATFORM_COMPUTE_DISABLED"

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        capability=capability_name_strategy,
        surface=surface_strategy,
        org_id=uuid_strategy,
        role=role_strategy,
        workload_type=compute_workload_strategy,
    )
    def test_both_disabled_both_reject(
        self,
        capability: str,
        surface: Surface,
        org_id: UUID,
        role: WorkspaceRole,
        workload_type: WorkloadType,
    ) -> None:
        """Both feature rollout AND compute disabled — both reject independently.

        **Validates: Requirements R86.2, R106.3**

        Property: When BOTH controls are disabled, each independently
        rejects the request. The rejections are independent — neither
        masks the other.
        """
        # Disable via feature rollout
        rollout_service = FeatureRolloutService()
        rollout_service.disable_capability(capability, RolloutScope.GLOBAL)

        # Disable via compute availability
        compute_service = ComputeAvailabilityService(
            state=ComputeAvailabilityState.DISABLED
        )

        # Feature rollout rejects
        with pytest.raises(CapabilityDisabledError) as exc_info:
            rollout_service.check_capability(capability, surface, org_id=org_id)
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "CAPABILITY_DISABLED"

        # Compute availability ALSO rejects independently
        with pytest.raises(PlatformComputeDisabledError) as exc_info2:
            compute_service.check_availability(org_id, role, workload_type)
        assert exc_info2.value.status_code == 403
        assert exc_info2.value.code == "PLATFORM_COMPUTE_DISABLED"

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        capability=capability_name_strategy,
        surface=surface_strategy,
        org_id=uuid_strategy,
        role=role_strategy,
        workload_type=compute_workload_strategy,
    )
    def test_feature_disabled_blocks_even_when_compute_enabled(
        self,
        capability: str,
        surface: Surface,
        org_id: UUID,
        role: WorkspaceRole,
        workload_type: WorkloadType,
    ) -> None:
        """Feature rollout DISABLED blocks even when compute is ENABLED.

        **Validates: Requirements R19.9, R106.3**

        Property: Compute ENABLED does not override a feature rollout
        disable. The feature rollout is an independent control layer.
        """
        # Disable via feature rollout
        rollout_service = FeatureRolloutService()
        rollout_service.disable_capability(capability, RolloutScope.GLOBAL)

        # Compute is ENABLED
        compute_service = ComputeAvailabilityService(
            state=ComputeAvailabilityState.ENABLED
        )

        # Compute passes (no exception)
        compute_service.check_availability(org_id, role, workload_type)

        # But feature rollout still blocks
        with pytest.raises(CapabilityDisabledError) as exc_info:
            rollout_service.check_capability(capability, surface, org_id=org_id)
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "CAPABILITY_DISABLED"

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        capability=capability_name_strategy,
        surface=surface_strategy,
        org_id=uuid_strategy,
        role=role_strategy,
        workload_type=compute_workload_strategy,
    )
    def test_both_enabled_allows_access(
        self,
        capability: str,
        surface: Surface,
        org_id: UUID,
        role: WorkspaceRole,
        workload_type: WorkloadType,
    ) -> None:
        """Both feature rollout AND compute enabled — access granted.

        **Validates: Requirements R86.2, R106.3**

        Property: When BOTH controls are in an allowing state, the request
        passes through without error.
        """
        # Feature rollout does NOT disable (default state)
        rollout_service = FeatureRolloutService()

        # Compute is ENABLED
        compute_service = ComputeAvailabilityService(
            state=ComputeAvailabilityState.ENABLED
        )

        # Both checks pass (no exception)
        rollout_service.check_capability(capability, surface, org_id=org_id)
        compute_service.check_availability(org_id, role, workload_type)
