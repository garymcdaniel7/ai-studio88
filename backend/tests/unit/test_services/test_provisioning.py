"""Unit tests for ProvisioningService — idempotent workspace provisioning.

Tests cover:
    - Happy path: new user gets workspace provisioned (org + membership + onboarding)
    - Idempotency: calling provision_workspace twice returns existing workspace
    - is_eligible_for_provisioning: True for new users, False for existing members
    - Org name derivation from email
    - Org slug derivation from email
    - Race condition handling: concurrent provisioning resolves gracefully
    - System org filtering: system org membership does not count

Requirements: R1.6, R1.11, R84.4, R84.5
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

# =============================================================================
# Mock sqlalchemy and app.db.session BEFORE importing modules that depend on it.
# The root .venv has a partial sqlalchemy install (missing AsyncEngine etc.)
# so we inject complete mocks into sys.modules.
# =============================================================================

_sa_mock = MagicMock()
_sa_ext_mock = MagicMock()
_sa_ext_asyncio_mock = MagicMock()

# Ensure the sqlalchemy.ext.asyncio module has the needed attributes
_sa_ext_asyncio_mock.AsyncEngine = MagicMock
_sa_ext_asyncio_mock.AsyncSession = MagicMock
_sa_ext_asyncio_mock.async_sessionmaker = MagicMock
_sa_ext_asyncio_mock.create_async_engine = MagicMock

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.ext", _sa_ext_mock)
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.orm", MagicMock())

# Mock app.db.session so that app.core.dependencies can import it
_mock_db_session = ModuleType("app.db.session")
_mock_db_session.get_db_session = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db", ModuleType("app.db"))
sys.modules.setdefault("app.db.session", _mock_db_session)

# Now safe to import our modules
from app.core.dependencies import TenantContext, TrustDomain, WorkspaceRole
from app.services.provisioning_service import (
    DEFAULT_WORKSPACE_SLUG_MAX_LENGTH,
    ProvisioningError,
    ProvisioningResult,
    ProvisioningService,
    SYSTEM_ORG_ID,
)


# =============================================================================
# Fixtures
# =============================================================================


@dataclass
class MockQueryResult:
    """Simulates a Supabase query result."""

    data: list[dict] | None = None


class MockTableQuery:
    """Simulates a Supabase table query builder with chaining."""

    def __init__(self, data: list[dict] | None = None) -> None:
        self._data = data if data is not None else []

    def select(self, *args, **kwargs) -> "MockTableQuery":
        return self

    def eq(self, *args, **kwargs) -> "MockTableQuery":
        return self

    def order(self, *args, **kwargs) -> "MockTableQuery":
        return self

    def execute(self) -> MockQueryResult:
        return MockQueryResult(data=self._data)


class MockUpsertQuery:
    """Simulates a Supabase upsert query builder."""

    def __init__(self) -> None:
        self.upserted_data: dict | None = None

    def execute(self) -> MockQueryResult:
        return MockQueryResult(data=[self.upserted_data] if self.upserted_data else [])


@pytest.fixture
def mock_supabase_client():
    """Create a mock Supabase client with configurable table responses."""
    client = MagicMock()
    return client


@pytest.fixture
def service(mock_supabase_client):
    """Create a ProvisioningService with a mock client."""
    return ProvisioningService(supabase_client=mock_supabase_client)


@pytest.fixture
def new_user_id() -> UUID:
    """A user ID representing a brand-new user with no memberships."""
    return uuid4()


@pytest.fixture
def existing_user_id() -> UUID:
    """A user ID representing a user with an existing membership."""
    return uuid4()


@pytest.fixture
def existing_org_id() -> UUID:
    """An org_id for an existing organization."""
    return uuid4()


# =============================================================================
# Tests: provision_workspace — Happy Path
# =============================================================================


@pytest.mark.unit
class TestProvisionWorkspaceHappyPath:
    """Tests for successful workspace provisioning of new users."""

    @pytest.mark.asyncio
    async def test_new_user_gets_workspace_provisioned(
        self, service, mock_supabase_client, new_user_id
    ):
        """A new user with no memberships gets a workspace created."""
        email = "alice@example.com"

        # Mock: no existing membership
        upsert_mock = MagicMock()
        upsert_mock.execute.return_value = MockQueryResult(data=[])

        def table_handler(table_name):
            mock_table = MagicMock()
            if table_name == "org_members":
                mock_table.select.return_value = mock_table
                mock_table.eq.return_value = mock_table
                mock_table.order.return_value = mock_table
                mock_table.execute.return_value = MockQueryResult(data=[])
                mock_table.upsert.return_value = upsert_mock
            elif table_name == "organizations":
                mock_table.select.return_value = mock_table
                mock_table.eq.return_value = mock_table
                mock_table.execute.return_value = MockQueryResult(data=[])
                mock_table.upsert.return_value = upsert_mock
            elif table_name == "onboarding_state":
                mock_table.upsert.return_value = upsert_mock
            return mock_table

        mock_supabase_client.table.side_effect = table_handler

        result = await service.provision_workspace(new_user_id, email)

        assert isinstance(result, ProvisioningResult)
        assert result.created is True
        assert result.tenant_context.user_id == new_user_id
        assert result.tenant_context.role == WorkspaceRole.OWNER
        assert result.tenant_context.trust_domain == TrustDomain.WORKSPACE_ADMIN
        assert result.tenant_context.email == email
        assert result.org_name == "Alice's Workspace"

    @pytest.mark.asyncio
    async def test_provisioned_user_gets_owner_role(
        self, service, mock_supabase_client, new_user_id
    ):
        """Newly provisioned users always get the OWNER role."""
        email = "bob@startup.io"

        def table_handler(table_name):
            mock_table = MagicMock()
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table
            mock_table.execute.return_value = MockQueryResult(data=[])
            upsert_mock = MagicMock()
            upsert_mock.execute.return_value = MockQueryResult(data=[])
            mock_table.upsert.return_value = upsert_mock
            return mock_table

        mock_supabase_client.table.side_effect = table_handler

        result = await service.provision_workspace(new_user_id, email)

        assert result.tenant_context.role == WorkspaceRole.OWNER

    @pytest.mark.asyncio
    async def test_org_membership_and_onboarding_all_created(
        self, service, mock_supabase_client, new_user_id
    ):
        """Provisioning creates: organization, org_member, and onboarding_state."""
        email = "charlie@corp.com"
        upsert_calls = []

        def table_handler(table_name):
            mock_table = MagicMock()
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table
            mock_table.execute.return_value = MockQueryResult(data=[])

            upsert_mock = MagicMock()
            upsert_mock.execute.return_value = MockQueryResult(data=[])

            def capture_upsert(*args, **kwargs):
                upsert_calls.append((table_name, args, kwargs))
                return upsert_mock

            mock_table.upsert.side_effect = capture_upsert
            return mock_table

        mock_supabase_client.table.side_effect = table_handler

        await service.provision_workspace(new_user_id, email)

        # Verify all three tables were upserted
        upserted_tables = [call[0] for call in upsert_calls]
        assert "organizations" in upserted_tables
        assert "org_members" in upserted_tables
        assert "onboarding_state" in upserted_tables


# =============================================================================
# Tests: provision_workspace — Idempotency
# =============================================================================


@pytest.mark.unit
class TestProvisionWorkspaceIdempotency:
    """Tests proving provisioning is idempotent (no duplicates on retry)."""

    @pytest.mark.asyncio
    async def test_existing_user_returns_existing_workspace(
        self, service, mock_supabase_client, existing_user_id, existing_org_id
    ):
        """If user already has a membership, return existing workspace."""
        email = "alice@example.com"

        def table_handler(table_name):
            mock_table = MagicMock()
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table

            if table_name == "org_members":
                mock_table.execute.return_value = MockQueryResult(
                    data=[
                        {
                            "org_id": str(existing_org_id),
                            "role": "owner",
                            "status": "active",
                        }
                    ]
                )
            elif table_name == "organizations":
                mock_table.execute.return_value = MockQueryResult(
                    data=[{"name": "Alice's Workspace"}]
                )
            return mock_table

        mock_supabase_client.table.side_effect = table_handler

        result = await service.provision_workspace(existing_user_id, email)

        assert result.created is False
        assert result.org_id == existing_org_id
        assert result.tenant_context.org_id == existing_org_id
        assert result.tenant_context.role == WorkspaceRole.OWNER
        assert result.org_name == "Alice's Workspace"

    @pytest.mark.asyncio
    async def test_retry_does_not_create_duplicates(
        self, service, mock_supabase_client, existing_user_id, existing_org_id
    ):
        """Calling provision_workspace twice for the same user returns the same result."""
        email = "alice@example.com"

        def table_handler(table_name):
            mock_table = MagicMock()
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table

            if table_name == "org_members":
                mock_table.execute.return_value = MockQueryResult(
                    data=[
                        {
                            "org_id": str(existing_org_id),
                            "role": "owner",
                            "status": "active",
                        }
                    ]
                )
            elif table_name == "organizations":
                mock_table.execute.return_value = MockQueryResult(
                    data=[{"name": "Existing Workspace"}]
                )
            return mock_table

        mock_supabase_client.table.side_effect = table_handler

        result1 = await service.provision_workspace(existing_user_id, email)
        result2 = await service.provision_workspace(existing_user_id, email)

        assert result1.org_id == result2.org_id
        assert result1.created is False
        assert result2.created is False

    @pytest.mark.asyncio
    async def test_race_condition_resolved_gracefully(
        self, service, mock_supabase_client, new_user_id
    ):
        """If creation fails due to a race, fallback to existing membership."""
        email = "racer@example.com"
        call_count = {"org_members_select": 0}
        org_id = uuid4()

        def table_handler(table_name):
            mock_table = MagicMock()
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table

            if table_name == "org_members":
                call_count["org_members_select"] += 1
                if call_count["org_members_select"] == 1:
                    # First call: no membership (triggers creation)
                    mock_table.execute.return_value = MockQueryResult(data=[])
                else:
                    # Second call (after race): membership exists
                    mock_table.execute.return_value = MockQueryResult(
                        data=[
                            {
                                "org_id": str(org_id),
                                "role": "owner",
                                "status": "active",
                            }
                        ]
                    )
                # Make upsert raise to simulate a conflict/race
                mock_table.upsert.side_effect = Exception(
                    "duplicate key value violates unique constraint"
                )
            elif table_name == "organizations":
                if call_count["org_members_select"] <= 1:
                    # First org lookup: raise to trigger race path
                    mock_table.upsert.side_effect = Exception(
                        "duplicate key value violates unique constraint"
                    )
                    mock_table.execute.return_value = MockQueryResult(data=[])
                else:
                    # After race resolution
                    mock_table.execute.return_value = MockQueryResult(
                        data=[{"name": "Racer's Workspace"}]
                    )
            elif table_name == "onboarding_state":
                mock_table.upsert.side_effect = Exception(
                    "duplicate key value violates unique constraint"
                )
            return mock_table

        mock_supabase_client.table.side_effect = table_handler

        result = await service.provision_workspace(new_user_id, email)

        # Should resolve to existing workspace despite race
        assert result.created is False
        assert result.org_id == org_id


# =============================================================================
# Tests: is_eligible_for_provisioning
# =============================================================================


@pytest.mark.unit
class TestIsEligibleForProvisioning:
    """Tests for is_eligible_for_provisioning."""

    def test_new_user_is_eligible(
        self, service, mock_supabase_client, new_user_id
    ):
        """User with no org_members record is eligible for provisioning."""

        def table_handler(table_name):
            mock_table = MagicMock()
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table
            mock_table.execute.return_value = MockQueryResult(data=[])
            return mock_table

        mock_supabase_client.table.side_effect = table_handler

        assert service.is_eligible_for_provisioning(new_user_id) is True

    def test_existing_member_is_not_eligible(
        self, service, mock_supabase_client, existing_user_id, existing_org_id
    ):
        """User with an active org_members record is NOT eligible."""

        def table_handler(table_name):
            mock_table = MagicMock()
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table

            if table_name == "org_members":
                mock_table.execute.return_value = MockQueryResult(
                    data=[
                        {
                            "org_id": str(existing_org_id),
                            "role": "editor",
                            "status": "active",
                        }
                    ]
                )
            elif table_name == "organizations":
                mock_table.execute.return_value = MockQueryResult(
                    data=[{"name": "Some Org"}]
                )
            return mock_table

        mock_supabase_client.table.side_effect = table_handler

        assert service.is_eligible_for_provisioning(existing_user_id) is False

    def test_system_org_membership_does_not_count(
        self, service, mock_supabase_client, new_user_id
    ):
        """Membership in the system org does not make user ineligible."""

        def table_handler(table_name):
            mock_table = MagicMock()
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table

            if table_name == "org_members":
                # Only has system org membership
                mock_table.execute.return_value = MockQueryResult(
                    data=[
                        {
                            "org_id": str(SYSTEM_ORG_ID),
                            "role": "viewer",
                            "status": "active",
                        }
                    ]
                )
            else:
                mock_table.execute.return_value = MockQueryResult(data=[])
            return mock_table

        mock_supabase_client.table.side_effect = table_handler

        assert service.is_eligible_for_provisioning(new_user_id) is True

    def test_db_error_returns_eligible(
        self, service, mock_supabase_client, new_user_id
    ):
        """If DB lookup fails, return None (treated as eligible by callers)."""

        def table_handler(table_name):
            mock_table = MagicMock()
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table
            mock_table.execute.side_effect = Exception("connection timeout")
            return mock_table

        mock_supabase_client.table.side_effect = table_handler

        # When DB fails, _get_existing_membership returns None → eligible
        assert service.is_eligible_for_provisioning(new_user_id) is True


# =============================================================================
# Tests: Org Name Derivation
# =============================================================================


@pytest.mark.unit
class TestOrgNameDerivation:
    """Tests for workspace name derivation from email."""

    def test_simple_email(self, service):
        """alice@example.com → Alice's Workspace."""
        assert service._derive_org_name("alice@example.com") == "Alice's Workspace"

    def test_dotted_email(self, service):
        """john.doe@company.com → John Doe's Workspace."""
        assert service._derive_org_name("john.doe@company.com") == "John Doe's Workspace"

    def test_underscored_email(self, service):
        """jane_smith@org.co → Jane Smith's Workspace."""
        assert service._derive_org_name("jane_smith@org.co") == "Jane Smith's Workspace"

    def test_hyphenated_email(self, service):
        """bob-jones@startup.io → Bob Jones's Workspace."""
        assert service._derive_org_name("bob-jones@startup.io") == "Bob Jones's Workspace"

    def test_no_at_sign(self, service):
        """Invalid email without @ → My Workspace."""
        assert service._derive_org_name("noemail") == "My Workspace"

    def test_empty_local_part(self, service):
        """@example.com → My Workspace."""
        assert service._derive_org_name("@example.com") == "My Workspace"


