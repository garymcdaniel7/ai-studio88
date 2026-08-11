"""Consent service — business logic for consent record management.

Consent is a first-class subsystem:
    - Versioned, scoped, revocable, auditable records
    - Provenance tracking
    - Enforcement through the Governance Boundary
    - Fictional talent exemption for generation consent
    - Scope-specific evaluation: only relevant scopes checked per operation type
    - Missing/expired/revoked consent → 403 CONSENT_REQUIRED or CONSENT_REVOKED

Requirements: R10.2, R10.3, R10.11, R10.12, 39.6, A2-004
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status

from app.core.logging import get_logger
from app.repositories.consent_repository import ConsentRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.dependencies import TenantContext

logger = get_logger(__name__)


# =============================================================================
# Scope-to-Operation Mapping (R10.3: scope-specific evaluation)
# =============================================================================

OPERATION_SCOPE_MAP: dict[str, list[str]] = {
    "generation": ["generation"],
    "image_generation": ["generation", "likeness"],
    "voice_generation": ["voice"],
    "training": ["training"],
    "lora_training": ["training"],
    "publishing": ["publishing"],
    "commercial_use": ["commercial"],
    "adult_content": ["adult_content"],
    "client_work": ["client_work"],
}
"""Maps operation types to required consent scopes.

