"""Focused unit coverage for the authoritative authentication boundary.

The tests in this module exercise policy, middleware, and dependency branches
without contacting Supabase, external APIs, or production services.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt
from starlette.requests import Request as StarletteRequest
from starlette.responses import PlainTextResponse

from app.core.auth_policy import PUBLIC_PROBE_ALLOWLIST, AuthPolicy
from app.core.middleware import (
    AuthMiddleware,
    OrgIdInjectionGuard,
    RequestIdMiddleware,
    _load_dev_payload,
)
from app.core.security import ExpiredTokenError, InvalidTokenError, JWTPayload

TEST_SECRET = "test-jwt-secret-at-least-32-chars-long"


def _settings(**overrides: object) -> SimpleNamespace:
    """Build settings with safe local defaults for middleware tests."""
    values: dict[str, object] = {
        "app_env": "local",
        "auth_required": False,
        "auth_dev_mode": False,
        "auth_enforcement_flip": False,
        "auth_dark_launch": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _request(path: str = "/protected", method: str = "GET", headers: list[tuple[bytes, bytes]] | None = None) -> StarletteRequest:
    """Build a minimal request for direct dependency tests."""
    return StarletteRequest(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers or [],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
        }
    )


def _middleware_app() -> FastAPI:
    """Create a tiny app whose handler exposes middleware state."""
    app = FastAPI()
    app.add_middleware(OrgIdInjectionGuard)
    app.add_middleware(AuthMiddleware)

    @app.get("/protected")
    async def protected(request: Request) -> dict[str, object]:
        payload = getattr(request.state, "jwt_payload", None)
        return {
            "events": request.state.security_events,
            "sub": payload.sub if payload else None,
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _request_id_app() -> FastAPI:
    """Create an app for request-id header normalization tests."""
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/request-id")
    async def request_id(request: Request) -> dict[str, str]:
        return {"request_id": request.state.request_id}

    return app


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    ((True, True), (False, False), ("yes", True), ("ON", True), ("0", False), ("other", False), (1, False)),
)
def test_auth_policy_setting_bool_is_strict(value: object, expected: bool) -> None:
    """Boolean settings accept explicit strings but not truthy test doubles."""
    policy = AuthPolicy.from_settings(_settings(auth_dev_mode=value))
    assert policy.auth_dev_mode is expected


@pytest.mark.unit
def test_auth_policy_override_and_exact_public_method_matrix() -> None:
    """The override is honored and only exact paths or OPTIONS are public."""
    policy = AuthPolicy.from_settings(_settings(auth_dev_mode=False), auth_dev_mode_override=True)
    assert policy.auth_dev_mode
    assert policy.is_public("/health", "GET")
    assert policy.is_public("/not-listed", "OPTIONS")
    assert not policy.is_public("/healthz", "GET")
    assert not policy.is_public("/auth/callback/extra", "POST")
    assert PUBLIC_PROBE_ALLOWLIST.isdisjoint({"/healthz", "/readyz"})


@pytest.mark.unit
@pytest.mark.parametrize(
    ("app_env", "auth_dev_mode", "flip", "dark", "allows", "observes", "enforces"),
    (
        ("local", True, False, False, True, False, False),
        ("test", True, False, False, True, False, False),
        ("development", True, False, False, True, False, False),
        ("local", False, False, True, False, True, False),
        ("local", False, True, True, False, False, True),
        ("local", False, False, False, False, False, True),
        ("staging", False, True, False, False, False, True),
        ("production", True, True, False, False, False, True),
    ),
)
def test_auth_policy_environment_matrix(
    app_env: str,
    auth_dev_mode: bool,
    flip: bool,
    dark: bool,
    allows: bool,
    observes: bool,
    enforces: bool,
) -> None:
    """Local fallback, dark launch, and protected environments remain distinct."""
    policy = AuthPolicy.from_settings(
        _settings(
            app_env=app_env,
            auth_dev_mode=auth_dev_mode,
            auth_enforcement_flip=flip,
            auth_dark_launch=dark,
        )
    )
    assert policy.allows_dev_fallback is allows
    assert policy.observes_only is observes
    assert policy.enforces_authentication is enforces


@pytest.mark.unit
@pytest.mark.parametrize(
    ("settings", "message"),
    (
        (_settings(app_env="staging", auth_required=False, auth_enforcement_flip=True), "AUTH_REQUIRED"),
        (_settings(app_env="production", auth_required=True, auth_enforcement_flip=False), "AUTH_ENFORCEMENT_FLIP"),
        (_settings(app_env="staging", auth_required=True, auth_enforcement_flip=True, auth_dev_mode=True), "AUTH_DEV_MODE"),
        (_settings(app_env="production", auth_required=True, auth_enforcement_flip=True, auth_dark_launch=True), "AUTH_DARK_LAUNCH"),
    ),
)
def test_auth_policy_startup_rejects_each_unsafe_protected_combination(
    settings: SimpleNamespace, message: str
) -> None:
    """Every protected startup misconfiguration fails closed with a useful reason."""
    with pytest.raises(RuntimeError, match=message):
        AuthPolicy.from_settings(settings).validate_startup()


@pytest.mark.unit
def test_auth_policy_valid_protected_startup_and_telemetry_exclude_secrets() -> None:
    """Valid protected startup succeeds and telemetry contains no bearer material."""
    policy = AuthPolicy.from_settings(
        _settings(app_env="production", auth_required=True, auth_enforcement_flip=True)
    )
    policy.validate_startup()
    with patch("app.core.auth_policy.logger.info") as info:
        policy.telemetry(
            outcome="authenticated",
            path="/protected",
            method="GET",
            request_id="request-id",
        )
    fields = info.call_args.kwargs
    assert fields["outcome"] == "authenticated"
    assert "authorization" not in fields
    assert "token" not in str(fields).lower()
    assert "org_id" not in fields


@pytest.mark.unit
def test_org_guard_public_safe_and_injection_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard preserves public/no-selector requests and rejects selectors."""
    app = FastAPI()
    app.add_middleware(OrgIdInjectionGuard)

    @app.get("/probe")
    async def probe() -> PlainTextResponse:
        return PlainTextResponse("ok")

    @app.get("/protected")
    async def protected(request: Request) -> dict[str, object]:
        return {"events": request.state.security_events}

    monkeypatch.setattr("app.core.middleware.get_settings", lambda: _settings())
    client = TestClient(app)
    assert client.get("/probe").status_code == 200
    assert client.get("/protected?status=ready").json() == {"events": ["org"]}
    response = client.get("/protected?org_id=attacker")
    assert response.status_code == 422
    assert response.json()["code"] == "ORG_ID_INJECTION_REJECTED"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "method", "expected_status"),
    (("/health", "GET", 200), ("/protected", "OPTIONS", 405)),
)
def test_auth_middleware_public_and_preflight_paths(
    monkeypatch: pytest.MonkeyPatch, path: str, method: str, expected_status: int
) -> None:
    """Exact public probes and all OPTIONS requests bypass bearer rejection."""
    monkeypatch.setattr("app.core.middleware.get_settings", lambda: _settings())
    response = TestClient(_middleware_app()).request(method, path)
    assert response.status_code == expected_status
    assert response.status_code != 401


