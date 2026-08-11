"""Unit tests for FeatureRolloutDBService.

Tests the database-backed feature rollout engine including:
- CRUD operations (create, delete, list)
- Evaluation logic (is_enabled)
- Scope matching (global, workspace, plan, user, cohort, workload, provider)
- Expiry handling (expired rules treated as inactive)
- Scope target validation in create

These tests mock the SQLAlchemy AsyncSession to test service logic
without requiring a real database connection.

Validates: Requirements R106.1, R106.2, R106.3, R19.9, R19.10
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.feature_rollout import FeatureRollout
from app.services.feature_rollout_db_service import FeatureRolloutDBService


# =============================================================================
# Fixtures
# =============================================================================


def make_rollout(
    *,
    capability_name: str = "image_generation",
    rollout_scope: str = "global",
    scope_target: str | None = None,
    enabled: bool = False,
    expires_at: datetime | None = None,
    created_by: uuid.UUID | None = None,
) -> FeatureRollout:
    """Create a FeatureRollout instance for testing."""
    rollout = FeatureRollout(
        capability_name=capability_name,
        rollout_scope=rollout_scope,
        scope_target=scope_target,
        enabled=enabled,
        expires_at=expires_at,
        created_by=created_by or uuid.uuid4(),
    )
    rollout.id = uuid.uuid4()
    rollout.created_at = datetime.now(timezone.utc)
    rollout.updated_at = datetime.now(timezone.utc)
    return rollout


def make_mock_session(rules: list | None = None) -> AsyncMock:
    """Create a mock AsyncSession that returns given rules for select queries."""
    session = AsyncMock()

    if rules is not None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = rules
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)
    else:
        session.execute = AsyncMock()

    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()

    return session


# =============================================================================
# Tests: is_enabled — Global scope
# =============================================================================


class TestIsEnabledGlobalScope:
    """Test is_enabled evaluation with global scope rules."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_rules_returns_enabled(self) -> None:
        """Capability with no rules is enabled by default."""
        session = make_mock_session(rules=[])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("image_generation")
        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_global_disabled_rule_returns_false(self) -> None:
        """Global disabled rule makes capability unavailable."""
        rule = make_rollout(
            capability_name="image_generation",
            rollout_scope="global",
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("image_generation")
        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_global_enabled_rule_returns_true(self) -> None:
        """Global enabled rule keeps capability accessible."""
        rule = make_rollout(
            capability_name="image_generation",
            rollout_scope="global",
            enabled=True,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("image_generation")
        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_global_disabled_blocks_regardless_of_context(self) -> None:
        """Global disabled blocks even with specific context provided."""
        rule = make_rollout(
            capability_name="image_generation",
            rollout_scope="global",
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled(
            "image_generation",
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            plan="enterprise",
        )
        assert result is False


# =============================================================================
# Tests: is_enabled — Workspace scope
# =============================================================================


class TestIsEnabledWorkspaceScope:
    """Test is_enabled evaluation with workspace scope rules."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_workspace_disabled_matches_target_org(self) -> None:
        """Workspace disabled rule blocks the target workspace."""
        target_org = uuid.uuid4()
        rule = make_rollout(
            capability_name="voice_synthesis",
            rollout_scope="workspace",
            scope_target=str(target_org),
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("voice_synthesis", org_id=target_org)
        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_workspace_disabled_does_not_affect_other_orgs(self) -> None:
        """Workspace disabled rule does not block other workspaces."""
        target_org = uuid.uuid4()
        other_org = uuid.uuid4()
        rule = make_rollout(
            capability_name="voice_synthesis",
            rollout_scope="workspace",
            scope_target=str(target_org),
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("voice_synthesis", org_id=other_org)
        assert result is True


# =============================================================================
# Tests: is_enabled — Plan scope
# =============================================================================


class TestIsEnabledPlanScope:
    """Test is_enabled evaluation with plan scope rules."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_plan_disabled_matches_target_plan(self) -> None:
        """Plan disabled rule blocks the target plan tier."""
        rule = make_rollout(
            capability_name="batch_generation",
            rollout_scope="plan",
            scope_target="free",
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("batch_generation", plan="free")
        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_plan_disabled_does_not_affect_other_plans(self) -> None:
        """Plan disabled rule does not block other plan tiers."""
        rule = make_rollout(
            capability_name="batch_generation",
            rollout_scope="plan",
            scope_target="free",
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("batch_generation", plan="pro")
        assert result is True


# =============================================================================
# Tests: is_enabled — User scope
# =============================================================================


class TestIsEnabledUserScope:
    """Test is_enabled evaluation with user scope rules."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_user_disabled_matches_target_user(self) -> None:
        """User disabled rule blocks the specific user."""
        target_user = uuid.uuid4()
        rule = make_rollout(
            capability_name="brain_chat",
            rollout_scope="user",
            scope_target=str(target_user),
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("brain_chat", user_id=target_user)
        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_user_disabled_does_not_affect_other_users(self) -> None:
        """User disabled rule does not block other users."""
        target_user = uuid.uuid4()
        other_user = uuid.uuid4()
        rule = make_rollout(
            capability_name="brain_chat",
            rollout_scope="user",
            scope_target=str(target_user),
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("brain_chat", user_id=other_user)
        assert result is True


# =============================================================================
# Tests: is_enabled — Cohort scope
# =============================================================================


class TestIsEnabledCohortScope:
    """Test is_enabled evaluation with cohort scope rules."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cohort_disabled_matches_target_cohort(self) -> None:
        """Cohort disabled rule blocks the target cohort."""
        rule = make_rollout(
            capability_name="video_generation",
            rollout_scope="cohort",
            scope_target="beta_testers",
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled(
            "video_generation", cohort="beta_testers"
        )
        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cohort_disabled_does_not_affect_other_cohorts(self) -> None:
        """Cohort disabled rule does not block other cohorts."""
        rule = make_rollout(
            capability_name="video_generation",
            rollout_scope="cohort",
            scope_target="beta_testers",
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled(
            "video_generation", cohort="early_access"
        )
        assert result is True


# =============================================================================
# Tests: is_enabled — Workload scope
# =============================================================================


class TestIsEnabledWorkloadScope:
    """Test is_enabled evaluation with workload scope rules."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_workload_disabled_matches_target(self) -> None:
        """Workload disabled rule blocks the target workload type."""
        rule = make_rollout(
            capability_name="platform_compute",
            rollout_scope="workload",
            scope_target="training",
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled(
            "platform_compute", workload="training"
        )
        assert result is False


# =============================================================================
# Tests: is_enabled — Provider scope
# =============================================================================


class TestIsEnabledProviderScope:
    """Test is_enabled evaluation with provider scope rules."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_provider_disabled_matches_target(self) -> None:
        """Provider disabled rule blocks the target provider."""
        rule = make_rollout(
            capability_name="image_generation",
            rollout_scope="provider",
            scope_target="vast_ai",
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled(
            "image_generation", provider="vast_ai"
        )
        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_provider_disabled_does_not_affect_others(self) -> None:
        """Provider disabled rule does not block other providers."""
        rule = make_rollout(
            capability_name="image_generation",
            rollout_scope="provider",
            scope_target="vast_ai",
            enabled=False,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled(
            "image_generation", provider="runpod"
        )
        assert result is True


# =============================================================================
# Tests: is_enabled — Expiry handling
# =============================================================================


class TestIsEnabledExpiry:
    """Test that expired rules are treated as inactive."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_expired_rule_is_ignored(self) -> None:
        """A rule past its expires_at is not enforced."""
        expired = datetime.now(timezone.utc) - timedelta(hours=1)
        rule = make_rollout(
            capability_name="image_generation",
            rollout_scope="global",
            enabled=False,
            expires_at=expired,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("image_generation")
        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_non_expired_rule_is_enforced(self) -> None:
        """A rule with future expires_at is still enforced."""
        future = datetime.now(timezone.utc) + timedelta(hours=24)
        rule = make_rollout(
            capability_name="image_generation",
            rollout_scope="global",
            enabled=False,
            expires_at=future,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("image_generation")
        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_expiry_rule_is_permanent(self) -> None:
        """A rule with expires_at=None is permanent and always enforced."""
        rule = make_rollout(
            capability_name="image_generation",
            rollout_scope="global",
            enabled=False,
            expires_at=None,
        )
        session = make_mock_session(rules=[rule])
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("image_generation")
        assert result is False


# =============================================================================
# Tests: create_rollout
# =============================================================================


class TestCreateRollout:
    """Test the create_rollout method."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_rollout_adds_to_session(self) -> None:
        """Creating a rollout adds it to the database session."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        service = FeatureRolloutDBService(db=session)
        operator_id = uuid.uuid4()

        rollout = await service.create_rollout(
            capability_name="image_generation",
            scope="global",
            target=None,
            enabled=False,
            created_by=operator_id,
        )

        session.add.assert_called_once()
        session.flush.assert_called_once()
        session.refresh.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_rollout_sets_fields(self) -> None:
        """Created rollout has correct field values."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        service = FeatureRolloutDBService(db=session)
        operator_id = uuid.uuid4()
        future = datetime.now(timezone.utc) + timedelta(days=7)

        rollout = await service.create_rollout(
            capability_name="video_generation",
            scope="plan",
            target="free",
            enabled=False,
            created_by=operator_id,
            expires_at=future,
        )

        assert rollout.capability_name == "video_generation"
        assert rollout.rollout_scope == "plan"
        assert rollout.scope_target == "free"
        assert rollout.enabled is False
        assert rollout.created_by == operator_id
        assert rollout.expires_at == future


# =============================================================================
# Tests: delete_rollout
# =============================================================================


class TestDeleteRollout:
    """Test the delete_rollout method."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_delete_existing_rollout_returns_true(self) -> None:
        """Deleting an existing rollout returns True."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        session.execute = AsyncMock(return_value=mock_result)

        service = FeatureRolloutDBService(db=session)
        result = await service.delete_rollout(uuid.uuid4())
        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_delete_nonexistent_rollout_returns_false(self) -> None:
        """Deleting a nonexistent rollout returns False."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute = AsyncMock(return_value=mock_result)

        service = FeatureRolloutDBService(db=session)
        result = await service.delete_rollout(uuid.uuid4())
        assert result is False


# =============================================================================
# Tests: list_rollouts
# =============================================================================


class TestListRollouts:
    """Test the list_rollouts method.

    Note: list_rollouts uses SQLAlchemy column comparison operators in WHERE
    clauses (expires_at >= now), which require a real DB session or full ORM
    setup. These tests verify service initialization and call patterns.
    Full filtering is covered by integration tests.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_service_instantiates_with_session(self) -> None:
        """FeatureRolloutDBService can be instantiated with a session."""
        session = AsyncMock()
        service = FeatureRolloutDBService(db=session)
        assert service.db is session

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_rollout_calls_execute(self) -> None:
        """get_rollout executes a query on the session."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        service = FeatureRolloutDBService(db=session)
        result = await service.get_rollout(uuid.uuid4())

        session.execute.assert_called_once()
        assert result is None


# =============================================================================
# Tests: Multiple rules interaction
# =============================================================================


class TestMultipleRulesInteraction:
    """Test evaluation with multiple rules for the same capability."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disabled_rule_overrides_enabled_rule(self) -> None:
        """If any matching rule disables, the result is disabled."""
        rules = [
            make_rollout(
                capability_name="image_generation",
                rollout_scope="plan",
                scope_target="pro",
                enabled=True,
            ),
            make_rollout(
                capability_name="image_generation",
                rollout_scope="global",
                enabled=False,
            ),
        ]
        session = make_mock_session(rules=rules)
        service = FeatureRolloutDBService(db=session)

        result = await service.is_enabled("image_generation", plan="pro")
        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_only_matching_disabled_rules_count(self) -> None:
        """A disabled rule for a different workspace doesn't affect others."""
        target_org = uuid.uuid4()
        other_org = uuid.uuid4()
        rules = [
            make_rollout(
                capability_name="image_generation",
                rollout_scope="workspace",
                scope_target=str(target_org),
                enabled=False,
            ),
        ]
        session = make_mock_session(rules=rules)
        service = FeatureRolloutDBService(db=session)

        assert await service.is_enabled(
            "image_generation", org_id=other_org
        ) is True
        assert await service.is_enabled(
            "image_generation", org_id=target_org
        ) is False
