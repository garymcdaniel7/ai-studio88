"""Integrity checks for the complete Alembic revision graph."""

from __future__ import annotations

import ast
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[3] / "alembic" / "versions"


def _declarations(path: Path) -> tuple[str, str | tuple[str, ...] | None]:
    """Extract revision and parent declarations without importing migrations."""
    tree = ast.parse(path.read_text(), filename=str(path))
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                values[target.id] = ast.literal_eval(value)

    revision = values["revision"]
    down_revision = values.get("down_revision")
    assert isinstance(revision, str)
    assert down_revision is None or isinstance(down_revision, str | tuple)
    return revision, down_revision


def _graph() -> tuple[dict[str, Path], dict[str, str | tuple[str, ...] | None]]:
    """Return revision declarations indexed by revision ID."""
    files: dict[str, Path] = {}
    parents: dict[str, str | tuple[str, ...] | None] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        revision, down_revision = _declarations(path)
        assert revision not in files, f"duplicate revision {revision}: {files[revision]} and {path}"
        files[revision] = path
        parents[revision] = down_revision
    return files, parents


def test_alembic_revision_ids_are_unique_and_parents_resolve() -> None:
    """Every migration ID is unique and every declared parent exists."""
    files, parents = _graph()
    revisions = set(files)
    missing: list[tuple[str, str]] = []
    for revision, parent in parents.items():
        parent_ids = () if parent is None else (parent,) if isinstance(parent, str) else parent
        missing.extend((revision, parent_id) for parent_id in parent_ids if parent_id not in revisions)

    assert not missing, f"unresolvable Alembic parents: {missing}"


def test_alembic_revision_graph_has_exactly_one_head() -> None:
    """The complete migration graph must converge to one upgrade head."""
    files, parents = _graph()
    referenced: set[str] = set()
    for parent in parents.values():
        if parent is None:
            continue
        referenced.update((parent,) if isinstance(parent, str) else parent)

    heads = set(files) - referenced
    assert len(heads) == 1, f"expected one Alembic head, found {sorted(heads)}"
