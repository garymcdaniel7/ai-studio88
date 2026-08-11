"""Database-backed Feature Rollout Service.

Provides persistent feature rollout control via the feature_rollouts table.
This service complements the in-memory FeatureRolloutService by persisting
rollout rules to the database and evaluating them for each request context.

Evaluation logic:
    1. Check global rules first — if a global DISABLED rule exists, capability
       is blocked for everyone.
    2. Check narrower scopes in priority order: plan, workspace, cohort, user,
       workload, provider.
    3. Expired rules (expires_at < now()) are treated as inactive.
    4. If any active rule disables the capability for the given context,
       the capability is considered disabled.

No code deployment required for state changes — rules are read from the
database on each evaluation.

Validates: Requirements R106.1, R106.2, R106.3, R19.9, R19.10
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.feature_rollout import FeatureRollout

logger = get_logger(__name__)


class FeatureRolloutDBService:
    """Database-backed feature rollout management and evaluation.

    This service is the persistent backend for feature rollout controls.
    It provides:
        - CRUD operations for rollout rules
        - Evaluation of capability state against a request context
        - Expiry handling (expired rules are treated as inactive)

    Key invariants:
        1. A globally disabled capability is NEVER accessible through ANY
           surface, for ANY org/user/role combination.
        2. Scoped rules apply only to their matching context.
        3. Expired rules are ignored during evaluation.
        4. No code deployment required — rules are database-driven.

    Validates: Requirements R106.1, R106.2, R106.3, R19.9, R19.10
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -------------------------------------------------------------------------
    # Evaluation
    # -------------------------------------------------------------------------

    async def is_enabled(
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
        """Evaluate whether a capability is enabled for the given context.

        Checks all active (non-expired) rollout rules that match the
        capability name. Returns False (disabled) if any matching rule
        has enabled=False.

        Evaluation order:
            1. Global scope — if disabled globally, return False immediately.
            2. Narrower scopes — check each in order. If any matching scope
               has enabled=False, return False.

        Expired rollouts (expires_at < now()) are treated as inactive and
        ignored.

        Args:
            capability_name: The capability being checked.
            org_id: Workspace/org_id of the request.
            user_id: User making the request.
            plan: Plan tier of the workspace.
            cohort: User cohort.
            workload: Workload type.
            provider: Provider being used.

        Returns:
            True if the capability is enabled, False if disabled.
        """
        now = datetime.now(timezone.utc)

        # Fetch all active rules for this capability
        stmt = (
            select(FeatureRollout)
            .where(FeatureRollout.capability_name == capability_name)
        )
        result = await self.db.execute(stmt)
        rules = list(result.scalars().all())

        for rule in rules:
            # Skip expired rules
            if rule.expires_at is not None and rule.expires_at < now:
                continue

            # If rule is enabling (enabled=True), it doesn't block access
            if rule.enabled:
                continue

            # Rule is disabling (enabled=False) — check if it matches context
            if self._rule_matches_context(
                rule,
                org_id=org_id,
                user_id=user_id,
                plan=plan,
                cohort=cohort,
                workload=workload,
                provider=provider,
            ):
                return False

        return True

    def _rule_matches_context(
        self,
        rule: FeatureRollout,
        *,
        org_id: UUID | None = None,
        user_id: UUID | None = None,
        plan: str | None = None,
        cohort: str | None = None,
        workload: str | None = None,
        provider: str | None = None,
    ) -> bool:
        """Check if a rollout rule matches the given evaluation context.

        Global rules always match. Scoped rules match only when the
        scope_target matches the corresponding context value.
        """
        scope = rule.rollout_scope

        if scope == "global":
            return True
        elif scope == "workspace":
            return org_id is not None and rule.scope_target == str(org_id)
        elif scope == "plan":
            return plan is not None and rule.scope_target == plan
        elif scope == "cohort":
            return cohort is not None and rule.scope_target == cohort
        elif scope == "user":
            return user_id is not None and rule.scope_target == str(user_id)
        elif scope == "workload":
            return workload is not None and rule.scope_target == workload
        elif scope == "provider":
            return provider is not None and rule.scope_target == provider
        else:
            return False

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    async def create_rollout(
        self,
        capability_name: str,
        scope: str,
        target: str | None,
        enabled: bool,
        created_by: UUID,
        expires_at: datetime | None = None,
    ) -> FeatureRollout:
        """Create a new feature rollout rule.

        Args:
            capability_name: Name of the capability to control.
            scope: Rollout scope (global, plan, workspace, cohort, user, workload, provider).
            target: Scope-specific target. None for global scope.
            enabled: Whether the capability is enabled or disabled.
            created_by: User ID of the operator creating the rule.
            expires_at: Optional expiry timestamp.

        Returns:
            The created FeatureRollout record.
        """
        rollout = FeatureRollout(
            capability_name=capability_name,
            rollout_scope=scope,
            scope_target=target,
            enabled=enabled,
            created_by=created_by,
            expires_at=expires_at,
        )
        self.db.add(rollout)
        await self.db.flush()
        await self.db.refresh(rollout)

        logger.info(
            "feature_rollout_created",
            rollout_id=str(rollout.id),
            capability_name=capability_name,
            scope=scope,
            target=target,
            enabled=enabled,
            created_by=str(created_by),
        )

        return rollout

    async def delete_rollout(self, rollout_id: UUID) -> bool:
        """Delete a feature rollout rule by ID.

        Args:
            rollout_id: UUID of the rollout to delete.

        Returns:
            True if a row was deleted, False if not found.
        """
        stmt = delete(FeatureRollout).where(FeatureRollout.id == rollout_id)
        result = await self.db.execute(stmt)
        deleted = result.rowcount > 0

        if deleted:
            logger.info(
                "feature_rollout_deleted",
                rollout_id=str(rollout_id),
            )

        return deleted

    async def list_rollouts(
        self,
        capability_name: str | None = None,
    ) -> list[FeatureRollout]:
        """List all active (non-expired) rollout rules.

        Args:
            capability_name: Optional filter by capability name.

        Returns:
            List of FeatureRollout records (excluding expired ones).
        """
        now = datetime.now(timezone.utc)

        stmt = select(FeatureRollout)

        if capability_name is not None:
            stmt = stmt.where(
                FeatureRollout.capability_name == capability_name
            )

        # Exclude expired rules
        stmt = stmt.where(
            (FeatureRollout.expires_at.is_(None))
            | (FeatureRollout.expires_at >= now)
        )

        stmt = stmt.order_by(FeatureRollout.created_at.desc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_rollout(self, rollout_id: UUID) -> FeatureRollout | None:
        """Get a single rollout rule by ID.

        Args:
            rollout_id: UUID of the rollout.

        Returns:
            FeatureRollout if found, None otherwise.
        """
        stmt = select(FeatureRollout).where(FeatureRollout.id == rollout_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
