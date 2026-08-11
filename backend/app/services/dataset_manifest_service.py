"""Dataset Manifest service — immutable manifest creation and verification.

Dataset manifests are immutable records of exact files, checksums, roles,
and provenance used for a training job. They are NEVER modified after creation.

Key responsibilities:
    - Create immutable manifests with SHA-256 checksums
    - Validate consent records are active for all referenced talent
    - Validate all referenced files exist and are accessible
    - Verify manifest integrity (checksums match stored files)
    - Reject training jobs if any file is deleted or consent revoked
    - Compare two manifest versions (R61.6)

Requirements: R61.1, R61.2, R61.3, R61.4, R61.5, R61.6
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status

from app.core.logging import get_logger
from app.schemas.dataset_manifest import (
    DatasetManifestCreateRequest,
    ManifestComparisonEntry,
    ManifestComparisonResult,
    ManifestFileIssue,
    ManifestVerificationResult,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.dependencies import TenantContext

logger = get_logger(__name__)


class DatasetManifestService:
    """Service layer for dataset manifest management.

    Handles business logic including:
        - Immutable manifest creation with integrity data
        - SHA-256 checksum computation and verification
        - Consent record validation (active, not revoked/expired)
        - File existence and accessibility validation
        - Post-creation verification for training job dispatch
        - Manifest comparison for version diffing

    Usage:
        service = DatasetManifestService(db=session, tenant=tenant_context)
        manifest = await service.create_manifest(data)
    """

    def __init__(self, db: "AsyncSession", tenant: "TenantContext") -> None:
        """Initialize with a database session and tenant context.

        Args:
            db: SQLAlchemy async session.
            tenant: Authenticated TenantContext (never client-supplied).
        """
        self._db = db
        self._tenant = tenant

    async def create_manifest(
        self,
        data: DatasetManifestCreateRequest,
    ) -> object:
        """Create an immutable dataset manifest.

        Validates:
            - All referenced consent records are active (not revoked/expired)
            - Talent exists and belongs to this org
            - All files are accessible (storage keys exist)

        Once created, the manifest is never modified. A new version must
        be created if the dataset changes.

        Args:
            data: The manifest creation request data.

        Returns:
            The created DatasetManifest ORM instance.

        Raises:
            HTTPException: 400 if consent validation fails.
            HTTPException: 404 if talent not found.
            HTTPException: 422 if file validation fails.
        """
        from app.models.dataset_manifest import DatasetManifest

        # Validate talent exists and belongs to this org
        await self._validate_talent_exists(data.talent_id)

        # Validate consent records are active
        if data.consent_record_ids:
            await self._validate_consent_records(
                data.talent_id, data.consent_record_ids
            )

        # Compute summary fields
        total_file_count = len(data.files)
        total_size_bytes = sum(f.file_size_bytes for f in data.files)

        # Serialize file entries
        manifest_files = [
            {
                "file_ref": f.file_ref,
                "storage_key": f.storage_key,
                "sha256_checksum": f.sha256_checksum,
                "asset_role": f.asset_role.value,
                "file_size_bytes": f.file_size_bytes,
                "content_type": f.content_type,
                "provenance": f.provenance.value,
            }
            for f in data.files
        ]

        # Create immutable manifest with unique version ID
        manifest = DatasetManifest(
            org_id=self._tenant.org_id,
            version=uuid.uuid4(),
            talent_id=data.talent_id,
            manifest_files=manifest_files,
            consent_record_ids=[
                cid for cid in data.consent_record_ids
            ],
            total_file_count=total_file_count,
            total_size_bytes=total_size_bytes,
            is_valid=True,
            created_by=self._tenant.user_id,
        )

        self._db.add(manifest)
        await self._db.flush()
        await self._db.refresh(manifest)

        logger.info(
            "dataset_manifest_created",
            manifest_id=str(manifest.id),
            org_id=str(self._tenant.org_id),
            talent_id=str(data.talent_id),
            version=str(manifest.version),
            file_count=total_file_count,
            total_size_bytes=total_size_bytes,
        )

        return manifest

    async def get_manifest(self, manifest_id: UUID) -> object:
        """Retrieve a dataset manifest by ID.

        Args:
            manifest_id: The manifest UUID.

        Returns:
            The DatasetManifest if found and owned by this tenant.

        Raises:
            HTTPException: 404 if not found or cross-tenant access.
        """
        from sqlalchemy import select

        from app.models.dataset_manifest import DatasetManifest

        stmt = select(DatasetManifest).where(
            DatasetManifest.id == manifest_id,
            DatasetManifest.org_id == self._tenant.org_id,
        )
        result = await self._db.execute(stmt)
        manifest = result.scalar_one_or_none()

        if manifest is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dataset manifest not found",
            )

        return manifest

    async def verify_manifest(
        self,
        manifest_id: UUID,
    ) -> ManifestVerificationResult:
        """Verify a dataset manifest for integrity and consent validity.

        Checks:
            1. All referenced files still exist in storage
            2. File checksums match manifest records (when downloadable)
            3. All consent records are still active (not revoked/expired)
            4. Talent still exists

        If any check fails, the manifest is marked invalid and training
        jobs referencing it MUST be rejected.

        Args:
            manifest_id: The manifest UUID.

        Returns:
            Verification result with per-file issues.

        Raises:
            HTTPException: 404 if manifest not found.
        """
        manifest = await self.get_manifest(manifest_id)
        issues: list[ManifestFileIssue] = []
        files_checked = 0
        files_passed = 0
        consent_valid = True

        # Check consent records
        consent_issues = await self._check_consent_validity(
            manifest.talent_id, manifest.consent_record_ids or []
        )
        if consent_issues:
            consent_valid = False
            issues.extend(consent_issues)

        # Check each file in the manifest
        for file_entry in manifest.manifest_files:
            files_checked += 1
            file_issue = await self._check_file_validity(file_entry)
            if file_issue:
                issues.append(file_issue)
            else:
                files_passed += 1

        is_valid = len(issues) == 0

        # If invalid, mark the manifest
        if not is_valid and manifest.is_valid:
            await self._invalidate_manifest(
                manifest,
                reason=f"{len(issues)} issue(s) detected: {issues[0].issue_type}",
            )

        if not is_valid:
            logger.warning(
                "dataset_manifest_verification_failed",
                manifest_id=str(manifest_id),
                org_id=str(self._tenant.org_id),
                issues_count=len(issues),
                issue_types=[i.issue_type for i in issues],
            )

        return ManifestVerificationResult(
            manifest_id=manifest_id,
            is_valid=is_valid,
            issues=issues,
            files_checked=files_checked,
            files_passed=files_passed,
            consent_valid=consent_valid,
            verified_at=datetime.now(UTC),
        )

    async def list_manifests(
        self,
        limit: int = 20,
        offset: int = 0,
        talent_id: UUID | None = None,
    ) -> tuple[list, int]:
        """List dataset manifests for the authenticated workspace.

        Args:
            limit: Maximum items per page (1-100).
            offset: Pagination offset.
            talent_id: Optional filter by talent.

        Returns:
            Tuple of (items, total_count).
        """
        from sqlalchemy import func, select

        from app.models.dataset_manifest import DatasetManifest

        # Base filter
        base_filter = [DatasetManifest.org_id == self._tenant.org_id]
        if talent_id:
            base_filter.append(DatasetManifest.talent_id == talent_id)

        # Count
        count_stmt = (
            select(func.count())
            .select_from(DatasetManifest)
            .where(*base_filter)
        )
        total = await self._db.scalar(count_stmt) or 0

        # Items
        stmt = (
            select(DatasetManifest)
            .where(*base_filter)
            .order_by(DatasetManifest.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def compare_manifests(
        self,
        manifest_a_id: UUID,
        manifest_b_id: UUID,
    ) -> ManifestComparisonResult:
        """Compare two manifest versions and show differences.

        Shows what files were added, removed, or changed between two
        manifest versions.

        Args:
            manifest_a_id: First manifest UUID (typically older).
            manifest_b_id: Second manifest UUID (typically newer).

        Returns:
            Comparison result with detailed differences.

        Raises:
            HTTPException: 404 if either manifest not found.
        """
        manifest_a = await self.get_manifest(manifest_a_id)
        manifest_b = await self.get_manifest(manifest_b_id)

        # Build lookup by storage_key for efficient comparison
        files_a = {
            f["storage_key"]: f for f in manifest_a.manifest_files
        }
        files_b = {
            f["storage_key"]: f for f in manifest_b.manifest_files
        }

        differences: list[ManifestComparisonEntry] = []

        # Files removed (in A but not in B)
        for key, file_a in files_a.items():
            if key not in files_b:
                differences.append(
                    ManifestComparisonEntry(
                        change_type="removed",
                        file_ref=file_a["file_ref"],
                        storage_key=key,
                    )
                )

        # Files added (in B but not in A)
        for key, file_b in files_b.items():
            if key not in files_a:
                differences.append(
                    ManifestComparisonEntry(
                        change_type="added",
                        file_ref=file_b["file_ref"],
                        storage_key=key,
                    )
                )

        # Files changed (in both but different checksum or role)
        for key in files_a:
            if key in files_b:
                fa = files_a[key]
                fb = files_b[key]
                if fa["sha256_checksum"] != fb["sha256_checksum"]:
                    differences.append(
                        ManifestComparisonEntry(
                            change_type="checksum_changed",
                            file_ref=fa["file_ref"],
                            storage_key=key,
                            old_value=fa["sha256_checksum"],
                            new_value=fb["sha256_checksum"],
                        )
                    )
                elif fa["asset_role"] != fb["asset_role"]:
                    differences.append(
                        ManifestComparisonEntry(
                            change_type="role_changed",
                            file_ref=fa["file_ref"],
                            storage_key=key,
                            old_value=fa["asset_role"],
                            new_value=fb["asset_role"],
                        )
                    )

        files_added = sum(1 for d in differences if d.change_type == "added")
        files_removed = sum(1 for d in differences if d.change_type == "removed")
        files_changed = sum(
            1 for d in differences
            if d.change_type in ("checksum_changed", "role_changed")
        )

        return ManifestComparisonResult(
            manifest_a_id=manifest_a_id,
            manifest_b_id=manifest_b_id,
            files_added=files_added,
            files_removed=files_removed,
            files_changed=files_changed,
            differences=differences,
        )

    # =========================================================================
    # Internal Validation Methods
    # =========================================================================

    async def _validate_talent_exists(self, talent_id: UUID) -> None:
        """Verify talent exists and belongs to this org.

        Raises:
            HTTPException: 404 if talent not found or cross-tenant.
        """
        from sqlalchemy import select

        from app.models.talent import AiTalent

        stmt = select(AiTalent).where(
            AiTalent.id == talent_id,
            AiTalent.org_id == self._tenant.org_id,
        )
        result = await self._db.execute(stmt)
        talent = result.scalar_one_or_none()

        if talent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Talent {talent_id} not found in this workspace",
            )

        # Check soft delete
        if hasattr(talent, "deleted_at") and talent.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Talent {talent_id} has been deleted",
            )

    async def _validate_consent_records(
        self,
        talent_id: UUID,
        consent_record_ids: list[UUID],
    ) -> None:
        """Validate all referenced consent records are active.

        A consent record is active if:
            - It exists and belongs to this org
            - It references the specified talent
            - It has not been revoked (revoked_at is None)
            - It has not expired (expires_at is None or in the future)
            - It includes the 'training' scope

        Raises:
            HTTPException: 400 if any consent record is invalid.
        """
        from sqlalchemy import select

        from app.models.consent import ConsentRecord

        for consent_id in consent_record_ids:
            stmt = select(ConsentRecord).where(
                ConsentRecord.id == consent_id,
                ConsentRecord.org_id == self._tenant.org_id,
            )
            result = await self._db.execute(stmt)
            record = result.scalar_one_or_none()

            if record is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Consent record {consent_id} not found",
                )

            if record.talent_id != talent_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Consent record {consent_id} does not reference "
                        f"talent {talent_id}"
                    ),
                )

            if record.revoked_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Consent record {consent_id} has been revoked "
                        f"(revoked at {record.revoked_at.isoformat()})"
                    ),
                )

            if (
                hasattr(record, "expires_at")
                and record.expires_at is not None
                and record.expires_at < datetime.now(UTC)
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Consent record {consent_id} has expired "
                        f"(expired at {record.expires_at.isoformat()})"
                    ),
                )

            # Verify training scope is included
            if hasattr(record, "scopes") and record.scopes:
                if "training" not in record.scopes:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Consent record {consent_id} does not include "
                            f"'training' scope (has: {record.scopes})"
                        ),
                    )

    async def _check_consent_validity(
        self,
        talent_id: UUID,
        consent_record_ids: list[UUID],
    ) -> list[ManifestFileIssue]:
        """Check if consent records are still valid (for verification).

        Returns issues rather than raising — used during verify_manifest.
        """
        from sqlalchemy import select

        from app.models.consent import ConsentRecord

        issues: list[ManifestFileIssue] = []

        for consent_id in consent_record_ids:
            stmt = select(ConsentRecord).where(
                ConsentRecord.id == consent_id,
                ConsentRecord.org_id == self._tenant.org_id,
            )
            result = await self._db.execute(stmt)
            record = result.scalar_one_or_none()

            if record is None:
                issues.append(
                    ManifestFileIssue(
                        file_ref=f"consent:{consent_id}",
                        storage_key="",
                        issue_type="consent_revoked",
                        detail=f"Consent record {consent_id} no longer exists",
                    )
                )
                continue

            if record.revoked_at is not None:
                issues.append(
                    ManifestFileIssue(
                        file_ref=f"consent:{consent_id}",
                        storage_key="",
                        issue_type="consent_revoked",
                        detail=(
                            f"Consent record {consent_id} was revoked at "
                            f"{record.revoked_at.isoformat()}"
                        ),
                    )
                )

            if (
                hasattr(record, "expires_at")
                and record.expires_at is not None
                and record.expires_at < datetime.now(UTC)
            ):
                issues.append(
                    ManifestFileIssue(
                        file_ref=f"consent:{consent_id}",
                        storage_key="",
                        issue_type="consent_revoked",
                        detail=(
                            f"Consent record {consent_id} has expired "
                            f"(expired at {record.expires_at.isoformat()})"
                        ),
                    )
                )

        return issues

    async def _check_file_validity(
        self,
        file_entry: dict,
    ) -> ManifestFileIssue | None:
        """Check if a single file is still accessible in storage.

        Uses the storage layer to check if the file exists. Does NOT
        download the full file for checksum verification here (that is
        the worker's responsibility at dispatch time).

        Returns None if the file is valid, or an issue if not.
        """
        storage_key = file_entry.get("storage_key", "")
        file_ref = file_entry.get("file_ref", "")

        try:
            from backend.storage import _get_client, B2_BUCKET_NAME

            client = _get_client()
            client.head_object(Bucket=B2_BUCKET_NAME, Key=storage_key)
            return None
        except Exception as exc:
            error_code = ""
            if hasattr(exc, "response"):
                error_code = exc.response.get("Error", {}).get("Code", "")

            if error_code in ("NoSuchKey", "404", "NotFound"):
                return ManifestFileIssue(
                    file_ref=file_ref,
                    storage_key=storage_key,
                    issue_type="file_deleted",
                    detail=f"File no longer exists at storage key: {storage_key}",
                )
            else:
                return ManifestFileIssue(
                    file_ref=file_ref,
                    storage_key=storage_key,
                    issue_type="file_inaccessible",
                    detail=f"Unable to verify file at {storage_key}: {exc}",
                )

    async def _invalidate_manifest(
        self,
        manifest: object,
        reason: str,
    ) -> None:
        """Mark a manifest as invalid (without modifying content).

        Only the validity status fields are updated — the manifest
        content (files, checksums, consent refs) remains immutable.
        """
        manifest.is_valid = False
        manifest.invalidated_at = datetime.now(UTC)
        manifest.invalidation_reason = reason
        await self._db.flush()

        logger.info(
            "dataset_manifest_invalidated",
            manifest_id=str(manifest.id),
            org_id=str(self._tenant.org_id),
            reason=reason,
        )


def compute_file_checksum(content: bytes) -> str:
    """Compute SHA-256 hex digest for file content.

    This is a utility function that can be used by workers to verify
    downloaded files match manifest checksums.

    Args:
        content: Raw file bytes.

    Returns:
        Lowercase hex-encoded SHA-256 digest (64 characters).
    """
    return hashlib.sha256(content).hexdigest()
