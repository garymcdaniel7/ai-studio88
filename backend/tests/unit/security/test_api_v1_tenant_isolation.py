"""Focused tenant-isolation tests for the Task 4 API query remediation."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from backend.api_v1 import (
    _tenant_delete,
    _tenant_insert,
    _tenant_select,
    _tenant_update,
    v1_delete_storyboard,
    v1_get_storyboard,
    v1_get_talent_loras,
    v1_update_model,
    v1_update_storyboard,
    v1_update_talent,
)
from backend.auth import AuthUser
from backend.data_access import AuthorizedClient
from backend.database import create_scene
from backend.membership import OrgRole, TenantContext
from backend.tenant_repo import TenantRepo
from fastapi import HTTPException

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
TALENT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
STORYBOARD_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class RecordingQuery:
    """Small Supabase query double that models tenant filtering."""

    def __init__(self, table: str, rows: list[dict[str, object]]) -> None:
        self.table_name = table
        self.rows = rows
        self.filters: list[tuple[str, object]] = []
        self.payload: dict[str, object] | None = None
        self.operation = "select"

    def select(self, *_columns: object, **_kwargs: object) -> RecordingQuery:
        self.operation = "select"
        return self

    def insert(self, payload: dict[str, object]) -> RecordingQuery:
        self.operation = "insert"
        self.payload = payload
        return self

    def update(self, payload: dict[str, object]) -> RecordingQuery:
        self.operation = "update"
        self.payload = payload
        return self

    def delete(self) -> RecordingQuery:
        self.operation = "delete"
        return self

    def eq(self, key: str, value: object) -> RecordingQuery:
        self.filters.append((key, value))
        return self

    def in_(self, key: str, values: list[str]) -> RecordingQuery:
        self.filters.append((key, values))
        return self

    def ilike(self, *_args: object) -> RecordingQuery:
        return self

    def order(self, *_args: object, **_kwargs: object) -> RecordingQuery:
        return self

    def limit(self, *_args: object, **_kwargs: object) -> RecordingQuery:
        return self

    def single(self) -> RecordingQuery:
        return self

    def execute(self) -> SimpleNamespace:
        requested_org = next((value for key, value in self.filters if key == "org_id"), None)
        rows = self.rows if requested_org in (None, ORG_A) else []
        if self.operation == "insert" and self.payload is not None:
            rows = [self.payload]
        return SimpleNamespace(data=rows)


class RecordingSupabase:
    """Supabase double retaining each query for assertions."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.queries: list[RecordingQuery] = []

    def table(self, table: str) -> RecordingQuery:
        query = RecordingQuery(table, self.rows)
        self.queries.append(query)
        return query


def user(org_id: str) -> AuthUser:
    """Build a trusted authenticated user for one organization."""
    return AuthUser(user_id="user-1", email="user@example.test", org_id=org_id, role="owner")


@pytest.mark.unit
def test_direct_helpers_never_return_foreign_tenant_rows() -> None:
    """A and B receive only rows selected with their own trusted org."""
    client = RecordingSupabase([{"id": TALENT_ID, "org_id": ORG_A}])
    with patch("backend.api_v1.supabase", client):
        selected_a = _tenant_select(user(ORG_A), "talent").eq("id", TALENT_ID).execute()
        selected_b = _tenant_select(user(ORG_B), "talent").eq("id", TALENT_ID).execute()

    assert selected_a.data == [{"id": TALENT_ID, "org_id": ORG_A}]
    assert selected_b.data == []
    assert ("org_id", ORG_A) in client.queries[0].filters
    assert ("org_id", ORG_B) in client.queries[1].filters


@pytest.mark.unit
def test_insert_overwrites_client_org_and_update_cannot_reassign() -> None:
    """Writes attribute and retain ownership from the trusted context."""
    client = RecordingSupabase([])
    with patch("backend.api_v1.supabase", client):
        _tenant_insert(user(ORG_B), "talent", {"name": "B", "org_id": ORG_A})
        _tenant_update(user(ORG_B), "talent", TALENT_ID, {"bio": "updated", "org_id": ORG_A})

    insert_query, update_query = client.queries
    assert insert_query.payload == {"name": "B", "org_id": ORG_B}
    assert update_query.payload == {"bio": "updated", "updated_at": "now()"}
    assert ("org_id", ORG_B) in update_query.filters


@pytest.mark.unit
def test_tenant_mutations_use_id_and_org_predicates() -> None:
    """A delete cannot target the same record ID in another organization."""
    client = RecordingSupabase([{"id": TALENT_ID, "org_id": ORG_A}])
    with patch("backend.api_v1.supabase", client):
        _tenant_delete(user(ORG_A), "talent", TALENT_ID)
        result_b = _tenant_delete(user(ORG_B), "talent", TALENT_ID)

    assert ("id", TALENT_ID) in client.queries[0].filters
    assert ("org_id", ORG_A) in client.queries[0].filters
    assert ("org_id", ORG_B) in client.queries[1].filters
    assert result_b.data == []


@pytest.mark.unit
def test_route_update_rejects_foreign_talent_without_mutation() -> None:
    """The route's A/B behavior is a 404/no-write boundary, not a global ID lookup."""
    client = RecordingSupabase([{"id": TALENT_ID, "org_id": ORG_A, "name": "A"}])
    with patch("backend.api_v1.supabase", client), patch("backend.database.supabase", client):
        result_a = v1_update_talent(TALENT_ID, {"name": "A2"}, user(ORG_A))
        with pytest.raises(HTTPException) as denied:
            v1_update_talent(TALENT_ID, {"name": "B2"}, user(ORG_B))

    assert result_a["org_id"] == ORG_A
    assert denied.value.status_code == 404
    assert ("org_id", ORG_B) in client.queries[-1].filters


