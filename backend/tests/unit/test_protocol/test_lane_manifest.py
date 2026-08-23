"""Invariant tests for the repository lane manifest."""

from __future__ import annotations

import json
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = REPOSITORY_ROOT / "LANES.json"
FRONTEND_APP_ROOT = REPOSITORY_ROOT / "frontend" / "src" / "app"

REQUIRED_FRONTEND_LANES: dict[str, set[str]] = {
    "talent": {"src/app/talent/**", "src/app/training/**"},
    "creation": {
        "src/app/create/**",
        "src/app/story/**",
        "src/app/production/**",
    },
    "post": {
        "src/app/editor/**",
        "src/app/assets/**",
        "src/app/projects/**",
    },
    "platform": {
        "src/app/admin/**",
        "src/app/settings/**",
        "src/app/models/**",
        "src/app/workflows/**",
    },
    "growth": {
        "src/app/page.tsx",
        "src/app/login/**",
        "src/app/analytics/**",
        "src/app/publish/**",
        "src/app/pricing/**",
    },
    "brain": {"src/app/brain/**"},
}


def _load_manifest() -> dict[str, Any]:
    """Load the checked-in lane manifest."""
    return json.loads(MANIFEST_PATH.read_text())


def _frontend_lanes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Return frontend lanes, excluding the backend lane."""
    return [lane for lane in manifest["lanes"] if lane["id"] != "backend"]


def test_required_lane_paths_are_present() -> None:
    """The manifest retains every path assignment required by the protocol."""
    lanes_by_id = {lane["id"]: lane for lane in _frontend_lanes(_load_manifest())}

    assert set(lanes_by_id) == set(REQUIRED_FRONTEND_LANES)
    for lane_id, required_paths in REQUIRED_FRONTEND_LANES.items():
        assert required_paths <= set(lanes_by_id[lane_id]["owned_paths"])
        assert lanes_by_id[lane_id]["executor"] == "subagent"


def test_every_frontend_app_file_belongs_to_exactly_one_lane() -> None:
    """Every current app file is covered once, with no overlapping ownership."""
    frontend_lanes = _frontend_lanes(_load_manifest())
    app_files = sorted(
        path.relative_to(FRONTEND_APP_ROOT).as_posix()
        for path in FRONTEND_APP_ROOT.rglob("*")
        if path.is_file()
    )

    unmatched: list[str] = []
    multiply_owned: dict[str, list[str]] = {}
    for app_file in app_files:
        owners = [
            lane["id"]
            for lane in frontend_lanes
            if any(fnmatchcase(f"src/app/{app_file}", pattern) for pattern in lane["owned_paths"])
        ]
        if not owners:
            unmatched.append(app_file)
        if len(owners) > 1:
            multiply_owned[app_file] = owners

    assert not unmatched
    assert not multiply_owned


def test_backend_lane_owns_backend_tree() -> None:
    """The Kiro-owned backend lane is explicit and correctly scoped."""
    manifest = _load_manifest()
    backend_lanes = [lane for lane in manifest["lanes"] if lane["id"] == "backend"]

    assert len(backend_lanes) == 1
    assert backend_lanes[0]["owned_paths"] == ["backend/**"]
    assert backend_lanes[0]["executor"] == "kiro"
