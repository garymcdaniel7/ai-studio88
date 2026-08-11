"""Unit tests for ConnectionPermissionService — access control and member departure.

Tests cover:
    - Viewer blocked from workspace connection creation (R85.6)
    - Editor can create user connections (R92.4)
    - Admin can create workspace connections (R85.6)
    - User with insufficient role denied access to connection (R85.7)
    - Tool policy deny blocks specific tool usage (R92.7)
    - Tool policy allow restricts to listed tools only
    - Member departure revokes user connections (R92.5)
    - Member departure leaves workspace connections intact (R96.2)
    - Empty allowed_roles means no one can use the connection (A2-013)
    - Empty tool_policy allows all tools by default

Requirements: R85.6, R85.7, R92.4, R92.5, R92.7, R96.2
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# =============================================================================
# Mock heavy dependencies before importing application modules.
# =============================================================================

_sa_mock = MagicMock()
_sa_mock.DateTime = MagicMock
_sa_mock.Float = MagicMock
_sa_mock.Integer = MagicMock
_sa_mock.String = MagicMock
_sa_mock.Text = MagicMock
_sa_mock.Boolean = MagicMock
_sa_mock.ForeignKey = MagicMock
_sa_mock.Index = MagicMock
_sa_mock.func = MagicMock()
_sa_mock.select = MagicMock()
_sa_mock.update = MagicMock()

_sa_orm_mock = MagicMock()
_sa_orm_mock.Mapped = MagicMock
_sa_orm_mock.mapped_column = MagicMock(return_value=None)
_sa_orm_mock.relationship = MagicMock(return_value=None)
_sa_orm_mock.DeclarativeBase = type("DeclarativeBase", (), {})

_sa_dialects_pg_mock = MagicMock()
_sa_dialects_pg_mock.UUID = MagicMock
_sa_dialects_pg_mock.JSONB = MagicMock
_sa_dialects_pg_mock.ARRAY = MagicMock

_sa_ext_asyncio_mock = MagicMock()
_sa_ext_asyncio_mock.AsyncEngine = MagicMock
_sa_ext_asyncio_mock.AsyncSession = MagicMock
_sa_ext_asyncio_mock.async_sessionmaker = MagicMock
_sa_ext_asyncio_mock.create_async_engine = MagicMock

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)

_sa_exc_mock = ModuleType("sqlalchemy.exc")


class _IntegrityError(Exception):
    def __init__(self, statement=None, params=None, orig=None):
        self.statement = statement
        self.params = params
        self.orig = orig
        super().__init__(str(orig) if orig else "IntegrityError")


_sa_exc_mock.IntegrityError = _IntegrityError  # type: ignore[attr-defined]
sys.modules.setdefault("sqlalchemy.exc", _sa_exc_mock)

# Mock app.db modules
_mock_db_module = ModuleType("app.db")
sys.modules.setdefault("app.db", _mock_db_module)

_mock_db_session = ModuleType("app.db.session")
_mock_db_session.get_db_session = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.session", _mock_db_session)

_mock_db_base = ModuleType("app.db.base")


class _MockBase:
    pass


class _MockTimestampMixin:
    pass


class _MockUUIDMixin:
    pass


class _MockTenantMixin:
    pass


class _MockSoftDeleteMixin:
    pass


_mock_db_base.Base = _MockBase  # type: ignore[attr-defined]
_mock_db_base.TimestampMixin = _MockTimestampMixin  # type: ignore[attr-defined]
_mock_db_base.UUIDMixin = _MockUUIDMixin  # type: ignore[attr-defined]
_mock_db_base.TenantMixin = _MockTenantMixin  # type: ignore[attr-defined]
_mock_db_base.SoftDeleteMixin = _MockSoftDeleteMixin  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.base", _mock_db_base)

# Mock app.db.tenant_scope
_mock_tenant_scope = ModuleType("app.db.tenant_scope")
_mock_tenant_scope.QUARANTINED_ORG_ID = UUID(  # type: ignore[attr-defined]
    "00000000-0000-0000-0000-000000000000"
)
_mock_tenant_scope.TenantScopedRepository = MagicMock()  # type: ignore[attr-defined]
_mock_tenant_scope.validate_org_id = MagicMock()  # type: ignore[attr-defined]
_mock_tenant_scope.tenant_filter = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.tenant_scope", _mock_tenant_scope)

# Mock app.models package
_mock_models_pkg = ModuleType("app.models")
_mock_models_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.models", _mock_models_pkg)

# app.models.connection — provide real enum values
_mock_models_connection = ModuleType("app.models.connection")

from enum import Enum


class _ConnectionOwnership(str, Enum):
    USER = "user"
    WORKSPACE = "workspace"


class _ConnectionLifecycle(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    REAUTH_REQUIRED = "reauth_required"
    DISCONNECTED = "disconnected"
    REVOKED = "revoked"


class _ConnectionCategory(str, Enum):
    AI_PROVIDER = "ai_provider"
    STORAGE = "storage"
    SOCIAL = "social"
    COMPUTE = "compute"
    DEVELOPER = "developer"
    BUSINESS = "business"


class _ConnectionAuthMethod(str, Enum):
    OAUTH = "oauth"
    API_KEY = "api_key"
    SSH = "ssh"
    MCP = "mcp"


class _MockConnection:
    """Mock Connection ORM model."""

    __tablename__ = "connections"


_mock_models_connection.Connection = _MockConnection  # type: ignore[attr-defined]
_mock_models_connection.ConnectionOwnership = _ConnectionOwnership  # type: ignore[attr-defined]
_mock_models_connection.ConnectionLifecycle = _ConnectionLifecycle  # type: ignore[attr-defined]
_mock_models_connection.ConnectionCategory = _ConnectionCategory  # type: ignore[attr-defined]
_mock_models_connection.ConnectionAuthMethod = _ConnectionAuthMethod  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.connection", _mock_models_connection)

# Mock other models that may be imported transitively
_mock_models_job = ModuleType("app.models.job")
_mock_models_job.Job = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.job", _mock_models_job)

_mock_models_job_lease = ModuleType("app.models.job_lease")
_mock_models_job_lease.JobLease = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.job_lease", _mock_models_job_lease)

# Mock repository module
_mock_repo_module = ModuleType("app.repositories")
_mock_repo_module.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.repositories", _mock_repo_module)

_mock_conn_repo = ModuleType("app.repositories.connection_repository")
_mock_conn_repo.ConnectionRepository = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.repositories.connection_repository", _mock_conn_repo)

# Now import the service under test
from app.services.connection_permission_service import (
    ConnectionCreationDenied,
    ConnectionPermissionDenied,
    ConnectionPermissionService,
    ConnectionToolDenied,
    MemberDepartureResult,
)


# =============================================================================
# Fixtures
# =============================================================================

ORG_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")
DEPARTING_USER_ID = UUID("55555555-5555-5555-5555-555555555555")


def _make_mock_connection(
    connection_id: UUID | None = None,
    lifecycle_state: str = "connected",
    ownership: str = "workspace",
    allowed_roles: list[str] | None = None,
    tool_policy: dict | None = None,
    user_id: UUID | None = None,
    **kwargs,
) -> MagicMock:
    """Create a mock Connection ORM instance."""
    conn = MagicMock()
    conn.id = connection_id or uuid4()
    conn.org_id = ORG_ID
    conn.lifecycle_state = lifecycle_state
    conn.ownership = ownership
    conn.allowed_roles = allowed_roles if allowed_roles is not None else ["owner", "admin", "editor"]
    conn.tool_policy = tool_policy if tool_policy is not None else {}
    conn.user_id = user_id
    conn.provider_name = kwargs.get("provider_name", "openai")
    conn.display_name = kwargs.get("display_name", "Test Connection")
    conn.category = kwargs.get("category", "ai_provider")
    return conn


@pytest.fixture
def mock_repo():
    """Mock ConnectionRepository."""
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    """Create a ConnectionPermissionService with mocked repository."""
    return ConnectionPermissionService(repo=mock_repo)


# =============================================================================
# Tests: Connection Creation Permission (R85.6, R92.4)
# =============================================================================


class TestCreationPermission:
    """Tests for connection creation role requirements."""

    def test_viewer_blocked_from_workspace_connection_creation(self, service):
        """Viewer cannot create workspace connections (R85.6).

        Workspace connections require admin or owner role.
        """
        with pytest.raises(ConnectionCreationDenied) as exc_info:
            service.check_creation_permission(
                ownership="workspace",
                user_role="viewer",
            )

        assert "admin or owner" in exc_info.value.message
        assert exc_info.value.code == "CONNECTION_CREATION_DENIED"

    def test_editor_blocked_from_workspace_connection_creation(self, service):
        """Editor cannot create workspace connections (R85.6).

        Workspace connections require admin or owner — editor is insufficient.
        """
        with pytest.raises(ConnectionCreationDenied) as exc_info:
            service.check_creation_permission(
                ownership="workspace",
                user_role="editor",
            )

        assert "admin or owner" in exc_info.value.message

    def test_admin_can_create_workspace_connections(self, service):
        """Admin can create workspace connections (R85.6)."""
        result = service.check_creation_permission(
            ownership="workspace",
            user_role="admin",
        )
        assert result is True

    def test_owner_can_create_workspace_connections(self, service):
        """Owner can create workspace connections (R85.6)."""
        result = service.check_creation_permission(
            ownership="workspace",
            user_role="owner",
        )
        assert result is True

    def test_editor_can_create_user_connections(self, service):
        """Editor can create user connections (R92.4).

        Any authenticated member (editor+) can create personal connections.
        """
        result = service.check_creation_permission(
            ownership="user",
            user_role="editor",
        )
        assert result is True

    def test_admin_can_create_user_connections(self, service):
        """Admin can create user connections."""
        result = service.check_creation_permission(
            ownership="user",
            user_role="admin",
        )
        assert result is True

    def test_owner_can_create_user_connections(self, service):
        """Owner can create user connections."""
        result = service.check_creation_permission(
            ownership="user",
            user_role="owner",
        )
        assert result is True

    def test_viewer_blocked_from_user_connection_creation(self, service):
        """Viewer cannot create user connections (editor+ required)."""
        with pytest.raises(ConnectionCreationDenied) as exc_info:
            service.check_creation_permission(
                ownership="user",
                user_role="viewer",
            )

        assert "editor" in exc_info.value.message


# =============================================================================
# Tests: Connection Access Check (R85.7, R92.5)
# =============================================================================


class TestConnectionAccess:
    """Tests for connection access role verification."""

    def test_user_with_allowed_role_granted_access(self, service):
        """User whose role is in allowed_roles can access connection."""
        connection = _make_mock_connection(
            allowed_roles=["owner", "admin", "editor"],
        )

        result = service.check_connection_access(connection, user_role="editor")
        assert result is True

    def test_user_with_insufficient_role_denied_access(self, service):
        """User whose role is NOT in allowed_roles is denied (R85.7)."""
        connection = _make_mock_connection(
            allowed_roles=["owner", "admin"],
        )

        with pytest.raises(ConnectionPermissionDenied) as exc_info:
            service.check_connection_access(connection, user_role="editor")

        assert "editor" in exc_info.value.message
        assert exc_info.value.code == "CONNECTION_PERMISSION_DENIED"

    def test_viewer_denied_access_to_standard_connection(self, service):
        """Viewer denied access to connection with default roles (owner/admin/editor)."""
        connection = _make_mock_connection(
            allowed_roles=["owner", "admin", "editor"],
        )

        with pytest.raises(ConnectionPermissionDenied):
            service.check_connection_access(connection, user_role="viewer")

    def test_empty_allowed_roles_denies_everyone(self, service):
        """Connection with empty allowed_roles is usable by no one (A2-013).

        Connection existence alone never grants capabilities.
        """
        connection = _make_mock_connection(allowed_roles=[])

        with pytest.raises(ConnectionPermissionDenied):
            service.check_connection_access(connection, user_role="owner")

    def test_owner_granted_when_in_allowed_roles(self, service):
        """Owner can access when explicitly in allowed_roles."""
        connection = _make_mock_connection(
            allowed_roles=["owner"],
        )

        result = service.check_connection_access(connection, user_role="owner")
        assert result is True

    def test_none_allowed_roles_denies_access(self, service):
        """None value for allowed_roles treated as empty (denies all)."""
        connection = _make_mock_connection(allowed_roles=None)
        # Override the mock to return None for allowed_roles
        connection.allowed_roles = None

        with pytest.raises(ConnectionPermissionDenied):
            service.check_connection_access(connection, user_role="owner")


# =============================================================================
# Tests: Tool Policy Check (R85.7, R92.7)
# =============================================================================


class TestToolPermission:
    """Tests for tool-level permission enforcement via tool_policy."""

    def test_empty_policy_allows_all_tools(self, service):
        """Empty tool_policy allows all tool invocations."""
        connection = _make_mock_connection(tool_policy={})

        result = service.check_tool_permission(connection, tool_name="chat")
        assert result is True

    def test_deny_list_blocks_specific_tool(self, service):
        """Tool in deny list is explicitly blocked (R92.7)."""
        connection = _make_mock_connection(
            tool_policy={"deny": ["publish_media", "delete_post"]},
        )

        with pytest.raises(ConnectionToolDenied) as exc_info:
            service.check_tool_permission(connection, tool_name="publish_media")

        assert exc_info.value.tool_name == "publish_media"
        assert "explicitly denied" in exc_info.value.message
        assert exc_info.value.code == "CONNECTION_TOOL_DENIED"

    def test_deny_list_allows_unlisted_tools(self, service):
        """Tools NOT in deny list are permitted."""
        connection = _make_mock_connection(
            tool_policy={"deny": ["publish_media"]},
        )

        result = service.check_tool_permission(connection, tool_name="read_profile")
        assert result is True

    def test_allow_list_restricts_to_listed_tools(self, service):
        """Only tools in allow list are permitted."""
        connection = _make_mock_connection(
            tool_policy={"allow": ["chat", "embeddings"]},
        )

        result = service.check_tool_permission(connection, tool_name="chat")
        assert result is True

    def test_allow_list_blocks_unlisted_tools(self, service):
        """Tools not in allow list are denied."""
        connection = _make_mock_connection(
            tool_policy={"allow": ["chat", "embeddings"]},
        )

        with pytest.raises(ConnectionToolDenied) as exc_info:
            service.check_tool_permission(connection, tool_name="fine_tuning")

        assert exc_info.value.tool_name == "fine_tuning"
        assert "not in the connection's allow list" in exc_info.value.message

    def test_deny_takes_precedence_over_allow(self, service):
        """Deny list takes precedence when both allow and deny are present."""
        connection = _make_mock_connection(
            tool_policy={
                "allow": ["chat", "publish_media"],
                "deny": ["publish_media"],
            },
        )

        # publish_media is in both allow AND deny — deny wins
        with pytest.raises(ConnectionToolDenied):
            service.check_tool_permission(connection, tool_name="publish_media")

    def test_none_policy_allows_all(self, service):
        """None tool_policy (treated as empty dict) allows all tools."""
        connection = _make_mock_connection(tool_policy=None)
        connection.tool_policy = None

        result = service.check_tool_permission(connection, tool_name="anything")
        assert result is True


# =============================================================================
# Tests: Combined Access + Tool Check
# =============================================================================


class TestCombinedPermissions:
    """Tests for the full permission check flow (role + tool_policy)."""

    def test_must_pass_both_role_and_tool_check(self, service):
        """Tool invocation requires passing BOTH allowed_roles AND tool_policy."""
        connection = _make_mock_connection(
            allowed_roles=["owner", "admin", "editor"],
            tool_policy={"deny": ["dangerous_tool"]},
        )

        # Role check passes
        service.check_connection_access(connection, user_role="editor")

        # Tool check fails
        with pytest.raises(ConnectionToolDenied):
            service.check_tool_permission(connection, tool_name="dangerous_tool")

    def test_role_denied_even_if_tool_would_pass(self, service):
        """Role denial blocks access regardless of tool_policy."""
        connection = _make_mock_connection(
            allowed_roles=["owner", "admin"],
            tool_policy={},  # All tools allowed
        )

        # Role check fails for editor
        with pytest.raises(ConnectionPermissionDenied):
            service.check_connection_access(connection, user_role="editor")


# =============================================================================
# Tests: Member Departure (R92.5, R92.7, R96.2)
# =============================================================================


class TestMemberDeparture:
    """Tests for member departure connection handling."""

    @pytest.mark.asyncio
    async def test_departure_revokes_user_connections(self, service, mock_repo):
        """Member departure revokes all USER_CONNECTIONs owned by departing user (R92.5)."""
        user_conn_1 = _make_mock_connection(
            connection_id=uuid4(),
            ownership="user",
            lifecycle_state="connected",
            user_id=DEPARTING_USER_ID,
        )
        user_conn_2 = _make_mock_connection(
            connection_id=uuid4(),
            ownership="user",
            lifecycle_state="connected",
            user_id=DEPARTING_USER_ID,
        )
        mock_repo.list_all.side_effect = [
            # First call: user connections for departing user
            ([user_conn_1, user_conn_2], 2),
            # Second call: workspace connections
            ([], 0),
        ]
        mock_repo.update_lifecycle_state.return_value = MagicMock()

        result = await service.process_member_departure(
            org_id=ORG_ID,
            departing_user_id=DEPARTING_USER_ID,
        )

        assert len(result.revoked_connection_ids) == 2
        assert user_conn_1.id in result.revoked_connection_ids
        assert user_conn_2.id in result.revoked_connection_ids

        # Verify each was set to 'revoked'
        assert mock_repo.update_lifecycle_state.call_count == 2
        for call in mock_repo.update_lifecycle_state.call_args_list:
            assert call[1]["new_state"] == "revoked"

    @pytest.mark.asyncio
    async def test_departure_leaves_workspace_connections_intact(self, service, mock_repo):
        """Member departure does NOT affect workspace connections (R96.2)."""
        workspace_conn = _make_mock_connection(
            connection_id=uuid4(),
            ownership="workspace",
            lifecycle_state="connected",
        )
        mock_repo.list_all.side_effect = [
            # First call: user connections (none for this user)
            ([], 0),
            # Second call: workspace connections
            ([workspace_conn], 1),
        ]

        result = await service.process_member_departure(
            org_id=ORG_ID,
            departing_user_id=DEPARTING_USER_ID,
        )

        assert len(result.revoked_connection_ids) == 0
        assert len(result.preserved_connection_ids) == 1
        assert workspace_conn.id in result.preserved_connection_ids

        # No state transitions should have been called
        mock_repo.update_lifecycle_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_departure_skips_already_revoked_connections(self, service, mock_repo):
        """Already-revoked user connections are not re-transitioned."""
        already_revoked = _make_mock_connection(
            connection_id=uuid4(),
            ownership="user",
            lifecycle_state="revoked",
            user_id=DEPARTING_USER_ID,
        )
        mock_repo.list_all.side_effect = [
            ([already_revoked], 1),
            ([], 0),
        ]

        result = await service.process_member_departure(
            org_id=ORG_ID,
            departing_user_id=DEPARTING_USER_ID,
        )

        # The connection is still counted as revoked but state not re-set
        assert len(result.revoked_connection_ids) == 1
        mock_repo.update_lifecycle_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_departure_flags_for_reauth(self, service, mock_repo):
        """Active user connections are flagged for scheduled ops pause."""
        active_conn = _make_mock_connection(
            connection_id=uuid4(),
            ownership="user",
            lifecycle_state="connected",
            user_id=DEPARTING_USER_ID,
        )
        mock_repo.list_all.side_effect = [
            ([active_conn], 1),
            ([], 0),
        ]
        mock_repo.update_lifecycle_state.return_value = MagicMock()

        result = await service.process_member_departure(
            org_id=ORG_ID,
            departing_user_id=DEPARTING_USER_ID,
        )

        assert len(result.flagged_for_reauth) == 1
        assert active_conn.id in result.flagged_for_reauth

    @pytest.mark.asyncio
    async def test_departure_mixed_connections(self, service, mock_repo):
        """Departure correctly handles a mix of user and workspace connections."""
        user_active = _make_mock_connection(
            connection_id=uuid4(),
            ownership="user",
            lifecycle_state="connected",
            user_id=DEPARTING_USER_ID,
        )
        user_degraded = _make_mock_connection(
            connection_id=uuid4(),
            ownership="user",
            lifecycle_state="degraded",
            user_id=DEPARTING_USER_ID,
        )
        workspace_active = _make_mock_connection(
            connection_id=uuid4(),
            ownership="workspace",
            lifecycle_state="connected",
        )
        workspace_degraded = _make_mock_connection(
            connection_id=uuid4(),
            ownership="workspace",
            lifecycle_state="degraded",
        )

        mock_repo.list_all.side_effect = [
            # User connections for departing user
            ([user_active, user_degraded], 2),
            # Workspace connections
            ([workspace_active, workspace_degraded], 2),
        ]
        mock_repo.update_lifecycle_state.return_value = MagicMock()

        result = await service.process_member_departure(
            org_id=ORG_ID,
            departing_user_id=DEPARTING_USER_ID,
        )

        # Both user connections revoked
        assert len(result.revoked_connection_ids) == 2
        # Both workspace connections preserved
        assert len(result.preserved_connection_ids) == 2
        # Active user connections flagged
        assert len(result.flagged_for_reauth) == 2
        # Only user connections had state transitions
        assert mock_repo.update_lifecycle_state.call_count == 2

    @pytest.mark.asyncio
    async def test_departure_no_connections(self, service, mock_repo):
        """Departure for user with no connections returns empty result."""
        mock_repo.list_all.side_effect = [
            ([], 0),
            ([], 0),
        ]

        result = await service.process_member_departure(
            org_id=ORG_ID,
            departing_user_id=DEPARTING_USER_ID,
        )

        assert result.revoked_connection_ids == []
        assert result.preserved_connection_ids == []
        assert result.flagged_for_reauth == []
