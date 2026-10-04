"""Focused unit/API tests for the Thunder instance watcher."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.auth import require_auth
from backend.infrastructure.authorization import TenantContext, require_infra_admin
from backend.infrastructure.thunder_watch import (
    ThunderWatcher,
    read_recent_job_activity,
    start_thunder_watch_scheduler,
    stop_thunder_watch_scheduler,
)
from backend.infrastructure.thunder_watch_router import router
from backend.membership import OrgRole

pytestmark = pytest.mark.unit

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"


def _settings() -> SimpleNamespace:
    """Return non-secret watcher settings for unit tests."""
    return SimpleNamespace(
        thunder_compute_api_key="test-thunder-token",
        thunder_compute_base_url="https://thunder.test",
        provider_timeout_seconds=2.0,
        thunder_watch_enabled=True,
        thunder_watch_interval_seconds=60,
    )


def _watcher(
    instances: list[dict],
    *,
    active_job: bool = False,
) -> tuple[ThunderWatcher, list[str]]:
    """Build a watcher with an async mock activity reader and transport."""
    deleted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=instances)
        if request.method == "DELETE":
            deleted.append(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(204)
        return httpx.Response(405)

    transport = httpx.MockTransport(handler)

    async def activity_reader(_now: datetime) -> bool:
        return active_job

    return (
        ThunderWatcher(
            _settings(),
            job_activity_reader=activity_reader,
            client_factory=lambda: httpx.AsyncClient(transport=transport),
            clock=lambda: NOW,
        ),
        deleted,
    )


def _instance(instance_id: str, uptime: timedelta, **extra: str) -> dict:
    """Build a Thunder inventory row with a deterministic start time."""
    return {
        "uuid": instance_id,
        "status": "RUNNING",
        "started_at": (NOW - uptime).isoformat(),
        **extra,
    }


async def test_recent_active_job_saves_idle_instance() -> None:
    """Recent queued/started work prevents ordinary idle termination."""
    watcher, deleted = _watcher([_instance("protected", timedelta(hours=2))], active_job=True)

    result = await watcher.run()

    assert result == {"terminated": [], "warned": []}
    assert deleted == []


async def test_idle_instance_is_terminated() -> None:
    """An instance with no recent work and over one hour uptime is deleted."""
    watcher, deleted = _watcher([_instance("idle", timedelta(hours=2))])

    result = await watcher.run()

    assert result == {"terminated": ["idle"], "warned": []}
    assert deleted == ["idle"]


async def test_over_eight_hours_force_terminates_even_with_recent_work() -> None:
    """The hard eight-hour ceiling terminates a leaked instance."""
    watcher, deleted = _watcher(
        [_instance("leaked", timedelta(hours=9))], active_job=True
    )

    result = await watcher.run()

    assert result == {"terminated": ["leaked"], "warned": []}
    assert deleted == ["leaked"]


async def test_over_four_hours_warns_when_recent_work_protects_instance() -> None:
    """A protected instance over four hours is reported but not deleted."""
    watcher, deleted = _watcher(
        [_instance("warm", timedelta(hours=5))], active_job=True
    )

    result = await watcher.run()

    assert result == {"terminated": [], "warned": ["warm"]}
    assert deleted == []


async def test_zero_instances_is_idempotent_noop() -> None:
    """An empty provider inventory returns the exact safe shape."""
    watcher, deleted = _watcher([])

    result = await watcher.run()

    assert result == {"terminated": [], "warned": []}
    assert deleted == []


async def test_activity_from_any_tenant_protects_global_provider_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tenant A activity protects the shared provider from tenant B cleanup."""
    monkeypatch.setattr(
        "backend.infrastructure.thunder_watch._read_active_job_rows",
        lambda: [
            {
                "id": "job-a",
                "org_id": ORG_A,
                "status": "started",
                "started_at": (NOW - timedelta(minutes=10)).isoformat(),
            },
            {
                "id": "job-b-old",
                "org_id": ORG_B,
                "status": "queued",
                "created_at": (NOW - timedelta(hours=2)).isoformat(),
            },
        ],
    )

    assert await read_recent_job_activity(NOW) is True

    watcher, deleted = _watcher([_instance("tenant-b-worker", timedelta(hours=2))])
    watcher._job_activity_reader = lambda _now: read_recent_job_activity(NOW)
    result = await watcher.run()

    assert result == {"terminated": [], "warned": []}
    assert deleted == []


