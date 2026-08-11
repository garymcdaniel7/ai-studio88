"""Unit tests for the Connection data model and schemas.

Tests the Connection ORM model enums, Pydantic schema validation,
and constraint enforcement for the Connections Hub.

Validates: Requirements R85.1, R85.3, R85.4, R92.1, R92.2, R92.3
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.connection import (
    ConnectionAuthMethod,
    ConnectionCategory,
    ConnectionLifecycle,
    ConnectionOwnership,
)
from app.schemas.connection import (
    ConnectionAuthMethodEnum,
    ConnectionCategoryEnum,
    ConnectionCreate,
    ConnectionHealthUpdate,
    ConnectionLifecycleEnum,
    ConnectionListResponse,
    ConnectionOwnershipEnum,
    ConnectionResponse,
    ConnectionUpdate,
)


# =============================================================================
# Enum Tests
# =============================================================================


@pytest.mark.unit
class TestConnectionEnums:
    """Test that all enums have expected values."""

    def test_ownership_values(self) -> None:
        assert ConnectionOwnership.USER == "user"
        assert ConnectionOwnership.WORKSPACE == "workspace"
        assert len(ConnectionOwnership) == 2

    def test_lifecycle_values(self) -> None:
        expected = {
            "connecting",
            "connected",
            "degraded",
            "reauth_required",
            "disconnected",
            "revoked",
        }
        assert {e.value for e in ConnectionLifecycle} == expected

    def test_category_values(self) -> None:
        expected = {
            "ai_provider",
            "storage",
            "social",
            "compute",
            "developer",
            "business",
        }
        assert {e.value for e in ConnectionCategory} == expected

    def test_auth_method_values(self) -> None:
        expected = {"oauth", "api_key", "ssh", "mcp"}
        assert {e.value for e in ConnectionAuthMethod} == expected


# =============================================================================
# Schema Enum Tests (Pydantic mirror enums)
# =============================================================================


@pytest.mark.unit
class TestSchemaEnums:
    """Test schema-level enum mirroring."""

    def test_ownership_enum_matches_orm(self) -> None:
        orm_values = {e.value for e in ConnectionOwnership}
        schema_values = {e.value for e in ConnectionOwnershipEnum}
        assert orm_values == schema_values

    def test_lifecycle_enum_matches_orm(self) -> None:
        orm_values = {e.value for e in ConnectionLifecycle}
        schema_values = {e.value for e in ConnectionLifecycleEnum}
        assert orm_values == schema_values

    def test_category_enum_matches_orm(self) -> None:
        orm_values = {e.value for e in ConnectionCategory}
        schema_values = {e.value for e in ConnectionCategoryEnum}
        assert orm_values == schema_values

    def test_auth_method_enum_matches_orm(self) -> None:
        orm_values = {e.value for e in ConnectionAuthMethod}
        schema_values = {e.value for e in ConnectionAuthMethodEnum}
        assert orm_values == schema_values


# =============================================================================
# ConnectionCreate Schema Tests
# =============================================================================


@pytest.mark.unit
class TestConnectionCreate:
    """Test ConnectionCreate request schema validation."""

    def test_valid_workspace_connection(self) -> None:
        data = ConnectionCreate(
            ownership="workspace",
            category="ai_provider",
            provider_name="openai",
            display_name="OpenAI GPT-4",
            auth_method="api_key",
        )
        assert data.ownership == ConnectionOwnershipEnum.WORKSPACE
        assert data.category == ConnectionCategoryEnum.AI_PROVIDER
        assert data.provider_name == "openai"
        assert data.display_name == "OpenAI GPT-4"
        assert data.auth_method == ConnectionAuthMethodEnum.API_KEY
        assert data.capabilities == []
        assert data.allowed_roles == ["owner", "admin", "editor"]
        assert data.tool_policy == {}
        assert data.oauth_token_ref is None

    def test_valid_user_connection_oauth(self) -> None:
        token_ref = uuid4()
        data = ConnectionCreate(
            ownership="user",
            category="social",
            provider_name="instagram",
            display_name="My Instagram",
            auth_method="oauth",
            oauth_token_ref=token_ref,
            capabilities=["publish", "read_insights"],
        )
        assert data.ownership == ConnectionOwnershipEnum.USER
        assert data.category == ConnectionCategoryEnum.SOCIAL
        assert data.auth_method == ConnectionAuthMethodEnum.OAUTH
        assert data.oauth_token_ref == token_ref
        assert data.capabilities == ["publish", "read_insights"]

    def test_invalid_ownership_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ConnectionCreate(
                ownership="invalid",
                category="storage",
                provider_name="b2",
                display_name="Backblaze",
                auth_method="api_key",
            )
        assert "ownership" in str(exc_info.value)

    def test_invalid_category_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ConnectionCreate(
                ownership="workspace",
                category="unknown_category",
                provider_name="b2",
                display_name="Backblaze",
                auth_method="api_key",
            )
        assert "category" in str(exc_info.value)

    def test_invalid_auth_method_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ConnectionCreate(
                ownership="workspace",
                category="storage",
                provider_name="b2",
                display_name="Backblaze",
                auth_method="password",
            )
        assert "auth_method" in str(exc_info.value)

    def test_empty_provider_name_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ConnectionCreate(
                ownership="workspace",
                category="storage",
                provider_name="",
                display_name="Backblaze",
                auth_method="api_key",
            )
        assert "provider_name" in str(exc_info.value)

    def test_empty_display_name_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ConnectionCreate(
                ownership="workspace",
                category="storage",
                provider_name="b2",
                display_name="",
                auth_method="api_key",
            )
        assert "display_name" in str(exc_info.value)

    def test_provider_name_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ConnectionCreate(
                ownership="workspace",
                category="storage",
                provider_name="x" * 101,
                display_name="Backblaze",
                auth_method="api_key",
            )

    def test_display_name_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ConnectionCreate(
                ownership="workspace",
                category="storage",
                provider_name="b2",
                display_name="x" * 201,
                auth_method="api_key",
            )

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ConnectionCreate(
                ownership="workspace",
                category="storage",
                provider_name="b2",
                display_name="Backblaze",
                auth_method="api_key",
                secret_key="should_not_be_here",  # type: ignore[call-arg]
            )
        assert "extra" in str(exc_info.value).lower()

    def test_all_categories_accepted(self) -> None:
        for cat in ConnectionCategoryEnum:
            data = ConnectionCreate(
                ownership="workspace",
                category=cat.value,
                provider_name="test",
                display_name="Test Provider",
                auth_method="api_key",
            )
            assert data.category == cat

    def test_all_auth_methods_accepted(self) -> None:
        for method in ConnectionAuthMethodEnum:
            data = ConnectionCreate(
                ownership="workspace",
                category="developer",
                provider_name="test",
                display_name="Test",
                auth_method=method.value,
            )
            assert data.auth_method == method


# =============================================================================
# ConnectionUpdate Schema Tests
# =============================================================================


@pytest.mark.unit
class TestConnectionUpdate:
    """Test ConnectionUpdate (PATCH) schema validation."""

    def test_partial_update_display_name(self) -> None:
        data = ConnectionUpdate(display_name="New Name")
        assert data.display_name == "New Name"
        assert data.lifecycle_state is None
        assert data.capabilities is None

    def test_partial_update_lifecycle_state(self) -> None:
        data = ConnectionUpdate(lifecycle_state="connected")
        assert data.lifecycle_state == ConnectionLifecycleEnum.CONNECTED

    def test_all_lifecycle_states_valid(self) -> None:
        for state in ConnectionLifecycleEnum:
            data = ConnectionUpdate(lifecycle_state=state.value)
            assert data.lifecycle_state == state

    def test_invalid_lifecycle_state_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConnectionUpdate(lifecycle_state="invalid_state")

    def test_empty_update_valid(self) -> None:
        data = ConnectionUpdate()
        assert data.display_name is None
        assert data.lifecycle_state is None

    def test_update_capabilities(self) -> None:
        data = ConnectionUpdate(capabilities=["publish", "analytics"])
        assert data.capabilities == ["publish", "analytics"]

    def test_update_tool_policy(self) -> None:
        policy = {"publish": "allow", "delete": "deny"}
        data = ConnectionUpdate(tool_policy=policy)
        assert data.tool_policy == policy


# =============================================================================
# ConnectionHealthUpdate Schema Tests
# =============================================================================


@pytest.mark.unit
class TestConnectionHealthUpdate:
    """Test ConnectionHealthUpdate schema validation."""

    def test_valid_health_status(self) -> None:
        data = ConnectionHealthUpdate(health_status="healthy")
        assert data.health_status == "healthy"

    def test_empty_health_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConnectionHealthUpdate(health_status="")

    def test_health_status_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ConnectionHealthUpdate(health_status="x" * 31)


# =============================================================================
# ConnectionResponse Schema Tests
# =============================================================================


@pytest.mark.unit
class TestConnectionResponse:
    """Test ConnectionResponse serialization."""

    def test_full_response(self) -> None:
        now = datetime.now(timezone.utc)
        conn_id = uuid4()
        org_id = uuid4()
        user_id = uuid4()
        token_ref = uuid4()

        data = ConnectionResponse(
            id=conn_id,
            org_id=org_id,
            user_id=user_id,
            ownership="user",
            category="social",
            provider_name="instagram",
            display_name="My Instagram",
            lifecycle_state="connected",
            auth_method="oauth",
            oauth_token_ref=token_ref,
            capabilities=["publish", "read_insights"],
            allowed_roles=["owner", "admin", "editor"],
            tool_policy={"publish": "allow"},
            last_health_check_at=now,
            health_status="healthy",
            created_at=now,
            updated_at=now,
        )
        assert data.id == conn_id
        assert data.org_id == org_id
        assert data.user_id == user_id
        assert data.ownership == ConnectionOwnershipEnum.USER
        assert data.lifecycle_state == ConnectionLifecycleEnum.CONNECTED
        assert data.auth_method == ConnectionAuthMethodEnum.OAUTH

    def test_workspace_response_no_user_id(self) -> None:
        now = datetime.now(timezone.utc)
        data = ConnectionResponse(
            id=uuid4(),
            org_id=uuid4(),
            user_id=None,
            ownership="workspace",
            category="ai_provider",
            provider_name="openai",
            display_name="OpenAI",
            lifecycle_state="connected",
            auth_method="api_key",
            created_at=now,
            updated_at=now,
        )
        assert data.user_id is None
        assert data.ownership == ConnectionOwnershipEnum.WORKSPACE


# =============================================================================
# ConnectionListResponse Schema Tests
# =============================================================================


@pytest.mark.unit
class TestConnectionListResponse:
    """Test paginated list response."""

    def test_empty_list(self) -> None:
        data = ConnectionListResponse(items=[], total=0, limit=20, offset=0)
        assert data.items == []
        assert data.total == 0
        assert not data.has_more

    def test_has_more_pagination(self) -> None:
        now = datetime.now(timezone.utc)
        item = ConnectionResponse(
            id=uuid4(),
            org_id=uuid4(),
            ownership="workspace",
            category="storage",
            provider_name="b2",
            display_name="Backblaze",
            lifecycle_state="connected",
            auth_method="api_key",
            created_at=now,
            updated_at=now,
        )
        data = ConnectionListResponse(items=[item], total=50, limit=20, offset=0)
        assert data.has_more is True

    def test_no_more_pagination(self) -> None:
        data = ConnectionListResponse(items=[], total=5, limit=20, offset=0)
        assert data.has_more is False
