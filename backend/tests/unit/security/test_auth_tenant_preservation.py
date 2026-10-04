"""Property 2 preservation tests for the unfixed auth/tenant baseline.

Observed local shapes: ``GET /`` and ``GET /health`` return ``200`` JSON
``{"status": "ok"}``; ``GET /api/v1/health`` returns ``200`` JSON
``{"status": "ok", "api": "v1"}``; and CORS ``OPTIONS /api/v1/talent``
returns ``200`` text ``OK`` with the localhost allow-origin header. Local
fallback returns ``AuthUser("dev-user-local", "dev@localhost", None, "owner")``;
recipes return ``{"recipes": [...], "total": 10}``; MCP discovery returns
``tools``, ``categories``, ``org_id``, ``total`` with credential tenancy; and
``dashboard/app.py`` remains a configured Streamlit entrypoint with a title.

The native ``/projects`` and ``/talent`` root routes are not asserted because
baseline observation shows the Task 1 defect: handlers call scoped database
helpers without ``org_id``. No external services are used.

**Validates: Requirements 3.1-3.13**
**Validates: Property 2 - Preservation - Valid Existing Behavior**
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode
from uuid import UUID

import pytest
from backend.auth import AuthUser
from backend.tenant_context import QUARANTINED_UUID
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from starlette.requests import Request

REPO_ROOT = Path(__file__).resolve().parents[4]

VALID_UUIDS = st.uuids().filter(lambda value: value.int != 0).map(str)
SUPPORTED_CRUD = st.sampled_from(("list", "detail", "update", "delete", "insert"))
WORKER_OPERATIONS = st.sampled_from(("poll", "claim", "complete", "fail"))
SAFE_QUERY_KEYS = st.sampled_from(("status", "type", "tab", "limit", "offset"))
SAFE_QUERY_VALUES = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"),
    max_size=12,
)
SAFE_QUERY_PARAMS = st.dictionaries(SAFE_QUERY_KEYS, SAFE_QUERY_VALUES, max_size=3)
PUBLIC_PROBES = ("/", "/health", "/docs", "/redoc", "/openapi.json", "/api/v1/health")
ORG_SELECTOR_NAMES = ("org_id", "orgId", "org-id", "organization_id")


@dataclass
class _RecordingQuery:
    """Small Supabase query double that records tenant predicates."""

    table_name: str
    filters: list[tuple[str, object]] = field(default_factory=list)
    inserted: dict | None = None
    response_id: str = "record-1"
    response_org_id: str = "00000000-0000-0000-0000-000000000001"

    def select(self, *_columns: object) -> _RecordingQuery:
        return self

    def insert(self, data: dict) -> _RecordingQuery:
        self.inserted = data
        return self

    def update(self, _data: dict) -> _RecordingQuery:
        return self

    def delete(self) -> _RecordingQuery:
        return self

    def eq(self, name: str, value: object) -> _RecordingQuery:
        self.filters.append((name, value))
        return self

    def order(self, *_args: object, **_kwargs: object) -> _RecordingQuery:
        return self

    def limit(self, *_args: object, **_kwargs: object) -> _RecordingQuery:
        return self

    def execute(self) -> SimpleNamespace:
        row = self.inserted or {"id": self.response_id, "org_id": self.response_org_id}
        return SimpleNamespace(data=[row])


class _RecordingSupabase:
    """Supabase double retaining every query created by one operation."""

    def __init__(self, record_id: str, org_id: str) -> None:
        self.queries: list[_RecordingQuery] = []
        self.record_id = record_id
        self.org_id = org_id

    def table(self, table_name: str) -> _RecordingQuery:
        query = _RecordingQuery(
            table_name=table_name,
            response_id=self.record_id,
            response_org_id=self.org_id,
        )
        self.queries.append(query)
        return query


def _request(path: str = "/optional") -> Request:
    """Build a dependency request without starting an HTTP server."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
        }
    )


@pytest.mark.unit
@given(org_id=VALID_UUIDS, record_id=VALID_UUIDS, operation=SUPPORTED_CRUD)
@settings(max_examples=30, deadline=None)
def test_same_tenant_crud_preserves_scoped_result_shape(
    org_id: str,
    record_id: str,
    operation: str,
) -> None:
    """Valid same-tenant CRUD keeps list/detail/mutation results scoped and shaped."""
    from backend import database

    client = _RecordingSupabase(record_id, org_id)
    with patch.object(database, "supabase", client):
        user = AuthUser(user_id=str(UUID(record_id)), org_id=org_id)

        if operation == "list":
            result = database.get_talent(user.org_id)
        elif operation == "detail":
            result = database.get_talent_by_id(record_id, user.org_id)
        elif operation == "update":
            result = database.update_job(record_id, {"status": "running", "org_id": QUARANTINED_UUID}, user.org_id)
        elif operation == "delete":
            result = database.delete_job(record_id, user.org_id)
        else:
            result = database.create_talent({"name": "Preserved"}, user.org_id)

    assert isinstance(result.data, list)
    assert result.data[0]["org_id"] == org_id
    assert client.queries
    if operation != "insert":
        assert all(("org_id", org_id) in query.filters for query in client.queries)
    else:
        assert client.queries[0].inserted == {"name": "Preserved", "org_id": org_id}


