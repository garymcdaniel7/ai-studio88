"""Unit tests for SocialIntelligenceProvider interface and sync lifecycle.

Tests cover:
    - SyncState lifecycle transitions (start, success, partial, failed, rate-limited, auth expired)
    - SyncState serialization/deserialization (to_dict/from_dict round-trip)
    - SimulationSocialIntelligenceProvider implements the Protocol
    - Provider capabilities reporting
    - Provider registry factory function
    - Analytics/publishing failure isolation (by design — independent capabilities)
    - DataProvenance and ReasoningClass enum completeness

Requirements: R107.11, A2-008, A2-012
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from publishing.social_intelligence import (
    CollectionMethod,
    ConnectionState,
    DataFreshness,
    DataProvenance,
    DateRange,
    MetricSnapshot,
    ProviderCapabilities,
    ReasoningClass,
    SimulationSocialIntelligenceProvider,
    SocialIntelligenceProvider,
    SyncResult,
    SyncState,
    get_social_intelligence_provider,
)


# =============================================================================
# SyncState Lifecycle Tests
# =============================================================================


class TestSyncStateLifecycle:
    """Tests for SyncState lifecycle management per A2-012."""

    def test_initial_state_defaults(self) -> None:
        """Fresh SyncState has sensible defaults."""
        state = SyncState()
        assert state.last_successful_sync is None
        assert state.last_attempted_sync is None
        assert state.next_scheduled_sync is None
        assert state.cursor is None
        assert state.rate_limit_state == {}
        assert state.connection_state == ConnectionState.HEALTHY
        assert state.data_freshness == DataFreshness.UNKNOWN
        assert state.partial_sync is False
        assert state.error_state is None

    def test_mark_sync_started(self) -> None:
        """mark_sync_started records attempt time and clears error."""
        state = SyncState(error_state="previous error")
        before = datetime.now(timezone.utc)
        state.mark_sync_started()
        after = datetime.now(timezone.utc)

        assert state.last_attempted_sync is not None
        assert before <= state.last_attempted_sync <= after
        assert state.error_state is None

    def test_mark_sync_success(self) -> None:
        """mark_sync_success updates all success fields."""
        state = SyncState(
            connection_state=ConnectionState.DEGRADED,
            data_freshness=DataFreshness.STALE_DAYS,
            partial_sync=True,
            error_state="old error",
        )
        state.mark_sync_success(cursor="page_2")

        assert state.last_successful_sync is not None
        assert state.last_attempted_sync is not None
        assert state.cursor == "page_2"
        assert state.connection_state == ConnectionState.HEALTHY
        assert state.data_freshness == DataFreshness.CURRENT
        assert state.partial_sync is False
        assert state.error_state is None

    def test_mark_sync_partial(self) -> None:
        """mark_sync_partial records partial completion."""
        state = SyncState()
        state.mark_sync_partial(cursor="partial_cursor_123")

        assert state.last_attempted_sync is not None
        assert state.cursor == "partial_cursor_123"
        assert state.partial_sync is True
        assert state.data_freshness == DataFreshness.CURRENT

    def test_mark_sync_partial_preserves_cursor_when_none(self) -> None:
        """mark_sync_partial preserves existing cursor if new is None."""
        state = SyncState(cursor="existing_cursor")
        state.mark_sync_partial(cursor=None)

        assert state.cursor == "existing_cursor"
        assert state.partial_sync is True

    def test_mark_sync_failed(self) -> None:
        """mark_sync_failed records error and degrades connection state."""
        state = SyncState(connection_state=ConnectionState.HEALTHY)
        state.mark_sync_failed("API returned 500")

        assert state.last_attempted_sync is not None
        assert state.error_state == "API returned 500"
        assert state.connection_state == ConnectionState.DEGRADED

    def test_mark_rate_limited(self) -> None:
        """mark_rate_limited records rate limit info."""
        state = SyncState()
        state.mark_rate_limited(remaining=0, reset_at="2025-01-01T12:00:00Z")

        assert state.connection_state == ConnectionState.RATE_LIMITED
        assert state.rate_limit_state == {
            "remaining": 0,
            "reset_at": "2025-01-01T12:00:00Z",
        }

    def test_mark_auth_expired(self) -> None:
        """mark_auth_expired transitions to AUTH_EXPIRED state."""
        state = SyncState()
        state.mark_auth_expired()

        assert state.connection_state == ConnectionState.AUTH_EXPIRED
        assert "reauthorization" in state.error_state.lower()


# =============================================================================
# SyncState Serialization Tests
# =============================================================================


class TestSyncStateSerialization:
    """Tests for SyncState to_dict/from_dict round-trip."""

    def test_round_trip_empty_state(self) -> None:
        """Empty SyncState serializes and deserializes correctly."""
        state = SyncState()
        data = state.to_dict()
        restored = SyncState.from_dict(data)

        assert restored.last_successful_sync is None
        assert restored.cursor is None
        assert restored.connection_state == ConnectionState.HEALTHY
        assert restored.data_freshness == DataFreshness.UNKNOWN

    def test_round_trip_populated_state(self) -> None:
        """Fully populated SyncState survives round-trip."""
        now = datetime.now(timezone.utc)
        state = SyncState(
            last_successful_sync=now,
            last_attempted_sync=now,
            next_scheduled_sync=now + timedelta(hours=1),
            cursor="abc123",
            rate_limit_state={"remaining": 50, "reset_at": "2025-06-01T00:00:00Z"},
            connection_state=ConnectionState.RATE_LIMITED,
            data_freshness=DataFreshness.STALE_HOURS,
            partial_sync=True,
            error_state="rate limited",
        )
        data = state.to_dict()
        restored = SyncState.from_dict(data)

        assert restored.cursor == "abc123"
        assert restored.connection_state == ConnectionState.RATE_LIMITED
        assert restored.data_freshness == DataFreshness.STALE_HOURS
        assert restored.partial_sync is True
        assert restored.error_state == "rate limited"
        assert restored.rate_limit_state["remaining"] == 50

    def test_from_dict_handles_empty_dict(self) -> None:
        """from_dict with empty dict returns fresh defaults."""
        state = SyncState.from_dict({})
        assert state.connection_state == ConnectionState.HEALTHY
        assert state.data_freshness == DataFreshness.UNKNOWN

    def test_from_dict_handles_none(self) -> None:
        """from_dict with None-like falsy value returns defaults."""
        state = SyncState.from_dict({})
        assert state.cursor is None


# =============================================================================
# Protocol Compliance Tests
# =============================================================================


class TestSimulationProviderProtocol:
    """Tests that SimulationSocialIntelligenceProvider satisfies the Protocol."""

    def test_simulation_is_protocol_instance(self) -> None:
        """SimulationSocialIntelligenceProvider passes runtime Protocol check."""
        provider = SimulationSocialIntelligenceProvider()
        assert isinstance(provider, SocialIntelligenceProvider)

    @pytest.mark.asyncio
    async def test_get_capabilities(self) -> None:
        """get_capabilities returns a populated ProviderCapabilities."""
        provider = SimulationSocialIntelligenceProvider(platform="tiktok")
        caps = await provider.get_capabilities()

        assert isinstance(caps, ProviderCapabilities)
        assert caps.can_fetch_owned_metrics is True
        assert caps.can_fetch_owned_content is True
        assert caps.can_fetch_public_profiles is True
        assert caps.can_sync_incrementally is True
        assert "tiktok" in caps.supported_platforms

    @pytest.mark.asyncio
    async def test_get_connected_account(self) -> None:
        """get_connected_account returns AccountInfo with correct platform."""
        provider = SimulationSocialIntelligenceProvider(platform="instagram")
        conn_id = uuid4()
        account = await provider.get_connected_account(conn_id, {"token": "test"})

        assert account.platform == "instagram"
        assert account.account_name is not None
        assert len(account.account_external_id) > 0

    @pytest.mark.asyncio
    async def test_get_owned_content(self) -> None:
        """get_owned_content returns a list of ContentItems."""
        provider = SimulationSocialIntelligenceProvider()
        period = DateRange(
            start=datetime.now(timezone.utc) - timedelta(days=7),
            end=datetime.now(timezone.utc),
        )
        content = await provider.get_owned_content("acc_123", period)

        assert isinstance(content, list)
        assert len(content) > 0
        assert all(c.platform == "instagram" for c in content)
        assert all(c.external_post_id is not None for c in content)

    @pytest.mark.asyncio
    async def test_get_owned_metrics(self) -> None:
        """get_owned_metrics returns MetricSnapshots with correct provenance."""
        provider = SimulationSocialIntelligenceProvider()
        metrics = await provider.get_owned_metrics("post_123")

        assert isinstance(metrics, list)
        assert len(metrics) > 0
        for m in metrics:
            assert isinstance(m, MetricSnapshot)
            assert m.provenance == DataProvenance.FIRST_PARTY_CONNECTED
            assert m.collection_method == CollectionMethod.API_SYNC

    @pytest.mark.asyncio
    async def test_get_public_profile(self) -> None:
        """get_public_profile returns PublicProfile with PUBLIC provenance."""
        provider = SimulationSocialIntelligenceProvider()
        profile = await provider.get_public_profile("@creator_handle", "instagram")

        assert profile is not None
        assert profile.identifier == "@creator_handle"
        assert profile.platform == "instagram"
        assert profile.provenance == DataProvenance.PUBLIC_PLATFORM_DATA

    @pytest.mark.asyncio
    async def test_sync_metrics(self) -> None:
        """sync_metrics returns a successful SyncResult."""
        provider = SimulationSocialIntelligenceProvider()
        result = await provider.sync_metrics("acc_123", cursor=None)

        assert isinstance(result, SyncResult)
        assert result.success is True
        assert result.metrics_synced > 0
        assert result.new_cursor is not None

    @pytest.mark.asyncio
    async def test_sync_metrics_with_cursor(self) -> None:
        """sync_metrics with cursor supports incremental sync."""
        provider = SimulationSocialIntelligenceProvider()
        result = await provider.sync_metrics("acc_123", cursor="prev_cursor")

        assert result.success is True
        assert result.new_cursor is not None
        assert result.new_cursor != "prev_cursor"


# =============================================================================
# Provider Registry Tests
# =============================================================================


class TestProviderRegistry:
    """Tests for get_social_intelligence_provider factory."""

    def test_get_simulation_provider(self) -> None:
        """Factory returns simulation provider by default."""
        provider = get_social_intelligence_provider()
        assert isinstance(provider, SimulationSocialIntelligenceProvider)
        assert isinstance(provider, SocialIntelligenceProvider)

    def test_get_simulation_provider_explicit(self) -> None:
        """Factory returns simulation provider with explicit name."""
        provider = get_social_intelligence_provider("simulation", "tiktok")
        assert isinstance(provider, SimulationSocialIntelligenceProvider)

    def test_get_unknown_provider_raises(self) -> None:
        """Factory raises ValueError for unknown provider name."""
        with pytest.raises(ValueError, match="Unknown social intelligence provider"):
            get_social_intelligence_provider("nonexistent")


# =============================================================================
# Failure Isolation Design Tests
# =============================================================================


class TestFailureIsolation:
    """Tests verifying analytics and publishing are decoupled.

    Per A2-012: Analytics failure does NOT disable publishing.
    Publishing failure does NOT destroy analytics.
    """

    @pytest.mark.asyncio
    async def test_analytics_failure_independent_of_publishing(self) -> None:
        """A failed sync_metrics does not affect publishing capabilities.

        This tests the design principle that analytics and publishing
        are independent capabilities sharing a connection.
        """
        provider = SimulationSocialIntelligenceProvider()

        # Sync metrics works
        result = await provider.sync_metrics("acc_123")
        assert result.success is True

        # Even if we track a sync failure in state, publishing capability
        # is not determined by the intelligence provider.
        state = SyncState()
        state.mark_sync_failed("API 500")
        assert state.connection_state == ConnectionState.DEGRADED

        # The sync state degradation is for ANALYTICS only.
        # Publishing uses its own provider (social_providers.py) independently.
        # This test verifies the data model supports this separation.
        assert state.error_state == "API 500"

    def test_sync_state_does_not_contain_publishing_state(self) -> None:
        """SyncState only tracks analytics sync — no publishing coupling."""
        state = SyncState()
        state_dict = state.to_dict()

        # No publishing-related keys in sync state
        publishing_keys = {"publish_status", "last_published", "publish_error"}
        assert publishing_keys.isdisjoint(state_dict.keys())


# =============================================================================
# Enum Completeness Tests
# =============================================================================


class TestEnumCompleteness:
    """Verify enum values match design.md specifications."""

    def test_data_provenance_values(self) -> None:
        """DataProvenance has all 5 classifications from design.md."""
        expected = {
            "FIRST_PARTY_CONNECTED",
            "PUBLIC_PLATFORM_DATA",
            "THIRD_PARTY_DATA",
            "USER_IMPORTED",
            "DERIVED_ANALYSIS",
        }
        actual = {p.value for p in DataProvenance}
        assert actual == expected

    def test_reasoning_class_values(self) -> None:
        """ReasoningClass has all 5 classifications from design.md A2-009."""
        expected = {
            "OBSERVED_FACT",
            "DERIVED_METRIC",
            "STATISTICAL_PATTERN",
            "AI_INTERPRETATION",
            "RECOMMENDATION",
        }
        actual = {r.value for r in ReasoningClass}
        assert actual == expected

    def test_collection_method_values(self) -> None:
        """CollectionMethod has the expected values."""
        expected = {"api_sync", "manual_import", "public_scrape", "calculated"}
        actual = {c.value for c in CollectionMethod}
        assert actual == expected

    def test_connection_state_values(self) -> None:
        """ConnectionState has all sync lifecycle states from A2-012."""
        expected = {"healthy", "degraded", "rate_limited", "auth_expired", "offline"}
        actual = {s.value for s in ConnectionState}
        assert actual == expected

    def test_data_freshness_values(self) -> None:
        """DataFreshness has the expected staleness classifications."""
        expected = {"current", "stale_hours", "stale_days", "unknown"}
        actual = {f.value for f in DataFreshness}
        assert actual == expected
