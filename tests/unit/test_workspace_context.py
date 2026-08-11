"""Unit tests for Workspace Relationship Context Model (Task 15.2).

Tests that:
  - Context builds with correct trust domain filtering
  - Boundary crossings are logged when higher-privilege content is excluded
  - Customer user context excludes founder/platform content
  - WorkspaceContextSummary serializes correctly
  - build_workspace_context integrates with resolve_trust_domain and filter_by_trust_domain

Run with:
    pytest tests/unit/test_workspace_context.py -v

Validates: Requirements R57.6, R57.7, R57.8
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from backend.app.core.trust_domains import (
    TrustDomain,
    clear_domain_audit,
    get_domain_audit,
)
from backend.app.core.workspace_context import (
    ConnectionSummary,
    KnowledgeItem,
    PreferenceItem,
    ProjectSummary,
    TalentSummary,
    UserContext,
    WorkspaceContextSummary,
    WorkspaceInfo,
    WorkspaceRelationshipContext,
    build_workspace_context,
    summarize_context,
)


FOUNDER_USER_ID = str(uuid4())
ADMIN_USER_ID = str(uuid4())
EDITOR_USER_ID = str(uuid4())
VIEWER_USER_ID = str(uuid4())
ORG_ID = str(uuid4())


@pytest.fixture(autouse=True)
def _clean_audit():
    """Clear audit trail before and after each test."""
    clear_domain_audit()
    yield
    clear_domain_audit()


@pytest.fixture
def _founder_env():
    """Patch FOUNDER_USER_IDS to include our test founder."""
    with patch(
        "backend.app.core.trust_domains.FOUNDER_USER_IDS",
        frozenset({FOUNDER_USER_ID}),
    ):
        yield


@pytest.fixture
def mixed_knowledge() -> list[KnowledgeItem]:
    """Knowledge items spanning multiple trust domains."""
    return [
        KnowledgeItem(
            id="k1",
            content="Customer creative prompt style",
            source="workspace",
            trust_domain=TrustDomain.CUSTOMER_USER,
            category="creative",
        ),
        KnowledgeItem(
            id="k2",
            content="Workspace admin billing info",
            source="workspace",
            trust_domain=TrustDomain.WORKSPACE_ADMIN,
            category="admin",
        ),
        KnowledgeItem(
            id="k3",
            content="Platform ops config secrets",
            source="platform",
            trust_domain=TrustDomain.PLATFORM_ADMIN,
            category="infrastructure",
        ),
        KnowledgeItem(
            id="k4",
            content="Founder strategy document",
            source="founder",
            trust_domain=TrustDomain.FOUNDER_PRIVATE,
            category="strategy",
        ),
        KnowledgeItem(
            id="k5",
            content="Another customer item",
            source="workspace",
            trust_domain=TrustDomain.CUSTOMER_USER,
            category="creative",
        ),
    ]


# =============================================================================
# Trust Domain Filtering Tests
# =============================================================================


class TestTrustDomainFiltering:
    """Verify knowledge is filtered through the requesting user's trust domain."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_customer_user_sees_only_customer_content(
        self, mixed_knowledge: list[KnowledgeItem]
    ):
        """CUSTOMER_USER should only see items at their level or below.

        Validates R57.5: Filter retrieved knowledge through requesting user's
        trust domain.
        """
        ctx = await build_workspace_context(
            user_id=EDITOR_USER_ID,
            user_name="Editor User",
            org_id=ORG_ID,
            org_name="Test Org",
            org_plan="pro",
            role="editor",
            knowledge=mixed_knowledge,
        )

        # Customer user (editor) should only see CUSTOMER_USER items
        assert len(ctx.knowledge) == 2
        knowledge_ids = {item.id for item in ctx.knowledge}
        assert knowledge_ids == {"k1", "k5"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_workspace_admin_sees_admin_and_below(
        self, mixed_knowledge: list[KnowledgeItem]
    ):
        """WORKSPACE_ADMIN should see workspace, customer, service, system items."""
        ctx = await build_workspace_context(
            user_id=ADMIN_USER_ID,
            user_name="Admin User",
            org_id=ORG_ID,
            org_name="Test Org",
            org_plan="pro",
            role="admin",
            knowledge=mixed_knowledge,
        )

        # Workspace admin sees CUSTOMER_USER + WORKSPACE_ADMIN items
        assert len(ctx.knowledge) == 3
        knowledge_ids = {item.id for item in ctx.knowledge}
        assert knowledge_ids == {"k1", "k2", "k5"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_founder_sees_all_content(
        self, _founder_env, mixed_knowledge: list[KnowledgeItem]
    ):
        """FOUNDER_PRIVATE should see all items across all trust domains."""
        ctx = await build_workspace_context(
            user_id=FOUNDER_USER_ID,
            user_name="Founder",
            org_id=ORG_ID,
            org_name="Test Org",
            org_plan="enterprise",
            role="owner",
            knowledge=mixed_knowledge,
        )

        # Founder sees everything
        assert len(ctx.knowledge) == 5
        knowledge_ids = {item.id for item in ctx.knowledge}
        assert knowledge_ids == {"k1", "k2", "k3", "k4", "k5"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_platform_admin_excludes_founder_content(
        self, mixed_knowledge: list[KnowledgeItem]
    ):
        """PLATFORM_ADMIN should see everything except FOUNDER_PRIVATE."""
        ctx = await build_workspace_context(
            user_id=ADMIN_USER_ID,
            user_name="Platform Admin",
            org_id=ORG_ID,
            org_name="Test Org",
            org_plan="enterprise",
            role="admin",
            is_platform_operator=True,
            platform_capabilities=frozenset({"manage_platform_config"}),
            knowledge=mixed_knowledge,
        )

        # Platform admin sees everything except FOUNDER_PRIVATE
        assert len(ctx.knowledge) == 4
        knowledge_ids = {item.id for item in ctx.knowledge}
        assert knowledge_ids == {"k1", "k2", "k3", "k5"}
        # Founder content k4 excluded
        assert "k4" not in knowledge_ids


# =============================================================================
# Boundary Crossing Audit Tests
# =============================================================================


class TestBoundaryCrossingAudit:
    """Verify that boundary crossings are logged per R57.6 and R57.7."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_boundary_crossings_logged_for_excluded_items(
        self, mixed_knowledge: list[KnowledgeItem]
    ):
        """When items are filtered out, boundary crossings must be logged.

        Validates R57.6: Log trust domain boundary crossings with full audit trail.
        """
        ctx = await build_workspace_context(
            user_id=EDITOR_USER_ID,
            user_name="Editor",
            org_id=ORG_ID,
            org_name="Test Org",
            org_plan="pro",
            role="editor",
            knowledge=mixed_knowledge,
        )

        # 3 items excluded (k2=WORKSPACE_ADMIN, k3=PLATFORM_ADMIN, k4=FOUNDER_PRIVATE)
        assert ctx.boundary_crossings_logged == 3

        # Verify audit trail contains entries
        audit = get_domain_audit(org_id=ORG_ID)
        assert len(audit) == 3

        # All should be "denied" outcome
        for entry in audit:
            assert entry["outcome"] == "denied"
            assert entry["org_id"] == ORG_ID
            assert entry["user_id"] == EDITOR_USER_ID
            assert entry["event"] == "trust_domain_crossing"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_crossings_logged_when_all_content_accessible(
        self, _founder_env
    ):
        """Founder accessing all content should log zero boundary crossings."""
        knowledge = [
            KnowledgeItem(
                id="k1", content="test", source="ws",
                trust_domain=TrustDomain.CUSTOMER_USER,
            ),
            KnowledgeItem(
                id="k2", content="test2", source="ws",
                trust_domain=TrustDomain.FOUNDER_PRIVATE,
            ),
        ]

        ctx = await build_workspace_context(
            user_id=FOUNDER_USER_ID,
            user_name="Founder",
            org_id=ORG_ID,
            org_name="Test Org",
            org_plan="enterprise",
            role="owner",
            knowledge=knowledge,
        )

        assert ctx.boundary_crossings_logged == 0
        audit = get_domain_audit(org_id=ORG_ID)
        assert len(audit) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_audit_records_correct_domain_info(
        self, mixed_knowledge: list[KnowledgeItem]
    ):
        """Audit entries should capture the correct requesting and target domains."""
        await build_workspace_context(
            user_id=VIEWER_USER_ID,
            user_name="Viewer",
            org_id=ORG_ID,
            org_name="Test Org",
            org_plan="starter",
            role="viewer",
            knowledge=mixed_knowledge,
        )

        audit = get_domain_audit(org_id=ORG_ID)
        # Viewer (CUSTOMER_USER) should have 3 crossings logged
        assert len(audit) == 3

        requesting_domains = {e["requesting_domain"] for e in audit}
        assert requesting_domains == {"CUSTOMER_USER"}

        target_domains = {e["target_domain"] for e in audit}
        assert target_domains == {"WORKSPACE_ADMIN", "PLATFORM_ADMIN", "FOUNDER_PRIVATE"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_crossings_with_empty_knowledge(self):
        """No knowledge items means no crossings."""
        ctx = await build_workspace_context(
            user_id=EDITOR_USER_ID,
            user_name="Editor",
            org_id=ORG_ID,
            org_name="Test Org",
            org_plan="pro",
            role="editor",
            knowledge=[],
        )

        assert ctx.boundary_crossings_logged == 0
        assert ctx.knowledge == []


# =============================================================================
# Context Building Tests
# =============================================================================


class TestBuildWorkspaceContext:
    """Verify the full context building pipeline."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_builds_with_all_fields(self):
        """Context should include all supplied entity information."""
        project = ProjectSummary(id="proj-1", name="Campaign X", status="active")
        talent = TalentSummary(id="talent-1", name="Aria", talent_type="ai_persona")
        connections = [
            ConnectionSummary(id="conn-1", name="TikTok", provider="tiktok"),
            ConnectionSummary(id="conn-2", name="Instagram", provider="instagram"),
        ]
        preferences = [
            PreferenceItem(key="style", value="photorealistic", category="generation"),
        ]
        knowledge = [
            KnowledgeItem(
                id="k1", content="Brand guidelines", source="workspace",
                trust_domain=TrustDomain.CUSTOMER_USER,
            ),
        ]

        ctx = await build_workspace_context(
            user_id=EDITOR_USER_ID,
            user_name="Creative Director",
            org_id=ORG_ID,
            org_name="Brand Studio",
            org_plan="pro",
            role="editor",
            active_project=project,
            selected_talent=talent,
            connections=connections,
            preferences=preferences,
            knowledge=knowledge,
            email="director@studio.com",
        )

        # User context
        assert ctx.user.user_id == EDITOR_USER_ID
        assert ctx.user.name == "Creative Director"
        assert ctx.user.role == "editor"
        assert ctx.user.trust_domain == TrustDomain.CUSTOMER_USER
        assert ctx.user.email == "director@studio.com"

        # Workspace
        assert ctx.workspace.org_id == ORG_ID
        assert ctx.workspace.name == "Brand Studio"
        assert ctx.workspace.plan == "pro"

        # Entities
        assert ctx.active_project == project
        assert ctx.selected_talent == talent
        assert len(ctx.connections) == 2
        assert len(ctx.preferences) == 1
        assert len(ctx.knowledge) == 1

        # Trust context
        assert ctx.trust_context is not None
        assert ctx.trust_context.domain == TrustDomain.CUSTOMER_USER

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_builds_with_minimal_fields(self):
        """Context should work with only required fields."""
        ctx = await build_workspace_context(
            user_id=EDITOR_USER_ID,
            user_name="User",
            org_id=ORG_ID,
            org_name="Org",
            org_plan="free",
            role="viewer",
        )

        assert ctx.user.user_id == EDITOR_USER_ID
        assert ctx.workspace.org_id == ORG_ID
        assert ctx.active_project is None
        assert ctx.selected_talent is None
        assert ctx.connections == []
        assert ctx.preferences == []
        assert ctx.knowledge == []
        assert ctx.boundary_crossings_logged == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_trust_domain_resolved_correctly_for_owner(self):
        """Owner role should resolve to WORKSPACE_ADMIN trust domain."""
        ctx = await build_workspace_context(
            user_id=ADMIN_USER_ID,
            user_name="Owner",
            org_id=ORG_ID,
            org_name="Org",
            org_plan="enterprise",
            role="owner",
        )

        assert ctx.user.trust_domain == TrustDomain.WORKSPACE_ADMIN
        assert ctx.trust_context is not None
        assert ctx.trust_context.domain == TrustDomain.WORKSPACE_ADMIN


# =============================================================================
# Context Summary Tests
# =============================================================================


class TestWorkspaceContextSummary:
    """Verify the serializable summary for Brain context injection."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_summarize_context_captures_all_fields(self):
        """Summary should capture key fields from the full context."""
        ctx = await build_workspace_context(
            user_id=EDITOR_USER_ID,
            user_name="Creator",
            org_id=ORG_ID,
            org_name="Studio",
            org_plan="pro",
            role="editor",
            active_project=ProjectSummary(id="p1", name="Summer Campaign"),
            selected_talent=TalentSummary(id="t1", name="Aria"),
            connections=[ConnectionSummary(id="c1", name="TikTok", provider="tiktok")],
            preferences=[PreferenceItem(key="style", value="anime")],
            knowledge=[
                KnowledgeItem(
                    id="k1", content="info", source="ws",
                    trust_domain=TrustDomain.CUSTOMER_USER,
                ),
            ],
        )

        summary = summarize_context(ctx)

        assert summary.user_name == "Creator"
        assert summary.user_role == "editor"
        assert summary.trust_domain == "CUSTOMER_USER"
        assert summary.workspace_name == "Studio"
        assert summary.workspace_plan == "pro"
        assert summary.active_project_name == "Summer Campaign"
        assert summary.selected_talent_name == "Aria"
        assert summary.connection_count == 1
        assert summary.preference_count == 1
        assert summary.knowledge_item_count == 1

    @pytest.mark.unit
    def test_summary_to_context_string(self):
        """to_context_string should produce a readable multi-line string."""
        summary = WorkspaceContextSummary(
            user_name="Alice",
            user_role="editor",
            trust_domain="CUSTOMER_USER",
            workspace_name="Creative Studio",
            workspace_plan="pro",
            active_project_name="Q4 Campaign",
            selected_talent_name="Aria",
            connection_count=3,
            preference_count=2,
            knowledge_item_count=5,
        )

        ctx_str = summary.to_context_string()

        assert "User: Alice (role: editor)" in ctx_str
        assert "Workspace: Creative Studio (plan: pro)" in ctx_str
        assert "Active Project: Q4 Campaign" in ctx_str
        assert "Selected Talent: Aria" in ctx_str
        assert "Connections: 3" in ctx_str
        assert "Preferences: 2" in ctx_str
        assert "Knowledge Items: 5" in ctx_str

    @pytest.mark.unit
    def test_summary_without_optional_fields(self):
        """Summary should handle None project and talent gracefully."""
        summary = WorkspaceContextSummary(
            user_name="Bob",
            user_role="viewer",
            trust_domain="CUSTOMER_USER",
            workspace_name="Org",
            workspace_plan="free",
            active_project_name=None,
            selected_talent_name=None,
            connection_count=0,
            preference_count=0,
            knowledge_item_count=0,
        )

        ctx_str = summary.to_context_string()

        assert "Active Project:" not in ctx_str
        assert "Selected Talent:" not in ctx_str
        assert "User: Bob (role: viewer)" in ctx_str


# =============================================================================
# Customer Isolation Tests (R57.3, R57.4)
# =============================================================================


class TestCustomerIsolation:
    """Verify that customer users never see founder or platform content."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_customer_never_sees_founder_private(self):
        """R57.3: FOUNDER_PRIVATE content SHALL NEVER be visible to customers."""
        knowledge = [
            KnowledgeItem(
                id="founder-secret",
                content="Founder strategy: exit plan Q4",
                source="founder",
                trust_domain=TrustDomain.FOUNDER_PRIVATE,
            ),
            KnowledgeItem(
                id="customer-item",
                content="User prompt preferences",
                source="workspace",
                trust_domain=TrustDomain.CUSTOMER_USER,
            ),
        ]

        ctx = await build_workspace_context(
            user_id=EDITOR_USER_ID,
            user_name="Customer",
            org_id=ORG_ID,
            org_name="Org",
            org_plan="pro",
            role="editor",
            knowledge=knowledge,
        )

        # Only customer content visible
        assert len(ctx.knowledge) == 1
        assert ctx.knowledge[0].id == "customer-item"

        # Founder content never leaked
        for item in ctx.knowledge:
            assert item.trust_domain != TrustDomain.FOUNDER_PRIVATE

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_customer_never_sees_platform_admin(self):
        """R57.4: PLATFORM_ADMIN content SHALL NOT be accessible to CUSTOMER_USER."""
        knowledge = [
            KnowledgeItem(
                id="platform-config",
                content="Platform database credentials",
                source="platform",
                trust_domain=TrustDomain.PLATFORM_ADMIN,
            ),
            KnowledgeItem(
                id="user-creative",
                content="Creative brief for summer",
                source="workspace",
                trust_domain=TrustDomain.CUSTOMER_USER,
            ),
        ]

        ctx = await build_workspace_context(
            user_id=VIEWER_USER_ID,
            user_name="Viewer",
            org_id=ORG_ID,
            org_name="Org",
            org_plan="starter",
            role="viewer",
            knowledge=knowledge,
        )

        assert len(ctx.knowledge) == 1
        assert ctx.knowledge[0].id == "user-creative"

        for item in ctx.knowledge:
            assert item.trust_domain != TrustDomain.PLATFORM_ADMIN

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_viewer_and_editor_get_same_filtering(self):
        """Both viewer and editor resolve to CUSTOMER_USER with same filtering."""
        knowledge = [
            KnowledgeItem(
                id="k1", content="open", source="ws",
                trust_domain=TrustDomain.CUSTOMER_USER,
            ),
            KnowledgeItem(
                id="k2", content="admin", source="ws",
                trust_domain=TrustDomain.WORKSPACE_ADMIN,
            ),
        ]

        viewer_ctx = await build_workspace_context(
            user_id=VIEWER_USER_ID,
            user_name="Viewer",
            org_id=ORG_ID,
            org_name="Org",
            org_plan="pro",
            role="viewer",
            knowledge=knowledge,
        )

        # Clear audit between calls
        clear_domain_audit()

        editor_ctx = await build_workspace_context(
            user_id=EDITOR_USER_ID,
            user_name="Editor",
            org_id=ORG_ID,
            org_name="Org",
            org_plan="pro",
            role="editor",
            knowledge=knowledge,
        )

        # Both see only customer-level content
        assert len(viewer_ctx.knowledge) == len(editor_ctx.knowledge) == 1
        assert viewer_ctx.knowledge[0].id == "k1"
        assert editor_ctx.knowledge[0].id == "k1"
