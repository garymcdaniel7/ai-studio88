"""Unit tests for Application Context envelope (Task 19.1).

Tests that:
  - Server-derived fields (org_id, user_id, role, trust_domain) CANNOT be
    overridden by client-supplied data
  - Invalid IDs (wrong org) are rejected/dropped with 422-equivalent behavior
  - Full context builds correctly from valid inputs
  - Capabilities are resolved correctly from plan + role
  - UI state is sanitized (auth/secret keys stripped)
  - BrainMode enum works correctly
  - ApplicationContextRequest rejects extra fields

Validates: Requirements R58.1, R58.2, R58.3, R58.4
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from backend.app.core.dependencies import TenantContext, TrustDomain, WorkspaceRole
from backend.app.schemas.application_context import (
    ApplicationContext,
    ApplicationContextRequest,
    BrainMode,
    OrgOwnershipValidator,
    UserContextInfo,
    WorkspaceContextInfo,
    build_application_context,
    resolve_capabilities,
)


# =============================================================================
# Fixtures
# =============================================================================


ORG_ID = uuid4()
USER_ID = uuid4()
OTHER_ORG_PROJECT_ID = uuid4()
VALID_PROJECT_ID = uuid4()
VALID_TALENT_ID = uuid4()
VALID_ASSET_1 = uuid4()
VALID_ASSET_2 = uuid4()
INVALID_ASSET = uuid4()
VALID_JOB_ID = uuid4()


@pytest.fixture
def tenant_context() -> TenantContext:
    """A standard authenticated tenant context for testing."""
    return TenantContext(
        user_id=USER_ID,
        org_id=ORG_ID,
        role=WorkspaceRole.EDITOR,
        trust_domain=TrustDomain.CUSTOMER_USER,
        email="test@example.com",
    )


@pytest.fixture
def admin_tenant_context() -> TenantContext:
    """Admin-level tenant context for testing."""
    return TenantContext(
        user_id=USER_ID,
        org_id=ORG_ID,
        role=WorkspaceRole.ADMIN,
        trust_domain=TrustDomain.WORKSPACE_ADMIN,
        email="admin@example.com",
    )


@pytest.fixture
def owner_tenant_context() -> TenantContext:
    """Owner-level tenant context for testing."""
    return TenantContext(
        user_id=USER_ID,
        org_id=ORG_ID,
        role=WorkspaceRole.OWNER,
        trust_domain=TrustDomain.WORKSPACE_ADMIN,
        email="owner@example.com",
    )


class MockValidator(OrgOwnershipValidator):
    """Mock validator that simulates org-scoped ownership checks.

    Only IDs in the valid_* sets are considered owned by the org.
    """

    def __init__(
        self,
        valid_projects: set[UUID] | None = None,
        valid_talents: set[UUID] | None = None,
        valid_assets: set[UUID] | None = None,
        valid_jobs: set[UUID] | None = None,
    ) -> None:
        self.valid_projects = valid_projects or set()
        self.valid_talents = valid_talents or set()
        self.valid_assets = valid_assets or set()
        self.valid_jobs = valid_jobs or set()

    async def validate_project(self, project_id: UUID, org_id: UUID) -> bool:
        return project_id in self.valid_projects

    async def validate_talent(self, talent_id: UUID, org_id: UUID) -> bool:
        return talent_id in self.valid_talents

    async def validate_assets(
        self, asset_ids: list[UUID], org_id: UUID
    ) -> list[UUID]:
        return [aid for aid in asset_ids if aid in self.valid_assets]

    async def validate_job(self, job_id: UUID, org_id: UUID) -> bool:
        return job_id in self.valid_jobs


@pytest.fixture
def mock_validator() -> MockValidator:
    """Validator that recognizes our test IDs as valid."""
    return MockValidator(
        valid_projects={VALID_PROJECT_ID},
        valid_talents={VALID_TALENT_ID},
        valid_assets={VALID_ASSET_1, VALID_ASSET_2},
        valid_jobs={VALID_JOB_ID},
    )


@pytest.fixture
def empty_validator() -> MockValidator:
    """Validator that rejects all IDs (simulates cross-tenant access)."""
    return MockValidator()


# =============================================================================
# ApplicationContextRequest Tests
# =============================================================================


class TestApplicationContextRequest:
    """Verify client request schema validation."""

    @pytest.mark.unit
    def test_minimal_request_defaults(self):
        """Empty request should use all defaults."""
        req = ApplicationContextRequest()

        assert req.current_page is None
        assert req.active_project_id is None
        assert req.selected_talent_id is None
        assert req.selected_asset_ids == []
        assert req.active_job_id is None
        assert req.active_brain_mode == BrainMode.CREATIVE
        assert req.workflow_state is None
        assert req.ui_state is None
        assert req.context_version == "1"

    @pytest.mark.unit
    def test_full_request_parses(self):
        """All fields should parse correctly."""
        req = ApplicationContextRequest(
            current_page="/talent",
            active_project_id=VALID_PROJECT_ID,
            selected_talent_id=VALID_TALENT_ID,
            selected_asset_ids=[VALID_ASSET_1, VALID_ASSET_2],
            active_job_id=VALID_JOB_ID,
            active_brain_mode=BrainMode.PROMPT_ENGINEER,
            workflow_state={"step": 2},
            ui_state={"panel": "open"},
            context_version="1",
        )

        assert req.current_page == "/talent"
        assert req.active_project_id == VALID_PROJECT_ID
        assert req.selected_talent_id == VALID_TALENT_ID
        assert req.selected_asset_ids == [VALID_ASSET_1, VALID_ASSET_2]
        assert req.active_job_id == VALID_JOB_ID
        assert req.active_brain_mode == BrainMode.PROMPT_ENGINEER

    @pytest.mark.unit
    def test_rejects_extra_fields(self):
        """Extra fields (like org_id, user_id) should be rejected with 422."""
        with pytest.raises(Exception):  # ValidationError
            ApplicationContextRequest(
                org_id=uuid4(),  # type: ignore[call-arg]
                current_page="/home",
            )

    @pytest.mark.unit
    def test_rejects_user_id_field(self):
        """Client cannot sneak user_id into the request."""
        with pytest.raises(Exception):
            ApplicationContextRequest(
                user_id=uuid4(),  # type: ignore[call-arg]
            )

    @pytest.mark.unit
    def test_rejects_role_field(self):
        """Client cannot set role via request."""
        with pytest.raises(Exception):
            ApplicationContextRequest(
                role="owner",  # type: ignore[call-arg]
            )

    @pytest.mark.unit
    def test_ui_state_sanitizes_auth_keys(self):
        """UI state should strip any auth/secret-related keys."""
        req = ApplicationContextRequest(
            ui_state={
                "panel": "open",
                "token": "abc123",
                "jwt": "eyJ...",
                "password": "secret",
                "api_key": "sk-xxx",
                "theme": "dark",
            }
        )

        assert req.ui_state is not None
        assert "panel" in req.ui_state
        assert "theme" in req.ui_state
        # Auth keys stripped
        assert "token" not in req.ui_state
        assert "jwt" not in req.ui_state
        assert "password" not in req.ui_state
        assert "api_key" not in req.ui_state

    @pytest.mark.unit
    def test_invalid_brain_mode_rejected(self):
        """Invalid brain mode string should be rejected."""
        with pytest.raises(Exception):
            ApplicationContextRequest(
                active_brain_mode="invalid_mode",  # type: ignore[arg-type]
            )


# =============================================================================
# Server-Derived Fields Tests (R58.3)
# =============================================================================


class TestServerDerivedFields:
    """Verify that server fields CANNOT be overridden by client data."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_org_id_always_from_tenant_context(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """org_id in context MUST come from TenantContext, not client.

        R58.3: Authorization fields are ALWAYS server-derived from JWT.
        """
        req = ApplicationContextRequest(current_page="/home")

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Test Org",
            workspace_plan="pro",
            validator=mock_validator,
        )

        # org_id is from tenant_context, not from any client field
        assert ctx.workspace.org_id == ORG_ID
        assert ctx.workspace.org_id == tenant_context.org_id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_user_id_always_from_tenant_context(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """user_id in context MUST come from TenantContext, not client.

        R58.3: user_id SHALL NEVER be trusted from browser-supplied context.
        """
        req = ApplicationContextRequest(current_page="/brain")

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Test Org",
            workspace_plan="pro",
            validator=mock_validator,
        )

        assert ctx.user.user_id == USER_ID
        assert ctx.user.user_id == tenant_context.user_id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_role_always_from_tenant_context(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """role in context MUST come from TenantContext.

        Even if client could somehow inject role, it's overwritten.
        """
        req = ApplicationContextRequest()

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="free",
            validator=mock_validator,
        )

        assert ctx.user.role == WorkspaceRole.EDITOR
        assert ctx.user.role == tenant_context.role

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_trust_domain_always_from_tenant_context(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """trust_domain in context MUST come from TenantContext."""
        req = ApplicationContextRequest()

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="free",
            validator=mock_validator,
        )

        assert ctx.user.trust_domain == TrustDomain.CUSTOMER_USER
        assert ctx.user.trust_domain == tenant_context.trust_domain


# =============================================================================
# ID Validation Tests (R58.4)
# =============================================================================


class TestIDValidation:
    """Verify that all referenced IDs are validated against authenticated org_id.

    R58.4: Invalid or cross-tenant references SHALL be silently dropped
    with a warning log.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_valid_project_id_accepted(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """Valid project ID should be included in context."""
        req = ApplicationContextRequest(active_project_id=VALID_PROJECT_ID)

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="pro",
            validator=mock_validator,
        )

        assert ctx.active_project_id == VALID_PROJECT_ID
        assert len(ctx.dropped_references) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_project_id_dropped(
        self, tenant_context: TenantContext, empty_validator: MockValidator
    ):
        """Project ID not belonging to org should be silently dropped."""
        req = ApplicationContextRequest(active_project_id=OTHER_ORG_PROJECT_ID)

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="pro",
            validator=empty_validator,
        )

        assert ctx.active_project_id is None
        assert len(ctx.dropped_references) == 1
        assert f"project:{OTHER_ORG_PROJECT_ID}" in ctx.dropped_references

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_valid_talent_id_accepted(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """Valid talent ID should be included in context."""
        req = ApplicationContextRequest(selected_talent_id=VALID_TALENT_ID)

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="pro",
            validator=mock_validator,
        )

        assert ctx.selected_talent_id == VALID_TALENT_ID

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_talent_id_dropped(
        self, tenant_context: TenantContext, empty_validator: MockValidator
    ):
        """Talent ID not belonging to org should be dropped."""
        fake_talent = uuid4()
        req = ApplicationContextRequest(selected_talent_id=fake_talent)

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="pro",
            validator=empty_validator,
        )

        assert ctx.selected_talent_id is None
        assert f"talent:{fake_talent}" in ctx.dropped_references

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_valid_assets_accepted(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """Valid asset IDs should be included."""
        req = ApplicationContextRequest(
            selected_asset_ids=[VALID_ASSET_1, VALID_ASSET_2]
        )

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="pro",
            validator=mock_validator,
        )

        assert set(ctx.selected_asset_ids) == {VALID_ASSET_1, VALID_ASSET_2}
        assert len(ctx.dropped_references) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_assets_dropped_valid_kept(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """Mix of valid and invalid asset IDs: invalid are dropped, valid kept."""
        req = ApplicationContextRequest(
            selected_asset_ids=[VALID_ASSET_1, INVALID_ASSET, VALID_ASSET_2]
        )

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="pro",
            validator=mock_validator,
        )

        assert set(ctx.selected_asset_ids) == {VALID_ASSET_1, VALID_ASSET_2}
        assert f"asset:{INVALID_ASSET}" in ctx.dropped_references

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_all_assets_invalid(
        self, tenant_context: TenantContext, empty_validator: MockValidator
    ):
        """All invalid assets should result in empty list."""
        req = ApplicationContextRequest(
            selected_asset_ids=[uuid4(), uuid4()]
        )

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="pro",
            validator=empty_validator,
        )

        assert ctx.selected_asset_ids == []
        assert len(ctx.dropped_references) == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_valid_job_id_accepted(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """Valid job ID should be included in context."""
        req = ApplicationContextRequest(active_job_id=VALID_JOB_ID)

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="pro",
            validator=mock_validator,
        )

        assert ctx.active_job_id == VALID_JOB_ID

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_job_id_dropped(
        self, tenant_context: TenantContext, empty_validator: MockValidator
    ):
        """Job ID not belonging to org should be dropped."""
        fake_job = uuid4()
        req = ApplicationContextRequest(active_job_id=fake_job)

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="pro",
            validator=empty_validator,
        )

        assert ctx.active_job_id is None
        assert f"job:{fake_job}" in ctx.dropped_references


