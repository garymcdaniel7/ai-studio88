"""Core Publishing Service — scheduling, dispatch, token refresh, resize.

Implements the publishing pipeline:
    - Schedule posts with validation (min 5 min future)
    - Dispatch within ±60 seconds of scheduled time
    - Evaluate disclosure hooks at dispatch time (R80.4)
    - Include required disclosures in published content
    - OAuth token refresh on expired; mark failed if refresh fails
    - Platform-specific resize specs (9:16 TikTok, 4:5 IG, 16:9 YouTube)
    - Status tracking: scheduled → dispatching → published/failed
    - Cancellation of scheduled (not yet dispatched) posts
    - Audit log all disclosure decisions (R80.6)

Requirements: R38.1, R38.2, R38.3, R38.4, R38.5, R38.6, R38.7, R38.8, R80.4, R80.6
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, update

from app.core.logging import get_logger
from app.models.disclosure_audit_log import DisclosureAuditLog
from app.models.scheduled_post import ScheduledPost, ScheduledPostStatus
from app.services.disclosure_hook_service import DisclosureHookService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.dependencies import TenantContext

logger = get_logger(__name__)

# Minimum scheduling lead time
MIN_SCHEDULE_MINUTES = 5

# Platform-specific resize specifications
PLATFORM_RESIZE_SPECS: dict[str, dict] = {
    "tiktok": {"width": 1080, "height": 1920, "aspect": "9:16"},
    "instagram": {"width": 1080, "height": 1350, "aspect": "4:5"},
    "youtube": {"width": 1920, "height": 1080, "aspect": "16:9"},
}

# Supported platforms for validation
SUPPORTED_PLATFORMS = {"tiktok", "instagram", "youtube", "x", "linkedin", "pinterest"}


class PublishingService:
    """Service for scheduling and dispatching social media posts.

    Manages the full post lifecycle from scheduling through dispatch,
    including OAuth credential refresh and platform-specific transformations.

    Usage:
        service = PublishingService(db=session, tenant=tenant_context)
        post = await service.schedule_post(request_data)
        await service.dispatch_post(post_id)
    """

    def __init__(self, db: "AsyncSession", tenant: "TenantContext") -> None:
        """Initialize with a database session and tenant context.

        Args:
            db: SQLAlchemy async session.
            tenant: Authenticated TenantContext (never client-supplied).
        """
        self._db = db
        self._tenant = tenant

    # =========================================================================
    # Schedule a Post
    # =========================================================================

    async def schedule_post(
        self,
        asset_id: UUID,
        platform: str,
        scheduled_at: datetime,
        caption: str = "",
        talent_id: UUID | None = None,
        connection_id: UUID | None = None,
        approval_id: UUID | None = None,
    ) -> ScheduledPost:
        """Schedule a post for future publishing.

        Validates:
            - Platform is supported
            - scheduled_at is at least 5 minutes in the future
            - Resolves platform-specific resize spec

        Args:
            asset_id: UUID of the asset to publish.
            platform: Target platform (tiktok, instagram, youtube, etc.).
            scheduled_at: When to publish (must be >= now + 5 minutes).
            caption: Post caption text.
            talent_id: Optional talent association.
            connection_id: Optional connection for OAuth credentials.
            approval_id: Optional FK to publishing_approved_packages.

        Returns:
            The created ScheduledPost record.

        Raises:
            HTTPException 422: If platform invalid or scheduled_at too soon.
        """
        # Validate platform
        if platform not in SUPPORTED_PLATFORMS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported platform: {platform}. "
                f"Valid: {sorted(SUPPORTED_PLATFORMS)}",
            )

        # Validate scheduled_at is at least 5 minutes in the future
        now = datetime.now(UTC)
        min_scheduled = now + timedelta(minutes=MIN_SCHEDULE_MINUTES)

        # Ensure scheduled_at is timezone-aware for comparison
        if scheduled_at.tzinfo is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="scheduled_at must include timezone information",
            )

        if scheduled_at < min_scheduled:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"scheduled_at must be at least {MIN_SCHEDULE_MINUTES} minutes "
                f"in the future. Earliest allowed: {min_scheduled.isoformat()}",
            )

        # Resolve resize spec for platform
        resize_spec = PLATFORM_RESIZE_SPECS.get(platform)

        record = ScheduledPost(
            org_id=self._tenant.org_id,
            asset_id=asset_id,
            talent_id=talent_id,
            connection_id=connection_id,
            approval_id=approval_id,
            platform=platform,
            caption=caption,
            scheduled_at=scheduled_at,
            status=ScheduledPostStatus.SCHEDULED,
            resize_spec=resize_spec,
        )

        self._db.add(record)
        await self._db.flush()
        await self._db.refresh(record)

        logger.info(
            "post_scheduled",
            post_id=str(record.id),
            org_id=str(self._tenant.org_id),
            platform=platform,
            scheduled_at=scheduled_at.isoformat(),
        )

        return record

    # =========================================================================
    # List Scheduled Posts
    # =========================================================================

    async def list_scheduled_posts(
        self,
        limit: int = 20,
        offset: int = 0,
        status_filter: ScheduledPostStatus | None = None,
        platform_filter: str | None = None,
    ) -> tuple[list[ScheduledPost], int]:
        """List scheduled posts for the current org with pagination.

        Args:
            limit: Max results per page (1-100).
            offset: Number of records to skip.
            status_filter: Optional filter by post status.
            platform_filter: Optional filter by platform.

        Returns:
            Tuple of (list of posts, total count).
        """
        # Build base conditions
        conditions = [ScheduledPost.org_id == self._tenant.org_id]

        if status_filter is not None:
            conditions.append(ScheduledPost.status == status_filter)
        if platform_filter:
            conditions.append(ScheduledPost.platform == platform_filter)

        # Count query
        count_stmt = select(func.count()).select_from(ScheduledPost).where(*conditions)
        total = await self._db.scalar(count_stmt) or 0

        # Data query
        stmt = (
            select(ScheduledPost)
            .where(*conditions)
            .order_by(ScheduledPost.scheduled_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # =========================================================================
    # Get Single Post
    # =========================================================================

    async def get_post(self, post_id: UUID) -> ScheduledPost:
        """Get a scheduled post by ID (tenant-scoped).

        Args:
            post_id: The post UUID.

        Returns:
            The ScheduledPost record.

        Raises:
            HTTPException 404: If not found or cross-tenant.
        """
        stmt = select(ScheduledPost).where(
            ScheduledPost.id == post_id,
            ScheduledPost.org_id == self._tenant.org_id,
        )
        result = await self._db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scheduled post not found",
            )

        return record

    # =========================================================================
    # Cancel a Post
    # =========================================================================

    async def cancel_post(self, post_id: UUID) -> ScheduledPost:
        """Cancel a scheduled post.

        Only posts with status 'scheduled' can be cancelled.
        Posts that are already dispatching, published, or failed cannot be
        cancelled and return 409.

        Args:
            post_id: The post UUID.

        Returns:
            The updated ScheduledPost record.

        Raises:
            HTTPException 404: If not found.
            HTTPException 409: If post cannot be cancelled (wrong status).
        """
        record = await self.get_post(post_id)

        if record.status != ScheduledPostStatus.SCHEDULED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot cancel post with status '{record.status.value}'. "
                "Only 'scheduled' posts can be cancelled.",
            )

        record.status = ScheduledPostStatus.CANCELLED
        await self._db.flush()
        await self._db.refresh(record)

        logger.info(
            "post_cancelled",
            post_id=str(post_id),
            org_id=str(self._tenant.org_id),
        )

        return record

    # =========================================================================
    # Dispatch a Post
    # =========================================================================

    async def dispatch_post(self, post_id: UUID, force: bool = False) -> ScheduledPost:
        """Dispatch a scheduled post for publishing.

        This is the core dispatch logic that:
        1. Validates the post is ready for dispatch
        2. Evaluates disclosure hooks (R80.4) and augments content
        3. Attempts OAuth token refresh if needed
        4. Marks status as dispatching
        5. Calls the platform provider (or simulation)
        6. Updates status to published/failed
        7. Logs all disclosure decisions for audit (R80.6)

        Args:
            post_id: The post UUID to dispatch.
            force: If True, dispatch even if scheduled_at is in the future.

        Returns:
            The updated ScheduledPost record.

        Raises:
            HTTPException 404: If not found.
            HTTPException 409: If post cannot be dispatched.
        """
        record = await self.get_post(post_id)

        if record.status not in (
            ScheduledPostStatus.SCHEDULED,
            ScheduledPostStatus.FAILED,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot dispatch post with status '{record.status.value}'. "
                "Only 'scheduled' or 'failed' posts can be dispatched.",
            )

        # Check if time is right (within ±60 seconds or forced)
        now = datetime.now(UTC)
        if not force and record.scheduled_at > now + timedelta(seconds=60):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Post is not yet due for dispatch. "
                f"Scheduled at: {record.scheduled_at.isoformat()}. "
                "Use force=true to dispatch immediately.",
            )

        # ─── Evaluate disclosure hooks at dispatch time (R80.4) ───────────
        disclosure_result = await self._evaluate_disclosures_for_dispatch(record)
        # Augment caption with disclosure text
        original_caption = record.caption or ""
        augmented_caption = disclosure_result["final_caption"]

        # Mark as dispatching
        record.status = ScheduledPostStatus.DISPATCHING
        record.dispatched_at = now
        record.caption = augmented_caption
        await self._db.flush()

        # Attempt OAuth token refresh
        token_valid = await self._refresh_token_if_needed(record)
        if not token_valid:
            record.status = ScheduledPostStatus.FAILED
            record.error_message = (
                "OAuth token expired and refresh failed. "
                "Connection marked as disconnected."
            )
            await self._db.flush()
            await self._db.refresh(record)

            logger.warning(
                "post_dispatch_token_failure",
                post_id=str(post_id),
                org_id=str(self._tenant.org_id),
                platform=record.platform,
            )
            return record

        # Attempt publish via provider
        publish_result = await self._publish_to_platform(record)

        if publish_result["success"]:
            record.status = ScheduledPostStatus.PUBLISHED
            record.platform_post_id = publish_result.get("post_id", "")
            record.error_message = None
        else:
            record.status = ScheduledPostStatus.FAILED
            record.error_message = publish_result.get("error", "Unknown error")

        await self._db.flush()
        await self._db.refresh(record)

        logger.info(
            "post_dispatched",
            post_id=str(post_id),
            org_id=str(self._tenant.org_id),
            platform=record.platform,
            status=record.status.value,
            disclosures_applied=disclosure_result["triggered_count"],
        )

        return record

    # =========================================================================
    # Internal: Disclosure Hook Evaluation at Dispatch Time (R80.4, R80.6)
    # =========================================================================

    async def _evaluate_disclosures_for_dispatch(
        self, post: ScheduledPost
    ) -> dict:
        """Evaluate disclosure hooks at dispatch time and persist audit records.

        Calls the DisclosureHookService to evaluate all applicable hooks,
        constructs the augmented caption with disclosure text, and persists
        audit log entries for every hook evaluation (R80.6).

        Args:
            post: The ScheduledPost being dispatched.

        Returns:
            Dict with:
                - final_caption: caption with disclosure text appended
                - triggered_count: number of hooks that triggered
                - hooks: list of DisclosureHookResult objects
        """
        disclosure_service = DisclosureHookService(
            db=self._db, tenant=self._tenant
        )

        # Evaluate all disclosure hooks
        hooks = await disclosure_service.evaluate_hooks(
            platform=post.platform,
            is_sponsored=False,  # TODO: derive from post metadata when available
            asset_id=post.asset_id,
        )

        # Build augmented caption with disclosure texts
        original_caption = post.caption or ""
        disclosure_texts: list[str] = []
        triggered_count = 0

        for hook in hooks:
            if hook.triggered:
                triggered_count += 1
                if hook.text:
                    disclosure_texts.append(hook.text)

        # Construct final caption
        final_caption = original_caption
        if disclosure_texts:
            separator = "\n\n" if original_caption else ""
            final_caption = original_caption + separator + "\n".join(disclosure_texts)

        # Persist audit log entries (R80.6)
        config = await disclosure_service.get_config()
        config_snapshot = {
            "ai_disclosure_enabled": config.ai_disclosure_enabled,
            "sponsorship_disclosure_enabled": config.sponsorship_disclosure_enabled,
            "c2pa_enabled": config.c2pa_enabled,
            "platform_requirements": config.platform_requirements,
        }

        for hook in hooks:
            audit_entry = DisclosureAuditLog(
                org_id=self._tenant.org_id,
                post_id=post.id,
                asset_id=post.asset_id,
                platform=post.platform,
                hook_type=hook.hook_type.value,
                triggered=hook.triggered,
                applied_text=hook.text if hook.triggered else None,
                applied_tags=hook.tags if hook.triggered and hook.tags else None,
                reason=hook.reason,
                metadata_payload=hook.metadata if hook.metadata else None,
                config_snapshot=config_snapshot,
            )
            self._db.add(audit_entry)

        logger.info(
            "disclosure_hooks_applied_at_dispatch",
            post_id=str(post.id),
            org_id=str(self._tenant.org_id),
            platform=post.platform,
            hooks_triggered=triggered_count,
            hooks_total=len(hooks),
        )

        return {
            "final_caption": final_caption,
            "triggered_count": triggered_count,
            "hooks": hooks,
        }

    # =========================================================================
    # Internal: Token Refresh
    # =========================================================================

    async def _refresh_token_if_needed(self, post: ScheduledPost) -> bool:
        """Attempt to refresh OAuth token for the post's connection.

        If the token is expired and refresh fails, marks the connection
        as 'disconnected' and returns False.

        Args:
            post: The ScheduledPost with connection details.

        Returns:
            True if token is valid (or no token needed), False if expired
            and refresh failed.
        """
        if not post.connection_id:
            # No connection linked — assume simulation mode
            return True

        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return True

            client = get_supabase_client()

            # Look up the connection
            result = (
                client.table("social_connections")
                .select("*")
                .eq("platform", post.platform)
                .execute()
            )
            connections = result.data or []

            if not connections:
                return True  # No connection found — simulation mode

            conn = connections[0]
            expires_at_str = conn.get("expires_at", "")

            if not expires_at_str:
                return True  # No expiry tracked — assume valid

            # Parse expiry and check if token is expired
            try:
                expires_at = datetime.fromisoformat(
                    expires_at_str.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                return True  # Can't parse — assume valid

            now = datetime.now(UTC)
            if expires_at > now:
                return True  # Token still valid

            # Token expired — attempt refresh
            refresh_token = conn.get("refresh_token", "")
            if not refresh_token:
                # No refresh token — mark disconnected
                await self._mark_connection_disconnected(post.platform)
                return False

            # Attempt token refresh
            refreshed = await self._perform_token_refresh(
                post.platform, refresh_token
            )
            if not refreshed:
                await self._mark_connection_disconnected(post.platform)
                return False

            return True

        except Exception as exc:
            logger.error(
                "token_refresh_error",
                post_id=str(post.id),
                platform=post.platform,
                error=str(exc),
            )
            return True  # Don't block dispatch on unexpected errors

    async def _perform_token_refresh(
        self, platform: str, refresh_token: str
    ) -> bool:
        """Exchange a refresh token for a new access token.

        Args:
            platform: The social platform.
            refresh_token: The OAuth refresh token.

        Returns:
            True if refresh succeeded, False otherwise.
        """
        import os

        from backend.publishing.oauth import OAUTH_CONFIG

        config = OAUTH_CONFIG.get(platform)
        if not config:
            return False

        client_id = os.getenv(config.get("client_id_env", ""), "")
        client_secret = os.getenv(config.get("client_secret_env", ""), "")

        if not client_id or not client_secret:
            return False

        try:
            import httpx

            token_url = config["token_url"]
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            }

            async with httpx.AsyncClient() as http_client:
                resp = await http_client.post(token_url, data=payload, timeout=15)

            if resp.status_code != 200:
                logger.warning(
                    "token_refresh_failed",
                    platform=platform,
                    status_code=resp.status_code,
                )
                return False

            token_data = resp.json()
            new_access_token = token_data.get("access_token", "")
            if not new_access_token:
                return False

            # Update the stored connection
            from backend.database import get_supabase_client

            client = get_supabase_client()
            import time

            expires_in = token_data.get("expires_in", 3600)
            expires_at = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + expires_in)
            )

            client.table("social_connections").update(
                {
                    "access_token": new_access_token,
                    "expires_at": expires_at,
                    "refresh_token": token_data.get("refresh_token", refresh_token),
                }
            ).eq("platform", platform).execute()

            logger.info("token_refreshed", platform=platform)
            return True

        except Exception as exc:
            logger.error(
                "token_refresh_exception",
                platform=platform,
                error=str(exc),
            )
            return False

    async def _mark_connection_disconnected(self, platform: str) -> None:
        """Mark a social connection as disconnected after refresh failure.

        Args:
            platform: The social platform to disconnect.
        """
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return

            client = get_supabase_client()
            client.table("social_connections").update(
                {"status": "disconnected"}
            ).eq("platform", platform).execute()

            logger.warning(
                "connection_disconnected",
                platform=platform,
                org_id=str(self._tenant.org_id),
            )
        except Exception as exc:
            logger.error(
                "mark_disconnected_error",
                platform=platform,
                error=str(exc),
            )

    # =========================================================================
    # Internal: Platform Publishing
    # =========================================================================

    async def _publish_to_platform(self, post: ScheduledPost) -> dict:
        """Publish content to the target platform.

        Uses simulation provider by default. When real providers are
        configured, dispatches to the appropriate platform API.

        The publishing_provider setting controls behavior:
        - "simulation": records intent, sets status "simulated" (R38.8)
        - "live": calls real platform API

        Args:
            post: The ScheduledPost to publish.

        Returns:
            Dict with 'success', 'post_id', 'error' keys.
        """
        import os

        provider_mode = os.getenv("PUBLISHING_PROVIDER", "simulation")

        if provider_mode == "simulation":
            # Simulation mode — record intent without API calls (R38.8)
            import uuid as uuid_mod

            simulated_id = f"sim_{uuid_mod.uuid4().hex[:12]}"
            logger.info(
                "post_published_simulation",
                post_id=str(post.id),
                platform=post.platform,
                simulated_post_id=simulated_id,
            )
            return {
                "success": True,
                "post_id": simulated_id,
                "url": f"https://{post.platform}.com/p/{simulated_id}",
            }

        # Live mode — use actual social provider
        try:
            from backend.publishing.social_providers import get_social_provider

            provider = get_social_provider(post.platform)

            # Get access token from connection
            from backend.database import get_supabase_client

            client = get_supabase_client()
            conn_result = (
                client.table("social_connections")
                .select("access_token")
                .eq("platform", post.platform)
                .execute()
            )
            connections = conn_result.data or []
            token = connections[0].get("access_token", "") if connections else ""

            if not token:
                return {
                    "success": False,
                    "error": f"No access token for {post.platform}",
                }

            provider.authenticate({"access_token": token})
            result = provider.publish(
                {
                    "caption": post.caption,
                    "asset_id": str(post.asset_id),
                    "resize_spec": post.resize_spec,
                }
            )

            return {
                "success": result.success,
                "post_id": result.post_id or "",
                "error": result.error,
            }

        except Exception as exc:
            logger.error(
                "publish_to_platform_error",
                post_id=str(post.id),
                platform=post.platform,
                error=str(exc),
            )
            return {"success": False, "error": str(exc)[:200]}

    # =========================================================================
    # Dispatch Due Posts (Scheduler Tick)
    # =========================================================================

    async def dispatch_due_posts(self) -> dict:
        """Find and dispatch all posts that are due within ±60 seconds.

        Called periodically (e.g., every 30 seconds) by a scheduler or cron.
        Finds posts where: status='scheduled' AND scheduled_at <= now + 60s.
        Dispatches each one and reports results.

        Returns:
            Dict with 'dispatched', 'failed', 'checked_at' keys.

        Validates: R38.3 — dispatch within ±60 seconds of schedule.
        """
        now = datetime.now(UTC)
        window = now + timedelta(seconds=60)

        # Find posts due for dispatch (within ±60s window)
        stmt = (
            select(ScheduledPost)
            .where(
                ScheduledPost.org_id == self._tenant.org_id,
                ScheduledPost.status == ScheduledPostStatus.SCHEDULED,
                ScheduledPost.scheduled_at <= window,
            )
            .order_by(ScheduledPost.scheduled_at.asc())
            .limit(50)  # Process max 50 per tick to avoid timeout
        )
        result = await self._db.execute(stmt)
        due_posts = list(result.scalars().all())

        dispatched = []
        failed = []

        for post in due_posts:
            try:
                updated = await self._dispatch_single(post)
                if updated.status == ScheduledPostStatus.PUBLISHED:
                    dispatched.append(str(post.id))
                else:
                    failed.append(
                        {"post_id": str(post.id), "error": updated.error_message}
                    )
            except Exception as exc:
                failed.append({"post_id": str(post.id), "error": str(exc)[:200]})

        logger.info(
            "scheduler_tick_complete",
            org_id=str(self._tenant.org_id),
            due_count=len(due_posts),
            dispatched_count=len(dispatched),
            failed_count=len(failed),
        )

        return {
            "checked_at": now.isoformat(),
            "due_count": len(due_posts),
            "dispatched": dispatched,
            "failed": failed,
        }

    async def _dispatch_single(self, post: ScheduledPost) -> ScheduledPost:
        """Dispatch a single post (internal helper for scheduler tick).

        Performs token refresh, platform publish, and status update
        without the lookup/validation that dispatch_post() does.

        Args:
            post: The ScheduledPost record to dispatch.

        Returns:
            The updated ScheduledPost record.
        """
        now = datetime.now(UTC)

        # Mark as dispatching
        post.status = ScheduledPostStatus.DISPATCHING
        post.dispatched_at = now
        await self._db.flush()

        # Token refresh
        token_valid = await self._refresh_token_if_needed(post)
        if not token_valid:
            post.status = ScheduledPostStatus.FAILED
            post.error_message = (
                "OAuth token expired and refresh failed. "
                "Connection marked as disconnected."
            )
            await self._db.flush()
            return post

        # Publish
        publish_result = await self._publish_to_platform(post)

        if publish_result["success"]:
            post.status = ScheduledPostStatus.PUBLISHED
            post.platform_post_id = publish_result.get("post_id", "")
            post.error_message = None
        else:
            post.status = ScheduledPostStatus.FAILED
            post.error_message = publish_result.get("error", "Unknown error")

        await self._db.flush()
        return post

    # =========================================================================
    # Utility: Get Platform Resize Spec
    # =========================================================================

    @staticmethod
    def get_resize_spec(platform: str) -> dict | None:
        """Get the platform-specific resize specification.

        Args:
            platform: Target platform name.

        Returns:
            Resize spec dict or None if no resize needed.
        """
        return PLATFORM_RESIZE_SPECS.get(platform)
