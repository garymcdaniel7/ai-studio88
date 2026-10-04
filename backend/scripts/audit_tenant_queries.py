"""Audit direct tenant query boundaries without importing application runtime code.

This tool is intentionally outside the request path. It inventories direct
Supabase/SQLAlchemy-style table calls, dynamic table wrappers, worker lifecycle
operations, and optional-auth call sites. Every finding receives exactly one
classification. Unscoped tenant findings are reported as BLOCKED rather than
being hidden behind RLS assumptions.

Usage:
    uv run python backend/scripts/audit_tenant_queries.py
    uv run python backend/scripts/audit_tenant_queries.py --check
"""
from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
DEFAULT_OUTPUT = REPO_ROOT / "docs/architecture/AUTH_TENANT_QUERY_AUDIT.md"

TENANT_TABLES = frozenset(
    {
        "assets",
        "content_jobs",
        "jobs",
        "lora_versions",
        "models",
        "organizations",
        "publishing_posts",
        "scenes",
        "shots",
        "storyboards",
        "talent",
        "talent_loras",
        "talent_relationships",
    }
)
SHARED_TABLES = frozenset(
    {
        "lora_catalog",
        "platform_packages",
        "system_settings",
    }
)
API_V1_FINDINGS = (
    "talent list/detail/mutation",
    "scenes and shots",
    "lora_versions",
    "assets and generation history",
    "storyboards list/detail/mutation",
    "talent media",
    "talent LoRA assignments",
    "talent relationships",
    "model list/detail/mutation",
    "production assembly",
    "generation job lifecycle",
    "project compatibility routes",
    "search aggregate",
    "video source assets",
    "story memory inherited reads",
    "workflow parent validation",
    "worker jobs poll/claim",
    "worker jobs complete/fail",
    "related database/data_access helpers",
)


@dataclass(frozen=True)
class Finding:
    """One source-level query or optional-auth audit finding."""

    path: str
    line: int
    symbol: str
    operation: str
    table: str
    classification: str
    evidence: str
    status: str


def _literal_table(call: ast.Call) -> str:
    """Return a literal table name or a safe dynamic marker."""
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return "<dynamic>"


def _symbol(tree: ast.AST, line: int) -> str:
    """Return the nearest enclosing function/class symbol."""
    symbols: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            end = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= line <= end:
                symbols.append(getattr(node, "name", type(node).__name__))
    return ".".join(symbols[-2:]) or "module"


def _call_name(call: ast.Call) -> str:
    """Return the final attribute/name component for a call."""
    target = call.func
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Name):
        return target.id
    return "<call>"


def _classify(path: Path, table: str, window: str, operation: str) -> tuple[str, str, str]:
    """Classify one finding and return classification, evidence, status."""
    if table in SHARED_TABLES:
        return (
            "SYSTEM_SHARED_EXEMPTION",
            f"{table} is listed as shared/reference data; owner and write policy require review",
            "EXEMPT_DOCUMENTED",
        )
    if path.name == "worker.py" and table == "jobs" and '"org_id"' in window:
        return (
            "WORKER_LIFECYCLE_SCOPED",
            "worker lifecycle query includes a trusted org_id predicate",
            "PROVEN",
        )
    if path.name in {"data_access.py", "tenant_repo.py"}:
        return (
            "APPROVED_SCOPED_WRAPPER",
            "central tenant boundary/helper is the approved query wrapper",
            "PROVEN" if '"org_id"' in window or "parent" in window.lower() else "BLOCKED",
        )
    if re.search(r"\.eq\(\s*['\"](?:org_id|organization_id)['\"]", window):
        return (
            "DIRECT_ORG_PREDICATE",
            "source window contains an explicit application organization predicate",
            "PROVEN",
        )
    if re.search(r"parent|owned|trusted_org|tenant", window, re.IGNORECASE) and table not in TENANT_TABLES:
        return (
            "INHERITED_PARENT_PROOF",
            "source window names an inherited ownership or trusted-tenant proof",
            "PROVEN",
        )
    if table in TENANT_TABLES or table == "<dynamic>":
        return (
            "UNSCOPED_REQUIRES_REMEDIATION",
            "no application predicate/parent proof was found; RLS alone is not accepted",
            "BLOCKED",
        )
    return (
        "NON_TENANT_REVIEW",
        f"{table} is not in the known tenant table set; owner classification requires review",
        "BLOCKED",
    )