async def test_scheduler_start_is_singleton_and_stops_cleanly() -> None:
    """Repeated startup calls reuse one task and shutdown cancels it cleanly."""
    await stop_thunder_watch_scheduler()
    settings = _settings()

    first = await start_thunder_watch_scheduler(settings, watcher_factory=ThunderWatcher)
    second = await start_thunder_watch_scheduler(settings, watcher_factory=ThunderWatcher)

    assert first is not None
    assert second is first
    assert not first.done()

    await stop_thunder_watch_scheduler()
    assert first.done()


async def test_lifespan_startup_and_shutdown_do_not_crash() -> None:
    """The backend lifespan owns one scheduler start and one graceful stop."""
    with (
        patch("dotenv.load_dotenv"),
        patch.dict(
            os.environ,
            {
                "APP_ENV": "local",
                "OLLAMA_MODEL": "llama3.1:8b",
                "OLLAMA_UNCENSORED_OPT_IN": "false",
            },
            clear=False,
        ),
    ):
        from backend.main import app, lifespan

        start = AsyncMock(return_value=None)
        stop = AsyncMock(return_value=None)
        with (
            patch(
                "backend.infrastructure.thunder_watch.start_thunder_watch_scheduler",
                new=start,
            ),
            patch(
                "backend.infrastructure.thunder_watch.stop_thunder_watch_scheduler",
                new=stop,
            ),
        ):
            async with lifespan(app):
                pass

    start.assert_awaited_once()
    stop.assert_awaited_once()


def _api_client() -> FastAPI:
    """Build an isolated app so API tests do not start the full application."""
    app = FastAPI()
    app.include_router(router)
    return app


def test_api_requires_authentication() -> None:
    """An unauthenticated internal watcher request is rejected with 401."""
    app = _api_client()

    def unauthorized() -> TenantContext:
        raise HTTPException(status_code=401, detail="Authentication required")

    app.dependency_overrides[require_auth] = unauthorized
    with TestClient(app) as client:
        response = client.post("/api/v1/internal/thunder-watch")

    assert response.status_code == 401


def test_api_rejects_non_admin() -> None:
    """A viewer cannot invoke the destructive admin watcher."""
    app = _api_client()

    def forbidden() -> TenantContext:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    app.dependency_overrides[require_infra_admin] = forbidden
    with TestClient(app) as client:
        response = client.post("/api/v1/internal/thunder-watch")

    assert response.status_code == 403


def test_api_returns_exact_safe_response_for_admin() -> None:
    """An admin receives only terminated and warned arrays."""
    app = _api_client()
    app.dependency_overrides[require_infra_admin] = lambda: TenantContext(
        user_id="user-a",
        org_id=ORG_A,
        role=OrgRole.ADMIN,
    )
    with (
        patch(
            "backend.infrastructure.thunder_watch_router.ThunderWatcher.run",
            new=AsyncMock(return_value={"terminated": ["idle"], "warned": ["warm"]}),
        ),
        patch(
            "backend.infrastructure.thunder_watch_router.get_settings",
            return_value=_settings(),
        ),
        TestClient(app) as client,
    ):
        response = client.post("/api/v1/internal/thunder-watch")

    assert response.status_code == 200
    assert response.json() == {"terminated": ["idle"], "warned": ["warm"]}
    assert set(response.json()) == {"terminated", "warned"}
