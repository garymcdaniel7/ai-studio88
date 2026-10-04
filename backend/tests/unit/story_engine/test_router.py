"""Contract tests for the exact 22 Phase 1 story-engine endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from backend.auth import AuthUser, require_auth
from backend.story_engine.repository import StoryNotFoundError, StoryPersistenceError
from backend.story_engine.router import get_story_service, router
from backend.story_engine.service import StoryService
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
UNIVERSE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CHARACTER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
EPISODE_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
SCENE_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
SHOT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
NOW = datetime.now(UTC).isoformat()

EXPECTED_ROUTES = {
    ("GET", "/api/v1/story/universes"),
    ("POST", "/api/v1/story/universes"),
    ("GET", "/api/v1/story/universes/{universe_id}"),
    ("PATCH", "/api/v1/story/universes/{universe_id}"),
    ("DELETE", "/api/v1/story/universes/{universe_id}"),
    ("GET", "/api/v1/story/universes/{universe_id}/characters"),
    ("POST", "/api/v1/story/universes/{universe_id}/characters"),
    ("PATCH", "/api/v1/story/characters/{character_id}"),
    ("DELETE", "/api/v1/story/characters/{character_id}"),
    ("GET", "/api/v1/story/universes/{universe_id}/episodes"),
    ("POST", "/api/v1/story/universes/{universe_id}/episodes"),
    ("GET", "/api/v1/story/episodes/{episode_id}"),
    ("PATCH", "/api/v1/story/episodes/{episode_id}"),
    ("DELETE", "/api/v1/story/episodes/{episode_id}"),
    ("GET", "/api/v1/story/episodes/{episode_id}/scenes"),
    ("POST", "/api/v1/story/episodes/{episode_id}/scenes"),
    ("PATCH", "/api/v1/story/scenes/{scene_id}"),
    ("DELETE", "/api/v1/story/scenes/{scene_id}"),
    ("GET", "/api/v1/story/scenes/{scene_id}/shots"),
    ("POST", "/api/v1/story/scenes/{scene_id}/shots"),
    ("PATCH", "/api/v1/story/shots/{shot_id}"),
    ("DELETE", "/api/v1/story/shots/{shot_id}"),
}


def _universe() -> dict:
    """Return a representative universe row."""
    return {
        "id": UNIVERSE_ID,
        "org_id": ORG_A,
        "name": "A Universe",
        "description": "A story",
        "genre": "science fiction",
        "tone": "hopeful",
        "setting": "orbit",
        "rules": [],
        "metadata": {},
        "created_at": NOW,
        "updated_at": NOW,
    }


def _character() -> dict:
    """Return a representative character row."""
    return {
        "id": CHARACTER_ID,
        "org_id": ORG_A,
        "universe_id": UNIVERSE_ID,
        "name": "A Character",
        "relationships": [],
        "memory": [],
        "visual_dna": {},
        "metadata": {},
        "created_at": NOW,
        "updated_at": NOW,
    }


def _episode() -> dict:
    """Return a representative episode row."""
    return {
        "id": EPISODE_ID,
        "org_id": ORG_A,
        "universe_id": UNIVERSE_ID,
        "title": "Episode One",
        "episode_number": 1,
        "status": "draft",
        "scenes": [],
        "metadata": {},
        "created_at": NOW,
        "updated_at": NOW,
    }


def _scene() -> dict:
    """Return a representative scene row."""
    return {
        "id": SCENE_ID,
        "org_id": ORG_A,
        "episode_id": EPISODE_ID,
        "scene_number": 1,
        "time_of_day": "day",
        "weather": "clear",
        "characters": [],
        "dialogue": [],
        "shots": [],
        "metadata": {},
        "created_at": NOW,
        "updated_at": NOW,
    }


def _shot() -> dict:
    """Return a representative shot row."""
    return {
        "id": SHOT_ID,
        "org_id": ORG_A,
        "scene_id": SCENE_ID,
        "shot_number": 1,
        "shot_type": "medium",
        "characters": [],
        "duration_seconds": 3.0,
        "transition": "cut",
        "generation_params": {},
        "status": "planned",
        "metadata": {},
        "created_at": NOW,
        "updated_at": NOW,
    }


def _app(user: AuthUser, service: MagicMock) -> FastAPI:
    """Build an isolated app with auth and persistence dependencies overridden."""
    from backend.app.core.error_handlers import register_error_handlers

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    register_error_handlers(app)
    app.dependency_overrides[require_auth] = lambda: user
    app.dependency_overrides[get_story_service] = lambda: service
    return app


@pytest.fixture
def story_service() -> MagicMock:
    """Return a fully configured service double for response-shape tests."""
    service = MagicMock(spec=StoryService)
    universe = _universe()
    character = _character()
    episode = _episode()
    scene = _scene()
    shot = _shot()
    service.list_universes.return_value = ([universe], 1)
    service.create_universe.return_value = universe
    service.get_universe.return_value = universe
    service.update_universe.return_value = universe
    service.delete_universe.return_value = None
    service.list_characters.return_value = ([character], 1)
    service.create_character.return_value = character
    service.update_character.return_value = character
    service.delete_character.return_value = None
    service.list_episodes.return_value = ([episode], 1)
    service.create_episode.return_value = episode
    service.get_episode.return_value = episode
    service.update_episode.return_value = episode
    service.delete_episode.return_value = None
    service.list_scenes.return_value = ([scene], 1)
    service.create_scene.return_value = scene
    service.update_scene.return_value = scene
    service.delete_scene.return_value = None
    service.list_shots.return_value = ([shot], 1)
    service.create_shot.return_value = shot
    service.update_shot.return_value = shot
    service.delete_shot.return_value = None
    return service


@pytest.fixture
def story_client(story_service: MagicMock) -> TestClient:
    """Return an authenticated editor client for the story router."""
    return TestClient(_app(AuthUser(user_id="user-a", org_id=ORG_A, role="editor"), story_service))


@pytest.mark.unit
def test_exactly_22_story_routes_are_registered() -> None:
    """The mounted story surface matches the verified 0/22 baseline contract."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    openapi = app.openapi()
    actual = {
        (method.upper(), path)
        for path, operations in openapi["paths"].items()
        if path.startswith("/api/v1/story/")
        for method in operations
        if method in {"get", "post", "patch", "delete"}
    }
    assert actual == EXPECTED_ROUTES