@pytest.mark.unit
def test_authorized_client_strips_org_id_from_updates() -> None:
    """The shared privileged boundary preserves immutable organization ownership."""
    query = RecordingQuery("talent", [{"id": TALENT_ID, "org_id": ORG_A}])
    client = SimpleNamespace(table=lambda _table: query)
    context = TenantContext("user-1", ORG_A, OrgRole.OWNER)
    authorized = AuthorizedClient(context)
    with patch.object(authorized, "_get_client", return_value=client):
        authorized.update("talent", {"name": "safe", "org_id": ORG_B}, record_id=TALENT_ID)

    assert query.payload == {"name": "safe"}
    assert ("org_id", ORG_A) in query.filters


@pytest.mark.unit
def test_inherited_parent_check_blocks_cross_tenant_scene_insert() -> None:
    """A scene cannot be inserted under an episode owned by organization A from B."""
    client = RecordingSupabase([{"id": "episode-a", "org_id": ORG_A}])
    with patch("backend.database.supabase", client), pytest.raises(ValueError, match="not owned"):
        create_scene({"episode_id": "episode-a", "title": "foreign"}, ORG_B)

    assert len(client.queries) == 1
    assert ("org_id", ORG_B) in client.queries[0].filters


@pytest.mark.unit
def test_tenant_repo_refuses_unfiltered_inherited_collection() -> None:
    """Inherited child collections cannot fall back to an unscoped list."""
    client = RecordingSupabase([])
    context = TenantContext("user-1", ORG_B, OrgRole.OWNER)
    with patch("backend.tenant_repo.get_supabase_client", return_value=client):
        repo = TenantRepo(context)
        with pytest.raises(ValueError, match="requires a scene_id filter"):
            repo.list("shots")


@pytest.mark.unit
def test_storyboard_detail_update_delete_are_a_b_scoped() -> None:
    """A storyboard ID cannot be read, changed, or deleted by organization B."""
    client = RecordingSupabase([{"id": STORYBOARD_ID, "org_id": ORG_A, "name": "A"}])
    with patch("backend.api_v1.supabase", client):
        assert v1_get_storyboard(STORYBOARD_ID, user(ORG_A))["org_id"] == ORG_A
        with pytest.raises(HTTPException) as detail_denied:
            v1_get_storyboard(STORYBOARD_ID, user(ORG_B))
        with pytest.raises(HTTPException) as update_denied:
            v1_update_storyboard(STORYBOARD_ID, {"name": "B", "org_id": ORG_B}, user(ORG_B))
        with pytest.raises(HTTPException) as delete_denied:
            v1_delete_storyboard(STORYBOARD_ID, user(ORG_B))

    assert detail_denied.value.status_code == 404
    assert update_denied.value.status_code == 404
    assert delete_denied.value.status_code == 404
    assert all(
        ("org_id", ORG_B) in query.filters
        for query in client.queries[-3:]
    )


@pytest.mark.unit
def test_lora_collection_requires_owned_talent_before_child_reads() -> None:
    """LoRA reads cannot use a foreign talent ID as an unscoped child selector."""
    client = RecordingSupabase([{"id": TALENT_ID, "org_id": ORG_A}])
    with patch("backend.api_v1.supabase", client):
        allowed = v1_get_talent_loras(TALENT_ID, user(ORG_A))
        with pytest.raises(HTTPException) as denied:
            v1_get_talent_loras(TALENT_ID, user(ORG_B))

    assert allowed["total"] == 2
    assert denied.value.status_code == 404
    assert ("org_id", ORG_A) in client.queries[0].filters
    assert ("org_id", ORG_B) in client.queries[-1].filters


@pytest.mark.unit
def test_direct_api_supabase_calls_are_confined_to_tenant_helpers() -> None:
    """Every direct Supabase client call must stay in a tenant-safe helper.

    source-line shifts in api_v1.py must not require changes to this test.
    """
    import ast
    from pathlib import Path

    source_path = Path(__file__).parents[3] / "api_v1.py"
    tree = ast.parse(source_path.read_text())
    allowlisted_helpers = {
        "_tenant_select",
        "_tenant_insert",
        "_tenant_update",
        "_tenant_delete",
    }
    direct_calls: list[tuple[str | None, int]] = []

    class SupabaseCallVisitor(ast.NodeVisitor):
        """Collect direct Supabase calls with their lexical function owner."""

        def __init__(self) -> None:
            self.function_stack: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self.function_stack.append(node.name)
            self.generic_visit(node)
            self.function_stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self.function_stack.append(node.name)
            self.generic_visit(node)
            self.function_stack.pop()

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "supabase"
            ):
                owner = self.function_stack[-1] if self.function_stack else None
                direct_calls.append((owner, node.lineno))
            self.generic_visit(node)

    SupabaseCallVisitor().visit(tree)

    assert direct_calls
    assert all(owner in allowlisted_helpers for owner, _line in direct_calls), direct_calls


@pytest.mark.unit
def test_model_update_passes_only_trusted_org_and_rejects_foreign_row() -> None:
    """Model updates cannot use a client organization selector or foreign row."""
    empty = SimpleNamespace(data=[])
    with patch("backend.api_v1.update_model_record", return_value=empty) as update, pytest.raises(
        HTTPException
    ) as denied:
            v1_update_model("model-a", {"status": "archived", "org_id": ORG_A}, user(ORG_B))

    assert denied.value.status_code == 404
    update.assert_called_once_with(
        "model-a", {"status": "archived", "org_id": ORG_A}, ORG_B
    )
