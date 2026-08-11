"""Unit tests for WorkspacePrivacyService.

Tests:
- get_restrictions: returns restrictions for workspace
- set_restrictions: replaces all restrictions, validates types
- remove_restriction: removes a single restriction
- check_provider_allowed: evaluates restrictions against providers
- check_provider_allowed_sync: synchronous hot-path evaluation
- Invalid restriction type raises error
- Privacy enforcement per context (llm, compute, storage)
- Scoped restrictions (project, talent)

No I/O, no DB — all tested in-memory.

Validates: Requirements R103.1, R103.2, R103.3
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.workspace_privacy_service import (
    InvalidRestrictionTypeError,
    PrivacyRestriction,
    ProviderCheckResult,
    WorkspacePrivacyService,
)


# =============================================================================
# Helpers
# =============================================================================

ORG_ID = uuid4()
OTHER_ORG_ID = uuid4()


def _make_restriction(
    restriction_type: str = "approved_llm_only",
    restriction_target: str | None = None,
    allowed_providers: list[str] | None = None,
    denied_providers: list[str] | None = None,
    org_id=ORG_ID,
) -> PrivacyRestriction:
    """Create a PrivacyRestriction for testing."""
    return PrivacyRestriction(
        id=uuid4(),
        org_id=org_id,
        restriction_type=restriction_type,
        restriction_target=restriction_target,
        allowed_providers=allowed_providers or [],
        denied_providers=denied_providers or [],
    )


# =============================================================================
# get_restrictions tests
# =============================================================================


class TestGetRestrictions:
    """Test get_restrictions retrieves workspace restrictions."""

    @pytest.mark.asyncio
    async def test_empty_when_no_restrictions(self) -> None:
        """Returns empty list when workspace has no restrictions."""
        service = WorkspacePrivacyService(restrictions=[])
        result = await service.get_restrictions(ORG_ID)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_only_matching_org(self) -> None:
        """Returns only restrictions for the requested org_id."""
        r1 = _make_restriction(org_id=ORG_ID)
        r2 = _make_restriction(org_id=OTHER_ORG_ID)
        service = WorkspacePrivacyService(restrictions=[r1, r2])

        result = await service.get_restrictions(ORG_ID)
        assert len(result) == 1
        assert result[0].org_id == ORG_ID

    @pytest.mark.asyncio
    async def test_returns_multiple_restrictions(self) -> None:
        """Returns all restrictions for the workspace."""
        r1 = _make_restriction(restriction_type="local_models_only")
        r2 = _make_restriction(restriction_type="approved_storage_only")
        service = WorkspacePrivacyService(restrictions=[r1, r2])

        result = await service.get_restrictions(ORG_ID)
        assert len(result) == 2


# =============================================================================
# set_restrictions tests
# =============================================================================


class TestSetRestrictions:
    """Test set_restrictions replaces workspace privacy config."""

    @pytest.mark.asyncio
    async def test_replaces_all_restrictions(self) -> None:
        """Replaces existing restrictions with new ones."""
        existing = _make_restriction(restriction_type="local_models_only")
        service = WorkspacePrivacyService(restrictions=[existing])

        new_restrictions = [
            {
                "restriction_type": "approved_llm_only",
                "allowed_providers": ["openai", "anthropic"],
                "denied_providers": [],
            }
        ]
        result = await service.set_restrictions(ORG_ID, new_restrictions)

        assert len(result) == 1
        assert result[0].restriction_type == "approved_llm_only"
        assert result[0].allowed_providers == ["openai", "anthropic"]

        # Old restriction should be gone
        all_restrictions = await service.get_restrictions(ORG_ID)
        assert len(all_restrictions) == 1
        assert all_restrictions[0].restriction_type == "approved_llm_only"

    @pytest.mark.asyncio
    async def test_empty_list_clears_all(self) -> None:
        """Empty list removes all restrictions."""
        existing = _make_restriction(restriction_type="local_models_only")
        service = WorkspacePrivacyService(restrictions=[existing])

        result = await service.set_restrictions(ORG_ID, [])
        assert result == []

        all_restrictions = await service.get_restrictions(ORG_ID)
        assert all_restrictions == []

    @pytest.mark.asyncio
    async def test_invalid_restriction_type_raises(self) -> None:
        """Invalid restriction type raises InvalidRestrictionTypeError."""
        service = WorkspacePrivacyService(restrictions=[])

        with pytest.raises(InvalidRestrictionTypeError) as exc_info:
            await service.set_restrictions(
                ORG_ID,
                [{"restriction_type": "invalid_type"}],
            )
        assert "invalid_type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_does_not_affect_other_orgs(self) -> None:
        """Setting restrictions for one org doesn't affect another."""
        r_other = _make_restriction(
            org_id=OTHER_ORG_ID,
            restriction_type="local_models_only",
        )
        service = WorkspacePrivacyService(restrictions=[r_other])

        await service.set_restrictions(
            ORG_ID,
            [{"restriction_type": "approved_llm_only", "allowed_providers": ["openai"]}],
        )

        # Other org still has its restriction
        other_restrictions = await service.get_restrictions(OTHER_ORG_ID)
        assert len(other_restrictions) == 1
        assert other_restrictions[0].restriction_type == "local_models_only"


