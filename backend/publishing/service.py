"""Tenant-scoped publishing service used by authenticated MCP tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend import database
from backend.app.services.platform_registry import connection_allowed, get_platform_definition


class PublishingServiceError(Exception):
    """Raised for safe publishing service failures."""

    def __init__(self, message: str, code: str = "PUBLISHING_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def _safe_record(row: dict[str, Any]) -> dict[str, Any]:
    """Return a publishing row without credential material or raw B2 URLs."""
    secret_parts = ("token", "secret", "password", "api_key", "credential")

    def clean(value: Any, key: str = "") -> Any:
        lowered = key.lower()
        if any(part in lowered for part in secret_parts):
            return None
        if isinstance(value, dict):
            return {
                child_key: clean(child_value, str(child_key))
                for child_key, child_value in value.items()
                if clean(child_value, str(child_key)) is not None
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, str) and value.startswith(("http://", "https://")) and (
            "backblaze" in value.lower() or "b2" in value.lower() or ".s3." in value.lower()
        ):
            return None
        return value

    return {key: clean(value, str(key)) for key, value in row.items() if clean(value, str(key)) is not None}


def _one(query: Any) -> dict[str, Any]:
    """Extract one row or raise a tenant-safe not-found error."""
    try:
        data = query.execute().data or []
    except Exception as exc:
        raise PublishingServiceError("Publishing service unavailable", "PUBLISHING_UNAVAILABLE") from exc
    if not data:
        raise PublishingServiceError("Publishing post not found", "PUBLISH_NOT_FOUND")
    return _safe_record(data[0])


class PublishingService:
    """Perform publishing/calendar mutations with an explicit org predicate."""

    def __init__(self, org_id: str) -> None:
        """Initialize for one trusted organization."""
        if not org_id:
            raise PublishingServiceError("Workspace context required", "WORKSPACE_CONTEXT_REQUIRED")
        self.org_id = org_id

    def create_or_schedule(
        self,
        *,
        platform: str,
        content: str,
        scheduled_for: str,
        asset_id: str | None = None,
        post_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or schedule a tenant-owned post."""
        normalized = platform.strip().lower()
        definition = get_platform_definition(normalized)
        if not connection_allowed(normalized) or (definition and not definition.enabled):
            raise PublishingServiceError(
                f"Platform '{normalized}' is not enabled",
                "PLATFORM_UNAVAILABLE",
            )
        if not content.strip() or not scheduled_for:
            raise PublishingServiceError("content and scheduled_for are required", "INVALID_INPUT")
        try:
            datetime.fromisoformat(scheduled_for.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PublishingServiceError("scheduled_for must be ISO-8601", "INVALID_INPUT") from exc

        if post_id:
            existing = _one(
                database.supabase.table("publishing_posts")
                .select("*")
                .eq("id", post_id)
                .eq("org_id", self.org_id)
            )
            if existing.get("platform") != normalized:
                raise PublishingServiceError("Post platform cannot be changed", "INVALID_INPUT")
            query = (
                database.supabase.table("publishing_posts")
                .update({"caption": content, "scheduled_for": scheduled_for, "status": "scheduled"})
                .eq("id", post_id)
                .eq("org_id", self.org_id)
            )
            return _one(query)

        record = {
            "org_id": self.org_id,
            "platform": normalized,
            "post_type": "image",
            "caption": content,
            "asset_id": asset_id,
            "scheduled_for": scheduled_for,
            "status": "scheduled",
            "approval_status": "approved",
            "provider": normalized,
        }
        try:
            result = database.supabase.table("publishing_posts").insert(record).execute()
            rows = result.data or []
        except Exception as exc:
            raise PublishingServiceError("Publishing service unavailable", "PUBLISHING_UNAVAILABLE") from exc
        return _safe_record(rows[0] if rows else record)

    def list_scheduled(self, status: str | None = None) -> list[dict[str, Any]]:
        """List scheduled posts for the trusted organization."""
        query = (
            database.supabase.table("publishing_posts")
            .select("*")
            .eq("org_id", self.org_id)
            .order("scheduled_for")
        )
        if status:
            query = query.eq("status", status)
        else:
            query = query.in_("status", ["scheduled", "published", "cancelled", "failed"])
        try:
            return [_safe_record(row) for row in (query.execute().data or [])]
        except Exception as exc:
            raise PublishingServiceError("Publishing service unavailable", "PUBLISHING_UNAVAILABLE") from exc

    def get_status(self, post_id: str) -> dict[str, Any]:
        """Read one tenant-owned post status."""
        return _one(
            database.supabase.table("publishing_posts")
            .select("*")
            .eq("id", post_id)
            .eq("org_id", self.org_id)
        )

    def cancel(self, post_id: str) -> dict[str, Any]:
        """Cancel a scheduled post idempotently."""
        self.get_status(post_id)
        return _one(
            database.supabase.table("publishing_posts")
            .update({"status": "cancelled"})
            .eq("id", post_id)
            .eq("org_id", self.org_id)
        )

    def calendar(self, status: str | None = None) -> list[dict[str, Any]]:
        """Return the organization calendar using the same scoped list query."""
        return self.list_scheduled(status)
