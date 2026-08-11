"""Create page guidance hierarchy tests — Story 116.

Tests prove:
  - Creator sees outcome-focused guidance (no infrastructure)
  - Admin can access diagnostics when toggled
  - Unauthorized user cannot see diagnostics
  - Degraded state is truthfully shown
  - No SSH/worker commands in basic creator path
  - Content classification catches infrastructure patterns
  - Link protection: admin links hidden from creators
  - Advanced controls only shown when toggled
  - All capability states have truthful messages
"""

import pytest

from backend.create_guidance import (
    CapabilityState,
    DiagnosticInfo,
    GuidanceTier,
    UserRole,
    classify_content,
    filter_links_for_role,
    is_content_appropriate_for_tier,
    is_link_authorized,
    resolve_guidance,
)


# =============================================================================
# Creator Path (outcome-focused, no infrastructure)
# =============================================================================


@pytest.mark.unit
class TestCreatorPath:

    def test_ready_shows_outcome_guidance(self):
        guidance = resolve_guidance(UserRole.EDITOR, CapabilityState.READY)
        assert guidance.can_generate is True
        assert guidance.status.headline == "Ready to create"
        # Creator items present
        creator_items = [i for i in guidance.visible_items if i.tier == GuidanceTier.CREATOR]
        assert len(creator_items) > 0
        assert "create" in creator_items[0].message.lower() or "describe" in creator_items[0].message.lower()

    def test_no_infrastructure_in_creator_items(self):
        guidance = resolve_guidance(UserRole.EDITOR, CapabilityState.READY)
        for item in guidance.visible_items:
            if item.tier == GuidanceTier.CREATOR:
                assert "ssh" not in item.message.lower()
                assert "worker" not in item.message.lower()
                assert "comfyui" not in item.message.lower()
                assert "vast.ai" not in item.message.lower()

    def test_unavailable_still_helpful(self):
        guidance = resolve_guidance(UserRole.EDITOR, CapabilityState.UNAVAILABLE)
        assert guidance.can_generate is False
        assert guidance.status.headline == "Generation unavailable"
        # Offers alternative action
        creator_items = [i for i in guidance.visible_items if i.tier == GuidanceTier.CREATOR]
        assert any(i.action_label for i in creator_items)

    def test_provisioning_shows_progress(self):
        guidance = resolve_guidance(UserRole.EDITOR, CapabilityState.PROVISIONING)
        assert "ready" in guidance.status.headline.lower() or "setting up" in guidance.status.headline.lower()
        assert guidance.status.recoverable is True


# =============================================================================
# Admin Diagnostics (role-gated)
# =============================================================================


@pytest.mark.unit
class TestAdminDiagnostics:

    def test_admin_can_see_diagnostics_toggle(self):
        guidance = resolve_guidance(UserRole.ADMIN, CapabilityState.READY)
        assert guidance.can_see_diagnostics is True

    def test_admin_sees_diagnostics_when_toggled(self):
        diag = DiagnosticInfo(
            worker_status="running",
            gpu_provider="vast.ai",
            ssh_command="ssh root@1.2.3.4",
            model_cache_status="2 models cached",
        )
        guidance = resolve_guidance(
            UserRole.ADMIN, CapabilityState.READY,
            show_diagnostics=True, diagnostics=diag,
        )
        assert guidance.diagnostics is not None
        assert guidance.diagnostics.ssh_command == "ssh root@1.2.3.4"

    def test_editor_cannot_see_diagnostics(self):
        guidance = resolve_guidance(UserRole.EDITOR, CapabilityState.READY)
        assert guidance.can_see_diagnostics is False

    def test_editor_diagnostics_toggle_ignored(self):
        diag = DiagnosticInfo(ssh_command="ssh secret")
        guidance = resolve_guidance(
            UserRole.EDITOR, CapabilityState.READY,
            show_diagnostics=True, diagnostics=diag,
        )
        assert guidance.diagnostics is None

    def test_viewer_cannot_see_diagnostics(self):
        guidance = resolve_guidance(UserRole.VIEWER, CapabilityState.READY)
        assert guidance.can_see_diagnostics is False


# =============================================================================
# Degraded State Truthful
# =============================================================================


