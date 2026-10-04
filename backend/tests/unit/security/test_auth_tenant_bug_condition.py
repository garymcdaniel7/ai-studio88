"""Exploration property for Phase 1 Property 1 on the unfixed baseline.

This test intentionally asserts the post-remediation contract against the current
checkout. It is expected to fail before the Phase 1 remediation is implemented.

**Validates: Requirements 1.1-1.17, 2.1-2.5, 2.11-2.18**
**Validates: Property 1 - Bug Condition - Trusted Tenant Enforcement**

Recorded minimized unfixed counterexamples from the source baseline:

* ``GET /projects`` without a bearer token reaches ``projects()`` and calls
  ``get_projects()`` without an organization; ``GET /talent`` and ``POST
  /talent`` have the same missing dependency/context defect.
* ``execute_tool("search_talent", {"query": "A"})`` accepts no trusted
  ``org_id`` and ``_exec_search_talent`` queries ``talent`` without a scope.
* ``api_v1.py`` contains ``talent``/``assets``/``scenes``/``shots`` and other
  tenant-table operations without an application ``org_id`` predicate.
* ``Worker()`` selects the historical development UUID
  ``c7dc65c0-a0b1-4980-9f60-884d024a19ca``; malformed or absent worker context
  is not rejected before polling.
* ``frontend/src/components/topbar.tsx`` and other protected callers invoke
  raw ``fetch`` instead of the authenticated API transport.
* ``backend/story_engine/router.py`` and the 33-route redirect contract are
  absent; ``CredentialRecord`` has no ``expires_at`` and ``ProviderType`` has
  no ``USER_API_KEY``; the 11-value frame grid is not represented in backend
  validation; and no rollout gate enforces ``BLOCKED`` when evidence is absent.

The failure is deliberately preserved as evidence for the later post-fix rerun.
No production services, databases, credentials, or external APIs are used.
"""
from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from hypothesis import example, given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"

INVALID_BEARERS = (
    None,
    "",
    "Basic dXNlcjpwYXNz",
    "Bearer ",
    "Bearer not-a-valid-jwt",
    # Expired ``exp=1`` token-shaped bearer; the signature is intentionally invalid.
    "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJleHBpcmVkIiwiZXhwIjoxfQ.invalid",
)
ORG_SELECTOR_NAMES = ("org_id", "orgId", "org-id", "organization_id")
TENANT_OPERATIONS = ("read", "update", "delete", "insert")
NATIVE_ROUTES = (
    ("GET", "/projects"),
    ("GET", "/talent"),
    ("POST", "/talent"),
)
TENANT_TABLES = {
    "assets",
    "lora_versions",
    "publishing_posts",
    "scenes",
    "shots",
    "storyboards",
    "talent",
    "talent_loras",
    "talent_relationships",
}
AFFECTED_EXECUTORS = (
    "_exec_generate_image",
    "_exec_generate_video",
    "_exec_train_lora",
    "_exec_search_talent",
    "_exec_create_talent",
    "_exec_schedule_post",
)
V2_DESTINATIONS = {
    "/create": "/make",
    "/editor": "/write",
    "/production": "/write",
    "/training": "/cast?tab=training",
    "/talent": "/cast",
    "/workflows": "/make?tab=workflow",
    "/analytics": "/publish?tab=analytics",
    "/projects": "/start",
    "/jobs": "/make",
    "/assets": "/publish",
}
FRAME_GRID = (124, 141, 209, 226, 243, 260, 277, 294, 362, 480, 600)


@dataclass(frozen=True)
class Observation:
    """Result of evaluating one bug-condition input against the baseline."""

    safe: bool
    evidence: str


def _source(path: Path) -> str:
    """Read a repository source file for a local contract audit."""
    return path.read_text(encoding="utf-8")


def _legacy_unscoped_operations() -> list[str]:
    """Find tenant-table Supabase chains without an application org predicate."""
    source = _source(BACKEND_ROOT / "api_v1.py")
    lines = source.splitlines()
    findings: list[str] = []
    for index, line in enumerate(lines):
        match = re.search(r'table\(["\']([a-z_]+)["\']\)', line)
        if not match or match.group(1) not in TENANT_TABLES:
            continue
        chain = "\n".join(lines[index : index + 15])
        if ".execute()" in chain and not re.search(r"\.eq\([\"']org_id[\"']", chain):
            findings.append(f"{match.group(1)}:line {index + 1}")
    return findings


def _protected_raw_fetches() -> list[str]:
    """Enumerate protected frontend callers bypassing api.ts/authFetch."""
    findings: list[str] = []
    frontend_root = REPO_ROOT / "frontend" / "src"
    raw_fetch = re.compile(r"(?<![A-Za-z])fetch\(")
    for path in frontend_root.rglob("*.tsx"):
        text = _source(path)
        if raw_fetch.search(text) and ("/api/v1/" in text or "/aios/" in text):
            findings.append(str(path.relative_to(REPO_ROOT)))
    return findings


