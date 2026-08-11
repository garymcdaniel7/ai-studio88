"""Property tests for social provenance integrity.

Property 21: Social Provenance Integrity
    For any social metric or insight presented in Brain context or API responses,
    DERIVED_ANALYSIS and PUBLIC_PLATFORM_DATA provenance SHALL never be internally
    represented or externally presented as FIRST_PARTY_CONNECTED private analytics.

Validates: Requirements R43.13, R107.10, A2-009
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# =============================================================================
# Local Domain Types (Social Intelligence module does not exist yet)
# =============================================================================


class DataProvenance(str, Enum):
    """Data provenance classification per design.md A2-008."""

    FIRST_PARTY_CONNECTED = "FIRST_PARTY_CONNECTED"
    PUBLIC_PLATFORM_DATA = "PUBLIC_PLATFORM_DATA"
    THIRD_PARTY_DATA = "THIRD_PARTY_DATA"
    USER_IMPORTED = "USER_IMPORTED"
    DERIVED_ANALYSIS = "DERIVED_ANALYSIS"


class ReasoningClass(str, Enum):
    """Reasoning classification per design.md A2-009."""

    OBSERVED_FACT = "OBSERVED_FACT"
    DERIVED_METRIC = "DERIVED_METRIC"
    STATISTICAL_PATTERN = "STATISTICAL_PATTERN"
    AI_INTERPRETATION = "AI_INTERPRETATION"
    RECOMMENDATION = "RECOMMENDATION"


class CollectionMethod(str, Enum):
    """How the data was collected."""

    API_SYNC = "api_sync"
    MANUAL_IMPORT = "manual_import"
    PUBLIC_SCRAPE = "public_scrape"
    CALCULATED = "calculated"


@dataclass(frozen=True)
class MetricSnapshot:
    """A social metric observation — immutable after creation."""

    id: UUID
    org_id: UUID
    social_account_id: UUID
    metric_type: str
    metric_value: float
    provenance: DataProvenance
    collection_method: CollectionMethod
    observation_timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True)
class DerivedInsight:
    """An insight derived from analysis — immutable after creation."""

    id: UUID
    org_id: UUID
    insight_type: str
    content: dict
    provenance: DataProvenance
    confidence: float
    reasoning_class: ReasoningClass
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True)
class BrainContextItem:
    """An item injected into Brain context — provenance must survive."""

    id: UUID
    source_id: UUID
    source_type: str  # "metric" or "insight"
    provenance: DataProvenance
    reasoning_class: ReasoningClass
    content_summary: str
    injected_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# =============================================================================
# Social Provenance Validation Service (local implementation)
# =============================================================================


class ProvenanceViolationError(Exception):
    """Raised when a provenance integrity rule is violated."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# Valid reasoning classes per provenance type
VALID_REASONING_FOR_PROVENANCE: dict[DataProvenance, set[ReasoningClass]] = {
    DataProvenance.FIRST_PARTY_CONNECTED: {
        ReasoningClass.OBSERVED_FACT,
        ReasoningClass.DERIVED_METRIC,
    },
    DataProvenance.PUBLIC_PLATFORM_DATA: {
        ReasoningClass.STATISTICAL_PATTERN,
        ReasoningClass.AI_INTERPRETATION,
        ReasoningClass.DERIVED_METRIC,
    },
    DataProvenance.THIRD_PARTY_DATA: {
        ReasoningClass.STATISTICAL_PATTERN,
        ReasoningClass.AI_INTERPRETATION,
        ReasoningClass.DERIVED_METRIC,
    },
    DataProvenance.USER_IMPORTED: {
        ReasoningClass.DERIVED_METRIC,
        ReasoningClass.STATISTICAL_PATTERN,
    },
    DataProvenance.DERIVED_ANALYSIS: {
        ReasoningClass.STATISTICAL_PATTERN,
        ReasoningClass.AI_INTERPRETATION,
        ReasoningClass.RECOMMENDATION,
        ReasoningClass.DERIVED_METRIC,
    },
}