@pytest.mark.unit
def test_auth_middleware_rejects_missing_auth_and_handles_dev_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Strict local mode rejects missing auth; approved fallback can proceed."""
    monkeypatch.setattr("app.core.middleware.get_settings", lambda: _settings())
    strict = TestClient(_middleware_app()).get("/protected")
    assert strict.status_code == 401
    assert strict.json() == {"detail": "Authentication required", "code": "UNAUTHORIZED"}

    monkeypatch.setattr(
        "app.core.middleware.get_settings",
        lambda: _settings(auth_dev_mode=True),
    )
    monkeypatch.setattr(
        "app.core.middleware._load_dev_payload",
        lambda: JWTPayload(sub="dev-user", exp=4_102_444_800, raw={}),
    )
    fallback = TestClient(_middleware_app()).get("/protected")
    assert fallback.status_code == 200
    assert fallback.json()["sub"] == "dev-user"


@pytest.mark.unit
def test_auth_middleware_fallback_without_member_falls_through_to_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty dev fallback does not silently create anonymous access."""
    monkeypatch.setattr(
        "app.core.middleware.get_settings", lambda: _settings(auth_dev_mode=True)
    )
    monkeypatch.setattr("app.core.middleware._load_dev_payload", lambda: None)
    response = TestClient(_middleware_app()).get("/protected")
    assert response.status_code == 401


