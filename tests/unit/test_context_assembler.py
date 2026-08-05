"""Context Assembler Tests (Story 081).

Proves: complete load, partial load, missing sources, failed loads,
authorization guard, stale exclusion, filtering, and cross-workspace rejection.

Run with:
    pytest tests/unit/test_context_assembler.py -v
"""
from __future__ import annotations

import pytest

from backend.context_assembler import (
    SOURCE_REQUIREMENTS,
    AssembledContext,
    ContextAssembler,
    ContextSource,
    LoadRequest,
    SourceLoadResult,
    SourceRequirement,
    SourceStatus,
    filter_by_approval,
    verify_workspace_access,
)


# =============================================================================
# Helpers
# =============================================================================


def _request(**overrides) -> LoadRequest:
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "talent_id": "talent-789",
        "project_id": "proj-abc",
    }
    defaults.update(overrides)
    return LoadRequest(**defaults)


def _success_loader(record_ids: list[str] | None = None, versions: list[int] | None = None):
    """Create a loader that returns LOADED with given records."""
    ids = record_ids or ["rec-1"]
    vers = versions or [1]

    def loader(request: LoadRequest) -> SourceLoadResult:
        return SourceLoadResult(
            source=ContextSource.TALENT_PROFILE,  # Will be overridden by assembler
            status=SourceStatus.LOADED,
            record_ids=ids,
            versions=vers,
            record_count=len(ids),
            data={"loaded": True},
        )
    return loader


def _absent_loader():
    """Create a loader that returns ABSENT."""
    def loader(request: LoadRequest) -> SourceLoadResult:
        return SourceLoadResult(
            source=ContextSource.TALENT_PROFILE,
            status=SourceStatus.ABSENT,
            error="No records found",
        )
    return loader


def _error_loader(msg: str = "Database timeout"):
    """Create a loader that raises an exception."""
    def loader(request: LoadRequest) -> SourceLoadResult:
        raise RuntimeError(msg)
    return loader


def _filtered_loader(loaded: int = 2, filtered: int = 3):
    """Create a loader that returns FILTERED with some excluded."""
    def loader(request: LoadRequest) -> SourceLoadResult:
        return SourceLoadResult(
            source=ContextSource.TALENT_PROFILE,
            status=SourceStatus.FILTERED if loaded == 0 else SourceStatus.LOADED,
            record_ids=[f"rec-{i}" for i in range(loaded)],
            record_count=loaded,
            filtered_count=filtered,
            filter_reasons=["approval_state=draft" for _ in range(filtered)],
        )
    return loader


# =============================================================================
# Complete Load
# =============================================================================


class TestCompleteLoad:

    @pytest.mark.unit
    def test_all_sources_loaded_successfully(self):
        """When all loaders succeed, all sources are LOADED."""
        loaders = {source: _success_loader() for source in ContextSource}
        assembler = ContextAssembler(loaders=loaders)
        ctx = assembler.assemble(_request())

        assert ctx.total_loaded == 10
        assert ctx.total_errors == 0
        assert ctx.has_required_failures is False
        for source, result in ctx.sources.items():
            assert result.status == SourceStatus.LOADED

    @pytest.mark.unit
    def test_all_sources_represented(self):
        """Every ContextSource is present in the assembled context."""
        assembler = ContextAssembler()
        ctx = assembler.assemble(_request())
        for source in ContextSource:
            assert source in ctx.sources

    @pytest.mark.unit
    def test_loaded_includes_versions(self):
        """Loaded sources include version numbers for pinning."""
        loaders = {
            ContextSource.TALENT_PROFILE: _success_loader(
                record_ids=["t-1"], versions=[5],
            ),
        }
        assembler = ContextAssembler(loaders=loaders)
        ctx = assembler.assemble(_request())
        result = ctx.sources[ContextSource.TALENT_PROFILE]
        assert result.versions == [5]
        assert result.record_ids == ["t-1"]

    @pytest.mark.unit
    def test_context_serializable(self):
        """AssembledContext.to_dict() is JSON-serializable."""
        import json
        assembler = ContextAssembler()
        ctx = assembler.assemble(_request())
        json.dumps(ctx.to_dict())


# =============================================================================
# Partial Load
# =============================================================================


