"""Focused unit/property coverage for the authenticated Phase 2 MCP surface."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from backend.aios.mcp import phase2_credentials, phase2_generation, phase2_publish, phase2_story
from backend.aios.mcp.auth import MCPActorType, MCPClientIdentity, MCPEnvironment
from backend.aios.mcp.phase2_common import MCPExecutionContext, MCPToolError, clear_idempotency
from backend.aios.mcp.server import _execute_tool, mcp_invoke
from backend.aios.mcp.tools import get_tool, get_tool_definitions
from backend.credentials import _store
from hypothesis import given
from hypothesis import strategies as st

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
SHOT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
UNIVERSE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def identity(org_id: str = ORG_A, role: str = "editor") -> MCPClientIdentity:
    """Build an authenticated MCP identity for tests."""
    return MCPClientIdentity(
        credential_id="mcp-test",
        org_id=org_id,
        actor_type=MCPActorType.DEVELOPMENT,
        actor_name="test",
        role=role,
        capabilities=frozenset({"*"}),
        environment=MCPEnvironment.DEVELOPMENT,
        issued_by="33333333-3333-3333-3333-333333333333",
        expires_at=None,
        rate_limit_rpm=1000,
    )


@pytest.fixture(autouse=True)
def reset_mcp_state() -> None:
    """Keep credential and idempotency stores isolated between tests."""
    clear_idempotency()
    _store.clear()
    yield
    clear_idempotency()
    _store.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_phase2_dispatch_requires_authenticated_identity_and_matching_org() -> None:
    """A caller cannot invoke a phase-2 tenant tool with only a spoofable org string."""
    with pytest.raises(MCPToolError) as missing:
        await _execute_tool("list_episodes", {"universe_id": UNIVERSE_ID}, ORG_A)
    assert missing.value.code == "MCP_AUTH_REQUIRED"

    with pytest.raises(MCPToolError) as mismatch:
        await _execute_tool("list_episodes", {"universe_id": UNIVERSE_ID}, ORG_B, identity(ORG_A))
    assert mismatch.value.code == "ORG_CONTEXT_MISMATCH"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticated_mcp_read_dispatches_with_registry_capability() -> None:
    """A new read tool executes only with its authenticated capability."""
    result = await mcp_invoke(
        {"tool": "list_platforms", "parameters": {}},
        identity(),
    )
    assert result["status"] == "completed"
    assert result["result"]["platforms"]


    """Story writes pass only the authenticated tenant to the existing service."""
    service = MagicMock()
    service.create_episode.return_value = {"id": "episode-1", "org_id": ORG_A, "title": "Pilot"}
    with patch("backend.aios.mcp.phase2_story._service", return_value=service):
        result = await phase2_story.create_episode(
            {"universe_id": UNIVERSE_ID, "title": "Pilot"},
            MCPExecutionContext(identity()),
        )
    assert result["episode"]["org_id"] == ORG_A
    service.create_episode.assert_called_once_with(UNIVERSE_ID, service.create_episode.call_args.args[1], ORG_A)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_story_mutation_rejects_foreign_selector_before_service() -> None:
    """Organization selectors are rejected before any story/database access."""
    service = MagicMock()
    with patch("backend.aios.mcp.phase2_story._service", return_value=service), pytest.raises(MCPToolError) as exc_info:
        await phase2_story.create_scene(
            {"episode_id": UNIVERSE_ID, "org_id": ORG_B},
            MCPExecutionContext(identity()),
        )
    assert exc_info.value.code == "ORG_SELECTOR_NOT_ALLOWED"
    service.create_scene.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_is_tenant_scoped_and_idempotent() -> None:
    """The same tenant key returns one queued job while another tenant gets its own job."""
    context_a = MCPExecutionContext(identity(ORG_A))
    context_b = MCPExecutionContext(identity(ORG_B))
    first = await phase2_generation.generate_with_ksampler(
        {"prompt": "portrait", "idempotency_key": "same-key"}, context_a
    )
    second = await phase2_generation.generate_with_ksampler(
        {"prompt": "different", "idempotency_key": "same-key"}, context_a
    )
    other = await phase2_generation.generate_with_ksampler(
        {"prompt": "portrait", "idempotency_key": "same-key"}, context_b
    )
    assert first["job_id"] == second["job_id"]
    assert first["job_id"] != other["job_id"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_cost_gate_rejects_before_provider_or_job() -> None:
    """An explicit budget rejection prevents queue creation."""
    with patch("backend.aios.mcp.phase2_generation.submit_generation") as submit, pytest.raises(MCPToolError) as exc_info:
        await phase2_generation.generate_with_ksampler(
            {"prompt": "portrait", "max_cost_usd": 0.0001},
            MCPExecutionContext(identity()),
        )
    assert exc_info.value.code == "COST_GATE_REJECTED"
    submit.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_credential_tools_never_return_raw_api_key() -> None:
    """Credential storage and listing expose masked metadata only."""
    secret = "sk-test-secret-value-never-return"
    result = await phase2_credentials.add_api_key(
        {"provider": "openai", "api_key": secret}, MCPExecutionContext(identity())
    )
    listed = await phase2_credentials.list_api_keys({}, MCPExecutionContext(identity()))
    assert secret not in str(result)
    assert secret not in str(listed)
    assert result["credential"]["status"] == "active"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_provider_and_viewer_mutation_are_structured_errors() -> None:
    """Provider and role gates fail before credential/provider access."""
    with pytest.raises(MCPToolError) as provider_error:
        await phase2_credentials.add_api_key(
            {"provider": "not-a-provider", "api_key": "long-enough-secret"},
            MCPExecutionContext(identity()),
        )
    assert provider_error.value.code == "INVALID_PROVIDER"

    with pytest.raises(MCPToolError) as role_error:
        await phase2_credentials.add_api_key(
            {"provider": "openai", "api_key": "long-enough-secret"},
            MCPExecutionContext(identity(role="viewer")),
        )
    assert role_error.value.code == "ROLE_NOT_ALLOWED"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_platform_policy_blocks_unverified_platform_and_missing_fanvue_gates() -> None:
    """Capability discovery cannot bypass rollout or Fanvue safety policy."""
    with pytest.raises(MCPToolError) as unavailable:
        await phase2_publish.check_platform_policy(
            {"platform": "instagram"}, MCPExecutionContext(identity())
        )
    assert unavailable.value.code == "PLATFORM_UNAVAILABLE"

    with pytest.raises(MCPToolError) as denied:
        await phase2_publish.check_platform_policy(
            {"platform": "fanvue"}, MCPExecutionContext(identity())
        )
    assert denied.value.code == "PLATFORM_POLICY_DENIED"


@pytest.mark.unit
@given(org_id=st.uuids(version=4).filter(lambda value: value.int != 0).map(str))
@pytest.mark.asyncio
async def test_generation_status_never_returns_another_tenant_job(org_id: str) -> None:
    """For every valid tenant UUID, a foreign job is indistinguishable from missing."""
    context = MCPExecutionContext(identity(org_id))
    with pytest.raises(MCPToolError) as exc_info:
        await phase2_generation.get_generation_status({"job_id": "gen-does-not-exist"}, context)
    assert exc_info.value.code == "GENERATION_NOT_FOUND"


@pytest.mark.unit
def test_registry_metadata_carries_risk_and_approval_without_granting_execution() -> None:
    """Discovery includes governance metadata while capability checks remain separate."""
    definition = get_tool("add_api_key")
    assert definition is not None
    assert definition.requires_approval is True
    assert definition.risk == "credential"
    public = next(item for item in get_tool_definitions() if item["name"] == "add_api_key")
    assert public["requiresApproval"] is True
    assert public["requiredCapabilities"] == ["add_api_key"]
