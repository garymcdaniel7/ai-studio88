"""Unit Tests — Cross-Tenant Learning Boundary (Task 17.1).

Proves:
  - Items from org B never appear in org A's context retrieval
  - All protected content types are excluded cross-tenant
  - Platform learning gate rejects submissions when disabled
  - Violation logging records P0 security incidents correctly
  - Same-org items are always included
  - Items without org_id are excluded (deny by default)

Validates: Requirements R95.1, R95.2, R95.3, R95.4, A2-034

Run with:
    pytest tests/unit/test_cross_tenant_boundary.py -v
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core.cross_tenant_boundary import (
    PLATFORM_LEARNING_DISABLED,
    PERMITTED_PLATFORM_SIGNALS,
    PROTECTED_CONTENT_TYPES,
    CrossTenantBoundary,
    CrossTenantViolationError,
    PlatformLearningDisabledError,
    PlatformLearningGate,
)


# =============================================================================
# Test Fixtures — Mock context items
# =============================================================================


@dataclass
class MockContextItem:
    """Mock context item implementing the ContextItem protocol."""

    id: str
    org_id: str
    content_type: str
    data: str = ""


@pytest.fixture
def boundary() -> CrossTenantBoundary:
    """Fresh CrossTenantBoundary instance for each test."""
    b = CrossTenantBoundary()
    b.clear_violations()
    return b


@pytest.fixture
def gate() -> PlatformLearningGate:
    """Fresh PlatformLearningGate instance."""
    return PlatformLearningGate()


# =============================================================================
# CrossTenantBoundary — Core Isolation Tests
# =============================================================================


@pytest.mark.unit
class TestCrossTenantBoundaryIsolation:
    """Items from org B never appear in org A's context retrieval.

    **Validates: Requirements R95.1, R95.2**
    """

    def test_same_org_items_included(self, boundary: CrossTenantBoundary):
        """Items from the requesting org are always included."""
        items = [
            MockContextItem(id="item-1", org_id="org-alpha", content_type="prompts"),
            MockContextItem(id="item-2", org_id="org-alpha", content_type="assets"),
            MockContextItem(id="item-3", org_id="org-alpha", content_type="conversations"),
        ]
        result = boundary.validate_context_retrieval(items, requesting_org_id="org-alpha")
        assert len(result) == 3
        assert all(item.org_id == "org-alpha" for item in result)

    def test_different_org_protected_content_excluded(self, boundary: CrossTenantBoundary):
        """Protected content from a different org is excluded."""
        items = [
            MockContextItem(id="item-1", org_id="org-alpha", content_type="prompts"),
            MockContextItem(id="item-2", org_id="org-beta", content_type="prompts"),
            MockContextItem(id="item-3", org_id="org-alpha", content_type="assets"),
        ]
        result = boundary.validate_context_retrieval(items, requesting_org_id="org-alpha")
        assert len(result) == 2
        assert all(item.org_id == "org-alpha" for item in result)

    def test_all_protected_content_types_excluded_cross_tenant(
        self, boundary: CrossTenantBoundary
    ):
        """Every protected content type from another org is excluded."""
        requesting_org = "org-alpha"
        other_org = "org-beta"

        for content_type in PROTECTED_CONTENT_TYPES:
            items = [
                MockContextItem(
                    id=f"item-{content_type}",
                    org_id=other_org,
                    content_type=content_type,
                ),
            ]
            result = boundary.validate_context_retrieval(
                items, requesting_org_id=requesting_org
            )
            assert len(result) == 0, (
                f"ISOLATION BREACH: content_type='{content_type}' from "
                f"org='{other_org}' was included in org='{requesting_org}' context"
            )

    def test_non_protected_content_from_other_org_also_excluded(
        self, boundary: CrossTenantBoundary
    ):
        """Even non-protected content from another org is excluded (defense in depth)."""
        items = [
            MockContextItem(
                id="item-1",
                org_id="org-beta",
                content_type="some_unknown_type",
            ),
        ]
        result = boundary.validate_context_retrieval(
            items, requesting_org_id="org-alpha"
        )
        assert len(result) == 0

    def test_mixed_orgs_only_requesting_org_returned(
        self, boundary: CrossTenantBoundary
    ):
        """In a mixed-org item list, only requesting org's items are returned."""
        items = [
            MockContextItem(id="1", org_id="org-alpha", content_type="prompts"),
            MockContextItem(id="2", org_id="org-beta", content_type="prompts"),
            MockContextItem(id="3", org_id="org-gamma", content_type="assets"),
            MockContextItem(id="4", org_id="org-alpha", content_type="creative_dna"),
            MockContextItem(id="5", org_id="org-delta", content_type="workflows"),
        ]
        result = boundary.validate_context_retrieval(
            items, requesting_org_id="org-alpha"
        )
        assert len(result) == 2
        assert {item.id for item in result} == {"1", "4"}

    def test_empty_items_returns_empty(self, boundary: CrossTenantBoundary):
        """Empty input returns empty output."""
        result = boundary.validate_context_retrieval([], requesting_org_id="org-alpha")
        assert result == []

    def test_empty_requesting_org_id_returns_empty(self, boundary: CrossTenantBoundary):
        """Empty requesting_org_id returns empty (deny by default)."""
        items = [
            MockContextItem(id="1", org_id="org-alpha", content_type="prompts"),
        ]
        result = boundary.validate_context_retrieval(items, requesting_org_id="")
        assert result == []

    def test_item_without_org_id_excluded(self, boundary: CrossTenantBoundary):
        """Items without org_id attribute are excluded (deny by default)."""
        items = [
            MockContextItem(id="1", org_id="", content_type="prompts"),
        ]
        result = boundary.validate_context_retrieval(
            items, requesting_org_id="org-alpha"
        )
        assert result == []


