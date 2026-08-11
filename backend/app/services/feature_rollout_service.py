"""Feature Rollout Service — capability state enforcement across all surfaces.

Implements the feature rollout control system (R19.9, R106) that determines
whether a capability is accessible through any surface (UI, API, Brain/Hermes,
MCP, direct execution).

A capability can be disabled at multiple scopes:
- global: disabled for everyone
- workspace: disabled for a specific org/workspace
- plan: disabled for a specific plan tier
- cohort: disabled for a specific user cohort
- user: disabled for a specific user
- workload: disabled for a specific workload type
- provider: disabled for a specific provider

When disabled, the capability is rejected with HTTP 403 CAPABILITY_DISABLED
regardless of request origin (UI, API, Brain/Hermes, MCP, direct path, forged).

Validates: Requirements R19.9, R106.1, R106.2, R106.3
"""

from __future__ import annotations

from enum import Enum
from uuid import UUID


# =============================================================================
# Enums
# =============================================================================


class RolloutScope(str, Enum):
    """Rollout scope for feature controls."""

    GLOBAL = "global"
    PLAN = "plan"
    WORKSPACE = "workspace"
    COHORT = "cohort"
    USER = "user"
    WORKLOAD = "workload"
    PROVIDER = "provider"


class Surface(str, Enum):
    """All invocation surfaces that must be blocked when a capability is disabled.

    R19.9 and R106.3 require rejection across ALL surfaces.
    """

    UI = "ui"
    API = "api"
    BRAIN_HERMES = "brain_hermes"
    MCP = "mcp"
    DIRECT = "direct"


# =============================================================================
# Errors
# =============================================================================


class CapabilityDisabledError(Exception):
    """Raised when a disabled capability is invoked through any surface.

    Maps to HTTP 403 with code CAPABILITY_DISABLED.
    This error is raised regardless of request origin per R19.9 and R106.3.
    """

    def __init__(self, capability_name: str, scope: RolloutScope) -> None:
        super().__init__(
            f"Capability '{capability_name}' is disabled (scope: {scope.value})"
        )
        self.status_code = 403
        self.code = "CAPABILITY_DISABLED"
        self.capability_name = capability_name
        self.scope = scope


# =============================================================================
# Service
# =============================================================================