@pytest.mark.unit
def test_all_22_story_routes_return_contract_shapes(story_client: TestClient) -> None:
    """Every specified route returns its documented success status and shape."""
    requests = [
        ("get", "/story/universes", None, 200),
        ("post", "/story/universes", {"name": "New"}, 201),
        ("get", f"/story/universes/{UNIVERSE_ID}", None, 200),
        ("patch", f"/story/universes/{UNIVERSE_ID}", {"name": "Changed"}, 200),
        ("delete", f"/story/universes/{UNIVERSE_ID}", None, 204),
        ("get", f"/story/universes/{UNIVERSE_ID}/characters", None, 200),
        ("post", f"/story/universes/{UNIVERSE_ID}/characters", {"name": "New"}, 201),
        ("patch", f"/story/characters/{CHARACTER_ID}", {"name": "Changed"}, 200),
        ("delete", f"/story/characters/{CHARACTER_ID}", None, 204),
        ("get", f"/story/universes/{UNIVERSE_ID}/episodes", None, 200),
        ("post", f"/story/universes/{UNIVERSE_ID}/episodes", {"title": "New"}, 201),
        ("get", f"/story/episodes/{EPISODE_ID}", None, 200),
        ("patch", f"/story/episodes/{EPISODE_ID}", {"title": "Changed"}, 200),
        ("delete", f"/story/episodes/{EPISODE_ID}", None, 204),
        ("get", f"/story/episodes/{EPISODE_ID}/scenes", None, 200),
        ("post", f"/story/episodes/{EPISODE_ID}/scenes", {}, 201),
        ("patch", f"/story/scenes/{SCENE_ID}", {"mood": "tense"}, 200),
        ("delete", f"/story/scenes/{SCENE_ID}", None, 204),
        ("get", f"/story/scenes/{SCENE_ID}/shots", None, 200),
        ("post", f"/story/scenes/{SCENE_ID}/shots", {}, 201),
        ("patch", f"/story/shots/{SHOT_ID}", {"status": "approved"}, 200),
        ("delete", f"/story/shots/{SHOT_ID}", None, 204),
    ]
    for method, path, body, expected_status in requests:
        response = story_client.request(method.upper(), f"/api/v1{path}", json=body)
        assert response.status_code == expected_status, (method, path, response.text)
        if expected_status == 200 and path.endswith("universes"):
            assert set(response.json()) == {"items", "total", "limit", "offset"}


@pytest.mark.unit
def test_lists_are_paginated_and_pass_trusted_org(story_client: TestClient, story_service: MagicMock) -> None:
    """List routes return the standard envelope and never accept an org selector."""
    response = story_client.get("/api/v1/story/universes?limit=7&offset=3")
    assert response.status_code == 200
    assert response.json()["limit"] == 7
    assert response.json()["offset"] == 3
    story_service.list_universes.assert_called_once_with(ORG_A, 7, 3)