class TestPartialLoad:

    @pytest.mark.unit
    def test_some_sources_loaded_some_absent(self):
        """Mixed results: some loaded, some absent."""
        loaders = {
            ContextSource.TALENT_PROFILE: _success_loader(),
            ContextSource.CREATIVE_PREFERENCES: _success_loader(),
            ContextSource.WARDROBE_ITEMS: _absent_loader(),
        }
        assembler = ContextAssembler(loaders=loaders)
        ctx = assembler.assemble(_request())

        assert ctx.sources[ContextSource.TALENT_PROFILE].status == SourceStatus.LOADED
        assert ctx.sources[ContextSource.CREATIVE_PREFERENCES].status == SourceStatus.LOADED
        assert ctx.sources[ContextSource.WARDROBE_ITEMS].status == SourceStatus.ABSENT
        assert ctx.total_loaded == 2

    @pytest.mark.unit
    def test_optional_absent_no_required_failure(self):
        """Absent optional sources don't trigger has_required_failures."""
        loaders = {
            ContextSource.TALENT_PROFILE: _success_loader(),  # Required
            ContextSource.WARDROBE_ITEMS: _absent_loader(),    # Optional
        }
        assembler = ContextAssembler(loaders=loaders)
        ctx = assembler.assemble(_request())
        assert ctx.has_required_failures is False

    @pytest.mark.unit
    def test_filtered_records_counted(self):
        """Filtered records are counted in summary."""
        loaders = {
            ContextSource.CONTINUITY_RULES: _filtered_loader(loaded=2, filtered=3),
        }
        assembler = ContextAssembler(loaders=loaders)
        ctx = assembler.assemble(_request())
        result = ctx.sources[ContextSource.CONTINUITY_RULES]
        assert result.filtered_count == 3
        assert result.record_count == 2


# =============================================================================
# Missing Sources (No Loader)
# =============================================================================


class TestMissingSources:

    @pytest.mark.unit
    def test_no_loaders_all_absent(self):
        """Assembler with no loaders reports all sources as ABSENT."""
        assembler = ContextAssembler()
        ctx = assembler.assemble(_request())
        assert ctx.total_absent == 10
        assert ctx.total_loaded == 0

    @pytest.mark.unit
    def test_absent_sources_have_error_message(self):
        """Absent sources explain why (no loader configured)."""
        assembler = ContextAssembler()
        ctx = assembler.assemble(_request())
        for result in ctx.sources.values():
            assert result.error is not None
            assert "loader" in result.error.lower()


# =============================================================================
# Failed Loads
# =============================================================================


class TestFailedLoads:

    @pytest.mark.unit
    def test_loader_exception_becomes_error_status(self):
        """Loader exception is caught and reported as ERROR."""
        loaders = {
            ContextSource.TALENT_PROFILE: _error_loader("Connection refused"),
        }
        assembler = ContextAssembler(loaders=loaders)
        ctx = assembler.assemble(_request())

        result = ctx.sources[ContextSource.TALENT_PROFILE]
        assert result.status == SourceStatus.ERROR
        assert "Connection refused" in result.error
        assert ctx.total_errors >= 1

    @pytest.mark.unit
    def test_required_source_error_sets_flag(self):
        """Error on REQUIRED source sets has_required_failures."""
        loaders = {
            ContextSource.TALENT_PROFILE: _error_loader("DB down"),
        }
        assembler = ContextAssembler(loaders=loaders)
        ctx = assembler.assemble(_request())
        assert ctx.has_required_failures is True

    @pytest.mark.unit
    def test_optional_source_error_no_required_flag(self):
        """Error on OPTIONAL source does NOT set has_required_failures."""
        loaders = {
            ContextSource.TALENT_PROFILE: _success_loader(),  # Required — OK
            ContextSource.RECENT_FEEDBACK: _error_loader("timeout"),  # Optional
        }
        assembler = ContextAssembler(loaders=loaders)
        ctx = assembler.assemble(_request())
        assert ctx.has_required_failures is False
        assert ctx.total_errors >= 1

    @pytest.mark.unit
    def test_error_does_not_stop_other_sources(self):
        """One source erroring does not prevent other sources from loading."""
        loaders = {
            ContextSource.TALENT_PROFILE: _error_loader("fail"),
            ContextSource.CREATIVE_PREFERENCES: _success_loader(),
            ContextSource.LORA_ASSIGNMENT: _success_loader(),
        }
        assembler = ContextAssembler(loaders=loaders)
        ctx = assembler.assemble(_request())
        assert ctx.sources[ContextSource.CREATIVE_PREFERENCES].status == SourceStatus.LOADED
        assert ctx.sources[ContextSource.LORA_ASSIGNMENT].status == SourceStatus.LOADED
        assert ctx.total_loaded == 2


# =============================================================================
# Authorization
# =============================================================================


