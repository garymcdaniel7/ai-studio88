"""Property-Based Tests — Property 15: Cross-Tenant Learning Boundary (Task 17.2).

Proves via property-based testing (hypothesis):
  - For ANY org O context retrieval, ZERO items from org P's proprietary
    creative content appear (where O != P)
  - This holds for ALL protected content types individually and in combination
  - Cross-tenant retrieval is logged as a P0 severity incident
  - Platform learning gate rejects ALL submissions while disabled
  - Multiple orgs with mixed items — only requesting org's items returned

Cross-tenant retrieval = P0 security incident.

**Validates: Requirements R95.1, R95.2**

Run with:
    pytest tests/unit/test_properties/test_property_15_cross_tenant_boundary.py -v
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.core.cross_tenant_boundary import (
    PLATFORM_LEARNING_DISABLED,
    PERMITTED_PLATFORM_SIGNALS,
    PROTECTED_CONTENT_TYPES,
    CrossTenantBoundary,
    PlatformLearningDisabledError,
    PlatformLearningGate,
)


# =============================================================================
# Strategies — constrained generators for property-based testing
# =============================================================================

# Org ID strategy: generates realistic org identifiers
org_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-_"),
    min_size=4,
    max_size=40,
).filter(lambda s: len(s.strip()) >= 4)

# Generate two DISTINCT org IDs
distinct_org_pair = st.tuples(org_id_strategy, org_id_strategy).filter(
    lambda pair: pair[0] != pair[1]
)

# Strategy for protected content types — picks from the real set
protected_content_type_strategy = st.sampled_from(sorted(PROTECTED_CONTENT_TYPES))

# Strategy for arbitrary content type strings (including non-protected ones)
arbitrary_content_type_strategy = st.one_of(
    protected_content_type_strategy,
    st.text(min_size=1, max_size=30).filter(
        lambda s: s not in PROTECTED_CONTENT_TYPES and s.strip()
    ),
)

# Strategy for multiple org IDs (3-6 distinct orgs)
multi_org_strategy = st.lists(
    org_id_strategy, min_size=3, max_size=6, unique=True
)

# Strategy for item counts per org
item_count_strategy = st.integers(min_value=1, max_value=10)

# Strategy for permitted platform signal types
permitted_signal_strategy = st.sampled_from(sorted(PERMITTED_PLATFORM_SIGNALS))

# Strategy for non-permitted signal types
non_permitted_signal_strategy = st.text(min_size=1, max_size=30).filter(
    lambda s: s not in PERMITTED_PLATFORM_SIGNALS and s.strip()
)


# =============================================================================
# Mock Context Item
# =============================================================================


@dataclass
class MockContextItem:
    """Mock context item implementing the ContextItem protocol."""

    id: str
    org_id: str
    content_type: str
    data: str = ""


# =============================================================================
# Property 15: Cross-Tenant Learning Boundary
# "For any org O context retrieval, zero items from org P's proprietary
#  creative content appear."
# =============================================================================


@pytest.mark.unit
class TestProperty15CrossTenantLearningBoundary:
    """Property 15: Cross-Tenant Learning Boundary.

    For any Brain/Hermes context retrieval for org O, zero items from org P's
    proprietary creative content (prompts, Creative DNA, assets, workflows,
    conversations) SHALL appear.

    **Validates: Requirements R95.1, R95.2**
    """

    @given(
        org_pair=distinct_org_pair,
        content_type=protected_content_type_strategy,
        item_count=item_count_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_zero_cross_tenant_items_for_each_protected_type(
        self,
        org_pair: tuple[str, str],
        content_type: str,
        item_count: int,
    ):
        """For EACH protected content type, org P's items never appear in org O's retrieval.

        **Validates: Requirements R95.1, R95.2**
        """
        org_o, org_p = org_pair
        boundary = CrossTenantBoundary()

        # Create items from org P with a protected content type
        items = [
            MockContextItem(
                id=f"item-{i}",
                org_id=org_p,
                content_type=content_type,
            )
            for i in range(item_count)
        ]

        # Org O requests context retrieval
        result = boundary.validate_context_retrieval(items, requesting_org_id=org_o)

        # PROPERTY: zero items from org P in org O's result
        assert len(result) == 0, (
            f"P0 CROSS-TENANT BREACH: {len(result)} items of type '{content_type}' "
            f"from org_p='{org_p}' appeared in org_o='{org_o}' context retrieval"
        )

    @given(
        org_pair=distinct_org_pair,
        content_type=arbitrary_content_type_strategy,
        item_count=item_count_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_zero_cross_tenant_items_for_any_content_type(
        self,
        org_pair: tuple[str, str],
        content_type: str,
        item_count: int,
    ):
        """Defense in depth: ANY content from another org is excluded, not just protected types.

        **Validates: Requirements R95.1**
        """
        org_o, org_p = org_pair
        boundary = CrossTenantBoundary()

        items = [
            MockContextItem(
                id=f"item-{i}",
                org_id=org_p,
                content_type=content_type,
            )
            for i in range(item_count)
        ]

        result = boundary.validate_context_retrieval(items, requesting_org_id=org_o)

        assert len(result) == 0, (
            f"ISOLATION BREACH: {len(result)} items of type '{content_type}' "
            f"from org_p='{org_p}' appeared in org_o='{org_o}' context"
        )

    @given(
        orgs=multi_org_strategy,
        content_types=st.lists(
            protected_content_type_strategy, min_size=3, max_size=10
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_multiple_orgs_mixed_items_only_requesting_org_returned(
        self,
        orgs: list[str],
        content_types: list[str],
    ):
        """With mixed items from multiple orgs, only requesting org's items returned.

        **Validates: Requirements R95.1, R95.2**
        """
        boundary = CrossTenantBoundary()
        requesting_org = orgs[0]

        # Create items from all orgs with various content types
        items: list[MockContextItem] = []
        for i, ct in enumerate(content_types):
            # Distribute items across orgs (round-robin)
            owner_org = orgs[i % len(orgs)]
            items.append(
                MockContextItem(
                    id=f"item-{i}",
                    org_id=owner_org,
                    content_type=ct,
                )
            )

        result = boundary.validate_context_retrieval(
            items, requesting_org_id=requesting_org
        )

        # PROPERTY: every item in result belongs to requesting org
        for item in result:
            assert item.org_id == requesting_org, (
                f"P0 CROSS-TENANT BREACH: item '{item.id}' from org '{item.org_id}' "
                f"appeared in requesting org '{requesting_org}' context"
            )

        # PROPERTY: all items from requesting org are included
        expected_count = sum(
            1 for it in items if it.org_id == requesting_org
        )
        assert len(result) == expected_count, (
            f"Expected {expected_count} items from requesting org, got {len(result)}"
        )

    @given(
        org_pair=distinct_org_pair,
        own_items_count=st.integers(min_value=1, max_value=5),
        foreign_items_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=200, deadline=None)
    def test_own_items_preserved_while_foreign_excluded(
        self,
        org_pair: tuple[str, str],
        own_items_count: int,
        foreign_items_count: int,
    ):
        """Requesting org's own items are preserved; foreign items are excluded.

        **Validates: Requirements R95.1**
        """
        org_o, org_p = org_pair
        boundary = CrossTenantBoundary()

        # Mix of own and foreign items
        items: list[MockContextItem] = []
        for i in range(own_items_count):
            items.append(
                MockContextItem(
                    id=f"own-{i}", org_id=org_o, content_type="prompts"
                )
            )
        for i in range(foreign_items_count):
            items.append(
                MockContextItem(
                    id=f"foreign-{i}", org_id=org_p, content_type="creative_dna"
                )
            )

        result = boundary.validate_context_retrieval(items, requesting_org_id=org_o)

        # Exactly own_items_count items returned (all from org_o)
        assert len(result) == own_items_count
        assert all(item.org_id == org_o for item in result)
        # None of org_p's items leaked
        assert not any(item.org_id == org_p for item in result)


# =============================================================================
# Property: Cross-Tenant Violation Logged as P0 Severity
# =============================================================================


@pytest.mark.unit
class TestProperty15ViolationLogging:
    """Cross-tenant retrieval of protected content is logged as P0 severity.

    **Validates: Requirements R95.1, R95.2**
    """

    @given(
        org_pair=distinct_org_pair,
        content_type=protected_content_type_strategy,
        item_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100, deadline=None)
    def test_violation_logged_as_p0_for_protected_cross_tenant_content(
        self,
        org_pair: tuple[str, str],
        content_type: str,
        item_count: int,
    ):
        """Each cross-tenant protected item generates a P0 violation log entry.

        **Validates: Requirements R95.1, R95.2**
        """
        org_o, org_p = org_pair
        boundary = CrossTenantBoundary()
        boundary.clear_violations()

        items = [
            MockContextItem(
                id=f"leak-{i}",
                org_id=org_p,
                content_type=content_type,
            )
            for i in range(item_count)
        ]

        # Trigger retrieval (items excluded but violations logged)
        boundary.validate_context_retrieval(items, requesting_org_id=org_o)

        violations = boundary.get_violations()

        # PROPERTY: exactly item_count violations logged
        assert len(violations) == item_count, (
            f"Expected {item_count} P0 violations, got {len(violations)}"
        )

        # PROPERTY: each violation has P0 severity
        for v in violations:
            assert v["severity"] == "P0", (
                f"Violation severity should be P0, got '{v['severity']}'"
            )
            assert v["event"] == "P0_CROSS_TENANT_VIOLATION"
            assert v["item_org_id"] == org_p
            assert v["requesting_org_id"] == org_o
            assert v["content_type"] == content_type

    @given(
        org_pair=distinct_org_pair,
        content_types=st.lists(
            protected_content_type_strategy, min_size=2, max_size=6
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_multiple_content_types_each_generates_violation(
        self,
        org_pair: tuple[str, str],
        content_types: list[str],
    ):
        """Multiple protected content types each generate separate violations.

        **Validates: Requirements R95.2**
        """
        org_o, org_p = org_pair
        boundary = CrossTenantBoundary()
        boundary.clear_violations()

        items = [
            MockContextItem(
                id=f"leak-{i}-{ct}",
                org_id=org_p,
                content_type=ct,
            )
            for i, ct in enumerate(content_types)
        ]

        boundary.validate_context_retrieval(items, requesting_org_id=org_o)

        violations = boundary.get_violations()
        assert len(violations) == len(content_types)

        # Verify each violation maps to the correct content type
        violation_types = {v["content_type"] for v in violations}
        expected_types = set(content_types)
        assert violation_types == expected_types


# =============================================================================
# Property: Platform Learning Gate Rejects All While Disabled
# =============================================================================


@pytest.mark.unit
class TestProperty15PlatformLearningGateDisabled:
    """Platform learning gate rejects ALL submissions while PLATFORM_LEARNING_DISABLED=True.

    **Validates: Requirements R95.1, R95.2**
    """

    @given(signal_type=permitted_signal_strategy)
    @settings(max_examples=50, deadline=None)
    def test_gate_rejects_even_permitted_signals_when_disabled(
        self,
        signal_type: str,
    ):
        """Even permitted signal types are rejected when the gate is disabled.

        **Validates: Requirements R95.1**
        """
        gate = PlatformLearningGate()

        # Gate should be disabled
        assert PLATFORM_LEARNING_DISABLED is True
        assert gate.is_enabled() is False

        # Submission of any signal type raises
        with pytest.raises(PlatformLearningDisabledError):
            gate.submit_for_aggregation({"signal_type": signal_type, "data": {}})

    @given(signal_type=non_permitted_signal_strategy)
    @settings(max_examples=50, deadline=None)
    def test_gate_rejects_non_permitted_signals_when_disabled(
        self,
        signal_type: str,
    ):
        """Non-permitted signal types are also rejected when disabled.

        **Validates: Requirements R95.2**
        """
        gate = PlatformLearningGate()

        with pytest.raises(PlatformLearningDisabledError):
            gate.submit_for_aggregation({"signal_type": signal_type, "data": {}})

    @given(
        data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(st.text(max_size=50), st.integers(), st.booleans()),
            min_size=0,
            max_size=5,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_gate_rejects_arbitrary_data_payloads_when_disabled(
        self,
        data: dict,
    ):
        """Arbitrary data payloads are rejected regardless of content.

        **Validates: Requirements R95.1**
        """
        gate = PlatformLearningGate()

        with pytest.raises(PlatformLearningDisabledError):
            gate.submit_for_aggregation(data)


# =============================================================================
# Property: is_cross_tenant_violation correctness
# =============================================================================


@pytest.mark.unit
class TestProperty15ViolationDetection:
    """is_cross_tenant_violation correctly classifies all combinations.

    **Validates: Requirements R95.1, R95.2**
    """

    @given(
        org_pair=distinct_org_pair,
        content_type=protected_content_type_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_different_org_protected_type_is_always_violation(
        self,
        org_pair: tuple[str, str],
        content_type: str,
    ):
        """Different org + protected content type = ALWAYS a violation.

        **Validates: Requirements R95.2**
        """
        org_o, org_p = org_pair
        boundary = CrossTenantBoundary()

        assert boundary.is_cross_tenant_violation(
            item_org_id=org_p,
            requesting_org_id=org_o,
            content_type=content_type,
        ) is True

    @given(
        org=org_id_strategy,
        content_type=protected_content_type_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_same_org_is_never_violation(
        self,
        org: str,
        content_type: str,
    ):
        """Same org is NEVER a violation regardless of content type.

        **Validates: Requirements R95.1**
        """
        boundary = CrossTenantBoundary()

        assert boundary.is_cross_tenant_violation(
            item_org_id=org,
            requesting_org_id=org,
            content_type=content_type,
        ) is False
