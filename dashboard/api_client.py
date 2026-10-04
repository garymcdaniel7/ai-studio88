"""Authenticated API client for the legacy Streamlit dashboard.

The dashboard remains a legacy/admin surface.  This module keeps its existing
response and error handling while obtaining the current access token from an
injected session provider (Streamlit uses ``st.session_state``).  It never
reads browser storage, accepts a client organization selector, or handles
service-role credentials.
"""
from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

from dashboard.session import (
    AuthenticationRequiredError,
    SessionProvider,
    extract_access_token,
    finish_authentication,
    get_current_session_token,
    get_session_provider,
    set_session_provider,
)

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Backward-compatible names for callers that need auth-provider injection.
AuthenticationRequired = AuthenticationRequiredError

__all__ = [
    "AuthenticationRequired",
    "SessionProvider",
    "set_session_provider",
    "get_current_session_token",
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "upload",
]


def _request(method: str, url: str, *, require_auth: bool = True, **kwargs: Any) -> requests.Response:
    """Send one request, refreshing an unauthorized session at most once."""
    provider = get_session_provider()
    token = get_current_session_token()

    if require_auth and token is None:
        try:
            token = extract_access_token(provider.refresh_access_token())
        except Exception:
            token = None
        if token is None:
            finish_authentication(provider)
            raise AuthenticationRequired("A valid dashboard session is required")

    refresh_attempted = False
    while True:
        request_kwargs = dict(kwargs)
        headers = dict(request_kwargs.pop("headers", {}) or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request_kwargs["headers"] = headers
        response = requests.request(method, url, **request_kwargs)

        if not require_auth or response.status_code != 401:
            return response
        if refresh_attempted:
            finish_authentication(provider)
            raise AuthenticationRequired("The dashboard session expired; please sign in again")

        refresh_attempted = True
        try:
            token = extract_access_token(provider.refresh_access_token())
        except Exception:
            token = None
        if token is None:
            finish_authentication(provider)
            raise AuthenticationRequired("The dashboard session expired; please sign in again")


def _url(path: str) -> str:
    """Build a version-one API URL."""
    return f"{API_BASE_URL}/api/v1{path}"


def _handle(resp: requests.Response) -> Any:
    """Return JSON or raise with the existing structured API detail."""
    if resp.ok:
        return resp.json()
    detail = (
        resp.json().get("detail", resp.text)
        if resp.headers.get("content-type", "").startswith("application/json")
        else resp.text
    )
    raise Exception(f"API error {resp.status_code}: {detail}")


# ── Generic authenticated transport ──────────────────────────────────────────

def get(url: str, **kwargs: Any) -> Any:
    """Issue an authenticated GET request."""
    return _handle(_request("GET", url, **kwargs))


def post(url: str, **kwargs: Any) -> Any:
    """Issue an authenticated POST request."""
    return _handle(_request("POST", url, **kwargs))


def put(url: str, **kwargs: Any) -> Any:
    """Issue an authenticated PUT request."""
    return _handle(_request("PUT", url, **kwargs))


def patch(url: str, **kwargs: Any) -> Any:
    """Issue an authenticated PATCH request."""
    return _handle(_request("PATCH", url, **kwargs))


def delete(url: str, **kwargs: Any) -> Any:
    """Issue an authenticated DELETE request."""
    return _handle(_request("DELETE", url, **kwargs))


def upload(url: str, **kwargs: Any) -> Any:
    """Issue an authenticated multipart upload request."""
    return _handle(_request("POST", url, **kwargs))


def _probe_get(url: str) -> Any:
    """Issue a public health/probe request, attaching a token when available."""
    return _handle(_request("GET", url, require_auth=False))


# ── Health ────────────────────────────────────────────────────────────────────

def health() -> Any:
    """Return the public backend health response."""
    return _probe_get(f"{API_BASE_URL}/")


def v1_health() -> Any:
    """Return the v1 health response without forcing a login for the probe."""
    return _probe_get(_url("/health"))


# ── Projects ──────────────────────────────────────────────────────────────────

def list_projects() -> Any:
    """List projects for the authenticated dashboard organization."""
    return get(f"{API_BASE_URL}/projects")


# ── Talent ───────────────────────────────────────────────────────────────────

def list_talent() -> Any:
    """List talent for the authenticated dashboard organization."""
    return get(_url("/talent"))


def create_talent(data: dict[str, Any]) -> Any:
    """Create talent for the authenticated dashboard organization."""
    return post(_url("/talent"), json=data)


# ── Assets ────────────────────────────────────────────────────────────────────

def list_assets() -> Any:
    """List assets for the authenticated dashboard organization."""
    return get(_url("/assets"))


def get_asset(asset_id: str) -> Any:
    """Get one asset by ID for the authenticated dashboard organization."""
    return get(_url(f"/assets/{asset_id}"))


def upload_asset(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    asset_type: str = "general",
    tags: str = "",
) -> Any:
    """Upload one asset using the authenticated multipart transport."""
    files = {"file": (filename, file_bytes, content_type)}
    data = {"asset_type": asset_type, "tags": tags}
    return upload(_url("/assets"), files=files, data=data)


def delete_asset(asset_id: str) -> Any:
    """Delete one asset for the authenticated dashboard organization."""
    return delete(_url(f"/assets/{asset_id}"))


# ── Jobs ──────────────────────────────────────────────────────────────────────

def list_jobs(status: str | None = None, job_type: str | None = None) -> Any:
    """List jobs for the authenticated dashboard organization."""
    params: dict[str, str] = {}
    if status:
        params["status"] = status
    if job_type:
        params["type"] = job_type
    return get(_url("/jobs"), params=params)


def get_job(job_id: str) -> Any:
    """Get one job by ID for the authenticated dashboard organization."""
    return get(_url(f"/jobs/{job_id}"))


def create_job(data: dict[str, Any]) -> Any:
    """Create a job for the authenticated dashboard organization."""
    return post(_url("/jobs"), json=data)


def cancel_job(job_id: str) -> Any:
    """Cancel one job for the authenticated dashboard organization."""
    return post(_url(f"/jobs/{job_id}/cancel"))


def retry_job(job_id: str) -> Any:
    """Retry one job for the authenticated dashboard organization."""
    return post(_url(f"/jobs/{job_id}/retry"))


def delete_job(job_id: str) -> Any:
    """Delete one job for the authenticated dashboard organization."""
    return delete(_url(f"/jobs/{job_id}"))


# ── Workflows ─────────────────────────────────────────────────────────────────

def list_workflows() -> Any:
    """List workflows for the authenticated dashboard organization."""
    return get(_url("/workflows"))


def get_workflow(workflow_id: str) -> Any:
    """Get one workflow by ID for the authenticated dashboard organization."""
    return get(_url(f"/workflows/{workflow_id}"))


def create_workflow(data: dict[str, Any]) -> Any:
    """Create a workflow for the authenticated dashboard organization."""
    return post(_url("/workflows"), json=data)


def run_workflow(workflow_id: str, input_data: dict[str, Any] | None = None) -> Any:
    """Run one workflow for the authenticated dashboard organization."""
    return post(_url(f"/workflows/{workflow_id}/run"), json={"input": input_data or {}})


def delete_workflow(workflow_id: str) -> Any:
    """Delete one workflow for the authenticated dashboard organization."""
    return delete(_url(f"/workflows/{workflow_id}"))
