"""Publishing Approval Service — business logic for approval binding.

Implements immutable approval records that bind the exact state of a
publishing package at approval time. Any mutation to bound elements
invalidates the approval and requires re-evaluation.

Key behaviors:
    - Creates immutable approval records binding exact package state
    - Computes canonical hash of all bound elements for fast comparison
    - Detects changes to any bound element and invalidates approval
    - Verifies current state matches approved state at publish time
    - Returns clear error if approval is stale/invalidated

Requirements: R79.1, R79.2, R79.3, R79.4, R79.5, R79.6
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update

from app.core.logging import get_logger
from app.models.publishing_approved_package import PublishingApprovedPackage

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.dependencies import TenantContext

logger = get_logger(__name__)


def compute_package_hash(
    asset_checksum: str,
    caption: str,
    destination: dict,
    schedule: dict,
    targeting: dict,
    consent_state: list,
    disclosure_settings: dict,
    policy_state: dict,
) -> str:
    """Compute a canonical SHA-256 hash of all bound package elements.

    The hash is deterministic: identical inputs always produce the same hash.
    Used to detect any mutation to bound elements after approval.

    Args:
        asset_checksum: SHA-256 of the asset binary.
        caption: Post caption text.
        destination: Destination platform/account/type.
        schedule: Scheduling configuration.
        targeting: Audience targeting.
        consent_state: List of consent state snapshots.
        disclosure_settings: Disclosure/transparency settings.
        policy_state: Policy/governance state.

    Returns:
        64-character hex SHA-256 hash.
    """
    canonical_payload = {
        "asset_checksum": asset_checksum,
        "caption": caption,
        "destination": destination,
        "schedule": schedule,
        "targeting": targeting,
        "consent_state": consent_state,
        "disclosure_settings": disclosure_settings,
        "policy_state": policy_state,
    }
    canonical_json = json.dumps(canonical_payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class PublishingApprovalService:
    """Service for publishing approval binding management.

    Creates immutable approval records, detects changes, and verifies
    package integrity at publish time.

    Usage:
        service = PublishingApprovalService(db=session, tenant=tenant_context)
        approval = await service.create_approval(request_data)
        result = await service.verify_approval(approval_id, current_state)
    """

    def __init__(self, db: "AsyncSession", tenant: "TenantContext") -> None:
        """Initialize with a database session and tenant context.

        Args:
            db: SQLAlchemy async session.
            tenant: Authenticated TenantContext (never client-supplied).
        """
        self._db = db
        self._tenant = tenant

    async def create_approval(
        self,
        asset_id: UUID,
        asset_checksum: str,
        caption: str,
        destination: dict,
        schedule: dict,
        targeting: dict,
        consent_state: list,
        disclosure_settings: dict,
        policy_state: dict,
        talent_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> PublishingApprovedPackage:
        """Create an immutable publishing approval record.

        Binds the exact current state of all elements into an immutable
        record. Computes a canonical hash for fast equality checks at
        publish time.

        Also invalidates any previously valid approvals for the same
        asset in this org (only one valid approval per asset at a time).

        Args:
            asset_id: UUID of the asset being approved for publishing.
            asset_checksum: SHA-256 checksum of the asset binary.
            caption: Post caption text.
            destination: Platform/account/post_type configuration.
            schedule: Scheduling configuration.
            targeting: Audience targeting configuration.
            consent_state: Consent state for all referenced talent.
            disclosure_settings: Disclosure/transparency settings.
            policy_state: Policy/governance state.
            talent_id: Optional talent ID associated with the content.
            project_id: Optional project ID for the content.

        Returns:
            The created PublishingApprovedPackage.
        """
        # Compute canonical hash of all bound elements
        package_hash = compute_package_hash(
            asset_checksum=asset_checksum,
            caption=caption,
            destination=destination,
            schedule=schedule,
            targeting=targeting,
            consent_state=consent_state,
            disclosure_settings=disclosure_settings,
            policy_state=policy_state,
        )

        # Invalidate any existing valid approvals for this asset in this org
        await self._invalidate_existing_for_asset(
            asset_id=asset_id,
            reason="Superseded by new approval",
        )

        now = datetime.now(UTC)

        record = PublishingApprovedPackage(
            org_id=self._tenant.org_id,
            asset_id=asset_id,
            asset_checksum=asset_checksum,
            caption=caption,
            destination=destination,
            schedule=schedule,
            targeting=targeting,
            consent_state=consent_state,
            disclosure_settings=disclosure_settings,
            policy_state=policy_state,
            talent_id=talent_id,
            project_id=project_id,
            package_hash=package_hash,
            approved_by=self._tenant.user_id,
            approved_at=now,
            is_valid=True,
        )

        self._db.add(record)
        await self._db.flush()
        await self._db.refresh(record)

        logger.info(
            "publishing_approval_created",
            approval_id=str(record.id),
            org_id=str(self._tenant.org_id),
            asset_id=str(asset_id),
            package_hash=package_hash,
            approved_by=str(self._tenant.user_id),
        )

        return record

    async def get_approval(self, approval_id: UUID) -> PublishingApprovedPackage:
        """Get a publishing approval record by ID.

        Args:
            approval_id: The approval record UUID.

        Returns:
            The PublishingApprovedPackage.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        stmt = select(PublishingApprovedPackage).where(
            PublishingApprovedPackage.id == approval_id,
            PublishingApprovedPackage.org_id == self._tenant.org_id,
        )
        result = await self._db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Publishing approval not found",
            )

        return record

    async def verify_approval(
        self,
        approval_id: UUID,
        current_asset_checksum: str,
        current_caption: str,
        current_destination: dict,
        current_schedule: dict,
        current_targeting: dict,
        current_consent_state: list,
        current_disclosure_settings: dict,
        current_policy_state: dict,
    ) -> dict:
        """Verify an approval is still valid against current state.

        Compares the current state of all bound elements against the
        approved state. If any element has changed, the approval is
        invalidated and the mismatched fields are reported.

        Args:
            approval_id: The approval to verify.
            current_*: Current state of each bound element.

        Returns:
            Dict with is_valid, mismatched_fields, invalidation_reason,
            approved_at, and message.

        Raises:
            HTTPException: 404 if approval not found.
        """
        record = await self.get_approval(approval_id)

        # Already invalidated — return immediately
        if not record.is_valid:
            return {
                "approval_id": record.id,
                "is_valid": False,
                "mismatched_fields": [],
                "invalidation_reason": record.invalidation_reason,
                "approved_at": record.approved_at,
                "message": f"Approval was invalidated: {record.invalidation_reason}",
            }

        # Compute current hash and compare
        current_hash = compute_package_hash(
            asset_checksum=current_asset_checksum,
            caption=current_caption,
            destination=current_destination,
            schedule=current_schedule,
            targeting=current_targeting,
            consent_state=current_consent_state,
            disclosure_settings=current_disclosure_settings,
            policy_state=current_policy_state,
        )

        if current_hash == record.package_hash:
            return {
                "approval_id": record.id,
                "is_valid": True,
                "mismatched_fields": [],
                "invalidation_reason": None,
                "approved_at": record.approved_at,
                "message": "Approval is valid. Current state matches approved package.",
            }

        # Hash mismatch — determine which fields changed
        mismatched_fields = self._detect_mismatches(
            record=record,
            current_asset_checksum=current_asset_checksum,
            current_caption=current_caption,
            current_destination=current_destination,
            current_schedule=current_schedule,
            current_targeting=current_targeting,
            current_consent_state=current_consent_state,
            current_disclosure_settings=current_disclosure_settings,
            current_policy_state=current_policy_state,
        )

        # Invalidate the approval
        reason = f"Bound elements changed: {', '.join(mismatched_fields)}"
        await self._invalidate_record(record, reason)

        logger.warning(
            "publishing_approval_invalidated_on_verify",
            approval_id=str(approval_id),
            org_id=str(self._tenant.org_id),
            mismatched_fields=mismatched_fields,
        )

        return {
            "approval_id": record.id,
            "is_valid": False,
            "mismatched_fields": mismatched_fields,
            "invalidation_reason": reason,
            "approved_at": record.approved_at,
            "message": f"Approval invalidated. Changed: {', '.join(mismatched_fields)}. "
            "Re-approval required.",
        }

    async def invalidate_for_asset(
        self, asset_id: UUID, reason: str
    ) -> int:
        """Invalidate all valid approvals for an asset.

        Called when any bound element is externally mutated (e.g., asset
        re-uploaded, consent revoked, caption edited).

        Args:
            asset_id: The asset whose approvals should be invalidated.
            reason: Human-readable invalidation reason.

        Returns:
            Number of approvals invalidated.
        """
        return await self._invalidate_existing_for_asset(asset_id, reason)

    async def invalidate_for_talent(
        self, talent_id: UUID, reason: str
    ) -> int:
        """Invalidate all valid approvals referencing a talent.

        Called when consent state changes for a talent.

        Args:
            talent_id: The talent whose approvals should be invalidated.
            reason: Human-readable invalidation reason.

        Returns:
            Number of approvals invalidated.
        """
        now = datetime.now(UTC)
        stmt = (
            update(PublishingApprovedPackage)
            .where(
                PublishingApprovedPackage.org_id == self._tenant.org_id,
                PublishingApprovedPackage.talent_id == talent_id,
                PublishingApprovedPackage.is_valid.is_(True),
            )
            .values(
                is_valid=False,
                invalidated_at=now,
                invalidation_reason=reason,
            )
        )
        result = await self._db.execute(stmt)
        count = result.rowcount

        if count > 0:
            logger.info(
                "publishing_approvals_invalidated_for_talent",
                org_id=str(self._tenant.org_id),
                talent_id=str(talent_id),
                count=count,
                reason=reason,
            )

        return count

    # =========================================================================
    # Internal helpers
    # =========================================================================

    async def _invalidate_existing_for_asset(
        self, asset_id: UUID, reason: str
    ) -> int:
        """Invalidate all existing valid approvals for an asset in this org.

        Args:
            asset_id: The asset UUID.
            reason: Invalidation reason.

        Returns:
            Number of records invalidated.
        """
        now = datetime.now(UTC)
        stmt = (
            update(PublishingApprovedPackage)
            .where(
                PublishingApprovedPackage.org_id == self._tenant.org_id,
                PublishingApprovedPackage.asset_id == asset_id,
                PublishingApprovedPackage.is_valid.is_(True),
            )
            .values(
                is_valid=False,
                invalidated_at=now,
                invalidation_reason=reason,
            )
        )
        result = await self._db.execute(stmt)
        return result.rowcount

    async def _invalidate_record(
        self, record: PublishingApprovedPackage, reason: str
    ) -> None:
        """Invalidate a specific approval record.

        Args:
            record: The ORM record to invalidate.
            reason: Invalidation reason.
        """
        now = datetime.now(UTC)
        record.is_valid = False
        record.invalidated_at = now
        record.invalidation_reason = reason
        await self._db.flush()

    def _detect_mismatches(
        self,
        record: PublishingApprovedPackage,
        current_asset_checksum: str,
        current_caption: str,
        current_destination: dict,
        current_schedule: dict,
        current_targeting: dict,
        current_consent_state: list,
        current_disclosure_settings: dict,
        current_policy_state: dict,
    ) -> list[str]:
        """Detect which bound fields differ between approved and current state.

        Returns:
            List of field names that have changed.
        """
        mismatched: list[str] = []

        if record.asset_checksum != current_asset_checksum:
            mismatched.append("asset_checksum")

        if record.caption != current_caption:
            mismatched.append("caption")

        # Normalize JSON comparison (sort keys for stable comparison)
        if self._json_ne(record.destination, current_destination):
            mismatched.append("destination")

        if self._json_ne(record.schedule, current_schedule):
            mismatched.append("schedule")

        if self._json_ne(record.targeting, current_targeting):
            mismatched.append("targeting")

        if self._json_ne(record.consent_state, current_consent_state):
            mismatched.append("consent_state")

        if self._json_ne(record.disclosure_settings, current_disclosure_settings):
            mismatched.append("disclosure_settings")

        if self._json_ne(record.policy_state, current_policy_state):
            mismatched.append("policy_state")

        return mismatched

    @staticmethod
    def _json_ne(stored: dict | list, current: dict | list) -> bool:
        """Compare two JSON-serializable values for inequality.

        Uses canonical JSON encoding for stable comparison.
        """
        stored_str = json.dumps(stored, sort_keys=True, default=str)
        current_str = json.dumps(current, sort_keys=True, default=str)
        return stored_str != current_str