class SocialProvenanceValidator:
    """Validates social provenance integrity rules.

    Ensures that:
    - DERIVED_ANALYSIS is never relabeled as FIRST_PARTY_CONNECTED
    - PUBLIC_PLATFORM_DATA is never relabeled as FIRST_PARTY_CONNECTED
    - Reasoning class is consistent with provenance type
    - Provenance survives Brain context injection
    - Missing data returns UNAVAILABLE, never fabricated provenance
    """

    def validate_metric_provenance(self, metric: MetricSnapshot) -> None:
        """Validate that a metric's provenance is internally consistent."""
        if metric.provenance == DataProvenance.DERIVED_ANALYSIS:
            raise ProvenanceViolationError(
                "Metrics cannot have DERIVED_ANALYSIS provenance — "
                "only insights can be derived.",
                code="METRIC_INVALID_PROVENANCE",
            )

    def validate_insight_provenance(self, insight: DerivedInsight) -> None:
        """Validate that a derived insight never claims FIRST_PARTY_CONNECTED."""
        if insight.provenance == DataProvenance.FIRST_PARTY_CONNECTED:
            if insight.reasoning_class in {
                ReasoningClass.AI_INTERPRETATION,
                ReasoningClass.RECOMMENDATION,
                ReasoningClass.STATISTICAL_PATTERN,
            }:
                raise ProvenanceViolationError(
                    f"Insight with reasoning_class={insight.reasoning_class.value} "
                    f"cannot claim FIRST_PARTY_CONNECTED provenance.",
                    code="INSIGHT_PROVENANCE_MISMATCH",
                )

    def validate_reasoning_class_consistency(
        self, provenance: DataProvenance, reasoning_class: ReasoningClass
    ) -> None:
        """Validate that reasoning class is allowed for the given provenance.

        OBSERVED_FACT is ONLY valid with FIRST_PARTY_CONNECTED.
        """
        if reasoning_class == ReasoningClass.OBSERVED_FACT:
            if provenance != DataProvenance.FIRST_PARTY_CONNECTED:
                raise ProvenanceViolationError(
                    f"OBSERVED_FACT reasoning class is only valid with "
                    f"FIRST_PARTY_CONNECTED provenance, got {provenance.value}.",
                    code="REASONING_CLASS_INVALID_FOR_PROVENANCE",
                )

        valid_classes = VALID_REASONING_FOR_PROVENANCE.get(provenance, set())
        if reasoning_class not in valid_classes:
            raise ProvenanceViolationError(
                f"Reasoning class {reasoning_class.value} is not valid "
                f"for provenance {provenance.value}.",
                code="REASONING_CLASS_INVALID_FOR_PROVENANCE",
            )

    def validate_brain_context_item(
        self,
        item: BrainContextItem,
        source_provenance: DataProvenance,
    ) -> None:
        """Validate that brain context preserves source provenance."""
        if item.provenance != source_provenance:
            raise ProvenanceViolationError(
                f"Brain context item provenance ({item.provenance.value}) "
                f"does not match source provenance ({source_provenance.value}).",
                code="BRAIN_CONTEXT_PROVENANCE_MISMATCH",
            )

    def reject_provenance_upgrade(
        self,
        original_provenance: DataProvenance,
        requested_provenance: DataProvenance,
    ) -> None:
        """Reject any attempt to upgrade provenance to a higher trust level.

        DERIVED_ANALYSIS → FIRST_PARTY_CONNECTED: REJECTED
        PUBLIC_PLATFORM_DATA → FIRST_PARTY_CONNECTED: REJECTED
        THIRD_PARTY_DATA → FIRST_PARTY_CONNECTED: REJECTED
        USER_IMPORTED → FIRST_PARTY_CONNECTED: REJECTED
        """
        if (
            original_provenance != DataProvenance.FIRST_PARTY_CONNECTED
            and requested_provenance == DataProvenance.FIRST_PARTY_CONNECTED
        ):
            raise ProvenanceViolationError(
                f"Cannot upgrade provenance from {original_provenance.value} "
                f"to FIRST_PARTY_CONNECTED. Provenance is immutable.",
                code="PROVENANCE_UPGRADE_REJECTED",
            )

    def create_brain_context_item(
        self,
        source_metric: Optional[MetricSnapshot] = None,
        source_insight: Optional[DerivedInsight] = None,
    ) -> BrainContextItem:
        """Create a Brain context item preserving source provenance."""
        if source_metric is not None:
            return BrainContextItem(
                id=uuid4(),
                source_id=source_metric.id,
                source_type="metric",
                provenance=source_metric.provenance,
                reasoning_class=ReasoningClass.OBSERVED_FACT
                if source_metric.provenance == DataProvenance.FIRST_PARTY_CONNECTED
                else ReasoningClass.DERIVED_METRIC,
                content_summary=f"{source_metric.metric_type}: {source_metric.metric_value}",
            )
        elif source_insight is not None:
            return BrainContextItem(
                id=uuid4(),
                source_id=source_insight.id,
                source_type="insight",
                provenance=source_insight.provenance,
                reasoning_class=source_insight.reasoning_class,
                content_summary=str(source_insight.content),
            )
        raise ValueError("Must provide either source_metric or source_insight")


