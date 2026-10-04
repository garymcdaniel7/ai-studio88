"""Exactly 22 authenticated, tenant-scoped story-engine API endpoints."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from backend.auth import AuthUser, require_auth
from backend.story_engine.repository import (
    StoryNotFoundError,
    StoryPersistenceError,
    StoryRepository,
)
from backend.story_engine.schemas import (
    CharacterCreate,
    CharacterPage,
    CharacterPatch,
    CharacterResponse,
    EpisodeCreate,
    EpisodePage,
    EpisodePatch,
    EpisodeResponse,
    PreviewGenerationResponse,
    SceneCreate,
    ScenePage,
    ScenePatch,
    SceneResponse,
    ShotCreate,
    ShotPage,
    ShotPatch,
    ShotPreviewRequest,
    ShotResponse,
    ShotWriteUpdate,
    UniverseCreate,
    UniversePage,
    UniversePatch,
    UniverseResponse,
)
from backend.story_engine.service import StoryGenerationError, StoryService
from backend.tenant_context import TenantValidationError, validate_org_id

router = APIRouter(tags=["story-engine"])

_EDITOR_ROLES = {"owner", "admin", "editor"}


def get_story_service() -> StoryService:
    """Build the story service for a request."""
    return StoryService(StoryRepository())


def _org(user: AuthUser) -> str:
    """Return the organization resolved from authentication, never from input."""
    try:
        return validate_org_id(user.org_id)
    except TenantValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active workspace membership required",
            headers={"X-Error-Code": "WORKSPACE_MEMBERSHIP_REQUIRED"},
        ) from exc


def _editor(user: AuthUser) -> str:
    """Require an editor-capable role and return its trusted organization."""
    org_id = _org(user)
    if user.role.lower() not in _EDITOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Editor role required",
            headers={"X-Error-Code": "EDITOR_ROLE_REQUIRED"},
        )
    return org_id


def _execute(operation: Callable[[], Any]) -> Any:
    """Map repository failures to the story API error contract."""
    try:
        return operation()
    except StoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story resource not found",
            headers={"X-Error-Code": "STORY_NOT_FOUND"},
        ) from exc
    except StoryPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Story service unavailable",
            headers={"X-Error-Code": "STORY_PERSISTENCE_ERROR"},
        ) from exc
    except StoryGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Preview generation unavailable",
            headers={"X-Error-Code": "STORY_GENERATION_ERROR"},
        ) from exc


# ── Universes (5 endpoints) ──────────────────────────────────────────────────


@router.get("/story/universes", response_model=UniversePage)
def list_universes(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> UniversePage:
    """List universes visible to the authenticated organization."""
    items, total = _execute(lambda: service.list_universes(_org(user), limit, offset))
    return UniversePage(items=items, total=total, limit=limit, offset=offset)


@router.post("/story/universes", response_model=UniverseResponse, status_code=status.HTTP_201_CREATED)
def create_universe(
    data: UniverseCreate,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> UniverseResponse:
    """Create a universe owned by the authenticated organization."""
    return _execute(lambda: service.create_universe(data, _editor(user)))


@router.get("/story/universes/{universe_id}", response_model=UniverseResponse)
def get_universe(
    universe_id: UUID,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> UniverseResponse:
    """Get one organization-owned universe."""
    return _execute(lambda: service.get_universe(str(universe_id), _org(user)))


@router.patch("/story/universes/{universe_id}", response_model=UniverseResponse)
def update_universe(
    universe_id: UUID,
    data: UniversePatch,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> UniverseResponse:
    """Update one organization-owned universe."""
    return _execute(lambda: service.update_universe(str(universe_id), data, _editor(user)))


@router.delete("/story/universes/{universe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_universe(
    universe_id: UUID,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> Response:
    """Delete one organization-owned universe."""
    _execute(lambda: service.delete_universe(str(universe_id), _editor(user)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Characters (4 endpoints) ─────────────────────────────────────────────────


@router.get("/story/universes/{universe_id}/characters", response_model=CharacterPage)
def list_characters(
    universe_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> CharacterPage:
    """List characters under an organization-owned universe."""
    items, total = _execute(lambda: service.list_characters(str(universe_id), _org(user), limit, offset))
    return CharacterPage(items=items, total=total, limit=limit, offset=offset)


@router.post("/story/universes/{universe_id}/characters", response_model=CharacterResponse, status_code=status.HTTP_201_CREATED)
def create_character(
    universe_id: UUID,
    data: CharacterCreate,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> CharacterResponse:
    """Create a character under an organization-owned universe."""
    return _execute(lambda: service.create_character(str(universe_id), data, _editor(user)))


@router.patch("/story/characters/{character_id}", response_model=CharacterResponse)
def update_character(
    character_id: UUID,
    data: CharacterPatch,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> CharacterResponse:
    """Update an organization-owned character."""
    return _execute(lambda: service.update_character(str(character_id), data, _editor(user)))


@router.delete("/story/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(
    character_id: UUID,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> Response:
    """Delete an organization-owned character."""
    _execute(lambda: service.delete_character(str(character_id), _editor(user)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Episodes (5 endpoints) ───────────────────────────────────────────────────


@router.get("/story/universes/{universe_id}/episodes", response_model=EpisodePage)
def list_episodes(
    universe_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> EpisodePage:
    """List episodes under an organization-owned universe."""
    items, total = _execute(lambda: service.list_episodes(str(universe_id), _org(user), limit, offset))
    return EpisodePage(items=items, total=total, limit=limit, offset=offset)


@router.post("/story/universes/{universe_id}/episodes", response_model=EpisodeResponse, status_code=status.HTTP_201_CREATED)
def create_episode(
    universe_id: UUID,
    data: EpisodeCreate,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> EpisodeResponse:
    """Create an episode under an organization-owned universe."""
    return _execute(lambda: service.create_episode(str(universe_id), data, _editor(user)))


@router.get("/story/episodes/{episode_id}", response_model=EpisodeResponse)
def get_episode(
    episode_id: UUID,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> EpisodeResponse:
    """Get one organization-owned episode."""
    return _execute(lambda: service.get_episode(str(episode_id), _org(user)))


@router.patch("/story/episodes/{episode_id}", response_model=EpisodeResponse)
def update_episode(
    episode_id: UUID,
    data: EpisodePatch,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> EpisodeResponse:
    """Update one organization-owned episode."""
    return _execute(lambda: service.update_episode(str(episode_id), data, _editor(user)))


@router.delete("/story/episodes/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_episode(
    episode_id: UUID,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> Response:
    """Delete one organization-owned episode."""
    _execute(lambda: service.delete_episode(str(episode_id), _editor(user)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Scenes (4 endpoints) ─────────────────────────────────────────────────────


@router.get("/story/episodes/{episode_id}/scenes", response_model=ScenePage)
def list_scenes(
    episode_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> ScenePage:
    """List scenes under an organization-owned episode."""
    items, total = _execute(lambda: service.list_scenes(str(episode_id), _org(user), limit, offset))
    return ScenePage(items=items, total=total, limit=limit, offset=offset)


@router.post("/story/episodes/{episode_id}/scenes", response_model=SceneResponse, status_code=status.HTTP_201_CREATED)
def create_scene(
    episode_id: UUID,
    data: SceneCreate,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> SceneResponse:
    """Create a scene under an organization-owned episode."""
    return _execute(lambda: service.create_scene(str(episode_id), data, _editor(user)))


@router.patch("/story/scenes/{scene_id}", response_model=SceneResponse)
def update_scene(
    scene_id: UUID,
    data: ScenePatch,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> SceneResponse:
    """Update one organization-owned scene."""
    return _execute(lambda: service.update_scene(str(scene_id), data, _editor(user)))


@router.delete("/story/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene(
    scene_id: UUID,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> Response:
    """Delete one organization-owned scene."""
    _execute(lambda: service.delete_scene(str(scene_id), _editor(user)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Shots (4 endpoints) ──────────────────────────────────────────────────────


@router.get("/story/scenes/{scene_id}/shots", response_model=ShotPage)
def list_shots(
    scene_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> ShotPage:
    """List shots under an organization-owned scene."""
    items, total = _execute(lambda: service.list_shots(str(scene_id), _org(user), limit, offset))
    return ShotPage(items=items, total=total, limit=limit, offset=offset)


@router.post("/story/scenes/{scene_id}/shots", response_model=ShotResponse, status_code=status.HTTP_201_CREATED)
def create_shot(
    scene_id: UUID,
    data: ShotCreate,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> ShotResponse:
    """Create a shot under an organization-owned scene."""
    return _execute(lambda: service.create_shot(str(scene_id), data, _editor(user)))


@router.put("/shots/{shot_id}", response_model=ShotResponse)
def write_update_shot(
    shot_id: UUID,
    data: ShotWriteUpdate,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> ShotResponse:
    """Persist the authenticated WRITE editor's prompt and preview context."""
    return _execute(lambda: service.update_shot_write(str(shot_id), data, _editor(user)))


@router.post("/shots/{shot_id}/generate", response_model=PreviewGenerationResponse)
def generate_shot_preview(
    shot_id: UUID,
    data: ShotPreviewRequest,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> PreviewGenerationResponse:
    """Queue a tenant-validated, cost-estimated WRITE preview generation."""
    return _execute(
        lambda: service.generate_shot_preview(
            str(shot_id), data, _editor(user), user.user_id
        )
    )


@router.patch("/story/shots/{shot_id}", response_model=ShotResponse)
def update_shot(
    shot_id: UUID,
    data: ShotPatch,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> ShotResponse:
    """Update one organization-owned shot."""
    return _execute(lambda: service.update_shot(str(shot_id), data, _editor(user)))


@router.delete("/story/shots/{shot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shot(
    shot_id: UUID,
    user: AuthUser = Depends(require_auth),
    service: StoryService = Depends(get_story_service),
) -> Response:
    """Delete one organization-owned shot."""
    _execute(lambda: service.delete_shot(str(shot_id), _editor(user)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
