"""Compute Availability Service — Founder-controlled compute state enforcement.

Implements DISABLED/SELECTIVE/ENABLED compute availability states (R86).
State is stored in the database and cached with a 60-second TTL to ensure
configuration changes propagate without code deployment or service restart.

When DISABLED, all requests for platform-managed compute are rejected with
HTTP 403 PLATFORM_COMPUTE_DISABLED regardless of org, role, or workload.

When SELECTIVE, only workspaces/plans/cohorts/workloads/providers matching
an active (non-expired, non-revoked) grant record are allowed access.

Validates: Requirements R86.1, R86.2, R86.3, R86.5, R13.14, R13.15, R13.16
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.compute_availability import (
        ComputeAvailabilityConfig,
        ComputeSelectiveGrant,
    )

from app.core.logging import get_logger

logger = get_logger(__name__)

# Cache TTL in seconds — state propagates within this window (R86.5)
_CACHE_TTL_SECONDS: int = 60


# =============================================================================
# Enums
# =============================================================================


class ComputeAvailabilityState(str, Enum):
    """Founder-controlled global state for platform-managed compute.

    DISABLED: Entirely unavailable — all surfaces reject.
    SELECTIVE: Available to Founder-selected workspaces/cohorts.
    ENABLED: Available to all eligible workspaces.
    """

    DISABLED = "disabled"
    SELECTIVE = "selective"
    ENABLED = "enabled"


class GrantType(str, Enum):
    """Types of selective grants for enabling compute."""

    WORKSPACE = "workspace"
    PLAN = "plan"
    COHORT = "cohort"
    WORKLOAD = "workload"
    PROVIDER = "provider"
    PROMOTION = "promotion"


class WorkspaceRole(str, Enum):
    """Workspace membership roles (kept for backward compatibility)."""

    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class WorkloadType(str, Enum):
    """Workload classes for compute scheduling (R88)."""

    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    TRAINING = "training"
    VOICE_AUDIO = "voice_audio"
    BATCH_GENERATION = "batch_generation"
    INTERACTIVE_LANGUAGE = "interactive_language"
    PRODUCTION_STAGES = "production_stages"
    PUBLISHING = "publishing"


# =============================================================================
# Errors
# =============================================================================


class PlatformComputeDisabledError(Exception):
    """Raised when platform-managed compute is DISABLED and a request is made.

    Maps to HTTP 403 with code PLATFORM_COMPUTE_DISABLED.
    """

    def __init__(self) -> None:
        super().__init__("Platform-managed compute is currently disabled")
        self.status_code = 403
        self.code = "PLATFORM_COMPUTE_DISABLED"


class ComputeNotGrantedError(Exception):
    """Raised when compute is SELECTIVE and workspace is not granted access.

    Maps to HTTP 403 with code COMPUTE_NOT_GRANTED.
    """

    def __init__(self, reason: str = "") -> None:
        msg = "Platform-managed compute is not available for this workspace"
        if reason:
            msg = f"{msg}: {reason}"
        super().__init__(msg)
        self.status_code = 403
        self.code = "COMPUTE_NOT_GRANTED"


# =============================================================================
# Cached State
# =============================================================================


class _CachedState:
    """Internal cache for compute availability state.

    The cache holds the current state and the list of active selective grants.
    It refreshes from the database when the TTL expires (60 seconds max).
    This ensures configuration changes propagate without restart (R86.5).
    """

    def __init__(self) -> None:
        self._state: ComputeAvailabilityState = ComputeAvailabilityState.DISABLED
        self._grants: list = []
        self._last_refresh: float = 0.0
        self._changed_by: UUID | None = None
        self._changed_at: datetime | None = None
        self._reason: str | None = None

    @property
    def is_stale(self) -> bool:
        """Check if the cache needs refresh."""
        return (time.monotonic() - self._last_refresh) > _CACHE_TTL_SECONDS

    def update(
        self,
        state: ComputeAvailabilityState,
        grants: list,
        changed_by: UUID | None = None,
        changed_at: datetime | None = None,
        reason: str | None = None,
    ) -> None:
        """Update the cache with fresh data from the database."""
        self._state = state
        self._grants = grants
        self._changed_by = changed_by
        self._changed_at = changed_at
        self._reason = reason
        self._last_refresh = time.monotonic()

    @property
    def state(self) -> ComputeAvailabilityState:
        return self._state

    @property
    def grants(self) -> list:
        return self._grants

    @property
    def changed_by(self) -> UUID | None:
        return self._changed_by

    @property
    def changed_at(self) -> datetime | None:
        return self._changed_at

    @property
    def reason(self) -> str | None:
        return self._reason

    def invalidate(self) -> None:
        """Force cache refresh on next access."""
        self._last_refresh = 0.0


# Module-level cache instance (shared across requests in the same process)
_cache = _CachedState()


def invalidate_compute_cache() -> None:
    """Force the compute availability cache to refresh on next access.

    Call this after state changes to ensure immediate propagation
    within the same process.
    """
    _cache.invalidate()


# =============================================================================
# Service
# =============================================================================


class ComputeAvailabilityService:
    """Enforces compute availability state with DB-backed caching.

    This service is the single enforcement point that checks whether a request
    for platform-managed compute should be allowed or rejected based on:
    1. The global availability state (DISABLED/SELECTIVE/ENABLED)
    2. Selective grants (when in SELECTIVE mode)

    The enforcement is ABSOLUTE when DISABLED — no request may bypass it
    regardless of org_id, user role, workload type, or request origin.

    State is loaded from the database and cached with a 60-second TTL.
    Configuration changes propagate without code deployment or restart.

    Constructor modes:
    - ComputeAvailabilityService(db=session) — production, DB-backed
    - ComputeAvailabilityService(state=...) — testing, in-memory

    Validates: Requirements R86.1, R86.2, R86.3, R86.5, R13.14, R13.15, R13.16
    """

    def __init__(
        self,
        db: AsyncSession | None = None,
        state: ComputeAvailabilityState | None = None,
    ) -> None:
        self._db = db

        # In-memory mode (backward compatibility for testing)
        if state is not None:
            self._in_memory = True
            self._state = state
            self._selective_grants: set[UUID] = set()
        else:
            self._in_memory = False

    # =========================================================================
    # Backward-compatible synchronous interface (for property tests)
    # =========================================================================

    @property
    def state(self) -> ComputeAvailabilityState:
        """Current compute availability state (in-memory mode)."""
        if self._in_memory:
            return self._state
        return _cache.state

    def set_state(self, state: ComputeAvailabilityState) -> None:
        """Update the compute availability state (in-memory mode)."""
        if self._in_memory:
            self._state = state

    def add_selective_grant(self, org_id: UUID) -> None:
        """Grant a specific workspace access in SELECTIVE mode (in-memory)."""
        if self._in_memory:
            self._selective_grants.add(org_id)

    def remove_selective_grant(self, org_id: UUID) -> None:
        """Revoke a specific workspace's selective access (in-memory)."""
        if self._in_memory:
            self._selective_grants.discard(org_id)

    def check_availability(
        self,
        org_id: UUID,
        role: WorkspaceRole | None = None,
        workload_type: WorkloadType | None = None,
    ) -> None:
        """Synchronous check for compute availability (in-memory mode).

        Raises:
            PlatformComputeDisabledError: When state is DISABLED (always).
            ComputeNotGrantedError: When state is SELECTIVE and org not granted.
        """
        current_state = self._state if self._in_memory else _cache.state

        if current_state == ComputeAvailabilityState.DISABLED:
            raise PlatformComputeDisabledError()

        if current_state == ComputeAvailabilityState.SELECTIVE:
            if self._in_memory:
                if org_id not in self._selective_grants:
                    raise ComputeNotGrantedError()
            else:
                if not self._has_matching_grant(org_id, None, None):
                    raise ComputeNotGrantedError()

        return None

    # =========================================================================
    # Production async interface (DB-backed with cache)
    # =========================================================================

    async def _refresh_cache_if_stale(self) -> None:
        """Refresh the cached state from the database if TTL expired."""
        if not _cache.is_stale:
            return

        if self._db is None:
            # No DB session — fall back to safe default
            _cache.update(
                state=ComputeAvailabilityState.DISABLED,
                grants=[],
                reason="No database session — defaulting to disabled",
            )
            return

        from app.models.compute_availability import (
            ComputeAvailabilityConfig,
            ComputeSelectiveGrant,
        )
        from sqlalchemy import select

        # Fetch the latest state (most recent row by changed_at)
        state_stmt = (
            select(ComputeAvailabilityConfig)
            .order_by(ComputeAvailabilityConfig.changed_at.desc())
            .limit(1)
        )
        result = await self._db.execute(state_stmt)
        config_row = result.scalar_one_or_none()

        if config_row is None:
            # No config exists — default to DISABLED (safe default)
            _cache.update(
                state=ComputeAvailabilityState.DISABLED,
                grants=[],
                changed_by=None,
                changed_at=None,
                reason="No configuration found — defaulting to disabled",
            )
            return

        current_state = ComputeAvailabilityState(config_row.state)

        # Fetch active grants (not revoked, not expired)
        now = datetime.now(timezone.utc)
        grants_stmt = select(ComputeSelectiveGrant).where(
            ComputeSelectiveGrant.revoked_at.is_(None),
            # Filter out expired grants
            (ComputeSelectiveGrant.expires_at.is_(None))
            | (ComputeSelectiveGrant.expires_at > now),
        )
        grants_result = await self._db.execute(grants_stmt)
        active_grants = list(grants_result.scalars().all())

        _cache.update(
            state=current_state,
            grants=active_grants,
            changed_by=config_row.changed_by,
            changed_at=config_row.changed_at,
            reason=config_row.reason,
        )

        logger.debug(
            "compute_availability_cache_refreshed",
            state=current_state.value,
            active_grants=len(active_grants),
        )

    async def get_current_state(self) -> ComputeAvailabilityState:
        """Get the current compute availability state.

        Returns the cached state, refreshing from DB if TTL expired.
        """
        await self._refresh_cache_if_stale()
        return _cache.state

    async def get_state_details(self) -> dict:
        """Get full state details including metadata.

        Returns:
            Dictionary with state, changed_by, changed_at, reason, and grants.
        """
        await self._refresh_cache_if_stale()
        return {
            "state": _cache.state,
            "changed_by": _cache.changed_by,
            "changed_at": _cache.changed_at,
            "reason": _cache.reason,
            "grants": _cache.grants,
        }

    async def check_compute_availability(
        self,
        org_id: UUID,
        workload_class: str | None = None,
        provider: str | None = None,
    ) -> None:
        """Check if platform-managed compute is available for this request.

        This is the primary enforcement method. Call this before any
        platform-managed compute operation (provisioning, job dispatch, etc.).

        Args:
            org_id: The workspace requesting compute access.
            workload_class: Optional workload class for workload-specific grants.
            provider: Optional provider name for provider-specific grants.

        Raises:
            PlatformComputeDisabledError: When state is DISABLED (always).
            ComputeNotGrantedError: When state is SELECTIVE and no matching grant.

        When state is ENABLED, this method returns without error.

        The check is DEFINITIVE when DISABLED — it raises regardless of:
        - Any org_id value
        - Any user role (owner, admin, editor, viewer)
        - Any workload type
        - Whether the request came from UI, direct API, or forged request
        """
        await self._refresh_cache_if_stale()

        if _cache.state == ComputeAvailabilityState.DISABLED:
            logger.info(
                "compute_request_blocked_disabled",
                org_id=str(org_id),
                workload_class=workload_class,
                provider=provider,
            )
            raise PlatformComputeDisabledError()

        if _cache.state == ComputeAvailabilityState.SELECTIVE:
            if not self._has_matching_grant(org_id, workload_class, provider):
                logger.info(
                    "compute_request_blocked_no_grant",
                    org_id=str(org_id),
                    workload_class=workload_class,
                    provider=provider,
                )
                raise ComputeNotGrantedError()

        # ENABLED: no restriction — all eligible workspaces have access
        return None

    def _has_matching_grant(
        self,
        org_id: UUID,
        workload_class: str | None,
        provider: str | None,
    ) -> bool:
        """Check if any active grant matches the request.

        A request is granted if ANY of the following match:
        - A workspace grant for this org_id
        - A workload grant matching the workload_class
        - A provider grant matching the provider
        - A promotion grant (any active promotion enables access)

        Plan and cohort grants are matched by the caller providing
        the org_id (the service layer should resolve plan/cohort
        membership before calling this method if needed).
        """
        org_id_str = str(org_id)

        for grant in _cache.grants:
            grant_type = grant.grant_type if hasattr(grant, 'grant_type') else ""
            grant_target = grant.grant_target if hasattr(grant, 'grant_target') else ""

            if grant_type == GrantType.WORKSPACE.value:
                if grant_target == org_id_str:
                    return True

            elif grant_type == GrantType.WORKLOAD.value:
                if workload_class and grant_target == workload_class:
                    return True

            elif grant_type == GrantType.PROVIDER.value:
                if provider and grant_target == provider:
                    return True

            elif grant_type == GrantType.PROMOTION.value:
                # Any active promotion grants access to all
                return True

            elif grant_type == GrantType.PLAN.value:
                # Plan grants match by org's plan — for now, we check
                # if the org_id is directly the target (caller should
                # resolve plan membership externally)
                if grant_target == org_id_str:
                    return True

            elif grant_type == GrantType.COHORT.value:
                # Cohort grants — similar to plan, resolved externally
                if grant_target == org_id_str:
                    return True

        return False

    async def set_state_async(
        self,
        new_state: ComputeAvailabilityState,
        changed_by: UUID,
        reason: str | None = None,
    ) -> "ComputeAvailabilityConfig":
        """Change the compute availability state (Founder action).

        Inserts a new row in compute_availability_config (append-only audit).
        Invalidates the cache so the change propagates immediately in this
        process, and within 60 seconds in other processes.

        Args:
            new_state: The new availability state.
            changed_by: User ID of the Founder/operator making the change.
            reason: Optional reason for the state change.

        Returns:
            The new ComputeAvailabilityConfig record.
        """
        from app.models.compute_availability import ComputeAvailabilityConfig

        config = ComputeAvailabilityConfig(
            state=new_state.value,
            changed_by=changed_by,
            reason=reason,
        )
        self._db.add(config)
        await self._db.flush()

        # Invalidate cache for immediate propagation in this process
        invalidate_compute_cache()

        logger.info(
            "compute_availability_state_changed",
            new_state=new_state.value,
            changed_by=str(changed_by),
            reason=reason or "",
        )

        return config

    async def create_selective_grant(
        self,
        grant_type: GrantType,
        grant_target: str,
        granted_by: UUID,
        expires_at: datetime | None = None,
    ) -> "ComputeSelectiveGrant":
        """Create a new selective compute access grant.

        Args:
            grant_type: Type of grant (workspace, plan, cohort, etc.).
            grant_target: Target identifier for the grant.
            granted_by: User ID of the Founder/operator creating the grant.
            expires_at: Optional expiration time (NULL = permanent).

        Returns:
            The new ComputeSelectiveGrant record.
        """
        from app.models.compute_availability import ComputeSelectiveGrant

        grant = ComputeSelectiveGrant(
            grant_type=grant_type.value,
            grant_target=grant_target,
            granted_by=granted_by,
            expires_at=expires_at,
        )
        self._db.add(grant)
        await self._db.flush()

        # Invalidate cache so new grant is picked up
        invalidate_compute_cache()

        logger.info(
            "compute_selective_grant_created",
            grant_type=grant_type.value,
            grant_target=grant_target,
            granted_by=str(granted_by),
            expires_at=str(expires_at) if expires_at else "permanent",
        )

        return grant

    async def revoke_selective_grant(
        self,
        grant_id: UUID,
        revoked_by: UUID,
    ) -> "ComputeSelectiveGrant | None":
        """Revoke a selective grant.

        Args:
            grant_id: ID of the grant to revoke.
            revoked_by: User ID of the operator revoking the grant.

        Returns:
            The updated grant record, or None if not found.
        """
        from app.models.compute_availability import ComputeSelectiveGrant
        from sqlalchemy import select

        stmt = select(ComputeSelectiveGrant).where(
            ComputeSelectiveGrant.id == grant_id,
            ComputeSelectiveGrant.revoked_at.is_(None),
        )
        result = await self._db.execute(stmt)
        grant = result.scalar_one_or_none()

        if grant is None:
            return None

        grant.revoked_at = datetime.now(timezone.utc)
        grant.revoked_by = revoked_by
        await self._db.flush()

        # Invalidate cache
        invalidate_compute_cache()

        logger.info(
            "compute_selective_grant_revoked",
            grant_id=str(grant_id),
            grant_type=grant.grant_type,
            grant_target=grant.grant_target,
            revoked_by=str(revoked_by),
        )

        return grant

    async def list_active_grants(self) -> list:
        """List all active (non-revoked, non-expired) selective grants.

        Returns:
            List of active ComputeSelectiveGrant records.
        """
        from app.models.compute_availability import ComputeSelectiveGrant
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        stmt = select(ComputeSelectiveGrant).where(
            ComputeSelectiveGrant.revoked_at.is_(None),
            (ComputeSelectiveGrant.expires_at.is_(None))
            | (ComputeSelectiveGrant.expires_at > now),
        ).order_by(ComputeSelectiveGrant.created_at.desc())

        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    def is_platform_compute_available(self) -> bool:
        """Quick synchronous check if platform compute is available at all.

        Uses the cached state (or in-memory state for testing).
        Returns False only when DISABLED.
        Does NOT refresh the cache (for performance in hot paths).

        Returns:
            True for SELECTIVE and ENABLED, False for DISABLED.
        """
        if self._in_memory:
            return self._state != ComputeAvailabilityState.DISABLED
        return _cache.state != ComputeAvailabilityState.DISABLED