@pytest.mark.unit
def test_auth_middleware_handles_valid_expired_and_invalid_bearers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bearer success and both stable rejection mappings are covered."""
    monkeypatch.setattr("app.core.middleware.get_settings", lambda: _settings())
    decode = MagicMock(return_value=JWTPayload(sub="user-1", exp=4_102_444_800, raw={}))
    monkeypatch.setattr("app.core.security.decode_supabase_jwt", decode)
    valid = TestClient(_middleware_app()).get(
        "/protected", headers={"Authorization": "Bearer valid-token"}
    )
    assert valid.status_code == 200
    decode.assert_called_once_with("valid-token")

    decode.side_effect = ExpiredTokenError()
    expired = TestClient(_middleware_app()).get(
        "/protected", headers={"Authorization": "Bearer expired-token"}
    )
    assert expired.status_code == 401
    assert expired.json()["code"] == "TOKEN_EXPIRED"

    decode.side_effect = InvalidTokenError("Token missing or empty sub claim")
    invalid_claims = TestClient(_middleware_app()).get(
        "/protected", headers={"Authorization": "Bearer invalid-token"}
    )
    assert invalid_claims.status_code == 401
    assert invalid_claims.json()["code"] == "INVALID_TOKEN"

    decode.side_effect = InvalidTokenError("Invalid token")
    invalid = TestClient(_middleware_app()).get(
        "/protected", headers={"Authorization": "Bearer invalid-token"}
    )
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "UNAUTHORIZED"


@pytest.mark.unit
def test_auth_middleware_dark_launch_observes_failures_without_rejecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Controlled local dark launch observes missing and invalid auth only."""
    monkeypatch.setattr(
        "app.core.middleware.get_settings",
        lambda: _settings(auth_dark_launch=True),
    )
    missing = TestClient(_middleware_app()).get("/protected")
    assert missing.status_code == 200

    monkeypatch.setattr(
        "app.core.security.decode_supabase_jwt",
        MagicMock(side_effect=InvalidTokenError("Invalid token")),
    )
    invalid = TestClient(_middleware_app()).get(
        "/protected", headers={"Authorization": "Bearer invalid-token"}
    )
    assert invalid.status_code == 200

    monkeypatch.setattr(
        "app.core.security.decode_supabase_jwt",
        MagicMock(side_effect=ExpiredTokenError()),
    )
    expired = TestClient(_middleware_app()).get(
        "/protected", headers={"Authorization": "Bearer expired-token"}
    )
    assert expired.status_code == 200


