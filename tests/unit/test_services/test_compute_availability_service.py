"""Unit tests for the ComputeAvailabilityService.

Tests the enforcement logic for DISABLED/SELECTIVE/ENABLED compute availability
states, cache TTL behavior, and selective grant evaluation.

No I/O — uses mocked database sessions.

Run with: pytest tests/unit/test_services/test_compute_availability_service.py -v
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.compute_availability_service import (
    ComputeAvailabilityService,
    ComputeAvailabilityState,
    ComputeNotGrantedError,
    GrantType,
    PlatformComputeDisabledError,
    _cache,
    _CACHE_TTL_SECONDS,
    invalidate_compute_cache,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset the module-level cache before each test."""
    _cache._state = ComputeAvailabilityState.DISABLED
    _cache._grants = []
    _cache._last_refresh = 0.0
    _cache._changed_by = None
    _cache._changed_at = None
    _cache._reason = None
    yield
    # Clean up after test
    _cache._state = ComputeAvailabilityState.DISABLED
    _cache._grants = []
    _cache._last_refresh = 0.0


def _make_grant(
    grant_type: str = "workspace",
    grant_target: str = "",
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> MagicMock:
    """Create a mock ComputeSelectiveGrant for testing."""
    grant = MagicMock()
    grant.id = uuid.uuid4()
    grant.grant_type = grant_type
    grant.grant_target = grant_target
    grant.expires_at = expires_at
    grant.revoked_at = revoked_at
    grant.revoked_by = None
    grant.granted_by = uuid.uuid4()
    grant.created_at = datetime.now(timezone.utc)
    return grant


def _make_config(
    state: str = "disabled",
    changed_by: uuid.UUID | None = None,
    reason: str | None = None,
) -> MagicMock:
    """Create a mock ComputeAvailabilityConfig for testing."""
    config = MagicMock()
    config.id = uuid.uuid4()
    config.state = state
    config.changed_by = changed_by or uuid.uuid4()
    config.changed_at = datetime.now(timezone.utc)
    config.reason = reason
    return config


# =============================================================================
# Tests: DISABLED State Enforcement (Property 14)
# =============================================================================


@pytest.mark.unit
class TestDisabledStateEnforcement:
    """When state is DISABLED, ALL compute requests are rejected.

    This is the core enforcement of R86.2: DISABLED rejects regardless of
    org_id, role, workload type, or request origin.
    """

    @pytest.mark.asyncio
    async def test_disabled_rejects_any_org(self):
        """DISABLED state rejects any org_id with PlatformComputeDisabledError."""
        # Set cache to DISABLED (fresh)
        _cache.update(
            state=ComputeAvailabilityState.DISABLED,
            grants=[],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        with pytest.raises(PlatformComputeDisabledError) as exc_info:
            await service.check_compute_availability(org_id=uuid.uuid4())

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "PLATFORM_COMPUTE_DISABLED"

    @pytest.mark.asyncio
    async def test_disabled_rejects_with_workload_class(self):
        """DISABLED rejects regardless of workload_class."""
        _cache.update(
            state=ComputeAvailabilityState.DISABLED,
            grants=[],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        with pytest.raises(PlatformComputeDisabledError):
            await service.check_compute_availability(
                org_id=uuid.uuid4(),
                workload_class="image_generation",
            )

    @pytest.mark.asyncio
    async def test_disabled_rejects_with_provider(self):
        """DISABLED rejects regardless of provider."""
        _cache.update(
            state=ComputeAvailabilityState.DISABLED,
            grants=[],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        with pytest.raises(PlatformComputeDisabledError):
            await service.check_compute_availability(
                org_id=uuid.uuid4(),
                provider="runpod",
            )

    @pytest.mark.asyncio
    async def test_disabled_ignores_grants(self):
        """DISABLED ignores selective grants — still rejects."""
        org_id = uuid.uuid4()
        grant = _make_grant(grant_type="workspace", grant_target=str(org_id))

        _cache.update(
            state=ComputeAvailabilityState.DISABLED,
            grants=[grant],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        # Even with a matching grant, DISABLED always rejects
        with pytest.raises(PlatformComputeDisabledError):
            await service.check_compute_availability(org_id=org_id)


# =============================================================================
# Tests: ENABLED State
# =============================================================================


@pytest.mark.unit
class TestEnabledState:
    """When state is ENABLED, all eligible workspaces have access."""

    @pytest.mark.asyncio
    async def test_enabled_allows_any_org(self):
        """ENABLED state allows any org_id."""
        _cache.update(
            state=ComputeAvailabilityState.ENABLED,
            grants=[],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        # Should not raise
        result = await service.check_compute_availability(org_id=uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_enabled_allows_with_any_workload(self):
        """ENABLED allows any workload class."""
        _cache.update(
            state=ComputeAvailabilityState.ENABLED,
            grants=[],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        result = await service.check_compute_availability(
            org_id=uuid.uuid4(),
            workload_class="training",
            provider="runpod",
        )
        assert result is None


# =============================================================================
# Tests: SELECTIVE State Enforcement
# =============================================================================


@pytest.mark.unit
class TestSelectiveStateEnforcement:
    """When state is SELECTIVE, only granted workspaces/criteria have access."""

    @pytest.mark.asyncio
    async def test_selective_rejects_without_grant(self):
        """SELECTIVE rejects workspace without a matching grant."""
        _cache.update(
            state=ComputeAvailabilityState.SELECTIVE,
            grants=[],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        with pytest.raises(ComputeNotGrantedError) as exc_info:
            await service.check_compute_availability(org_id=uuid.uuid4())

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "COMPUTE_NOT_GRANTED"

    @pytest.mark.asyncio
    async def test_selective_allows_workspace_grant(self):
        """SELECTIVE allows workspace with a matching workspace grant."""
        org_id = uuid.uuid4()
        grant = _make_grant(grant_type="workspace", grant_target=str(org_id))

        _cache.update(
            state=ComputeAvailabilityState.SELECTIVE,
            grants=[grant],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        result = await service.check_compute_availability(org_id=org_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_selective_allows_workload_grant(self):
        """SELECTIVE allows request with matching workload grant."""
        grant = _make_grant(grant_type="workload", grant_target="image_generation")

        _cache.update(
            state=ComputeAvailabilityState.SELECTIVE,
            grants=[grant],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        result = await service.check_compute_availability(
            org_id=uuid.uuid4(),
            workload_class="image_generation",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_selective_rejects_mismatched_workload(self):
        """SELECTIVE rejects when workload doesn't match any grant."""
        grant = _make_grant(grant_type="workload", grant_target="training")

        _cache.update(
            state=ComputeAvailabilityState.SELECTIVE,
            grants=[grant],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        with pytest.raises(ComputeNotGrantedError):
            await service.check_compute_availability(
                org_id=uuid.uuid4(),
                workload_class="image_generation",
            )

    @pytest.mark.asyncio
    async def test_selective_allows_provider_grant(self):
        """SELECTIVE allows request with matching provider grant."""
        grant = _make_grant(grant_type="provider", grant_target="runpod")

        _cache.update(
            state=ComputeAvailabilityState.SELECTIVE,
            grants=[grant],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        result = await service.check_compute_availability(
            org_id=uuid.uuid4(),
            provider="runpod",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_selective_allows_promotion_grant(self):
        """SELECTIVE allows any workspace when a promotion grant is active."""
        grant = _make_grant(grant_type="promotion", grant_target="launch_promo_2026")

        _cache.update(
            state=ComputeAvailabilityState.SELECTIVE,
            grants=[grant],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        # Any org_id should be allowed during active promotion
        result = await service.check_compute_availability(org_id=uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_selective_rejects_different_workspace(self):
        """SELECTIVE rejects workspace not in any grant."""
        granted_org = uuid.uuid4()
        requesting_org = uuid.uuid4()
        grant = _make_grant(grant_type="workspace", grant_target=str(granted_org))

        _cache.update(
            state=ComputeAvailabilityState.SELECTIVE,
            grants=[grant],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        with pytest.raises(ComputeNotGrantedError):
            await service.check_compute_availability(org_id=requesting_org)

    @pytest.mark.asyncio
    async def test_selective_multiple_grants_any_match(self):
        """SELECTIVE allows if ANY grant matches (OR logic)."""
        org_id = uuid.uuid4()
        grant_other = _make_grant(
            grant_type="workspace", grant_target=str(uuid.uuid4())
        )
        grant_matching = _make_grant(
            grant_type="workspace", grant_target=str(org_id)
        )

        _cache.update(
            state=ComputeAvailabilityState.SELECTIVE,
            grants=[grant_other, grant_matching],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        result = await service.check_compute_availability(org_id=org_id)
        assert result is None


# =============================================================================
# Tests: Cache TTL Behavior
# =============================================================================


@pytest.mark.unit
class TestCacheTTLBehavior:
    """Test that the cache refreshes when TTL expires (within 60s)."""

    def test_cache_is_stale_when_never_refreshed(self):
        """Cache should be stale when _last_refresh is 0."""
        _cache._last_refresh = 0.0
        assert _cache.is_stale is True

    def test_cache_is_fresh_after_update(self):
        """Cache should not be stale immediately after update."""
        _cache.update(
            state=ComputeAvailabilityState.ENABLED,
            grants=[],
        )
        assert _cache.is_stale is False

    def test_cache_becomes_stale_after_ttl(self):
        """Cache should become stale after TTL seconds."""
        _cache.update(
            state=ComputeAvailabilityState.ENABLED,
            grants=[],
        )
        # Simulate time passage
        _cache._last_refresh = time.monotonic() - (_CACHE_TTL_SECONDS + 1)
        assert _cache.is_stale is True

    def test_invalidate_forces_stale(self):
        """invalidate_compute_cache() forces cache to be stale."""
        _cache.update(
            state=ComputeAvailabilityState.ENABLED,
            grants=[],
        )
        assert _cache.is_stale is False

        invalidate_compute_cache()
        assert _cache.is_stale is True

    @pytest.mark.asyncio
    async def test_stale_cache_triggers_db_query(self):
        """When cache is stale, service queries the database."""
        _cache._last_refresh = 0.0  # Force stale

        db = AsyncMock()

        # Mock the DB query results
        config_row = _make_config(state="enabled")
        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = config_row

        grants_result = MagicMock()
        grants_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[state_result, grants_result])

        service = ComputeAvailabilityService(db=db)
        state = await service.get_current_state()

        assert state == ComputeAvailabilityState.ENABLED
        assert db.execute.call_count == 2  # state + grants queries

    @pytest.mark.asyncio
    async def test_fresh_cache_skips_db_query(self):
        """When cache is fresh, service does NOT query the database."""
        _cache.update(
            state=ComputeAvailabilityState.ENABLED,
            grants=[],
            changed_by=uuid.uuid4(),
            changed_at=datetime.now(timezone.utc),
        )

        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)

        state = await service.get_current_state()

        assert state == ComputeAvailabilityState.ENABLED
        db.execute.assert_not_called()


# =============================================================================
# Tests: State Changes
# =============================================================================


@pytest.mark.unit
class TestStateChanges:
    """Test set_state_async() method for changing compute availability."""

    @pytest.mark.asyncio
    async def test_set_state_creates_config_row(self):
        """set_state_async() adds a new config row to the database."""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        service = ComputeAvailabilityService(db=db)
        user_id = uuid.uuid4()

        config = await service.set_state_async(
            new_state=ComputeAvailabilityState.ENABLED,
            changed_by=user_id,
            reason="Enabling for launch",
        )

        # Verify db.add was called
        db.add.assert_called_once()
        db.flush.assert_called_once()

        # Verify the returned config
        assert config.state == "enabled"
        assert config.changed_by == user_id
        assert config.reason == "Enabling for launch"

    @pytest.mark.asyncio
    async def test_set_state_invalidates_cache(self):
        """set_state_async() invalidates the cache for immediate propagation."""
        _cache.update(
            state=ComputeAvailabilityState.DISABLED,
            grants=[],
        )
        assert _cache.is_stale is False

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        service = ComputeAvailabilityService(db=db)

        await service.set_state_async(
            new_state=ComputeAvailabilityState.ENABLED,
            changed_by=uuid.uuid4(),
        )

        # Cache should be invalidated
        assert _cache.is_stale is True


# =============================================================================
# Tests: Grant Management
# =============================================================================


@pytest.mark.unit
class TestGrantManagement:
    """Test selective grant creation and revocation."""

    @pytest.mark.asyncio
    async def test_create_grant_adds_to_db(self):
        """create_selective_grant() adds a grant record."""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        service = ComputeAvailabilityService(db=db)
        user_id = uuid.uuid4()

        grant = await service.create_selective_grant(
            grant_type=GrantType.WORKSPACE,
            grant_target=str(uuid.uuid4()),
            granted_by=user_id,
        )

        db.add.assert_called_once()
        db.flush.assert_called_once()
        assert grant.grant_type == "workspace"
        assert grant.granted_by == user_id

    @pytest.mark.asyncio
    async def test_create_grant_with_expiry(self):
        """create_selective_grant() respects expires_at."""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        service = ComputeAvailabilityService(db=db)
        expires = datetime.now(timezone.utc) + timedelta(days=30)

        grant = await service.create_selective_grant(
            grant_type=GrantType.PROMOTION,
            grant_target="launch_promo",
            granted_by=uuid.uuid4(),
            expires_at=expires,
        )

        assert grant.expires_at == expires

    @pytest.mark.asyncio
    async def test_create_grant_invalidates_cache(self):
        """Creating a grant invalidates the cache."""
        _cache.update(
            state=ComputeAvailabilityState.SELECTIVE,
            grants=[],
        )
        assert _cache.is_stale is False

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        service = ComputeAvailabilityService(db=db)

        await service.create_selective_grant(
            grant_type=GrantType.WORKSPACE,
            grant_target=str(uuid.uuid4()),
            granted_by=uuid.uuid4(),
        )

        assert _cache.is_stale is True

    @pytest.mark.asyncio
    async def test_revoke_grant_sets_revoked_at(self):
        """revoke_selective_grant() sets revoked_at and revoked_by."""
        grant_id = uuid.uuid4()
        revoker_id = uuid.uuid4()

        mock_grant = MagicMock()
        mock_grant.id = grant_id
        mock_grant.grant_type = "workspace"
        mock_grant.grant_target = str(uuid.uuid4())
        mock_grant.revoked_at = None

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_grant
        db.execute = AsyncMock(return_value=result)
        db.flush = AsyncMock()

        service = ComputeAvailabilityService(db=db)
        revoked = await service.revoke_selective_grant(
            grant_id=grant_id,
            revoked_by=revoker_id,
        )

        assert revoked is not None
        assert mock_grant.revoked_by == revoker_id
        assert mock_grant.revoked_at is not None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_grant_returns_none(self):
        """Revoking a non-existent grant returns None."""
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        service = ComputeAvailabilityService(db=db)
        revoked = await service.revoke_selective_grant(
            grant_id=uuid.uuid4(),
            revoked_by=uuid.uuid4(),
        )

        assert revoked is None


# =============================================================================
# Tests: is_platform_compute_available (synchronous check)
# =============================================================================


@pytest.mark.unit
class TestIsPlatformComputeAvailable:
    """Test the quick synchronous availability check."""

    def test_returns_false_when_disabled(self):
        """Returns False when state is DISABLED."""
        _cache.update(
            state=ComputeAvailabilityState.DISABLED,
            grants=[],
        )
        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)
        assert service.is_platform_compute_available() is False

    def test_returns_true_when_selective(self):
        """Returns True when state is SELECTIVE."""
        _cache.update(
            state=ComputeAvailabilityState.SELECTIVE,
            grants=[],
        )
        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)
        assert service.is_platform_compute_available() is True

    def test_returns_true_when_enabled(self):
        """Returns True when state is ENABLED."""
        _cache.update(
            state=ComputeAvailabilityState.ENABLED,
            grants=[],
        )
        db = AsyncMock()
        service = ComputeAvailabilityService(db=db)
        assert service.is_platform_compute_available() is True


# =============================================================================
# Tests: Default State Behavior
# =============================================================================


@pytest.mark.unit
class TestDefaultStateBehavior:
    """Test behavior when no configuration exists in the database."""

    @pytest.mark.asyncio
    async def test_no_config_defaults_to_disabled(self):
        """When no config row exists, state defaults to DISABLED (safe)."""
        _cache._last_refresh = 0.0  # Force stale

        db = AsyncMock()
        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=state_result)

        service = ComputeAvailabilityService(db=db)

        with pytest.raises(PlatformComputeDisabledError):
            await service.check_compute_availability(org_id=uuid.uuid4())