def _observe(
    case: str,
    invalid_bearer: str | None,
    selector: str,
    operation: str,
) -> Observation:
    """Evaluate one generated bug-condition input against the fixed contract."""
    main_source = _source(REPO_ROOT / "backend" / "main.py")
    middleware_source = _source(REPO_ROOT / "backend" / "app" / "core" / "middleware.py")
    tools_source = _source(BACKEND_ROOT / "aios" / "execution" / "tools.py")
    worker_source = _source(BACKEND_ROOT / "worker.py")
    credentials_source = _source(BACKEND_ROOT / "credentials.py")
    next_config = _source(REPO_ROOT / "frontend" / "next.config.ts")
    policy_source = _source(REPO_ROOT / "backend" / "app" / "core" / "auth_policy.py")
    rollout_evidence = _source(REPO_ROOT / "docs" / "architecture" / "AUTH_ROLLOUT_GATES.md")

    if case == "invalid_bearer":
        route_is_protected = "AuthMiddleware" in main_source and "require_auth" in main_source
        return Observation(
            route_is_protected,
            f"invalid bearer {invalid_bearer!r} on non-public route has no authoritative auth boundary",
        )
    if case == "org_selector":
        guarded = all(name in middleware_source for name in ORG_SELECTOR_NAMES) and "ORG_ID_INJECTION_REJECTED" in middleware_source
        return Observation(guarded, f"client selector spelling {selector!r} is not rejected before handler")
    if case == "brain_context":
        bridge = inspect.signature(_load_tools().execute_tool)
        missing = [
            name for name in AFFECTED_EXECUTORS
            if name not in tools_source or "org_id" not in str(inspect.signature(getattr(_load_tools(), name)))
        ]
        return Observation("org_id" in bridge.parameters and not missing, f"missing trusted Brain org context: {missing}")
    if case == "unscoped_query":
        findings = _legacy_unscoped_operations()
        return Observation(not findings, f"unscoped tenant operations: {findings[:3]}")
    if case == "cross_tenant":
        findings = _legacy_unscoped_operations()
        return Observation(
            not findings,
            f"organization B can reach A-owned {operation} operations: {findings[:3]}",
        )
    if case in {"worker_context", "worker_missing_job_context", "worker_malformed_org_id"}:
        safe = (
            "required=True" in worker_source
            and "c7dc65c0-a0b1-4980-9f60-884d024a19ca" not in worker_source
            and "uuid.UUID" in worker_source
            and "self.org_id = validate_worker_org_id(org_id)" in worker_source
        )
        return Observation(safe, "worker accepts missing/malformed org or historical fallback")
    if case == "frontend_transport":
        findings = _protected_raw_fetches()
        return Observation(not findings, f"protected raw fetch callers: {findings[:3]}")
    if case == "story_routes":
        router = BACKEND_ROOT / "story_engine" / "router.py"
        return Observation(router.exists(), "story-engine router is missing; frontend story calls have no route")
    if case == "migration_destination":
        safe = (
            "redirects" in next_config
            and all(source in next_config for source in V2_DESTINATIONS)
            and all(destination.startswith("/") for destination in V2_DESTINATIONS.values())
        )
        return Observation(safe, "V1 route migration has no configured valid destinations")
    if case == "credential_expiry":
        active_block = (
            re.search(r"def _find_active[\s\S]*expires_at", credentials_source) is not None
            and "expires_at" in credentials_source
            and "USER_API_KEY" in credentials_source
        )
        return Observation(active_block, "active expired credential is not treated as inactive")
    if case == "frame_grid":
        frame_source = "\n".join(_source(path) for path in BACKEND_ROOT.rglob("*.py"))
        safe = all(str(value) in frame_source for value in FRAME_GRID) and "216" not in frame_source and "280" not in frame_source
        return Observation(safe, "stale or missing frame-grid validation accepts unsupported values")
    if case == "rollout_evidence":
        has_fail_closed_gate = (
            "AUTH_ENFORCEMENT_FLIP" in policy_source
            and "STAGING-REQUIRED" in rollout_evidence
            and "BLOCKED" in rollout_evidence
        )
        return Observation(has_fail_closed_gate, "rollout can be marked complete without required evidence")
    raise AssertionError(f"unknown bug-condition case: {case}")


def _load_tools():
    """Import the Brain executor module lazily so collection has no side effects."""
    from backend.aios.execution import tools

    return tools


BUG_CONDITION_CASES = (
    "invalid_bearer",
    "org_selector",
    "cross_tenant",
    "brain_context",
    "unscoped_query",
    "worker_context",
    "worker_missing_job_context",
    "worker_malformed_org_id",
    "frontend_transport",
    "story_routes",
    "migration_destination",
    "credential_expiry",
    "frame_grid",
    "rollout_evidence",
)


@pytest.mark.unit
@given(
    case=st.sampled_from(BUG_CONDITION_CASES),
    invalid_bearer=st.sampled_from(INVALID_BEARERS),
    selector=st.sampled_from(ORG_SELECTOR_NAMES),
    operation=st.sampled_from(TENANT_OPERATIONS),
)
@example(
    case="invalid_bearer",
    invalid_bearer=None,
    selector="org_id",
    operation="read",
)
@settings(max_examples=50, deadline=None)
def test_property_1_bug_condition_requires_fixed_contract(
    case: str,
    invalid_bearer: str | None,
    selector: str,
    operation: str,
) -> None:
    """Every generated bug-condition input must be rejected or remain blocked."""
    observation = _observe(case, invalid_bearer, selector, operation)
    assert observation.safe, f"counterexample={case!r}: {observation.evidence}"


@pytest.mark.unit
@pytest.mark.parametrize("method,path", NATIVE_ROUTES)
def test_native_routes_have_no_unprotected_counterexample(
    method: str,
    path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native routes must reject unauthenticated calls before handler/database access."""
    from backend import main

    called = False

    def record_call(*_args, **_kwargs):
        nonlocal called
        called = True
        return SimpleNamespace(data=[])

    monkeypatch.setattr(main, "get_projects", record_call)
    monkeypatch.setattr(main, "get_talent", record_call)
    monkeypatch.setattr(main, "create_talent", record_call)
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.request(method, path, json={"name": "counterexample"} if method == "POST" else None)

    assert response.status_code == 401, f"{method} {path} returned {response.status_code} without auth"
    assert not called, f"{method} {path} invoked its handler/database helper before auth"
