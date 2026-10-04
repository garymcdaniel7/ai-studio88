#!/usr/bin/env python3
"""
validate_mcp_vs_spec.py — Verifies that every MCP tool definition maps 1:1
to an operation in gen-bridge.yaml.

Usage:
    python scripts/validate_mcp_vs_spec.py \
        --spec docs/specs/gen-bridge.yaml \
        --tools docs/specs/mcp-tools.json

Checks performed:
    1. Every tool in mcp-tools.json maps to a spec operationId.
    2. Every non-internal spec operation has a tool.
    3. Tool input params are a subset of the spec's declared params.
    4. LIVE REGISTRY: every tool actually served by backend/aios/mcp/tools.py
       maps to a spec operationId, and vice versa.

Check 4 matters because checks 1-3 only compare two documents to each other.
Both can agree perfectly while the running MCP server serves a completely
different tool set — which is the current state of this repo. Use
--allow-live-drift to downgrade check 4 to a warning during migration.

Exit code: 0 = all tools verified, 1 = mismatches found.
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

# Running this file directly puts scripts/ on sys.path rather than the repo
# root, which makes `import backend.*` fail. Add the repo root explicitly so
# the live-registry check can import the tool registry.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def load_yaml(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_json(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def spec_operation_ids(spec: dict) -> set[str]:
    """Extract all operationIds from the OpenAPI spec."""
    ops = set()
    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if isinstance(details, dict) and "operationId" in details:
                ops.add(details["operationId"])
    return ops


def mcp_tool_names(tools_def: dict) -> set[str]:
    """Extract all tool names from the MCP tools definition."""
    return {t["name"] for t in tools_def.get("tools", [])}


def live_tool_names() -> set[str]:
    """Extract tool names from the live MCP registry actually served by the API.

    Imported lazily so the document-only checks still run in environments
    where the backend package is not importable.
    """
    from backend.aios.mcp.tools import MCP_TOOLS

    return {t.name for t in MCP_TOOLS}


def check_live_registry(spec: dict, strict: bool) -> bool:
    """Compare the live MCP tool registry against the spec operationIds.

    Returns True if the live registry is consistent with the spec (or if
    drift is permitted via strict=False).
    """
    marker = "❌" if strict else "⚠ "

    print("\n Live Registry (backend/aios/mcp/tools.py):")
    try:
        live = live_tool_names()
    except ImportError as exc:
        print(f"  ⚠  could not import live registry: {exc}")
        print("     (skipping — run from the repo root with the backend installed)")
        return True

    spec_ops = spec_operation_ids(spec)
    missing_in_spec = sorted(live - spec_ops)
    missing_in_live = sorted(spec_ops - live)

    print(f"  live tools: {len(live)}  |  spec operations: {len(spec_ops)}")

    if not missing_in_spec and not missing_in_live:
        print("  ✓ live registry matches spec exactly")
        return True

    for name in missing_in_spec:
        print(f"  {marker} live tool '{name}' has no matching operationId in spec")
    for op_id in missing_in_live:
        print(f"  {marker} spec operation '{op_id}' is not served by the live registry")

    if not (live & spec_ops):
        print(
            "\n  ‼  ZERO overlap between the live registry and the spec."
            "\n     The spec and mcp-tools.json agree with each other but describe"
            "\n     a different system than the one actually running. Reconcile"
            "\n     naming (live uses snake_case, spec uses camelCase) before"
            "\n     treating this spec as the source of truth."
        )

    return not strict


def _find_spec_operation(spec: dict, op_id: str) -> dict | None:
    """Find a spec operation by operationId, returning its full method block."""
    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if isinstance(details, dict) and details.get("operationId") == op_id:
                return details
    return None


def _collect_all_spec_params(spec_op: dict) -> dict[str, dict]:
    """Collect all spec-defined parameters (path, query, requestBody) into a flat map."""
    all_params: dict[str, dict] = {}

    # 1. Path and query parameters
    for param in spec_op.get("parameters", []):
        name = param.get("name", "")
        all_params[name] = {
            "in": param.get("in", "query"),
            "required": param.get("required", False),
        }

    # 2. RequestBody parameters
    req_body = spec_op.get("requestBody", {})
    content = req_body.get("content", {})
    json_schema = content.get("application/json", {}).get("schema", {})
    for prop_name, prop_schema in json_schema.get("properties", {}).items():
        all_params[prop_name] = {
            "in": "body",
            "required": prop_name in json_schema.get("required", []),
            "schema": prop_schema,
        }

    return all_params


def check_spec_parameter_coverage(
    spec: dict, tool: dict
) -> list[str]:
    """Check that MCP input params are a subset of ALL spec-defined parameters."""
    issues = []
    op_id = tool["name"]
    spec_op = _find_spec_operation(spec, op_id)

    if not spec_op:
        return [f"Operation '{op_id}' not found in spec"]

    spec_params = _collect_all_spec_params(spec_op)
    mcp_props = tool.get("inputSchema", {}).get("properties", {})
    mcp_required = set(tool.get("inputSchema", {}).get("required", []))

    # ── Check every MCP parameter exists in spec ─────────────────────────
    for param_name in mcp_props:
        if param_name not in spec_params:
            issues.append(
                f"  PARAM '{param_name}' in MCP tool '{op_id}' not found in spec"
                f" (neither in parameters nor requestBody)"
            )

    # ── Check required params match ──────────────────────────────────────
    for req_param in mcp_required:
        if req_param in spec_params:
            spec_req = spec_params[req_param]["required"]
            if not spec_req:
                issues.append(
                    f"  REQUIRED '{req_param}' in MCP tool '{op_id}' "
                    f"but optional in spec"
                )
        else:
            # Already flagged above; don't double-report
            pass

    return issues


def validate(spec_path: str, tools_path: str, strict_live: bool = True) -> bool:
    spec = load_yaml(spec_path)
    tools_def = load_json(tools_path)

    spec_ops = spec_operation_ids(spec)
    tool_names = mcp_tool_names(tools_def)

    all_ok = True

    print(f"\n{'='*60}")
    print(f" MCP ↔ Spec Validation")
    print(f"  Spec:  {spec_path} ({len(spec_ops)} operations)")
    print(f"  Tools: {tools_path} ({len(tool_names)} tools)")
    print(f"{'='*60}")

    # 1. Every tool must have a matching operationId in spec
    for name in sorted(tool_names):
        if name not in spec_ops:
            print(f"  ❌ MCP tool '{name}' has no matching operationId in spec")
            all_ok = False
        else:
            print(f"  ✓ '{name}' → matched to spec operationId")

    # 2. Every production-relevant spec operation should have a tool
    # (skip internal operations like claimJob, heartbeat, completeJob, failJob)
    internal_ops = {"claimJob", "jobHeartbeat", "completeJob", "failJob"}
    for op_id in sorted(spec_ops):
        if op_id in tool_names:
            continue
        if op_id in internal_ops:
            print(f"  ~ '{op_id}' → internal (no MCP tool needed)")
            continue
        print(f"  ⚠  Spec operation '{op_id}' has no MCP tool")
        all_ok = False

    # 3. Parameter coverage check
    print(f"\n Parameter Coverage:")
    tools_list = tools_def.get("tools", [])
    for tool in sorted(tools_list, key=lambda t: t["name"]):
        if tool["name"] not in spec_ops:
            continue
        issues = check_spec_parameter_coverage(spec, tool)
        if issues:
            print(f"  ❌ {tool['name']}:")
            for issue in issues:
                print(f"     {issue}")
            all_ok = False
        else:
            print(f"  ✓ {tool['name']}: params match spec")

    # 4. Live registry check — the only check that looks at running code
    if not check_live_registry(spec, strict_live):
        all_ok = False

    print(f"\n{'='*60}")
    if all_ok:
        print(" RESULT: ✓ All MCP tools verified against spec")
    else:
        print(" RESULT: ❌ Mismatches found — fix before deployment")
    print(f"{'='*60}\n")

    return all_ok


def main():
    parser = argparse.ArgumentParser(
        description="Validate MCP tools against OpenAPI spec"
    )
    parser.add_argument(
        "--spec",
        default="docs/specs/gen-bridge.yaml",
        help="Path to OpenAPI spec (YAML)",
    )
    parser.add_argument(
        "--tools",
        default="docs/specs/mcp-tools.json",
        help="Path to MCP tools definition (JSON)",
    )
    parser.add_argument(
        "--allow-live-drift",
        action="store_true",
        help=(
            "Report live-registry drift as a warning instead of failing. "
            "Use during migration while the live tools are reconciled with the spec."
        ),
    )
    args = parser.parse_args()

    ok = validate(args.spec, args.tools, strict_live=not args.allow_live_drift)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
