"""Talent service — business logic for AI Talent CRUD, relationships, and LoRAs.

Orchestrates repository operations and enforces business rules:
    - Talent CRUD with soft-delete
    - Typed relationships between talents (unique per src/tgt/type)
    - LoRA association management (max 5 per talent)

Requirements: R10.1, R10.4, R10.5, R10.6, R10.7, R10.8
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.core.logging import get_logger
from app.db.tenant_scope import TenantScopedRepository
from app.models.talent import AiTalent
from app.models.talent_lora import TalentLora
from app.models.talent_relationship import TalentRelationship

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

MAX_LORAS_PER_TALENT = 5


class TalentService(TenantScopedRepository):
    """Service for managing AI Talent, relationships, and LoRA associations.

    All operations are scoped to the authenticated org_id.
    Cross-tenant access returns 404.

    Validates: R10.1, R10.4, R10.5, R10.6, R10.7, R10.8
    """

    def __init__(self, db: "AsyncSession", org_id: UUID) -> None:
        super().__init__(db, org_id)

    # =========================================================================
    # Talent CRUD
    # =========================================================================

    async def get_talent(self, talent_id: UUID) -> AiTalent:
        """Fetch a single talent by ID, scoped to authenticated org.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        return await self._get_one(AiTalent, talent_id, "Talent")

    async def list_talent(
        self,
        limit: int = 20,
        offset: int = 0,
        is_active: bool | None = None,
        talent_type: str | None = None,
    ) -> tuple[list[AiTalent], int]:
        """List talent for the authenticated org with optional filters."""
        stmt = select(AiTalent)

        if is_active is not None:
            stmt = stmt.where(AiTalent.is_active == is_active)
        if talent_type is not None:
            stmt = stmt.where(AiTalent.talent_type == talent_type)

        return await self._list(AiTalent, stmt, limit, offset)

    async def create_talent(
        self,
        name: str,
        description: str | None = None,
        talent_type: str | None = None,
        identity_classification: str | None = None,
        is_active: bool = True,
    ) -> AiTalent:
        """Create a new talent record for the authenticated org.

        org_id is set from the service's authenticated context.
        """
        talent = AiTalent(
            org_id=self._org_id,
            name=name,
            description=description,
            talent_type=talent_type,
            identity_classification=identity_classification,
            is_active=is_active,
        )
        self._db.add(talent)
        await self._db.flush()
        logger.info(
            "talent_created",
            talent_id=str(talent.id),
            org_id=str(self._org_id),
            identity_classification=identity_classification,
        )
        return talent

    async def update_talent(self, talent_id: UUID, **kwargs: object) -> AiTalent:
        """Update a talent record owned by the authenticated org.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        talent = await self.get_talent(talent_id)

        for key, value in kwargs.items():
            if hasattr(talent, key):
                setattr(talent, key, value)

        await self._db.flush()
        logger.info(
            "talent_updated",
            talent_id=str(talent_id),
            org_id=str(self._org_id),
            fields=list(kwargs.keys()),
        )
        return talent

    async def soft_delete_talent(self, talent_id: UUID) -> None:
        """Soft-delete a talent by setting deleted_at.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        from datetime import UTC, datetime

        from sqlalchemy import update

        # Verify ownership (raises 404 for cross-tenant)
        await self.get_talent(talent_id)

        stmt = (
            update(AiTalent)
            .where(AiTalent.id == talent_id, AiTalent.org_id == self._org_id)
            .values(deleted_at=datetime.now(UTC))
        )
        await self._db.execute(stmt)
        logger.info(
            "talent_soft_deleted",
            talent_id=str(talent_id),
            org_id=str(self._org_id),
        )

    # =========================================================================
    # Talent Relationships (R10.7)
    # =========================================================================

    async def create_relationship(
        self,
        source_talent_id: UUID,
        target_talent_id: UUID,
        relationship_type: str,
        metadata: dict | None = None,
    ) -> TalentRelationship:
        """Create a typed relationship between two talents.

        Validates that both source and target talent exist and belong
        to the authenticated org.

        Raises:
            HTTPException: 404 if either talent not found or cross-tenant.
            HTTPException: 409 if relationship already exists.
        """
        # Verify both talents exist and belong to this org
        await self.get_talent(source_talent_id)
        await self.get_talent(target_talent_id)

        # Check for duplicate
        existing = await self._db.execute(
            select(TalentRelationship).where(
                TalentRelationship.org_id == self._org_id,
                TalentRelationship.source_talent_id == source_talent_id,
                TalentRelationship.target_talent_id == target_talent_id,
                TalentRelationship.relationship_type == relationship_type,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Relationship '{relationship_type}' already exists "
                    f"between these talents"
                ),
            )

        relationship = TalentRelationship(
            org_id=self._org_id,
            source_talent_id=source_talent_id,
            target_talent_id=target_talent_id,
            relationship_type=relationship_type,
            metadata_=metadata,
        )
        self._db.add(relationship)
        await self._db.flush()
        logger.info(
            "talent_relationship_created",
            relationship_id=str(relationship.id),
            source_talent_id=str(source_talent_id),
            target_talent_id=str(target_talent_id),
            relationship_type=relationship_type,
            org_id=str(self._org_id),
        )
        return relationship

    async def list_relationships(
        self,
        talent_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[TalentRelationship], int]:
        """List relationships where talent_id is the source.

        Only returns relationships belonging to the authenticated org.
        """
        # Verify talent exists and belongs to org
        await self.get_talent(talent_id)

        stmt = select(TalentRelationship).where(
            TalentRelationship.source_talent_id == talent_id,
        )
        return await self._list(TalentRelationship, stmt, limit, offset)

    async def delete_relationship(self, talent_id: UUID, relationship_id: UUID) -> None:
        """Delete a specific talent relationship.

        Raises:
            HTTPException: 404 if relationship not found or cross-tenant.
        """
        # Verify source talent belongs to org
        await self.get_talent(talent_id)

        stmt = select(TalentRelationship).where(
            TalentRelationship.id == relationship_id,
            TalentRelationship.org_id == self._org_id,
            TalentRelationship.source_talent_id == talent_id,
        )
        result = await self._db.execute(stmt)
        relationship = result.scalar_one_or_none()

        if relationship is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Relationship not found",
            )

        await self._db.delete(relationship)
        await self._db.flush()
        logger.info(
            "talent_relationship_deleted",
            relationship_id=str(relationship_id),
            talent_id=str(talent_id),
            org_id=str(self._org_id),
        )

    # =========================================================================
    # Talent LoRA Associations (R10.8)
    # =========================================================================

    async def assign_lora(
        self,
        talent_id: UUID,
        lora_model_id: UUID,
        type: str = "identity",
        strength: float = 0.8,
        always_on: bool = False,
    ) -> TalentLora:
        """Associate a LoRA model with a talent.

        Enforces max 5 LoRAs per talent.

        Raises:
            HTTPException: 404 if talent not found or cross-tenant.
            HTTPException: 409 if this LoRA is already assigned.
            HTTPException: 422 if max LoRAs exceeded.
        """
        # Verify talent exists and belongs to org
        await self.get_talent(talent_id)

        # Check current count
        count_stmt = (
            select(func.count())
            .select_from(TalentLora)
            .where(
                TalentLora.org_id == self._org_id,
                TalentLora.talent_id == talent_id,
            )
        )
        current_count = await self._db.scalar(count_stmt) or 0

        if current_count >= MAX_LORAS_PER_TALENT:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Maximum {MAX_LORAS_PER_TALENT} LoRAs per talent exceeded. "
                    f"Remove an existing LoRA before adding a new one."
                ),
            )

        # Check for duplicate assignment
        existing = await self._db.execute(
            select(TalentLora).where(
                TalentLora.org_id == self._org_id,
                TalentLora.talent_id == talent_id,
                TalentLora.lora_model_id == lora_model_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This LoRA is already assigned to this talent",
            )

        lora_assoc = TalentLora(
            org_id=self._org_id,
            talent_id=talent_id,
            lora_model_id=lora_model_id,
            type=type,
            strength=strength,
            always_on=always_on,
        )
        self._db.add(lora_assoc)
        await self._db.flush()
        logger.info(
            "talent_lora_assigned",
            talent_lora_id=str(lora_assoc.id),
            talent_id=str(talent_id),
            lora_model_id=str(lora_model_id),
            type=type,
            strength=strength,
            always_on=always_on,
            org_id=str(self._org_id),
        )
        return lora_assoc

    async def list_loras(self, talent_id: UUID) -> tuple[list[TalentLora], int]:
        """List all LoRAs associated with a talent.

        Returns all (no pagination needed — max 5).
        """
        # Verify talent exists and belongs to org
        await self.get_talent(talent_id)

        stmt = select(TalentLora).where(
            TalentLora.org_id == self._org_id,
            TalentLora.talent_id == talent_id,
        )

        if hasattr(TalentLora, "created_at"):
            stmt = stmt.order_by(TalentLora.created_at.desc())

        result = await self._db.execute(stmt)
        items = list(result.scalars().all())
        return items, len(items)

    async def update_lora(
        self,
        talent_id: UUID,
        lora_id: UUID,
        **kwargs: object,
    ) -> TalentLora:
        """Update a LoRA association.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        await self.get_talent(talent_id)

        stmt = select(TalentLora).where(
            TalentLora.id == lora_id,
            TalentLora.org_id == self._org_id,
            TalentLora.talent_id == talent_id,
        )
        result = await self._db.execute(stmt)
        lora_assoc = result.scalar_one_or_none()

        if lora_assoc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="LoRA association not found",
            )

        for key, value in kwargs.items():
            if hasattr(lora_assoc, key):
                setattr(lora_assoc, key, value)

        await self._db.flush()
        return lora_assoc

    async def remove_lora(self, talent_id: UUID, lora_id: UUID) -> None:
        """Remove a LoRA association from a talent.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        await self.get_talent(talent_id)

        stmt = select(TalentLora).where(
            TalentLora.id == lora_id,
            TalentLora.org_id == self._org_id,
            TalentLora.talent_id == talent_id,
        )
        result = await self._db.execute(stmt)
        lora_assoc = result.scalar_one_or_none()

        if lora_assoc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="LoRA association not found",
            )

        await self._db.delete(lora_assoc)
        await self._db.flush()
        logger.info(
            "talent_lora_removed",
            lora_id=str(lora_id),
            talent_id=str(talent_id),
            org_id=str(self._org_id),
        )