@pytest.mark.unit
@given(worker_org_id=VALID_UUIDS, operation=WORKER_OPERATIONS, job_id=VALID_UUIDS)
@settings(max_examples=20, deadline=None)
def test_trusted_worker_context_preserves_lifecycle_scope(
    worker_org_id: str,
    operation: str,
    job_id: str,
) -> None:
    """Valid worker contexts preserve the existing four-operation org predicate."""
    from backend import database
    from backend.worker import Worker

    client = _RecordingSupabase(job_id, worker_org_id)
    with patch.object(database, "supabase", client):
        worker = Worker(name="preservation-worker", poll_interval=1, org_id=worker_org_id)
        assert worker.org_id == worker_org_id

        if operation == "poll":
            result = database.get_jobs(worker.org_id)
        elif operation == "claim":
            result = database.claim_next_job(worker.name, worker.worker_id, worker.org_id)
        elif operation == "complete":
            result = database.complete_job(job_id, {"status": "ok"}, worker.org_id)
        else:
            result = database.fail_job(job_id, "expected test failure", worker.org_id)

    assert result is not None
    assert client.queries
    assert all(("org_id", worker_org_id) in query.filters for query in client.queries)


@pytest.mark.unit
@given(path=st.sampled_from(PUBLIC_PROBES))
@settings(max_examples=10, deadline=None)
def test_exact_public_probes_preserve_observed_responses(path: str) -> None:
    """The exact observed local public probes remain reachable without a token."""
    from backend.main import app

    response = TestClient(app, raise_server_exceptions=False).get(path)
    assert response.status_code == 200
    if path in {"/", "/health"}:
        assert response.json() == {"status": "ok"}
    elif path == "/api/v1/health":
        assert response.json() == {"status": "ok", "api": "v1"}
    else:
        assert response.headers["content-type"].startswith("text/html") or path == "/openapi.json"


@pytest.mark.unit
@given(method=st.sampled_from(("GET", "POST", "PATCH", "DELETE")), params=SAFE_QUERY_PARAMS)
@settings(max_examples=20, deadline=None)
def test_valid_unauthenticated_options_preflight_preserves_cors(
    method: str,
    params: dict[str, str],
) -> None:
    """Valid preflight remains a 200 ``OK`` response before route auth."""
    from backend.main import app

    query = urlencode(params)
    response = TestClient(app, raise_server_exceptions=False).options(
        f"/api/v1/talent?{query}" if query else "/api/v1/talent",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.text == "OK"
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert not any(name in query for name in ORG_SELECTOR_NAMES)


@pytest.mark.unit
def test_approved_local_fallback_and_optional_auth_without_tenant_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local fallback and anonymous optional-auth paths retain their observed identities."""
    import backend.auth as auth
    from backend.app.core.config import reset_settings

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    reset_settings()
    fallback = auth.require_auth(_request())
    assert fallback == AuthUser("dev-user-local", "dev@localhost", None, "owner")
    assert auth.optional_auth(_request()) == fallback

    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    reset_settings()
    assert auth.optional_auth(_request()) is None


@pytest.mark.unit
def test_documented_shared_reference_data_preserves_recipe_shape() -> None:
    """System-owned recipes remain available without an organization filter."""
    from backend.api_v1 import list_recipes

    result = list_recipes()
    assert set(result) == {"recipes", "total"}
    assert result["total"] == 10
    assert len(result["recipes"]) == result["total"]
    assert set(result["recipes"][0]) == {
        "id", "name", "description", "category", "model", "cfg", "steps",
        "quality_score", "recommended_for", "created_by",
    }
    assert all(recipe["created_by"] == "system" for recipe in result["recipes"])


@pytest.mark.unit
@given(org_id=VALID_UUIDS)
@settings(max_examples=10, deadline=None)
def test_existing_mcp_authentication_preserves_credential_org(org_id: str) -> None:
    """The current MCP boundary authenticates and propagates credential tenancy."""
    from backend.aios.mcp import auth as mcp_auth
    from backend.aios.mcp.server import mcp_list_tools

    mcp_auth._reset_store()
    _credential_id, raw_key = mcp_auth.issue_credential(
        org_id=org_id,
        issued_by="preservation-test-user",
        actor_name="preservation-test-client",
        capabilities=frozenset({"search_talent"}),
        expires_in_days=None,
    )
    identity = mcp_auth.authenticate_mcp_request(f"Bearer {raw_key}")
    result = mcp_list_tools(identity)

    assert identity.org_id == org_id
    assert set(result) == {"tools", "categories", "org_id", "total"}
    assert result["org_id"] == org_id
    assert result["total"] == len(result["tools"])
    mcp_auth._reset_store()


@pytest.mark.unit
@given(token=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-", min_size=20, max_size=80))
@settings(max_examples=15, deadline=None)
def test_valid_frontend_session_transport_contract(token: str) -> None:
    """The existing frontend transport obtains and sends a session bearer token."""
    source = (REPO_ROOT / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    assert "getAccessToken" in source
    assert 'return { Authorization: `Bearer ${token}` };' in source
    assert "X-Request-ID" in source
    assert 'window.location.assign("/login")' in source
    assert not any(name in token for name in ORG_SELECTOR_NAMES)


@pytest.mark.unit
def test_streamlit_legacy_admin_entrypoint_remains_available() -> None:
    """Streamlit remains available as the documented legacy/admin surface."""
    source = (REPO_ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    assert "import streamlit as st" in source
    assert "st.set_page_config" in source
    assert "st.title(\"AI Studio Dashboard\")" in source
    assert (REPO_ROOT / "dashboard" / "pages").is_dir()