# =============================================================================
# Full Context Build Tests (R58.1)
# =============================================================================


class TestBuildApplicationContext:
    """Verify the full context builds correctly from valid inputs."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_full_valid_context(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """All valid inputs should produce a complete context.

        R58.1: Contains workspace, page, project, talent, assets, job,
        mode, capabilities, workflow state, and UI state.
        """
        req = ApplicationContextRequest(
            current_page="/create",
            active_project_id=VALID_PROJECT_ID,
            selected_talent_id=VALID_TALENT_ID,
            selected_asset_ids=[VALID_ASSET_1, VALID_ASSET_2],
            active_job_id=VALID_JOB_ID,
            active_brain_mode=BrainMode.PRODUCTION_ADVISOR,
            workflow_state={"step": 3, "total": 5},
            ui_state={"sidebar": "collapsed"},
        )

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Creative Studio",
            workspace_plan="pro",
            validator=mock_validator,
        )

        # Server-derived
        assert ctx.workspace.org_id == ORG_ID
        assert ctx.workspace.name == "Creative Studio"
        assert ctx.workspace.plan == "pro"
        assert ctx.user.user_id == USER_ID
        assert ctx.user.role == WorkspaceRole.EDITOR
        assert ctx.user.trust_domain == TrustDomain.CUSTOMER_USER

        # Client-supplied, validated
        assert ctx.current_page == "/create"
        assert ctx.active_project_id == VALID_PROJECT_ID
        assert ctx.selected_talent_id == VALID_TALENT_ID
        assert set(ctx.selected_asset_ids) == {VALID_ASSET_1, VALID_ASSET_2}
        assert ctx.active_job_id == VALID_JOB_ID
        assert ctx.active_brain_mode == BrainMode.PRODUCTION_ADVISOR

        # State
        assert ctx.workflow_state == {"step": 3, "total": 5}
        assert ctx.ui_state == {"sidebar": "collapsed"}

        # Capabilities resolved
        assert len(ctx.capabilities) > 0
        assert "generation.basic" in ctx.capabilities

        # No dropped references
        assert ctx.dropped_references == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_minimal_context(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """Minimal request (all defaults) should still produce valid context."""
        req = ApplicationContextRequest()

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="free",
            validator=mock_validator,
        )

        assert ctx.workspace.org_id == ORG_ID
        assert ctx.user.user_id == USER_ID
        assert ctx.current_page is None
        assert ctx.active_project_id is None
        assert ctx.selected_talent_id is None
        assert ctx.selected_asset_ids == []
        assert ctx.active_job_id is None
        assert ctx.active_brain_mode == BrainMode.CREATIVE
        assert ctx.workflow_state is None
        assert ctx.ui_state is None
        assert ctx.dropped_references == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_context_version_preserved(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """context_version from request should be preserved."""
        req = ApplicationContextRequest(context_version="2")

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="pro",
            validator=mock_validator,
        )

        assert ctx.context_version == "2"


# =============================================================================
# Capability Resolution Tests
# =============================================================================


class TestCapabilityResolution:
    """Verify capabilities are resolved correctly from plan + role."""

    @pytest.mark.unit
    def test_free_plan_basic_capabilities(self):
        """Free plan should have limited capabilities."""
        caps = resolve_capabilities("free", WorkspaceRole.VIEWER)

        assert "generation.basic" in caps
        assert "brain.chat" in caps
        assert "generation.advanced" not in caps
        assert "video.basic" not in caps

    @pytest.mark.unit
    def test_pro_plan_expanded_capabilities(self):
        """Pro plan should include advanced features."""
        caps = resolve_capabilities("pro", WorkspaceRole.EDITOR)

        assert "generation.basic" in caps
        assert "generation.advanced" in caps
        assert "brain.modes" in caps
        assert "brain.memory" in caps
        assert "video.basic" in caps
        assert "workspace.create_content" in caps  # from editor role

    @pytest.mark.unit
    def test_enterprise_plan_full_capabilities(self):
        """Enterprise plan should include everything."""
        caps = resolve_capabilities("enterprise", WorkspaceRole.OWNER)

        assert "generation.advanced" in caps
        assert "brain.autonomous" in caps
        assert "video.advanced" in caps
        assert "audio.voice" in caps
        assert "workspace.billing" in caps  # from owner role
        assert "workspace.delete" in caps

    @pytest.mark.unit
    def test_owner_role_adds_workspace_caps(self):
        """Owner role should add workspace management capabilities."""
        caps = resolve_capabilities("free", WorkspaceRole.OWNER)

        assert "workspace.settings" in caps
        assert "workspace.billing" in caps
        assert "workspace.members" in caps
        assert "workspace.connections" in caps
        assert "workspace.delete" in caps

    @pytest.mark.unit
    def test_admin_role_adds_subset_caps(self):
        """Admin role should add settings/members/connections but not billing/delete."""
        caps = resolve_capabilities("free", WorkspaceRole.ADMIN)

        assert "workspace.settings" in caps
        assert "workspace.members" in caps
        assert "workspace.connections" in caps
        assert "workspace.billing" not in caps
        assert "workspace.delete" not in caps

    @pytest.mark.unit
    def test_unknown_plan_falls_back_to_free(self):
        """Unknown plan name should resolve to free tier capabilities."""
        caps = resolve_capabilities("unknown_plan", WorkspaceRole.VIEWER)
        free_caps = resolve_capabilities("free", WorkspaceRole.VIEWER)

        assert caps == free_caps

    @pytest.mark.unit
    def test_capabilities_are_sorted_and_deduplicated(self):
        """Capabilities list should be sorted with no duplicates."""
        caps = resolve_capabilities("enterprise", WorkspaceRole.OWNER)

        assert caps == sorted(caps)
        assert len(caps) == len(set(caps))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_capabilities_populated_in_context(
        self, tenant_context: TenantContext, mock_validator: MockValidator
    ):
        """Capabilities should be populated in the built context."""
        req = ApplicationContextRequest()

        ctx = await build_application_context(
            req,
            tenant_context,
            workspace_name="Org",
            workspace_plan="enterprise",
            validator=mock_validator,
        )

        # Enterprise + editor role
        assert "generation.advanced" in ctx.capabilities
        assert "workspace.create_content" in ctx.capabilities


# =============================================================================
# BrainMode Enum Tests
# =============================================================================


class TestBrainMode:
    """Verify BrainMode enum values."""

    @pytest.mark.unit
    def test_all_modes_defined(self):
        """All expected Brain modes should be defined."""
        expected = {
            "creative",
            "prompt_engineer",
            "story_assistant",
            "production_advisor",
            "research",
            "image_analyzer",
            "business_strategy",
        }
        actual = {mode.value for mode in BrainMode}
        assert actual == expected

    @pytest.mark.unit
    def test_mode_string_values(self):
        """Mode values should be lowercase snake_case strings."""
        for mode in BrainMode:
            assert mode.value == mode.value.lower()
            assert " " not in mode.value
