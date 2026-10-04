"""Focused regression tests for Task 5 authentication boundaries."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from backend.auth import AuthUser, require_auth
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

from app.core.auth_policy import PUBLIC_PROBE_ALLOWLIST
from app.core.middleware import AuthMiddleware, OrgIdInjectionGuard
from app.core.security import JWTPayload

TEST_SECRET = "test-jwt-secret-at-least-32-chars-long"


def _token() -> str:
    """Create a locally verifiable test token."""
    return jose_jwt.encode(
        {"sub": "user-1", "exp": 4_102_444_800, "role": "authenticated"},
        TEST_SECRET,
        algorithm="HS256",
    )


def _settings() -> SimpleNamespace:
    """Return settings sufficient for the local authoritative policy."""
    return SimpleNamespace(app_env="local", auth_required=False, auth_dev_mode=False)


def _security_app() -> FastAPI:
    """Build the production middleware order around a sentinel route."""
    app = FastAPI()
    called = {"handler": False}

    @app.get("/protected")
    async def protected(request: Request) -> dict[str, object]:
        called["handler"] = True
        return {"events": request.state.security_events}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.state.handler_called = called
    # Last added middleware is outermost in Starlette.
    app.add_middleware(OrgIdInjectionGuard)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    return app


@pytest.mark.unit
def test_active_app_registers_cors_auth_and_org_guard_in_effective_order() -> None:
    """The active app has CORS outside AuthMiddleware outside the org guard."""
    from backend.app.core.middleware import (
        AuthMiddleware as BackendAuthMiddleware,
    )
    from backend.app.core.middleware import (
        OrgIdInjectionGuard as BackendOrgIdInjectionGuard,
    )
    from backend.main import app

    classes = [middleware.cls for middleware in app.user_middleware]
    assert classes.index(CORSMiddleware) < classes.index(BackendAuthMiddleware)
    assert classes.index(BackendAuthMiddleware) < classes.index(BackendOrgIdInjectionGuard)


@pytest.mark.unit
def test_sentinel_events_prove_auth_precedes_org_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid request reaches the handler only after auth then org checks."""
    app = _security_app()
    monkeypatch.setattr("app.core.middleware.get_settings", _settings)
    monkeypatch.setattr(
        "app.core.security.decode_supabase_jwt",
        lambda _token: JWTPayload(sub="user-1", exp=4_102_444_800, raw={}),
    )

    response = TestClient(app).get("/protected", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 200
    assert response.json()["events"] == ["auth", "org"]
    assert app.state.handler_called["handler"] is True


@pytest.mark.unit
def test_missing_auth_never_invokes_native_or_sentinel_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protected requests fail closed before a handler can run."""
    app = _security_app()
    monkeypatch.setattr("app.core.middleware.get_settings", _settings)

    response = TestClient(app).get("/protected")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert app.state.handler_called["handler"] is False


@pytest.mark.unit
@pytest.mark.parametrize("parameter", ("org_id", "orgId", "org-id", "organization_id"))
def test_org_selector_and_repeated_selector_are_rejected_before_handler(
    monkeypatch: pytest.MonkeyPatch,
    parameter: str,
) -> None:
    """Every client organization spelling, including repeats, returns 422."""
    app = _security_app()
    monkeypatch.setattr("app.core.middleware.get_settings", _settings)
    monkeypatch.setattr(
        "app.core.security.decode_supabase_jwt",
        lambda _token: JWTPayload(sub="user-1", exp=4_102_444_800, raw={}),
    )

    response = TestClient(app).get(
        f"/protected?{parameter}=org-a&{parameter}=org-b",
        headers={"Authorization": f"Bearer {_token()}"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "ORG_ID_INJECTION_REJECTED"
    assert app.state.handler_called["handler"] is False


@pytest.mark.unit
def test_valid_cors_preflight_completes_without_bearer() -> None:
    """CORS handles a valid preflight before authentication can reject it."""
    app = _security_app()
    response = TestClient(app).options(
        "/protected",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.text == "OK"
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


@pytest.mark.unit
def test_public_allowlist_is_exact_and_near_match_is_not_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exact probes are public while a prefix near-match remains protected."""
    assert "/health" in PUBLIC_PROBE_ALLOWLIST
    assert "/healthz" not in PUBLIC_PROBE_ALLOWLIST

    app = _security_app()
    monkeypatch.setattr("app.core.middleware.get_settings", _settings)
    response = TestClient(app).get("/healthz")
    assert response.status_code == 401


@pytest.mark.unit
def test_native_routes_keep_explicit_require_auth_dependency() -> None:
    """The three legacy native routes retain route-level defense in depth."""
    from backend.main import add_talent, projects, talent

    for handler in (projects, talent, add_talent):
        signature = inspect.signature(handler)
        user = signature.parameters["user"]
        assert user.default.dependency is require_auth


@pytest.mark.unit
def test_native_routes_pass_trusted_org_to_database_helpers() -> None:
    """Native handlers pass AuthUser.org_id without accepting client selectors."""
    from backend import main

    user = AuthUser(user_id="user-1", org_id="org-b", role="owner")
    result = SimpleNamespace(data=[{"org_id": "org-b"}])

    with (
        patch.object(main, "get_projects", return_value=result) as projects_mock,
        patch.object(main, "get_talent", return_value=result) as talent_mock,
        patch.object(main, "create_talent", return_value=result) as create_mock,
    ):
        assert main.projects(user) == result.data
        assert main.talent(user) == result.data
        assert main.add_talent({"name": "Nova"}, user) == result.data

    projects_mock.assert_called_once_with("org-b")
    talent_mock.assert_called_once_with("org-b")
    create_mock.assert_called_once_with({"name": "Nova"}, "org-b")


@pytest.mark.unit
def test_missing_native_membership_fails_before_database_access() -> None:
    """Null trusted organization returns the canonical authorization error."""
    from backend import main

    user = AuthUser(user_id="user-1", org_id=None, role="authenticated")
    with (
        patch.object(main, "get_talent") as talent_mock,
        pytest.raises(Exception) as raised,
    ):
        main.talent(user)

    assert raised.value.status_code == 403
    assert raised.value.headers["X-Error-Code"] == "WORKSPACE_MEMBERSHIP_REQUIRED"
    talent_mock.assert_not_called()
