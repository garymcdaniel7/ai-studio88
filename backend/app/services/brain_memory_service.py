"""Brain Memory Service — provenance-tracked memory lifecycle.

Manages per-user private memory with strict provenance hierarchy enforcement.
The provenance hierarchy ensures LLM output is NEVER silently promoted to
canonical truth:

    USER_CONFIRMED > OBSERVED > IMPORTED > INFERRED > SUGGESTED

INFERRED/SUGGESTED items explicitly indicate source and confidence when surfaced.

Requirements covered: R29.6, R29.7, R29.8, R29.11
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence
from uuid import UUID

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brain_memory import BrainUserMemory

logger = structlog.get_logger(__name__)


# =============================================================================
# Provenance Hierarchy
# =============================================================================

PROVENANCE_HIERARCHY: dict[str, int] = {
    "USER_CONFIRMED": 5,
    "OBSERVED": 4,
    "IMPORTED": 3,
    "INFERRED": 2,
    "SUGGESTED": 1,
}
"""Maps provenance levels to numeric priority (higher = more trusted).

Used for:
  - Context ordering: USER_CONFIRMED items surface first
  - Transition validation: provenance can only be upgraded, never downgraded
  - Conflict resolution: higher-provenance items take precedence
"""

VALID_PROVENANCES: frozenset[str] = frozenset(PROVENANCE_HIERARCHY.keys())


# =============================================================================
# Exceptions
# =============================================================================


class BrainMemoryServiceError(Exception):
    """Base exception for BrainMemoryService operations."""

    def __init__(self, message: str, code: str = "MEMORY_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class MemoryNotFoundError(BrainMemoryServiceError):
    """Raised when a memory item cannot be found for the given org/user scope."""

    def __init__(self, memory_id: UUID, org_id: UUID, user_id: UUID) -> None:
        super().__init__(
            message=f"Memory {memory_id} not found",
            code="MEMORY_NOT_FOUND",
        )
        self.memory_id = memory_id
        self.org_id = org_id
        self.user_id = user_id


class InvalidProvenanceError(BrainMemoryServiceError):
    """Raised when a provenance value is not in the valid set."""

    def __init__(self, provenance: str) -> None:
        super().__init__(
            message=(
                f"Invalid provenance '{provenance}'. "
                f"Valid values: {sorted(VALID_PROVENANCES)}"
            ),
            code="INVALID_PROVENANCE",
        )


class ProvenanceDowngradeError(BrainMemoryServiceError):
    """Raised when attempting to downgrade provenance (e.g. USER_CONFIRMED → INFERRED)."""

    def __init__(self, current: str, requested: str) -> None:
        super().__init__(
            message=(
                f"Cannot downgrade provenance from '{current}' to '{requested}'. "
                f"Provenance can only be upgraded."
            ),
            code="PROVENANCE_DOWNGRADE",
        )


class MissingConfidenceError(BrainMemoryServiceError):
    """Raised when INFERRED/SUGGESTED provenance is used without a confidence score."""

    def __init__(self, provenance: str) -> None:
        super().__init__(
            message=(
                f"Provenance '{provenance}' requires a confidence score (0.0-1.0). "
                f"INFERRED/SUGGESTED items must clearly indicate confidence."
            ),
            code="MISSING_CONFIDENCE",
        )


# =============================================================================
# Provenance Validation
# =============================================================================


def validate_provenance_transition(old: str, new: str) -> bool:
    """Validate that a provenance transition is an upgrade (not a downgrade).

    Returns True only if the new provenance is >= the old provenance in the
    hierarchy. Provenance can never be downgraded — this prevents LLM output
    from overwriting user-confirmed knowledge.

    Args:
        old: Current provenance level.
        new: Requested new provenance level.

    Returns:
        True if the transition is valid (upgrade or same level).

    Raises:
        InvalidProvenanceError: If either value is not a valid provenance.
    """
    if old not in VALID_PROVENANCES:
        raise InvalidProvenanceError(old)
    if new not in VALID_PROVENANCES:
        raise InvalidProvenanceError(new)

    return PROVENANCE_HIERARCHY[new] >= PROVENANCE_HIERARCHY[old]


# =============================================================================
# Brain Memory Service
# =============================================================================


class BrainMemoryService:
    """Per-user memory lifecycle management with provenance enforcement.

    All operations are tenant-isolated (org_id) and user-scoped (user_id).
    The service ensures:
      - Provenance is always valid and can only be upgraded
      - INFERRED/SUGGESTED items require confidence scores
      - LLM output is NEVER silently promoted to canonical truth
      - Active memory is returned sorted by provenance hierarchy for context injection

    Requirements covered: R29.6, R29.7, R29.8, R29.11
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an async database session.

        Args:
            db: SQLAlchemy async session (injected via Depends).
        """
        self.db = db

    async def create_memory(
        self,
        org_id: UUID,
        user_id: UUID,
        memory_type: str,
        content: dict,
        provenance: str,
        confidence: Decimal | float | None = None,
        source_conversation_id: UUID | None = None,
    ) -> BrainUserMemory:
        """Create a new user memory item with provenance tracking.

        INFERRED and SUGGESTED provenance levels require a confidence score
        to ensure these items are never presented as canonical truth.

        Args:
            org_id: Organization scope (tenant isolation).
            user_id: User who owns this memory.
            memory_type: Category (e.g., 'preference', 'pattern', 'correction').
            content: JSONB content of the memory item.
            provenance: Trust level (USER_CONFIRMED, OBSERVED, IMPORTED, INFERRED, SUGGESTED).
            confidence: Required for INFERRED/SUGGESTED (0.0-1.0).
            source_conversation_id: Optional conversation that generated this memory.

        Returns:
            The created BrainUserMemory record.

        Raises:
            InvalidProvenanceError: If provenance is not in the valid set.
            MissingConfidenceError: If INFERRED/SUGGESTED without confidence.
        """
        if provenance not in VALID_PROVENANCES:
            raise InvalidProvenanceError(provenance)

        # R29.8: INFERRED/SUGGESTED items must indicate confidence
        if provenance in ("INFERRED", "SUGGESTED") and confidence is None:
            raise MissingConfidenceError(provenance)

        # Convert float to Decimal if needed
        confidence_decimal: Decimal | None = None
        if confidence is not None:
            confidence_decimal = (
                Decimal(str(confidence))
                if not isinstance(confidence, Decimal)
                else confidence
            )

        memory = BrainUserMemory(
            org_id=org_id,
            user_id=user_id,
            memory_type=memory_type,
            content=content,
            provenance=provenance,
            confidence=confidence_decimal,
            is_active=True,
            source_conversation_id=source_conversation_id,
        )

        self.db.add(memory)
        await self.db.flush()

        logger.info(
            "brain_memory_created",
            memory_id=str(memory.id),
            org_id=str(org_id),
            user_id=str(user_id),
            memory_type=memory_type,
            provenance=provenance,
        )

        return memory

    async def get_memory(
        self,
        memory_id: UUID,
        org_id: UUID,
        user_id: UUID,
    ) -> BrainUserMemory:
        """Get a specific memory item, scoped to tenant + user.

        Returns 404 (not 403) for wrong org/user — prevents info leakage.

        Args:
            memory_id: The memory item to retrieve.
            org_id: Organization scope (from JWT).
            user_id: User scope (from JWT).

        Returns:
            The BrainUserMemory record.

        Raises:
            MemoryNotFoundError: If not found for this org/user.
        """
        stmt = select(BrainUserMemory).where(
            BrainUserMemory.id == memory_id,
            BrainUserMemory.org_id == org_id,
            BrainUserMemory.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        memory = result.scalar_one_or_none()

        if memory is None:
            raise MemoryNotFoundError(
                memory_id=memory_id, org_id=org_id, user_id=user_id
            )

        return memory

    async def list_user_memory(
        self,
        org_id: UUID,
        user_id: UUID,
        memory_type: str | None = None,
        active_only: bool = True,
        limit: int = 50,
    ) -> Sequence[BrainUserMemory]:
        """List memory items for a user with optional filtering.

        Always scoped to (org_id, user_id) for tenant + user isolation.

        Args:
            org_id: Organization scope.
            user_id: User whose memory to list.
            memory_type: Optional filter by type (e.g., 'preference').
            active_only: If True, only return is_active=True items.
            limit: Maximum items to return (default 50).

        Returns:
            Sequence of BrainUserMemory records.
        """
        stmt = select(BrainUserMemory).where(
            BrainUserMemory.org_id == org_id,
            BrainUserMemory.user_id == user_id,
        )

        if active_only:
            stmt = stmt.where(BrainUserMemory.is_active.is_(True))

        if memory_type is not None:
            stmt = stmt.where(BrainUserMemory.memory_type == memory_type)

        stmt = stmt.order_by(BrainUserMemory.created_at.desc()).limit(limit)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_memory(
        self,
        memory_id: UUID,
        org_id: UUID,
        user_id: UUID,
        content: dict | None = None,
        provenance: str | None = None,
        is_active: bool | None = None,
    ) -> BrainUserMemory:
        """Partially update a memory item.

        Provenance can only be upgraded (e.g., INFERRED → USER_CONFIRMED),
        never downgraded. This prevents LLM output from silently overwriting
        user-confirmed knowledge.

        Args:
            memory_id: The memory item to update.
            org_id: Organization scope (from JWT).
            user_id: User scope (from JWT).
            content: New content (optional).
            provenance: New provenance level (optional, upgrade only).
            is_active: New active state (optional).

        Returns:
            The updated BrainUserMemory record.

        Raises:
            MemoryNotFoundError: If not found for this org/user.
            InvalidProvenanceError: If provenance is not valid.
            ProvenanceDowngradeError: If attempting to downgrade provenance.
        """
        memory = await self.get_memory(memory_id, org_id, user_id)

        if provenance is not None:
            if provenance not in VALID_PROVENANCES:
                raise InvalidProvenanceError(provenance)
            if not validate_provenance_transition(memory.provenance, provenance):
                raise ProvenanceDowngradeError(
                    current=memory.provenance, requested=provenance
                )
            memory.provenance = provenance

        if content is not None:
            memory.content = content

        if is_active is not None:
            memory.is_active = is_active

        await self.db.flush()

        logger.info(
            "brain_memory_updated",
            memory_id=str(memory_id),
            org_id=str(org_id),
            user_id=str(user_id),
            provenance=memory.provenance,
        )

        return memory

    async def deactivate_memory(
        self,
        memory_id: UUID,
        org_id: UUID,
        user_id: UUID,
    ) -> BrainUserMemory:
        """Soft-disable a memory item (set is_active=False).

        The memory still exists but is no longer injected into Brain context.

        Args:
            memory_id: The memory item to deactivate.
            org_id: Organization scope.
            user_id: User scope.

        Returns:
            The deactivated BrainUserMemory record.

        Raises:
            MemoryNotFoundError: If not found for this org/user.
        """
        return await self.update_memory(
            memory_id=memory_id,
            org_id=org_id,
            user_id=user_id,
            is_active=False,
        )

    async def delete_memory(
        self,
        memory_id: UUID,
        org_id: UUID,
        user_id: UUID,
    ) -> None:
        """Hard-delete a memory item.

        Permanently removes the memory from the database.
        Use deactivate_memory() for reversible removal.

        Args:
            memory_id: The memory item to delete.
            org_id: Organization scope.
            user_id: User scope.

        Raises:
            MemoryNotFoundError: If not found for this org/user.
        """
        # Verify existence and ownership first
        await self.get_memory(memory_id, org_id, user_id)

        stmt = delete(BrainUserMemory).where(
            BrainUserMemory.id == memory_id,
            BrainUserMemory.org_id == org_id,
            BrainUserMemory.user_id == user_id,
        )
        await self.db.execute(stmt)
        await self.db.flush()

        logger.info(
            "brain_memory_deleted",
            memory_id=str(memory_id),
            org_id=str(org_id),
            user_id=str(user_id),
        )

    async def get_active_memory_for_context(
        self,
        org_id: UUID,
        user_id: UUID,
        limit: int = 20,
    ) -> Sequence[BrainUserMemory]:
        """Get active memory items sorted by provenance hierarchy for Brain context.

        Returns active memory items ordered by trust level (USER_CONFIRMED first,
        SUGGESTED last). This ordering ensures the Brain prioritizes
        user-confirmed knowledge over AI-inferred suggestions.

        INFERRED/SUGGESTED items will have their confidence score available
        for the context assembly pipeline to indicate source and certainty.

        Args:
            org_id: Organization scope.
            user_id: User whose memory to retrieve for context injection.
            limit: Maximum items to inject (default 20, per R25.15).

        Returns:
            Sequence of BrainUserMemory records, ordered by provenance priority
            (highest trust first).
        """
        stmt = select(BrainUserMemory).where(
            BrainUserMemory.org_id == org_id,
            BrainUserMemory.user_id == user_id,
            BrainUserMemory.is_active.is_(True),
        )

        # Order by provenance hierarchy using CASE expression
        # USER_CONFIRMED=5 (first), SUGGESTED=1 (last)
        from sqlalchemy import case

        provenance_order = case(
            (BrainUserMemory.provenance == "USER_CONFIRMED", 1),
            (BrainUserMemory.provenance == "OBSERVED", 2),
            (BrainUserMemory.provenance == "IMPORTED", 3),
            (BrainUserMemory.provenance == "INFERRED", 4),
            (BrainUserMemory.provenance == "SUGGESTED", 5),
            else_=6,
        )

        stmt = stmt.order_by(provenance_order, BrainUserMemory.created_at.desc())
        stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        return result.scalars().all()
