"""Disclosure Hook Service — evaluates disclosure policies at publish time.

Implements configurable policy hooks for:
    - AI/synthetic media disclosure (labeling content as AI-generated)
    - Sponsorship/commercial disclosure (FTC/ASA compliance)
    - Provenance metadata (C2PA/Content Credentials attachment points)
    - Platform-specific policy (destination ToS compliance)

Key behaviors:
    - Evaluates applicable hooks based on workspace config + platform
    - Returns disclosure payload to include in published content
    - Provides disclosure preview before actual publishing
    - Logs all disclosure decisions for audit/compliance

Requirements: R80.1, R80.2, R80.3, R80.4, R80.5, R80.6
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select

from app.core.logging import get_logger
from app.models.workspace_disclosure_config import WorkspaceDisclosureConfig
from app.schemas.disclosure_config import (
    DisclosureConfigResponse,
    DisclosureConfigUpdateRequest,
    DisclosureHookResult,
    DisclosureHookType,
    DisclosurePreviewResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.dependencies import TenantContext

logger = get_logger(__name__)


class DisclosureHookService:
    """Service for managing disclosure configuration and evaluating hooks.

    Evaluates disclosure hooks at publish time based on workspace config,
    destination platform, and post attributes. All evaluation decisions
    are logged for audit and compliance purposes.

    Usage:
        service = DisclosureHookService(db=session, tenant=tenant_context)
        config = await service.get_config()
        preview = await service.preview_disclosures(platform="instagram", ...)
    """

    def __init__(self, db: "AsyncSession", tenant: "TenantContext") -> None:
        """Initialize with database session and tenant context.

        Args:
            db: SQLAlchemy async session.
            tenant: Authenticated TenantContext (never client-supplied).
        """
        self._db = db
        self._tenant = tenant

    # =========================================================================
    # Configuration CRUD
    # =========================================================================

    async def get_config(self) -> WorkspaceDisclosureConfig:
        """Get the disclosure configuration for this workspace.

        Returns the existing config or creates a default one if none exists.

        Returns:
            WorkspaceDisclosureConfig ORM instance.
        """
        stmt = select(WorkspaceDisclosureConfig).where(
            WorkspaceDisclosureConfig.org_id == self._tenant.org_id,
        )
        result = await self._db.execute(stmt)
        config = result.scalar_one_or_none()

        if config is None:
            # Create default config (all disclosures disabled by default)
            config = WorkspaceDisclosureConfig(
                org_id=self._tenant.org_id,
                ai_disclosure_enabled=False,
                sponsorship_disclosure_enabled=False,
                c2pa_enabled=False,
            )
            self._db.add(config)
            await self._db.flush()
            await self._db.refresh(config)

            logger.info(
                "disclosure_config_created_default",
                org_id=str(self._tenant.org_id),
                config_id=str(config.id),
            )

        return config

    async def update_config(
        self, request: DisclosureConfigUpdateRequest
    ) -> WorkspaceDisclosureConfig:
        """Update the workspace disclosure configuration.

        Only provided (non-None) fields are updated. Creates config if
        it doesn't exist yet.

        Args:
            request: Update request with optional fields.

        Returns:
            Updated WorkspaceDisclosureConfig ORM instance.
        """
        config = await self.get_config()

        # Apply only provided fields
        update_data = request.model_dump(exclude_unset=True, exclude_none=True)

        for field_name, value in update_data.items():
            setattr(config, field_name, value)

        await self._db.flush()
        await self._db.refresh(config)

        logger.info(
            "disclosure_config_updated",
            org_id=str(self._tenant.org_id),
            config_id=str(config.id),
            updated_fields=list(update_data.keys()),
        )

        return config

    # =========================================================================
    # Disclosure Evaluation
    # =========================================================================

    async def evaluate_hooks(
        self,
        platform: str,
        is_sponsored: bool = False,
        asset_id: UUID | None = None,
    ) -> list[DisclosureHookResult]:
        """Evaluate all applicable disclosure hooks for a publishing action.

        Called at dispatch time to determine what disclosures must be
        included in the published content.

        Args:
            platform: Target platform (instagram, tiktok, youtube, etc.)
            is_sponsored: Whether this is sponsored/commercial content.
            asset_id: Optional asset UUID for provenance lookup.

        Returns:
            List of DisclosureHookResult for each evaluated hook.

        Requirements: R80.4
        """
        config = await self.get_config()
        results: list[DisclosureHookResult] = []

        # 1. AI/Synthetic disclosure
        results.append(self._evaluate_ai_disclosure(config, platform))

        # 2. Sponsorship/commercial disclosure
        results.append(self._evaluate_sponsorship_disclosure(config, platform, is_sponsored))

        # 3. C2PA provenance
        results.append(self._evaluate_c2pa(config, asset_id))

        # 4. Platform-specific policy
        results.append(self._evaluate_platform_specific(config, platform))

        # Log disclosure decisions for audit (R80.6)
        triggered_hooks = [r.hook_type.value for r in results if r.triggered]
        logger.info(
            "disclosure_hooks_evaluated",
            org_id=str(self._tenant.org_id),
            platform=platform,
            is_sponsored=is_sponsored,
            asset_id=str(asset_id) if asset_id else None,
            hooks_triggered=triggered_hooks,
            hooks_total=len(results),
        )

        return results

    async def preview_disclosures(
        self,
        platform: str,
        caption: str = "",
        is_sponsored: bool = False,
        asset_id: UUID | None = None,
    ) -> DisclosurePreviewResponse:
        """Preview what disclosures would be attached to a post.

        Shows the user exactly what will be added before publishing.
        Does NOT persist anything — purely read-only preview.

        Args:
            platform: Target platform.
            caption: Current post caption.
            is_sponsored: Whether this is sponsored content.
            asset_id: Optional asset for provenance.

        Returns:
            DisclosurePreviewResponse with final caption, tags, and summary.

        Requirements: R80.5
        """
        hooks = await self.evaluate_hooks(
            platform=platform,
            is_sponsored=is_sponsored,
            asset_id=asset_id,
        )

        # Build final caption with disclosure text
        disclosure_texts: list[str] = []
        all_tags: list[str] = []
        c2pa_attached = False

        for hook in hooks:
            if hook.triggered:
                if hook.text:
                    disclosure_texts.append(hook.text)
                all_tags.extend(hook.tags)
                if hook.hook_type == DisclosureHookType.PROVENANCE_C2PA:
                    c2pa_attached = True

        # Construct final caption
        final_caption = caption
        if disclosure_texts:
            separator = "\n\n" if caption else ""
            final_caption = caption + separator + "\n".join(disclosure_texts)

        # Build summary
        triggered_count = sum(1 for h in hooks if h.triggered)
        if triggered_count == 0:
            summary = "No disclosures required for this post."
        else:
            triggered_names = [h.hook_type.value for h in hooks if h.triggered]
            summary = (
                f"{triggered_count} disclosure(s) will be applied: "
                f"{', '.join(triggered_names)}."
            )

        return DisclosurePreviewResponse(
            hooks_evaluated=hooks,
            final_caption=final_caption,
            final_tags=all_tags,
            c2pa_attached=c2pa_attached,
            platform=platform,
            summary=summary,
        )

    # =========================================================================
    # Individual hook evaluators
    # =========================================================================

    def _evaluate_ai_disclosure(
        self, config: WorkspaceDisclosureConfig, platform: str
    ) -> DisclosureHookResult:
        """Evaluate the AI/synthetic media disclosure hook.

        Args:
            config: Workspace disclosure configuration.
            platform: Target platform.

        Returns:
            Hook result with triggered state and disclosure content.
        """
        if not config.ai_disclosure_enabled:
            return DisclosureHookResult(
                hook_type=DisclosureHookType.AI_SYNTHETIC,
                triggered=False,
                reason="AI disclosure is disabled in workspace configuration",
            )

        # Determine text and tags
        text = config.ai_disclosure_text or "This content was created with AI assistance."
        tags = [t for t in (config.disclosure_tags or []) if "ai" in t.lower() or "generated" in t.lower()]

        # Check platform-specific override
        platform_reqs = config.platform_requirements or {}
        platform_config = platform_reqs.get(platform, {})
        if platform_config.get("ai_label"):
            text = platform_config["ai_label"]

        return DisclosureHookResult(
            hook_type=DisclosureHookType.AI_SYNTHETIC,
            triggered=True,
            text=text,
            tags=tags,
            metadata={"platform": platform, "source": "workspace_config"},
            reason="AI disclosure enabled in workspace configuration",
        )

    def _evaluate_sponsorship_disclosure(
        self,
        config: WorkspaceDisclosureConfig,
        platform: str,
        is_sponsored: bool,
    ) -> DisclosureHookResult:
        """Evaluate the sponsorship/commercial disclosure hook.

        Only triggers if BOTH the config is enabled AND the post is flagged
        as sponsored.

        Args:
            config: Workspace disclosure configuration.
            platform: Target platform.
            is_sponsored: Whether the post is sponsored content.

        Returns:
            Hook result.
        """
        if not config.sponsorship_disclosure_enabled:
            return DisclosureHookResult(
                hook_type=DisclosureHookType.SPONSORSHIP_COMMERCIAL,
                triggered=False,
                reason="Sponsorship disclosure is disabled in workspace configuration",
            )

        if not is_sponsored:
            return DisclosureHookResult(
                hook_type=DisclosureHookType.SPONSORSHIP_COMMERCIAL,
                triggered=False,
                reason="Post is not marked as sponsored content",
            )

        text = config.sponsorship_text or "#Ad #Sponsored"
        tags = [t for t in (config.disclosure_tags or []) if "sponsor" in t.lower() or "ad" in t.lower()]

        # Platform-specific sponsorship format
        platform_reqs = config.platform_requirements or {}
        platform_config = platform_reqs.get(platform, {})
        if platform_config.get("sponsorship_label"):
            text = platform_config["sponsorship_label"]

        return DisclosureHookResult(
            hook_type=DisclosureHookType.SPONSORSHIP_COMMERCIAL,
            triggered=True,
            text=text,
            tags=tags,
            metadata={"platform": platform, "compliance": "FTC/ASA"},
            reason="Post is sponsored and sponsorship disclosure is enabled",
        )

    def _evaluate_c2pa(
        self, config: WorkspaceDisclosureConfig, asset_id: UUID | None
    ) -> DisclosureHookResult:
        """Evaluate the C2PA/Content Credentials provenance hook.

        Args:
            config: Workspace disclosure configuration.
            asset_id: Optional asset UUID for provenance attachment.

        Returns:
            Hook result.
        """
        if not config.c2pa_enabled:
            return DisclosureHookResult(
                hook_type=DisclosureHookType.PROVENANCE_C2PA,
                triggered=False,
                reason="C2PA provenance is disabled in workspace configuration",
            )

        if not asset_id:
            return DisclosureHookResult(
                hook_type=DisclosureHookType.PROVENANCE_C2PA,
                triggered=False,
                reason="No asset_id provided for provenance attachment",
            )

        return DisclosureHookResult(
            hook_type=DisclosureHookType.PROVENANCE_C2PA,
            triggered=True,
            text=None,
            tags=[],
            metadata={
                "asset_id": str(asset_id),
                "c2pa_action": "attach_manifest",
                "standard": "C2PA v2.0",
            },
            reason="C2PA enabled and asset provided for provenance attachment",
        )

    def _evaluate_platform_specific(
        self, config: WorkspaceDisclosureConfig, platform: str
    ) -> DisclosureHookResult:
        """Evaluate platform-specific disclosure requirements.

        Looks up platform requirements in the workspace config and applies
        any platform-mandated disclosures.

        Args:
            config: Workspace disclosure configuration.
            platform: Target platform name.

        Returns:
            Hook result.
        """
        platform_reqs = config.platform_requirements or {}
        platform_config = platform_reqs.get(platform)

        if not platform_config:
            return DisclosureHookResult(
                hook_type=DisclosureHookType.PLATFORM_SPECIFIC,
                triggered=False,
                reason=f"No platform-specific requirements configured for '{platform}'",
            )

        # Extract platform-specific disclosure text and tags
        text = platform_config.get("disclosure_text")
        tags = platform_config.get("disclosure_tags", [])
        label = platform_config.get("label")

        if not text and not tags and not label:
            return DisclosureHookResult(
                hook_type=DisclosureHookType.PLATFORM_SPECIFIC,
                triggered=False,
                reason=f"Platform config for '{platform}' has no disclosure content",
            )

        return DisclosureHookResult(
            hook_type=DisclosureHookType.PLATFORM_SPECIFIC,
            triggered=True,
            text=text or label,
            tags=tags,
            metadata={"platform": platform, "platform_config": platform_config},
            reason=f"Platform-specific disclosure configured for '{platform}'",
        )