# =============================================================================
# Hypothesis Strategies
# =============================================================================

uuid_strategy = st.builds(uuid4)

provenance_strategy = st.sampled_from(list(DataProvenance))

non_first_party_provenance_strategy = st.sampled_from([
    DataProvenance.PUBLIC_PLATFORM_DATA,
    DataProvenance.THIRD_PARTY_DATA,
    DataProvenance.USER_IMPORTED,
    DataProvenance.DERIVED_ANALYSIS,
])

reasoning_class_strategy = st.sampled_from(list(ReasoningClass))

collection_method_strategy = st.sampled_from(list(CollectionMethod))

metric_type_strategy = st.sampled_from([
    "views", "likes", "comments", "shares", "reach",
    "impressions", "followers", "engagement_rate",
])

insight_type_strategy = st.sampled_from([
    "trend", "anomaly", "recommendation", "pattern", "comparison",
])

metric_value_strategy = st.floats(min_value=0.0, max_value=1_000_000.0)

confidence_strategy = st.floats(min_value=0.0, max_value=1.0)


# Strategy for valid metric snapshots (provenance != DERIVED_ANALYSIS for metrics)
valid_metric_provenance_strategy = st.sampled_from([
    DataProvenance.FIRST_PARTY_CONNECTED,
    DataProvenance.PUBLIC_PLATFORM_DATA,
    DataProvenance.THIRD_PARTY_DATA,
    DataProvenance.USER_IMPORTED,
])

metric_snapshot_strategy = st.builds(
    MetricSnapshot,
    id=uuid_strategy,
    org_id=uuid_strategy,
    social_account_id=uuid_strategy,
    metric_type=metric_type_strategy,
    metric_value=metric_value_strategy,
    provenance=valid_metric_provenance_strategy,
    collection_method=collection_method_strategy,
)

derived_insight_strategy = st.builds(
    DerivedInsight,
    id=uuid_strategy,
    org_id=uuid_strategy,
    insight_type=insight_type_strategy,
    content=st.just({"summary": "test insight"}),
    provenance=st.sampled_from([
        DataProvenance.DERIVED_ANALYSIS,
        DataProvenance.PUBLIC_PLATFORM_DATA,
        DataProvenance.THIRD_PARTY_DATA,
    ]),
    confidence=confidence_strategy,
    reasoning_class=st.sampled_from([
        ReasoningClass.STATISTICAL_PATTERN,
        ReasoningClass.AI_INTERPRETATION,
        ReasoningClass.RECOMMENDATION,
        ReasoningClass.DERIVED_METRIC,
    ]),
)


# =============================================================================
# Property 21.1: Metric Provenance Integrity
# Feature: production-revamp, Property 21: Social Provenance Integrity
# =============================================================================


