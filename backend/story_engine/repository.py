"""Tenant-scoped persistence boundary for the story-engine API."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend import database


class StoryNotFoundError(LookupError):
    """Raised when a story record is absent or belongs to another tenant."""


class StoryPersistenceError(RuntimeError):
    """Raised when the story persistence provider fails unexpectedly."""


_NOT_FOUND_CODES = {"PGRST116", "404", 404, 406}


def _is_not_found_error(exc: Exception) -> bool:
    """Identify Supabase's single-row not-found response without importing its SDK."""
    code = getattr(exc, "code", None)
    status = getattr(exc, "status_code", getattr(exc, "status", None))
    message = str(exc).lower()
    return code in _NOT_FOUND_CODES or status in _NOT_FOUND_CODES or "0 rows" in message


def _rows(result: Any) -> list[dict[str, Any]]:
    """Extract a list of row mappings from a Supabase response."""
    data = getattr(result, "data", result)
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    return list(data)


def _one(result: Any, resource: str) -> dict[str, Any]:
    """Extract one row or report a tenant-safe not-found result."""
    rows = _rows(result)
    if not rows:
        raise StoryNotFoundError(f"{resource} not found")
    return rows[0]


def _call(operation: Callable[[], Any], resource: str) -> Any:
    """Run a database operation and normalize provider errors."""
    try:
        return operation()
    except StoryNotFoundError:
        raise
    except ValueError as exc:
        # Existing database helpers use ValueError for a missing/foreign parent.
        raise StoryNotFoundError(f"{resource} not found") from exc
    except Exception as exc:
        if _is_not_found_error(exc):
            raise StoryNotFoundError(f"{resource} not found") from exc
        raise StoryPersistenceError(f"Unable to access {resource}") from exc