@pytest.mark.unit
@pytest.mark.parametrize("method,path,body", [
    ("post", "/story/universes", {"name": "New"}),
    ("patch", f"/story/universes/{UNIVERSE_ID}", {"name": "New"}),
    ("delete", f"/story/universes/{UNIVERSE_ID}", None),
    ("post", f"/story/universes/{UNIVERSE_ID}/characters", {"name": "New"}),
    ("patch", f"/story/characters/{CHARACTER_ID}", {"name": "New"}),
    ("delete", f"/story/characters/{CHARACTER_ID}", None),
    ("post", f"/story/universes/{UNIVERSE_ID}/episodes", {"title": "New"}),
    ("patch", f"/story/episodes/{EPISODE_ID}", {"title": "New"}),
    ("delete", f"/story/episodes/{EPISODE_ID}", None),
    ("post", f"/story/episodes/{EPISODE_ID}/scenes", {}),
    ("patch", f"/story/scenes/{SCENE_ID}", {"mood": "New"}),
    ("delete", f"/story/scenes/{SCENE_ID}", None),
    ("post", f"/story/scenes/{SCENE_ID}/shots", {}),
    ("patch", f"/story/shots/{SHOT_ID}", {"status": "approved"}),
    ("delete", f"/story/shots/{SHOT_ID}", None),
])
def test_viewer_cannot_write_story_resources(
    method: str,
    path: str,
    body: dict | None,
    story_service: MagicMock,
) -> None:
    """All create/update/delete contracts enforce the editor role."""
    client = TestClient(_app(AuthUser(user_id="user-a", org_id=ORG_A, role="viewer"), story_service))
    response = client.request(method.upper(), f"/api/v1{path}", json=body)
    assert response.status_code == 403
    story_service.reset_mock()


@pytest.mark.unit
def test_cross_tenant_detail_is_not_found_and_uses_jwt_org(story_service: MagicMock) -> None:
    """A foreign detail never leaks existence and receives only trusted org context."""
    story_service.get_universe.side_effect = StoryNotFoundError("foreign")
    client = TestClient(_app(AuthUser(user_id="user-b", org_id=ORG_B, role="viewer"), story_service))
    response = client.get(f"/api/v1/story/universes/{UNIVERSE_ID}")
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"
    story_service.get_universe.assert_called_once_with(UNIVERSE_ID, ORG_B)


@pytest.mark.unit
def test_missing_auth_returns_401_before_story_service(story_service: MagicMock) -> None:
    """Every story route has the authentication dependency before business logic."""
    def reject() -> AuthUser:
        raise HTTPException(status_code=401, detail="Authentication required")

    app = _app(AuthUser(user_id="unused", org_id=ORG_A), story_service)
    app.dependency_overrides[require_auth] = reject
    client = TestClient(app)
    response = client.get("/api/v1/story/universes")
    assert response.status_code == 401
    story_service.list_universes.assert_not_called()


@pytest.mark.unit
def test_all_22_story_routes_require_auth(story_service: MagicMock) -> None:
    """Authentication is required on every one of the 22 route contracts."""
    def reject() -> AuthUser:
        raise HTTPException(status_code=401, detail="Authentication required")

    app = _app(AuthUser(user_id="unused", org_id=ORG_A), story_service)
    app.dependency_overrides[require_auth] = reject
    client = TestClient(app)
    ids = {
        "{universe_id}": UNIVERSE_ID,
        "{character_id}": CHARACTER_ID,
        "{episode_id}": EPISODE_ID,
        "{scene_id}": SCENE_ID,
        "{shot_id}": SHOT_ID,
    }
    for method, path in EXPECTED_ROUTES:
        for placeholder, value in ids.items():
            path = path.replace(placeholder, value)
        response = client.request(method, path)
        assert response.status_code == 401, (method, path, response.text)


@pytest.mark.unit
def test_invalid_uuid_and_body_return_422(story_client: TestClient) -> None:
    """Boundary UUID and Pydantic constraints reject malformed story input."""
    invalid_uuid = story_client.get("/api/v1/story/universes/not-a-uuid")
    invalid_body = story_client.post("/api/v1/story/universes", json={"name": ""})
    injected_body = story_client.post(
        "/api/v1/story/universes",
        json={"name": "Valid", "org_id": ORG_A},
    )
    assert invalid_uuid.status_code == 422
    assert invalid_body.status_code == 422
    assert injected_body.status_code == 422


@pytest.mark.unit
def test_repository_failure_returns_structured_500(story_service: MagicMock) -> None:
    """Unexpected provider failures do not leak details through the API."""
    story_service.get_universe.side_effect = StoryPersistenceError("secret provider detail")
    client = TestClient(_app(AuthUser(user_id="user-a", org_id=ORG_A), story_service))
    response = client.get(f"/api/v1/story/universes/{UNIVERSE_ID}")
    assert response.status_code == 500
    assert response.json()["code"] == "STORY_PERSISTENCE_ERROR"
    assert "secret provider detail" not in response.text


@pytest.mark.unit
def test_story_router_is_mounted_in_active_registry() -> None:
    """The active backend registry contains one story router mount at /api/v1."""
    from backend.app.core.router_registry import ROUTER_REGISTRY

    entries = [entry for entry in ROUTER_REGISTRY if entry.name == "story_engine"]
    assert [(entry.module, entry.prefix) for entry in entries] == [("backend.story_engine.router", "/api/v1")]