# =============================================================================
# CrossTenantBoundary — is_cross_tenant_violation() Tests
# =============================================================================


@pytest.mark.unit
class TestIsCrossTenantViolation:
    """is_cross_tenant_violation correctly identifies violations.

    **Validates: Requirements R95.1, R95.5**
    """

    def test_same_org_not_violation(self, boundary: CrossTenantBoundary):
        """Same org is never a violation regardless of content type."""
        for ct in PROTECTED_CONTENT_TYPES:
            assert boundary.is_cross_tenant_violation(
                item_org_id="org-a", requesting_org_id="org-a", content_type=ct
            ) is False

    def test_different_org_protected_type_is_violation(
        self, boundary: CrossTenantBoundary
    ):
        """Different org + protected content type = violation."""
        for ct in PROTECTED_CONTENT_TYPES:
            assert boundary.is_cross_tenant_violation(
                item_org_id="org-a", requesting_org_id="org-b", content_type=ct
            ) is True

    def test_different_org_non_protected_type_not_violation(
        self, boundary: CrossTenantBoundary
    ):
        """Different org + non-protected type = not a P0 violation (but still excluded)."""
        assert boundary.is_cross_tenant_violation(
            item_org_id="org-a",
            requesting_org_id="org-b",
            content_type="unknown_safe_type",
        ) is False

    def test_empty_org_ids_not_violation(self, boundary: CrossTenantBoundary):
        """Empty org_ids are not considered violations (handled separately)."""
        assert boundary.is_cross_tenant_violation(
            item_org_id="", requesting_org_id="org-b", content_type="prompts"
        ) is False
        assert boundary.is_cross_tenant_violation(
            item_org_id="org-a", requesting_org_id="", content_type="prompts"
        ) is False


# =============================================================================
# CrossTenantBoundary — Violation Logging Tests
# =============================================================================


@pytest.mark.unit
class TestViolationLogging:
    """Violation logging records P0 security incidents correctly.

    **Validates: Requirements R95.5**
    """

    def test_violation_logged_when_cross_tenant_content_present(
        self, boundary: CrossTenantBoundary
    ):
        """When cross-tenant protected content is in retrieval, a violation is logged."""
        items = [
            MockContextItem(id="leak-1", org_id="org-beta", content_type="prompts"),
        ]
        boundary.validate_context_retrieval(items, requesting_org_id="org-alpha")

        violations = boundary.get_violations()
        assert len(violations) == 1
        assert violations[0]["event"] == "P0_CROSS_TENANT_VIOLATION"
        assert violations[0]["severity"] == "P0"
        assert violations[0]["item_org_id"] == "org-beta"
        assert violations[0]["requesting_org_id"] == "org-alpha"
        assert violations[0]["content_type"] == "prompts"
        assert violations[0]["item_id"] == "leak-1"

    def test_multiple_violations_all_logged(self, boundary: CrossTenantBoundary):
        """Multiple cross-tenant items each generate a violation record."""
        items = [
            MockContextItem(id="leak-1", org_id="org-beta", content_type="prompts"),
            MockContextItem(id="leak-2", org_id="org-gamma", content_type="assets"),
            MockContextItem(id="leak-3", org_id="org-beta", content_type="creative_dna"),
        ]
        boundary.validate_context_retrieval(items, requesting_org_id="org-alpha")

        violations = boundary.get_violations()
        assert len(violations) == 3

    def test_log_violation_direct_call(self, boundary: CrossTenantBoundary):
        """log_violation() can be called directly and records the incident."""
        boundary.log_violation(
            item_org_id="org-evil",
            requesting_org_id="org-victim",
            content_type="conversations",
            item_id="conv-123",
        )

        violations = boundary.get_violations()
        assert len(violations) == 1
        assert violations[0]["content_type"] == "conversations"
        assert violations[0]["item_id"] == "conv-123"

    def test_get_violations_filtered_by_org(self, boundary: CrossTenantBoundary):
        """get_violations() can filter by org_id."""
        boundary.log_violation("org-a", "org-b", "prompts", "item-1")
        boundary.log_violation("org-c", "org-d", "assets", "item-2")
        boundary.log_violation("org-a", "org-e", "workflows", "item-3")

        # Filter by org-a (as item_org_id or requesting_org_id)
        violations = boundary.get_violations(org_id="org-a")
        assert len(violations) == 2

    def test_clear_violations(self, boundary: CrossTenantBoundary):
        """clear_violations() removes all recorded violations."""
        boundary.log_violation("org-a", "org-b", "prompts", "item-1")
        assert len(boundary.get_violations()) == 1
        boundary.clear_violations()
        assert len(boundary.get_violations()) == 0

    def test_no_violation_for_same_org_content(self, boundary: CrossTenantBoundary):
        """No violation logged when content is from the same org."""
        items = [
            MockContextItem(id="item-1", org_id="org-alpha", content_type="prompts"),
        ]
        boundary.validate_context_retrieval(items, requesting_org_id="org-alpha")
        assert len(boundary.get_violations()) == 0