# =============================================================================
# Tests: Org Slug Derivation
# =============================================================================


@pytest.mark.unit
class TestOrgSlugDerivation:
    """Tests for URL-safe slug derivation from email."""

    def test_simple_email_slug(self, service):
        """alice@example.com → alice-{org_id[:8]}."""
        org_id = UUID("12345678-1234-1234-1234-123456789abc")
        slug = service._derive_org_slug("alice@example.com", org_id)
        assert slug == "alice-12345678"

    def test_dotted_email_slug(self, service):
        """john.doe@company.com → john-doe-{org_id[:8]}."""
        org_id = UUID("abcdef01-1234-1234-1234-123456789abc")
        slug = service._derive_org_slug("john.doe@company.com", org_id)
        assert slug == "john-doe-abcdef01"

    def test_no_at_sign_slug(self, service):
        """Invalid email → workspace-{org_id[:8]}."""
        org_id = UUID("99999999-1234-1234-1234-123456789abc")
        slug = service._derive_org_slug("noemail", org_id)
        assert slug == "workspace-99999999"

    def test_slug_max_length(self, service):
        """Slugs are truncated to max length."""
        long_email = "a" * 100 + "@example.com"
        org_id = uuid4()
        slug = service._derive_org_slug(long_email, org_id)
        assert len(slug) <= DEFAULT_WORKSPACE_SLUG_MAX_LENGTH

    def test_slug_lowercase(self, service):
        """Slugs are always lowercase."""
        org_id = uuid4()
        slug = service._derive_org_slug("Alice.BOB@Example.com", org_id)
        assert slug == slug.lower()


# =============================================================================
# Tests: Error Cases
# =============================================================================


@pytest.mark.unit
class TestProvisioningErrors:
    """Tests for error handling during provisioning."""

    @pytest.mark.asyncio
    async def test_db_failure_with_no_fallback_raises_error(
        self, service, mock_supabase_client, new_user_id
    ):
        """If DB fails and no existing membership can be found, raise ProvisioningError."""
        email = "unlucky@example.com"

        def table_handler(table_name):
            mock_table = MagicMock()
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table
            # All DB calls fail
            mock_table.execute.side_effect = Exception("database unavailable")
            mock_table.upsert.side_effect = Exception("database unavailable")
            return mock_table

        mock_supabase_client.table.side_effect = table_handler

        with pytest.raises(ProvisioningError) as exc_info:
            await service.provision_workspace(new_user_id, email)

        assert "Failed to provision workspace" in str(exc_info.value.message)
        assert exc_info.value.user_id == str(new_user_id)
