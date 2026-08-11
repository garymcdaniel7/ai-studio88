"""Workspace Autonomy Profile Service.

Manages per-workspace agent autonomy levels that determine how much
autonomous authority Brain/Hermes has:

- ADVISORY: Recommend only — no mutations without explicit user instruction.
- ASSISTED: Low-risk auto-execute (reads, knowledge retrieval).
- AUTONOMOUS_WITHIN_LIMITS: Delegated actions within configured limits.

Default is ADVISORY for new workspaces. Mandatory safety, security,
consent, budget, and destructive-action controls are enforced REGARDLESS
of the active autonomy profile — autonomy profiles control convenience
delegation, not security bypass.

Validates: Requirements R98.1, R98.2, R30.12, R30.13
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


class AutonomyLevel(str, Enum):
    """Workspace-level agent autonomy setting.

    ADVISORY: Recommend only — no mutations without explicit user instruction.
    ASSISTED: Low-risk actions auto-execute, high-risk require confirmation.
    AUTONOMOUS_WITHIN_LIMITS: Delegated actions execute within configured
        limits without per-action confirmation.
    """

    ADVISORY = "advisory"
    ASSISTED = "assisted"
    AUTONOMOUS_WITHIN_LIMITS = "autonomous_within_limits"


# =============================================================================
# Action Risk Classification
# =============================================================================


class ActionRisk(str, Enum):
    """Risk classification for actions evaluated against autonomy profiles."""

    READ = "read"
    LOW_RISK_MUTATE = "low_risk_mutate"
    HIGH_RISK_MUTATE = "high_risk_mutate"
    DESTRUCTIVE = "destructive"


# =============================================================================
# Dataclasses
# =============================================================================


# Mandatory controls that cannot be overridden by autonomy profile
MANDATORY_CONTROLS = {
    "safety_kernel": True,
    "security_sensitive": True,
    "consent_verification": True,
    "budget_exceeding": True,
    "destructive_operations": True,
}

# Actions that always require explicit user approval regardless of profile
MANDATORY_APPROVAL_ACTIONS = frozenset({
    "delete_permanent",
    "force_delete",
    "publish_to_social",
    "clone_voice",
    "spend_above_threshold",
    "launch_fleet",
    "revoke_credential",
    "modify_safety_policy",
    "modify_consent",
    "access_escalation",
})


@dataclass(frozen=True)
class AutonomyProfile:
    """Per-workspace autonomy configuration.

    Attributes:
        org_id: The workspace (organisation) this profile belongs to.
        autonomy_level: Current autonomy level for the workspace.
        mandatory_controls: Controls enforced regardless of autonomy level.
    """

    org_id: UUID
    autonomy_level: AutonomyLevel = AutonomyLevel.ADVISORY
    mandatory_controls: dict = field(default_factory=lambda: dict(MANDATORY_CONTROLS))


@dataclass(frozen=True)
class ActionEvaluation:
    """Result of evaluating an action against the autonomy profile.

    Attributes:
        allowed: Whether the action can auto-execute without user approval.
        reason: Human-readable explanation of the decision.
        requires_approval: Whether explicit user approval is required.
        mandatory_control_triggered: Which mandatory control blocked it (if any).
    """

    allowed: bool
    reason: str
    requires_approval: bool = False
    mandatory_control_triggered: str | None = None


# =============================================================================
# Service
# =============================================================================


class AutonomyProfileService:
    """Manages workspace autonomy profiles and evaluates action permissions.

    This service provides:
    1. CRUD for autonomy profile (get/set per workspace)
    2. Action evaluation against the active autonomy profile
    3. Mandatory control enforcement (never bypassed)

    Constructor modes:
    - AutonomyProfileService(db=session) — production, DB-backed
    - AutonomyProfileService(profile=...) — testing, in-memory

    Validates: Requirements R98.1, R98.2, R30.12, R30.13
    """

    def __init__(
        self,
        db: "AsyncSession | None" = None,
        profile: AutonomyProfile | None = None,
    ) -> None:
        self._db = db
        # In-memory mode for testing
        if profile is not None:
            self._in_memory = True
            self._profile = profile
        else:
            self._in_memory = False
            self._profile = None

    # =========================================================================
    # Profile Management
    # =========================================================================

    async def get_profile(self, org_id: UUID) -> AutonomyProfile:
        """Retrieve the autonomy profile for a workspace.

        Returns default profile (ADVISORY) if none has been configured.

        Args:
            org_id: The workspace to retrieve the profile for.

        Returns:
            AutonomyProfile for the workspace.
        """
        if self._in_memory:
            return self._profile or AutonomyProfile(org_id=org_id)

        if self._db is None:
            return AutonomyProfile(org_id=org_id)

        from sqlalchemy import select

        from app.models.workspace_autonomy import WorkspaceAutonomyProfileModel

        stmt = select(WorkspaceAutonomyProfileModel).where(
            WorkspaceAutonomyProfileModel.org_id == org_id,
        )
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            return AutonomyProfile(org_id=org_id)

        return AutonomyProfile(
            org_id=row.org_id,
            autonomy_level=AutonomyLevel(row.autonomy_level),
            mandatory_controls=row.mandatory_controls or dict(MANDATORY_CONTROLS),
        )

    async def set_profile(
        self,
        org_id: UUID,
        autonomy_level: AutonomyLevel,
        updated_by: UUID,
    ) -> AutonomyProfile:
        """Create or update the autonomy profile for a workspace.

        This is an upsert operation. Mandatory controls are always
        preserved — they cannot be disabled through this method.

        Args:
            org_id: The workspace to configure.
            autonomy_level: The desired autonomy level.
            updated_by: User ID making the change (for audit).

        Returns:
            The updated AutonomyProfile.
        """
        if self._in_memory:
            self._profile = AutonomyProfile(
                org_id=org_id,
                autonomy_level=autonomy_level,
                mandatory_controls=dict(MANDATORY_CONTROLS),
            )
            return self._profile

        if self._db is None:
            raise RuntimeError("No database session available")

        from sqlalchemy import select

        from app.models.workspace_autonomy import WorkspaceAutonomyProfileModel

        stmt = select(WorkspaceAutonomyProfileModel).where(
            WorkspaceAutonomyProfileModel.org_id == org_id,
        )
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            row = WorkspaceAutonomyProfileModel(
                org_id=org_id,
                autonomy_level=autonomy_level.value,
                mandatory_controls=dict(MANDATORY_CONTROLS),
                last_updated_by=updated_by,
            )
            self._db.add(row)
        else:
            row.autonomy_level = autonomy_level.value
            row.mandatory_controls = dict(MANDATORY_CONTROLS)
            row.last_updated_by = updated_by

        await self._db.flush()

        logger.info(
            "workspace_autonomy_profile_updated",
            org_id=str(org_id),
            autonomy_level=autonomy_level.value,
            updated_by=str(updated_by),
        )

        return AutonomyProfile(
            org_id=org_id,
            autonomy_level=autonomy_level,
            mandatory_controls=dict(MANDATORY_CONTROLS),
        )

    # =========================================================================
    # Action Evaluation
    # =========================================================================

    def evaluate_action(
        self,
        profile: AutonomyProfile,
        action: str,
        risk: ActionRisk = ActionRisk.LOW_RISK_MUTATE,
    ) -> ActionEvaluation:
        """Determine if an action can auto-execute given the autonomy profile.

        Mandatory controls are checked FIRST — if a mandatory control applies,
        the action always requires approval regardless of autonomy level.

        Then the autonomy level determines behavior for non-mandatory actions:
        - ADVISORY: All mutations require explicit user approval.
        - ASSISTED: Read and low-risk mutations auto-execute; high-risk require approval.
        - AUTONOMOUS_WITHIN_LIMITS: All non-mandatory actions auto-execute.

        Args:
            profile: The workspace's current autonomy profile.
            action: The action identifier being evaluated.
            risk: The risk classification of the action.

        Returns:
            ActionEvaluation indicating whether auto-execution is permitted.
        """
        # ─── Mandatory controls always enforced (R30.13) ───────────────────
        if action in MANDATORY_APPROVAL_ACTIONS:
            return ActionEvaluation(
                allowed=False,
                reason=f"Action '{action}' requires mandatory approval (safety/security/consent/budget/destructive control)",
                requires_approval=True,
                mandatory_control_triggered="mandatory_approval_action",
            )

        if risk == ActionRisk.DESTRUCTIVE:
            return ActionEvaluation(
                allowed=False,
                reason="Destructive operations always require explicit approval",
                requires_approval=True,
                mandatory_control_triggered="destructive_operations",
            )

        # ─── Autonomy level evaluation ────────────────────────────────────
        if profile.autonomy_level == AutonomyLevel.ADVISORY:
            # ADVISORY: only read operations auto-execute
            if risk == ActionRisk.READ:
                return ActionEvaluation(
                    allowed=True,
                    reason="Read operations allowed in ADVISORY mode",
                )
            return ActionEvaluation(
                allowed=False,
                reason=f"ADVISORY mode: action '{action}' requires explicit user instruction",
                requires_approval=True,
            )

        if profile.autonomy_level == AutonomyLevel.ASSISTED:
            # ASSISTED: read + low-risk auto-execute
            if risk in (ActionRisk.READ, ActionRisk.LOW_RISK_MUTATE):
                return ActionEvaluation(
                    allowed=True,
                    reason=f"ASSISTED mode: {risk.value} action auto-executed",
                )
            return ActionEvaluation(
                allowed=False,
                reason=f"ASSISTED mode: high-risk action '{action}' requires confirmation",
                requires_approval=True,
            )

        if profile.autonomy_level == AutonomyLevel.AUTONOMOUS_WITHIN_LIMITS:
            # AUTONOMOUS_WITHIN_LIMITS: all non-mandatory auto-execute
            return ActionEvaluation(
                allowed=True,
                reason=f"AUTONOMOUS_WITHIN_LIMITS mode: action '{action}' auto-executed within delegated limits",
            )

        # Fallback — should not reach here, default to requiring approval
        return ActionEvaluation(
            allowed=False,
            reason="Unknown autonomy level — defaulting to require approval",
            requires_approval=True,
        )
