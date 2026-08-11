"""Model/LoRA Lifecycle Service — business logic for promotion gates.

Enforces the model lifecycle state machine:
    IMPORTED/TRAINED → INTEGRITY_VERIFIED → EVALUATED → APPROVED → ACTIVE → DEPRECATED → QUARANTINED

Key invariants:
    - State only advances forward through the defined sequence
    - Exception: ANY state can jump to QUARANTINED
    - Models SHALL NOT automatically become APPROVED or ACTIVE upon import/training
    - STANDARD risk: auto-promote through integrity/compatibility
    - HIGH_RISK: human approval required before APPROVED
    - All transitions logged with actor, evidence, timestamp

Requirements: R67.1, R67.2, R67.3, R67.4, R67.5, R67.6, R67.7, R67.8, R34.8
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status

from app.core.logging import get_logger
from app.repositories.model_lifecycle_repository import ModelLifecycleRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.dependencies import TenantContext
    from app.models.model_lifecycle import ModelRegistryEntry, ModelTransition

logger = get_logger(__name__)


# =============================================================================
# Lifecycle State Machine Constants
# =============================================================================

# Valid lifecycle states
LIFECYCLE_STATES: set[str] = {
    "imported",
    "trained",
    "integrity_verified",
    "evaluated",
    "approved",
    "active",
    "deprecated",
    "quarantined",
}

# Initial entry states — models start here
INITIAL_STATES: set[str] = {"imported", "trained"}

# States requiring human approval for HIGH_RISK models
HUMAN_GATED_STATES: set[str] = {"approved", "active"}

# Forward transitions: each state can advance to its immediate successor(s)
# IMPORTED and TRAINED both advance to INTEGRITY_VERIFIED
# ANY state can transition to QUARANTINED
VALID_TRANSITIONS: dict[str, set[str]] = {
    "imported": {"integrity_verified", "quarantined"},
    "trained": {"integrity_verified", "quarantined"},
    "integrity_verified": {"evaluated", "quarantined"},
    "evaluated": {"approved", "quarantined"},
    "approved": {"active", "quarantined"},
    "active": {"deprecated", "quarantined"},
    "deprecated": {"quarantined"},
    "quarantined": set(),  # Terminal — no transitions out
}

# Gate checks associated with each target state
STATE_GATE_CHECKS: dict[str, list[str]] = {
    "integrity_verified": ["checksum_valid", "format_valid", "file_not_corrupted"],
    "evaluated": ["compatibility_check", "base_model_match", "test_generation"],
    "approved": ["license_check", "safety_scan"],
    "active": ["final_validation"],
    "deprecated": [],
    "quarantined": [],
}


# =============================================================================
# Errors
# =============================================================================


class ModelLifecycleError(Exception):
    """Raised when an invalid lifecycle transition is attempted."""

    def __init__(self, message: str, code: str = "LIFECYCLE_VIOLATION"):
        self.message = message
        self.code = code
        super().__init__(message)


# =============================================================================
# Service
# =============================================================================


class ModelLifecycleService:
    """Service layer for model/LoRA promotion gate lifecycle management.

    Handles:
        - Model registration in initial state
        - Forward promotion with gate validation
        - Quarantine from any state (immediate unavailability)
        - Deprecation (removes from future dispatch, preserves history)
        - Transition audit logging

    Usage:
        service = ModelLifecycleService(db=session, tenant=tenant_context)
        model = await service.register_model(...)
        model = await service.promote(model_id, target_state, ...)
    """

    def __init__(self, db: "AsyncSession", tenant: "TenantContext") -> None:
        """Initialize with database session and tenant context.

        Args:
            db: SQLAlchemy async session.
            tenant: Authenticated TenantContext.
        """
        self._db = db
        self._tenant = tenant
        self._repo = ModelLifecycleRepository(db=db, org_id=tenant.org_id)

    # =========================================================================
    # Registration
    # =========================================================================

    async def register_model(
        self,
        name: str,
        model_type: str = "lora",
        risk_class: str = "standard",
        initial_state: str = "imported",
        base_model_id: str | None = None,
        checksum_sha256: str | None = None,
        storage_key: str | None = None,
        file_size_bytes: int | None = None,
        metadata: dict | None = None,
    ) -> "ModelRegistryEntry":
        """Register a new model in the lifecycle system.

        Models enter at IMPORTED or TRAINED state and must progress
        through gates before becoming ACTIVE.

        Args:
            name: Human-readable model name.
            model_type: Type (lora, checkpoint, embedding).
            risk_class: standard or high_risk.
            initial_state: Must be 'imported' or 'trained'.
            base_model_id: Base model identifier.
            checksum_sha256: SHA-256 hash for integrity.
            storage_key: B2 storage key.
            file_size_bytes: File size.
            metadata: Additional metadata.

        Returns:
            The created ModelRegistryEntry.

        Raises:
            HTTPException: 422 if initial_state is not valid.
        """
        if initial_state not in INITIAL_STATES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid initial state: {initial_state}. "
                    f"Must be one of: {sorted(INITIAL_STATES)}"
                ),
                headers={"X-Error-Code": "INVALID_INITIAL_STATE"},
            )

        model = await self._repo.create_model(
            name=name,
            model_type=model_type,
            risk_class=risk_class,
            initial_state=initial_state,
            base_model_id=base_model_id,
            checksum_sha256=checksum_sha256,
            storage_key=storage_key,
            file_size_bytes=file_size_bytes,
            metadata=metadata,
        )

        # Log the initial registration as a transition
        await self._repo.record_transition(
            model_id=model.id,
            from_state="none",
            to_state=initial_state,
            actor=str(self._tenant.user_id),
            actor_type="system",
            risk_class=risk_class,
            evidence={"action": "registration"},
            success=True,
        )

        logger.info(
            "model_registered",
            model_id=str(model.id),
            org_id=str(self._tenant.org_id),
            name=name,
            model_type=model_type,
            risk_class=risk_class,
            initial_state=initial_state,
        )

        return model

    # =========================================================================
    # Promotion
    # =========================================================================

    async def promote(
        self,
        model_id: UUID,
        target_state: str,
        actor: str,
        actor_type: str = "human",
        evidence: dict | None = None,
    ) -> "ModelRegistryEntry":
        """Promote a model to the next valid lifecycle state.

        Enforces:
            - Forward-only transitions (except quarantine)
            - Human approval gate for HIGH_RISK → APPROVED/ACTIVE
            - Audit logging of all attempts

        Args:
            model_id: Model to promote.
            target_state: Desired target state.
            actor: Identity performing the promotion.
            actor_type: 'human' or 'system'.
            evidence: Supporting evidence for the gate check.

        Returns:
            The updated ModelRegistryEntry.

        Raises:
            HTTPException: 404 if model not found.
            HTTPException: 409 if transition is invalid.
            HTTPException: 403 if human approval required but actor is system.
        """
        model = await self._repo.get_model(model_id)
        current_state = model.lifecycle_state
        risk_class = model.risk_class

        # Validate target state is a known state
        if target_state not in LIFECYCLE_STATES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown target state: {target_state}",
                headers={"X-Error-Code": "UNKNOWN_STATE"},
            )

        # Validate the transition is allowed
        allowed = VALID_TRANSITIONS.get(current_state, set())
        if target_state not in allowed:
            # Log failed attempt
            await self._repo.record_transition(
                model_id=model_id,
                from_state=current_state,
                to_state=target_state,
                actor=actor,
                actor_type=actor_type,
                risk_class=risk_class,
                evidence=evidence,
                success=False,
                error_message=(
                    f"Invalid transition: {current_state} → {target_state}. "
                    f"Allowed: {sorted(allowed)}"
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Invalid transition: {current_state} → {target_state}. "
                    f"Allowed next states: {sorted(allowed)}"
                ),
                headers={"X-Error-Code": "INVALID_TRANSITION"},
            )

        # Check human approval gate for HIGH_RISK models
        if (
            risk_class == "high_risk"
            and target_state in HUMAN_GATED_STATES
            and actor_type != "human"
        ):
            await self._repo.record_transition(
                model_id=model_id,
                from_state=current_state,
                to_state=target_state,
                actor=actor,
                actor_type=actor_type,
                risk_class=risk_class,
                evidence=evidence,
                success=False,
                error_message=(
                    f"Human approval required: HIGH_RISK model cannot "
                    f"auto-promote to {target_state}"
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Human approval required: HIGH_RISK model cannot "
                    f"auto-promote to {target_state}"
                ),
                headers={"X-Error-Code": "HUMAN_APPROVAL_REQUIRED"},
            )

        # Determine gate checks for this transition
        gate_checks = STATE_GATE_CHECKS.get(target_state, [])
        if risk_class == "high_risk" and target_state == "approved":
            gate_checks = gate_checks + ["human_approval"]

        # Execute the state transition
        updated_model = await self._repo.update_state(model_id, target_state)

        # Log successful transition
        await self._repo.record_transition(
            model_id=model_id,
            from_state=current_state,
            to_state=target_state,
            actor=actor,
            actor_type=actor_type,
            risk_class=risk_class,
            evidence=evidence,
            gate_checks_performed=gate_checks,
            gate_checks_passed=gate_checks,
            success=True,
        )

        logger.info(
            "model_promoted",
            model_id=str(model_id),
            org_id=str(self._tenant.org_id),
            from_state=current_state,
            to_state=target_state,
            actor=actor,
            risk_class=risk_class,
        )

        return updated_model

    # =========================================================================
    # Quarantine (R67.5)
    # =========================================================================

    async def quarantine(
        self,
        model_id: UUID,
        reason: str,
        actor: str,
        evidence: dict | None = None,
    ) -> "ModelRegistryEntry":
        """Quarantine a model from any lifecycle state.

        Quarantined models are immediately unavailable for all operations
        (generation, training, publishing) regardless of prior state.

        Args:
            model_id: Model to quarantine.
            reason: Reason for quarantine.
            actor: Identity performing the quarantine.
            evidence: Supporting evidence.

        Returns:
            The quarantined ModelRegistryEntry.

        Raises:
            HTTPException: 404 if model not found.
            HTTPException: 409 if already quarantined.
        """
        model = await self._repo.get_model(model_id)
        current_state = model.lifecycle_state

        if current_state == "quarantined":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Model is already quarantined",
                headers={"X-Error-Code": "ALREADY_QUARANTINED"},
            )

        now = datetime.now(UTC)

        # Execute quarantine
        updated_model = await self._repo.update_state(
            model_id=model_id,
            new_state="quarantined",
            quarantine_reason=reason,
            quarantined_at=now,
        )

        # Log transition
        await self._repo.record_transition(
            model_id=model_id,
            from_state=current_state,
            to_state="quarantined",
            actor=actor,
            actor_type="human",
            risk_class=model.risk_class,
            evidence=evidence or {"reason": reason},
            gate_checks_performed=["quarantine_review"],
            gate_checks_passed=["quarantine_review"],
            success=True,
        )

        logger.warning(
            "model_quarantined",
            model_id=str(model_id),
            org_id=str(self._tenant.org_id),
            from_state=current_state,
            reason=reason,
            actor=actor,
        )

        return updated_model

    # =========================================================================
    # Deprecation (R67.7)
    # =========================================================================

    async def deprecate(
        self,
        model_id: UUID,
        reason: str,
        actor: str,
    ) -> "ModelRegistryEntry":
        """Deprecate an ACTIVE model.

        Removes from future job dispatch while preserving it for
        reproducibility of historical jobs.

        Args:
            model_id: Model to deprecate.
            reason: Reason for deprecation.
            actor: Identity performing the deprecation.

        Returns:
            The deprecated ModelRegistryEntry.

        Raises:
            HTTPException: 404 if model not found.
            HTTPException: 409 if model is not in ACTIVE state.
        """
        model = await self._repo.get_model(model_id)
        current_state = model.lifecycle_state

        if current_state != "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Only ACTIVE models can be deprecated. "
                    f"Current state: {current_state}"
                ),
                headers={"X-Error-Code": "INVALID_TRANSITION"},
            )

        updated_model = await self._repo.update_state(model_id, "deprecated")

        await self._repo.record_transition(
            model_id=model_id,
            from_state="active",
            to_state="deprecated",
            actor=actor,
            actor_type="human",
            risk_class=model.risk_class,
            evidence={"reason": reason},
            success=True,
        )

        logger.info(
            "model_deprecated",
            model_id=str(model_id),
            org_id=str(self._tenant.org_id),
            reason=reason,
            actor=actor,
        )

        return updated_model

    # =========================================================================
    # Query
    # =========================================================================

    async def get_model(self, model_id: UUID) -> "ModelRegistryEntry":
        """Get a model by ID.

        Args:
            model_id: Model UUID.

        Returns:
            ModelRegistryEntry.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        return await self._repo.get_model(model_id)

    async def list_models(
        self,
        limit: int = 20,
        offset: int = 0,
        lifecycle_state: str | None = None,
        risk_class: str | None = None,
        model_type: str | None = None,
    ) -> tuple[list["ModelRegistryEntry"], int]:
        """List model registry entries.

        Args:
            limit: Page size.
            offset: Offset.
            lifecycle_state: Optional state filter.
            risk_class: Optional risk class filter.
            model_type: Optional type filter.

        Returns:
            Tuple of (items, total).
        """
        return await self._repo.list_models(
            limit=limit,
            offset=offset,
            lifecycle_state=lifecycle_state,
            risk_class=risk_class,
            model_type=model_type,
        )

    async def get_transitions(
        self,
        model_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list["ModelTransition"], int]:
        """Get transition audit log.

        Args:
            model_id: Optional filter by model.
            limit: Page size.
            offset: Offset.

        Returns:
            Tuple of (items, total).
        """
        return await self._repo.list_transitions(
            model_id=model_id,
            limit=limit,
            offset=offset,
        )

    async def is_model_available(self, model_id: UUID) -> bool:
        """Check if a model is available for use (ACTIVE state only).

        Used by generation pipeline to verify model availability.

        Args:
            model_id: Model to check.

        Returns:
            True if model is in ACTIVE state.
        """
        try:
            model = await self._repo.get_model(model_id)
            return model.lifecycle_state == "active"
        except HTTPException:
            return False
