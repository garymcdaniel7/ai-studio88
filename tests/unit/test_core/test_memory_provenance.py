"""Memory provenance and truthful labeling tests — Story 044.

Tests prove:
  - Unstored claims are NEVER presented as memory
  - Empty state is truthful ("no memories" not fabricated defaults)
  - Inferred content is visibly distinct from confirmed facts
  - Prompt assembly separates confirmed from observed
  - Low-confidence items excluded from prompts
  - System/default items never injected into prompts
  - Provenance labels are correct for each source type
  - Fabricated _production_memory defaults are NOT returned
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.brain.memory_provenance import (
    LabeledMemory,
    ProvenanceLabel,
    assemble_memory_context,
    get_empty_memory_state,
    get_labeled_memories,
    get_production_memory_truthful,
)

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_A = "user-aaaa"


# =============================================================================
# Truthful Empty State
# =============================================================================


@pytest.mark.unit
class TestTruthfulEmptyState:
    """Verify empty memory produces truthful state, not fabricated defaults."""

    def test_empty_state_has_no_items(self):
        """Empty state returns zero items (not hardcoded defaults)."""
        state = get_empty_memory_state()
        assert state["status"] == "empty"
        assert state["items"] == []
        assert state["total"] == 0

    def test_empty_state_has_truthful_message(self):
        """Empty state message says 'no memories' not fake data."""
        state = get_empty_memory_state()
        assert "No memories" in state["message"]
        assert "learn" in state["message"].lower()

    @patch("backend.memory_service.recall")
    def test_no_context_returns_empty(self, mock_recall):
        """Missing org/user returns empty (never fabricates)."""
        result = get_labeled_memories("", "")
        assert result == []
        mock_recall.assert_not_called()

    @patch("backend.memory_service.recall")
    def test_recall_failure_returns_empty(self, mock_recall):
        """Database failure returns empty (never fabricates)."""
        mock_recall.side_effect = RuntimeError("DB down")
        result = get_labeled_memories(TENANT_A, USER_A)
        assert result == []


# =============================================================================
# Provenance Labeling
# =============================================================================


@pytest.mark.unit
class TestProvenanceLabeling:
    """Verify provenance labels are correct for each source type."""

    @patch("backend.memory_service.recall")
    def test_user_confirmed_labeled_correctly(self, mock_recall):
        mock_recall.return_value = [{
            "category": "preferences", "key": "theme", "value": {"v": "dark"},
            "provenance": "user_confirmed", "confidence": 0.95,
            "namespace": "workspace_shared", "user_id": USER_A,
        }]
        memories = get_labeled_memories(TENANT_A, USER_A)
        assert len(memories) == 1
        assert memories[0].label == ProvenanceLabel.CONFIRMED
        assert memories[0].is_confirmed is True
        assert memories[0].source_description == "You told me this"

    @patch("backend.memory_service.recall")
    def test_inferred_labeled_as_observed(self, mock_recall):
        mock_recall.return_value = [{
            "category": "style", "key": "lighting", "value": {"v": "golden_hour"},
            "provenance": "inferred", "confidence": 0.7,
            "namespace": "workspace_shared", "user_id": USER_A,
        }]
        memories = get_labeled_memories(TENANT_A, USER_A)
        assert len(memories) == 1
        assert memories[0].label == ProvenanceLabel.OBSERVED
        assert memories[0].is_confirmed is False
        assert "Observed" in memories[0].source_description

    @patch("backend.memory_service.recall")
    def test_system_labeled_as_default(self, mock_recall):
        mock_recall.return_value = [{
            "category": "config", "key": "model", "value": {"v": "flux-dev"},
            "provenance": "system", "confidence": 1.0,
            "namespace": "workspace_shared", "user_id": USER_A,
        }]
        memories = get_labeled_memories(TENANT_A, USER_A)
        assert len(memories) == 1
        assert memories[0].label == ProvenanceLabel.DEFAULT
        assert memories[0].can_be_used_in_prompts is False  # System items excluded


# =============================================================================
# Prompt Assembly — Confirmed vs Inferred Distinction
# =============================================================================


@pytest.mark.unit
class TestPromptAssembly:
    """Verify prompt assembly distinguishes confirmed from observed."""

    @patch("backend.memory_service.recall")
    def test_confirmed_in_known_facts_section(self, mock_recall):
        mock_recall.return_value = [{
            "category": "preferences", "key": "name", "value": {"v": "Gary"},
            "provenance": "user_confirmed", "confidence": 0.95,
            "namespace": "workspace_shared", "user_id": USER_A,
        }]
        context = assemble_memory_context(TENANT_A, USER_A)
        assert "Known facts" in context
        assert "name: Gary" in context

    @patch("backend.memory_service.recall")
    def test_observed_in_separate_section(self, mock_recall):
        mock_recall.return_value = [{
            "category": "style", "key": "lighting", "value": {"v": "warm"},
            "provenance": "inferred", "confidence": 0.8,
            "namespace": "workspace_shared", "user_id": USER_A,
        }]
        context = assemble_memory_context(TENANT_A, USER_A)
        assert "Observed preferences" in context
        assert "may not be current" in context
        assert "confidence:" in context.lower()

    @patch("backend.memory_service.recall")
    def test_empty_memory_produces_empty_context(self, mock_recall):
        """No reliable memory → empty string (don't inject anything)."""
        mock_recall.return_value = []
        context = assemble_memory_context(TENANT_A, USER_A)
        assert context == ""

    @patch("backend.memory_service.recall")
    def test_low_confidence_excluded_from_prompts(self, mock_recall):
        mock_recall.return_value = [{
            "category": "style", "key": "color", "value": {"v": "blue"},
            "provenance": "inferred", "confidence": 0.3,  # Below 0.7 threshold
            "namespace": "workspace_shared", "user_id": USER_A,
        }]
        context = assemble_memory_context(TENANT_A, USER_A)
        assert context == ""  # Excluded — too low confidence

    @patch("backend.memory_service.recall")
    def test_system_defaults_never_in_prompts(self, mock_recall):
        mock_recall.return_value = [{
            "category": "config", "key": "model", "value": {"v": "flux-dev"},
            "provenance": "system", "confidence": 1.0,
            "namespace": "workspace_shared", "user_id": USER_A,
        }]
        context = assemble_memory_context(TENANT_A, USER_A)
        assert context == ""  # System defaults excluded from prompts


# =============================================================================
# Production Memory API — Truthful Replacement
# =============================================================================


@pytest.mark.unit
class TestProductionMemoryTruthful:
    """Verify the new API never returns fabricated defaults."""

    @patch("backend.memory_service.recall")
    def test_empty_returns_truthful_state(self, mock_recall):
        mock_recall.return_value = []
        result = get_production_memory_truthful(TENANT_A, USER_A)
        assert result["status"] == "empty"
        assert result["total"] == 0
        assert "dolly_in" not in str(result)
        assert "golden_hour" not in str(result)
        assert "7pm EST" not in str(result)

    @patch("backend.memory_service.recall")
    def test_with_memories_returns_labeled(self, mock_recall):
        mock_recall.return_value = [
            {"category": "pref", "key": "model", "value": {"v": "flux-dev"},
             "provenance": "user_confirmed", "confidence": 0.9,
             "namespace": "workspace_shared", "user_id": USER_A},
        ]
        result = get_production_memory_truthful(TENANT_A, USER_A)
        assert result["status"] == "active"
        assert result["total"] == 1
        assert result["items"][0]["provenance"] == "confirmed"
        assert result["items"][0]["confirmed"] is True


# =============================================================================
# No Fabricated Data — Regression Guard
# =============================================================================


@pytest.mark.unit
class TestNoFabricatedData:
    """Verify the old hardcoded _production_memory defaults are not returned."""

    FABRICATED_VALUES = [
        "dolly_in", "slow_pan", "golden_hour", "warm_cinematic",
        "cinematic", "7pm EST", "instagram", "tiktok",
    ]

    @patch("backend.memory_service.recall")
    def test_no_fabricated_defaults_in_empty_state(self, mock_recall):
        """Empty memory NEVER contains the old hardcoded defaults."""
        mock_recall.return_value = []
        result = get_production_memory_truthful(TENANT_A, USER_A)
        result_str = str(result)
        for fake_value in self.FABRICATED_VALUES:
            assert fake_value not in result_str, (
                f"Fabricated default '{fake_value}' found in empty memory state!"
            )

    @patch("backend.memory_service.recall")
    def test_no_fabricated_defaults_in_labeled_memories(self, mock_recall):
        """labeled_memories never returns fabricated items."""
        mock_recall.return_value = []
        memories = get_labeled_memories(TENANT_A, USER_A)
        assert memories == []  # Truthful empty — no fabrication

    def test_old_get_production_memory_has_fabricated_data(self):
        """REGRESSION: Prove the OLD function still has fabricated data (to be removed)."""
        from backend.brain.memory import get_production_memory
        old_result = get_production_memory()
        # The old function STILL has fabricated defaults (not yet removed)
        assert "dolly_in" in str(old_result) or "golden_hour" in str(old_result)


# =============================================================================
# LabeledMemory Display Contract
# =============================================================================


@pytest.mark.unit
class TestLabeledMemoryDisplay:
    """Verify display dict includes provenance information."""

    def test_display_dict_has_provenance(self):
        m = LabeledMemory(
            category="pref", key="theme", value="dark",
            label=ProvenanceLabel.CONFIRMED, confidence=0.95,
            source_description="You told me this",
            is_confirmed=True, can_be_used_in_prompts=True,
        )
        d = m.to_display_dict()
        assert d["provenance"] == "confirmed"
        assert d["confidence"] == 0.95
        assert d["source"] == "You told me this"
        assert d["confirmed"] is True

    def test_observed_display_shows_not_confirmed(self):
        m = LabeledMemory(
            category="style", key="color", value="blue",
            label=ProvenanceLabel.OBSERVED, confidence=0.6,
            source_description="Observed from your activity",
            is_confirmed=False, can_be_used_in_prompts=False,
        )
        d = m.to_display_dict()
        assert d["provenance"] == "observed"
        assert d["confirmed"] is False