def collect_findings() -> list[Finding]:
    """Collect deterministic query and optional-auth findings from backend code."""
    findings: list[Finding] = []
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        if any(part in {".venv", "__pycache__"} for part in path.parts) or "/tests/" in str(path):
            continue
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            findings.append(
                Finding(
                    str(path.relative_to(REPO_ROOT)),
                    exc.lineno or 1,
                    "module",
                    "parse",
                    "<syntax>",
                    "AUDIT_PARSE_ERROR",
                    str(exc),
                    "BLOCKED",
                )
            )
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            operation = _call_name(node)
            if operation not in {"table", "from_"}:
                continue
            line = node.lineno
            start = max(0, line - 16)
            end = min(len(lines), line + 16)
            window = "\n".join(lines[start:end])
            table = _literal_table(node)
            classification, evidence, status = _classify(path, table, window, operation)
            findings.append(
                Finding(
                    str(path.relative_to(REPO_ROOT)),
                    line,
                    _symbol(tree, line),
                    operation,
                    table,
                    classification,
                    evidence,
                    status,
                )
            )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Name) or node.id != "optional_auth":
                continue
            line = node.lineno
            start = max(0, line - 12)
            end = min(len(lines), line + 12)
            window = "\n".join(lines[start:end])
            tenant_path = bool(re.search(r"org_id|tenant|asset|talent|job|post", window, re.IGNORECASE))
            findings.append(
                Finding(
                    str(path.relative_to(REPO_ROOT)),
                    line,
                    _symbol(tree, line),
                    "optional_auth",
                    "<optional-auth>",
                    "OPTIONAL_AUTH_TENANT_PATH" if tenant_path else "OPTIONAL_AUTH_NON_TENANT_PATH",
                    "optional-auth call site is reviewed for null-org behavior",
                    "BLOCKED" if tenant_path else "PROVEN",
                )
            )
    return sorted(findings, key=lambda item: (item.path, item.line, item.operation))


def render(findings: list[Finding]) -> str:
    """Render the audit evidence as a reviewable Markdown artifact."""
    blocked = sum(item.status == "BLOCKED" for item in findings)
    proven = sum(item.status == "PROVEN" for item in findings)
    exempt = sum(item.status == "EXEMPT_DOCUMENTED" for item in findings)
    rows = [
        "# Repository Query Audit Evidence",
        "",
        "Generated by `backend/scripts/audit_tenant_queries.py`; this artifact is source evidence, not a claim of staging acceptance.",
        "",
        f"- Findings: **{len(findings)}** (proven {proven}, documented exemptions {exempt}, blocked {blocked})",
        "- Unknown findings are not emitted: every row has exactly one classification.",
        "- `BLOCKED` means an application predicate/parent proof was not demonstrated; RLS-only access is not accepted.",
        "- The 19+ API V1 findings are tracked in `docs/architecture/AUTH_TENANT_QUERY_INVENTORY.md`; the required audit set is:",
        *[f"  - {item}" for item in API_V1_FINDINGS],
        "",
        "| File | Line | Symbol | Operation | Table | Classification | Evidence | Status |",
        "|---|---:|---|---|---|---|---|---|",
    ]
    for item in findings:
        rows.append(
            "| "
            + " | ".join(
                (
                    item.path,
                    str(item.line),
                    item.symbol,
                    item.operation,
                    item.table,
                    item.classification,
                    item.evidence.replace("|", "\\|"),
                    item.status,
                )
            )
            + " |"
        )
    rows.extend(
        [
            "",
            "## Gate result",
            "",
            "`BLOCKED` until every tenant-owned occurrence is proven scoped or has a separately approved system/shared exemption. Local unit tests and RLS do not close this gate.",
            "",
        ]
    )
    return "\n".join(rows)


def main() -> int:
    """Write audit evidence and optionally fail on blocked findings."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="return non-zero when any finding is blocked")
    args = parser.parse_args()
    findings = collect_findings()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(findings), encoding="utf-8")
    blocked = [item for item in findings if item.status == "BLOCKED"]
    print(f"audit findings={len(findings)} blocked={len(blocked)} output={args.output}")
    return 1 if args.check and blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