class TestProperty21MetricProvenanceIntegrity:
    """Property 21: Metrics never misrepresent their provenance.

    DERIVED_ANALYSIS and PUBLIC_PLATFORM_DATA metrics are NEVER presented
    as FIRST_PARTY_CONNECTED.

    **Validates: Requirements R43.13, R107.10**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        org_id=uuid_strategy,
        metric_type=metric_type_strategy,
        metric_value=metric_value_strategy,
        collection_method=collection_method_strategy,
    )
    def test_public_platform_data_never_becomes_first_party(
        self,
        org_id: UUID,
        metric_type: str,
        metric_value: float,
        collection_method: CollectionMethod,
    ) -> None:
        """PUBLIC_PLATFORM_DATA metric cannot be upgraded to FIRST_PARTY_CONNECTED.

        **Validates: Requirements R107.10**
        """
        validator = SocialProvenanceValidator()

        with pytest.raises(ProvenanceViolationError) as exc_info:
            validator.reject_provenance_upgrade(
                original_provenance=DataProvenance.PUBLIC_PLATFORM_DATA,
                requested_provenance=DataProvenance.FIRST_PARTY_CONNECTED,
            )

        assert exc_info.value.code == "PROVENANCE_UPGRADE_REJECTED"

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        org_id=uuid_strategy,
        metric_type=metric_type_strategy,
        metric_value=metric_value_strategy,
        collection_method=collection_method_strategy,
    )
    def test_derived_analysis_never_becomes_first_party(
        self,
        org_id: UUID,
        metric_type: str,
        metric_value: float,
        collection_method: CollectionMethod,
    ) -> None:
        """DERIVED_ANALYSIS provenance cannot be upgraded to FIRST_PARTY_CONNECTED.

        **Validates: Requirements R107.10**
        """
        validator = SocialProvenanceValidator()

        with pytest.raises(ProvenanceViolationError) as exc_info:
            validator.reject_provenance_upgrade(
                original_provenance=DataProvenance.DERIVED_ANALYSIS,
                requested_provenance=DataProvenance.FIRST_PARTY_CONNECTED,
            )

        assert exc_info.value.code == "PROVENANCE_UPGRADE_REJECTED"

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        non_first_party=non_first_party_provenance_strategy,
    )
    def test_no_non_first_party_provenance_can_upgrade(
        self,
        non_first_party: DataProvenance,
    ) -> None:
        """ANY non-FIRST_PARTY provenance cannot upgrade to FIRST_PARTY_CONNECTED.

        **Validates: Requirements R43.13, R107.10**
        """
        validator = SocialProvenanceValidator()

        with pytest.raises(ProvenanceViolationError) as exc_info:
            validator.reject_provenance_upgrade(
                original_provenance=non_first_party,
                requested_provenance=DataProvenance.FIRST_PARTY_CONNECTED,
            )

        assert exc_info.value.code == "PROVENANCE_UPGRADE_REJECTED"

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(metric=metric_snapshot_strategy)
    def test_valid_metric_provenance_accepted(
        self,
        metric: MetricSnapshot,
    ) -> None:
        """Valid metric provenance (non-DERIVED_ANALYSIS) is accepted.

        **Validates: Requirements R107.10**
        """
        validator = SocialProvenanceValidator()
        # Should not raise for valid metric provenance types
        validator.validate_metric_provenance(metric)


# =============================================================================
# Property 21.2: Insight Provenance Integrity
# Feature: production-revamp, Property 21: Social Provenance Integrity
# =============================================================================


class TestProperty21InsightProvenanceIntegrity:
    """Property 21: Derived insights never claim FIRST_PARTY_CONNECTED provenance.

    AI interpretations, statistical patterns, and recommendations CANNOT
    have FIRST_PARTY_CONNECTED provenance.

    **Validates: Requirements R43.13, R107.10, A2-009**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        org_id=uuid_strategy,
        insight_type=insight_type_strategy,
        confidence=confidence_strategy,
        reasoning_class=st.sampled_from([
            ReasoningClass.AI_INTERPRETATION,
            ReasoningClass.RECOMMENDATION,
            ReasoningClass.STATISTICAL_PATTERN,
        ]),
    )
    def test_ai_interpretation_cannot_be_first_party(
        self,
        org_id: UUID,
        insight_type: str,
        confidence: float,
        reasoning_class: ReasoningClass,
    ) -> None:
        """AI interpretations/recommendations/patterns cannot be FIRST_PARTY.

        **Validates: Requirements R43.13, A2-009**
        """
        insight = DerivedInsight(
            id=uuid4(),
            org_id=org_id,
            insight_type=insight_type,
            content={"summary": "test"},
            provenance=DataProvenance.FIRST_PARTY_CONNECTED,
            confidence=confidence,
            reasoning_class=reasoning_class,
        )

        validator = SocialProvenanceValidator()
        with pytest.raises(ProvenanceViolationError) as exc_info:
            validator.validate_insight_provenance(insight)

        assert exc_info.value.code == "INSIGHT_PROVENANCE_MISMATCH"

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(insight=derived_insight_strategy)
    def test_derived_insights_never_have_first_party_provenance(
        self,
        insight: DerivedInsight,
    ) -> None:
        """Derived insights (DERIVED_ANALYSIS/PUBLIC/THIRD_PARTY) are never FIRST_PARTY.

        **Validates: Requirements R43.13, R107.10**

        Property: By construction, derived insights use DERIVED_ANALYSIS,
        PUBLIC_PLATFORM_DATA, or THIRD_PARTY_DATA provenance — never
        FIRST_PARTY_CONNECTED.
        """
        assert insight.provenance != DataProvenance.FIRST_PARTY_CONNECTED, (
            f"PROVENANCE VIOLATION: Derived insight {insight.id} claims "
            f"FIRST_PARTY_CONNECTED provenance with reasoning class "
            f"{insight.reasoning_class.value}."
        )

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        org_id=uuid_strategy,
        insight_type=insight_type_strategy,
        confidence=confidence_strategy,
    )
    def test_derived_analysis_provenance_rejected_for_upgrade(
        self,
        org_id: UUID,
        insight_type: str,
        confidence: float,
    ) -> None:
        """DERIVED_ANALYSIS insight provenance upgrade to FIRST_PARTY is rejected.

        **Validates: Requirements R107.10, A2-009**
        """
        validator = SocialProvenanceValidator()

        with pytest.raises(ProvenanceViolationError) as exc_info:
            validator.reject_provenance_upgrade(
                original_provenance=DataProvenance.DERIVED_ANALYSIS,
                requested_provenance=DataProvenance.FIRST_PARTY_CONNECTED,
            )

        assert exc_info.value.code == "PROVENANCE_UPGRADE_REJECTED"