# =============================================================================
# PlatformLearningGate Tests
# =============================================================================


@pytest.mark.unit
class TestPlatformLearningGate:
    """Platform learning gate rejects when disabled (A2-034).

    **Validates: Requirements R95.3, R95.4, A2-034**
    """

    def test_platform_learning_disabled_flag(self):
        """PLATFORM_LEARNING_DISABLED is True at module level."""
        assert PLATFORM_LEARNING_DISABLED is True

    def test_gate_is_not_enabled(self, gate: PlatformLearningGate):
        """Gate reports not enabled when PLATFORM_LEARNING_DISABLED=True."""
        assert gate.is_enabled() is False

    def test_submit_for_aggregation_raises_when_disabled(
        self, gate: PlatformLearningGate
    ):
        """submit_for_aggregation() raises PlatformLearningDisabledError."""
        with pytest.raises(PlatformLearningDisabledError) as exc_info:
            gate.submit_for_aggregation({"signal_type": "ux_patterns", "data": {}})
        assert "A2-034" in str(exc_info.value)

    def test_submit_raises_for_all_signal_types_when_disabled(
        self, gate: PlatformLearningGate
    ):
        """Even permitted signal types are rejected when gate is disabled."""
        for signal_type in PERMITTED_PLATFORM_SIGNALS:
            with pytest.raises(PlatformLearningDisabledError):
                gate.submit_for_aggregation(
                    {"signal_type": signal_type, "value": 42}
                )

    def test_validate_signal_type_permitted(self, gate: PlatformLearningGate):
        """validate_signal_type() returns True for permitted signals."""
        for signal in PERMITTED_PLATFORM_SIGNALS:
            assert gate.validate_signal_type(signal) is True

    def test_validate_signal_type_not_permitted(self, gate: PlatformLearningGate):
        """validate_signal_type() returns False for non-permitted signals."""
        forbidden_signals = ["prompts", "creative_dna", "raw_content", "talent_ideas"]
        for signal in forbidden_signals:
            assert gate.validate_signal_type(signal) is False

    def test_permitted_signals_are_aggregated_only(self):
        """Verify PERMITTED_PLATFORM_SIGNALS only contains aggregated types."""
        # These are the signals defined in R95.3
        expected_signals = {
            "ux_patterns",
            "routing_optimization",
            "success_rates",
            "assistance_patterns",
            "performance_optimization",
            "recommendation_quality",
            "general_capability",
        }
        assert PERMITTED_PLATFORM_SIGNALS == expected_signals


# =============================================================================
# Protected Content Types — Completeness Tests
# =============================================================================


@pytest.mark.unit
class TestProtectedContentTypes:
    """Verify PROTECTED_CONTENT_TYPES covers all required types per R95.2.

    **Validates: Requirements R95.2**
    """

    def test_all_required_types_present(self):
        """All content types listed in R95.2 are in PROTECTED_CONTENT_TYPES."""
        required = {
            "prompts",
            "campaigns",
            "stories",
            "talent_data",
            "creative_dna",
            "assets",
            "conversations",
            "workflows",
            "generated_media",
            "brain_memory",
            "workspace_knowledge",
        }
        assert required.issubset(PROTECTED_CONTENT_TYPES)

    def test_protected_types_is_frozenset(self):
        """PROTECTED_CONTENT_TYPES is immutable (frozenset)."""
        assert isinstance(PROTECTED_CONTENT_TYPES, frozenset)

    def test_protected_types_not_empty(self):
        """PROTECTED_CONTENT_TYPES has at least the 11 required types."""
        assert len(PROTECTED_CONTENT_TYPES) >= 11


# =============================================================================
# Exception Tests
# =============================================================================


@pytest.mark.unit
class TestExceptions:
    """Exception classes carry correct metadata."""

    def test_cross_tenant_violation_error_attributes(self):
        """CrossTenantViolationError carries org, content_type, and item_id."""
        err = CrossTenantViolationError(
            item_org_id="org-evil",
            requesting_org_id="org-victim",
            content_type="prompts",
            item_id="item-123",
        )
        assert err.item_org_id == "org-evil"
        assert err.requesting_org_id == "org-victim"
        assert err.content_type == "prompts"
        assert err.item_id == "item-123"
        assert "P0" in str(err)
        assert "CROSS-TENANT" in str(err)

    def test_platform_learning_disabled_error_message(self):
        """PlatformLearningDisabledError has a descriptive message."""
        err = PlatformLearningDisabledError()
        assert "A2-034" in str(err)
