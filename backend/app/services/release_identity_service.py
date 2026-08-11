"""Release Identity Service — immutable deployment record management.

Manages the lifecycle of Release Identity records: creation during
deployment, retrieval of the current active release, completeness
validation, and release comparison.

Key design constraints:
    - Platform-level (no org_id scoping — release identities are global)
    - Immutable: once created, records are NEVER updated or deleted
    - Only one record may be active (is_current=True) at any time
    - Deployments that cannot produce a complete Release_Identity are rejected
    - Surfaced in /ready, structured logs, job records, error reports

Validates: Requirements R72.1, R72.2, R72.3, R72.4, R72.5, R72.6
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import false, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.release_identity import ReleaseIdentity
from app.schemas.release_identity import ReleaseIdentityCreate

logger = get_logger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class ReleaseIdentityError(Exception):
    """Base exception for ReleaseIdentityService operations."""

    def __init__(self, message: str, code: str = "RELEASE_IDENTITY_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class IncompleteReleaseError(ReleaseIdentityError):
    """Raised when a release cannot produce a complete Release_Identity.

    Per R72.5: missing commit SHA, unsigned artifacts, or untracked
    migrations block production deployment.
    """

    def __init__(self, missing_fields: list[str]) -> None:
        super().__init__(
            message=(
                f"Cannot create Release Identity — required fields missing: "
                f"{', '.join(missing_fields)}. Deployment blocked per R72.5."
            ),
            code="INCOMPLETE_RELEASE_IDENTITY",
        )
        self.missing_fields = missing_fields


class ReleaseNotFoundError(ReleaseIdentityError):
    """Raised when a release identity record is not found."""

    def __init__(self, identifier: str) -> None:
        super().__init__(
            message=f"Release identity not found: {identifier}",
            code="RELEASE_NOT_FOUND",
        )


# =============================================================================
# Service
# =============================================================================


class ReleaseIdentityService:
    """Service for managing immutable Release Identity records.

    All creation methods validate completeness before persisting.
    The service does NOT perform authentication — callers must verify
    the requesting user has deployment/release_management capabilities.

    Args:
        db: SQLAlchemy async session.

    Validates: R72.1, R72.2, R72.3, R72.4, R72.5, R72.6
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # =========================================================================
    # Create
    # =========================================================================

    async def create_release(
        self,
        data: ReleaseIdentityCreate,
    ) -> ReleaseIdentity:
        """Create an immutable Release Identity record.

        Validates completeness (R72.5), deactivates any previous current
        release, and persists the new record as the active release.

        The record is immutable once created — never modified after this point.

        Args:
            data: Validated release identity creation data.

        Returns:
            The created ReleaseIdentity record.

        Raises:
            IncompleteReleaseError: If required fields are missing (R72.5).
        """
        # Validate completeness before creating
        self.validate_completeness(data)

        # Deactivate any currently active release
        await self._deactivate_current()

        # Create immutable record
        release = ReleaseIdentity(
            git_commit_sha=data.git_commit_sha,
            frontend_artifact=data.frontend_artifact,
            backend_artifact=data.backend_artifact,
            migration_set=data.migration_set,
            config_version=data.config_version,
            model_manifest=data.model_manifest,
            deployment_ids=data.deployment_ids,
            is_current=True,
            created_by=data.created_by,
        )
        self._db.add(release)
        await self._db.flush()

        logger.info(
            "release_identity_created",
            release_id=str(release.id),
            git_commit_sha=release.git_commit_sha[:7],
            frontend_artifact=release.frontend_artifact,
            backend_artifact=release.backend_artifact,
            migration_set=release.migration_set[:50],
            created_by=release.created_by,
        )

        return release

    # =========================================================================
    # Query
    # =========================================================================

    async def get_current(self) -> ReleaseIdentity | None:
        """Get the currently active Release Identity.

        Returns None if no release has been deployed yet (e.g., in
        local development without a deployment pipeline).

        Returns:
            The current ReleaseIdentity or None.
        """
        stmt = select(ReleaseIdentity).where(
            ReleaseIdentity.is_current.is_(True),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, release_id: UUID) -> ReleaseIdentity | None:
        """Get a Release Identity by its primary key.

        Args:
            release_id: The UUID of the release identity.

        Returns:
            The ReleaseIdentity or None if not found.
        """
        stmt = select(ReleaseIdentity).where(ReleaseIdentity.id == release_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_commit(self, commit_sha: str) -> ReleaseIdentity | None:
        """Get a Release Identity by git commit SHA.

        Supports both full (40-char) and short (7+ char) SHA lookups.

        Args:
            commit_sha: Full or partial git commit SHA.

        Returns:
            The ReleaseIdentity or None if not found.
        """
        if len(commit_sha) == 40:
            stmt = select(ReleaseIdentity).where(
                ReleaseIdentity.git_commit_sha == commit_sha,
            )
        else:
            stmt = select(ReleaseIdentity).where(
                ReleaseIdentity.git_commit_sha.startswith(commit_sha),
            )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_releases(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ReleaseIdentity], int]:
        """List Release Identity records with pagination.

        Ordered by creation time descending (most recent first).

        Args:
            limit: Max items to return (1-100).
            offset: Pagination offset.

        Returns:
            Tuple of (release list, total count).
        """
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        count_stmt = select(func.count()).select_from(ReleaseIdentity)
        total = await self._db.scalar(count_stmt) or 0

        stmt = (
            select(ReleaseIdentity)
            .order_by(ReleaseIdentity.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # =========================================================================
    # Validation
    # =========================================================================

    @staticmethod
    def validate_completeness(data: ReleaseIdentityCreate) -> None:
        """Validate that all required fields are present for a complete Release_Identity.

        Per R72.5: missing commit SHA, unsigned artifacts, or untracked
        migrations SHALL block production deployment.

        Args:
            data: The release identity data to validate.

        Raises:
            IncompleteReleaseError: If any required field is empty/missing.
        """
        required_fields = {
            "git_commit_sha": data.git_commit_sha,
            "frontend_artifact": data.frontend_artifact,
            "backend_artifact": data.backend_artifact,
            "migration_set": data.migration_set,
        }

        missing = [
            field_name
            for field_name, value in required_fields.items()
            if not value or not value.strip()
        ]

        if missing:
            raise IncompleteReleaseError(missing)

    # =========================================================================
    # Comparison (R72.6)
    # =========================================================================

    async def compare_releases(
        self,
        from_id: UUID,
        to_id: UUID,
    ) -> dict:
        """Compare two releases and show what changed.

        Per R72.6: given two releases, show what changed (commits,
        migrations, config, models).

        Args:
            from_id: The earlier release UUID.
            to_id: The later release UUID.

        Returns:
            Dict with both release records and a changes summary.

        Raises:
            ReleaseNotFoundError: If either release is not found.
        """
        from_release = await self.get_by_id(from_id)
        if from_release is None:
            raise ReleaseNotFoundError(str(from_id))

        to_release = await self.get_by_id(to_id)
        if to_release is None:
            raise ReleaseNotFoundError(str(to_id))

        changes: dict = {}

        if from_release.git_commit_sha != to_release.git_commit_sha:
            changes["git_commit_sha"] = {
                "from": from_release.git_commit_sha[:7],
                "to": to_release.git_commit_sha[:7],
            }

        if from_release.frontend_artifact != to_release.frontend_artifact:
            changes["frontend_artifact"] = {
                "from": from_release.frontend_artifact,
                "to": to_release.frontend_artifact,
            }

        if from_release.backend_artifact != to_release.backend_artifact:
            changes["backend_artifact"] = {
                "from": from_release.backend_artifact,
                "to": to_release.backend_artifact,
            }

        if from_release.migration_set != to_release.migration_set:
            changes["migration_set"] = {
                "from": from_release.migration_set,
                "to": to_release.migration_set,
            }

        if from_release.config_version != to_release.config_version:
            changes["config_version"] = {
                "from": from_release.config_version,
                "to": to_release.config_version,
            }

        if from_release.model_manifest != to_release.model_manifest:
            changes["model_manifest"] = {
                "from": from_release.model_manifest,
                "to": to_release.model_manifest,
            }

        if from_release.deployment_ids != to_release.deployment_ids:
            changes["deployment_ids"] = {
                "from": from_release.deployment_ids,
                "to": to_release.deployment_ids,
            }

        return {
            "from_release_id": str(from_id),
            "to_release_id": str(to_id),
            "changes": changes,
            "total_changes": len(changes),
        }

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    async def _deactivate_current(self) -> None:
        """Deactivate the currently active release (set is_current=False).

        This ensures only one release is active at any time.
        """
        stmt = (
            update(ReleaseIdentity)
            .where(ReleaseIdentity.is_current.is_(True))
            .values(is_current=False)
        )
        await self._db.execute(stmt)