class FeatureRolloutService:
    """Enforces feature rollout state across all surfaces.

    This service is the single enforcement point that checks whether a
    capability is accessible. When disabled (at any scope matching the
    request context), the request is ALWAYS rejected with 403 regardless
    of which surface the request originates from.

    Key invariants:
    1. A globally disabled capability is NEVER accessible through ANY surface,
       for ANY org/user/role combination.
    2. A workspace-scoped disable ONLY affects that workspace.
    3. Disabling one capability does NOT affect others (isolation).
    4. Re-enabling a capability restores access.

    Validates: Requirements R19.9, R106.1, R106.2, R106.3
    """

    def __init__(self) -> None:
        # Global disables: set of capability names disabled globally
        self._global_disabled: set[str] = set()

        # Workspace-scoped disables: capability_name → set of org_ids
        self._workspace_disabled: dict[str, set[UUID]] = {}

        # Plan-scoped disables: capability_name → set of plan names
        self._plan_disabled: dict[str, set[str]] = {}

        # Cohort-scoped disables: capability_name → set of cohort IDs
        self._cohort_disabled: dict[str, set[str]] = {}

        # User-scoped disables: capability_name → set of user_ids
        self._user_disabled: dict[str, set[UUID]] = {}

        # Workload-scoped disables: capability_name → set of workload types
        self._workload_disabled: dict[str, set[str]] = {}

        # Provider-scoped disables: capability_name → set of provider names
        self._provider_disabled: dict[str, set[str]] = {}

    # -------------------------------------------------------------------------
    # State Management
    # -------------------------------------------------------------------------

    def disable_capability(
        self,
        capability_name: str,
        scope: RolloutScope = RolloutScope.GLOBAL,
        target: str | UUID | None = None,
    ) -> None:
        """Disable a capability at the specified scope.

        Args:
            capability_name: Name of the capability to disable.
            scope: Scope of the disable (global, workspace, plan, etc.).
            target: Scope-specific target (org_id, plan name, etc.).
                    Required for all scopes except GLOBAL.
        """
        if scope == RolloutScope.GLOBAL:
            self._global_disabled.add(capability_name)
        elif scope == RolloutScope.WORKSPACE:
            if capability_name not in self._workspace_disabled:
                self._workspace_disabled[capability_name] = set()
            self._workspace_disabled[capability_name].add(
                target if isinstance(target, UUID) else UUID(str(target))
            )
        elif scope == RolloutScope.PLAN:
            if capability_name not in self._plan_disabled:
                self._plan_disabled[capability_name] = set()
            self._plan_disabled[capability_name].add(str(target))
        elif scope == RolloutScope.COHORT:
            if capability_name not in self._cohort_disabled:
                self._cohort_disabled[capability_name] = set()
            self._cohort_disabled[capability_name].add(str(target))
        elif scope == RolloutScope.USER:
            if capability_name not in self._user_disabled:
                self._user_disabled[capability_name] = set()
            self._user_disabled[capability_name].add(
                target if isinstance(target, UUID) else UUID(str(target))
            )
        elif scope == RolloutScope.WORKLOAD:
            if capability_name not in self._workload_disabled:
                self._workload_disabled[capability_name] = set()
            self._workload_disabled[capability_name].add(str(target))
        elif scope == RolloutScope.PROVIDER:
            if capability_name not in self._provider_disabled:
                self._provider_disabled[capability_name] = set()
            self._provider_disabled[capability_name].add(str(target))

    def enable_capability(
        self,
        capability_name: str,
        scope: RolloutScope = RolloutScope.GLOBAL,
        target: str | UUID | None = None,
    ) -> None:
        """Re-enable a previously disabled capability at the specified scope.

        Args:
            capability_name: Name of the capability to enable.
            scope: Scope of the enable.
            target: Scope-specific target.
        """
        if scope == RolloutScope.GLOBAL:
            self._global_disabled.discard(capability_name)
        elif scope == RolloutScope.WORKSPACE:
            if capability_name in self._workspace_disabled:
                self._workspace_disabled[capability_name].discard(
                    target if isinstance(target, UUID) else UUID(str(target))
                )
        elif scope == RolloutScope.PLAN:
            if capability_name in self._plan_disabled:
                self._plan_disabled[capability_name].discard(str(target))
        elif scope == RolloutScope.COHORT:
            if capability_name in self._cohort_disabled:
                self._cohort_disabled[capability_name].discard(str(target))
        elif scope == RolloutScope.USER:
            if capability_name in self._user_disabled:
                self._user_disabled[capability_name].discard(
                    target if isinstance(target, UUID) else UUID(str(target))
                )
        elif scope == RolloutScope.WORKLOAD:
            if capability_name in self._workload_disabled:
                self._workload_disabled[capability_name].discard(str(target))
        elif scope == RolloutScope.PROVIDER:
            if capability_name in self._provider_disabled:
                self._provider_disabled[capability_name].discard(str(target))

    # -------------------------------------------------------------------------
    # Enforcement
    # -------------------------------------------------------------------------

    def check_capability(
        self,
        capability_name: str,
        surface: Surface,
        *,
        org_id: UUID | None = None,
        user_id: UUID | None = None,
        plan: str | None = None,
        cohort: str | None = None,
        workload: str | None = None,
        provider: str | None = None,
    ) -> None:
        """Check if a capability is accessible for the given context.

        Raises CapabilityDisabledError (HTTP 403, CAPABILITY_DISABLED) if the
        capability is disabled at any matching scope. The surface parameter is
        intentionally NOT checked against — a disabled capability is ALWAYS
        rejected regardless of surface (R19.9, R106.3).

        Args:
            capability_name: The capability being invoked.
            surface: The invocation surface (for audit — NOT for filtering).
            org_id: The requesting workspace/org.
            user_id: The requesting user.
            plan: The workspace's plan tier.
            cohort: The user's cohort.
            workload: The workload type.
            provider: The provider being used.

        Raises:
            CapabilityDisabledError: When the capability is disabled.
        """
        # Global check first — overrides everything
        if capability_name in self._global_disabled:
            raise CapabilityDisabledError(capability_name, RolloutScope.GLOBAL)

        # Workspace-scoped check
        if org_id is not None and capability_name in self._workspace_disabled:
            if org_id in self._workspace_disabled[capability_name]:
                raise CapabilityDisabledError(
                    capability_name, RolloutScope.WORKSPACE
                )

        # Plan-scoped check
        if plan is not None and capability_name in self._plan_disabled:
            if plan in self._plan_disabled[capability_name]:
                raise CapabilityDisabledError(
                    capability_name, RolloutScope.PLAN
                )

        # Cohort-scoped check
        if cohort is not None and capability_name in self._cohort_disabled:
            if cohort in self._cohort_disabled[capability_name]:
                raise CapabilityDisabledError(
                    capability_name, RolloutScope.COHORT
                )

        # User-scoped check
        if user_id is not None and capability_name in self._user_disabled:
            if user_id in self._user_disabled[capability_name]:
                raise CapabilityDisabledError(
                    capability_name, RolloutScope.USER
                )

        # Workload-scoped check
        if workload is not None and capability_name in self._workload_disabled:
            if workload in self._workload_disabled[capability_name]:
                raise CapabilityDisabledError(
                    capability_name, RolloutScope.WORKLOAD
                )

        # Provider-scoped check
        if provider is not None and capability_name in self._provider_disabled:
            if provider in self._provider_disabled[capability_name]:
                raise CapabilityDisabledError(
                    capability_name, RolloutScope.PROVIDER
                )

    def is_capability_enabled(
        self,
        capability_name: str,
        *,
        org_id: UUID | None = None,
        user_id: UUID | None = None,
        plan: str | None = None,
        cohort: str | None = None,
        workload: str | None = None,
        provider: str | None = None,
    ) -> bool:
        """Non-raising check for capability availability.

        Returns False if the capability is disabled at any matching scope.
        """
        try:
            self.check_capability(
                capability_name,
                Surface.API,  # Surface doesn't matter for the check
                org_id=org_id,
                user_id=user_id,
                plan=plan,
                cohort=cohort,
                workload=workload,
                provider=provider,
            )
            return True
        except CapabilityDisabledError:
            return False
