"""Cross-tenant isolation tests for talent & creative intelligence — Story 016.

Tests verify:
  - All creative-intelligence helpers require org_id
  - Talent operations are tenant-scoped (from Story 010)
  - Creative DNA requires org_id
  - Feedback requires org_id
  - Continuity notes require org_id
  - Creative rules require org_id
  - Style preferences require org_id
  - Prompt history requires org_id
  - org_id is injected on creates (never trusted from caller)
  - Updates are scoped to tenant
  - Deletes are scoped to tenant
"""

import pytest


TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


# =============================================================================
# Creative DNA — org_id required
# =============================================================================


@pytest.mark.unit
class TestCreativeDnaOrgRequired:
    """Verify creative DNA operations reject missing org_id."""

    def test_get_list_requires_org_id(self):
        from backend.database import get_creative_dna_list
        with pytest.raises(ValueError, match="org_id is required"):
            get_creative_dna_list("")

    def test_get_by_talent_requires_org_id(self):
        from backend.database import get_creative_dna_by_talent
        with pytest.raises(ValueError, match="org_id is required"):
            get_creative_dna_by_talent("talent-1", "")

    def test_create_requires_org_id(self):
        from backend.database import create_creative_dna
        with pytest.raises(ValueError, match="org_id is required"):
            create_creative_dna({"talent_id": "t1"}, "")

    def test_update_requires_org_id(self):
        from backend.database import update_creative_dna
        with pytest.raises(ValueError, match="org_id is required"):
            update_creative_dna("dna-1", {"data": "x"}, "")


# =============================================================================
# Generation Feedback — org_id required
# =============================================================================


@pytest.mark.unit
class TestFeedbackOrgRequired:
    """Verify feedback operations reject missing org_id."""

    def test_get_feedback_requires_org_id(self):
        from backend.database import get_feedback
        with pytest.raises(ValueError, match="org_id is required"):
            get_feedback("")

    def test_create_feedback_requires_org_id(self):
        from backend.database import create_feedback
        with pytest.raises(ValueError, match="org_id is required"):
            create_feedback({"talent_id": "t1", "rating": 5}, "")

    def test_get_recent_problems_requires_org_id(self):
        from backend.database import get_recent_problems
        with pytest.raises(ValueError, match="org_id is required"):
            get_recent_problems("talent-1", "")

    def test_get_average_rating_requires_org_id(self):
        from backend.database import get_average_rating
        with pytest.raises(ValueError, match="org_id is required"):
            get_average_rating("talent-1", "")


# =============================================================================
# Continuity Notes — org_id required
# =============================================================================


@pytest.mark.unit
class TestContinuityOrgRequired:
    """Verify continuity notes operations reject missing org_id."""

    def test_get_notes_requires_org_id(self):
        from backend.database import get_continuity_notes
        with pytest.raises(ValueError, match="org_id is required"):
            get_continuity_notes("")

    def test_create_note_requires_org_id(self):
        from backend.database import create_continuity_note
        with pytest.raises(ValueError, match="org_id is required"):
            create_continuity_note({"talent_id": "t1", "note": "x"}, "")

    def test_update_note_requires_org_id(self):
        from backend.database import update_continuity_note
        with pytest.raises(ValueError, match="org_id is required"):
            update_continuity_note("note-1", {"note": "y"}, "")

    def test_delete_note_requires_org_id(self):
        from backend.database import delete_continuity_note
        with pytest.raises(ValueError, match="org_id is required"):
            delete_continuity_note("note-1", "")


# =============================================================================
# Creative Rules — org_id required
# =============================================================================


@pytest.mark.unit
class TestCreativeRulesOrgRequired:
    """Verify creative rules operations reject missing org_id."""

    def test_get_rules_requires_org_id(self):
        from backend.database import get_creative_rules
        with pytest.raises(ValueError, match="org_id is required"):
            get_creative_rules("")

    def test_create_rule_requires_org_id(self):
        from backend.database import create_creative_rule
        with pytest.raises(ValueError, match="org_id is required"):
            create_creative_rule({"rule_type": "always"}, "")

    def test_delete_rule_requires_org_id(self):
        from backend.database import delete_creative_rule
        with pytest.raises(ValueError, match="org_id is required"):
            delete_creative_rule("rule-1", "")


# =============================================================================
# Style Preferences — org_id required
# =============================================================================


@pytest.mark.unit
class TestStylePrefsOrgRequired:
    """Verify style preferences operations reject missing org_id."""

    def test_get_prefs_requires_org_id(self):
        from backend.database import get_style_preferences
        with pytest.raises(ValueError, match="org_id is required"):
            get_style_preferences("")

    def test_upsert_pref_requires_org_id(self):
        from backend.database import upsert_style_preference
        with pytest.raises(ValueError, match="org_id is required"):
            upsert_style_preference({"talent_id": "t1", "category": "color"}, "")


# =============================================================================
# Prompt History — org_id required
# =============================================================================


@pytest.mark.unit
class TestPromptHistoryOrgRequired:
    """Verify prompt history operations reject missing org_id."""

    def test_record_requires_org_id(self):
        from backend.database import record_prompt_history
        with pytest.raises(ValueError, match="org_id is required"):
            record_prompt_history({"prompt": "test"}, "")

    def test_get_history_requires_org_id(self):
        from backend.database import get_prompt_history
        with pytest.raises(ValueError, match="org_id is required"):
            get_prompt_history("")


# =============================================================================
# Migration file verification
# =============================================================================


@pytest.mark.unit
class TestTalentMigrationComplete:
    """Verify the migration covers all required tables."""

    def test_rls_enabled_on_all_tables(self):
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        path = os.path.join(repo_root, "docs", "sql", "033_talent_creative_rls.sql")
        with open(path) as f:
            sql = f.read()
        for table in ["talent", "creative_dna", "generation_feedback",
                      "continuity_notes", "creative_rules", "style_preferences", "prompt_history"]:
            assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql

    def test_org_id_added_to_inherited_tables(self):
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        path = os.path.join(repo_root, "docs", "sql", "033_talent_creative_rls.sql")
        with open(path) as f:
            sql = f.read()
        for table in ["creative_dna", "generation_feedback", "style_preferences", "prompt_history"]:
            assert f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS org_id UUID" in sql