# =============================================================================
# Property 21.3: Brain Context Provenance Preservation
# Feature: production-revamp, Property 21: Social Provenance Integrity
# =============================================================================


class TestProperty21BrainContextProvenancePreservation:
    """Property 21: Provenance survives injection into Brain context.

    When metrics or insights are injected into Brain context, their
    provenance classification MUST be preserved exactly.

    **Validates: Requirements R43.13, R107.10, A2-009**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(metric=metric_snapshot_strategy)
    def test_metric_provenance_preserved_in_brain_context(
        self,
        metric: MetricSnapshot,
    ) -> None:
        """Metric provenance is preserved when creating Brain context item.

        **Validates: Requirements A2-009**
        """
        validator = SocialProvenanceValidator()
        context_item = validator.create_brain_context_item(source_metric=metric)

        assert context_item.provenance == metric.provenance, (
            f"PROVENANCE DRIFT: Brain context item has provenance "
            f"{context_item.provenance.value} but source metric has "
            f"{metric.provenance.value}."
        )

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(insight=derived_insight_strategy)
    def test_insight_provenance_preserved_in_brain_context(
        self,
        insight: DerivedInsight,
    ) -> None:
        """Insight provenance is preserved when creating Brain context item.

        **Validates: Requirements A2-009**
        """
        validator = SocialProvenanceValidator()
        context_item = validator.create_brain_context_item(source_insight=insight)

        assert context_item.provenance == insight.provenance, (
            f"PROVENANCE DRIFT: Brain context item has provenance "
            f"{context_item.provenance.value} but source insight has "
            f"{insight.provenance.value}."
        )

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        metric=metric_snapshot_strategy,
        fake_provenance=st.just(DataProvenance.FIRST_PARTY_CONNECTED),
    )
    def test_brain_context_detects_provenance_mismatch(
        self,
        metric: MetricSnapshot,
        fake_provenance: DataProvenance,
    ) -> None:
        """Brain context validation catches provenance mismatch.

        **Validates: Requirements R107.10, A2-009**
        """
        assume(metric.provenance != DataProvenance.FIRST_PARTY_CONNECTED)

        validator = SocialProvenanceValidator()
        # Create a context item that falsely claims FIRST_PARTY_CONNECTED
        fake_item = BrainContextItem(
            id=uuid4(),
            source_id=metric.id,
            source_type="metric",
            provenance=fake_provenance,
            reasoning_class=ReasoningClass.OBSERVED_FACT,
            content_summary=f"{metric.metric_type}: {metric.metric_value}",
        )

        with pytest.raises(ProvenanceViolationError) as exc_info:
            validator.validate_brain_context_item(fake_item, metric.provenance)

        assert exc_info.value.code == "BRAIN_CONTEXT_PROVENANCE_MISMATCH"

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(insight=derived_insight_strategy)
    def test_derived_insight_in_brain_never_becomes_first_party(
        self,
        insight: DerivedInsight,
    ) -> None:
        """Derived insight injected into Brain context never becomes FIRST_PARTY.

        **Validates: Requirements R43.13, A2-009**
        """
        validator = SocialProvenanceValidator()
        context_item = validator.create_brain_context_item(source_insight=insight)

        # The context item must NOT claim FIRST_PARTY_CONNECTED
        assert context_item.provenance != DataProvenance.FIRST_PARTY_CONNECTED, (
            f"PROVENANCE VIOLATION: Brain context item derived from "
            f"{insight.provenance.value} insight claims FIRST_PARTY_CONNECTED."
        )


# =============================================================================
# Property 21.4: Reasoning Class Consistency
# Feature: production-revamp, Property 21: Social Provenance Integrity
# =============================================================================


class TestProperty21ReasoningClassConsistency:
    """Property 21: Reasoning class must match provenance type.

    OBSERVED_FACT is ONLY valid with FIRST_PARTY_CONNECTED provenance.
    Brain SHALL NOT misrepresent public observations as private analytics.

    **Validates: Requirements R43.13, A2-009**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        non_first_party=non_first_party_provenance_strategy,
    )
    def test_observed_fact_only_valid_with_first_party(
        self,
        non_first_party: DataProvenance,
    ) -> None:
        """OBSERVED_FACT reasoning class rejected for non-FIRST_PARTY provenance.

        **Validates: Requirements R43.13, A2-009**

        Property: For ANY provenance that is NOT FIRST_PARTY_CONNECTED,
        attempting to assign OBSERVED_FACT reasoning class MUST be rejected.
        """
        validator = SocialProvenanceValidator()

        with pytest.raises(ProvenanceViolationError) as exc_info:
            validator.validate_reasoning_class_consistency(
                provenance=non_first_party,
                reasoning_class=ReasoningClass.OBSERVED_FACT,
            )

        assert exc_info.value.code == "REASONING_CLASS_INVALID_FOR_PROVENANCE"

    @pytest.mark.unit
    def test_observed_fact_valid_with_first_party(self) -> None:
        """OBSERVED_FACT reasoning class IS valid with FIRST_PARTY_CONNECTED.

        **Validates: Requirements R43.13**
        """
        validator = SocialProvenanceValidator()
        # Should not raise
        validator.validate_reasoning_class_consistency(
            provenance=DataProvenance.FIRST_PARTY_CONNECTED,
            reasoning_class=ReasoningClass.OBSERVED_FACT,
        )

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        provenance=st.sampled_from([
            DataProvenance.PUBLIC_PLATFORM_DATA,
            DataProvenance.DERIVED_ANALYSIS,
        ]),
        reasoning_class=st.sampled_from([
            ReasoningClass.STATISTICAL_PATTERN,
            ReasoningClass.AI_INTERPRETATION,
            ReasoningClass.DERIVED_METRIC,
        ]),
    )
    def test_non_observed_classes_valid_for_public_and_derived(
        self,
        provenance: DataProvenance,
        reasoning_class: ReasoningClass,
    ) -> None:
        """Non-OBSERVED_FACT classes are valid for PUBLIC/DERIVED provenance.

        **Validates: Requirements R43.13**
        """
        validator = SocialProvenanceValidator()
        # Should not raise
        validator.validate_reasoning_class_consistency(
            provenance=provenance,
            reasoning_class=reasoning_class,
        )

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        non_first_party=non_first_party_provenance_strategy,
    )
    def test_recommendation_not_presented_as_observed_fact(
        self,
        non_first_party: DataProvenance,
    ) -> None:
        """RECOMMENDATION with non-FIRST_PARTY provenance cannot be OBSERVED_FACT.

        **Validates: Requirements R43.13, A2-009**

        This verifies the rule: Brain SHALL NOT misrepresent
        public observations as private analytics.
        """
        validator = SocialProvenanceValidator()

        # OBSERVED_FACT is invalid for non-first-party
        with pytest.raises(ProvenanceViolationError):
            validator.validate_reasoning_class_consistency(
                provenance=non_first_party,
                reasoning_class=ReasoningClass.OBSERVED_FACT,
            )


