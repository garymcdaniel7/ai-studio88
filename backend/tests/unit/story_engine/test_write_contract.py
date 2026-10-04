"""Focused unit tests for the Phase 2 WRITE backend contract."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from backend.auth import AuthUser, require_auth
from backend.generation_jobs import GenerationJob, GenerationState
from backend.story_engine.repository import StoryNotFoundError, StoryRepository
from backend.story_engine.router import get_story_service, router
from backend.story_engine.schemas import ShotPreviewRequest
from backend.story_engine.service import StoryService
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
SHOT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
PREVIOUS_SHOT_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
ASSET_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CHARACTER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
NOW = datetime.now(UTC).isoformat()


def _shot(org_id: str = ORG_A) -> dict:
    """Return a response-compatible shot row."""
    return {
        "id": SHOT_ID,
        "org_id": org_id,
        "scene_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "shot_number": 1,
        "shot_type": "medium",
        "description": "### Subject\nA rooftop subject",
        "characters": [],
        "duration_seconds": 3.0,
        "transition": "cut",
        "generation_params": {"frame_grid": 226},
        "status": "planned",
        "asset_id": None,
        "job_id": None,
        "metadata": {},
        "created_at": NOW,
        "updated_at": NOW,
    }


def _app(user: AuthUser, service: MagicMock) -> FastAPI:
    """Build an isolated authenticated story app."""
    from backend.app.core.error_handlers import register_error_handlers

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    register_error_handlers(app)
    app.dependency_overrides[require_auth] = lambda: user
    app.dependency_overrides[get_story_service] = lambda: service
    return app


def _preview_body(**overrides: object) -> dict:
    """Return the exact preview request shape used by WRITE."""
    body: dict[str, object] = {
        "prompt": "### Subject\nA person on a rooftop",
        "negative_prompt": "blurred",
        "quality": "preview",
        "steps": 4,
        "height": 480,
        "frame_grid": 226,
        "seed": 9876,
        "previous_shot_id": PREVIOUS_SHOT_ID,
        "character_ids": [CHARACTER_ID],
        "location": "Rooftop",
        "continuity": "Keep wardrobe and screen direction.",
        "reference_asset_ids": [ASSET_ID],
        "workflow_id": "workflow-preview",
        "model_id": "h3-preview",
    }
    body.update(overrides)
    return body


@pytest.fixture
def write_service() -> MagicMock:
    """Return a service double for route-level contract tests."""
    service = MagicMock(spec=StoryService)
    service.update_shot_write.return_value = _shot()
    service.generate_shot_preview.return_value = {
        "shot_id": SHOT_ID,
        "job_id": "gen-preview-1",
        "status": "queued",
        "workflow_id": "workflow-preview",
        "model_id": "h3-preview",
        "seed": 9876,
        "estimated_cost_usd": 0.0,
        "generation_result": {"job_id": "gen-preview-1", "status": "queued"},
    }
    return service


@pytest.mark.unit
def test_write_update_passes_trusted_org_for_tenant_a_and_b(write_service: MagicMock) -> None:
    """The compatibility update cannot select an organization from its body."""
    body = {
        "description": "Updated prompt",
        "generation_params": {"frame_grid": 226},
        "metadata": {"reference_asset_ids": [ASSET_ID], "continuity": "Match shot one."},
    }
    client_a = TestClient(_app(AuthUser(user_id="user-a", org_id=ORG_A, role="editor"), write_service))
    client_b = TestClient(_app(AuthUser(user_id="user-b", org_id=ORG_B, role="editor"), write_service))

    assert client_a.put(f"/api/v1/shots/{SHOT_ID}", json=body).status_code == 200
    assert client_b.put(f"/api/v1/shots/{SHOT_ID}", json=body).status_code == 200
    assert write_service.update_shot_write.call_args_list[0].args[2] == ORG_A
    assert write_service.update_shot_write.call_args_list[1].args[2] == ORG_B


@pytest.mark.unit
def test_foreign_shot_update_returns_404_without_existence_leak(write_service: MagicMock) -> None:
    """A foreign shot is denied as not found and the service receives org B only."""
    write_service.update_shot_write.side_effect = StoryNotFoundError("foreign")
    client = TestClient(_app(AuthUser(user_id="user-b", org_id=ORG_B, role="editor"), write_service))

    response = client.put(f"/api/v1/shots/{SHOT_ID}", json={"description": "no access"})

    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"
    assert "foreign" not in response.text
    assert write_service.update_shot_write.call_args.args[2] == ORG_B


@pytest.mark.unit
def test_preview_contract_preserves_exact_request_and_tenant(write_service: MagicMock) -> None:
    """Preview requests retain H3 settings, references, context, and trusted org."""
    client_a = TestClient(_app(AuthUser(user_id="user-a", org_id=ORG_A, role="editor"), write_service))
    client_b = TestClient(_app(AuthUser(user_id="user-b", org_id=ORG_B, role="editor"), write_service))

    response_a = client_a.post(f"/api/v1/shots/{SHOT_ID}/generate", json=_preview_body())
    response_b = client_b.post(f"/api/v1/shots/{SHOT_ID}/generate", json=_preview_body(seed=9877))

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert response_a.json()["status"] == "queued"
    request = write_service.generate_shot_preview.call_args_list[0].args[1]
    assert request.quality == "preview"
    assert request.steps == 4
    assert request.height == 480
    assert request.frame_grid == 226
    assert request.seed == 9876
    assert str(request.previous_shot_id) == PREVIOUS_SHOT_ID
    assert [str(value) for value in request.reference_asset_ids] == [ASSET_ID]
    assert write_service.generate_shot_preview.call_args_list[0].args[2:] == (ORG_A, "user-a")
    assert write_service.generate_shot_preview.call_args_list[1].args[2:] == (ORG_B, "user-b")


@pytest.mark.unit
@pytest.mark.parametrize("frame_grid", [0, 216, 280, 601, 226.0, "226"])
def test_preview_rejects_non_exact_h3_frame_grid(write_service: MagicMock, frame_grid: object) -> None:
    """Only the exact H3 frame grid is accepted at the API boundary."""
    client = TestClient(_app(AuthUser(user_id="user-a", org_id=ORG_A, role="editor"), write_service))

    response = client.post(
        f"/api/v1/shots/{SHOT_ID}/generate",
        json=_preview_body(frame_grid=frame_grid),
    )

    assert response.status_code == 422
    write_service.generate_shot_preview.assert_not_called()


@pytest.mark.unit
def test_missing_auth_and_invalid_preview_body_fail_before_service(write_service: MagicMock) -> None:
    """Authentication and typed body validation happen before preview dispatch."""
    def reject() -> AuthUser:
        raise HTTPException(status_code=401, detail="Authentication required")

    app = _app(AuthUser(user_id="unused", org_id=ORG_A), write_service)
    app.dependency_overrides[require_auth] = reject
    unauthenticated = TestClient(app)
    assert unauthenticated.post(f"/api/v1/shots/{SHOT_ID}/generate", json={}).status_code == 401

    authenticated = TestClient(_app(AuthUser(user_id="user-a", org_id=ORG_A, role="editor"), write_service))
    invalid = authenticated.post(
        f"/api/v1/shots/{SHOT_ID}/generate",
        json=_preview_body(steps=5),
    )
    assert invalid.status_code == 422
    write_service.generate_shot_preview.assert_not_called()


@pytest.mark.unit
def test_foreign_reference_is_denied_before_preview_queue(write_service: MagicMock) -> None:
    """A reference rejected by tenant validation never reaches generation."""
    write_service.generate_shot_preview.side_effect = StoryNotFoundError("foreign asset")
    client = TestClient(_app(AuthUser(user_id="user-a", org_id=ORG_A, role="editor"), write_service))

    response = client.post(
        f"/api/v1/shots/{SHOT_ID}/generate",
        json=_preview_body(reference_asset_ids=[ASSET_ID]),
    )

    assert response.status_code == 404
    write_service.generate_shot_preview.assert_called_once()


@pytest.mark.unit
def test_preview_service_records_async_provenance_and_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    """The service queues work and records the exact effective preview context."""
    repository = MagicMock(spec=StoryRepository)
    captured: dict[str, object] = {}
    submitted: list[GenerationJob] = []

    def submit(**kwargs: object) -> GenerationJob:
        captured.update(kwargs)
        job = GenerationJob(
            id="gen-preview-2",
            org_id=ORG_A,
            user_id="user-a",
            session_id="",
            prompt=str(kwargs["prompt"]),
            state=GenerationState.QUEUED,
        )
        submitted.append(job)
        return job

    monkeypatch.setattr("backend.story_engine.service.submit_generation", submit)
    service = StoryService(repository)
    request = ShotPreviewRequest.model_validate(_preview_body())

    result = service.generate_shot_preview(SHOT_ID, request, ORG_A, "user-a")

    assert result["status"] == "queued"
    assert captured["estimated_cost_usd"] == 0.0
    assert captured["height"] == 480
    assert captured["steps"] == 4
    assert service.repository.validate_preview_context.call_args.args[2] == ORG_A
    assert submitted[0].effective_settings["frame_grid"] == 226
    assert submitted[0].effective_settings["reference_asset_ids"] == [ASSET_ID]
    assert submitted[0].effective_settings["workflow_id"] == "workflow-preview"


@pytest.mark.unit
def test_repository_reference_query_is_org_scoped() -> None:
    """Reference validation binds org_id and rejects incomplete ownership results."""
    class Query:
        def __init__(self) -> None:
            self.filters: list[tuple[str, object]] = []

        def select(self, *_fields: str) -> Query:
            return self

        def eq(self, key: str, value: object) -> Query:
            self.filters.append((key, value))
            return self

        def in_(self, key: str, values: list[str]) -> Query:
            self.filters.append((key, values))
            return self

        def execute(self) -> object:
            return type("Result", (), {"data": [{"id": ASSET_ID}]})()

    query = Query()
    database = __import__("backend.database", fromlist=["supabase"])
    original = getattr(database, "supabase", None)
    database.supabase = type("Client", (), {"table": lambda _self, _name: query})()
    try:
        with pytest.raises(StoryNotFoundError):
            StoryRepository()._validate_owned_ids("assets", [ASSET_ID, "99999999-9999-9999-9999-999999999999"], ORG_A)
    finally:
        database.supabase = original
    assert ("org_id", ORG_A) in query.filters
