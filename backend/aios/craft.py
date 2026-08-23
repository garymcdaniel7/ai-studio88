"""Tenant-scoped craft library with strict global recipe sanitization."""

from __future__ import annotations

from typing import Any

from backend.tenant_context import validate_org_id

IDENTITY_KEYS = {
    "talent",
    "talent_id",
    "talent_ids",
    "lora",
    "lora_id",
    "lora_ids",
    "voice",
    "voice_profile",
    "voice_profile_id",
    "voice_profiles",
    "org_id",
    "organization_id",
    "tenant_id",
    "user_id",
    "character_id",
    "asset_id",
    "source_asset_id",
    "reference_image",
    "reference_video",
    "embedding",
    "identity",
    "likeness",
    "private",
    "ip",
}


def _identity_key(key: str) -> bool:
    """Match exact identity keys and common identity-bearing suffixes."""
    normalized = key.lower().replace("-", "_").replace(" ", "_")
    return normalized in IDENTITY_KEYS or any(
        token in normalized for token in ("talent", "lora", "voice_profile", "tenant", "org_id")
    )


def find_identity_fields(value: Any, path: str = "recipe") -> list[str]:
    """Return paths to identity/IP-bearing keys in nested recipe data."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if _identity_key(str(key)):
                found.append(child_path)
            found.extend(find_identity_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_identity_fields(child, f"{path}[{index}]"))
    return found


def validate_recipe(*, is_global: bool, org_id: str | None, recipe: dict[str, Any]) -> None:
    """Validate tenant scope and reject identity-bearing global craft."""
    if is_global and org_id is not None:
        raise ValueError("global recipes must not carry org_id")
    if not is_global:
        validate_org_id(org_id)
    if is_global:
        paths = find_identity_fields(recipe)
        if paths:
            raise ValueError(f"global recipe contains tenant identity/IP fields: {', '.join(paths)}")


class CraftLibrary:
    """CRUD facade for global and tenant-owned craft recipes."""

    def __init__(self, db_client: Any | None = None) -> None:
        self._db_client = db_client

    def _db(self) -> Any:
        if self._db_client is not None:
            return self._db_client
        from backend.database import supabase

        return supabase

    def create(
        self,
        *,
        model: str,
        category: str,
        recipe: dict[str, Any],
        is_global: bool = False,
        org_id: str | None = None,
        draft: bool = False,
    ) -> dict:
        """Create a validated craft recipe, global or tenant-scoped."""
        validate_recipe(is_global=is_global, org_id=org_id, recipe=recipe)
        record = {
            "global": is_global,
            "org_id": org_id,
            "model": model,
            "category": category,
            "recipe": recipe,
            "rating_avg": 0.0,
            "uses": 0,
            "status": "draft" if draft else "published",
        }
        result = self._db().table("craft_recipes").insert(record).execute()
        return result.data[0] if result.data else record

    def list_visible(self, org_id: str) -> list[dict]:
        """List global recipes and recipes owned by the validated tenant."""
        org_id = validate_org_id(org_id)
        result = (
            self._db()
            .table("craft_recipes")
            .select("*")
            .or_(f"global.eq.true,org_id.eq.{org_id}")
            .order("rating_avg", desc=True)
            .execute()
        )
        return result.data or []

    def promote_to_global(self, recipe_id: str, org_id: str) -> dict:
        """Promote a tenant draft only after revalidating its craft-only payload."""
        org_id = validate_org_id(org_id)
        result = (
            self._db()
            .table("craft_recipes")
            .select("*")
            .eq("id", recipe_id)
            .eq("org_id", org_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise LookupError("craft recipe not found")
        recipe = result.data[0]
        validate_recipe(is_global=True, org_id=None, recipe=recipe.get("recipe") or {})
        updated = (
            self._db()
            .table("craft_recipes")
            .update({"global": True, "org_id": None, "status": "published"})
            .eq("id", recipe_id)
            .eq("org_id", org_id)
            .execute()
        )
        return updated.data[0] if updated.data else {**recipe, "global": True, "org_id": None}
