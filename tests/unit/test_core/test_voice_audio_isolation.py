"""Cross-tenant isolation tests for voice/audio — Story 018.

Tests verify:
  - Voice profile CRUD requires org_id
  - Voice samples require org_id
  - Audio clips require org_id
  - Cross-tenant profile access returns None (no existence leak)
  - org_id is injected on creates
  - org_id cannot be changed on updates
  - Deletes are scoped to tenant
  - Migration covers all tables with RLS
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
# Voice Profiles — org_id required
# =============================================================================


@pytest.mark.unit
class TestVoiceProfilesOrgRequired:
    """Verify voice profile operations reject missing org_id."""

    def test_list_requires_org_id(self):
        from backend.audio.repository import list_voice_profiles
        with pytest.raises(ValueError, match="org_id is required"):
            list_voice_profiles("")

    def test_get_requires_org_id(self):
        from backend.audio.repository import get_voice_profile
        with pytest.raises(ValueError, match="org_id is required"):
            get_voice_profile("profile-1", "")

    def test_create_requires_org_id(self):
        from backend.audio.repository import create_voice_profile
        with pytest.raises(ValueError, match="org_id is required"):
            create_voice_profile({"name": "test"}, "")

    def test_update_requires_org_id(self):
        from backend.audio.repository import update_voice_profile
        with pytest.raises(ValueError, match="org_id is required"):
            update_voice_profile("profile-1", {"name": "x"}, "")

    def test_delete_requires_org_id(self):
        from backend.audio.repository import delete_voice_profile
        with pytest.raises(ValueError, match="org_id is required"):
            delete_voice_profile("profile-1", "")


# =============================================================================
# Voice Samples — org_id required
# =============================================================================


@pytest.mark.unit
class TestVoiceSamplesOrgRequired:
    """Verify voice sample operations reject missing org_id."""

    def test_list_requires_org_id(self):
        from backend.audio.repository import list_voice_samples
        with pytest.raises(ValueError, match="org_id is required"):
            list_voice_samples("profile-1", "")

    def test_create_requires_org_id(self):
        from backend.audio.repository import create_voice_sample
        with pytest.raises(ValueError, match="org_id is required"):
            create_voice_sample({"voice_profile_id": "p1"}, "")


# =============================================================================
# Audio Clips — org_id required
# =============================================================================


@pytest.mark.unit
class TestAudioClipsOrgRequired:
    """Verify audio clip operations reject missing org_id."""

    def test_list_requires_org_id(self):
        from backend.audio.repository import list_audio_clips
        with pytest.raises(ValueError, match="org_id is required"):
            list_audio_clips("")

    def test_get_requires_org_id(self):
        from backend.audio.repository import get_audio_clip
        with pytest.raises(ValueError, match="org_id is required"):
            get_audio_clip("clip-1", "")

    def test_create_requires_org_id(self):
        from backend.audio.repository import create_audio_clip
        with pytest.raises(ValueError, match="org_id is required"):
            create_audio_clip({"text": "hello"}, "")

    def test_delete_requires_org_id(self):
        from backend.audio.repository import delete_audio_clip
        with pytest.raises(ValueError, match="org_id is required"):
            delete_audio_clip("clip-1", "")


# =============================================================================
# Cross-tenant isolation
# =============================================================================


@pytest.mark.unit
class TestVoiceCrossTenant:
    """Verify cross-tenant access is denied."""

    @patch("backend.audio.repository._db")
    def test_get_profile_cross_tenant_returns_none(self, mock_db_fn):
        """Fetching another org's voice profile returns None."""
        from backend.audio.repository import get_voice_profile
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        result = get_voice_profile("other-tenant-profile", TENANT_A)
        assert result is None

    @patch("backend.audio.repository._db")
    def test_delete_cross_tenant_returns_false(self, mock_db_fn):
        """Deleting another org's profile returns False."""
        from backend.audio.repository import delete_voice_profile
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        result = delete_voice_profile("other-tenant-profile", TENANT_A)
        assert result is False

    @patch("backend.audio.repository._db")
    def test_update_cross_tenant_returns_none(self, mock_db_fn):
        """Updating another org's profile returns None."""
        from backend.audio.repository import update_voice_profile
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([])

        result = update_voice_profile("other-tenant-profile", {"name": "hacked"}, TENANT_A)
        assert result is None


# =============================================================================
# org_id injection and immutability
# =============================================================================


@pytest.mark.unit
class TestVoiceOrgInjection:
    """Verify org_id is injected on create and stripped from update."""

    @patch("backend.audio.repository._db")
    def test_create_profile_injects_org_id(self, mock_db_fn):
        """Create always injects org_id from context."""
        from backend.audio.repository import create_voice_profile
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_execute([{"id": "new"}])

        create_voice_profile({"name": "Voice", "org_id": TENANT_B}, TENANT_A)
        call_data = mock_db.table.return_value.insert.call_args[0][0]
        assert call_data["org_id"] == TENANT_A  # Context wins

    @patch("backend.audio.repository._db")
    def test_update_strips_org_id(self, mock_db_fn):
        """Update prevents org_id reassignment."""
        from backend.audio.repository import update_voice_profile
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_execute([{"id": "p1"}])

        update_voice_profile("p1", {"name": "New", "org_id": TENANT_B}, TENANT_A)
        call_data = mock_db.table.return_value.update.call_args[0][0]
        assert "org_id" not in call_data

    @patch("backend.audio.repository._db")
    def test_create_clip_injects_org_id(self, mock_db_fn):
        """Audio clip creation injects org_id."""
        from backend.audio.repository import create_audio_clip
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_execute([{"id": "c1"}])

        create_audio_clip({"text": "hello"}, TENANT_A)
        call_data = mock_db.table.return_value.insert.call_args[0][0]
        assert call_data["org_id"] == TENANT_A

    @patch("backend.audio.repository._db")
    def test_create_sample_injects_org_id(self, mock_db_fn):
        """Voice sample creation injects org_id."""
        from backend.audio.repository import create_voice_sample
        mock_db = MagicMock()
        mock_db_fn.return_value = mock_db
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_execute([{"id": "s1"}])

        create_voice_sample({"voice_profile_id": "p1", "file_url": "/a.wav"}, TENANT_A)
        call_data = mock_db.table.return_value.insert.call_args[0][0]
        assert call_data["org_id"] == TENANT_A


# =============================================================================
# Migration file verification
# =============================================================================


@pytest.mark.unit
class TestVoiceMigrationComplete:
    """Verify migration covers all tables."""

    def test_rls_enabled_on_all_tables(self):
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        path = os.path.join(repo_root, "docs", "sql", "034_voice_audio_rls.sql")
        with open(path) as f:
            sql = f.read()
        for table in ["voice_profiles", "voice_samples", "audio_clips"]:
            assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql

    def test_is_transactional(self):
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        path = os.path.join(repo_root, "docs", "sql", "034_voice_audio_rls.sql")
        with open(path) as f:
            sql = f.read()
        assert "BEGIN;" in sql
        assert "COMMIT;" in sql
