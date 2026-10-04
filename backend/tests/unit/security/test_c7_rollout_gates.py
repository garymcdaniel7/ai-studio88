"""C7 regression/property gates for Phase 1 auth and tenant isolation.

This suite composes the unchanged Property 1/2 tests with focused rollout,
query-audit, route-inventory, worker, credential, and frame-grid checks.
It deliberately reports repository/staging blockers instead of treating local
fixtures as deployment acceptance.

**Validates: Properties 1-5; Requirements 2.1-2.19, 3.1-3.13**
"""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from backend.aios.mcp.tools import MCP_TOOLS
from backend.app.core.auth_policy import PUBLIC_PROBE_ALLOWLIST, AuthPolicy
from backend.app.core.middleware import _auth_error
from backend.scripts.audit_tenant_queries import collect_findings
from backend.video.adapters.thunder_h3_adapter import H3_LENGTH_GRID, validate_h3_length
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[4]
AFFECTED_EXECUTORS = (
    "_exec_generate_image",
    "_exec_generate_video",
    "_exec_train_lora",
    "_exec_search_talent",
    "_exec_create_talent",
    "_exec_schedule_post",
)

EXPECTED_NATIVE_API_ROUTES = frozenset(
    {
        ("GET", "/projects"),
        ("GET", "/talent"),
        ("POST", "/talent"),
    }
)

# The sealed Phase 1 contract announced 22 /story routes. The current router
# retains those routes and now also announces the two WRITE contracts at
# /shots/{shot_id} and /shots/{shot_id}/generate, for 24 operations total.
EXPECTED_STORY_ROUTES = frozenset(
    {
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
        ("PUT", "/api/v1/shots/{shot_id}"),
        ("POST", "/api/v1/shots/{shot_id}/generate"),
        ("PATCH", "/api/v1/story/shots/{shot_id}"),
        ("DELETE", "/api/v1/story/shots/{shot_id}"),
    }
)

# This is the live MCP registry inventory, including all Phase 2 story,
# publishing, credentials, and generation tools. The registry currently has
# 52 entries and 51 unique names because schedule_post remains dual-registered
# by its legacy and Phase 2 declarations; the exact name set catches drift.
EXPECTED_MCP_TOOL_NAMES = frozenset(
    {
        "search_talent",
        "get_talent_dna",
        "create_talent",
        "generate_image",
        "generate_video",
        "recommend_workflow",
        "continue_story",
        "get_story_context",
        "train_lora",
        "get_training_status",
        "search_assets",
        "schedule_post",
        "check_gpu_status",
        "estimate_cost",
        "list_models",
        "search_knowledge",
        "create_episode",
        "create_scene",
        "create_shot",
        "update_shot_prompt",
        "get_storyboard",
        "list_episodes",
        "upload_shot_reference",
        "connect_platform",
        "disconnect_platform",
        "list_connected_platforms",
        "list_platforms",
        "check_platform_policy",
        "list_scheduled_posts",
        "get_publishing_calendar",
        "cancel_scheduled_post",
        "get_publishing_status",
        "get_connection_status",
        "check_connection_health",
        "reauthorize_connection",
        "revoke_connection",
        "add_api_key",
        "list_api_keys",
        "remove_api_key",
        "test_api_key",
        "get_default_provider",
        "preview_generation",
        "get_generation_status",
        "get_generation_queue",
        "generate_with_ksampler",
        "generate_with_workflow",
        "list_workflows",
        "switch_workflow",
        "get_workflow_schema",
        "generate_batch",
        "cancel_generation",
    }
)


@pytest.mark.unit
@given(path=st.text(alphabet="abcdefghijklmnopqrstuvwxyz/-", min_size=1, max_size=24))
@settings(max_examples=40, deadline=None)
def test_property_1_and_4_policy_is_exact_and_fail_closed(path: str) -> None:
    """Public near-matches stay protected and protected rollout is fail-closed."""
    policy = AuthPolicy.from_settings(
        SimpleNamespace(
            app_env="staging",
            auth_required=True,
            auth_dev_mode=False,
            auth_enforcement_flip=True,
            auth_dark_launch=False,
        )
    )
    assert policy.enforces_authentication
    if path not in PUBLIC_PROBE_ALLOWLIST:
        assert not policy.is_public(path, "GET")


