"""Workspace Privacy Restrictions Service.

Manages per-workspace privacy and provider restrictions. These restrictions
control which providers and infrastructure a workspace's data can flow through.

Restriction types:
- local_models_only: Only local LLM providers (Ollama, LM Studio) permitted
- customer_compute_only: Only customer-managed GPU, no platform compute
- approved_llm_only: Only whitelisted LLM providers
- no_external_llm_for_project: Specific project uses only local/approved LLMs
- approved_storage_only: Only whitelisted storage providers
- talent_provider_restriction: Specific talent uses only certain providers
- project_privacy: Project-scoped combined privacy settings

Brain/Hermes, LLM routing, job dispatch, and all execution paths check
these restrictions. If a restriction prevents fulfilling a request, the
system returns an error rather than silently violating the policy.

Validates: Requirements R103.1, R103.2, R103.3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.workspace_privacy import VALID_RESTRICTION_TYPES

logger = get_logger(__name__)


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(frozen=True)
class PrivacyRestriction:
    """A single privacy restriction for a workspace.

    Attributes:
        id: Unique restriction ID.
        org_id: The workspace this restriction belongs to.
        restriction_type: Type of restriction applied.
        restriction_target: Optional scoped target (project_id, talent_id).
        allowed_providers: Whitelisted providers (empty = no whitelist filter).
        denied_providers: Blocklisted providers.
        created_at: When the restriction was created.
        updated_at: When the restriction was last updated.
    """

    id: UUID
    org_id: UUID
    restriction_type: str
    restriction_target: str | None = None
    allowed_providers: list[str] = field(default_factory=list)
    denied_providers: list[str] = field(default_factory=list)
    created_at: "datetime | None" = None
    updated_at: "datetime | None" = None


@dataclass(frozen=True)
class ProviderCheckResult:
    """Result of checking whether a provider is allowed.

    Attributes:
        allowed: Whether the provider is permitted.
        reason: Human-readable reason if denied.
        restriction_type: Which restriction type caused denial (if denied).
    """

    allowed: bool
    reason: str = ""
    restriction_type: str = ""


# =============================================================================
# Errors
# =============================================================================


class PrivacyRestrictionViolationError(Exception):
    """Raised when a provider is blocked by workspace privacy restrictions.

    Maps to HTTP 403 PRIVACY_POLICY_BLOCKED.
    """

    def __init__(
        self,
        provider_name: str,
        org_id: UUID,
        restriction_type: str,
        reason: str,
    ) -> None:
        self.provider_name = provider_name
        self.org_id = org_id
        self.restriction_type = restriction_type
        self.reason = reason
        super().__init__(
            f"Privacy restriction '{restriction_type}' blocks provider "
            f"'{provider_name}' for workspace {org_id}: {reason}"
        )


class InvalidRestrictionTypeError(Exception):
    """Raised when an invalid restriction type is provided."""

    def __init__(self, restriction_type: str) -> None:
        self.restriction_type = restriction_type
        valid = ", ".join(sorted(VALID_RESTRICTION_TYPES))
        super().__init__(
            f"Invalid restriction type '{restriction_type}'. "
            f"Valid types: {valid}"
        )


# =============================================================================
# Service
# =============================================================================


class WorkspacePrivacyService:
    """Manages workspace privacy restrictions and enforces provider policies.

    This service provides:
    1. CRUD for privacy restrictions (get/set per workspace)
    2. Provider allowance checking against active restrictions
    3. Context-aware restriction evaluation (project, talent scoping)

    Constructor modes:
    - WorkspacePrivacyService(db=session) — production, DB-backed
    - WorkspacePrivacyService(restrictions=...) — testing, in-memory

    Validates: Requirements R103.1, R103.2, R103.3
    """

    def __init__(
        self,
        db: "AsyncSession | None" = None,
        restrictions: list[PrivacyRestriction] | None = None,
    ) -> None:
        self._db = db
        if restrictions is not None:
            self._in_memory = True
            self._restrictions = list(restrictions)
        else:
            self._in_memory = False
            self._restrictions: list[PrivacyRestriction] = []

    # =========================================================================
    # Restriction Management
    # =========================================================================

    async def get_restrictions(self, org_id: UUID) -> list[PrivacyRestriction]:
        """Retrieve all active privacy restrictions for a workspace.

        Args:
            org_id: The workspace to retrieve restrictions for.

        Returns:
            List of active PrivacyRestriction records for the workspace.
        """
        if self._in_memory:
            return [r for r in self._restrictions if r.org_id == org_id]

        if self._db is None:
            return []

        from sqlalchemy import select

        from app.models.workspace_privacy import WorkspacePrivacyConfigModel

        stmt = select(WorkspacePrivacyConfigModel).where(
            WorkspacePrivacyConfigModel.org_id == org_id,
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        return [
            PrivacyRestriction(
                id=row.id,
                org_id=row.org_id,
                restriction_type=row.restriction_type,
                restriction_target=row.restriction_target,
                allowed_providers=row.allowed_providers or [],
                denied_providers=row.denied_providers or [],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def set_restrictions(
        self,
        org_id: UUID,
        restrictions: list[dict],
    ) -> list[PrivacyRestriction]:
        """Replace all privacy restrictions for a workspace.

        This is a full replacement operation — existing restrictions are
        deleted and replaced with the provided list.

        Args:
            org_id: The workspace to configure.
            restrictions: List of restriction dicts with keys:
                restriction_type, restriction_target, allowed_providers,
                denied_providers.

        Returns:
            The new list of PrivacyRestriction records.

        Raises:
            InvalidRestrictionTypeError: If any restriction_type is invalid.
        """
        # Validate restriction types
        for r in restrictions:
            if r.get("restriction_type") not in VALID_RESTRICTION_TYPES:
                raise InvalidRestrictionTypeError(r.get("restriction_type", ""))

        if self._in_memory:
            import uuid as uuid_mod

            self._restrictions = [
                r for r in self._restrictions if r.org_id != org_id
            ]
            new_restrictions = []
            for r in restrictions:
                restriction = PrivacyRestriction(
                    id=uuid_mod.uuid4(),
                    org_id=org_id,
                    restriction_type=r["restriction_type"],
                    restriction_target=r.get("restriction_target"),
                    allowed_providers=r.get("allowed_providers", []),
                    denied_providers=r.get("denied_providers", []),
                )
                new_restrictions.append(restriction)
                self._restrictions.append(restriction)

            logger.info(
                "workspace_privacy_restrictions_set",
                org_id=str(org_id),
                restriction_count=len(new_restrictions),
            )
            return new_restrictions

        if self._db is None:
            raise RuntimeError("No database session available")

        from sqlalchemy import delete, select

        from app.models.workspace_privacy import WorkspacePrivacyConfigModel

        # Delete existing restrictions for this workspace
        await self._db.execute(
            delete(WorkspacePrivacyConfigModel).where(
                WorkspacePrivacyConfigModel.org_id == org_id,
            )
        )

        # Create new restriction records
        new_rows = []
        for r in restrictions:
            row = WorkspacePrivacyConfigModel(
                org_id=org_id,
                restriction_type=r["restriction_type"],
                restriction_target=r.get("restriction_target"),
                allowed_providers=r.get("allowed_providers", []),
                denied_providers=r.get("denied_providers", []),
            )
            self._db.add(row)
            new_rows.append(row)

        await self._db.flush()

        logger.info(
            "workspace_privacy_restrictions_set",
            org_id=str(org_id),
            restriction_count=len(new_rows),
        )

        return [
            PrivacyRestriction(
                id=row.id,
                org_id=row.org_id,
                restriction_type=row.restriction_type,
                restriction_target=row.restriction_target,
                allowed_providers=row.allowed_providers or [],
                denied_providers=row.denied_providers or [],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in new_rows
        ]

    async def remove_restriction(
        self,
        org_id: UUID,
        restriction_id: UUID,
    ) -> bool:
        """Remove a single privacy restriction by ID.

        Args:
            org_id: The workspace owning the restriction.
            restriction_id: The ID of the restriction to remove.

        Returns:
            True if a restriction was removed, False if not found.
        """
        if self._in_memory:
            original_count = len(self._restrictions)
            self._restrictions = [
                r
                for r in self._restrictions
                if not (r.org_id == org_id and r.id == restriction_id)
            ]
            removed = len(self._restrictions) < original_count
            if removed:
                logger.info(
                    "workspace_privacy_restriction_removed",
                    org_id=str(org_id),
                    restriction_id=str(restriction_id),
                )
            return removed

        if self._db is None:
            raise RuntimeError("No database session available")

        from sqlalchemy import delete

        from app.models.workspace_privacy import WorkspacePrivacyConfigModel

        result = await self._db.execute(
            delete(WorkspacePrivacyConfigModel).where(
                WorkspacePrivacyConfigModel.org_id == org_id,
                WorkspacePrivacyConfigModel.id == restriction_id,
            )
        )
        removed = result.rowcount > 0
        if removed:
            await self._db.flush()
            logger.info(
                "workspace_privacy_restriction_removed",
                org_id=str(org_id),
                restriction_id=str(restriction_id),
            )
        return removed

    # =========================================================================
    # Provider Allowance Checking
    # =========================================================================

    async def check_provider_allowed(
        self,
        org_id: UUID,
        provider_name: str,
        context: str = "llm",
    ) -> ProviderCheckResult:
        """Check if a provider is allowed by workspace privacy restrictions.

        Evaluates all active restrictions for the workspace and determines
        whether the given provider is permitted for the specified context.

        Context types:
        - "llm": LLM provider check (evaluates local_models_only, approved_llm_only)
        - "compute": Compute provider check (evaluates customer_compute_only)
        - "storage": Storage provider check (evaluates approved_storage_only)

        Args:
            org_id: The workspace to check.
            provider_name: Name of the provider to validate.
            context: The operational context ("llm", "compute", "storage").

        Returns:
            ProviderCheckResult indicating allowed/denied with reason.
        """
        restrictions = await self.get_restrictions(org_id)
        return self._evaluate_restrictions(
            restrictions=restrictions,
            provider_name=provider_name,
            context=context,
        )

    def check_provider_allowed_sync(
        self,
        restrictions: list[PrivacyRestriction],
        provider_name: str,
        context: str = "llm",
        target: str | None = None,
    ) -> ProviderCheckResult:
        """Synchronous check for use in routing hot paths.

        Same logic as check_provider_allowed but takes pre-fetched
        restrictions to avoid async DB calls in tight loops.

        Args:
            restrictions: Pre-fetched list of workspace restrictions.
            provider_name: Name of the provider to validate.
            context: The operational context ("llm", "compute", "storage").
            target: Optional scoped target (project_id, talent_id).

        Returns:
            ProviderCheckResult indicating allowed/denied with reason.
        """
        return self._evaluate_restrictions(
            restrictions=restrictions,
            provider_name=provider_name,
            context=context,
            target=target,
        )

    # =========================================================================
    # Internal Evaluation Logic
    # =========================================================================

    def _evaluate_restrictions(
        self,
        restrictions: list[PrivacyRestriction],
        provider_name: str,
        context: str = "llm",
        target: str | None = None,
    ) -> ProviderCheckResult:
        """Evaluate privacy restrictions against a provider.

        Restriction evaluation logic:
        1. If 'local_models_only' is active and context is "llm": only allow
           local providers (ollama, lm_studio, local).
        2. If 'customer_compute_only' is active and context is "compute": deny
           platform-managed providers.
        3. If 'approved_llm_only' is active and context is "llm": provider must
           be in allowed_providers list.
        4. If 'no_external_llm_for_project' is active and target matches: only
           allow local providers for that project.
        5. If 'approved_storage_only' is active and context is "storage": provider
           must be in allowed_providers list.
        6. For any restriction: if provider is in denied_providers → blocked.
        7. For any restriction with a non-empty allowed_providers: if provider
           is not in allowed_providers → blocked.
        """
        provider_lower = provider_name.lower()

        # Known local LLM providers
        local_providers = {"ollama", "lm_studio", "lmstudio", "local"}

        for restriction in restrictions:
            # Skip restrictions that don't apply to the current target
            if restriction.restriction_target and target:
                if restriction.restriction_target != target:
                    continue
            elif restriction.restriction_target and not target:
                # Scoped restriction but no target context — skip
                continue

            rtype = restriction.restriction_type

            # ─── local_models_only ──────────────────────────────────────
            if rtype == "local_models_only" and context == "llm":
                if provider_lower not in local_providers:
                    return ProviderCheckResult(
                        allowed=False,
                        reason=(
                            f"Workspace requires local models only. "
                            f"Provider '{provider_name}' is not a local provider."
                        ),
                        restriction_type=rtype,
                    )

            # ─── customer_compute_only ──────────────────────────────────
            elif rtype == "customer_compute_only" and context == "compute":
                # Platform-managed providers are blocked
                platform_providers = {
                    "runpod", "fluidstack", "lambda_labs",
                    "tensordock", "vast_ai", "vastai",
                }
                if provider_lower in platform_providers:
                    return ProviderCheckResult(
                        allowed=False,
                        reason=(
                            f"Workspace requires customer-managed compute only. "
                            f"Platform provider '{provider_name}' is not permitted."
                        ),
                        restriction_type=rtype,
                    )

            # ─── approved_llm_only ──────────────────────────────────────
            elif rtype == "approved_llm_only" and context == "llm":
                allowed_lower = {p.lower() for p in restriction.allowed_providers}
                if allowed_lower and provider_lower not in allowed_lower:
                    return ProviderCheckResult(
                        allowed=False,
                        reason=(
                            f"Provider '{provider_name}' is not in the approved "
                            f"LLM provider list: {restriction.allowed_providers}"
                        ),
                        restriction_type=rtype,
                    )

            # ─── no_external_llm_for_project ────────────────────────────
            elif rtype == "no_external_llm_for_project" and context == "llm":
                # Only applies when target matches the restriction_target
                if restriction.restriction_target == target and target is not None:
                    if provider_lower not in local_providers:
                        return ProviderCheckResult(
                            allowed=False,
                            reason=(
                                f"Project '{target}' requires local models only. "
                                f"Provider '{provider_name}' is external."
                            ),
                            restriction_type=rtype,
                        )

            # ─── approved_storage_only ──────────────────────────────────
            elif rtype == "approved_storage_only" and context == "storage":
                allowed_lower = {p.lower() for p in restriction.allowed_providers}
                if allowed_lower and provider_lower not in allowed_lower:
                    return ProviderCheckResult(
                        allowed=False,
                        reason=(
                            f"Provider '{provider_name}' is not in the approved "
                            f"storage provider list: {restriction.allowed_providers}"
                        ),
                        restriction_type=rtype,
                    )

            # ─── talent_provider_restriction ────────────────────────────
            elif rtype == "talent_provider_restriction":
                if restriction.restriction_target == target and target is not None:
                    denied_lower = {
                        p.lower() for p in restriction.denied_providers
                    }
                    if provider_lower in denied_lower:
                        return ProviderCheckResult(
                            allowed=False,
                            reason=(
                                f"Provider '{provider_name}' is denied for "
                                f"talent '{target}'."
                            ),
                            restriction_type=rtype,
                        )
                    allowed_lower = {
                        p.lower() for p in restriction.allowed_providers
                    }
                    if allowed_lower and provider_lower not in allowed_lower:
                        return ProviderCheckResult(
                            allowed=False,
                            reason=(
                                f"Provider '{provider_name}' is not in the "
                                f"approved list for talent '{target}'."
                            ),
                            restriction_type=rtype,
                        )

            # ─── project_privacy ────────────────────────────────────────
            elif rtype == "project_privacy":
                if restriction.restriction_target == target and target is not None:
                    denied_lower = {
                        p.lower() for p in restriction.denied_providers
                    }
                    if provider_lower in denied_lower:
                        return ProviderCheckResult(
                            allowed=False,
                            reason=(
                                f"Provider '{provider_name}' is denied for "
                                f"project '{target}'."
                            ),
                            restriction_type=rtype,
                        )
                    allowed_lower = {
                        p.lower() for p in restriction.allowed_providers
                    }
                    if allowed_lower and provider_lower not in allowed_lower:
                        return ProviderCheckResult(
                            allowed=False,
                            reason=(
                                f"Provider '{provider_name}' is not in the "
                                f"approved list for project '{target}'."
                            ),
                            restriction_type=rtype,
                        )

            # ─── Global denied_providers check (any restriction) ────────
            denied_lower = {p.lower() for p in restriction.denied_providers}
            if provider_lower in denied_lower:
                return ProviderCheckResult(
                    allowed=False,
                    reason=(
                        f"Provider '{provider_name}' is in the denied list "
                        f"for restriction '{rtype}'."
                    ),
                    restriction_type=rtype,
                )

        # All restrictions passed
        return ProviderCheckResult(allowed=True)
