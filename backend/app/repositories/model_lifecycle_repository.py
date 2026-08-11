"""Model lifecycle repository — tenant-scoped database access.

All queries are automatically filtered by org_id from TenantContext.
Cross-tenant access returns 404.

Requirements: R2.2, R2.6, R67.1, R67.6
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.db.tenant_scope import TenantScopedRepository
from app.models.model_lifecycle import ModelRegistryEntry, ModelTransition

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ModelLifecycleRepository(TenantScopedRepository):
    """Tenant-scoped repository for model lifecycle operations.

    All operations scoped to the authenticated org_id. Append-only
    transition log — transitions are never updated or deleted.

    Usage:
        repo = ModelLifecycleRepository(db=session, org_id=tenant.org_id)
        model = await repo.get_model(model_id)
        transition = await repo.record_transition(...)
    """

    def __init__(self, db: "AsyncSession", org_id: UUID) -> None:
        """Initialize with DB session and authenticated org_id."""
        super().__init__(db, org_id)

    async def get_model(self, model_id: UUID) -> ModelRegistryEntry:
        """Fetch a model registry entry by ID, scoped to tenant.

        Args:
            model_id: The model UUID.

        Returns:
            ModelRegistryEntry if found and owned by this tenant.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        return await self._get_one(ModelRegistryEntry, model_id, "Model")

    async def list_models(
        self,
        limit: int = 20,
        offset: int = 0,
        lifecycle_state: str | None = None,
        risk_class: str | None = None,
        model_type: str | None = None,
    ) -> tuple[list[ModelRegistryEntry], int]:
        """List model registry entries with optional filters.

        Args:
            limit: Maximum items per page (1-100).
            offset: Pagination offset.
            lifecycle_state: Optional filter by state.
            risk_class: Optional filter by risk class.
            model_type: Optional filter by model type.

        Returns:
            Tuple of (items, total_count).
        """
        stmt = select(ModelRegistryEntry)

        if lifecycle_state:
            stmt = stmt.where(
                ModelRegistryEntry.lifecycle_state == lifecycle_state
            )
        if risk_class:
            stmt = stmt.where(ModelRegistryEntry.risk_class == risk_class)
        if model_type:
            stmt = stmt.where(ModelRegistryEntry.model_type == model_type)

        return await self._list(ModelRegistryEntry, stmt, limit, offset)

    async def create_model(
        self,
        name: str,
        model_type: str,
        risk_class: str,
        initial_state: str,
        base_model_id: str | None = None,
        checksum_sha256: str | None = None,
        storage_key: str | None = None,
        file_size_bytes: int | None = None,
        metadata: dict | None = None,
    ) -> ModelRegistryEntry:
        """Create a new model registry entry.

        Args:
            name: Human-readable model name.
            model_type: Type (lora, checkpoint, embedding).
            risk_class: Risk classification.
            initial_state: Initial lifecycle state.
            base_model_id: Base model identifier.
            checksum_sha256: SHA-256 hash.
            storage_key: B2 storage key.
            file_size_bytes: File size.
            metadata: Additional metadata.

        Returns:
            The created ModelRegistryEntry.
        """
        entry = ModelRegistryEntry(
            org_id=self._org_id,
            name=name,
            model_type=model_type,
            lifecycle_state=initial_state,
            risk_class=risk_class,
            base_model_id=base_model_id,
            checksum_sha256=checksum_sha256,
            storage_key=storage_key,
            file_size_bytes=file_size_bytes,
            metadata_=metadata or {},
        )
        self._db.add(entry)
        await self._db.flush()
        await self._db.refresh(entry)
        return entry

    async def update_state(
        self,
        model_id: UUID,
        new_state: str,
        quarantine_reason: str | None = None,
        quarantined_at: datetime | None = None,
    ) -> ModelRegistryEntry:
        """Update the lifecycle state of a model.

        This is the ONLY place state is mutated. The service layer
        validates the transition before calling this.

        Args:
            model_id: Model to update.
            new_state: New lifecycle state.
            quarantine_reason: Reason if quarantining.
            quarantined_at: Timestamp if quarantining.

        Returns:
            The updated ModelRegistryEntry.
        """
        model = await self.get_model(model_id)
        model.lifecycle_state = new_state
        if quarantine_reason is not None:
            model.quarantine_reason = quarantine_reason
        if quarantined_at is not None:
            model.quarantined_at = quarantined_at
        await self._db.flush()
        await self._db.refresh(model)
        return model

    async def record_transition(
        self,
        model_id: UUID,
        from_state: str,
        to_state: str,
        actor: str,
        actor_type: str = "human",
        risk_class: str = "standard",
        evidence: dict | None = None,
        gate_checks_performed: list[str] | None = None,
        gate_checks_passed: list[str] | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> ModelTransition:
        """Record an immutable transition audit log entry.

        Args:
            model_id: The model being transitioned.
            from_state: State before transition.
            to_state: State after transition.
            actor: Identity performing the transition.
            actor_type: human or system.
            risk_class: Risk class at time of transition.
            evidence: Supporting evidence.
            gate_checks_performed: Checks that were run.
            gate_checks_passed: Checks that passed.
            success: Whether the transition succeeded.
            error_message: Error message if failed.

        Returns:
            The created ModelTransition record.
        """
        transition = ModelTransition(
            org_id=self._org_id,
            model_id=model_id,
            from_state=from_state,
            to_state=to_state,
            actor=actor,
            actor_type=actor_type,
            risk_class=risk_class,
            evidence=evidence or {},
            gate_checks_performed=gate_checks_performed or [],
            gate_checks_passed=gate_checks_passed or [],
            success=success,
            error_message=error_message,
        )
        self._db.add(transition)
        await self._db.flush()
        await self._db.refresh(transition)
        return transition

    async def list_transitions(
        self,
        model_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ModelTransition], int]:
        """List transition audit records, optionally filtered by model_id.

        Args:
            model_id: Optional filter by specific model.
            limit: Maximum items per page.
            offset: Pagination offset.

        Returns:
            Tuple of (items, total_count).
        """
        stmt = select(ModelTransition)

        if model_id:
            stmt = stmt.where(ModelTransition.model_id == model_id)

        return await self._list(ModelTransition, stmt, limit, offset)

    async def get_active_models_using(
        self, model_id: UUID
    ) -> list[ModelRegistryEntry]:
        """Get models currently in ACTIVE state (used by quarantine logic).

        This is a simplified version — in production this would also
        check active jobs referencing this model.

        Args:
            model_id: The model being quarantined.

        Returns:
            List matching the given model_id in ACTIVE state.
        """
        stmt = select(ModelRegistryEntry).where(
            ModelRegistryEntry.org_id == self._org_id,
            ModelRegistryEntry.id == model_id,
            ModelRegistryEntry.lifecycle_state == "active",
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
