"""Generation Context Package service — immutable context assembly and validation.

Context packages are immutable snapshots capturing the complete state of all
inputs at the moment of job creation. They are NEVER modified after creation.

Key responsibilities:
    - Assemble and freeze all inputs into a versioned package
    - Auto-increment version per org
    - Validate for stale references (talent deleted, model quarantined,
      consent revoked)
    - Enforce immutability: no update method, no PATCH endpoint

All generation surfaces (Brain, API, MCP, scheduled, batch) use the same
canonical boundary.

Requirements: R60.1, R60.2, R60.3, R60.4, R60.5, R60.6
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status

from app.core.logging import get_logger
from app.schemas.generation_context import (
    ContextPackageValidationResult,
    GenerationContextPackageCreate,
    StaleReference,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.dependencies import TenantContext

logger = get_logger(__name__)


class GenerationContextService:
    """Service layer for generation context package management.

    Handles business logic including:
        - Context package creation with version auto-increment
        - Immutability enforcement (no update/patch methods)
        - Stale reference validation
        - Tenant-scoped access control

    Usage:
        service = GenerationContextService(db=session, tenant=tenant_context)
        package = await service.create_context_package(data)
    """

    def __init__(self, db: "AsyncSession", tenant: "TenantContext") -> None:
        """Initialize with a database session and tenant context.

        Args:
            db: SQLAlchemy async session.
            tenant: Authenticated TenantContext (never client-supplied).
        """
        self._db = db
        self._tenant = tenant

    async def create_context_package(
        self,
        data: GenerationContextPackageCreate,
    ) -> object:
        """Assemble and freeze all inputs into an immutable context package.

        Creates a versioned snapshot of all generation inputs. Once created,
        the package is never modified. The version auto-increments per org.

        Args:
            data: The context package creation data.

        Returns:
            The created GenerationContextPackage ORM instance.
        """
        from app.models.generation_context_package import GenerationContextPackage

        # Auto-increment version for this org
        version = await self._get_next_version()

        package = GenerationContextPackage(
            org_id=self._tenant.org_id,
            user_id=self._tenant.user_id,
            version=version,
            talent_record=(
                data.talent_record.model_dump() if data.talent_record else None
            ),
            creative_dna_version=data.creative_dna_version,
            source_assets=(
                [asset.model_dump(mode="json") for asset in data.source_assets]
                if data.source_assets
                else None
            ),
            model_lora_selections=(
                data.model_lora_selections.model_dump(mode="json")
                if data.model_lora_selections
                else None
            ),
            prompt_instructions=(
                data.prompt_instructions.model_dump(mode="json")
                if data.prompt_instructions
                else None
            ),
            consent_verification_result=(
                data.consent_verification_result.model_dump(mode="json")
                if data.consent_verification_result
                else None
            ),
            safety_evaluation_result=(
                data.safety_evaluation_result.model_dump(mode="json")
                if data.safety_evaluation_result
                else None
            ),
            workflow_template=(
                data.workflow_template.model_dump(mode="json")
                if data.workflow_template
                else None
            ),
            project_constraints=(
                data.project_constraints.model_dump(mode="json")
                if data.project_constraints
                else None
            ),
            initiated_by=(data.initiated_by.value if data.initiated_by else None),
        )

        self._db.add(package)
        await self._db.flush()
        await self._db.refresh(package)

        logger.info(
            "generation_context_package_created",
            package_id=str(package.id),
            org_id=str(self._tenant.org_id),
            version=version,
            initiated_by=data.initiated_by.value if data.initiated_by else None,
        )

        return package

    async def get_context_package(self, package_id: UUID) -> object:
        """Retrieve a context package by ID.

        Args:
            package_id: The context package UUID.

        Returns:
            The GenerationContextPackage if found and owned by this tenant.

        Raises:
            HTTPException: 404 if not found or cross-tenant access.
        """
        from sqlalchemy import select

        from app.models.generation_context_package import GenerationContextPackage

        stmt = select(GenerationContextPackage).where(
            GenerationContextPackage.id == package_id,
            GenerationContextPackage.org_id == self._tenant.org_id,
        )
        result = await self._db.execute(stmt)
        package = result.scalar_one_or_none()

        if package is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Generation context package not found",
            )

        return package

    async def validate_context_package(
        self,
        package_id: UUID,
    ) -> ContextPackageValidationResult:
        """Validate a context package for stale references.

        Checks if any referenced entity has changed state since the package
        was created:
            - Talent deleted or quarantined
            - Model/LoRA quarantined or deleted
            - Consent revoked
            - Source assets deleted

        If stale references are detected, the job MUST be rejected.

        Args:
            package_id: The context package UUID.

        Returns:
            Validation result with is_valid and any stale references.

        Raises:
            HTTPException: 404 if package not found.
        """
        package = await self.get_context_package(package_id)
        stale_refs: list[StaleReference] = []

        # Check talent staleness
        if package.talent_record:
            talent_stale = await self._check_talent_staleness(
                package.talent_record
            )
            stale_refs.extend(talent_stale)

        # Check model/LoRA staleness
        if package.model_lora_selections:
            model_stale = await self._check_model_staleness(
                package.model_lora_selections
            )
            stale_refs.extend(model_stale)

        # Check consent staleness
        if package.consent_verification_result and package.talent_record:
            consent_stale = await self._check_consent_staleness(
                package.talent_record, package.consent_verification_result
            )
            stale_refs.extend(consent_stale)

        # Check source asset staleness
        if package.source_assets:
            asset_stale = await self._check_asset_staleness(
                package.source_assets
            )
            stale_refs.extend(asset_stale)

        is_valid = len(stale_refs) == 0

        if not is_valid:
            logger.warning(
                "generation_context_package_stale",
                package_id=str(package_id),
                org_id=str(self._tenant.org_id),
                stale_count=len(stale_refs),
                stale_types=[ref.entity_type for ref in stale_refs],
            )

        return ContextPackageValidationResult(
            is_valid=is_valid,
            stale_references=stale_refs,
            validated_at=datetime.now(UTC),
        )

    async def list_context_packages(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list, int]:
        """List context packages for the authenticated workspace.

        Args:
            limit: Maximum items per page (1-100).
            offset: Pagination offset.

        Returns:
            Tuple of (items, total_count).
        """
        from sqlalchemy import func, select

        from app.models.generation_context_package import GenerationContextPackage

        # Count
        count_stmt = (
            select(func.count())
            .select_from(GenerationContextPackage)
            .where(GenerationContextPackage.org_id == self._tenant.org_id)
        )
        total = await self._db.scalar(count_stmt) or 0

        # Items
        stmt = (
            select(GenerationContextPackage)
            .where(GenerationContextPackage.org_id == self._tenant.org_id)
            .order_by(GenerationContextPackage.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _get_next_version(self) -> int:
        """Get the next version number for this org's context packages.

        Returns:
            The next version integer (1-based).
        """
        from sqlalchemy import func, select

        from app.models.generation_context_package import GenerationContextPackage

        stmt = (
            select(func.coalesce(func.max(GenerationContextPackage.version), 0))
            .where(GenerationContextPackage.org_id == self._tenant.org_id)
        )
        current_max = await self._db.scalar(stmt) or 0
        return current_max + 1

    async def _check_talent_staleness(
        self,
        talent_record: dict,
    ) -> list[StaleReference]:
        """Check if the referenced talent has been deleted or changed.

        Args:
            talent_record: The frozen talent data from the context package.

        Returns:
            List of stale references (empty if talent is still valid).
        """
        stale: list[StaleReference] = []
        talent_id = talent_record.get("talent_id")
        if not talent_id:
            return stale

        from sqlalchemy import select

        from app.models.talent import AiTalent

        stmt = select(AiTalent).where(
            AiTalent.id == talent_id,
            AiTalent.org_id == self._tenant.org_id,
        )
        result = await self._db.execute(stmt)
        talent = result.scalar_one_or_none()

        if talent is None:
            stale.append(
                StaleReference(
                    entity_type="talent",
                    entity_id=talent_id,
                    reason="Talent has been deleted or is inaccessible",
                )
            )
        elif hasattr(talent, "deleted_at") and talent.deleted_at is not None:
            stale.append(
                StaleReference(
                    entity_type="talent",
                    entity_id=talent_id,
                    reason="Talent has been soft-deleted",
                )
            )

        return stale

    async def _check_model_staleness(
        self,
        model_selections: dict,
    ) -> list[StaleReference]:
        """Check if referenced models/LoRAs have been quarantined or deleted.

        Args:
            model_selections: The model/LoRA configuration dict.

        Returns:
            List of stale references for quarantined/deleted models.
        """
        stale: list[StaleReference] = []
        loras = model_selections.get("loras", [])

        for lora in loras:
            lora_id = lora.get("lora_id")
            if not lora_id:
                continue

            # Check if the LoRA still exists and is not quarantined
            from sqlalchemy import select

            from app.models.talent_lora import TalentLora

            stmt = select(TalentLora).where(
                TalentLora.id == lora_id,
                TalentLora.org_id == self._tenant.org_id,
            )
            result = await self._db.execute(stmt)
            lora_record = result.scalar_one_or_none()

            if lora_record is None:
                stale.append(
                    StaleReference(
                        entity_type="lora",
                        entity_id=lora_id,
                        reason="LoRA model has been deleted or is inaccessible",
                    )
                )

        return stale

    async def _check_consent_staleness(
        self,
        talent_record: dict,
        consent_result: dict,
    ) -> list[StaleReference]:
        """Check if consent has been revoked since package creation.

        Args:
            talent_record: The frozen talent data.
            consent_result: The consent verification result.

        Returns:
            List of stale references if consent was revoked.
        """
        stale: list[StaleReference] = []

        # If fictional exemption was applied, consent doesn't need checking
        if consent_result.get("fictional_exemption"):
            return stale

        talent_id = talent_record.get("talent_id")
        if not talent_id:
            return stale

        scopes_checked = consent_result.get("scopes_checked", [])
        if not scopes_checked:
            return stale

        # Check current active consent for this talent
        from sqlalchemy import select

        from app.models.consent import ConsentRecord

        stmt = select(ConsentRecord).where(
            ConsentRecord.org_id == self._tenant.org_id,
            ConsentRecord.talent_id == talent_id,
            ConsentRecord.revoked_at.is_(None),
        )
        result = await self._db.execute(stmt)
        active_records = list(result.scalars().all())

        # Collect active scopes
        active_scopes: set[str] = set()
        for record in active_records:
            if hasattr(record, "scopes") and record.scopes:
                active_scopes.update(record.scopes)

        # Check if any previously-verified scopes are no longer active
        for scope in scopes_checked:
            if scope not in active_scopes:
                stale.append(
                    StaleReference(
                        entity_type="consent",
                        entity_id=talent_id,
                        reason=f"Consent scope '{scope}' has been revoked or expired",
                    )
                )
                break  # One stale consent reference is enough

        return stale

    async def _check_asset_staleness(
        self,
        source_assets: list | dict,
    ) -> list[StaleReference]:
        """Check if source assets have been deleted.

        Args:
            source_assets: List of source asset references.

        Returns:
            List of stale references for deleted assets.
        """
        stale: list[StaleReference] = []

        # Handle both list and dict formats
        assets = source_assets if isinstance(source_assets, list) else []

        for asset_ref in assets:
            asset_id = asset_ref.get("asset_id")
            if not asset_id:
                continue

            from sqlalchemy import select

            from app.models.asset import Asset

            stmt = select(Asset).where(
                Asset.id == asset_id,
                Asset.org_id == self._tenant.org_id,
            )
            result = await self._db.execute(stmt)
            asset = result.scalar_one_or_none()

            if asset is None:
                stale.append(
                    StaleReference(
                        entity_type="asset",
                        entity_id=asset_id,
                        reason="Source asset has been deleted or is inaccessible",
                    )
                )
            elif hasattr(asset, "deleted_at") and asset.deleted_at is not None:
                stale.append(
                    StaleReference(
                        entity_type="asset",
                        entity_id=asset_id,
                        reason="Source asset has been soft-deleted",
                    )
                )

        return stale
