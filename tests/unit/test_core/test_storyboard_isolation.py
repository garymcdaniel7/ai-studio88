"""Cross-tenant isolation and resume/recovery tests for storyboards — Story 020.

Tests verify:
  - Storyboard CRUD requires org_id
  - Cross-tenant storyboard access returns None
  - org_id injected on create, stripped from update
  - Shot status updates are tenant-scoped
  - Story engine (universes, episodes, scenes, shots) requires org_id
  - Resumability: get_storyboard returns full persisted state
  - Migration covers all required tables
"""

from unittest.mock import MagicMock, patch

import pytest

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "org-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def mock_execute(data=None):
    result = MagicMock()
    result.data = data if data is not None else []
    return result


# =============================================================================
# Storyboard CRUD — org_id required
# =============================================================================


@pytest.mark.unit
class TestStoryboardOrgRequired:
    """Verify storyboard operations reject missing org_id."""

    def test_list_requires_org_id(self):
        from backend.storyboard_repository import list_storyboards
        with pytest.raises(ValueError, match="org_id is required"):
            list_storyboards("")

    def test_get_requires_org_id(self):
        from backend.storyboard_repository import get_storyboard
        with pytest.raises(ValueError, match="org_id is required"):
            get_storyboard("sb-1", "")

    def test_create_requires_org_id(self):
        from backend.storyboard_repository import create_storyboard
        with pytest.raises(ValueError, match="org_id is required"):
            create_storyboard({"name": "test"}, "")

    def test_update_requires_org_id(self):
        from backend.storyboard_repository import update_storyboard
        with pytest.raises(ValueError, match="org_id is required"):
            update_storyboard("sb-1", {"name": "x"}, "")

    def test_delete_requires_org_id(self):
        from backend.storyboard_repository import delete_storyboard
        with pytest.raises(ValueError, match="org_id is required"):
            delete_storyboard("sb-1", "")

    def test_update_shot_status_requires_org_id(self):
        from backend.storyboard_repository import update_shot_status
        with pytest.raises(ValueError, match="org_id is required"):
            update_shot_status("sb-1", "shot-1", "", "completed")


# =============================================================================
# Cross-tenant denial
# =============================================================================


@pytest.mark.unit
class TestStoryboardCrossTenant:
    """Verify cross-tenant access is denied without data leakage."""

    @patch("backend.storyboard_repository._db")
    def test_get_cross_tenant_returns_none(self, mock_db_fn):
        from backend.storyboard_repository import get_storyboard
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])
        
        result = get_storyboard("other-tenant-sb", TENANT_A)
        assert result is None

    @patch("backend.storyboard_repository._db")
    def test_delete_cross_tenant_returns_false(self, mock_db_fn):
        from backend.storyboard_repository import delete_storyboard
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])
        
        result = delete_storyboard("other-tenant-sb", TENANT_A)
        assert result is False

    @patch("backend.storyboard_repository._db")
    def test_update_cross_tenant_returns_none(self, mock_db_fn):
        from backend.storyboard_repository import update_storyboard
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])
        
        result = update_storyboard("other-sb", {"name": "hacked"}, TENANT_A)
        assert result is None


# =============================================================================
# org_id injection and immutability
# =============================================================================


@pytest.mark.unit
class TestStoryboardOrgInjection:
    """Verify org_id is injected on create and stripped from update."""

    @patch("backend.storyboard_repository._db")
    def test_create_injects_org_id(self, mock_db_fn):
        from backend.storyboard_repository import create_storyboard
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_execute([{"id": "new"}])

        create_storyboard({"name": "Test", "org_id": TENANT_B}, TENANT_A)
        call_data = mock_db.table.return_value.insert.call_args[0][0]
        assert call_data["org_id"] == TENANT_A  # Context wins

    @patch("backend.storyboard_repository._db")
    def test_update_strips_org_id(self, mock_db_fn):
        from backend.storyboard_repository import update_storyboard
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([{"id": "sb-1"}])

        update_storyboard("sb-1", {"name": "New", "org_id": TENANT_B}, TENANT_A)
        call_data = mock_db.table.return_value.update.call_args[0][0]
        assert "org_id" not in call_data


# =============================================================================
# Resumability — server state is authoritative
# =============================================================================