# =============================================================================
# remove_restriction tests
# =============================================================================


class TestRemoveRestriction:
    """Test remove_restriction deletes a single restriction."""

    @pytest.mark.asyncio
    async def test_removes_existing_restriction(self) -> None:
        """Removes a restriction by ID and returns True."""
        restriction = _make_restriction()
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = await service.remove_restriction(ORG_ID, restriction.id)
        assert result is True

        remaining = await service.get_restrictions(ORG_ID)
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_returns_false_for_nonexistent(self) -> None:
        """Returns False when restriction ID not found."""
        service = WorkspacePrivacyService(restrictions=[])

        result = await service.remove_restriction(ORG_ID, uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_only_removes_matching_org(self) -> None:
        """Cannot remove a restriction belonging to another org."""
        restriction = _make_restriction(org_id=OTHER_ORG_ID)
        service = WorkspacePrivacyService(restrictions=[restriction])

        # Try to remove from ORG_ID — should fail (wrong org)
        result = await service.remove_restriction(ORG_ID, restriction.id)
        assert result is False

        # Still exists for other org
        remaining = await service.get_restrictions(OTHER_ORG_ID)
        assert len(remaining) == 1


# =============================================================================
# check_provider_allowed tests — LLM context
# =============================================================================


class TestCheckProviderAllowedLLM:
    """Test provider allowance checking for LLM context."""

    @pytest.mark.asyncio
    async def test_allowed_when_no_restrictions(self) -> None:
        """All providers allowed when no restrictions exist."""
        service = WorkspacePrivacyService(restrictions=[])

        result = await service.check_provider_allowed(ORG_ID, "openai", "llm")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_local_models_only_blocks_cloud(self) -> None:
        """local_models_only blocks non-local LLM providers."""
        restriction = _make_restriction(restriction_type="local_models_only")
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = await service.check_provider_allowed(ORG_ID, "openai", "llm")
        assert result.allowed is False
        assert "local models only" in result.reason
        assert result.restriction_type == "local_models_only"

    @pytest.mark.asyncio
    async def test_local_models_only_allows_ollama(self) -> None:
        """local_models_only allows local providers like Ollama."""
        restriction = _make_restriction(restriction_type="local_models_only")
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = await service.check_provider_allowed(ORG_ID, "ollama", "llm")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_local_models_only_allows_lm_studio(self) -> None:
        """local_models_only allows LM Studio."""
        restriction = _make_restriction(restriction_type="local_models_only")
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = await service.check_provider_allowed(ORG_ID, "lm_studio", "llm")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_approved_llm_only_blocks_unlisted(self) -> None:
        """approved_llm_only blocks providers not in allowed list."""
        restriction = _make_restriction(
            restriction_type="approved_llm_only",
            allowed_providers=["openai", "anthropic"],
        )
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = await service.check_provider_allowed(ORG_ID, "deepseek", "llm")
        assert result.allowed is False
        assert "not in the approved LLM provider list" in result.reason

    @pytest.mark.asyncio
    async def test_approved_llm_only_allows_listed(self) -> None:
        """approved_llm_only allows providers in the whitelist."""
        restriction = _make_restriction(
            restriction_type="approved_llm_only",
            allowed_providers=["openai", "anthropic"],
        )
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = await service.check_provider_allowed(ORG_ID, "openai", "llm")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_denied_providers_blocks_provider(self) -> None:
        """Any restriction with denied_providers blocks those providers."""
        restriction = _make_restriction(
            restriction_type="approved_llm_only",
            allowed_providers=["openai", "deepseek"],
            denied_providers=["deepseek"],
        )
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = await service.check_provider_allowed(ORG_ID, "deepseek", "llm")
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_case_insensitive_comparison(self) -> None:
        """Provider names are compared case-insensitively."""
        restriction = _make_restriction(
            restriction_type="approved_llm_only",
            allowed_providers=["OpenAI"],
        )
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = await service.check_provider_allowed(ORG_ID, "openai", "llm")
        assert result.allowed is True


# =============================================================================
# check_provider_allowed tests — Compute context
# =============================================================================


class TestCheckProviderAllowedCompute:
    """Test provider allowance checking for compute context."""

    @pytest.mark.asyncio
    async def test_customer_compute_only_blocks_platform(self) -> None:
        """customer_compute_only blocks platform-managed providers."""
        restriction = _make_restriction(restriction_type="customer_compute_only")
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = await service.check_provider_allowed(ORG_ID, "runpod", "compute")
        assert result.allowed is False
        assert "customer-managed compute only" in result.reason

    @pytest.mark.asyncio
    async def test_customer_compute_only_allows_custom(self) -> None:
        """customer_compute_only allows customer-managed providers."""
        restriction = _make_restriction(restriction_type="customer_compute_only")
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = await service.check_provider_allowed(
            ORG_ID, "my_custom_gpu", "compute"
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_compute_restriction_does_not_affect_llm(self) -> None:
        """customer_compute_only does not affect LLM provider selection."""
        restriction = _make_restriction(restriction_type="customer_compute_only")
        service = WorkspacePrivacyService(restrictions=[restriction])

        # Should not block LLM calls even though it blocks compute
        result = await service.check_provider_allowed(ORG_ID, "openai", "llm")
        assert result.allowed is True


# =============================================================================
# check_provider_allowed tests — Storage context
# =============================================================================


class TestCheckProviderAllowedStorage:
    """Test provider allowance checking for storage context."""

    @pytest.mark.asyncio
    async def test_approved_storage_only_blocks_unlisted(self) -> None:
        """approved_storage_only blocks storage providers not in whitelist."""
        restriction = _make_restriction(
            restriction_type="approved_storage_only",
            allowed_providers=["b2", "s3"],
        )
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = await service.check_provider_allowed(ORG_ID, "r2", "storage")
        assert result.allowed is False
        assert "not in the approved storage provider list" in result.reason

    @pytest.mark.asyncio
    async def test_approved_storage_only_allows_listed(self) -> None:
        """approved_storage_only allows providers in the whitelist."""
        restriction = _make_restriction(
            restriction_type="approved_storage_only",
            allowed_providers=["b2", "s3"],
        )
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = await service.check_provider_allowed(ORG_ID, "b2", "storage")
        assert result.allowed is True


# =============================================================================
# check_provider_allowed_sync tests — Scoped restrictions
# =============================================================================


class TestCheckProviderAllowedScoped:
    """Test scoped restrictions (project, talent targeting)."""

    def test_project_scoped_llm_restriction(self) -> None:
        """no_external_llm_for_project blocks external LLMs for specific project."""
        project_id = "project-abc123"
        restriction = _make_restriction(
            restriction_type="no_external_llm_for_project",
            restriction_target=project_id,
        )
        service = WorkspacePrivacyService(restrictions=[restriction])

        # When target matches: external blocked
        result = service.check_provider_allowed_sync(
            [restriction], "openai", "llm", target=project_id
        )
        assert result.allowed is False
        assert f"Project '{project_id}'" in result.reason

        # When target doesn't match: allowed
        result = service.check_provider_allowed_sync(
            [restriction], "openai", "llm", target="other-project"
        )
        assert result.allowed is True

    def test_project_scoped_allows_local(self) -> None:
        """no_external_llm_for_project allows local providers for the project."""
        project_id = "project-abc123"
        restriction = _make_restriction(
            restriction_type="no_external_llm_for_project",
            restriction_target=project_id,
        )
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = service.check_provider_allowed_sync(
            [restriction], "ollama", "llm", target=project_id
        )
        assert result.allowed is True

    def test_talent_provider_restriction_denies(self) -> None:
        """talent_provider_restriction blocks denied providers for talent."""
        talent_id = "talent-xyz"
        restriction = _make_restriction(
            restriction_type="talent_provider_restriction",
            restriction_target=talent_id,
            denied_providers=["provider_a"],
        )
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = service.check_provider_allowed_sync(
            [restriction], "provider_a", "llm", target=talent_id
        )
        assert result.allowed is False
        assert f"talent '{talent_id}'" in result.reason

    def test_talent_provider_restriction_allows(self) -> None:
        """talent_provider_restriction allows non-denied providers."""
        talent_id = "talent-xyz"
        restriction = _make_restriction(
            restriction_type="talent_provider_restriction",
            restriction_target=talent_id,
            denied_providers=["provider_a"],
            allowed_providers=["provider_b"],
        )
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = service.check_provider_allowed_sync(
            [restriction], "provider_b", "llm", target=talent_id
        )
        assert result.allowed is True

    def test_project_privacy_denies_provider(self) -> None:
        """project_privacy blocks denied providers for a project."""
        project_id = "project-secret"
        restriction = _make_restriction(
            restriction_type="project_privacy",
            restriction_target=project_id,
            denied_providers=["external_cloud"],
        )
        service = WorkspacePrivacyService(restrictions=[restriction])

        result = service.check_provider_allowed_sync(
            [restriction], "external_cloud", "llm", target=project_id
        )
        assert result.allowed is False

    def test_scoped_restriction_ignored_without_target(self) -> None:
        """Scoped restriction is not evaluated when no target is provided."""
        restriction = _make_restriction(
            restriction_type="no_external_llm_for_project",
            restriction_target="project-abc",
        )
        service = WorkspacePrivacyService(restrictions=[restriction])

        # No target → scoped restriction does not apply
        result = service.check_provider_allowed_sync(
            [restriction], "openai", "llm", target=None
        )
        assert result.allowed is True


# =============================================================================
# Multiple restrictions combined
# =============================================================================


class TestMultipleRestrictions:
    """Test behavior with multiple restrictions applied simultaneously."""

    @pytest.mark.asyncio
    async def test_multiple_restrictions_all_must_pass(self) -> None:
        """Provider must satisfy ALL active restrictions."""
        restrictions = [
            _make_restriction(
                restriction_type="approved_llm_only",
                allowed_providers=["openai", "anthropic", "ollama"],
            ),
            _make_restriction(
                restriction_type="local_models_only",
            ),
        ]
        service = WorkspacePrivacyService(restrictions=restrictions)

        # OpenAI is in approved list but NOT local → blocked by local_models_only
        result = await service.check_provider_allowed(ORG_ID, "openai", "llm")
        assert result.allowed is False
        assert result.restriction_type == "local_models_only"

    @pytest.mark.asyncio
    async def test_different_contexts_independent(self) -> None:
        """Restrictions for different contexts are independent."""
        restrictions = [
            _make_restriction(restriction_type="local_models_only"),
            _make_restriction(
                restriction_type="approved_storage_only",
                allowed_providers=["b2"],
            ),
        ]
        service = WorkspacePrivacyService(restrictions=restrictions)

        # LLM context: cloud blocked
        result = await service.check_provider_allowed(ORG_ID, "openai", "llm")
        assert result.allowed is False

        # Storage context: b2 allowed
        result = await service.check_provider_allowed(ORG_ID, "b2", "storage")
        assert result.allowed is True

        # Storage context: r2 blocked
        result = await service.check_provider_allowed(ORG_ID, "r2", "storage")
        assert result.allowed is False