@pytest.mark.unit
def test_property_4_flip_and_dark_launch_rules_are_single_source() -> None:
    """Only the authoritative flip enables protected deployment startup."""
    staging = SimpleNamespace(
        app_env="staging",
        auth_required=True,
        auth_dev_mode=False,
        auth_enforcement_flip=False,
        auth_dark_launch=False,
    )
    with pytest.raises(RuntimeError, match="AUTH_ENFORCEMENT_FLIP=true"):
        AuthPolicy.from_settings(staging).validate_startup()

    dark = AuthPolicy.from_settings(
        SimpleNamespace(
            app_env="test",
            auth_required=False,
            auth_dev_mode=False,
            auth_enforcement_flip=False,
            auth_dark_launch=True,
        )
    )
    assert dark.observes_only
    assert not dark.enforces_authentication


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "code"),
    (
        (401, "UNAUTHORIZED"),
        (403, "FORBIDDEN"),
        (404, "NOT_FOUND"),
        (422, "ORG_ID_INJECTION_REJECTED"),
        (500, "INTERNAL_ERROR"),
    ),
)
def test_property_1_stable_error_mapping(status: int, code: str) -> None:
    """Every auth boundary error retains a status, code, and request id."""
    response = _auth_error("stable test error", code, "request-c7", status=status)
    assert response.status_code == status
    assert response.body == (f'{{"detail":"stable test error","code":"{code}"}}').encode()
    assert response.headers["X-Request-ID"] == "request-c7"


@pytest.mark.unit
@given(org=st.uuids(version=4).map(str))
@settings(max_examples=20, deadline=None)
def test_property_1_null_org_is_rejected_before_tenant_use(org: str) -> None:
    """Null organization identities cannot be accepted for tenant paths."""
    assert org
    from backend import auth
    from starlette.requests import Request

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/tenant",
            "headers": [(b"authorization", b"Bearer token")],
            "query_string": b"",
        }
    )
    original_decode = auth._decode_token
    original_extract = auth._extract_user
    try:
        auth._decode_token = lambda _token: {"sub": "user-c7"}  # type: ignore[assignment]
        auth._extract_user = lambda _payload: auth.AuthUser("user-c7", org_id=None)  # type: ignore[assignment]
        with pytest.raises(Exception) as denied:
            auth.require_auth(request)
        assert getattr(denied.value, "status_code", None) == 403
    finally:
        auth._decode_token = original_decode
        auth._extract_user = original_extract


@pytest.mark.unit
def test_property_3_every_query_finding_has_one_classification() -> None:
    """Static audit rows are classified; blocked rows remain explicit blockers."""
    findings = collect_findings()
    assert findings
    assert all(item.classification and item.evidence and item.status for item in findings)
    assert not any(item.classification == "UNKNOWN" for item in findings)


@pytest.mark.unit
def test_property_3_api_v1_inventory_and_optional_auth_are_present() -> None:
    """The API inventory records the 19+ findings and null-org optional paths."""
    inventory = (ROOT / "docs/architecture/AUTH_TENANT_QUERY_INVENTORY.md").read_text()
    assert inventory.count("|") > 60
    assert "optional-auth" in (ROOT / "docs/architecture/AUTH_TENANT_QUERY_AUDIT.md").read_text()


@pytest.mark.unit
def test_property_2_and_3_tenant_a_b_crud_and_pagination_evidence_exists() -> None:
    """Existing A/B CRUD and paginated story contracts remain in the C7 gate."""
    security_tests = (ROOT / "backend/tests/unit/security/test_api_v1_tenant_isolation.py").read_text()
    story_router = (ROOT / "backend/story_engine/router.py").read_text()
    assert "foreign" in security_tests and "_tenant_delete" in security_tests
    assert "limit: int = Query(default=20, ge=1, le=100)" in story_router
    assert "offset: int = Query(default=0, ge=0)" in story_router