@pytest.mark.unit
class TestDegradedState:

    def test_degraded_shows_truthful_status(self):
        guidance = resolve_guidance(UserRole.EDITOR, CapabilityState.DEGRADED)
        assert guidance.status.state == CapabilityState.DEGRADED
        assert "limited" in guidance.status.headline.lower()

    def test_unknown_state_truthful(self):
        guidance = resolve_guidance(UserRole.EDITOR, CapabilityState.UNKNOWN)
        assert "checking" in guidance.status.headline.lower() or "unable" in guidance.status.detail.lower()

    def test_hermes_can_help_flagged(self):
        guidance = resolve_guidance(UserRole.EDITOR, CapabilityState.UNAVAILABLE)
        assert guidance.status.hermes_can_help is True


# =============================================================================
# No SSH in Basic Path
# =============================================================================


@pytest.mark.unit
class TestNoSSHInBasicPath:

    def test_ssh_classified_as_admin(self):
        assert classify_content("Run: ssh root@192.168.1.1 -p 22") == GuidanceTier.ADMIN

    def test_worker_commands_classified_as_admin(self):
        assert classify_content("Start the GPU worker with vast.ai") == GuidanceTier.ADMIN

    def test_comfyui_classified_as_admin(self):
        assert classify_content("Check ComfyUI health endpoint") == GuidanceTier.ADMIN

    def test_outcome_text_classified_as_creator(self):
        assert classify_content("Describe what you'd like to create") == GuidanceTier.CREATOR

    def test_prompt_text_classified_as_creator(self):
        assert classify_content("A photorealistic portrait in golden hour light") == GuidanceTier.CREATOR

    def test_infrastructure_not_appropriate_for_creator(self):
        assert is_content_appropriate_for_tier("ssh root@host", GuidanceTier.CREATOR) is False

    def test_infrastructure_appropriate_for_admin(self):
        assert is_content_appropriate_for_tier("ssh root@host", GuidanceTier.ADMIN) is True


# =============================================================================
# Advanced Controls (explicit toggle)
# =============================================================================


@pytest.mark.unit
class TestAdvancedControls:

    def test_advanced_hidden_by_default(self):
        guidance = resolve_guidance(UserRole.EDITOR, CapabilityState.READY)
        advanced_items = [i for i in guidance.visible_items if i.tier == GuidanceTier.ADVANCED]
        assert len(advanced_items) == 0

    def test_advanced_shown_when_toggled(self):
        guidance = resolve_guidance(UserRole.EDITOR, CapabilityState.READY, show_advanced=True)
        advanced_items = [i for i in guidance.visible_items if i.tier == GuidanceTier.ADVANCED]
        assert len(advanced_items) > 0

    def test_all_users_can_toggle_advanced(self):
        guidance = resolve_guidance(UserRole.VIEWER, CapabilityState.READY)
        assert guidance.can_see_advanced is True


# =============================================================================
# Link Protection
# =============================================================================


@pytest.mark.unit
class TestLinkProtection:

    def test_admin_sees_all_links(self):
        links = ["/create", "/admin/fleet", "/admin/health", "/talent"]
        filtered = filter_links_for_role(links, UserRole.ADMIN)
        assert filtered == links

    def test_editor_no_admin_links(self):
        links = ["/create", "/admin/fleet", "/admin/health", "/talent"]
        filtered = filter_links_for_role(links, UserRole.EDITOR)
        assert "/admin/fleet" not in filtered
        assert "/admin/health" not in filtered
        assert "/create" in filtered
        assert "/talent" in filtered

    def test_viewer_no_admin_links(self):
        links = ["/create", "/admin/fleet", "/settings"]
        filtered = filter_links_for_role(links, UserRole.VIEWER)
        assert "/admin/fleet" not in filtered
        assert "/settings" not in filtered

    def test_is_link_authorized_admin_only(self):
        assert is_link_authorized("/admin/fleet", UserRole.EDITOR) is False
        assert is_link_authorized("/admin/fleet", UserRole.ADMIN) is True
        assert is_link_authorized("/create", UserRole.VIEWER) is True


# =============================================================================
# All Capability States Have Messages
# =============================================================================


@pytest.mark.unit
class TestAllStatesHaveMessages:

    def test_every_state_has_status(self):
        for state in CapabilityState:
            guidance = resolve_guidance(UserRole.EDITOR, state)
            assert guidance.status is not None
            assert guidance.status.headline
            assert guidance.status.state == state
