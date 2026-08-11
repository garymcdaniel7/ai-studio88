"""Property tests for Connection Authorization Invariant (Property 18).

Property 18: Connection Authorization Invariant
    Connection existence alone NEVER grants capabilities without explicit
    permission configuration.

    Invariants tested:
    - For ANY connection + user role combination, if user's role is NOT in
      allowed_roles, access is ALWAYS denied (regardless of tool_policy,
      capabilities list, lifecycle state, or any other field)
    - A connection with capabilities=[...] but allowed_roles=[] grants zero
      access to any user
    - Connection existence (lifecycle_state='connected') alone never grants
      capabilities without explicit allowed_roles configuration

**Validates: Requirements R27.4, R85.7, A2-013**

No I/O, no DB — all connections are mocked in-memory.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


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
    ConnectionPermissionDenied,
    ConnectionPermissionService,
    ConnectionToolDenied,
)


# =============================================================================
# Constants
# =============================================================================

ORG_ID = UUID("11111111-1111-1111-1111-111111111111")

# All workspace roles in the platform
ALL_ROLES = ["owner", "admin", "editor", "viewer"]

# All possible lifecycle states a connection can be in
ALL_LIFECYCLE_STATES = [s.value for s in _ConnectionLifecycle]

# All connection categories
ALL_CATEGORIES = [c.value for c in _ConnectionCategory]

# All ownership types
ALL_OWNERSHIPS = [o.value for o in _ConnectionOwnership]


# =============================================================================
# Hypothesis Strategies
# =============================================================================

# Strategy for a single workspace role
role_strategy = st.sampled_from(ALL_ROLES)

# Strategy for allowed_roles: any subset of roles (including empty)
allowed_roles_strategy = st.lists(
    role_strategy,
    min_size=0,
    max_size=4,
    unique=True,
)

# Strategy for lifecycle state
lifecycle_strategy = st.sampled_from(ALL_LIFECYCLE_STATES)

# Strategy for connection category
category_strategy = st.sampled_from(ALL_CATEGORIES)

# Strategy for ownership type
ownership_strategy = st.sampled_from(ALL_OWNERSHIPS)

# Strategy for capabilities list (arbitrary JSON-like data)
capability_strategy = st.lists(
    st.text(min_size=1, max_size=30, alphabet=st.characters(categories=("L", "N", "P"))),
    min_size=0,
    max_size=10,
)

# Strategy for tool names
tool_name_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(categories=("L", "N"), whitelist_characters="_"),
)

# Strategy for tool_policy dicts
tool_policy_strategy = st.one_of(
    # Empty policy (all tools allowed)
    st.just({}),
    # Allow-only policy
    st.builds(
        lambda tools: {"allow": tools},
        st.lists(tool_name_strategy, min_size=1, max_size=5, unique=True),
    ),
    # Deny-only policy
    st.builds(
        lambda tools: {"deny": tools},
        st.lists(tool_name_strategy, min_size=1, max_size=5, unique=True),
    ),
    # Both allow and deny
    st.builds(
        lambda allow, deny: {"allow": allow, "deny": deny},
        st.lists(tool_name_strategy, min_size=1, max_size=5, unique=True),
        st.lists(tool_name_strategy, min_size=1, max_size=3, unique=True),
    ),
)


# =============================================================================
# Helper: Build a mock connection
# =============================================================================


def _make_connection(
    allowed_roles: list[str],
    lifecycle_state: str = "connected",
    capabilities: list[str] | None = None,
    tool_policy: dict | None = None,
    category: str = "ai_provider",
    ownership: str = "workspace",
) -> MagicMock:
    """Create a mock Connection with specified attributes."""
    conn = MagicMock()
    conn.id = uuid4()
    conn.org_id = ORG_ID
    conn.allowed_roles = allowed_roles
    conn.lifecycle_state = lifecycle_state
    conn.capabilities = capabilities or []
    conn.tool_policy = tool_policy if tool_policy is not None else {}
    conn.category = category
    conn.ownership = ownership
    conn.provider_name = "test_provider"
    conn.display_name = "Test Connection"
    conn.user_id = uuid4() if ownership == "user" else None
    return conn


# =============================================================================
# Helper: create service instance (stateless, no fixture needed)
# =============================================================================


def _make_service() -> ConnectionPermissionService:
    """Create a ConnectionPermissionService with a mocked repository.

    The service is stateless for permission checks — safe to reuse
    across Hypothesis examples without reset.
    """
    mock_repo = MagicMock()
    return ConnectionPermissionService(repo=mock_repo)


@pytest.fixture
def service() -> ConnectionPermissionService:
    """Fixture for deterministic edge case tests."""
    return _make_service()


# =============================================================================
# Property 18: Connection Authorization Invariant
# Feature: production-revamp, Property 18
# =============================================================================


class TestProperty18ConnectionAuthorizationInvariant:
    """Property 18: Connection existence alone NEVER grants capabilities
    without explicit permission configuration.

    For ANY connection + user role combination, if the user's role is NOT in
    allowed_roles, access is ALWAYS denied — regardless of tool_policy,
    capabilities list, lifecycle state, or any other field.

    **Validates: Requirements R27.4, R85.7, A2-013**
    """

    @pytest.mark.unit
    @settings(max_examples=200)
    @given(
        user_role=role_strategy,
        allowed_roles=allowed_roles_strategy,
        lifecycle_state=lifecycle_strategy,
        capabilities=capability_strategy,
        tool_policy=tool_policy_strategy,
        category=category_strategy,
        ownership=ownership_strategy,
    )
    def test_role_not_in_allowed_roles_always_denied(
        self,
        user_role: str,
        allowed_roles: list[str],
        lifecycle_state: str,
        capabilities: list[str],
        tool_policy: dict,
        category: str,
        ownership: str,
    ) -> None:
        """If user's role is NOT in allowed_roles, access is ALWAYS denied.

        **Validates: Requirements R85.7**

        Property: For ANY combination of connection attributes (lifecycle state,
        capabilities, tool_policy, category, ownership), if the user's role is
        not in the connection's allowed_roles, check_connection_access raises
        ConnectionPermissionDenied.
        """
        assume(user_role not in allowed_roles)

        svc = _make_service()
        connection = _make_connection(
            allowed_roles=allowed_roles,
            lifecycle_state=lifecycle_state,
            capabilities=capabilities,
            tool_policy=tool_policy,
            category=category,
            ownership=ownership,
        )

        with pytest.raises(ConnectionPermissionDenied):
            svc.check_connection_access(connection, user_role=user_role)

    @pytest.mark.unit
    @settings(max_examples=200)
    @given(
        user_role=role_strategy,
        lifecycle_state=lifecycle_strategy,
        capabilities=capability_strategy,
        tool_policy=tool_policy_strategy,
        category=category_strategy,
        ownership=ownership_strategy,
    )
    def test_empty_allowed_roles_denies_all_users(
        self,
        user_role: str,
        lifecycle_state: str,
        capabilities: list[str],
        tool_policy: dict,
        category: str,
        ownership: str,
    ) -> None:
        """A connection with allowed_roles=[] grants zero access to ANY user.

        **Validates: Requirements R27.4, A2-013**

        Property: For ANY user role, ANY lifecycle state, ANY capabilities list,
        ANY tool_policy, a connection with empty allowed_roles ALWAYS denies access.
        Connection existence alone never grants capabilities.
        """
        svc = _make_service()
        connection = _make_connection(
            allowed_roles=[],
            lifecycle_state=lifecycle_state,
            capabilities=capabilities,
            tool_policy=tool_policy,
            category=category,
            ownership=ownership,
        )

        with pytest.raises(ConnectionPermissionDenied):
            svc.check_connection_access(connection, user_role=user_role)

    @pytest.mark.unit
    @settings(max_examples=200)
    @given(
        user_role=role_strategy,
        capabilities=st.lists(
            st.text(min_size=1, max_size=30, alphabet=st.characters(categories=("L", "N"))),
            min_size=1,
            max_size=10,
        ),
        category=category_strategy,
        ownership=ownership_strategy,
    )
    def test_connected_with_capabilities_but_empty_roles_still_denied(
        self,
        user_role: str,
        capabilities: list[str],
        category: str,
        ownership: str,
    ) -> None:
        """Connection existence (lifecycle_state='connected') alone never grants
        capabilities without explicit allowed_roles configuration.

        **Validates: Requirements R27.4, R85.7, A2-013**

        Property: A connection that is CONNECTED and has a non-empty capabilities
        list, but has allowed_roles=[], STILL denies access to all users.
        The presence of capabilities does NOT bypass the role check.
        """
        svc = _make_service()
        connection = _make_connection(
            allowed_roles=[],
            lifecycle_state="connected",
            capabilities=capabilities,
            tool_policy={},  # All tools "allowed" by policy
            category=category,
            ownership=ownership,
        )

        # INVARIANT: even though the connection is alive and has capabilities,
        # without explicit role grants, no user can access it.
        with pytest.raises(ConnectionPermissionDenied):
            svc.check_connection_access(connection, user_role=user_role)

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        user_role=role_strategy,
        allowed_roles=allowed_roles_strategy,
        lifecycle_state=lifecycle_strategy,
        capabilities=capability_strategy,
        tool_policy=tool_policy_strategy,
    )
    def test_role_in_allowed_roles_always_granted(
        self,
        user_role: str,
        allowed_roles: list[str],
        lifecycle_state: str,
        capabilities: list[str],
        tool_policy: dict,
    ) -> None:
        """If user's role IS in allowed_roles, access check passes (positive case).

        **Validates: Requirements R85.7**

        Property: For ANY combination of other connection attributes, if the
        user's role is in allowed_roles, check_connection_access returns True.
        This confirms that only allowed_roles determines role-level access.
        """
        assume(user_role in allowed_roles)

        svc = _make_service()
        connection = _make_connection(
            allowed_roles=allowed_roles,
            lifecycle_state=lifecycle_state,
            capabilities=capabilities,
            tool_policy=tool_policy,
        )

        result = svc.check_connection_access(connection, user_role=user_role)
        assert result is True

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        user_role=role_strategy,
        allowed_roles=allowed_roles_strategy,
        tool_name=tool_name_strategy,
        tool_policy=tool_policy_strategy,
    )
    def test_role_denial_overrides_tool_policy(
        self,
        user_role: str,
        allowed_roles: list[str],
        tool_name: str,
        tool_policy: dict,
    ) -> None:
        """Role denial is independent of tool_policy — both layers must pass.

        **Validates: Requirements R85.7, A2-013**

        Property: If the user's role is NOT in allowed_roles, the role check
        raises BEFORE tool_policy is evaluated. Tool policy cannot override
        a role-level denial.
        """
        assume(user_role not in allowed_roles)

        svc = _make_service()
        connection = _make_connection(
            allowed_roles=allowed_roles,
            tool_policy=tool_policy,
        )

        # Role check denies — this is the authorization barrier
        with pytest.raises(ConnectionPermissionDenied):
            svc.check_connection_access(connection, user_role=user_role)


# =============================================================================
# Deterministic Edge Case Tests (complement to property tests)
# =============================================================================


class TestConnectionAuthorizationEdgeCases:
    """Deterministic edge cases for connection authorization invariant."""

    @pytest.mark.unit
    def test_all_roles_denied_when_allowed_roles_empty(self, service) -> None:
        """Every role in the hierarchy is denied when allowed_roles=[]."""
        connection = _make_connection(
            allowed_roles=[],
            lifecycle_state="connected",
            capabilities=["chat", "embeddings", "fine_tuning"],
        )

        for role in ALL_ROLES:
            with pytest.raises(ConnectionPermissionDenied):
                service.check_connection_access(connection, user_role=role)

    @pytest.mark.unit
    def test_connected_state_irrelevant_without_roles(self, service) -> None:
        """Being 'connected' does not bypass role checks."""
        connection = _make_connection(
            allowed_roles=[],
            lifecycle_state="connected",
            capabilities=["publish", "analytics"],
            tool_policy={"allow": ["publish", "analytics"]},
        )

        with pytest.raises(ConnectionPermissionDenied):
            service.check_connection_access(connection, user_role="owner")

    @pytest.mark.unit
    def test_rich_capabilities_irrelevant_without_roles(self, service) -> None:
        """A connection with many capabilities but no allowed_roles grants nothing."""
        connection = _make_connection(
            allowed_roles=[],
            lifecycle_state="connected",
            capabilities=[
                "chat", "completion", "embeddings", "fine_tuning",
                "models_list", "files_upload", "image_generation",
                "audio_transcription", "code_interpreter", "assistants",
            ],
            tool_policy={},
        )

        with pytest.raises(ConnectionPermissionDenied):
            service.check_connection_access(connection, user_role="owner")

    @pytest.mark.unit
    def test_tool_policy_allow_all_irrelevant_without_roles(self, service) -> None:
        """tool_policy allowing all tools does not bypass role restriction."""
        connection = _make_connection(
            allowed_roles=[],
            lifecycle_state="connected",
            capabilities=["chat"],
            tool_policy={},  # empty = allow all
        )

        # Even the most permissive tool_policy cannot help
        with pytest.raises(ConnectionPermissionDenied):
            service.check_connection_access(connection, user_role="admin")

    @pytest.mark.unit
    def test_only_specified_role_has_access(self, service) -> None:
        """When allowed_roles=['viewer'], only viewer can access."""
        connection = _make_connection(
            allowed_roles=["viewer"],
            lifecycle_state="connected",
            capabilities=["read_data"],
        )

        # viewer passes
        result = service.check_connection_access(connection, user_role="viewer")
        assert result is True

        # All other roles denied
        for role in ["owner", "admin", "editor"]:
            with pytest.raises(ConnectionPermissionDenied):
                service.check_connection_access(connection, user_role=role)

    @pytest.mark.unit
    def test_degraded_connection_still_requires_role(self, service) -> None:
        """A degraded connection still enforces allowed_roles."""
        connection = _make_connection(
            allowed_roles=["admin"],
            lifecycle_state="degraded",
            capabilities=["chat"],
        )

        with pytest.raises(ConnectionPermissionDenied):
            service.check_connection_access(connection, user_role="editor")

    @pytest.mark.unit
    def test_reauth_required_connection_still_requires_role(self, service) -> None:
        """A connection needing reauth still enforces role checks."""
        connection = _make_connection(
            allowed_roles=["owner", "admin"],
            lifecycle_state="reauth_required",
            capabilities=["publish"],
        )

        with pytest.raises(ConnectionPermissionDenied):
            service.check_connection_access(connection, user_role="viewer")

        # admin still passes role check
        result = service.check_connection_access(connection, user_role="admin")
        assert result is True

    @pytest.mark.unit
    def test_revoked_connection_still_applies_role_check(self, service) -> None:
        """Even a revoked connection applies role checks consistently."""
        connection = _make_connection(
            allowed_roles=["owner"],
            lifecycle_state="revoked",
            capabilities=[],
        )

        # owner passes role check (service doesn't check lifecycle)
        result = service.check_connection_access(connection, user_role="owner")
        assert result is True

        # editor denied
        with pytest.raises(ConnectionPermissionDenied):
            service.check_connection_access(connection, user_role="editor")
