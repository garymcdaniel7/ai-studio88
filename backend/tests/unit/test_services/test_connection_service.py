"""Unit tests for ConnectionService — lifecycle, OAuth, and API key flows.

Tests cover:
    - initiate_oauth creates a CONNECTING connection and returns redirect_url
    - initiate_oauth rejects unsupported providers
    - initiate_oauth rejects duplicate connections
    - complete_oauth_callback transitions to CONNECTED with capabilities
    - complete_oauth_callback rejects non-CONNECTING connections
    - create_api_key_connection validates and stores key
    - create_api_key_connection rejects invalid keys
    - create_api_key_connection rejects duplicates
    - transition_state validates allowed transitions
    - transition_state rejects invalid transitions
    - update_health auto-transitions lifecycle on degradation
    - delete_connection transitions to DISCONNECTED before removal
    - list_connections returns paginated results
    - get_connection returns a single connection

Requirements: R85.2, R85.4, R85.5, R85.6, R27.4, R27.6, R92.6
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

# Mock app.db.base with real-enough mixins
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
    pass

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

_mock_models_talent = ModuleType("app.models.talent")
_mock_models_talent.AiTalent = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.talent", _mock_models_talent)

_mock_models_asset = ModuleType("app.models.asset")
_mock_models_asset.Asset = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.asset", _mock_models_asset)

# Mock repository module
_mock_repo_module = ModuleType("app.repositories")
_mock_repo_module.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.repositories", _mock_repo_module)

_mock_conn_repo = ModuleType("app.repositories.connection_repository")
_mock_conn_repo.ConnectionRepository = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.repositories.connection_repository", _mock_conn_repo)

# Now import application modules under test
from app.services.connection_service import (
    ConnectionService,
    ConnectionServiceError,
    DuplicateConnectionError,
    InvalidStateTransitionError,
    VALID_TRANSITIONS,
)


# =============================================================================
# Fixtures
# =============================================================================

ORG_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")
CONN_ID = UUID("33333333-3333-3333-3333-333333333333")
TOKEN_REF = UUID("44444444-4444-4444-4444-444444444444")


def _make_mock_connection(
    connection_id: UUID = CONN_ID,
    lifecycle_state: str = "connecting",
    provider_name: str = "instagram",
    auth_method: str = "oauth",
    ownership: str = "workspace",
    org_id: UUID = ORG_ID,
    capabilities: list | None = None,
    **kwargs,
) -> MagicMock:
    """Create a mock Connection ORM instance."""
    conn = MagicMock()
    conn.id = connection_id
    conn.org_id = org_id
    conn.lifecycle_state = lifecycle_state
    conn.provider_name = provider_name
    conn.auth_method = auth_method
    conn.ownership = ownership
    conn.capabilities = capabilities or []
    conn.oauth_token_ref = kwargs.get("oauth_token_ref")
    conn.user_id = kwargs.get("user_id")
    conn.display_name = kwargs.get("display_name", "Test Connection")
    conn.category = kwargs.get("category", "social")
    conn.health_status = kwargs.get("health_status")
    conn.last_health_check_at = kwargs.get("last_health_check_at")
    conn.allowed_roles = kwargs.get("allowed_roles", ["owner", "admin", "editor"])
    conn.tool_policy = kwargs.get("tool_policy", {})
    return conn


@pytest.fixture
def mock_db():
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def mock_repo():
    """Mock ConnectionRepository."""
    return AsyncMock()


@pytest.fixture
def service(mock_db, mock_repo):
    """Create a ConnectionService with mocked repository."""
    with patch(
        "app.services.connection_service.ConnectionRepository",
        return_value=mock_repo,
    ):
        svc = ConnectionService(db=mock_db, org_id=ORG_ID)
        svc._repo = mock_repo
        return svc


# =============================================================================
# Tests: OAuth Flow
# =============================================================================


class TestOAuthInitiation:
    """Tests for OAuth flow initiation (R85.2, R27.4)."""

    @pytest.mark.asyncio
    async def test_initiate_oauth_success(self, service, mock_repo):
        """OAuth initiation creates CONNECTING connection and returns redirect_url."""
        mock_connection = _make_mock_connection()
        mock_repo.find_by_provider.return_value = None
        mock_repo.create.return_value = mock_connection

        result = await service.initiate_oauth(
            provider_name="instagram",
            category="social",
            ownership="workspace",
            display_name="My Instagram",
            user_id=USER_ID,
        )

        assert "redirect_url" in result
        assert "connection_id" in result
        assert "state" in result
        assert "instagram.com/oauth" in result["redirect_url"]
        mock_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_initiate_oauth_unsupported_provider(self, service, mock_repo):
        """OAuth initiation rejects unsupported providers with 422."""
        from fastapi import HTTPException

        mock_repo.find_by_provider.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.initiate_oauth(
                provider_name="unknown_provider",
                category="social",
                ownership="workspace",
                display_name="Unknown",
                user_id=USER_ID,
            )

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_initiate_oauth_duplicate_connection(self, service, mock_repo):
        """OAuth initiation rejects if active connection exists (409)."""
        from fastapi import HTTPException

        existing = _make_mock_connection(lifecycle_state="connected")
        mock_repo.find_by_provider.return_value = existing

        with pytest.raises(HTTPException) as exc_info:
            await service.initiate_oauth(
                provider_name="instagram",
                category="social",
                ownership="workspace",
                display_name="My Instagram",
                user_id=USER_ID,
            )

        assert exc_info.value.status_code == 409


class TestOAuthCallback:
    """Tests for OAuth callback completion."""

    @pytest.mark.asyncio
    async def test_complete_callback_success(self, service, mock_repo):
        """Callback exchanges code, stores token, discovers capabilities, transitions to CONNECTED."""
        connecting = _make_mock_connection(lifecycle_state="connecting")
        connected = _make_mock_connection(
            lifecycle_state="connected",
            capabilities=["read_profile", "read_media", "publish_media"],
            oauth_token_ref=TOKEN_REF,
        )
        mock_repo.get_by_id.return_value = connecting
        mock_repo.update_fields.return_value = connected

        result = await service.complete_oauth_callback(
            connection_id=CONN_ID,
            auth_code="test_auth_code_123",
        )

        assert result.lifecycle_state == "connected"
        mock_repo.update_fields.assert_called_once()
        call_kwargs = mock_repo.update_fields.call_args[1]
        assert call_kwargs["lifecycle_state"] == "connected"

    @pytest.mark.asyncio
    async def test_complete_callback_rejects_non_connecting(self, service, mock_repo):
        """Callback rejects connections not in CONNECTING state."""
        from fastapi import HTTPException

        already_connected = _make_mock_connection(lifecycle_state="connected")
        mock_repo.get_by_id.return_value = already_connected

        with pytest.raises(HTTPException) as exc_info:
            await service.complete_oauth_callback(
                connection_id=CONN_ID,
                auth_code="test_auth_code",
            )

        assert exc_info.value.status_code == 409


# =============================================================================
# Tests: API Key Flow
# =============================================================================


class TestApiKeyConnection:
    """Tests for API key connection creation (R27.6)."""

    @pytest.mark.asyncio
    async def test_create_api_key_success(self, service, mock_repo):
        """API key connection validates, stores encrypted, discovers capabilities."""
        mock_repo.find_by_provider.return_value = None
        connected = _make_mock_connection(
            lifecycle_state="connected",
            auth_method="api_key",
            provider_name="openai",
            capabilities=["chat", "embeddings"],
        )
        mock_repo.create.return_value = connected

        result = await service.create_api_key_connection(
            provider_name="openai",
            category="ai_provider",
            ownership="user",
            display_name="My OpenAI",
            api_key="sk-valid-test-key-1234567890abcdef",
            user_id=USER_ID,
        )

        assert result.lifecycle_state == "connected"
        mock_repo.create.assert_called_once()
        # Verify key is NOT in the created record (never redisplayed)
        call_kwargs = mock_repo.create.call_args[1]
        assert "api_key" not in call_kwargs

    @pytest.mark.asyncio
    async def test_create_api_key_invalid_key(self, service, mock_repo):
        """API key validation failure returns 422."""
        from fastapi import HTTPException

        mock_repo.find_by_provider.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.create_api_key_connection(
                provider_name="openai",
                category="ai_provider",
                ownership="user",
                display_name="My OpenAI",
                api_key="short",  # Too short — fails validation
                user_id=USER_ID,
            )

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_api_key_duplicate(self, service, mock_repo):
        """API key connection rejects duplicates with 409."""
        from fastapi import HTTPException

        existing = _make_mock_connection(lifecycle_state="connected")
        mock_repo.find_by_provider.return_value = existing

        with pytest.raises(HTTPException) as exc_info:
            await service.create_api_key_connection(
                provider_name="openai",
                category="ai_provider",
                ownership="user",
                display_name="My OpenAI",
                api_key="sk-valid-test-key-1234567890abcdef",
                user_id=USER_ID,
            )

        assert exc_info.value.status_code == 409


# =============================================================================
# Tests: Lifecycle State Transitions
# =============================================================================


class TestLifecycleTransitions:
    """Tests for connection lifecycle state machine (R85.4, R92.6)."""

    @pytest.mark.asyncio
    async def test_valid_transition_connecting_to_connected(self, service, mock_repo):
        """CONNECTING → CONNECTED is a valid transition."""
        connecting = _make_mock_connection(lifecycle_state="connecting")
        connected = _make_mock_connection(lifecycle_state="connected")
        mock_repo.get_by_id.return_value = connecting
        mock_repo.update_lifecycle_state.return_value = connected

        result = await service.transition_state(CONN_ID, "connected")
        assert result.lifecycle_state == "connected"

    @pytest.mark.asyncio
    async def test_valid_transition_connected_to_degraded(self, service, mock_repo):
        """CONNECTED → DEGRADED is a valid transition."""
        connected = _make_mock_connection(lifecycle_state="connected")
        degraded = _make_mock_connection(lifecycle_state="degraded")
        mock_repo.get_by_id.return_value = connected
        mock_repo.update_lifecycle_state.return_value = degraded

        result = await service.transition_state(CONN_ID, "degraded")
        assert result.lifecycle_state == "degraded"

    @pytest.mark.asyncio
    async def test_valid_transition_connected_to_reauth(self, service, mock_repo):
        """CONNECTED → REAUTH_REQUIRED is a valid transition."""
        connected = _make_mock_connection(lifecycle_state="connected")
        reauth = _make_mock_connection(lifecycle_state="reauth_required")
        mock_repo.get_by_id.return_value = connected
        mock_repo.update_lifecycle_state.return_value = reauth

        result = await service.transition_state(CONN_ID, "reauth_required")
        assert result.lifecycle_state == "reauth_required"

    @pytest.mark.asyncio
    async def test_invalid_transition_revoked_to_connected(self, service, mock_repo):
        """REVOKED → CONNECTED is NOT valid (REVOKED is terminal)."""
        revoked = _make_mock_connection(lifecycle_state="revoked")
        mock_repo.get_by_id.return_value = revoked

        with pytest.raises(InvalidStateTransitionError):
            await service.transition_state(CONN_ID, "connected")

    @pytest.mark.asyncio
    async def test_invalid_transition_connecting_to_degraded(self, service, mock_repo):
        """CONNECTING → DEGRADED is NOT valid."""
        connecting = _make_mock_connection(lifecycle_state="connecting")
        mock_repo.get_by_id.return_value = connecting

        with pytest.raises(InvalidStateTransitionError):
            await service.transition_state(CONN_ID, "degraded")

    @pytest.mark.asyncio
    async def test_disconnected_can_reconnect(self, service, mock_repo):
        """DISCONNECTED → CONNECTING is valid (reconnection flow)."""
        disconnected = _make_mock_connection(lifecycle_state="disconnected")
        connecting = _make_mock_connection(lifecycle_state="connecting")
        mock_repo.get_by_id.return_value = disconnected
        mock_repo.update_lifecycle_state.return_value = connecting

        result = await service.transition_state(CONN_ID, "connecting")
        assert result.lifecycle_state == "connecting"


# =============================================================================
# Tests: Health Monitoring
# =============================================================================


class TestHealthMonitoring:
    """Tests for health-based lifecycle transitions."""

    @pytest.mark.asyncio
    async def test_unreachable_triggers_degraded(self, service, mock_repo):
        """Health 'unreachable' auto-transitions CONNECTED → DEGRADED."""
        connected = _make_mock_connection(lifecycle_state="connected")
        degraded = _make_mock_connection(lifecycle_state="degraded")
        mock_repo.update_health.return_value = connected
        mock_repo.get_by_id.side_effect = [connected, degraded]
        mock_repo.update_lifecycle_state.return_value = degraded

        result = await service.update_health(CONN_ID, "unreachable")
        mock_repo.update_lifecycle_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_auth_expired_triggers_reauth(self, service, mock_repo):
        """Health 'auth_expired' auto-transitions to REAUTH_REQUIRED."""
        connected = _make_mock_connection(lifecycle_state="connected")
        reauth = _make_mock_connection(lifecycle_state="reauth_required")
        mock_repo.update_health.return_value = connected
        mock_repo.get_by_id.side_effect = [connected, reauth]
        mock_repo.update_lifecycle_state.return_value = reauth

        result = await service.update_health(CONN_ID, "auth_expired")
        mock_repo.update_lifecycle_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_healthy_restores_degraded(self, service, mock_repo):
        """Health 'healthy' auto-transitions DEGRADED → CONNECTED."""
        degraded = _make_mock_connection(lifecycle_state="degraded")
        connected = _make_mock_connection(lifecycle_state="connected")
        mock_repo.update_health.return_value = degraded
        mock_repo.get_by_id.side_effect = [degraded, connected]
        mock_repo.update_lifecycle_state.return_value = connected

        result = await service.update_health(CONN_ID, "healthy")
        mock_repo.update_lifecycle_state.assert_called_once()


# =============================================================================
# Tests: Delete Connection
# =============================================================================


class TestDeleteConnection:
    """Tests for connection deletion."""

    @pytest.mark.asyncio
    async def test_delete_transitions_to_disconnected(self, service, mock_repo):
        """Delete transitions CONNECTED → DISCONNECTED before removal."""
        connected = _make_mock_connection(lifecycle_state="connected")
        disconnected = _make_mock_connection(lifecycle_state="disconnected")
        mock_repo.get_by_id.side_effect = [connected, connected]
        mock_repo.update_lifecycle_state.return_value = disconnected
        mock_repo.delete.return_value = None

        await service.delete_connection(CONN_ID)
        mock_repo.delete.assert_called_once_with(CONN_ID)

    @pytest.mark.asyncio
    async def test_delete_already_disconnected(self, service, mock_repo):
        """Delete skips transition if already DISCONNECTED."""
        disconnected = _make_mock_connection(lifecycle_state="disconnected")
        mock_repo.get_by_id.return_value = disconnected
        mock_repo.delete.return_value = None

        await service.delete_connection(CONN_ID)
        mock_repo.update_lifecycle_state.assert_not_called()
        mock_repo.delete.assert_called_once_with(CONN_ID)


# =============================================================================
# Tests: List and Get
# =============================================================================


class TestListAndGet:
    """Tests for connection listing and retrieval."""

    @pytest.mark.asyncio
    async def test_list_connections(self, service, mock_repo):
        """List returns paginated results."""
        conn1 = _make_mock_connection(connection_id=uuid4())
        conn2 = _make_mock_connection(connection_id=uuid4())
        mock_repo.list_all.return_value = ([conn1, conn2], 2)

        items, total = await service.list_connections(limit=20, offset=0)
        assert len(items) == 2
        assert total == 2
        mock_repo.list_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_connection(self, service, mock_repo):
        """Get returns a single connection by ID."""
        conn = _make_mock_connection()
        mock_repo.get_by_id.return_value = conn

        result = await service.get_connection(CONN_ID)
        assert result.id == CONN_ID
        mock_repo.get_by_id.assert_called_once_with(CONN_ID)


# =============================================================================
# Tests: State Transition Completeness
# =============================================================================


class TestStateTransitionMap:
    """Tests verifying the VALID_TRANSITIONS map is complete."""

    def test_all_states_have_entries(self):
        """Every lifecycle state appears as a key in VALID_TRANSITIONS."""
        expected_states = {
            "connecting", "connected", "degraded",
            "reauth_required", "disconnected", "revoked",
        }
        assert set(VALID_TRANSITIONS.keys()) == expected_states

    def test_revoked_is_terminal(self):
        """REVOKED has no valid outgoing transitions."""
        assert VALID_TRANSITIONS["revoked"] == set()

    def test_connecting_can_become_connected(self):
        """CONNECTING can transition to CONNECTED."""
        assert "connected" in VALID_TRANSITIONS["connecting"]