class TestAuthorization:

    @pytest.mark.unit
    def test_missing_org_id_all_unauthorized(self):
        """Empty org_id makes all sources unauthorized."""
        assembler = ContextAssembler(loaders={
            ContextSource.TALENT_PROFILE: _success_loader(),
        })
        ctx = assembler.assemble(_request(org_id=""))
        assert ctx.has_required_failures is True
        for result in ctx.sources.values():
            assert result.status == SourceStatus.UNAUTHORIZED

    @pytest.mark.unit
    def test_missing_user_id_all_unauthorized(self):
        """Empty user_id makes all sources unauthorized."""
        assembler = ContextAssembler(loaders={
            ContextSource.TALENT_PROFILE: _success_loader(),
        })
        ctx = assembler.assemble(_request(user_id=""))
        assert ctx.has_required_failures is True
        for result in ctx.sources.values():
            assert result.status == SourceStatus.UNAUTHORIZED

    @pytest.mark.unit
    def test_cross_workspace_rejected(self):
        """Cross-workspace access is rejected."""
        assert verify_workspace_access("org-123", "org-123") is True
        assert verify_workspace_access("org-123", "org-evil") is False

    @pytest.mark.unit
    def test_unauthorized_context_has_error_reason(self):
        """Unauthorized context explains the reason."""
        assembler = ContextAssembler()
        ctx = assembler.assemble(_request(org_id=""))
        result = ctx.sources[ContextSource.TALENT_PROFILE]
        assert "org_id" in result.error


# =============================================================================
# Stale Exclusion and Filtering
# =============================================================================


class TestFiltering:

    @pytest.mark.unit
    def test_filter_by_approval_includes_approved(self):
        """Approved records pass filter."""
        records = [
            {"id": "1", "approval_state": "approved"},
            {"id": "2", "approval_state": "draft"},
            {"id": "3", "approval_state": "retired"},
        ]
        included, excluded, reasons = filter_by_approval(records, ["approved"])
        assert len(included) == 1
        assert included[0]["id"] == "1"
        assert len(excluded) == 2

    @pytest.mark.unit
    def test_filter_multiple_allowed_states(self):
        """Multiple allowed states pass."""
        records = [
            {"id": "1", "approval_state": "approved"},
            {"id": "2", "approval_state": "draft"},
        ]
        included, excluded, reasons = filter_by_approval(records, ["approved", "draft"])
        assert len(included) == 2

    @pytest.mark.unit
    def test_filter_produces_reasons(self):
        """Excluded records get filter reasons."""
        records = [{"id": "1", "approval_state": "retired"}]
        _, _, reasons = filter_by_approval(records, ["approved"])
        assert len(reasons) == 1
        assert "retired" in reasons[0]

    @pytest.mark.unit
    def test_loader_returning_filtered_status(self):
        """Loader can return FILTERED when all records excluded."""
        loaders = {
            ContextSource.WARDROBE_ITEMS: _filtered_loader(loaded=0, filtered=5),
        }
        assembler = ContextAssembler(loaders=loaders)
        ctx = assembler.assemble(_request())
        result = ctx.sources[ContextSource.WARDROBE_ITEMS]
        assert result.status == SourceStatus.FILTERED
        assert result.filtered_count == 5


# =============================================================================
# Source Requirements
# =============================================================================


class TestSourceRequirements:

    @pytest.mark.unit
    def test_talent_profile_is_required(self):
        """TalentProfile is classified as REQUIRED."""
        assert SOURCE_REQUIREMENTS[ContextSource.TALENT_PROFILE] == SourceRequirement.REQUIRED

    @pytest.mark.unit
    def test_creative_preferences_is_recommended(self):
        """CreativePreferences is RECOMMENDED."""
        assert SOURCE_REQUIREMENTS[ContextSource.CREATIVE_PREFERENCES] == SourceRequirement.RECOMMENDED

    @pytest.mark.unit
    def test_wardrobe_is_optional(self):
        """WardrobeItems is OPTIONAL."""
        assert SOURCE_REQUIREMENTS[ContextSource.WARDROBE_ITEMS] == SourceRequirement.OPTIONAL

    @pytest.mark.unit
    def test_all_sources_have_requirement(self):
        """Every ContextSource has a defined requirement level."""
        for source in ContextSource:
            assert source in SOURCE_REQUIREMENTS

    @pytest.mark.unit
    def test_results_include_requirement_level(self):
        """Each result carries its requirement classification."""
        assembler = ContextAssembler()
        ctx = assembler.assemble(_request())
        for source, result in ctx.sources.items():
            assert result.requirement == SOURCE_REQUIREMENTS[source]


# =============================================================================
# Request Identity Propagation
# =============================================================================


class TestRequestIdentity:

    @pytest.mark.unit
    def test_context_captures_request_identity(self):
        """Assembled context records org_id, user_id, talent_id."""
        assembler = ContextAssembler()
        ctx = assembler.assemble(_request(
            org_id="org-x", user_id="user-y", talent_id="talent-z",
        ))
        assert ctx.org_id == "org-x"
        assert ctx.user_id == "user-y"
        assert ctx.talent_id == "talent-z"

    @pytest.mark.unit
    def test_project_id_optional(self):
        """project_id can be None."""
        assembler = ContextAssembler()
        ctx = assembler.assemble(_request(project_id=None))
        assert ctx.project_id is None
