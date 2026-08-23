"""Runtime import smoke tests for local/deployment entrypoints."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_backend_main_imports_from_repo_root_without_pythonpath() -> None:
    """The documented `uvicorn backend.main:app` entrypoint imports from repo root."""
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from backend.main import app; print(app.title)",
        ],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "AI Studio API" in result.stdout
