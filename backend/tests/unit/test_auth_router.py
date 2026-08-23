"""Unit tests for the public Supabase Auth route surface."""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth_router import router


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build an isolated app with configured public Supabase Auth settings."""
    settings = SimpleNamespace(
        supabase_url="https://project.supabase.co",
        supabase_anon_key="public-anon-key",
        auth_frontend_url="https://frontend.example.com",
    )
    monkeypatch.setattr("backend.auth_router.get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.unit
class TestSupabaseAuthRoutes:
    """Verify the public OAuth route contract without external I/O."""

    def test_google_login_redirects_to_supabase_authorize(self, auth_client: TestClient) -> None:
        """Google login points to Supabase and the frontend callback."""
        response = auth_client.get(
            "/auth/google",
            params={"next": "/create"},
            follow_redirects=False,
        )

        assert response.status_code == 307
        location = urlsplit(response.headers["location"])
        assert location.netloc == "project.supabase.co"
        assert location.path == "/auth/v1/authorize"
        query = parse_qs(location.query)
        assert query["provider"] == ["google"]
        assert query["redirect_to"] == [
            "https://frontend.example.com/auth/callback?next=%2Fcreate"
        ]

    def test_login_alias_resolves_to_google_flow(self, auth_client: TestClient) -> None:
        """The documented login route is an alias for Google initiation."""
        response = auth_client.get("/auth/login", follow_redirects=False)

        assert response.status_code == 307
        assert "provider=google" in response.headers["location"]

    def test_external_next_target_is_rejected(self, auth_client: TestClient) -> None:
        """OAuth initiation cannot be used as an open redirect."""
        response = auth_client.get(
            "/auth/google",
            params={"next": "https://attacker.example/steal"},
            follow_redirects=False,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "INVALID_REDIRECT_TARGET"

    def test_callback_forwards_code_to_frontend_callback(self, auth_client: TestClient) -> None:
        """The backend callback proxy preserves only OAuth callback parameters."""
        response = auth_client.get(
            "/auth/callback",
            params={"code": "one-time-code", "state": "state-value", "next": "/create"},
            follow_redirects=False,
        )

        assert response.status_code == 307
        location = urlsplit(response.headers["location"])
        assert location.hostname == "frontend.example.com"
        assert location.path == "/auth/callback"
        assert parse_qs(location.query) == {
            "code": ["one-time-code"],
            "state": ["state-value"],
            "next": ["/create"],
        }

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_logout_resolves_to_frontend_logout_route(
        self,
        auth_client: TestClient,
        method: str,
    ) -> None:
        """Both logout methods delegate session clearing to the frontend."""
        response = getattr(auth_client, method)("/auth/logout", follow_redirects=False)

        assert response.status_code == 307
        assert response.headers["location"] == "https://frontend.example.com/auth/logout"

    def test_routes_fail_closed_when_supabase_is_not_configured(
        self,
        auth_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A route exists but never emits an unusable OAuth redirect."""
        monkeypatch.setattr(
            "backend.auth_router.get_settings",
            lambda: SimpleNamespace(
                supabase_url="",
                supabase_anon_key="",
                auth_frontend_url="https://frontend.example.com",
            ),
        )

        response = auth_client.get("/auth/google", follow_redirects=False)

        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "AUTH_CONFIGURATION_MISSING"

    def test_routes_fail_closed_when_frontend_origin_is_missing(
        self,
        auth_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The callback target must be explicitly configured."""
        monkeypatch.setattr(
            "backend.auth_router.get_settings",
            lambda: SimpleNamespace(
                supabase_url="https://project.supabase.co",
                supabase_anon_key="public-anon-key",
                auth_frontend_url="",
            ),
        )

        response = auth_client.get("/auth/google", follow_redirects=False)

        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "AUTH_CONFIGURATION_MISSING"


@pytest.mark.unit
def test_auth_settings_default_to_enforced_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """An omitted AUTH_DEV_MODE flag cannot silently enable auth bypass."""
    from app.core.config import Settings

    monkeypatch.delenv("AUTH_DEV_MODE", raising=False)
    settings = Settings(_env_file=None)

    assert settings.auth_dev_mode is False


@pytest.mark.unit
def test_readiness_reports_jwt_auth_ready_without_dev_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness treats configured JWT auth as ready when bypass is off."""
    from app.core.capability_readiness import CapState, check_auth

    monkeypatch.delenv("AUTH_DEV_MODE", raising=False)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret-at-least-32-chars-long")

    result = check_auth()

    assert result.state == CapState.READY
    assert result.evidence == {"secret_length": 38}
