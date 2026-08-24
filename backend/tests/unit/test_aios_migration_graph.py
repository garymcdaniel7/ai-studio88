"""Additional graph assertion for the AIOS Studio Craft revisions."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory


@pytest.mark.unit
def test_aios_craft_revisions_form_one_chain() -> None:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    revisions = [scripts.get_revision(revision) for revision in ("20260827001", "20260828001", "20260829001")]
    assert revisions[0].down_revision == "20260826001"
    assert revisions[1].down_revision == "20260827001"
    assert revisions[2].down_revision == "20260828001"
    assert scripts.get_current_head() == "20260830001"
