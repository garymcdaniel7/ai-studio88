"""Unit coverage for the legacy dashboard authenticated transport."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

import pytest
import requests

from dashboard import api_client


class FakeSessionProvider:
    """In-memory session provider used to test token and refresh states."""

    def __init__(self, token: str | None = "valid-token", refreshes: list[Any] | None = None):
        self.token = token
        self.refreshes = list(refreshes or [])
        self.clear_calls = 0
        self.login_calls = 0

    def get_access_token(self) -> str | None:
        return self.token

    def refresh_access_token(self) -> Any:
        return self.refreshes.pop(0) if self.refreshes else None

    def clear_session(self) -> None:
        self.clear_calls += 1
        self.token = None

    def redirect_to_login(self) -> None:
        self.login_calls += 1


@pytest.fixture
def session_provider() -> FakeSessionProvider:
    """Install and remove an isolated session provider for each test."""
    provider = FakeSessionProvider()
    api_client.set_session_provider(provider)
    yield provider
    api_client.set_session_provider(None)


def response(status: int = 200, payload: Any = None) -> Mock:
    """Build a response mock with the fields consumed by the client."""
    result = Mock(spec=requests.Response)
    result.status_code = status
    result.ok = 200 <= status < 300
    result.headers = {"content-type": "application/json"}
    result.json.return_value = payload if payload is not None else {"ok": True}
    result.text = "error detail"
    return result


@pytest.mark.unit
@pytest.mark.parametrize(
    ("method", "function"),
    [
        ("GET", api_client.get),
        ("POST", api_client.post),
        ("PUT", api_client.put),
        ("PATCH", api_client.patch),
        ("DELETE", api_client.delete),
        ("POST", api_client.upload),
    ],
)
def test_every_generic_method_attaches_current_bearer_token(
    session_provider: FakeSessionProvider,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    function: Callable[..., Any],
) -> None:
    """All generic methods send the provider's current token unchanged."""
    request = Mock(return_value=response())
    monkeypatch.setattr(api_client.requests, "request", request)

    kwargs = {"json": {"name": "Nova"}} if method != "DELETE" else {}
    if function is api_client.upload:
        kwargs = {"files": {"file": ("asset.png", b"bytes", "image/png")}}
    function("http://api.test/resource", **kwargs)

    assert request.call_args.kwargs["headers"] == {"Authorization": "Bearer valid-token"}
    assert request.call_args.args == (method, "http://api.test/resource")


@pytest.mark.unit
@pytest.mark.parametrize(
    "call",
    [
        lambda: api_client.list_projects(),
        lambda: api_client.list_talent(),
        lambda: api_client.create_talent({"name": "Nova"}),
        lambda: api_client.list_assets(),
        lambda: api_client.get_asset("asset-id"),
        lambda: api_client.upload_asset(b"bytes", "asset.png", "image/png"),
        lambda: api_client.delete_asset("asset-id"),
        lambda: api_client.list_jobs("queued", "image"),
        lambda: api_client.get_job("job-id"),
        lambda: api_client.create_job({"type": "image"}),
        lambda: api_client.cancel_job("job-id"),
        lambda: api_client.retry_job("job-id"),
        lambda: api_client.delete_job("job-id"),
        lambda: api_client.list_workflows(),
        lambda: api_client.get_workflow("workflow-id"),
        lambda: api_client.create_workflow({"name": "workflow"}),
        lambda: api_client.run_workflow("workflow-id", {"prompt": "portrait"}),
        lambda: api_client.delete_workflow("workflow-id"),
    ],
)
def test_every_dashboard_wrapper_uses_authenticated_transport(
    session_provider: FakeSessionProvider,
    monkeypatch: pytest.MonkeyPatch,
    call: Callable[[], Any],
) -> None:
    """Existing dashboard helpers retain their paths and attach Authorization."""
    request = Mock(return_value=response())
    monkeypatch.setattr(api_client.requests, "request", request)

    call()

    assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer valid-token"