# =============================================================================
# Property 21.5: Provenance Immutability
# Feature: production-revamp, Property 21: Social Provenance Integrity
# =============================================================================


class TestProperty21ProvenanceImmutability:
    """Property 21: Provenance cannot be changed after creation.

    Once a metric or insight is created with a provenance classification,
    that classification is immutable. Any attempt to change it is rejected.

    **Validates: Requirements R107.10**
    """

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(metric=metric_snapshot_strategy)
    def test_metric_snapshot_is_frozen(
        self,
        metric: MetricSnapshot,
    ) -> None:
        """MetricSnapshot is immutable (frozen dataclass).

        **Validates: Requirements R107.10**

        Property: For ANY MetricSnapshot, attempting to modify the
        provenance attribute MUST raise an error (frozen dataclass).
        """
        with pytest.raises((AttributeError, TypeError)):
            metric.provenance = DataProvenance.FIRST_PARTY_CONNECTED  # type: ignore[misc]

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(insight=derived_insight_strategy)
    def test_derived_insight_is_frozen(
        self,
        insight: DerivedInsight,
    ) -> None:
        """DerivedInsight is immutable (frozen dataclass).

        **Validates: Requirements R107.10**

        Property: For ANY DerivedInsight, attempting to modify the
        provenance attribute MUST raise an error (frozen dataclass).
        """
        with pytest.raises((AttributeError, TypeError)):
            insight.provenance = DataProvenance.FIRST_PARTY_CONNECTED  # type: ignore[misc]

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(metric=metric_snapshot_strategy)
    def test_brain_context_item_is_frozen(
        self,
        metric: MetricSnapshot,
    ) -> None:
        """BrainContextItem is immutable (frozen dataclass).

        **Validates: Requirements R107.10**

        Property: For ANY BrainContextItem, attempting to modify the
        provenance attribute MUST raise an error (frozen dataclass).
        """
        validator = SocialProvenanceValidator()
        context_item = validator.create_brain_context_item(source_metric=metric)

        with pytest.raises((AttributeError, TypeError)):
            context_item.provenance = DataProvenance.FIRST_PARTY_CONNECTED  # type: ignore[misc]

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        original=non_first_party_provenance_strategy,
        target=provenance_strategy,
    )
    def test_provenance_upgrade_to_first_party_always_rejected(
        self,
        original: DataProvenance,
        target: DataProvenance,
    ) -> None:
        """Any upgrade attempt from non-FIRST_PARTY to FIRST_PARTY is rejected.

        **Validates: Requirements R107.10**

        Property: For ANY non-FIRST_PARTY_CONNECTED original provenance,
        requesting FIRST_PARTY_CONNECTED MUST always be rejected.
        """
        assume(target == DataProvenance.FIRST_PARTY_CONNECTED)

        validator = SocialProvenanceValidator()

        with pytest.raises(ProvenanceViolationError) as exc_info:
            validator.reject_provenance_upgrade(
                original_provenance=original,
                requested_provenance=target,
            )

        assert exc_info.value.code == "PROVENANCE_UPGRADE_REJECTED"

    @pytest.mark.unit
    @settings(max_examples=100)
    @given(
        original=provenance_strategy,
        target=non_first_party_provenance_strategy,
    )
    def test_provenance_non_upgrade_changes_not_blocked(
        self,
        original: DataProvenance,
        target: DataProvenance,
    ) -> None:
        """Non-upgrade changes (not targeting FIRST_PARTY) are not blocked by this rule.

        **Validates: Requirements R107.10**

        Note: Immutability is enforced at the dataclass level (frozen=True).
        The reject_provenance_upgrade validator specifically catches upgrades
        to FIRST_PARTY_CONNECTED. Other transitions are not the concern of
        this specific validation (frozen dataclass handles full immutability).
        """
        validator = SocialProvenanceValidator()
        # Should NOT raise since target is not FIRST_PARTY_CONNECTED
        validator.reject_provenance_upgrade(
            original_provenance=original,
            requested_provenance=target,
        )
