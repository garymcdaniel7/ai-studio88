"""Brain Memory Promotion Service — private-to-workspace knowledge promotion.

Manages the explicit promotion workflow from user-private memory to
workspace-level knowledge. Key constraints:

    - Private memory NEVER auto-promotes (R93.5)
    - All promotions require explicit user action
    - Only editor+ roles can promote to workspace
    - Only owner/admin roles can delete workspace knowledge
    - Promotion records: promoted_by, promoted_from, timestamp (R29.12)
    - Users can inspect, correct, delete, disable any durable personalization (R94.2, R94.3)

Requirements covered: R29.12, R29.13, R93.5, R94.2, R94.3
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.brain_memory import BrainUserMemory, BrainWorkspaceKnowledge

logger = get_logger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class PromotionServiceError(Exception):
    """Base exception for MemoryPromotionService operations."""

    def __init__(self, message: str, code: str = "PROMOTION_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class MemoryNotFoundError(PromotionServiceError):
    """Raised when a memory item cannot be found for the given scope."""

    def __init__(self, memory_id: UUID) -> None:
        super().__init__(
            message=f"Memory {memory_id} not found",
            code="MEMORY_NOT_FOUND",
        )
        self.memory_id = memory_id


class KnowledgeNotFoundError(PromotionServiceError):
    """Raised when a workspace knowledge item cannot be found."""

    def __init__(self, knowledge_id: UUID) -> None:
        super().__init__(
            message=f"Workspace knowledge {knowledge_id} not found",
            code="KNOWLEDGE_NOT_FOUND",
        )
        self.knowledge_id = knowledge_id


class InsufficientRoleError(PromotionServiceError):
    """Raised when user lacks the required role for the operation."""

    def __init__(self, required: str, actual: str) -> None:
        super().__init__(
            message=f"Requires {required} role or above, user has '{actual}'",
            code="INSUFFICIENT_ROLE",
        )
        self.required = required
        self.actual = actual


class MemoryInactiveError(PromotionServiceError):
    """Raised when attempting to promote an inactive memory item."""

    def __init__(self, memory_id: UUID) -> None:
        super().__init__(
            message=f"Memory {memory_id} is inactive and cannot be promoted",
            code="MEMORY_INACTIVE",
        )
        self.memory_id = memory_id


# =============================================================================
# Role Hierarchy
# =============================================================================

ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 1,
    "editor": 2,
    "admin": 3,
    "owner": 4,
}
"""Maps workspace roles to numeric privilege levels (higher = more privilege)."""


def has_minimum_role(user_role: str, required_role: str) -> bool:
    """Check if user_role meets or exceeds the required role level.

    Args:
        user_role: The user's actual workspace role.
        required_role: The minimum required role.

    Returns:
        True if the user has sufficient privilege.
    """
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 99)
    return user_level >= required_level


# =============================================================================
# Memory Promotion Service
# =============================================================================


class MemoryPromotionService:
    """Manages private-to-workspace memory promotion workflow.

    All promotions are explicit (never automatic). The service enforces:
      - Tenant isolation (org_id on all queries)
      - User ownership validation (memory must belong to user+org)
      - Role-based access control (editor+ for promote, admin+ for delete knowledge)
      - Promotion metadata recording (promoted_by, promoted_from, timestamp)
      - Active memory validation (inactive items cannot be promoted)

    Requirements: R29.12, R29.13, R93.5, R94.2, R94.3
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an async database session.

        Args:
            db: SQLAlchemy async session (injected via Depends).
        """
        self.db = db

    async def promote_to_workspace(
        self,
        memory_id: UUID,
        org_id: UUID,
        user_id: UUID,
        role: str,
    ) -> BrainWorkspaceKnowledge:
        """Promote a private memory item to workspace knowledge.

        This is an EXPLICIT action (R93.5) — private memory never auto-promotes.
        Records promotion metadata: promoted_by, promoted_from, timestamp.

        Args:
            memory_id: The user memory item to promote.
            org_id: Organization scope (from JWT).
            user_id: User performing the promotion (from JWT).
            role: User's workspace role (must be editor+).

        Returns:
            The created BrainWorkspaceKnowledge record.

        Raises:
            InsufficientRoleError: If user lacks editor+ role.
            MemoryNotFoundError: If memory doesn't exist for this org/user.
            MemoryInactiveError: If the memory item is inactive.
        """
        # R94.3: Require editor+ role for promotion
        if not has_minimum_role(role, "editor"):
            raise InsufficientRoleError(required="editor", actual=role)

        # Fetch memory scoped to org + user
        stmt = select(BrainUserMemory).where(
            BrainUserMemory.id == memory_id,
            BrainUserMemory.org_id == org_id,
            BrainUserMemory.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        memory = result.scalar_one_or_none()

        if memory is None:
            raise MemoryNotFoundError(memory_id=memory_id)

        # Validate memory is active
        if not memory.is_active:
            raise MemoryInactiveError(memory_id=memory_id)

        # Create workspace knowledge record with promotion metadata
        knowledge = BrainWorkspaceKnowledge(
            org_id=org_id,
            knowledge_type=memory.memory_type,
            content=memory.content,
            provenance=memory.provenance,
            promoted_by=user_id,
            promoted_from=memory_id,
        )

        self.db.add(knowledge)
        await self.db.flush()

        logger.info(
            "memory_promoted_to_workspace",
            knowledge_id=str(knowledge.id),
            memory_id=str(memory_id),
            org_id=str(org_id),
            promoted_by=str(user_id),
        )

        return knowledge

    async def list_workspace_knowledge(
        self,
        org_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BrainWorkspaceKnowledge], int]:
        """List workspace knowledge items (paginated).

        All users in the workspace can view workspace knowledge.
        Items are ordered by creation time (newest first).

        Args:
            org_id: Organization scope (tenant isolation).
            limit: Maximum items to return (default 50).
            offset: Pagination offset (default 0).

        Returns:
            Tuple of (items, total_count).
        """
        # Count total
        count_stmt = (
            select(func.count())
            .select_from(BrainWorkspaceKnowledge)
            .where(BrainWorkspaceKnowledge.org_id == org_id)
        )
        total = await self.db.scalar(count_stmt) or 0

        # Fetch paginated items
        stmt = (
            select(BrainWorkspaceKnowledge)
            .where(BrainWorkspaceKnowledge.org_id == org_id)
            .order_by(BrainWorkspaceKnowledge.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def delete_workspace_knowledge(
        self,
        knowledge_id: UUID,
        org_id: UUID,
        user_id: UUID,
        role: str,
    ) -> None:
        """Delete a workspace knowledge item.

        Requires owner or admin role (R94.2: users can delete durable
        personalization).

        Args:
            knowledge_id: The workspace knowledge item to delete.
            org_id: Organization scope (from JWT).
            user_id: User performing the deletion (for audit).
            role: User's workspace role (must be admin+).

        Raises:
            InsufficientRoleError: If user lacks admin+ role.
            KnowledgeNotFoundError: If knowledge item doesn't exist for this org.
        """
        # Require admin+ role for deleting workspace knowledge
        if not has_minimum_role(role, "admin"):
            raise InsufficientRoleError(required="admin", actual=role)

        # Verify existence and org ownership
        stmt = select(BrainWorkspaceKnowledge).where(
            BrainWorkspaceKnowledge.id == knowledge_id,
            BrainWorkspaceKnowledge.org_id == org_id,
        )
        result = await self.db.execute(stmt)
        knowledge = result.scalar_one_or_none()

        if knowledge is None:
            raise KnowledgeNotFoundError(knowledge_id=knowledge_id)

        # Hard-delete the knowledge item
        delete_stmt = delete(BrainWorkspaceKnowledge).where(
            BrainWorkspaceKnowledge.id == knowledge_id,
            BrainWorkspaceKnowledge.org_id == org_id,
        )
        await self.db.execute(delete_stmt)
        await self.db.flush()

        logger.info(
            "workspace_knowledge_deleted",
            knowledge_id=str(knowledge_id),
            org_id=str(org_id),
            deleted_by=str(user_id),
        )
