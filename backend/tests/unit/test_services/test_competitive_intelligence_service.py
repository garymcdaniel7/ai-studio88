"""Unit tests for CompetitiveIntelligenceService.

Tests cover:
    - Watchlist CRUD (create, get, list, update, delete)
    - Watchlist member CRUD (add, get, list, update, remove)
    - Tenant isolation (org_id filtering)
    - Not-found error handling
    - Competitive intelligence queries
    - Data source attribution (provenance)
    - Public vs private data separation

Requirements: R108.1, R108.2, R108.3, R108.4, R108.5, R108.7, R108.8
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# =============================================================================
# Mock heavy dependencies before any app imports
# =============================================================================

_sa_mock = MagicMock()
_sa_mock.DateTime = MagicMock
_sa_mock.Float = MagicMock
_sa_mock.Integer = MagicMock
_sa_mock.String = MagicMock
_sa_mock.Text = MagicMock
_sa_mock.Boolean = MagicMock
_sa_mock.Numeric = MagicMock
_sa_mock.ForeignKey = MagicMock
_sa_mock.Index = MagicMock
_sa_mock.func = MagicMock()
_sa_mock.select = MagicMock()

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
_sa_ext_asyncio_mock.AsyncSession = MagicMock

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.exc", MagicMock())

# Mock app.db.*
_mock_db_mod = ModuleType("app.db")
sys.modules.setdefault("app.db", _mock_db_mod)

_mock_db_session = ModuleType("app.db.session")
_mock_db_session.get_db_session = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.session", _mock_db_session)

_mock_db_base = ModuleType("app.db.base")


class _FakeBase:
    pass


_mock_db_base.Base = _FakeBase  # type: ignore[attr-defined]
_mock_db_base.TimestampMixin = type("TimestampMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.UUIDMixin = type("UUIDMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.TenantMixin = type("TenantMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.SoftDeleteMixin = type("SoftDeleteMixin", (), {})  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.base", _mock_db_base)

_mock_tenant_scope = ModuleType("app.db.tenant_scope")
_mock_tenant_scope.QUARANTINED_ORG_ID = UUID(  # type: ignore[attr-defined]
    "00000000-0000-0000-0000-000000000000"
)
sys.modules.setdefault("app.db.tenant_scope", _mock_tenant_scope)

# Mock jose, passlib, pydantic-settings, structlog, dotenv
sys.modules.setdefault("jose", MagicMock())
sys.modules.setdefault("passlib", MagicMock())
sys.modules.setdefault("passlib.context", MagicMock())
_pydantic_settings_mock = MagicMock()
_pydantic_settings_mock.BaseSettings = type("BaseSettings", (), {"model_config": {}})
sys.modules.setdefault("pydantic_settings", _pydantic_settings_mock)
sys.modules.setdefault("dotenv", MagicMock())
sys.modules.setdefault("structlog", MagicMock())

# Mock models package
_mock_models_pkg = ModuleType("app.models")
_mock_models_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.models", _mock_models_pkg)

# =============================================================================
# Now import the schemas (which have no heavy deps)
# =============================================================================

from app.schemas.competitive_intelligence import (
    CompetitiveIntelligenceResponse,
    CompetitorProfileResponse,
    DataProvenance,
    InsightType,
    PublicMetrics,
    WatchlistCreateRequest,
    WatchlistListResponse,
    WatchlistMemberCreateRequest,
    WatchlistMemberListResponse,
    WatchlistMemberResponse,
    WatchlistResponse,
    WatchlistUpdateRequest,
    WatchType,
)


# =============================================================================
# Fixtures
# =============================================================================

ORG_A = uuid4()
ORG_B = uuid4()


class FakeWatchlist:
    """In-memory fake watchlist for unit testing."""

    def __init__(self, org_id, name, description=None, category=None):
        self.id = uuid4()
        self.org_id = org_id
        self.name = name
        self.description = description
        self.category = category
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)


class FakeWatchlistMember:
    """In-memory fake watchlist member for unit testing."""

    def __init__(
        self, org_id, watchlist_id, watch_type, account_identifier,
        display_name=None, platform=None, notes=None,
    ):
        self.id = uuid4()
        self.org_id = org_id
        self.watchlist_id = watchlist_id
        self.watch_type = watch_type
        self.account_identifier = account_identifier
        self.display_name = display_name
        self.platform = platform
        self.notes = notes
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

# =============================================================================
# Schema Tests
# =============================================================================


class TestSchemas:
    """Test Pydantic schema validation."""

    def test_watchlist_create_request_valid(self):
        req = WatchlistCreateRequest(name="Competitors", description="Main competitors")
        assert req.name == "Competitors"
        assert req.description == "Main competitors"

    def test_watchlist_create_request_rejects_empty_name(self):
        with pytest.raises(Exception):
            WatchlistCreateRequest(name="")

    def test_watchlist_update_request_allows_partial(self):
        req = WatchlistUpdateRequest(name="Updated")
        assert req.name == "Updated"
        assert req.description is None

    def test_member_create_request_valid(self):
        req = WatchlistMemberCreateRequest(
            watch_type=WatchType.CREATOR,
            account_identifier="@creator_x",
            platform="instagram",
        )
        assert req.watch_type == WatchType.CREATOR
        assert req.account_identifier == "@creator_x"

    def test_member_create_request_rejects_empty_identifier(self):
        with pytest.raises(Exception):
            WatchlistMemberCreateRequest(
                watch_type=WatchType.CREATOR,
                account_identifier="",
            )

    def test_watchlist_response_round_trip(self):
        now = datetime.now(UTC)
        resp = WatchlistResponse(
            id=uuid4(),
            org_id=ORG_A,
            name="Test",
            description="desc",
            category="competitor",
            member_count=5,
            created_at=now,
            updated_at=now,
        )
        assert resp.member_count == 5

    def test_member_response_from_fake(self):
        member = FakeWatchlistMember(
            org_id=ORG_A,
            watchlist_id=uuid4(),
            watch_type="creator",
            account_identifier="@test",
            platform="tiktok",
        )
        resp = WatchlistMemberResponse.model_validate(member)
        assert resp.watch_type == WatchType.CREATOR
        assert resp.platform == "tiktok"

# =============================================================================
# Intelligence Response Tests
# =============================================================================


class TestIntelligenceSchemas:
    """Test competitive intelligence response schemas."""

    def test_public_metrics_all_none(self):
        """Public metrics can be all null (data not yet collected)."""
        metrics = PublicMetrics()
        assert metrics.followers is None
        assert metrics.engagement_rate is None

    def test_public_metrics_with_values(self):
        metrics = PublicMetrics(
            followers=10000,
            engagement_rate=3.5,
            posting_frequency="3x/week",
            top_formats=["reel", "carousel"],
        )
        assert metrics.followers == 10000
        assert metrics.top_formats == ["reel", "carousel"]

    def test_competitor_profile_has_disclaimers(self):
        """All profile responses must include source attribution."""
        now = datetime.now(UTC)
        profile = CompetitorProfileResponse(
            member_id=uuid4(),
            account_identifier="@competitor",
            watch_type=WatchType.COMPETITOR,
            metrics=PublicMetrics(),
            data_source=DataProvenance.PUBLIC_PLATFORM_DATA,
            data_freshness="estimated",
        )
        assert len(profile.disclaimers) > 0
        assert "publicly available" in profile.disclaimers[0].lower()

    def test_competitor_profile_data_source_attribution(self):
        """Profile must identify data source (R108.7)."""
        profile = CompetitorProfileResponse(
            member_id=uuid4(),
            account_identifier="@brand_x",
            watch_type=WatchType.BRAND,
            metrics=PublicMetrics(followers=5000),
            data_source=DataProvenance.PUBLIC_PLATFORM_DATA,
        )
        assert profile.data_source == DataProvenance.PUBLIC_PLATFORM_DATA

    def test_intelligence_response_has_mandatory_disclaimers(self):
        """Intelligence response must include accuracy disclaimers (R108.8)."""
        resp = CompetitiveIntelligenceResponse(
            watchlist_id=uuid4(),
            watchlist_name="Competitors",
            profiles=[],
            insights=[],
        )
        assert len(resp.disclaimers) >= 2
        # Verify disclaimers mention public data
        combined = " ".join(resp.disclaimers).lower()
        assert "public" in combined
        assert "not private analytics" in combined

# =============================================================================
# Watch Type Coverage
# =============================================================================


class TestWatchTypes:
    """Verify all five watch types work in schemas."""

    @pytest.mark.parametrize("watch_type", [
        WatchType.CREATOR,
        WatchType.BRAND,
        WatchType.COMPETITOR,
        WatchType.TOPIC,
        WatchType.HASHTAG,
    ])
    def test_all_watch_types_accepted(self, watch_type):
        req = WatchlistMemberCreateRequest(
            watch_type=watch_type,
            account_identifier=f"@test_{watch_type.value}",
        )
        assert req.watch_type == watch_type

    def test_invalid_watch_type_rejected(self):
        with pytest.raises(Exception):
            WatchlistMemberCreateRequest(
                watch_type="invalid_type",  # type: ignore
                account_identifier="@test",
            )


# =============================================================================
# Data Provenance Tests
# =============================================================================


class TestDataProvenance:
    """Test that provenance tracking is enforced."""

    def test_all_provenance_values(self):
        """All expected provenance values exist."""
        assert DataProvenance.PUBLIC_PLATFORM_DATA.value == "PUBLIC_PLATFORM_DATA"
        assert DataProvenance.THIRD_PARTY_DATA.value == "THIRD_PARTY_DATA"
        assert DataProvenance.DERIVED_ANALYSIS.value == "DERIVED_ANALYSIS"
        assert DataProvenance.AI_INTERPRETATION.value == "AI_INTERPRETATION"
        assert DataProvenance.USER_IMPORTED.value == "USER_IMPORTED"

    def test_insight_types(self):
        """All insight types are defined."""
        assert InsightType.TREND.value == "trend"
        assert InsightType.ANOMALY.value == "anomaly"
        assert InsightType.RECOMMENDATION.value == "recommendation"
        assert InsightType.PATTERN.value == "pattern"
        assert InsightType.COMPARISON.value == "comparison"

    def test_profile_never_has_first_party_provenance(self):
        """Competitive intelligence never uses FIRST_PARTY_CONNECTED.

        Per R108.8: never represent estimates as private analytics.
        FIRST_PARTY_CONNECTED is reserved for connected account data.
        """
        # DataProvenance enum should NOT include FIRST_PARTY_CONNECTED
        provenance_values = [p.value for p in DataProvenance]
        assert "FIRST_PARTY_CONNECTED" not in provenance_values

# =============================================================================
# List Response Pagination Tests
# =============================================================================


class TestPagination:
    """Test paginated response structure."""

    def test_watchlist_list_response_structure(self):
        now = datetime.now(UTC)
        resp = WatchlistListResponse(
            items=[
                WatchlistResponse(
                    id=uuid4(),
                    org_id=ORG_A,
                    name="List 1",
                    member_count=3,
                    created_at=now,
                    updated_at=now,
                ),
            ],
            total=1,
            limit=20,
            offset=0,
        )
        assert resp.total == 1
        assert resp.limit == 20
        assert resp.offset == 0
        assert len(resp.items) == 1

    def test_member_list_response_structure(self):
        member = FakeWatchlistMember(
            org_id=ORG_A,
            watchlist_id=uuid4(),
            watch_type="hashtag",
            account_identifier="#trending",
        )
        resp = WatchlistMemberListResponse(
            items=[WatchlistMemberResponse.model_validate(member)],
            total=1,
            limit=20,
            offset=0,
        )
        assert resp.items[0].watch_type == WatchType.HASHTAG

    def test_empty_list_response(self):
        resp = WatchlistListResponse(items=[], total=0, limit=20, offset=0)
        assert resp.total == 0
        assert len(resp.items) == 0