def _page(result: Any, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    """Apply the API page window to the already tenant-filtered result."""
    rows = _rows(result)
    return rows[offset : offset + limit], len(rows)


def _payload(data: Any) -> dict[str, Any]:
    """Convert a validated Pydantic request into JSON-compatible data."""
    return data.model_dump(mode="json", exclude_unset=True)


def _normalise_reference_metadata(metadata: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """Keep ordered IDs while discarding client-supplied URL metadata."""
    normalized = dict(metadata or {})
    references = normalized.get("references")
    if references is not None:
        reference_ids = [str(reference["id"]) for reference in references]
    else:
        reference_ids = [str(reference_id) for reference_id in normalized.get("reference_asset_ids", [])]
    if reference_ids:
        normalized["reference_asset_ids"] = reference_ids
        normalized["references"] = [{"id": reference_id} for reference_id in reference_ids]
    return normalized, reference_ids


class StoryRepository:
    """Repository delegating to existing org-scoped story database helpers.

    The repository never accepts a client organization selector. Every call
    receives the trusted organization from the authenticated request and uses
    the existing database helpers' direct and inherited parent predicates.
    """

    def list_universes(self, org_id: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """List universes for one organization."""
        return _page(_call(lambda: database.get_universes(org_id), "Universe"), limit, offset)

    def create_universe(self, data: Any, org_id: str) -> dict[str, Any]:
        """Create a universe with server-owned organization attribution."""
        return _one(_call(lambda: database.create_universe(_payload(data), org_id), "Universe"), "Universe")

    def get_universe(self, universe_id: str, org_id: str) -> dict[str, Any]:
        """Get a universe scoped to the trusted organization."""
        return _one(_call(lambda: database.get_universe(universe_id, org_id), "Universe"), "Universe")

    def update_universe(self, universe_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Update a universe without permitting ownership changes."""
        return _one(
            _call(lambda: database.update_universe(universe_id, _payload(data), org_id), "Universe"),
            "Universe",
        )

    def delete_universe(self, universe_id: str, org_id: str) -> None:
        """Delete an owned universe after verifying its existence."""
        self.get_universe(universe_id, org_id)
        _call(lambda: database.delete_universe(universe_id, org_id), "Universe")

    def list_characters(
        self, universe_id: str, org_id: str, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        """List characters after verifying their universe parent."""
        return _page(_call(lambda: database.get_characters(universe_id, org_id), "Universe"), limit, offset)

    def create_character(self, universe_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Create a character under an owned universe."""
        payload = _payload(data)
        payload["universe_id"] = universe_id
        return _one(_call(lambda: database.create_character(payload, org_id), "Character"), "Character")

    def update_character(self, character_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Update an organization-owned character."""
        self.get_character(character_id, org_id)
        return _one(
            _call(lambda: database.update_character(character_id, _payload(data), org_id), "Character"),
            "Character",
        )

    def get_character(self, character_id: str, org_id: str) -> dict[str, Any]:
        """Verify a character's denormalized organization ownership."""
        return _one(_call(lambda: database.get_character(character_id, org_id), "Character"), "Character")

    def delete_character(self, character_id: str, org_id: str) -> None:
        """Delete a character with a direct organization predicate."""
        self.get_character(character_id, org_id)
        _call(
            lambda: database.supabase.table("characters")
            .delete()
            .eq("id", character_id)
            .eq("org_id", org_id)
            .execute(),
            "Character",
        )

    def list_episodes(
        self, universe_id: str, org_id: str, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        """List episodes after verifying their universe parent."""
        return _page(_call(lambda: database.get_episodes(universe_id, org_id), "Universe"), limit, offset)

    def create_episode(self, universe_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Create an episode under an owned universe."""
        payload = _payload(data)
        payload["universe_id"] = universe_id
        return _one(_call(lambda: database.create_episode(payload, org_id), "Episode"), "Episode")

    def get_episode(self, episode_id: str, org_id: str) -> dict[str, Any]:
        """Get an episode scoped to the trusted organization."""
        return _one(_call(lambda: database.get_episode(episode_id, org_id), "Episode"), "Episode")

    def update_episode(self, episode_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Update an organization-owned episode."""
        self.get_episode(episode_id, org_id)
        return _one(
            _call(lambda: database.update_episode(episode_id, _payload(data), org_id), "Episode"),
            "Episode",
        )

    def delete_episode(self, episode_id: str, org_id: str) -> None:
        """Delete an episode with a direct organization predicate."""
        self.get_episode(episode_id, org_id)
        _call(
            lambda: database.supabase.table("episodes")
            .delete()
            .eq("id", episode_id)
            .eq("org_id", org_id)
            .execute(),
            "Episode",
        )

    def list_scenes(
        self, episode_id: str, org_id: str, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        """List scenes after verifying their episode parent."""
        return _page(_call(lambda: database.get_scenes(episode_id, org_id), "Episode"), limit, offset)

    def create_scene(self, episode_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Create a scene under an owned episode."""
        payload = _payload(data)
        payload["episode_id"] = episode_id
        return _one(_call(lambda: database.create_scene(payload, org_id), "Scene"), "Scene")

    def get_scene(self, scene_id: str, org_id: str) -> dict[str, Any]:
        """Get a scene through its organization-scoped parent helper."""
        return _one(_call(lambda: database.supabase.table("scenes").select("*").eq("id", scene_id).eq("org_id", org_id).single().execute(), "Scene"), "Scene")

    def update_scene(self, scene_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Update an organization-owned scene."""
        self.get_scene(scene_id, org_id)
        return _one(
            _call(lambda: database.update_scene(scene_id, _payload(data), org_id), "Scene"),
            "Scene",
        )

    def delete_scene(self, scene_id: str, org_id: str) -> None:
        """Delete a scene with a direct organization predicate."""
        self.get_scene(scene_id, org_id)
        _call(
            lambda: database.supabase.table("scenes")
            .delete()
            .eq("id", scene_id)
            .eq("org_id", org_id)
            .execute(),
            "Scene",
        )

    def list_shots(
        self, scene_id: str, org_id: str, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        """List shots after verifying their scene parent."""
        return _page(_call(lambda: database.get_shots(scene_id, org_id), "Scene"), limit, offset)

    def create_shot(self, scene_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Create a shot under an owned scene."""
        payload = _payload(data)
        payload["scene_id"] = scene_id
        return _one(_call(lambda: database.create_shot(payload, org_id), "Shot"), "Shot")

    def get_shot(self, shot_id: str, org_id: str) -> dict[str, Any]:
        """Get a shot scoped to the trusted organization."""
        return _one(_call(lambda: database.supabase.table("shots").select("*").eq("id", shot_id).eq("org_id", org_id).single().execute(), "Shot"), "Shot")

    def update_shot(self, shot_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Update an organization-owned shot."""
        self.get_shot(shot_id, org_id)
        return _one(
            _call(lambda: database.update_shot(shot_id, _payload(data), org_id), "Shot"),
            "Shot",
        )

    def update_shot_write(self, shot_id: str, data: Any, org_id: str) -> dict[str, Any]:
        """Persist WRITE fields after validating all referenced assets belong to org."""
        payload = _payload(data)
        description = payload.pop("prompt", None) or payload.get("description")
        if description is not None:
            payload["description"] = description
        metadata, reference_ids = _normalise_reference_metadata(payload.get("metadata"))
        if "metadata" in payload:
            payload["metadata"] = metadata
        self._validate_owned_ids("assets", reference_ids, org_id)
        from backend.story_engine.schemas import ShotPatch

        return self.update_shot(shot_id, ShotPatch.model_validate(payload), org_id)

    def validate_preview_context(self, shot_id: str, request: Any, org_id: str) -> None:
        """Validate the shot, parent context, characters, and reference assets."""
        self.get_shot(shot_id, org_id)
        if request.previous_shot_id is not None:
            self.get_shot(str(request.previous_shot_id), org_id)
        self._validate_owned_ids("assets", [str(value) for value in request.reference_asset_ids], org_id)
        self._validate_owned_ids("characters", [str(value) for value in request.character_ids], org_id)

    def _validate_owned_ids(self, table: str, ids: list[str], org_id: str) -> None:
        """Require every referenced record to be visible through the trusted org."""
        if not ids:
            return
        client = getattr(database, "supabase", None)
        if client is None:
            raise StoryPersistenceError("Story persistence provider unavailable")
        result = _call(
            lambda: client.table(table)
            .select("id")
            .eq("org_id", org_id)
            .in_("id", ids)
            .execute(),
            table.title(),
        )
        owned_ids = {str(row.get("id")) for row in _rows(result)}
        if owned_ids != set(ids):
            raise StoryNotFoundError(f"{table.title()} reference not found")

    def delete_shot(self, shot_id: str, org_id: str) -> None:
        """Delete a shot with a direct organization predicate."""
        self.get_shot(shot_id, org_id)
        _call(
            lambda: database.supabase.table("shots")
            .delete()
            .eq("id", shot_id)
            .eq("org_id", org_id)
            .execute(),
            "Shot",
        )