@pytest.mark.unit
def test_health_probes_preserve_public_behavior_and_attach_token_when_present(
    session_provider: FakeSessionProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health probes do not force login but carry a token when one exists."""
    request = Mock(return_value=response())
    monkeypatch.setattr(api_client.requests, "request", request)

    api_client.health()
    api_client.v1_health()

    assert request.call_count == 2
    assert all(
        call.kwargs["headers"]["Authorization"] == "Bearer valid-token"
        for call in request.call_args_list
    )
    assert session_provider.clear_calls == 0


@pytest.mark.unit
def test_missing_token_refreshes_once_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing token uses the provider refresh path before login is required."""
    provider = FakeSessionProvider(token=None, refreshes=["refreshed-token"])
    api_client.set_session_provider(provider)
    request = Mock(return_value=response())
    monkeypatch.setattr(api_client.requests, "request", request)

    try:
        api_client.list_projects()
    finally:
        api_client.set_session_provider(None)

    assert request.call_count == 1
    assert request.call_args.kwargs["headers"] == {"Authorization": "Bearer refreshed-token"}
    assert provider.clear_calls == 0
    assert provider.login_calls == 0


@pytest.mark.unit
def test_missing_token_refresh_failure_clears_and_requests_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing session fails closed without issuing an unauthenticated request."""
    provider = FakeSessionProvider(token=None)
    api_client.set_session_provider(provider)
    request = Mock(return_value=response())
    monkeypatch.setattr(api_client.requests, "request", request)

    try:
        with pytest.raises(api_client.AuthenticationRequired):
            api_client.list_projects()
    finally:
        api_client.set_session_provider(None)

    request.assert_not_called()
    assert provider.clear_calls == 1
    assert provider.login_calls == 1


@pytest.mark.unit
def test_expired_token_refreshes_once_after_401(
    session_provider: FakeSessionProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One expired-token response refreshes once and retries with the new token."""
    request = Mock(side_effect=[response(401, {"detail": "expired"}), response()])
    session_provider.refreshes = ["refreshed-token"]
    monkeypatch.setattr(api_client.requests, "request", request)

    assert api_client.list_projects() == {"ok": True}

    assert request.call_count == 2
    assert request.call_args_list[0].kwargs["headers"]["Authorization"] == "Bearer valid-token"
    assert request.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer refreshed-token"
    assert session_provider.clear_calls == 0


@pytest.mark.unit
def test_expired_token_refresh_failure_does_not_loop(
    session_provider: FakeSessionProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed refresh after 401 clears the session and makes only one request."""
    request = Mock(return_value=response(401, {"detail": "expired"}))
    monkeypatch.setattr(api_client.requests, "request", request)

    with pytest.raises(api_client.AuthenticationRequired):
        api_client.list_projects()

    request.assert_called_once()
    assert session_provider.clear_calls == 1
    assert session_provider.login_calls == 1


@pytest.mark.unit
def test_second_401_after_refresh_does_not_retry_again(
    session_provider: FakeSessionProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refreshed token receives at most one retry before login is required."""
    request = Mock(side_effect=[response(401), response(401)])
    session_provider.refreshes = ["refreshed-token"]
    monkeypatch.setattr(api_client.requests, "request", request)

    with pytest.raises(api_client.AuthenticationRequired):
        api_client.list_projects()

    assert request.call_count == 2
    assert session_provider.clear_calls == 1
    assert session_provider.login_calls == 1


@pytest.mark.unit
def test_valid_non_auth_error_preserves_existing_structured_detail(
    session_provider: FakeSessionProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-auth failures retain the existing status/detail exception contract."""
    monkeypatch.setattr(
        api_client.requests,
        "request",
        Mock(return_value=response(422, {"detail": "invalid input"})),
    )

    with pytest.raises(Exception, match=r"API error 422: invalid input"):
        api_client.create_talent({"name": ""})

    assert session_provider.clear_calls == 0
    assert session_provider.login_calls == 0