@pytest.mark.unit
def test_property_1_six_executor_context_propagation() -> None:
    """All six tenant-aware Brain executors require the trusted org argument."""
    from backend.aios.execution import tools

    assert "org_id" in inspect.signature(tools.execute_tool).parameters
    for name in AFFECTED_EXECUTORS:
        assert "org_id" in inspect.signature(getattr(tools, name)).parameters


@pytest.mark.unit
def test_property_1_worker_lifecycle_predicates_are_audited() -> None:
    """Worker lifecycle operations retain explicit organization context evidence."""
    worker_source = (ROOT / "backend/worker.py").read_text()
    assert "poll" in worker_source and "claim" in worker_source and "complete" in worker_source and "fail" in worker_source
    assert "org_id" in worker_source
    assert "c7dc65c0-a0b1-4980-9f60-884d024a19ca" not in worker_source


@pytest.mark.unit
def test_property_5_route_and_provider_inventories_are_exact() -> None:
    """Announced native, story, and MCP inventories fail closed on drift.

    The documented delta from the sealed 22-route Phase 1 story baseline is
    the two current WRITE operations, making the live story router 24 routes.
    The native API surface remains three routes, while MCP exposes 52 entries
    (51 unique names because the existing registry has two schedule_post rows).
    """
    route_map = ROOT / "frontend/src/lib/route-migration.ts"
    assert route_map.exists()
    route_source = route_map.read_text()
    for route in ("/create", "/editor", "/models", "/projects", "/jobs"):
        assert route in route_source

    from backend.main import app

    openapi = app.openapi()
    native_routes = {
        (method.upper(), path)
        for path, operations in openapi["paths"].items()
        if path in {"/projects", "/talent"}
        for method in operations
        if method in {"get", "post", "patch", "put", "delete"}
    }
    assert native_routes == EXPECTED_NATIVE_API_ROUTES

    from backend.story_engine.router import router as story_router

    story_app = FastAPI()
    story_app.include_router(story_router, prefix="/api/v1")
    story_openapi = story_app.openapi()
    story_routes = {
        (method.upper(), path)
        for path, operations in story_openapi["paths"].items()
        if path.startswith("/api/v1/story/") or path.startswith("/api/v1/shots/")
        for method in operations
        if method in {"get", "post", "patch", "put", "delete"}
    }
    assert story_routes == EXPECTED_STORY_ROUTES

    tool_names = [tool.name for tool in MCP_TOOLS]
    assert len(tool_names) == 52
    assert set(tool_names) == EXPECTED_MCP_TOOL_NAMES


@pytest.mark.unit
def test_property_2_credential_and_frame_contracts_are_exact() -> None:
    """Credential expiry and the eleven-value H3 frame contract remain covered."""
    credential_source = (ROOT / "backend/credentials.py").read_text()
    assert "expires_at" in credential_source and "USER_API_KEY" in credential_source
    assert tuple(H3_LENGTH_GRID) == (124, 141, 209, 226, 243, 260, 277, 294, 362, 480, 600)
    for value in H3_LENGTH_GRID:
        assert validate_h3_length(value) == value
    for stale in (0, -1, 216, 280, "226", 226.0, True):
        with pytest.raises(ValueError):
            validate_h3_length(stale)


@pytest.mark.unit
def test_property_4_staging_gate_is_explicitly_blocked_without_controlled_evidence() -> None:
    """Local evidence never silently becomes staging acceptance."""
    evidence = (ROOT / "docs/architecture/AUTH_ROLLOUT_GATES.md").read_text()
    assert "STAGING-REQUIRED" in evidence
    assert "BLOCKED" in evidence
    assert "two controlled organization" in evidence.lower()
    assert "RLS-disabled" in evidence


@pytest.mark.unit
def test_property_2_cors_preflight_completes_before_auth() -> None:
    """A valid browser preflight succeeds without invoking bearer auth."""
    from backend.main import app

    response = TestClient(app, raise_server_exceptions=False).options(
        "/api/v1/capabilities",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
