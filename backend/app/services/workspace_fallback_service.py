"""Workspace Fallback Preferences Service.

Manages per-workspace LLM provider fallback behavior (AUTO/ASK/STRICT) and
privacy policy enforcement. When the preferred provider is unavailable, the
fallback preference determines system behavior:

- AUTO: Route to next available provider in the chain.
- ASK: Pause and request confirmation before switching providers.
- STRICT: Fail or queue the request — never route elsewhere.

Privacy policies OVERRIDE fallback: if AUTO mode would route to a
denied provider, treat as STRICT (fail/queue rather than violate privacy).

Every routing decision is logged with: provider, model, routing_reason,
estimated_cost, fallback_chain.

Validates: Requirements R26.3, R26.4, R26.9, R102.1, R102.2, R102.3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class FallbackMode(str, Enum):
    """Workspace-level fallback behavior for LLM routing.

    AUTO: Automatically route to the next available provider.
    ASK: Return a confirmation prompt before switching providers.
    STRICT: Fail or queue the request — never fallback to another provider.
    """

    AUTO = "auto"
    ASK = "ask"
    STRICT = "strict"


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(frozen=True)
class WorkspaceFallbackConfig:
    """Per-workspace fallback configuration.

    Attributes:
        org_id: The workspace (organisation) this config belongs to.
        fallback_mode: Behavior when preferred provider is unavailable.
        denied_providers: Providers blocked by privacy policy for this workspace.
    """

    org_id: UUID
    fallback_mode: FallbackMode = FallbackMode.AUTO
    denied_providers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoutingDecisionLog:
    """Structured record of a routing decision for observability.

    Logged on every LLM routing attempt for auditability (R26.9).
    """

    org_id: UUID
    provider: str
    model: str
    routing_reason: str
    estimated_cost: float
    fallback_chain: list[str]
    fallback_mode: FallbackMode
    privacy_override_applied: bool = False


# =============================================================================
# Errors
# =============================================================================


class FallbackStrictDeniedError(Exception):
    """Raised when STRICT mode blocks fallback to another provider.

    In STRICT mode, if the preferred provider is unavailable, the request
    is rejected rather than routed elsewhere. Maps to HTTP 503.
    """

    def __init__(self, preferred_provider: str, available_providers: list[str]) -> None:
        self.preferred_provider = preferred_provider
        self.available_providers = available_providers
        super().__init__(
            f"STRICT mode: preferred provider '{preferred_provider}' unavailable. "
            f"Fallback denied. Available: {available_providers}"
        )


class FallbackAskRequiredError(Exception):
    """Raised when ASK mode requires user confirmation before switching.

    In ASK mode, the system pauses and returns the available alternatives
    to the client for confirmation. Maps to HTTP 300 (Multiple Choices)
    or a custom response indicating user action required.
    """

    def __init__(
        self,
        preferred_provider: str,
        alternative_providers: list[str],
    ) -> None:
        self.preferred_provider = preferred_provider
        self.alternative_providers = alternative_providers
        super().__init__(
            f"ASK mode: preferred provider '{preferred_provider}' unavailable. "
            f"Confirmation required. Alternatives: {alternative_providers}"
        )


class PrivacyPolicyViolationError(Exception):
    """Raised when a routing decision would violate privacy policies.

    Privacy policies override AUTO mode: if the only available providers
    are in the denied list, treat as STRICT and fail. Maps to HTTP 403.
    """

    def __init__(self, denied_provider: str, org_id: UUID) -> None:
        self.denied_provider = denied_provider
        self.org_id = org_id
        super().__init__(
            f"Privacy policy violation: provider '{denied_provider}' "
            f"is denied for workspace {org_id}"
        )


# =============================================================================
# Service
# =============================================================================


class WorkspaceFallbackService:
    """Manages workspace fallback preferences and enforces privacy policies.

    This service is the single source of truth for workspace-level
    LLM routing preferences. It provides:
    1. CRUD for fallback configuration (get/set per workspace)
    2. Privacy policy enforcement (denied_providers filtering)
    3. Routing decision validation against workspace preferences
    4. Comprehensive logging of every routing decision

    Constructor modes:
    - WorkspaceFallbackService(db=session) — production, DB-backed
    - WorkspaceFallbackService(config=...) — testing, in-memory

    Validates: Requirements R26.3, R26.4, R26.9, R102.1, R102.2, R102.3
    """

    def __init__(
        self,
        db: "AsyncSession | None" = None,
        config: WorkspaceFallbackConfig | None = None,
    ) -> None:
        self._db = db
        # In-memory mode for testing
        if config is not None:
            self._in_memory = True
            self._config = config
        else:
            self._in_memory = False
            self._config = None

    # =========================================================================
    # Configuration Management
    # =========================================================================

    async def get_config(self, org_id: UUID) -> WorkspaceFallbackConfig:
        """Retrieve the fallback configuration for a workspace.

        Returns default configuration (AUTO, no denied providers) if none exists.

        Args:
            org_id: The workspace to retrieve configuration for.

        Returns:
            WorkspaceFallbackConfig for the workspace.
        """
        if self._in_memory:
            return self._config or WorkspaceFallbackConfig(org_id=org_id)

        if self._db is None:
            return WorkspaceFallbackConfig(org_id=org_id)

        from sqlalchemy import select

        from app.models.workspace_fallback import WorkspaceFallbackConfigModel

        stmt = select(WorkspaceFallbackConfigModel).where(
            WorkspaceFallbackConfigModel.org_id == org_id,
        )
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            return WorkspaceFallbackConfig(org_id=org_id)

        return WorkspaceFallbackConfig(
            org_id=row.org_id,
            fallback_mode=FallbackMode(row.fallback_mode),
            denied_providers=row.denied_providers or [],
        )

    async def set_config(
        self,
        org_id: UUID,
        fallback_mode: FallbackMode,
        denied_providers: list[str],
        updated_by: UUID,
    ) -> WorkspaceFallbackConfig:
        """Create or update the fallback configuration for a workspace.

        This is an upsert operation — if a config exists, it is updated;
        otherwise a new record is created.

        Args:
            org_id: The workspace to configure.
            fallback_mode: The desired fallback behavior.
            denied_providers: List of provider names blocked by privacy policy.
            updated_by: User ID making the change (for audit).

        Returns:
            The updated WorkspaceFallbackConfig.
        """
        if self._in_memory:
            self._config = WorkspaceFallbackConfig(
                org_id=org_id,
                fallback_mode=fallback_mode,
                denied_providers=denied_providers,
            )
            return self._config

        if self._db is None:
            raise RuntimeError("No database session available")

        from sqlalchemy import select

        from app.models.workspace_fallback import WorkspaceFallbackConfigModel

        stmt = select(WorkspaceFallbackConfigModel).where(
            WorkspaceFallbackConfigModel.org_id == org_id,
        )
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            row = WorkspaceFallbackConfigModel(
                org_id=org_id,
                fallback_mode=fallback_mode.value,
                denied_providers=denied_providers,
                updated_by=updated_by,
            )
            self._db.add(row)
        else:
            row.fallback_mode = fallback_mode.value
            row.denied_providers = denied_providers
            row.updated_by = updated_by

        await self._db.flush()

        logger.info(
            "workspace_fallback_config_updated",
            org_id=str(org_id),
            fallback_mode=fallback_mode.value,
            denied_providers=denied_providers,
            updated_by=str(updated_by),
        )

        return WorkspaceFallbackConfig(
            org_id=org_id,
            fallback_mode=fallback_mode,
            denied_providers=denied_providers,
        )

    # =========================================================================
    # Privacy Policy Enforcement
    # =========================================================================

    def is_provider_denied(self, provider_name: str, config: WorkspaceFallbackConfig) -> bool:
        """Check if a provider is blocked by the workspace's privacy policy.

        Args:
            provider_name: The provider to check.
            config: The workspace fallback configuration.

        Returns:
            True if the provider is in the denied_providers list.
        """
        return provider_name.lower() in [p.lower() for p in config.denied_providers]

    def filter_allowed_providers(
        self,
        provider_names: list[str],
        config: WorkspaceFallbackConfig,
    ) -> list[str]:
        """Filter provider list to only those allowed by privacy policy.

        Args:
            provider_names: Full list of provider names in the chain.
            config: The workspace fallback configuration.

        Returns:
            List of provider names NOT in the denied list.
        """
        denied_lower = {p.lower() for p in config.denied_providers}
        return [p for p in provider_names if p.lower() not in denied_lower]

    # =========================================================================
    # Routing Decision Validation
    # =========================================================================

    def validate_routing_decision(
        self,
        selected_provider: str,
        all_providers: list[str],
        config: WorkspaceFallbackConfig,
        is_fallback: bool = False,
    ) -> None:
        """Validate a routing decision against workspace preferences.

        Enforces:
        1. Privacy: selected provider must not be in denied list.
        2. STRICT mode: if fallback is required, reject.
        3. ASK mode: if fallback is required, request confirmation.

        Privacy policies ALWAYS override: if AUTO mode would route to a denied
        provider, the system treats it as STRICT and fails.

        Args:
            selected_provider: The provider the router selected.
            all_providers: Full provider chain for context.
            config: The workspace fallback configuration.
            is_fallback: Whether this selection is a fallback (not first choice).

        Raises:
            PrivacyPolicyViolationError: If selected provider is denied.
            FallbackStrictDeniedError: If STRICT mode and fallback required.
            FallbackAskRequiredError: If ASK mode and fallback required.
        """
        # Privacy check ALWAYS applies (R26.9, R102.3)
        if self.is_provider_denied(selected_provider, config):
            logger.warning(
                "routing_privacy_violation_blocked",
                org_id=str(config.org_id),
                denied_provider=selected_provider,
                fallback_mode=config.fallback_mode.value,
            )
            raise PrivacyPolicyViolationError(
                denied_provider=selected_provider,
                org_id=config.org_id,
            )

        # Fallback mode enforcement (only when this IS a fallback)
        if not is_fallback:
            return

        allowed = self.filter_allowed_providers(all_providers, config)

        if config.fallback_mode == FallbackMode.STRICT:
            logger.info(
                "routing_strict_mode_denied",
                org_id=str(config.org_id),
                fallback_provider=selected_provider,
                available_providers=allowed,
            )
            raise FallbackStrictDeniedError(
                preferred_provider=all_providers[0] if all_providers else "unknown",
                available_providers=allowed,
            )

        if config.fallback_mode == FallbackMode.ASK:
            logger.info(
                "routing_ask_mode_confirmation_required",
                org_id=str(config.org_id),
                preferred_provider=all_providers[0] if all_providers else "unknown",
                alternatives=allowed,
            )
            raise FallbackAskRequiredError(
                preferred_provider=all_providers[0] if all_providers else "unknown",
                alternative_providers=allowed,
            )

        # AUTO mode with non-denied provider — allow the fallback
        return

    def resolve_effective_mode(
        self,
        config: WorkspaceFallbackConfig,
        candidate_providers: list[str],
    ) -> FallbackMode:
        """Resolve the effective fallback mode considering privacy overrides.

        If AUTO mode would only have denied providers available as fallback
        targets, the effective mode becomes STRICT (privacy override).

        Args:
            config: The workspace fallback configuration.
            candidate_providers: Providers that could serve as fallback.

        Returns:
            The effective FallbackMode after privacy override consideration.
        """
        if config.fallback_mode != FallbackMode.AUTO:
            return config.fallback_mode

        # Check if ALL remaining candidates are denied
        allowed = self.filter_allowed_providers(candidate_providers, config)
        if not allowed:
            logger.info(
                "routing_privacy_override_auto_to_strict",
                org_id=str(config.org_id),
                denied_providers=config.denied_providers,
                candidate_providers=candidate_providers,
            )
            return FallbackMode.STRICT

        return FallbackMode.AUTO

    # =========================================================================
    # Routing Decision Logging
    # =========================================================================

    def log_routing_decision(
        self,
        org_id: UUID,
        provider: str,
        model: str,
        routing_reason: str,
        estimated_cost: float,
        fallback_chain: list[str],
        fallback_mode: FallbackMode,
        privacy_override_applied: bool = False,
    ) -> RoutingDecisionLog:
        """Log a routing decision with full context for observability.

        Every routing decision is logged regardless of outcome. This
        provides a complete audit trail for debugging and analytics.

        Args:
            org_id: Workspace making the request.
            provider: Selected provider name.
            model: Model used for completion.
            routing_reason: Why this provider was selected.
            estimated_cost: Estimated cost in USD.
            fallback_chain: Full chain of attempted providers.
            fallback_mode: Active fallback mode for this workspace.
            privacy_override_applied: Whether privacy policy overrode AUTO→STRICT.

        Returns:
            RoutingDecisionLog record (also emitted to structured logs).
        """
        decision = RoutingDecisionLog(
            org_id=org_id,
            provider=provider,
            model=model,
            routing_reason=routing_reason,
            estimated_cost=estimated_cost,
            fallback_chain=fallback_chain,
            fallback_mode=fallback_mode,
            privacy_override_applied=privacy_override_applied,
        )

        logger.info(
            "llm_routing_decision",
            org_id=str(org_id),
            provider=provider,
            model=model,
            routing_reason=routing_reason,
            estimated_cost=estimated_cost,
            fallback_chain=fallback_chain,
            fallback_mode=fallback_mode.value,
            privacy_override_applied=privacy_override_applied,
        )

        return decision
