"""Tenant isolation tests for the Brain executor bridge.

**Validates: Requirements 2.5, 2.9, 2.11, 2.13, 2.18, 3.4, 3.5**
**Validates: Property 1 - Bug Condition - Trusted Tenant Enforcement**
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from backend.aios.execution import tools
from hypothesis import given, settings
from hypothesis import strategies as st

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
TALENT_ID = "33333333-3333-3333-3333-333333333333"
ASSET_ID = "44444444-4444-4444-4444-444444444444"


class RecordingQuery:
    """Minimal Supabase query double that records filters and mutations."""

    def __init__(self, database: RecordingSupabase, table_name: str) -> None:
        self.database = database
        self.table_name = table_name
        self.filters: list[tuple[str, object]] = []
        self.inserted: dict | None = None

    def select(self, *_columns: object, **_kwargs: object) -> RecordingQuery:
        return self

    def insert(self, data: dict) -> RecordingQuery:
        self.inserted = data
        return self

    def eq(self, name: str, value: object) -> RecordingQuery:
        self.filters.append((name, value))
        return self

    def order(self, *_args: object, **_kwargs: object) -> RecordingQuery:
        return self

    def limit(self, _count: int) -> RecordingQuery:
        return self

    def is_(self, name: str, value: object) -> RecordingQuery:
        self.filters.append((name, value))
        return self

    def or_(self, _expression: str) -> RecordingQuery:
        return self

    def execute(self) -> SimpleNamespace:
        self.database.completed.append(self)
        org = dict(self.filters).get("org_id")
        if self.table_name == "assets" and org != ORG_A:
            return SimpleNamespace(data=[])
        if self.table_name == "talent":
            if self.inserted is not None:
                return SimpleNamespace(data=[self.inserted])
            if org not in {ORG_A, ORG_B}:
                return SimpleNamespace(data=[])
            return SimpleNamespace(data=[{"id": TALENT_ID, "org_id": org, "name": "A talent"}])
        if self.table_name == "assets":
            return SimpleNamespace(
                data=[{"id": ASSET_ID, "org_id": ORG_A, "talent_id": TALENT_ID}] * 5
            )
        if self.table_name == "publishing_posts":
            return SimpleNamespace(data=[self.inserted] if self.inserted else [])
        return SimpleNamespace(data=[])


class RecordingSupabase:
    """Supabase double retaining query filters for tenant assertions."""

    def __init__(self) -> None:
        self.queries: list[RecordingQuery] = []
        self.completed: list[RecordingQuery] = []

    def table(self, table_name: str) -> RecordingQuery:
        query = RecordingQuery(self, table_name)
        self.queries.append(query)
        return query


@pytest.mark.unit
@pytest.mark.asyncio
@given(tool_name=st.sampled_from(tuple(sorted(tools.TENANT_SCOPED_TOOLS))))
@settings(max_examples=12, deadline=None)
async def test_missing_trusted_org_is_rejected_before_executor_validation(tool_name: str) -> None:
    """Every tenant-aware executor rejects missing context before it is called."""
    executor_name = {
        "generate_image": "_exec_generate_image",
        "generate_video": "_exec_generate_video",
        "train_lora": "_exec_train_lora",
        "search_talent": "_exec_search_talent",
        "create_talent": "_exec_create_talent",
        "schedule_post": "_exec_schedule_post",
        "search_knowledge": "_exec_search_knowledge",
        "recommend_workflow": "_exec_recommend_workflow",
    }[tool_name]
    executor = getattr(tools, executor_name)
    with patch.object(tools, executor_name, new=AsyncMock(side_effect=AssertionError("called"))):
        result = await tools.execute_tool(tool_name, {"org_id": ORG_B})

    assert result["success"] is False
    assert "org_id" in result["error"]
    assert inspect.signature(executor).parameters["org_id"].default is inspect.Parameter.empty


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_talent_uses_trusted_org_and_ignores_selector() -> None:
    """A search uses the bridge organization, never a parameter organization."""
    database = RecordingSupabase()
    with patch("backend.database.supabase", database):
        result = await tools.execute_tool(
            "search_talent",
            {"query": "talent", "org_id": ORG_B, "organization_id": ORG_B},
            org_id=ORG_A,
        )

    assert result["success"] is True
    talent_query = next(query for query in database.completed if query.table_name == "talent")
    assert ("org_id", ORG_A) in talent_query.filters
    assert ("org_id", ORG_B) not in talent_query.filters


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_talent_inserts_only_trusted_org() -> None:
    """An insert overwrites hostile tenant selectors with the trusted org."""
    database = RecordingSupabase()
    with patch("backend.database.supabase", database):
        result = await tools.execute_tool(
            "create_talent",
            {"name": "new", "org_id": ORG_B, "organization_id": ORG_B},
            org_id=ORG_A,
        )

    assert result["success"] is True
    insert = next(query for query in database.completed if query.table_name == "talent")
    assert insert.inserted is not None
    assert insert.inserted["org_id"] == ORG_A


@pytest.mark.unit
@pytest.mark.asyncio
async def test_schedule_post_requires_owned_asset_and_scopes_post_insert() -> None:
    """Cross-tenant assets are rejected and posts carry trusted ownership."""
    database = RecordingSupabase()
    with patch("backend.database.supabase", database):
        denied = await tools.execute_tool(
            "schedule_post",
            {"content": "foreign", "asset_id": ASSET_ID},
            org_id=ORG_B,
        )
        allowed = await tools.execute_tool(
            "schedule_post",
            {"content": "owned", "asset_id": ASSET_ID, "org_id": ORG_B},
            org_id=ORG_A,
        )

    assert denied["success"] is True
    assert denied["status"] == "not_scheduled" if "status" in denied else "Asset" in denied["error"]
    assert allowed["success"] is True
    insert = next(query for query in database.completed if query.table_name == "publishing_posts")
    assert insert.inserted is not None
    assert insert.inserted["org_id"] == ORG_A


@pytest.mark.unit
@pytest.mark.asyncio
async def test_train_lora_scopes_talent_and_assets_to_trusted_org() -> None:
    """LoRA media lookup cannot read another organization’s assets."""
    database = RecordingSupabase()
    response = SimpleNamespace(status_code=400, text="test")
    with patch("backend.database.supabase", database), patch("httpx.post", return_value=response):
        result = await tools.execute_tool(
            "train_lora",
            {"talent_id": TALENT_ID, "steps": 10},
            org_id=ORG_A,
        )

    assert result["success"] is True
    assert any(
        query.table_name == "assets" and ("org_id", ORG_A) in query.filters
        for query in database.completed
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticated_mcp_dispatch_still_receives_org_context() -> None:
    """The existing MCP boundary keeps explicit authenticated org propagation."""
    from backend.aios.mcp import server

    observed: dict[str, str] = {}

    async def fake_search(params: dict, org_id: str) -> dict:
        observed["org_id"] = org_id
        return {"talents": []}

    with patch.object(server, "_exec_search_talent", new=fake_search):
        result = await server._execute_tool("search_talent", {}, ORG_A)

    assert result == {"talents": []}
    assert observed["org_id"] == ORG_A


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_knowledge_passes_trusted_org_and_ignores_selector() -> None:
    """Knowledge search receives only the bridge tenant, never parameter org_id."""
    with patch("backend.aios.knowledge.graph.search", return_value=[]) as search_mock:
        result = await tools.execute_tool(
            "search_knowledge",
            {"query": "workflow", "org_id": ORG_B, "organization_id": ORG_B},
            org_id=ORG_A,
        )

    assert result == {"success": True, "tool": "search_knowledge", "results": []}
    query, = search_mock.call_args.args
    assert search_mock.call_args.kwargs["org_id"] == ORG_A
    assert query.query == "workflow"
    assert query.include_vectors is False


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("org_id", "hostile_org_id"),
    [(ORG_A, ORG_B), (ORG_B, ORG_A)],
)
async def test_recommend_workflow_scopes_workflow_dna_to_each_trusted_org(
    org_id: str, hostile_org_id: str
) -> None:
    """Workflow recommendations use an application-layer organization filter."""
    database = RecordingSupabase()
    with patch("backend.database.supabase", database):
        result = await tools.execute_tool(
            "recommend_workflow",
            {"content_type": "image", "org_id": ORG_B},
            org_id=org_id,
        )

    assert result == {
        "success": True,
        "tool": "recommend_workflow",
        "recommendations": [],
    }
    workflow_query = next(
        query for query in database.completed if query.table_name == "workflow_dna"
    )
    assert ("org_id", org_id) in workflow_query.filters
    assert ("org_id", hostile_org_id) not in workflow_query.filters


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recommend_workflow_rejects_foreign_talent_before_query() -> None:
    """A talent selector must be proven owned before workflow recommendations."""
    with (
        patch("backend.database.get_talent_by_id", return_value=SimpleNamespace(data=[])) as owner,
        patch("backend.aios.knowledge.workflow_dna.recommend_workflow") as recommend,
    ):
        result = await tools.execute_tool(
            "recommend_workflow",
            {"content_type": "image", "talent_id": TALENT_ID},
            org_id=ORG_B,
        )

    assert result["success"] is True
    assert result["error"] == "Talent not found"
    owner.assert_called_once_with(TALENT_ID, ORG_B)
    recommend.assert_not_called()