@pytest.mark.unit
def test_auth_middleware_exception_returns_structured_internal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected policy failures do not leak internals or continue the request."""
    monkeypatch.setattr(
        "app.core.middleware.get_auth_policy",
        MagicMock(side_effect=RuntimeError("secret policy detail")),
    )
    response = TestClient(_middleware_app()).get("/protected")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error", "code": "INTERNAL_ERROR"}
    assert "secret policy detail" not in response.text


@pytest.mark.unit
def test_load_dev_payload_covers_unconfigured_empty_and_valid_member_paths() -> None:
    """Development payload lookup is fail-closed and uses member identity."""
    with patch("backend.database.is_supabase_configured", return_value=False):
        assert _load_dev_payload() is None

    result = SimpleNamespace(data=[])
    client = MagicMock()
    chain = client.table.return_value
    chain.select.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = result
    with (
        patch("backend.database.is_supabase_configured", return_value=True),
        patch("backend.database.get_supabase_client", return_value=client),
    ):
        assert _load_dev_payload() is None

    chain.execute.return_value = SimpleNamespace(
        data=[{"user_id": "member-1", "org_id": "org-1", "role": "owner"}]
    )
    with (
        patch("backend.database.is_supabase_configured", return_value=True),
        patch("backend.database.get_supabase_client", return_value=client),
    ):
        payload = _load_dev_payload()
    assert payload is not None
    assert payload.sub == "member-1"
    assert payload.raw["app_metadata"]["org_id"] == "org-1"


@pytest.mark.unit
def test_load_dev_payload_logs_failure_without_secret_details() -> None:
    """Lookup exceptions are contained and do not become client-visible secrets."""
    with (
        patch("backend.database.is_supabase_configured", side_effect=RuntimeError("secret")),
        patch("app.core.middleware.logger.exception") as log,
    ):
        assert _load_dev_payload() is None
    log.assert_called_once_with("dev_auth_member_lookup_failed")


@pytest.mark.unit
@pytest.mark.parametrize("header", (None, "not-a-uuid"))
def test_request_id_middleware_generates_valid_ids_for_missing_or_invalid_headers(
    header: str | None,
) -> None:
    """Request IDs are always valid UUIDs when clients omit or corrupt them."""
    headers = {"X-Request-ID": header} if header is not None else {}
    response = TestClient(_request_id_app()).get("/request-id", headers=headers)
    request_id = response.headers["X-Request-ID"]
    assert response.json()["request_id"] == request_id
    assert len(request_id) == 36


@pytest.mark.unit
def test_request_id_middleware_preserves_valid_client_uuid() -> None:
    """A valid client correlation UUID is propagated unchanged."""
    request_id = "12345678-1234-4234-8234-123456789abc"
    response = TestClient(_request_id_app()).get(
        "/request-id", headers={"X-Request-ID": request_id}
    )
    assert response.headers["X-Request-ID"] == request_id


@pytest.mark.unit
def test_decode_token_failures_and_es256_key_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy secret, ES256 JWKS, expiry, and malformed-token branches are covered."""
    import backend.auth as auth

    monkeypatch.setattr(auth, "_JWT_SECRET", "")
    with pytest.raises(Exception) as missing_secret:
        auth._decode_token("token")
    assert missing_secret.value.status_code == 500

    monkeypatch.setattr(auth, "_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr(auth.jwt, "get_unverified_header", lambda _token: {"alg": "ES256", "kid": "kid-1"})
    monkeypatch.setattr(auth, "_get_supabase_jwks_key", lambda _token: None)
    with pytest.raises(Exception) as no_key:
        auth._decode_token("token")
    assert no_key.value.status_code == 503

    monkeypatch.setattr(auth, "_get_supabase_jwks_key", lambda _token: "public-key")
    monkeypatch.setattr(auth.jwt, "decode", lambda *_args, **_kwargs: {"sub": "u"})
    assert auth._decode_token("token") == {"sub": "u"}

    monkeypatch.setattr(auth.jwt, "get_unverified_header", lambda _token: {"alg": "HS256"})
    monkeypatch.setattr(auth.jwt, "decode", lambda *_args, **_kwargs: {"sub": "u"})
    monkeypatch.setattr(auth.jwt, "get_unverified_header", MagicMock(side_effect=ValueError("malformed header")))
    assert auth._decode_token("header-fallback") == {"sub": "u"}

    monkeypatch.setattr(auth.jwt, "get_unverified_header", lambda _token: {"alg": "HS256"})
    monkeypatch.setattr(auth.jwt, "decode", MagicMock(side_effect=auth.jwt.ExpiredSignatureError()))
    with pytest.raises(Exception) as expired:
        auth._decode_token("token")
    assert expired.value.status_code == 401

    monkeypatch.setattr(auth.jwt, "decode", MagicMock(side_effect=auth.jwt.InvalidTokenError("bad")))
    with pytest.raises(Exception) as invalid:
        auth._decode_token("token")
    assert invalid.value.status_code == 401


@pytest.mark.unit
def test_jwks_lookup_covers_cache_missing_url_success_and_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JWKS lookup caches keyed results and fails closed on provider errors."""
    import backend.auth as auth

    auth._jwks_key_cache.clear()
    monkeypatch.setattr(auth.jwt, "get_unverified_header", lambda _token: {"kid": "cached"})
    auth._jwks_key_cache["cached"] = "cached-key"
    assert auth._get_supabase_jwks_key("token") == "cached-key"

    auth._jwks_key_cache.clear()
    monkeypatch.setattr(auth.os, "getenv", lambda _name, default="": default)
    assert auth._get_supabase_jwks_key("no-url") is None

    class FakeJWKClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def get_signing_key_from_jwt(self, *, token: str) -> SimpleNamespace:
            assert token == "remote-token"
            return SimpleNamespace(key="remote-key")

    monkeypatch.setattr(auth.os, "getenv", lambda name, default="": "https://supabase.test" if name == "SUPABASE_URL" else default)
    monkeypatch.setattr(auth.jwt, "get_unverified_header", lambda _token: {"kid": "remote"})
    monkeypatch.setattr(auth.jwt, "PyJWKClient", FakeJWKClient)
    assert auth._get_supabase_jwks_key("remote-token") == "remote-key"
    assert auth._jwks_key_cache["remote"] == "remote-key"

    class BrokenJWKClient(FakeJWKClient):
        def get_signing_key_from_jwt(self, *, token: str) -> SimpleNamespace:
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(auth.jwt, "PyJWKClient", BrokenJWKClient)
    monkeypatch.setattr(auth.jwt, "get_unverified_header", lambda _token: {"kid": "broken"})
    with patch("backend.auth.logger.warning") as warning:
        assert auth._get_supabase_jwks_key("broken-token") is None
    warning.assert_called_once()


@pytest.mark.unit
def test_jwks_lookup_handles_missing_kid_without_caching(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid provider key without a key id remains usable but is not cached."""
    import backend.auth as auth

    auth._jwks_key_cache.clear()
    monkeypatch.setattr(auth.os, "getenv", lambda name, default="": "https://supabase.test" if name == "SUPABASE_URL" else default)
    monkeypatch.setattr(auth.jwt, "get_unverified_header", lambda _token: {})

    class NoKidJWKClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def get_signing_key_from_jwt(self, *, token: str) -> SimpleNamespace:
            return SimpleNamespace(key="no-kid-key")

    monkeypatch.setattr(auth.jwt, "PyJWKClient", NoKidJWKClient)
    assert auth._get_supabase_jwks_key("no-kid-token") == "no-kid-key"
    assert auth._jwks_key_cache == {}


@pytest.mark.unit
def test_extract_user_membership_provisioning_and_null_context_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Membership success, provisioning, fallback hint, and no-context paths are covered."""
    import backend.auth as auth
    from backend.membership import MembershipError

    success_context = SimpleNamespace(org_id="org-a", role=SimpleNamespace(value="editor"))
    monkeypatch.setattr("backend.membership.resolve_membership", lambda *_args, **_kwargs: success_context)
    user = auth._extract_user({"sub": "user-1", "email": "u@example.com", "app_metadata": {"org_id": "org-a"}})
    assert user.org_id == "org-a"
    assert user.role == "editor"

    monkeypatch.setattr(
        "backend.membership.resolve_membership",
        MagicMock(side_effect=MembershipError("missing")),
    )
    provisioned = SimpleNamespace(
        org_id="org-provisioned",
        tenant_context=SimpleNamespace(role=SimpleNamespace(value="owner")),
    )
    service = MagicMock()
    service.provision_workspace_sync.return_value = provisioned
    import backend.app.services.provisioning_service as provisioning_service

    monkeypatch.setattr(provisioning_service, "ProvisioningService", lambda: service)
    valid_user_id = "12345678-1234-4234-8234-123456789abc"
    user = auth._extract_user({"sub": valid_user_id, "email": "u@example.com"})
    assert user.org_id == "org-provisioned"
    assert user.role == "owner"

    service.provision_workspace_sync.side_effect = RuntimeError("provisioning unavailable")
    user = auth._extract_user(
        {"sub": valid_user_id, "app_metadata": {"org_id": "org-hint-123456"}}
    )
    assert user.org_id == "org-hint-123456"

    user = auth._extract_user({"sub": valid_user_id, "app_metadata": {"org_id": "tiny"}})
    assert user.org_id is None

    monkeypatch.setattr(
        "backend.membership.resolve_membership",
        MagicMock(side_effect=RuntimeError("membership unavailable")),
    )
    no_hint = auth._extract_user({"sub": valid_user_id})
    assert no_hint.org_id is None


@pytest.mark.unit
def test_require_and_optional_auth_cover_valid_null_invalid_and_fallback_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route dependencies reject null membership and preserve optional semantics."""
    import backend.auth as auth

    request = _request(headers=[(b"authorization", b"Bearer token")])
    monkeypatch.setattr(auth, "_decode_token", lambda _token: {"sub": "user"})
    monkeypatch.setattr(auth, "_extract_user", lambda _payload: auth.AuthUser("user", org_id="org-a"))
    assert auth.require_auth(request).org_id == "org-a"
    assert auth.optional_auth(request).org_id == "org-a"

    monkeypatch.setattr(auth, "_extract_user", lambda _payload: auth.AuthUser("user", org_id=None))
    with pytest.raises(Exception) as denied:
        auth.require_auth(request)
    assert denied.value.status_code == 403
    assert denied.value.headers["X-Error-Code"] == "WORKSPACE_MEMBERSHIP_REQUIRED"
    assert auth.optional_auth(request) is None

    monkeypatch.setattr(auth, "_decode_token", MagicMock(side_effect=auth.HTTPException(status_code=401)))
    with pytest.raises(Exception) as invalid:
        auth.require_auth(request)
    assert invalid.value.status_code == 401
    assert auth.optional_auth(request) is None

    no_auth = _request()
    monkeypatch.setattr(
        auth,
        "_authoritative_policy",
        lambda: AuthPolicy.from_settings(_settings(auth_dev_mode=True)),
    )
    fallback = auth.require_auth(no_auth)
    assert fallback.user_id == "dev-user-local"
    assert auth.optional_auth(no_auth) == fallback

    monkeypatch.setattr(
        auth,
        "_authoritative_policy",
        lambda: AuthPolicy.from_settings(_settings(auth_dev_mode=False)),
    )
    with pytest.raises(Exception) as missing:
        auth.require_auth(no_auth)
    assert missing.value.status_code == 401
    assert auth.optional_auth(no_auth) is None


def test_jose_token_helper_remains_available_for_bearer_fixtures() -> None:
    """Keep a real token fixture smoke check alongside mocked dependency branches."""
    token = jose_jwt.encode({"sub": "fixture", "exp": 4_102_444_800}, TEST_SECRET, algorithm="HS256")
    assert token.count(".") == 2