@pytest.mark.unit
class TestStoryboardResume:
    """Verify storyboards are resumable from server state."""

    @patch("backend.storyboard_repository._db")
    def test_get_returns_full_shot_state(self, mock_db_fn):
        """Get storyboard returns complete persisted state for resume."""
        from backend.storyboard_repository import get_storyboard
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        
        persisted = {
            "id": "sb-1",
            "org_id": TENANT_A,
            "name": "Tokyo Walk",
            "status": "generating",
            "shots": [
                {"id": "s1", "status": "completed", "image_url": "/img/1.webp"},
                {"id": "s2", "status": "generating", "job_id": "job-123"},
                {"id": "s3", "status": "pending"},
            ],
            "completed_shots": 1,
            "total_shots": 3,
        }
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([persisted])

        result = get_storyboard("sb-1", TENANT_A)
        assert result is not None
        assert result["status"] == "generating"
        assert len(result["shots"]) == 3
        assert result["shots"][0]["status"] == "completed"
        assert result["shots"][1]["job_id"] == "job-123"
        assert result["completed_shots"] == 1

    @patch("backend.storyboard_repository._db")
    def test_shot_status_update_persists(self, mock_db_fn):
        """Shot status updates are persisted (not just in browser state)."""
        from backend.storyboard_repository import update_shot_status
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db

        # First call: get_storyboard returns current state
        storyboard = {
            "id": "sb-1", "org_id": TENANT_A,
            "shots": [
                {"id": "s1", "status": "generating"},
                {"id": "s2", "status": "pending"},
            ],
        }
        # get_storyboard call
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([storyboard])
        # update call
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([{"id": "sb-1"}])

        update_shot_status("sb-1", "s1", TENANT_A, "completed", image_url="/out/1.webp")

        # Verify the update was called with new shot state
        update_call = mock_db.table.return_value.update.call_args[0][0]
        assert update_call["shots"][0]["status"] == "completed"
        assert update_call["shots"][0]["image_url"] == "/out/1.webp"


# =============================================================================
# Story Engine — org_id required
# =============================================================================


@pytest.mark.unit
class TestStoryEngineOrgRequired:
    """Verify story engine operations reject missing org_id."""

    def test_list_universes_requires_org_id(self):
        from backend.storyboard_repository import list_universes
        with pytest.raises(ValueError, match="org_id is required"):
            list_universes("")

    def test_get_universe_requires_org_id(self):
        from backend.storyboard_repository import get_universe
        with pytest.raises(ValueError, match="org_id is required"):
            get_universe("u-1", "")

    def test_create_universe_requires_org_id(self):
        from backend.storyboard_repository import create_universe
        with pytest.raises(ValueError, match="org_id is required"):
            create_universe({"name": "test"}, "")

    def test_create_episode_requires_org_id(self):
        from backend.storyboard_repository import create_episode
        with pytest.raises(ValueError, match="org_id is required"):
            create_episode({"universe_id": "u1"}, "")

    def test_create_scene_requires_org_id(self):
        from backend.storyboard_repository import create_scene
        with pytest.raises(ValueError, match="org_id is required"):
            create_scene({"episode_id": "e1"}, "")

    def test_create_shot_requires_org_id(self):
        from backend.storyboard_repository import create_shot
        with pytest.raises(ValueError, match="org_id is required"):
            create_shot({"scene_id": "sc1"}, "")

    def test_create_shots_bulk_requires_org_id(self):
        from backend.storyboard_repository import create_shots_bulk
        with pytest.raises(ValueError, match="org_id is required"):
            create_shots_bulk([{"scene_id": "sc1"}], "")

    def test_list_episodes_requires_org_id(self):
        from backend.storyboard_repository import list_episodes
        with pytest.raises(ValueError, match="org_id is required"):
            list_episodes("u-1", "")

    def test_list_scenes_requires_org_id(self):
        from backend.storyboard_repository import list_scenes
        with pytest.raises(ValueError, match="org_id is required"):
            list_scenes("e-1", "")

    def test_list_shots_requires_org_id(self):
        from backend.storyboard_repository import list_shots
        with pytest.raises(ValueError, match="org_id is required"):
            list_shots("sc-1", "")


# =============================================================================
# Migration verification
# =============================================================================


@pytest.mark.unit
class TestStoryboardMigration:
    """Verify the migration covers all required tables."""

    def test_rls_on_all_tables(self):
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        path = os.path.join(repo_root, "docs", "sql", "035_storyboard_production_rls.sql")
        with open(path) as f:
            sql = f.read()
        for table in ["storyboard_panels", "universes", "episodes", "scenes", "shots", "characters", "story_memory"]:
            assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql

    def test_org_id_added_to_story_engine(self):
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        path = os.path.join(repo_root, "docs", "sql", "035_storyboard_production_rls.sql")
        with open(path) as f:
            sql = f.read()
        for table in ["universes", "episodes", "scenes", "shots", "characters", "story_memory"]:
            assert f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS org_id UUID" in sql

    def test_is_transactional(self):
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        path = os.path.join(repo_root, "docs", "sql", "035_storyboard_production_rls.sql")
        with open(path) as f:
            sql = f.read()
        assert "BEGIN;" in sql
        assert "COMMIT;" in sql