Only the scopes relevant to a given operation type are checked.
For example, image generation checks 'generation' + 'likeness',
while voice generation checks only 'voice'.
"""

VALID_CONSENT_SCOPES: frozenset[str] = frozenset({
    "likeness",
    "voice",
    "training",
    "generation",
    "adult_content",
    "commercial",
    "publishing",
    "client_work",
})
"""Canonical set of valid consent scopes (lowercase per schema enum)."""


class ConsentService:
    """Service layer for consent record management.

    Handles business logic including:
        - Talent ownership validation
        - Version auto-increment
        - Revocation with audit preservation
        - Already-revoked guard
        - Fictional talent exemption (handled at enforcement, not creation)

    Usage:
        service = ConsentService(db=session, tenant=tenant_context)
        record = await service.create_consent(data)
    """

    def __init__(self, db: "AsyncSession", tenant: "TenantContext") -> None:
        """Initialize with a database session and tenant context.

        Args:
            db: SQLAlchemy async session.
            tenant: Authenticated TenantContext (never client-supplied).
        """
        self._db = db
        self._tenant = tenant
        self._repo = ConsentRepository(db=db, org_id=tenant.org_id)

    async def list_consent(
        self,
        limit: int = 20,
        offset: int = 0,
        talent_id: UUID | None = None,
        scope: str | None = None,
        active_only: bool = False,
    ) -> tuple[list, int]:
        """List consent records for the authenticated workspace.

        Args:
            limit: Maximum items per page (1-100).
            offset: Pagination offset.
            talent_id: Optional filter by talent.
            scope: Optional filter by scope.
            active_only: If True, exclude revoked/expired records.

        Returns:
            Tuple of (items, total_count).
        """
        return await self._repo.list_all(
            limit=limit,
            offset=offset,
            talent_id=talent_id,
            scope=scope,
            active_only=active_only,
        )

    async def get_consent(self, consent_id: UUID) -> object:
        """Get a single consent record by ID.

        Args:
            consent_id: The consent record UUID.

        Returns:
            The ConsentRecord if found and owned by this tenant.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        return await self._repo.get_by_id(consent_id)

    async def create_consent(
        self,
        talent_id: UUID,
        scopes: list[str],
        provenance: str,
        evidence_type: str | None = None,
        evidence_url: str | None = None,
        grantor_identity: str | None = None,
        granted_at: datetime | None = None,
        expires_at: datetime | None = None,
        restrictions: dict | None = None,
        verification_state: str = "unverified",
    ) -> object:
        """Create a new consent record.

        Auto-increments the version for this talent. Validates that
        the talent exists in this workspace before creating consent.

        Args:
            talent_id: The talent UUID this consent applies to.
            scopes: List of consent scope strings.
            provenance: How consent was obtained.
            evidence_type: Type of supporting evidence.
            evidence_url: URL to stored evidence.
            grantor_identity: Who granted consent.
            granted_at: When granted (defaults to now).
            expires_at: When consent expires (NULL = no expiry).
            restrictions: JSON conditions/limitations.
            verification_state: Verification status.

        Returns:
            The created ConsentRecord.

        Raises:
            HTTPException: 404 if talent not found in this workspace.
        """
        # Validate talent exists in this workspace
        await self._validate_talent_exists(talent_id)

        # Get next version for this talent
        version = await self._repo.get_next_version(talent_id)

        record = await self._repo.create(
            talent_id=talent_id,
            scopes=scopes,
            provenance=provenance,
            evidence_type=evidence_type,
            evidence_url=evidence_url,
            grantor_identity=grantor_identity,
            granted_at=granted_at or datetime.now(UTC),
            expires_at=expires_at,
            restrictions=restrictions or {},
            verification_state=verification_state,
            version=version,
        )

        logger.info(
            "consent_record_created",
            consent_id=str(record.id),
            org_id=str(self._tenant.org_id),
            talent_id=str(talent_id),
            scopes=scopes,
            provenance=provenance,
            version=version,
        )

        return record

    async def update_consent(
        self,
        consent_id: UUID,
        **kwargs: object,
    ) -> object:
        """Update mutable fields on a consent record.

        Core fields (talent_id, scopes, granted_at, provenance) are immutable.
        Only evidence, expiry, restrictions, and verification_state can change.

        Args:
            consent_id: The consent record UUID.
            **kwargs: Fields to update.

        Returns:
            The updated ConsentRecord.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
            HTTPException: 400 if record is already revoked.
        """
        record = await self._repo.get_by_id(consent_id)

        # Cannot update a revoked record
        if record.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update a revoked consent record",
                headers={"X-Error-Code": "CONSENT_REVOKED"},
            )

        # Filter out None values
        update_data = {k: v for k, v in kwargs.items() if v is not None}

        if not update_data:
            return record

        updated = await self._repo.update(consent_id, **update_data)

        logger.info(
            "consent_record_updated",
            consent_id=str(consent_id),
            org_id=str(self._tenant.org_id),
            updated_fields=list(update_data.keys()),
        )

        return updated

    async def revoke_consent(
        self, consent_id: UUID, revocation_reason: str
    ) -> object:
        """Revoke a consent record.

        Revocation prevents FUTURE use but does NOT falsify historical
        audit records. The record remains with revoked_at timestamp.

        Args:
            consent_id: The consent record UUID.
            revocation_reason: Reason for revocation.

        Returns:
            The revoked ConsentRecord.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
            HTTPException: 400 if already revoked.
        """
        record = await self._repo.get_by_id(consent_id)

        # Cannot revoke an already-revoked record
        if record.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Consent record is already revoked",
                headers={"X-Error-Code": "CONSENT_ALREADY_REVOKED"},
            )

        revoked = await self._repo.revoke(consent_id, revocation_reason)

        logger.info(
            "consent_record_revoked",
            consent_id=str(consent_id),
            org_id=str(self._tenant.org_id),
            talent_id=str(record.talent_id),
            reason=revocation_reason,
        )

        return revoked

    async def _validate_talent_exists(self, talent_id: UUID) -> None:
        """Validate that a talent exists in this workspace.

        Args:
            talent_id: The talent UUID to validate.

        Raises:
            HTTPException: 404 if talent not found in this workspace.
        """
        from app.repositories.talent_repository import TalentRepository

        talent_repo = TalentRepository(db=self._db, org_id=self._tenant.org_id)
        exists = await talent_repo.exists(talent_id)
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Talent not found",
            )

    # =========================================================================
    # Consent Enforcement (R10.2, R10.3, R10.11, R10.12, A2-004)
    # =========================================================================

    async def evaluate_consent(
        self,
        talent_id: UUID,
        operation: str,
        required_scopes: list[str] | None = None,
    ) -> bool:
        """Evaluate whether consent is sufficient for an operation.

        This is the primary enforcement method called by the Governance
        Boundary and generation pipeline. Scope-specific evaluation means
        only relevant scopes are checked per operation type.

        Fictional talent exemption: If the talent has identity_classification
        = 'FICTIONAL', consent is not required for generation operations.

        Args:
            talent_id: Talent being operated on.
            operation: Operation type (e.g., 'generation', 'training', 'publishing').
            required_scopes: Override scopes to check (if None, uses OPERATION_SCOPE_MAP).

        Returns:
            True if consent is sufficient.

        Raises:
            HTTPException: 403 with code CONSENT_REQUIRED if consent is missing.
            HTTPException: 403 with code CONSENT_REVOKED if consent was revoked.
            HTTPException: 404 if talent not found.
        """
        # Determine required scopes for this operation
        if required_scopes is None:
            scopes_needed = OPERATION_SCOPE_MAP.get(operation, [])
        else:
            scopes_needed = required_scopes

        if not scopes_needed:
            # No scopes required for this operation type
            return True

        # Check fictional talent exemption (R10.12, A2-004)
        is_fictional = await self._is_fictional_talent(talent_id)
        if is_fictional:
            logger.debug(
                "consent_fictional_exemption",
                talent_id=str(talent_id),
                org_id=str(self._tenant.org_id),
                operation=operation,
            )
            return True

        # Get active consent records for this talent
        active_records = await self._repo.get_active_for_talent(talent_id)

        # Collect all active scopes across all active records
        active_scopes: set[str] = set()
        for record in active_records:
            active_scopes.update(record.scopes)

        # Determine which required scopes are missing
        missing_scopes = [s for s in scopes_needed if s not in active_scopes]

        if not missing_scopes:
            # All required scopes covered by active consent
            return True

        # Check if missing scopes are specifically revoked
        revoked_scopes = await self._get_revoked_scopes(talent_id)
        revoked_missing = [s for s in missing_scopes if s in revoked_scopes]

        if revoked_missing:
            logger.warning(
                "consent_revoked_enforcement",
                talent_id=str(talent_id),
                org_id=str(self._tenant.org_id),
                operation=operation,
                revoked_scopes=revoked_missing,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Consent has been revoked for scopes: {revoked_missing}. "
                    f"Operation '{operation}' cannot proceed."
                ),
                headers={"X-Error-Code": "CONSENT_REVOKED"},
            )

        # Consent simply doesn't exist for these scopes
        logger.warning(
            "consent_required_enforcement",
            talent_id=str(talent_id),
            org_id=str(self._tenant.org_id),
            operation=operation,
            missing_scopes=missing_scopes,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Consent required for scopes: {missing_scopes}. "
                f"Operation '{operation}' cannot proceed without consent."
            ),
            headers={"X-Error-Code": "CONSENT_REQUIRED"},
        )

    async def get_active_scopes_for_talent(
        self,
        talent_id: UUID,
    ) -> set[str]:
        """Get all currently active consent scopes for a talent.

        Useful for UI display and capability checking.

        Args:
            talent_id: Talent to check.

        Returns:
            Set of active scope strings.
        """
        active_records = await self._repo.get_active_for_talent(talent_id)
        active_scopes: set[str] = set()
        for record in active_records:
            active_scopes.update(record.scopes)
        return active_scopes

    async def _is_fictional_talent(self, talent_id: UUID) -> bool:
        """Check if a talent has FICTIONAL identity classification.

        FICTIONAL talent does NOT require consent for generation operations
        (they are not real persons). Adult content still requires
        adult_status verification (handled by safety kernel, not consent).

        Args:
            talent_id: Talent ID to check.

        Returns:
            True if the talent is classified as FICTIONAL.

        Raises:
            HTTPException: 404 if talent not found in this workspace.
        """
        from app.repositories.talent_repository import TalentRepository

        talent_repo = TalentRepository(db=self._db, org_id=self._tenant.org_id)
        talent = await talent_repo.get_by_id(talent_id)
        return talent.identity_classification == "FICTIONAL"

    async def _get_revoked_scopes(self, talent_id: UUID) -> set[str]:
        """Get scopes that have been explicitly revoked for a talent.

        Used to distinguish between 'never had consent' and 'consent revoked'
        for proper error code selection.

        Args:
            talent_id: Talent to check.

        Returns:
            Set of revoked scope strings.
        """
        from sqlalchemy import select

        from app.models.consent import ConsentRecord

        stmt = select(ConsentRecord).where(
            ConsentRecord.org_id == self._tenant.org_id,
            ConsentRecord.talent_id == talent_id,
            ConsentRecord.revoked_at.is_not(None),
        )
        result = await self._db.execute(stmt)
        revoked_records = list(result.scalars().all())

        revoked_scopes: set[str] = set()
        for record in revoked_records:
            revoked_scopes.update(record.scopes)
        return revoked_scopes
